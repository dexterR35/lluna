from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from backend.api.app import create_app
from backend.artifacts.store import DesktopGrantStore
from backend.core.paths import AppPaths
from backend.graph.registry import list_nodes
from backend.graph.schema import WorkflowDocument, WorkflowNode
from backend.graph.validation import validate_workflow
from backend.models.dynamic_registry import DynamicModelRegistry
from backend.models.importer import analyze_huggingface, configure_manifest, import_local
from backend.models.reference.capabilities import reviewed_huggingface_contract
from backend.models.reference.manifest import MANIFEST_FILENAME, ManifestError, ModelManifest
from backend.tools.installers import _shared


def paths(root: Path) -> AppPaths:
    config = root / "config"
    return AppPaths(
        project_root=root,
        config_dir=config,
        data_dir=root / "data",
        updates_dir=root / "data" / "updates",
        config_file=config / "config.json",
        runtime_config_file=config / "runtime.json",
        shipped_config_file=root / "defaults.json",
        models_dir=root / "models",
        runtime_file=config / "lluna_runtime.json",
    )


@pytest.fixture
def installed_runtimes(monkeypatch):
    """Report every model's runtime as present, whatever this machine has.

    The node catalog only offers a custom model whose runtime is runnable, so
    tests about what the catalog exposes would otherwise be testing whether
    diffusers and transformers happen to be installed. CI installs neither.
    """
    from backend.models.reference import runtimes

    real_status = runtimes.runtime_status

    def status(manifest) -> dict:
        return {**real_status(manifest), "installed": True, "runnable": True, "reasons": []}

    monkeypatch.setattr(runtimes, "runtime_status", status)


def safetensors_manifest(identifier: str = "local-transformers") -> dict:
    return {
        "schema": 1,
        "id": identifier,
        "name": "Local Transformers",
        "description": "Test model",
        "task": "image-restoration",
        "adapter": "transformers",
        "source": {"type": "local", "localName": "model.safetensors"},
        "runtime": {"profile": "transformers-torch"},
        "hardware": {"backends": ["cpu"]},
        "security": {"trustRemoteCode": False, "allowPickle": False},
        "variant": {"kind": "base"},
        "capabilities": {
            "provenance": "reviewed-manifest",
            "tasks": ["image-restoration"],
            "inputs": ["image"],
            "outputs": ["image"],
            "dtypes": ["fp32"],
        },
        "expectedFiles": ["model.safetensors"],
        "needsConfiguration": False,
    }


def test_manifest_rejects_traversal_and_remote_code_policy() -> None:
    raw = safetensors_manifest()
    raw["expectedFiles"] = ["../outside.safetensors"]
    with pytest.raises(ManifestError, match="inside"):
        ModelManifest.from_mapping(raw)

    raw = safetensors_manifest()
    raw["security"]["trustRemoteCode"] = True
    with pytest.raises(ManifestError, match="disabled"):
        configure_manifest(raw)


def test_scanner_surfaces_unconfigured_folder_then_accepts_manifest(tmp_path) -> None:
    registry = DynamicModelRegistry(paths(tmp_path))
    folder = registry.root / "restorer"
    folder.mkdir()
    (folder / "model.safetensors").write_bytes(b"weights")
    (folder / "config.json").write_text("{}", encoding="utf-8")

    record = registry.scan()[0]
    assert record.manifest.id == "restorer"
    assert record.manifest.needs_configuration
    assert record.installed

    raw = safetensors_manifest("restorer")
    registry.configure("restorer", ModelManifest.from_mapping(raw))
    configured = registry.get("restorer")
    assert not configured.manifest.needs_configuration
    assert (folder / MANIFEST_FILENAME).is_file()


def test_local_file_import_is_promoted_into_managed_folder(tmp_path, monkeypatch) -> None:
    registry = DynamicModelRegistry(paths(tmp_path))
    monkeypatch.setattr(DynamicModelRegistry, "_instance", registry)
    source = tmp_path / "outside" / "model.safetensors"
    source.parent.mkdir()
    source.write_bytes(b"safe-weights")

    manifest = import_local(source, safetensors_manifest())
    target = registry.root / manifest.id
    assert (target / "model.safetensors").read_bytes() == b"safe-weights"
    assert (target / ".lluna-installed").is_file()
    assert registry.get(manifest.id).installed


