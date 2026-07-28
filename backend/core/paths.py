"""Absolute project paths with optional test/runtime overrides."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


def _resolved_override(name: str, default: Path) -> Path:
    raw = os.environ.get(name)
    return Path(raw).expanduser().resolve() if raw else default.resolve()


@dataclass(frozen=True)
class AppPaths:
    project_root: Path
    config_dir: Path
    config_file: Path
    runtime_config_file: Path
    shipped_config_file: Path
    translation_file: Path
    models_dir: Path
    runtime_file: Path

    @classmethod
    def resolve(cls) -> "AppPaths":
        frozen_root = getattr(sys, "_MEIPASS", None)
        default_root = (
            Path(frozen_root)
            if frozen_root
            else Path(__file__).resolve().parents[2]
        )
        root = _resolved_override(
            "MIDGARD_PROJECT_ROOT", default_root
        )
        runtime_root = (
            Path(sys.executable).resolve().parent
            if getattr(sys, "frozen", False)
            else root
        )
        config_dir = _resolved_override(
            "MIDGARD_CONFIG_DIR", runtime_root / "config"
        )
        models_dir = _resolved_override(
            "MIDGARD_MODELS_DIR", root / "backend" / "models"
        )
        return cls(
            project_root=root,
            config_dir=config_dir,
            config_file=config_dir / "config.json",
            runtime_config_file=config_dir / "runtime.json",
            shipped_config_file=root / "config" / "defaults.json",
            translation_file=root / "backend" / "interface" / "en.ini",
            models_dir=models_dir,
            runtime_file=runtime_root / "midgard_runtime.json",
        )


PATHS = AppPaths.resolve()
