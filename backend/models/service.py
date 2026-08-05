"""Model lifecycle facade for the control-plane API."""

from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict
from pathlib import Path

from backend.api.events import EventBroker
from backend.configuration.service import get_settings
from backend.core.atomic import atomic_write_json
from backend.core.paths import PATHS
from backend.models.registry import MODEL_REGISTRY
from backend.tools.model_download_queue import ModelDownloadQueue

_GENERATION_REGISTRY_IDS = {"flux", "flux2-dev", "flux2-klein-9b-fp8", "qwen-image"}
_STATE_LOCK = threading.RLock()
_QUEUE_EVENT_LOCK = threading.Lock()
_QUEUE_EVENT_SOURCE: ModelDownloadQueue | None = None
_QUEUE_EVENT_LISTENER = None


def _download_job_payload(job) -> dict:
    return {
        "jobId": job.job_id,
        "kind": job.kind,
        "key": job.key,
        "modelId": job.key if job.kind == "model" else None,
        "operation": job.operation,
        "state": job.state,
        "position": job.position,
        "progress": job.progress,
        "detail": job.detail,
        "error": job.error,
        "downloadedBytes": job.downloaded_bytes,
        "totalBytes": job.total_bytes,
        "bytesPerSecond": job.bytes_per_second,
        "elapsedSeconds": job.elapsed_seconds,
        "etaSeconds": job.eta_seconds,
    }


def download_queue_snapshot(
    queue: ModelDownloadQueue | None = None,
) -> dict:
    source = queue or ModelDownloadQueue.instance()
    jobs = [_download_job_payload(job) for job in source.jobs(include_finished=True)]
    return {
        "active": [job for job in jobs if job["state"] in {"active", "stopping"}],
        "pending": [job for job in jobs if job["state"] == "queued"],
        # Keep terminal results in the snapshot so a fast failure is still
        # visible when the renderer reconnects or polls after the job exits.
        "recent": [job for job in jobs if job["state"] in {"completed", "failed", "cancelled"}][
            :20
        ],
    }


def _ensure_queue_events(queue: ModelDownloadQueue) -> None:
    global _QUEUE_EVENT_LISTENER, _QUEUE_EVENT_SOURCE
    with _QUEUE_EVENT_LOCK:
        if _QUEUE_EVENT_SOURCE is queue:
            return
        if _QUEUE_EVENT_SOURCE is not None and _QUEUE_EVENT_LISTENER is not None:
            _QUEUE_EVENT_SOURCE.remove_listener(_QUEUE_EVENT_LISTENER)

        def publish() -> None:
            EventBroker.instance().publish(
                "download.queue.updated",
                payload=download_queue_snapshot(queue),
            )

        queue.add_listener(publish)
        _QUEUE_EVENT_SOURCE = queue
        _QUEUE_EVENT_LISTENER = publish


def ensure_download_queue_events(queue: ModelDownloadQueue | None = None) -> None:
    _ensure_queue_events(queue or ModelDownloadQueue.instance())


def _state_path() -> Path:
    return Path(os.environ.get("MIDGARD_CONFIG_DIR", PATHS.config_dir)) / "model-lifecycle.json"


def _enabled_overrides() -> dict[str, bool]:
    try:
        value = json.loads(_state_path().read_text(encoding="utf-8"))
        return {str(key): bool(enabled) for key, enabled in value.items()}
    except (OSError, ValueError, TypeError):
        return {}


def _set_enabled_override(model_id: str, enabled: bool) -> None:
    with _STATE_LOCK:
        values = _enabled_overrides()
        values[model_id] = enabled
        atomic_write_json(_state_path(), values)


def _variant_ids() -> list[str]:
    from backend.tools.bg_remove_models import MODEL_CATALOG as background_models
    from backend.tools.generate_models import MODEL_CATALOG as generation_models

    return [
        *(f"bg-remove:{item.mode.value}" for item in background_models),
        *(f"generate:{item.mode.value}" for item in generation_models),
    ]


def known_model_ids() -> set[str]:
    generic = set(MODEL_REGISTRY) - {"rembg"} - _GENERATION_REGISTRY_IDS
    dynamic = {
        record.manifest.id
        for record in _dynamic_records()
        if record.manifest.id not in generic and record.manifest.id not in set(_variant_ids())
    }
    return generic | set(_variant_ids()) | dynamic


