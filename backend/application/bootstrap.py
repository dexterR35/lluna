"""Control-plane bootstrap for the Electron sidecar."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from time import monotonic

from backend.configuration.service import ConfigurationService
from backend.core.environment import EnvironmentChange, initialize_process_environment
from backend.core.paths import AppPaths
from backend.diagnostics.logging import initialize_logging

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BootstrapReport:
    paths: AppPaths
    environment_changes: tuple[EnvironmentChange, ...]
    elapsed_ms: int


def prepare_control_plane() -> BootstrapReport:
    started = monotonic()
    from backend.application.preflight import validate_packaged_runtime, validate_python_runtime
    validate_python_runtime()
    initialize_logging()
    changes = initialize_process_environment()
    paths = AppPaths.resolve()
    validate_packaged_runtime(paths)
    paths.config_dir.mkdir(parents=True, exist_ok=True)
    paths.data_dir.mkdir(parents=True, exist_ok=True)
    ConfigurationService.instance()
    try:
        from backend.api.events import EventBroker
        from backend.models.dynamic_registry import DynamicModelRegistry

        registry = DynamicModelRegistry.instance()
        registry.subscribe(
            lambda: EventBroker.instance().publish(
                "model.changed", payload={"source": "custom-folder"}
            )
        )
        model_settings = ConfigurationService.instance().get().models
        if model_settings.auto_scan:
            registry.start_watcher(
                interval_seconds=float(model_settings.scan_interval_seconds)
            )

        def apply_model_platform_settings(configuration) -> None:
            if configuration.models.auto_scan:
                registry.start_watcher(
                    interval_seconds=float(configuration.models.scan_interval_seconds)
                )
            else:
                registry.stop_watcher()

        ConfigurationService.instance().subscribe(apply_model_platform_settings)
    except (OSError, ValueError) as exc:
        logger.warning("Custom model registry was not started: %s", exc)
    try:
        from backend.tools.shared.download_lifecycle import prepare_restart_pending

        recovered = prepare_restart_pending()
        if recovered:
            logger.info(
                "Prepared %d interrupted model download(s) for retry",
                len(recovered),
            )
    except (OSError, RuntimeError, ValueError) as exc:
        logger.warning("Model download recovery was not applied: %s", exc)
    try:
        from backend.tools.shared.huggingface import apply_hf_token_to_env
        apply_hf_token_to_env()
    except (ImportError, OSError, ValueError):
        logger.info("No saved Hugging Face credential was applied")
    try:
        from backend.tools.shared.defaults import apply_soft_defaults_if_needed
        apply_soft_defaults_if_needed()
    except (OSError, RuntimeError, ValueError) as exc:
        logger.warning("Hardware soft defaults were not applied: %s", exc)
    try:
        from backend.media.workspace import cleanup_stale_workspaces
        cleanup_stale_workspaces()
    except (ImportError, OSError) as exc:
        logger.warning("Stale workspace cleanup skipped: %s", exc)
    os.environ["LLUNA_BOOTSTRAPPED"] = "1"
    elapsed_ms = int((monotonic() - started) * 1000)
    logger.info("Control-plane bootstrap completed in %d ms", elapsed_ms)
    return BootstrapReport(paths, changes, elapsed_ms)
