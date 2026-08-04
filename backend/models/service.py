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
    jobs = [
        _download_job_payload(job)
        for job in source.jobs(include_finished=False)
    ]
    return {
        "active": [job for job in jobs if job["state"] in {"active", "stopping"}],
        "pending": [job for job in jobs if job["state"] == "queued"],
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
    return generic | set(_variant_ids())


def model_available(model_id: str) -> bool:
    return model_id in known_model_ids() and _installed(model_id) and _enabled(model_id)


def _model_path(raw: str) -> Path:
    if raw.startswith("~/"):
        return Path(raw).expanduser()
    path = Path(raw)
    return path if path.is_absolute() else PATHS.project_root / path


def _installed(model_id: str) -> bool:
    if model_id.startswith("bg-remove:"):
        from backend.tools.bg_remove_models import is_model_installed
        from backend.tools.constant import BgRemoveMode
        return is_model_installed(BgRemoveMode(model_id.removeprefix("bg-remove:")))
    if model_id.startswith("generate:"):
        from backend.tools.generate_models import is_model_installed
        from backend.tools.constant import GenerateMode
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
    path = _model_path(metadata.local_path)
    if metadata.expected_files:
        return all((path / item.relative_path).is_file() for item in metadata.expected_files if item.required)
    return path.is_file() or (path.is_dir() and any(path.iterdir()))


def list_models() -> list[dict]:
    result = []
    for model_id in sorted(known_model_ids()):
        item = _model_description(model_id)
        item["installed"] = _installed(model_id)
        item["state"] = "installed" if item["installed"] else "not_installed"
        item["enabled"] = _enabled(model_id)
        item["disk_usage_bytes"] = _disk_usage(Path(item["resolved_path"]))
        item["can_install"] = model_id.startswith(("bg-remove:", "generate:")) or model_id in {
            "realesrgan-x2", "realesrgan-x4", "mirnet", "sam2", "grounding-dino"
        }
        item["can_uninstall"] = item["can_install"]
        item["can_toggle"] = True
        result.append(item)
    return result


def _model_description(model_id: str) -> dict:
    if model_id.startswith("bg-remove:"):
        from backend.tools.bg_remove_models import catalog_info, model_file_path
        from backend.tools.constant import BgRemoveMode
        mode = BgRemoveMode(model_id.removeprefix("bg-remove:"))
        info = catalog_info(mode)
        item = asdict(MODEL_REGISTRY["rembg"])
        item.update(id=model_id, display_name=mode.value, purpose=f"Background removal · {info.category if info else 'Local model'}", resolved_path=str(model_file_path(mode)))
        return item
    if model_id.startswith("generate:"):
        from backend.tools.constant import GenerateMode
        from backend.tools.generate_models import catalog_info, model_dir
        mode = GenerateMode(model_id.removeprefix("generate:"))
        info = catalog_info(mode)
        parent_id = "qwen-image" if mode == GenerateMode.QWEN_IMAGE else "flux2-dev" if mode == GenerateMode.FLUX2_DEV else "flux2-klein-9b-fp8" if mode == GenerateMode.FLUX2_KLEIN_9B_FP8 else "flux"
        item = asdict(MODEL_REGISTRY[parent_id])
        item.update(id=model_id, display_name=mode.value, source=info.hf_repo if info else item["source"], resolved_path=str(model_dir(mode)))
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
    if model_id == "mirnet":
        return "MIRNet_LOL" in settings.low_light.enabled_models
    return _enabled_overrides().get(model_id, MODEL_REGISTRY[model_id].enabled_by_default)


def _action(model_id: str, operation: str) -> None:
    if model_id not in known_model_ids():
        raise KeyError(model_id)
    settings = get_settings()
    if model_id.startswith("bg-remove:"):
        from backend.tools.bg_remove_models import install_model, set_model_enabled, uninstall_model
        from backend.tools.constant import BgRemoveMode
        mode = BgRemoveMode(model_id.removeprefix("bg-remove:"))
        {"install": install_model, "remove": uninstall_model}.get(operation, lambda value: set_model_enabled(value, operation == "enable"))(mode)
        return
    if model_id.startswith("generate:"):
        from backend.tools.constant import GenerateMode
        from backend.tools.generate_models import install_model, set_model_enabled, uninstall_model
        mode = GenerateMode(model_id.removeprefix("generate:"))
        {"install": install_model, "remove": uninstall_model}.get(operation, lambda value: set_model_enabled(value, operation == "enable"))(mode)
        return
    if model_id in {"realesrgan-x2", "realesrgan-x4"}:
        from backend.tools.constant import EnhanceMode
        from backend.tools.enhance_models import install_model, set_model_enabled, uninstall_model
        mode = EnhanceMode.X2PLUS if model_id.endswith("x2") else EnhanceMode.X4PLUS
        {"install": install_model, "remove": uninstall_model}.get(operation, lambda value: set_model_enabled(value, operation == "enable"))(mode)
        return
    if model_id == "mirnet":
        from backend.tools.constant import LowLightMode
        from backend.tools.low_light_models import install_model, set_model_enabled, uninstall_model
        mode = LowLightMode.MIRNET_LOL
        {"install": install_model, "remove": uninstall_model}.get(operation, lambda value: set_model_enabled(value, operation == "enable"))(mode)
        return
    if model_id == "rembg":
        from backend.tools.bg_remove_models import install_model, set_model_enabled, uninstall_model
        from backend.tools.constant import BgRemoveMode
        mode = BgRemoveMode(settings.background_removal.mode)
        {"install": install_model, "remove": uninstall_model}.get(operation, lambda value: set_model_enabled(value, operation == "enable"))(mode)
        return
    if model_id in {"sam2", "grounding-dino"}:
        from backend.tools.select_object_models import SelectObjectPairId, install_pair, uninstall_pair
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
                event_type = (
                    "download.cancelled" if cancelled else "download.failed"
                )
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
                if item.kind == "model"
                and item.key == model_id
                and item.operation == "install"
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