def _dynamic_records():
    try:
        from backend.models.dynamic_registry import DynamicModelRegistry

        return DynamicModelRegistry.instance().records()
    except (OSError, ValueError):
        return []


def _dynamic_record(model_id: str):
    try:
        from backend.models.dynamic_registry import DynamicModelRegistry

        return DynamicModelRegistry.instance().get(model_id)
    except KeyError:
        return None


def model_available(model_id: str) -> bool:
    return model_id in known_model_ids() and _installed(model_id) and _enabled(model_id)


def _model_path(raw: str) -> Path:
    if raw.startswith("~/"):
        return Path(raw).expanduser()
    path = Path(raw)
    return path if path.is_absolute() else PATHS.project_root / path


def _installed(model_id: str) -> bool:
    dynamic = _dynamic_record(model_id)
    if dynamic is not None:
        return dynamic.installed
    if model_id.startswith("bg-remove:"):
        from backend.tools.bg_remove_models import is_model_installed
        from backend.tools.constant import BgRemoveMode

        return is_model_installed(BgRemoveMode(model_id.removeprefix("bg-remove:")))
    if model_id.startswith("generate:"):
        from backend.tools.constant import GenerateMode
        from backend.tools.generate_models import is_model_installed

        return is_model_installed(GenerateMode(model_id.removeprefix("generate:")))
    metadata = MODEL_REGISTRY[model_id]
    if model_id in {"sam2", "grounding-dino"}:
        from backend.tools.select_object_models import is_fast_pair_installed

        return is_fast_pair_installed()
    if model_id == "mirnet":
        from backend.tools.constant import LowLightMode
        from backend.tools.low_light_models import is_model_installed

        return is_model_installed(LowLightMode.MIRNET_LOL)
    if model_id == "realesrgan-x2":
        from backend.tools.constant import EnhanceMode
        from backend.tools.enhance_models import is_model_installed

        return is_model_installed(EnhanceMode.X2PLUS)
    if model_id == "realesrgan-x4":
        from backend.tools.constant import EnhanceMode
        from backend.tools.enhance_models import is_model_installed

        return is_model_installed(EnhanceMode.X4PLUS)
    if model_id == "supir":
        from backend.tools.supir_models import is_model_installed

        return is_model_installed()
    path = _model_path(metadata.local_path)
    if metadata.expected_files:
        return all(
            (path / item.relative_path).is_file()
            for item in metadata.expected_files
            if item.required
        )
    return path.is_file() or (path.is_dir() and any(path.iterdir()))


def list_models() -> list[dict]:
    result = []
    builtin_ids = known_model_ids() - {record.manifest.id for record in _dynamic_records()}
    for model_id in sorted(builtin_ids):
        item = _model_description(model_id)
        item["installed"] = _installed(model_id)
        item["state"] = "installed" if item["installed"] else "not_installed"
        item["enabled"] = _enabled(model_id)
        item["disk_usage_bytes"] = _disk_usage(Path(item["resolved_path"]))
        lifecycle_managed = model_id.startswith(("bg-remove:", "generate:")) or model_id in {
            "realesrgan-x2",
            "realesrgan-x4",
            "supir",
            "mirnet",
            "sam2",
            "grounding-dino",
        }
        item["can_install"] = lifecycle_managed
        item["can_uninstall"] = lifecycle_managed
        item["can_toggle"] = True
        item.update(_builtin_platform_fields(model_id, item))
        result.append(item)
    for record in _dynamic_records():
        if record.manifest.id in builtin_ids:
            continue
        result.append(record.to_inventory())
    return result


