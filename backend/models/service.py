"""Qt-free model lifecycle facade for the control-plane API."""

from __future__ import annotations

import threading
from dataclasses import asdict
from pathlib import Path
from typing import Callable

from backend.api.events import EventBroker
from backend.configuration.service import get_settings
from backend.core.paths import PATHS
from backend.models.registry import MODEL_REGISTRY


def _model_path(raw: str) -> Path:
    if raw.startswith("~/"):
        return Path(raw).expanduser()
    path = Path(raw)
    return path if path.is_absolute() else PATHS.project_root / path


def _installed(model_id: str) -> bool:
    metadata = MODEL_REGISTRY[model_id]
    if model_id == "rembg":
        from backend.tools.bg_remove_models import installed_modes
        return bool(installed_modes())
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
    for model_id, metadata in MODEL_REGISTRY.items():
        item = asdict(metadata)
        item["installed"] = _installed(model_id)
        item["state"] = "installed" if item["installed"] else "not_installed"
        item["enabled"] = _enabled(model_id)
        item["disk_usage_bytes"] = _disk_usage(_model_path(metadata.local_path))
        result.append(item)
    return result


def _disk_usage(path: Path) -> int:
    try:
        if path.is_file():
            return path.stat().st_size
        return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())
    except OSError:
        return 0


def _enabled(model_id: str) -> bool:
    settings = get_settings()
    if model_id == "realesrgan-x2":
        return "RealESRGAN_x2plus" in settings.enhancement.enabled_models
    if model_id == "realesrgan-x4":
        return "RealESRGAN_x4plus" in settings.enhancement.enabled_models
    if model_id == "mirnet":
        return "MIRNet_LOL" in settings.low_light.enabled_models
    if model_id == "rembg":
        return settings.background_removal.enabled_models != "__none__"
    if model_id in {"flux", "flux2-dev", "flux2-klein-9b-fp8", "qwen-image"}:
        return settings.generation.enabled_models != "__none__"
    return MODEL_REGISTRY[model_id].enabled_by_default


def _action(model_id: str, operation: str) -> None:
    if model_id not in MODEL_REGISTRY:
        raise KeyError(model_id)
    settings = get_settings()
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
        if operation == "install": install_pair(SelectObjectPairId.FAST, skip_if_complete=True)
        elif operation == "remove": uninstall_pair(SelectObjectPairId.FAST)
        return
    if model_id in {"flux", "flux2-dev", "flux2-klein-9b-fp8", "qwen-image"}:
        from backend.tools.constant import GenerateMode
        from backend.tools.generate_models import install_model, set_model_enabled, uninstall_model
        mode = GenerateMode(settings.generation.mode)
        {"install": install_model, "remove": uninstall_model}.get(operation, lambda value: set_model_enabled(value, operation == "enable"))(mode)
        return
    if operation == "install" and model_id in {"lama", "sttn-auto", "sttn-detection", "propainter"}:
        from backend.models.paths import SubtitleModelPaths, prepare_bundled_subtitle_models
        prepare_bundled_subtitle_models(SubtitleModelPaths.resolve(settings.subtitle))
        return
    if operation == "remove":
        raise PermissionError("Bundled models cannot be removed independently")


def start_model_action(model_id: str, operation: str) -> str:
    action_id = f"{operation}:{model_id}"
    events = EventBroker.instance()
    def run() -> None:
        events.publish("download.queued" if operation == "install" else "model.changed", payload={"downloadId": action_id, "modelId": model_id, "operation": operation})
        try:
            _action(model_id, operation)
            events.publish("download.completed" if operation == "install" else "model.changed", payload={"downloadId": action_id, "modelId": model_id, "operation": operation})
        except Exception as exc:
            events.publish("download.failed", payload={"downloadId": action_id, "modelId": model_id, "operation": operation, "message": str(exc)})
    threading.Thread(target=run, name=f"model-{action_id}", daemon=True).start()
    return action_id
