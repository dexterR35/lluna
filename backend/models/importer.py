"""Analyze and atomically import Hugging Face or local models."""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

from backend.core.atomic import atomic_write_json
from backend.models.dynamic_registry import DynamicModelRegistry
from backend.models.manifest import (
    MANIFEST_FILENAME,
    HardwareRequirement,
    ManifestError,
    ModelManifest,
    ModelSource,
    RuntimeRequirement,
    SecurityPolicy,
    inferred_manifest,
    model_files,
    normalize_model_id,
)
from backend.models.runtime_profiles import runtime_status

_HF_URL = re.compile(
    r"^(?:https?://)?(?:www\.)?huggingface\.co/([^/\s]+)/([^/?#\s]+)(?:/.*)?$",
    re.IGNORECASE,
)
_SAFE_METADATA_EXTENSIONS = {
    ".json", ".txt", ".model", ".tiktoken", ".md", ".yaml", ".yml",
    ".safetensors", ".onnx", ".vocab", ".merges",
}


def parse_hf_repo(value: str) -> str:
    raw = str(value or "").strip().rstrip("/")
    match = _HF_URL.match(raw)
    if match:
        raw = f"{match.group(1)}/{match.group(2)}"
    parts = raw.split("/")
    if len(parts) != 2 or any(not part or part in {".", ".."} for part in parts):
        raise ValueError("Enter a Hugging Face URL or owner/model repository id.")
    return raw


def _adapter_for(library: str, pipeline: str, filenames: list[str]) -> tuple[str, str, str]:
    library = library.lower()
    pipeline = pipeline.lower()
    if library == "diffusers" or "model_index.json" in filenames:
        task = pipeline if pipeline in {"text-to-image", "image-to-image", "inpainting"} else "text-to-image"
        return "diffusers", "diffusers-torch", task
    if library in {"transformers", "sentence-transformers"} or "config.json" in filenames:
        known = {
            "image-segmentation", "object-detection", "text-generation",
            "automatic-speech-recognition", "text-to-image",
        }
        return "transformers", "transformers-torch", pipeline if pipeline in known else "custom"
    if any(name.endswith(".onnx") for name in filenames):
        return "onnx", "onnx-runtime", pipeline if pipeline else "custom"
    return "python-worker", "custom-python", "custom"


def _card_value(card: object, key: str, default: Any = "") -> Any:
    if isinstance(card, Mapping):
        return card.get(key, default)
    return getattr(card, key, default)


def analyze_huggingface(value: str, *, revision: str = "") -> dict:
    from huggingface_hub import HfApi

    from backend.tools.hf_auth import resolve_hf_token

    repo = parse_hf_repo(value)
    token = resolve_hf_token()
    info = HfApi(token=token).model_info(
        repo_id=repo,
        revision=revision or None,
        files_metadata=True,
        token=token,
    )
    siblings = list(getattr(info, "siblings", ()) or ())
    filenames = [str(getattr(item, "rfilename", "")) for item in siblings]
    card = getattr(info, "card_data", None)
    library = str(getattr(info, "library_name", "") or _card_value(card, "library_name") or "")
    pipeline = str(getattr(info, "pipeline_tag", "") or _card_value(card, "pipeline_tag") or "")
    adapter, runtime, task = _adapter_for(library, pipeline, filenames)
    selected = [
        name for name in filenames
        if Path(name).suffix.lower() in _SAFE_METADATA_EXTENSIONS
        or "/tokenizer" in name
        or name.startswith("tokenizer")
    ]
    # Avoid executing or unpickling arbitrary repository contents by default.
    selected = [name for name in selected if not name.endswith((".bin", ".pth", ".pt", ".ckpt", ".py"))]
    safe_weight_suffix = ".onnx" if adapter == "onnx" else ".safetensors"
    has_safe_weights = any(name.endswith(safe_weight_suffix) for name in selected)
    blocking_reasons = []
    if adapter in {"diffusers", "transformers", "onnx"} and not has_safe_weights:
        blocking_reasons.append(
            f"This repository does not expose {safe_weight_suffix} weights that Midgard can load safely."
        )
    if adapter == "python-worker":
        blocking_reasons.append(
            "Midgard could not identify a safe supported adapter for this repository. Import it locally with a reviewed manifest."
        )
    size_by_name = {
        str(getattr(item, "rfilename", "")): int(getattr(item, "size", 0) or 0)
        for item in siblings
    }
    total_size = sum(size_by_name.get(name, 0) for name in selected)
    license_name = str(_card_value(card, "license") or "See upstream model card")
    gated = bool(getattr(info, "gated", False))
    author, repo_name = repo.split("/", 1)
    identifier = normalize_model_id(f"hf-{author}-{repo_name}")
    minimum_vram = 0
    if total_size:
        minimum_vram = int(min(max(total_size / (1024 * 1024) * 0.65, 0), 98304))
    backends = ("cuda", "mps", "cpu") if adapter in {"diffusers", "transformers"} else ("cpu", "cuda", "directml")
    from backend.models.capability_resolver import (
        huggingface_metadata_contract,
        reviewed_huggingface_contract,
    )

    revision_sha = str(getattr(info, "sha", "") or revision)
    reviewed = reviewed_huggingface_contract(repo)
    if reviewed is not None:
        variant, capabilities = reviewed
    else:
        tags = tuple(getattr(info, "tags", ()) or ())
        base_model_raw = _card_value(card, "base_model", "")
        base_model = (
            str(base_model_raw[0]) if isinstance(base_model_raw, list) and base_model_raw
            else str(base_model_raw or "")
        )
        # ModelInfo.config is declarative Hub metadata returned with model_info;
        # no repository code or weights are downloaded during analysis.
        info_config = getattr(info, "config", None)
        configs = [info_config] if isinstance(info_config, Mapping) else []
        variant, capabilities = huggingface_metadata_contract(
            task=task,
            adapter=adapter,
            tags=tags,
            base_model=base_model,
            configs=configs,
        )
    unresolved = capabilities.unresolved(task)
    manifest = ModelManifest(
        id=identifier,
        name=repo_name.replace("-", " ").replace("_", " ").title(),
        description=f"{pipeline.replace('-', ' ').title() if pipeline else 'Hugging Face model'} by {author}",
        task=task,
        adapter=adapter,
        source=ModelSource(
            "huggingface",
            repo=repo,
            revision=revision_sha,
            allow_patterns=tuple(selected),
        ),
        runtime=RuntimeRequirement(runtime, isolated=runtime == "custom-python"),
        hardware=HardwareRequirement(
            backends=backends,
            minimum_vram_mb=minimum_vram,
            minimum_disk_mb=int(total_size / (1024 * 1024) * 1.1) if total_size else 0,
        ),
        security=SecurityPolicy(False, True, False),
        variant=variant,
        capabilities=capabilities,
        license=license_name,
        gated=gated,
        expected_files=tuple(selected),
        expected_size_bytes=total_size or None,
        needs_configuration=adapter == "python-worker" or bool(unresolved),
    )
    return _analysis(
        manifest,
        repo_url=f"https://huggingface.co/{repo}",
        blockingReasons=blocking_reasons,
        installable=not blocking_reasons,
        capabilityUnresolved=list(unresolved),
    )