def test_huggingface_analysis_pins_revision_and_filters_executable_files(monkeypatch) -> None:
    huggingface_hub = pytest.importorskip("huggingface_hub")

    info = SimpleNamespace(
        siblings=[
            SimpleNamespace(rfilename="model_index.json", size=100),
            SimpleNamespace(rfilename="transformer/model.safetensors", size=2_000),
            SimpleNamespace(rfilename="README.md", size=200),
            SimpleNamespace(rfilename="pipeline.py", size=300),
            SimpleNamespace(rfilename="legacy.bin", size=400),
        ],
        card_data=SimpleNamespace(
            license="apache-2.0", library_name="diffusers", pipeline_tag="text-to-image"
        ),
        library_name="diffusers",
        pipeline_tag="text-to-image",
        gated=False,
        sha="abc123",
    )
    monkeypatch.setattr(huggingface_hub.HfApi, "model_info", lambda *_args, **_kwargs: info)
    result = analyze_huggingface("https://huggingface.co/example/image-model")
    source = result["manifest"]["source"]
    assert source["revision"] == "abc123"
    assert "transformer/model.safetensors" in source["allowPatterns"]
    assert "pipeline.py" not in source["allowPatterns"]
    assert "legacy.bin" not in source["allowPatterns"]
    assert result["manifest"]["security"]["trustRemoteCode"] is False
    assert result["manifest"]["needsConfiguration"] is True
    assert result["manifest"]["capabilities"]["provenance"] == "huggingface-metadata"


def test_enabled_custom_diffusers_model_is_added_to_generate_node(
    tmp_path, monkeypatch, installed_runtimes
) -> None:
    registry = DynamicModelRegistry(paths(tmp_path))
    monkeypatch.setattr(DynamicModelRegistry, "_instance", registry)
    folder = registry.root / "custom-image"
    folder.mkdir()
    (folder / "model_index.json").write_text("{}", encoding="utf-8")
    (folder / "model.safetensors").write_bytes(b"weights")
    raw = {
        "schema": 1,
        "id": "custom-image",
        "name": "Custom Image",
        "task": "text-to-image",
        "adapter": "diffusers",
        "source": {"type": "local", "localName": "custom-image"},
        "runtime": {"profile": "diffusers-torch"},
        "hardware": {"backends": ["cpu", "cuda", "mps"]},
        "security": {},
        "variant": {"kind": "distilled"},
        "capabilities": {
            "provenance": "reviewed-manifest",
            "tasks": ["text-to-image"],
            "inputs": ["prompt"],
            "outputs": ["image"],
            "negativePrompt": False,
            "guidance": False,
            "seed": True,
            "steps": {"default": 4, "minimum": 1, "maximum": 8},
            "supportedWidths": [512, 768, 1024],
            "supportedHeights": [512, 768, 1024],
            "dtypes": ["fp32"],
        },
        "expectedFiles": ["model_index.json", "model.safetensors"],
    }
    (folder / MANIFEST_FILENAME).write_text(__import__("json").dumps(raw), encoding="utf-8")
    registry.scan()
    registry.set_enabled("custom-image", True)

    generate = next(node for node in list_nodes() if node.schema_id == "lluna.generate.image")
    model = next(parameter for parameter in generate.parameters if parameter.id == "model")
    assert any(option["value"] == "custom:custom-image" for option in model.options)


def test_enabled_custom_vision_language_model_is_added_to_describe_image_node(
    tmp_path, monkeypatch, installed_runtimes
) -> None:
    registry = DynamicModelRegistry(paths(tmp_path))
    monkeypatch.setattr(DynamicModelRegistry, "_instance", registry)
    folder = registry.root / "custom-captioner"
    folder.mkdir()
    (folder / "config.json").write_text("{}", encoding="utf-8")
    (folder / "model.safetensors").write_bytes(b"weights")
    raw = {
        "schema": 1,
        "id": "custom-captioner",
        "name": "Custom Captioner",
        "task": "image-to-text",
        "adapter": "transformers",
        "source": {"type": "local", "localName": "custom-captioner"},
        "runtime": {"profile": "transformers-torch"},
        "hardware": {"backends": ["cpu", "cuda", "mps"]},
        "security": {},
        "variant": {"kind": "base"},
        "capabilities": {
            "provenance": "reviewed-manifest",
            "tasks": ["image-to-text"],
            "inputs": ["image"],
            "outputs": ["text"],
            "temperature": {"default": 0.2, "minimum": 0, "maximum": 1},
            "topP": {"default": 0.7, "minimum": 0, "maximum": 1},
            "maxNewTokens": {"default": 200, "minimum": 1, "maximum": 2000},
            "defaultInstruction": "Describe this image in detail.",
        },
        "expectedFiles": ["config.json", "model.safetensors"],
    }
    (folder / MANIFEST_FILENAME).write_text(json.dumps(raw), encoding="utf-8")
    registry.scan()
    registry.set_enabled("custom-captioner", True)

    describe = next(node for node in list_nodes() if node.schema_id == "lluna.input.describe_image")
    model = next(parameter for parameter in describe.parameters if parameter.id == "model")
    matched = next((option for option in model.options if option["value"] == "custom:custom-captioner"), None)
    assert matched is not None
    assert matched["capabilities"]["temperature"]["default"] == 0.2
    assert matched["capabilities"]["maxNewTokens"]["maximum"] == 2000