def _builtin_platform_fields(model_id: str, item: dict) -> dict:
    from backend.models.capability_resolver import builtin_contract

    variant, capabilities = builtin_contract(model_id)
    if model_id.startswith("generate:"):
        task, adapter, profile = "text-to-image", "diffusers", "diffusers-torch"
    elif model_id.startswith("bg-remove:"):
        task, adapter, profile = "image-segmentation", "onnx", "onnx-runtime"
    elif model_id.startswith("realesrgan"):
        task, adapter, profile = "image-upscaling", "midgard-native", "midgard-native"
    elif model_id == "supir":
        task, adapter, profile = "image-upscaling", "supir", "supir-python"
    elif model_id == "mirnet":
        task, adapter, profile = "image-restoration", "midgard-native", "midgard-native"
    elif model_id == "sam2":
        task, adapter, profile = "image-segmentation", "transformers", "transformers-torch"
    elif model_id == "grounding-dino":
        task, adapter, profile = "object-detection", "transformers", "transformers-torch"
    elif model_id.startswith("paddleocr"):
        task, adapter, profile = "text-recognition", "paddle", "paddle"
    else:
        task, adapter, profile = "inpainting", "midgard-native", "midgard-native"
    try:
        from backend.models.runtime_profiles import get_runtime_profile, runtime_installed

        runtime = get_runtime_profile(profile)
        installed = runtime_installed(runtime)
    except (ImportError, ValueError):
        installed = False
    runtime_packages: list[str] = []
    runtime_reasons: list[str] = []
    runtime_warnings: list[str] = []
    runtime_isolated = False
    if model_id == "supir":
        from backend.hardware.detector import get_hardware_profile
        from backend.hardware.policy import select_execution_policy
        from backend.tools.supir_models import SUPIR_PACKAGES

        runtime_packages = list(SUPIR_PACKAGES)
        runtime_isolated = True
        selected_backend = select_execution_policy(get_hardware_profile()).backend
        if selected_backend != "cuda":
            runtime_reasons.append("The official SUPIR implementation requires an NVIDIA CUDA GPU.")
        runtime_warnings.append(
            "SUPIR source and checkpoints are restricted to non-commercial use."
        )
    manifest = {
        "schema": 1,
        "id": model_id.replace(":", "-").lower(),
        "legacyId": model_id,
        "name": item.get("display_name", model_id),
        "description": item.get("purpose", ""),
        "task": task,
        "adapter": adapter,
        "license": item.get("license", "See upstream model card"),
        "gated": bool(item.get("gated", False)),
        "source": {
            "type": "bundled"
            if item.get("source") == "bundled"
            else "huggingface"
            if "/" in str(item.get("source", ""))
            and not str(item.get("source", "")).startswith("http")
            else "url",
            "repo": item.get("source", "")
            if "/" in str(item.get("source", ""))
            and not str(item.get("source", "")).startswith("http")
            else "",
            "url": item.get("source", "") if str(item.get("source", "")).startswith("http") else "",
        },
        "runtime": {
            "profile": profile,
            "packages": runtime_packages,
            "isolated": runtime_isolated,
        },
        "hardware": {
            "backends": list(item.get("compatible_backends", ("cpu",))),
            "minimumRamMb": int(item.get("minimum_ram_mb", 0) or 0),
            "minimumVramMb": int(item.get("minimum_vram_mb", 0) or 0),
            "minimumDiskMb": (int(item.get("expected_size_bytes", 0) or 0) // (1024 * 1024)),
        },
        "security": {
            "trustRemoteCode": False,
            "preferSafetensors": model_id != "supir",
            "allowPickle": model_id == "supir",
        },
        "variant": variant.to_dict(),
        "capabilities": capabilities.to_dict(task),
        "managedBy": "midgard",
    }
    return {
        "dynamic": False,
        "task": task,
        "adapter": adapter,
        "variant": variant.to_dict(),
        "capabilities": capabilities.to_dict(task),
        "runtime": {
            "profile": profile,
            "installed": installed,
            "compatible": not runtime_reasons,
            "reasons": runtime_reasons,
            "warnings": runtime_warnings,
            "packages": runtime_packages,
            "isolated": runtime_isolated,
        },
        "manifest": manifest,
    }


def _model_description(model_id: str) -> dict:
    if model_id == "supir":
        from backend.tools.supir_models import readiness, supir_root

        item = asdict(MODEL_REGISTRY[model_id])
        item.update(resolved_path=str(supir_root()), setup=readiness())
        return item
    if model_id.startswith("bg-remove:"):
        from backend.tools.bg_remove_models import catalog_info, model_file_path
        from backend.tools.constant import BgRemoveMode

        mode = BgRemoveMode(model_id.removeprefix("bg-remove:"))
        info = catalog_info(mode)
        detail = (info.description if info else "").strip()
        purpose = detail or (info.category if info else "Local model")
        item = asdict(MODEL_REGISTRY["rembg"])
        item.update(
            id=model_id,
            display_name=mode.value,
            purpose=purpose,
            resolved_path=str(model_file_path(mode)),
        )
        return item
    if model_id.startswith("generate:"):
        from backend.tools.constant import GenerateMode
        from backend.tools.generate_models import catalog_info, model_dir

        mode = GenerateMode(model_id.removeprefix("generate:"))
        info = catalog_info(mode)
        parent_id = (
            "qwen-image"
            if mode == GenerateMode.QWEN_IMAGE
            else "flux2-dev"
            if mode == GenerateMode.FLUX2_DEV
            else "flux2-klein-9b-fp8"
            if mode == GenerateMode.FLUX2_KLEIN_9B_FP8
            else "flux"
        )
        item = asdict(MODEL_REGISTRY[parent_id])
        item.update(
            id=model_id,
            display_name=mode.value,
            source=info.hf_repo if info else item["source"],
            resolved_path=str(model_dir(mode)),
        )
        return item
    metadata = MODEL_REGISTRY[model_id]
    item = asdict(metadata)
    item["resolved_path"] = str(_model_path(metadata.local_path))
    return item


def _disk_usage(path: Path) -> int:
    try:
        if path.is_file():
            return path.stat().st_size
        return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())
    except OSError:
        return 0