def analyze_local(path: Path) -> dict:
    source = path.expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(source)
    if source.is_file() and not model_files(source):
        raise ValueError("Choose a supported model file (.safetensors, .onnx, .pth, .pt, .ckpt, or .bin).")
    manifest_path = source / MANIFEST_FILENAME if source.is_dir() else None
    manifest = (
        ModelManifest.from_file(manifest_path)
        if manifest_path and manifest_path.is_file()
        else inferred_manifest(source)
    )
    if manifest.capabilities.provenance == "unknown":
        from backend.models.capability_resolver import inspect_local_contract

        variant, capabilities = inspect_local_contract(
            source, task=manifest.task, adapter=manifest.adapter
        )
        manifest = replace(
            manifest,
            variant=variant,
            capabilities=capabilities,
        )
    total = sum(item.stat().st_size for item in model_files(source))
    manifest = replace(
        manifest,
        source=ModelSource("local", local_name=source.name),
        expected_size_bytes=total or manifest.expected_size_bytes,
        needs_configuration=(
            manifest.needs_configuration
            or not manifest.capabilities.is_complete(manifest.task)
        ),
    )
    return _analysis(manifest, local_path=str(source))


def _analysis(manifest: ModelManifest, **extra: Any) -> dict:
    return {
        "manifest": manifest.to_dict(),
        "runtime": runtime_status(manifest),
        "downloadBytes": manifest.expected_size_bytes,
        "license": manifest.license,
        "gated": manifest.gated,
        "requiresConfiguration": manifest.needs_configuration,
        "securityWarnings": [
            *(["Remote repository code will not be executed."] if manifest.source.type == "huggingface" else []),
            *(["This model contains a legacy pickle-capable weight format."] if manifest.security.allow_pickle else []),
        ],
        **extra,
    }