def test_reviewed_catalog_contract_precedes_metadata_and_is_complete() -> None:
    contract = reviewed_huggingface_contract("black-forest-labs/FLUX.2-klein-4B")
    assert contract is not None
    variant, capabilities = contract
    assert variant.kind == "distilled"
    assert capabilities.provenance == "reviewed-catalog"
    assert capabilities.steps is not None
    assert capabilities.steps.default == 4
    assert capabilities.guidance is False
    assert capabilities.is_complete("text-to-image")


def test_supir_reviewed_contract_and_checkpoint_import(tmp_path, monkeypatch) -> None:
    from backend.models.reference.capabilities import builtin_contract
    from backend.tools.installers import supir as supir_models

    monkeypatch.setattr(supir_models, "supir_root", lambda: tmp_path / "supir")
    source_q = tmp_path / "downloaded-q.ckpt"
    checkpoint = b"reviewed upstream checkpoint"
    source_q.write_bytes(checkpoint)
    monkeypatch.setitem(
        supir_models.CHECKPOINT_DOWNLOADS,
        "Q",
        {
            "repo": "test/supir",
            "revision": "abc123",
            "filename": "v0Q.ckpt",
            "size": len(checkpoint),
            "sha256": hashlib.sha256(checkpoint).hexdigest(),
        },
    )
    imported = supir_models.import_checkpoint(source_q, "Q")
    assert imported.name == "SUPIR-v0Q.ckpt"
    assert supir_models.readiness()["v0Q"] is True
    assert supir_models.is_model_installed() is False

    variant, capabilities = builtin_contract("supir")
    assert variant.architecture == "SUPIRModel"
    assert capabilities.scales == tuple(range(1, 9))
    assert capabilities.steps and capabilities.steps.maximum == 200
    assert capabilities.is_complete("image-upscaling")


def test_supir_checkpoint_download_is_revision_and_hash_pinned(tmp_path, monkeypatch) -> None:
    from backend.tools.installers import supir as supir_models
    from backend.tools.shared import huggingface as hf_auth

    checkpoint = b"small deterministic SUPIR fixture"
    monkeypatch.setattr(supir_models, "supir_root", lambda: tmp_path / "supir")
    monkeypatch.setitem(
        supir_models.CHECKPOINT_DOWNLOADS,
        "Q",
        {
            "repo": "test/supir",
            "revision": "pinned-commit",
            "filename": "v0Q.ckpt",
            "size": len(checkpoint),
            "sha256": hashlib.sha256(checkpoint).hexdigest(),
        },
    )
    downloads: list[dict] = []

    def fake_download(**kwargs):
        downloads.append(kwargs)
        target = Path(kwargs["local_dir"])
        target.mkdir(parents=True)
        (target / "v0Q.ckpt").write_bytes(checkpoint)
        return str(target)

    monkeypatch.setattr(hf_auth, "snapshot_download_with_progress", fake_download)

    installed = supir_models.download_checkpoint("Q")

    assert installed.read_bytes() == checkpoint
    assert downloads == [
        {
            "repo_id": "test/supir",
            "revision": "pinned-commit",
            "local_dir": str(tmp_path / "supir" / ".downloads" / "Q"),
            "allow_patterns": ["v0Q.ckpt"],
        }
    ]
    assert not (tmp_path / "supir" / ".downloads" / "Q").exists()


