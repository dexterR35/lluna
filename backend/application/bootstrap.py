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
        from backend.tools.model_download_lifecycle import prepare_restart_pending

        recovered = prepare_restart_pending()
        if recovered:
            logger.info(
                "Prepared %d interrupted model download(s) for retry",
                len(recovered),
            )
    except (OSError, RuntimeError, ValueError) as exc:
        logger.warning("Model download recovery was not applied: %s", exc)
    try:
        from backend.tools.hf_auth import apply_hf_token_to_env
        apply_hf_token_to_env()
    except (ImportError, OSError, ValueError):
        logger.info("No saved Hugging Face credential was applied")
    try:
        from backend.tools.soft_defaults import apply_soft_defaults_if_needed
        apply_soft_defaults_if_needed()
    except (OSError, RuntimeError, ValueError) as exc:
        logger.warning("Hardware soft defaults were not applied: %s", exc)
    try:
        from backend.media.workspace import cleanup_stale_workspaces
        cleanup_stale_workspaces()
    except (ImportError, OSError) as exc:
        logger.warning("Stale workspace cleanup skipped: %s", exc)
    os.environ["MIDGARD_BOOTSTRAPPED"] = "1"
    elapsed_ms = int((monotonic() - started) * 1000)
    logger.info("Control-plane bootstrap completed in %d ms", elapsed_ms)
    return BootstrapReport(paths, changes, elapsed_ms)