def _enabled(model_id: str) -> bool:
    dynamic = _dynamic_record(model_id)
    if dynamic is not None:
        from backend.models.runtime_profiles import runtime_status

        return dynamic.enabled and runtime_status(dynamic.manifest)["compatible"]
    settings = get_settings()
    if model_id.startswith("bg-remove:"):
        from backend.tools.bg_remove_models import get_enabled_values

        return model_id.removeprefix("bg-remove:") in get_enabled_values()
    if model_id.startswith("generate:"):
        from backend.tools.generate_models import get_enabled_values

        return model_id.removeprefix("generate:") in get_enabled_values()
    if model_id == "realesrgan-x2":
        return "RealESRGAN_x2plus" in settings.enhancement.enabled_models
    if model_id == "realesrgan-x4":
        return "RealESRGAN_x4plus" in settings.enhancement.enabled_models
    if model_id == "supir":
        return _enabled_overrides().get(model_id, False)
    if model_id == "mirnet":
        return "MIRNet_LOL" in settings.low_light.enabled_models
    return _enabled_overrides().get(model_id, MODEL_REGISTRY[model_id].enabled_by_default)


def _action(model_id: str, operation: str) -> None:
    if model_id not in known_model_ids():
        raise KeyError(model_id)
    settings = get_settings()
    dynamic = _dynamic_record(model_id)
    if dynamic is not None:
        from backend.models.dynamic_registry import DynamicModelRegistry
        from backend.models.importer import install_huggingface, uninstall_dynamic

        if operation == "install":
            install_huggingface(dynamic.manifest)
        elif operation == "remove":
            uninstall_dynamic(model_id)
        elif operation in {"enable", "disable"}:
            from backend.models.runtime_profiles import runtime_status

            if operation == "enable" and (
                not dynamic.installed
                or not dynamic.manifest.is_configured()
                or dynamic.error
                or not runtime_status(dynamic.manifest)["compatible"]
            ):
                raise ValueError("This model is not ready to enable.")
            DynamicModelRegistry.instance().set_enabled(model_id, operation == "enable")
        return
    if model_id.startswith("bg-remove:"):
        from backend.tools.bg_remove_models import install_model, set_model_enabled, uninstall_model
        from backend.tools.constant import BgRemoveMode

        mode = BgRemoveMode(model_id.removeprefix("bg-remove:"))
        {"install": install_model, "remove": uninstall_model}.get(
            operation, lambda value: set_model_enabled(value, operation == "enable")
        )(mode)
        return
    if model_id.startswith("generate:"):
        from backend.tools.constant import GenerateMode
        from backend.tools.generate_models import install_model, set_model_enabled, uninstall_model

        mode = GenerateMode(model_id.removeprefix("generate:"))
        {"install": install_model, "remove": uninstall_model}.get(
            operation, lambda value: set_model_enabled(value, operation == "enable")
        )(mode)
        return
    if model_id in {"realesrgan-x2", "realesrgan-x4"}:
        from backend.tools.constant import EnhanceMode
        from backend.tools.enhance_models import install_model, set_model_enabled, uninstall_model

        mode = EnhanceMode.X2PLUS if model_id.endswith("x2") else EnhanceMode.X4PLUS
        {"install": install_model, "remove": uninstall_model}.get(
            operation, lambda value: set_model_enabled(value, operation == "enable")
        )(mode)
        return
    if model_id == "supir":
        from backend.tools.supir_models import install_model, uninstall_model

        if operation == "install":
            install_model()
            _set_enabled_override(model_id, True)
        elif operation == "remove":
            uninstall_model()
            _set_enabled_override(model_id, False)
        else:
            if operation == "enable" and not _installed(model_id):
                raise ValueError("SUPIR is not fully installed.")
            _set_enabled_override(model_id, operation == "enable")
        return
    if model_id == "mirnet":
        from backend.tools.constant import LowLightMode
        from backend.tools.low_light_models import install_model, set_model_enabled, uninstall_model

        mode = LowLightMode.MIRNET_LOL
        {"install": install_model, "remove": uninstall_model}.get(
            operation, lambda value: set_model_enabled(value, operation == "enable")
        )(mode)
        return
    if model_id == "rembg":
        from backend.tools.bg_remove_models import install_model, set_model_enabled, uninstall_model
        from backend.tools.constant import BgRemoveMode

        mode = BgRemoveMode(settings.background_removal.mode)
        {"install": install_model, "remove": uninstall_model}.get(
            operation, lambda value: set_model_enabled(value, operation == "enable")
        )(mode)
        return
    if model_id in {"sam2", "grounding-dino"}:
        from backend.tools.select_object_models import (
            SelectObjectPairId,
            install_pair,
            uninstall_pair,
        )

        if operation == "install":
            install_pair(SelectObjectPairId.FAST, skip_if_complete=True)
            _set_enabled_override(model_id, True)
        elif operation == "remove":
            uninstall_pair(SelectObjectPairId.FAST)
            _set_enabled_override(model_id, False)
        else:
            _set_enabled_override(model_id, operation == "enable")
        return
    if operation == "install" and model_id in {"lama", "sttn-auto", "sttn-detection", "propainter"}:
        from backend.models.paths import SubtitleModelPaths, prepare_bundled_subtitle_models

        prepare_bundled_subtitle_models(SubtitleModelPaths.resolve(settings.subtitle))
        return
    if operation in {"enable", "disable"}:
        _set_enabled_override(model_id, operation == "enable")
        return
    if operation == "remove":
        raise PermissionError("This shipped runtime cannot be uninstalled independently")
    if operation == "install":
        raise PermissionError("This runtime is supplied by the Midgard installation")