def test_supir_checkpoint_source_env_override_replaces_mirror(tmp_path, monkeypatch) -> None:
    from backend.tools.installers import supir as supir_models

    checkpoint = b"official checkpoint bytes"
    monkeypatch.setattr(supir_models, "supir_root", lambda: tmp_path / "supir")
    monkeypatch.setenv(
        supir_models.CHECKPOINT_SOURCE_ENV,
        json.dumps(
            {
                "repo": "official-org/SUPIR",
                "revision": "official-commit",
                "checkpoints": {
                    "Q": {
                        "filename": "official-v0Q.ckpt",
                        "size": len(checkpoint),
                        "sha256": hashlib.sha256(checkpoint).hexdigest(),
                    }
                },
            }
        ),
    )

    resolved_q = supir_models._resolve_checkpoint_download("Q")
    assert resolved_q == {
        "repo": "official-org/SUPIR",
        "revision": "official-commit",
        "filename": "official-v0Q.ckpt",
        "size": len(checkpoint),
        "sha256": hashlib.sha256(checkpoint).hexdigest(),
    }
    # F was not included in the override, so it still falls back to the default mirror.
    assert supir_models._resolve_checkpoint_download("F") == supir_models.CHECKPOINT_DOWNLOADS["F"]
    # SDXL always comes from the official stabilityai repo and is never overridden.
    assert supir_models._resolve_checkpoint_download("sdxl") == supir_models.CHECKPOINT_DOWNLOADS["sdxl"]


def test_supir_checkpoint_source_env_invalid_json_fails_clearly(monkeypatch) -> None:
    from backend.tools.installers import supir as supir_models

    monkeypatch.setenv(supir_models.CHECKPOINT_SOURCE_ENV, "{not valid json")

    with pytest.raises(RuntimeError, match="must be valid JSON"):
        supir_models._resolve_checkpoint_download("Q")


def test_supir_checkpoint_source_env_missing_fields_fails_clearly(monkeypatch) -> None:
    from backend.tools.installers import supir as supir_models

    monkeypatch.setenv(supir_models.CHECKPOINT_SOURCE_ENV, json.dumps({"repo": "only-repo"}))

    with pytest.raises(RuntimeError, match="needs 'repo', 'revision'"):
        supir_models._resolve_checkpoint_download("Q")


def test_supir_checkpoint_source_env_incomplete_entry_fails_clearly(monkeypatch) -> None:
    from backend.tools.installers import supir as supir_models

    monkeypatch.setenv(
        supir_models.CHECKPOINT_SOURCE_ENV,
        json.dumps(
            {
                "repo": "official-org/SUPIR",
                "revision": "official-commit",
                "checkpoints": {"Q": {"filename": "official-v0Q.ckpt"}},
            }
        ),
    )

    with pytest.raises(RuntimeError, match="needs a filename"):
        supir_models._resolve_checkpoint_download("Q")


def test_supir_checkpoint_source_env_unset_keeps_default_mirror(monkeypatch) -> None:
    from backend.tools.installers import supir as supir_models

    monkeypatch.delenv(supir_models.CHECKPOINT_SOURCE_ENV, raising=False)

    assert supir_models._resolve_checkpoint_download("Q") == supir_models.CHECKPOINT_DOWNLOADS["Q"]


@pytest.mark.skipif(os.name == "nt", reason="Uses a POSIX shell fixture")
def test_supir_finds_uv_python_when_desktop_path_is_minimal(tmp_path, monkeypatch) -> None:
    from backend.tools.installers import supir as supir_models

    python = tmp_path / ".local" / "bin" / "python3.10"
    python.parent.mkdir(parents=True)
    python.write_text("#!/bin/sh\nprintf '3.10\\n'\n", encoding="utf-8")
    python.chmod(0o755)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PATH", "")
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.delenv("LLUNA_SUPIR_PYTHON", raising=False)

    assert supir_models._bootstrap_python() == str(python.resolve())


def test_supir_rejects_configured_unsupported_python(tmp_path, monkeypatch) -> None:
    from backend.tools.installers import supir as supir_models

    if os.name == "nt":
        python = Path(sys.executable)
    else:
        python = tmp_path / "python3.12"
        python.write_text("#!/bin/sh\nprintf '3.12\\n'\n", encoding="utf-8")
        python.chmod(0o755)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PATH", "")
    monkeypatch.setenv("LLUNA_SUPIR_PYTHON", str(python))
    # Provisioning would otherwise download a real interpreter; this test is about
    # refusing the *configured* one, which test_supir_provisions_python covers next.
    monkeypatch.setattr(_shared, "provision_python", lambda version: None)

    with pytest.raises(RuntimeError, match="Python 3.8-3.10"):
        supir_models._bootstrap_python()


