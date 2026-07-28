"""Lightweight desktop bootstrap that runs before importing Qt."""

from __future__ import annotations

import importlib.util
import logging
import os
import sys
from dataclasses import dataclass
from time import monotonic

from backend.core.environment import EnvironmentChange, initialize_process_environment
from backend.core.paths import AppPaths
from backend.diagnostics.errors import DependencyError
from backend.diagnostics.logging import initialize_logging

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BootstrapReport:
    paths: AppPaths
    environment_changes: tuple[EnvironmentChange, ...]
    elapsed_ms: int


def validate_desktop_dependencies() -> None:
    missing = [
        module
        for module in ("PySide6", "qfluentwidgets")
        if importlib.util.find_spec(module) is None
    ]
    if missing:
        raise DependencyError(
            "Missing desktop dependencies: " + ", ".join(missing)
        )


def prepare_desktop(argv: list[str] | None = None) -> BootstrapReport:
    started = monotonic()
    from backend.tools.diag import parse_cli_flags

    parse_cli_flags()
    initialize_logging()
    changes = initialize_process_environment()
    paths = AppPaths.resolve()
    validate_desktop_dependencies()
    os.environ["MIDGARD_BOOTSTRAPPED"] = "1"
    elapsed_ms = int((monotonic() - started) * 1000)
    logger.info("Desktop bootstrap completed in %d ms", elapsed_ms)
    return BootstrapReport(paths, changes, elapsed_ms)


def launch_desktop(argv: list[str] | None = None) -> int:
    try:
        prepare_desktop(argv)
        from gui import main

        return main(argv)
    except DependencyError as exc:
        print(f"Midgard could not start: {exc}", file=sys.stderr)
        return 2