def configure_manifest(raw: Mapping[str, Any]) -> ModelManifest:
    manifest = ModelManifest.from_mapping(raw)
    from backend.configuration.service import get_settings

    policy = get_settings().models
    if manifest.security.trust_remote_code and not policy.allow_remote_code:
        raise ManifestError("Remote repository code is disabled in Model platform settings.")
    if manifest.security.allow_pickle and not policy.allow_pickle_weights:
        raise ManifestError("Pickle-capable model weights are disabled in Model platform settings.")
    if manifest.runtime.isolated and not policy.isolate_custom_dependencies:
        raise ManifestError("Custom dependency isolation is disabled in Model platform settings.")
    issues = manifest.configuration_issues()
    if issues:
        raise ManifestError(
            "Confirm the model capabilities before installation; unresolved: "
            + ", ".join(issues)
        )
    if manifest.source.type == "huggingface":
        if manifest.adapter == "python-worker":
            raise ManifestError(
                "Custom Hugging Face execution code must be imported locally with a reviewed manifest."
            )
        suffix = ".onnx" if manifest.adapter == "onnx" else ".safetensors"
        if manifest.adapter in {"diffusers", "transformers", "onnx"} and not any(
            name.endswith(suffix) for name in manifest.expected_files
        ):
            raise ManifestError(
                f"The Hugging Face repository has no safe {suffix} weights for this adapter."
            )
    runtime_adapter = {
        "diffusers-torch": "diffusers",
        "transformers-torch": "transformers",
        "onnx-runtime": "onnx",
        "paddle": "paddle",
        "midgard-native": "midgard-native",
        "custom-python": "python-worker",
    }.get(manifest.runtime.profile)
    if runtime_adapter != manifest.adapter:
        raise ManifestError("The selected runtime profile does not match the model adapter.")
    return manifest


def register_huggingface(raw: Mapping[str, Any]) -> ModelManifest:
    manifest = configure_manifest(raw)
    if manifest.source.type != "huggingface":
        raise ManifestError("Expected a Hugging Face model manifest.")
    DynamicModelRegistry.instance().register(manifest)
    return manifest


def import_local(source: Path, raw: Mapping[str, Any]) -> ModelManifest:
    source = source.expanduser().resolve()
    manifest = configure_manifest(raw)
    registry = DynamicModelRegistry.instance()
    target = registry.root / manifest.id
    staging = registry.staging_root / f"{manifest.id}-{os.getpid()}"
    if staging.exists():
        shutil.rmtree(staging)
    try:
        if source.is_dir():
            shutil.copytree(source, staging, ignore=shutil.ignore_patterns(".git", "__pycache__", ".cache"))
        elif source.is_file():
            staging.mkdir(parents=True)
            shutil.copy2(source, staging / source.name)
        else:
            raise FileNotFoundError(source)
        local_manifest = replace(
            manifest,
            source=ModelSource("local", local_name=source.name),
            needs_configuration=False,
        )
        atomic_write_json(staging / MANIFEST_FILENAME, local_manifest.to_dict())
        (staging / ".midgard-installed").write_text("local\n", encoding="utf-8")
        _promote(staging, target)
        registry.scan()
        from backend.configuration.service import get_settings
        if get_settings().models.auto_enable_imports:
            registry.set_enabled(local_manifest.id, True)
        return local_manifest
    except Exception:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        raise


def install_huggingface(manifest: ModelManifest) -> Path:
    if manifest.source.type != "huggingface":
        raise ValueError("This model is not backed by Hugging Face.")
    if manifest.needs_configuration:
        raise ValueError("Configure this model before installation.")
    if manifest.security.trust_remote_code:
        raise PermissionError("Remote repository code is disabled by Midgard policy.")
    from backend.tools.hf_auth import snapshot_download_with_progress

    registry = DynamicModelRegistry.instance()
    target = registry.root / manifest.id
    staging = registry.staging_root / f"{manifest.id}-{os.getpid()}"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    try:
        snapshot_download_with_progress(
            repo_id=manifest.source.repo,
            local_dir=str(staging),
            allow_patterns=list(manifest.source.allow_patterns or ("*",)),
            revision=manifest.source.revision or None,
            ignore_patterns=["*.py", "*.ckpt", "*.pth", "*.pt", "*.bin"],
        )
        missing = [name for name in manifest.expected_files if not (staging / name).is_file()]
        if missing:
            raise RuntimeError("Downloaded snapshot is incomplete; missing: " + ", ".join(missing[:12]))
        cache = staging / ".cache"
        if cache.exists():
            shutil.rmtree(cache, ignore_errors=True)
        atomic_write_json(staging / MANIFEST_FILENAME, manifest.to_dict())
        (staging / ".midgard-installed").write_text(
            f"{manifest.source.repo}@{manifest.source.revision}\n", encoding="utf-8"
        )
        _promote(staging, target)
        registry.set_enabled(manifest.id, True)
        return target
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _promote(staging: Path, target: Path) -> None:
    backup = target.with_name(f".{target.name}.previous")
    if backup.exists():
        shutil.rmtree(backup)
    if target.exists():
        target.replace(backup)
    try:
        staging.replace(target)
    except Exception:
        if backup.exists() and not target.exists():
            backup.replace(target)
        raise
    shutil.rmtree(backup, ignore_errors=True)


def uninstall_dynamic(model_id: str) -> None:
    registry = DynamicModelRegistry.instance()
    record = registry.get(model_id)
    target = record.path.resolve()
    if registry.root.resolve() not in target.parents:
        raise PermissionError("Refusing to remove a model outside the custom model folder.")
    if target.is_dir():
        shutil.rmtree(target)
    elif target.is_file():
        target.unlink()
    registry.scan()