def test_supir_provisions_python_when_none_is_installed(tmp_path, monkeypatch) -> None:
    """A machine that has never installed Python 3.10 must still get a runtime."""
    from backend.tools.installers import supir as supir_models

    provisioned = tmp_path / "managed-python3.10"
    provisioned.write_text("#!/bin/sh\nprintf '3.10\\n'\n", encoding="utf-8")
    requested: list[str] = []

    def fake_provision(version: str) -> str:
        requested.append(version)
        return str(provisioned)

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PATH", "")
    monkeypatch.delenv("LLUNA_SUPIR_PYTHON", raising=False)
    monkeypatch.setattr(_shared, "provision_python", fake_provision)

    assert supir_models._bootstrap_python() == str(provisioned)
    assert requested == ["3.10"]


def test_looking_up_an_interpreter_never_downloads_one(monkeypatch) -> None:
    """Provisioning is an installer step, not a side effect of asking a question."""
    called = False

    def fake_provision(version: str) -> str | None:
        nonlocal called
        called = True
        return None

    monkeypatch.setattr(_shared, "provision_python", fake_provision)
    monkeypatch.setenv("PATH", "")

    with pytest.raises(RuntimeError):
        _shared.bootstrap_reviewed_python(
            env_var="LLUNA_UNUSED_PYTHON", versions=("3.10",), error_message="nope"
        )

    assert called is False