def start_model_action(model_id: str, operation: str) -> dict:
    if model_id not in known_model_ids():
        raise KeyError(model_id)
    action_id = f"{operation}:{model_id}"
    events = EventBroker.instance()

    if operation == "install":
        queue = ModelDownloadQueue.instance()
        _ensure_queue_events(queue)

        def work() -> None:
            queue.report_current_progress(0, detail="Preparing download")
            _action(model_id, operation)

        def done(error: BaseException | None) -> None:
            if error is None:
                event_type = "download.completed"
                payload = {
                    "downloadId": action_id,
                    "modelId": model_id,
                    "operation": operation,
                }
            else:
                cancelled = type(error).__name__ == "DownloadCancelled"
                event_type = "download.cancelled" if cancelled else "download.failed"
                payload = {
                    "downloadId": action_id,
                    "modelId": model_id,
                    "operation": operation,
                    "message": str(error),
                }
            events.publish(event_type, payload=payload)

        position = queue.enqueue(
            "model",
            model_id,
            work,
            done,
            operation="install",
        )
        job = next(
            (
                item
                for item in queue.jobs()
                if item.kind == "model" and item.key == model_id and item.operation == "install"
            ),
            None,
        )
        payload = {
            "downloadId": action_id,
            "modelId": model_id,
            "operation": operation,
            "jobId": job.job_id if job else None,
            "position": position,
        }
        events.publish("download.queued", payload=payload)
        return {
            "actionId": action_id,
            "jobId": job.job_id if job else None,
            "position": position,
        }

    def run() -> None:
        payload = {
            "downloadId": action_id,
            "modelId": model_id,
            "operation": operation,
        }
        events.publish("model.action.started", payload=payload)
        try:
            _action(model_id, operation)
            events.publish("model.changed", payload=payload)
        except Exception as exc:
            events.publish(
                "model.action.failed",
                payload={**payload, "message": str(exc)},
            )

    threading.Thread(target=run, name=f"model-{action_id}", daemon=True).start()
    return {"actionId": action_id, "jobId": None, "position": -1}