def test_bootstrap_skips_application_control_blocked_python_shim(
    tmp_path, monkeypatch
) -> None:
    """WinError 4551 from one PATH shim must not hide a usable interpreter."""
    blocked = tmp_path / "blocked-python.exe"
    allowed = tmp_path / "allowed-python.exe"
    blocked.write_bytes(b"shim")
    allowed.write_bytes(b"python")

    monkeypatch.setattr(_shared.sys, "frozen", True, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    monkeypatch.delenv("LLUNA_TEST_PYTHON", raising=False)
    monkeypatch.setattr(
        _shared.shutil,
        "which",
        lambda name: str(blocked) if name == "python3.11" else str(allowed),
    )

    def fake_run(args, **_kwargs):
        if Path(args[0]) == blocked:
            raise OSError(4551, "An Application Control policy has blocked this file")
        return subprocess.CompletedProcess(args, 0, stdout="3.12\n", stderr="")

    monkeypatch.setattr(_shared.subprocess, "run", fake_run)

    selected = _shared.bootstrap_reviewed_python(
        env_var="LLUNA_TEST_PYTHON",
        versions=("3.11", "3.12"),
        error_message="no interpreter",
    )
    assert selected == str(allowed.resolve())


def test_supir_run_throws_clear_error_without_cuda(monkeypatch) -> None:
    from backend.ai.runtimes import supir as image_supir
    from backend.tools.installers import supir as supir_models

    monkeypatch.setattr(supir_models, "cuda_compatible", lambda: False)

    with pytest.raises(RuntimeError, match="inference requires an NVIDIA CUDA GPU"):
        image_supir.run_supir(
            {},
            cancel_event=threading.Event(),
            progress=lambda _value: None,
            log=lambda _message: None,
        )


def test_supir_install_fetches_both_variants_and_official_sdxl(monkeypatch) -> None:
    from backend.tools.installers import supir as supir_models

    actions: list[str] = []
    monkeypatch.setattr(supir_models, "readiness", lambda: {"runtime": False})
    monkeypatch.setattr(supir_models, "_bootstrap_python", lambda: actions.append("python"))
    monkeypatch.setattr(
        supir_models, "download_checkpoint", lambda kind: actions.append(f"download:{kind}")
    )
    monkeypatch.setattr(supir_models, "_install_source", lambda: actions.append("source"))
    monkeypatch.setattr(supir_models, "_install_runtime", lambda: actions.append("runtime"))
    monkeypatch.setattr(
        supir_models,
        "_install_huggingface_dependencies",
        lambda: actions.append("dependencies"),
    )

    supir_models.install_model()

    assert actions == [
        "python",
        "download:Q",
        "download:F",
        "download:sdxl",
        "source",
        "runtime",
        "dependencies",
    ]


def test_supir_dependencies_use_resumable_managed_downloads(tmp_path, monkeypatch) -> None:
    from backend.tools.installers import supir as supir_models
    from backend.tools.shared import huggingface as hf_auth

    monkeypatch.setattr(supir_models, "supir_root", lambda: tmp_path / "supir")
    partial = supir_models.dependency_dir("llava-v1.5-13b")
    partial.mkdir(parents=True)
    (partial / "incomplete.part").write_bytes(b"partial")
    downloads: list[dict] = []
    monkeypatch.setattr(
        hf_auth,
        "snapshot_download_with_progress",
        lambda **kwargs: downloads.append(kwargs) or kwargs["local_dir"],
    )

    supir_models._install_huggingface_dependencies()

    assert len(downloads) == 4
    assert downloads[0]["repo_id"] == "liuhaotian/llava-v1.5-13b"
    assert downloads[0]["revision"] == "901a44b9113dea67b976e71f58d4e372cf9de81a"
    assert "pytorch_model-*.bin" in downloads[0]["allow_patterns"]
    assert "tf_model.h5" not in downloads[1]["allow_patterns"]
    assert downloads[-1]["allow_patterns"] == ["open_clip_pytorch_model.bin"]


def test_graph_rejects_controls_not_supported_by_selected_model() -> None:
    workflow = WorkflowDocument(
        nodes=[
            WorkflowNode(
                id="generate",
                schema_id="lluna.generate.image",
                parameters={
                    "model": "FLUX.2-klein-4B",
                    "width": 768,
                    "height": 768,
                    "steps": 50,
                    "guidance": 4.0,
                    "negativePrompt": "bad",
                    "seed": -1,
                },
            )
        ]
    )
    result = validate_workflow(workflow, include_unrelated=True)
    messages = [issue.message for issue in result.issues if issue.code == "MODEL_CAPABILITY"]
    assert any("Steps" in message for message in messages)
    assert any("guidance" in message for message in messages)
    assert any("negative prompts" in message for message in messages)


def test_local_model_analyze_and_import_api(tmp_path, monkeypatch) -> None:
    registry = DynamicModelRegistry(paths(tmp_path))
    monkeypatch.setattr(DynamicModelRegistry, "_instance", registry)
    monkeypatch.setattr(DesktopGrantStore, "_instance", None)
    source = tmp_path / "picked-transformers"
    source.mkdir()
    (source / "model.safetensors").write_bytes(b"safe-weights")
    (source / "config.json").write_text("{}", encoding="utf-8")
    grant = DesktopGrantStore.instance().issue(source, mode="directory")
    token = "model-platform-test-token-with-at-least-thirty-two-characters"  # noqa: S105
    headers = {"X-Lluna-Token": token}

    app = create_app(token)

    async def scenario():
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                analyzed = await client.post(
                    "/api/models/analyze",
                    headers=headers,
                    json={"sourceType": "local-folder", "grantId": grant.grant_id},
                )
                assert analyzed.status_code == 200, analyzed.text
                manifest = analyzed.json()["manifest"]
                manifest.update(task="image-restoration", adapter="transformers", needsConfiguration=False)
                manifest["runtime"] = {"profile": "transformers-torch"}
                manifest["variant"] = {"kind": "base"}
                manifest["capabilities"] = safetensors_manifest()["capabilities"]
                imported = await client.post(
                    "/api/models/import",
                    headers=headers,
                    json={
                        "sourceType": "local-folder",
                        "grantId": grant.grant_id,
                        "manifest": manifest,
                    },
                )
                assert imported.status_code == 202, imported.text
                # Local imports are queued through ModelDownloadQueue (same as
                # a remote install) instead of copying on the request thread,
                # so the job may still be running when the response returns.
                from backend.tools.shared.download_queue import ModelDownloadQueue

                job_id = imported.json()["jobId"]
                deadline = asyncio.get_event_loop().time() + 5.0
                while asyncio.get_event_loop().time() < deadline:
                    jobs = ModelDownloadQueue.instance().jobs()
                    job = next((item for item in jobs if item.job_id == job_id), None)
                    if job is not None and job.state in {"completed", "failed", "cancelled"}:
                        assert job.state == "completed", job.error
                        break
                    await asyncio.sleep(0.01)
                else:
                    raise AssertionError("Timed out waiting for local import to finish")
                inventory = (await client.get("/api/models", headers=headers)).json()
                custom = next(item for item in inventory if item["id"] == manifest["id"])
                assert custom["installed"] is True
                assert custom["dynamic"] is True

    asyncio.run(scenario())
