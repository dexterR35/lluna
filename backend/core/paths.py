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
    data_dir: Path
    updates_dir: Path
    config_file: Path
    runtime_config_file: Path
    shipped_config_file: Path
    models_dir: Path
    runtime_file: Path

    @classmethod
    def resolve(cls) -> "AppPaths":
        frozen = bool(getattr(sys, "frozen", False))
        frozen_root = getattr(sys, "_MEIPASS", None)
        default_root = Path(frozen_root) if frozen_root else Path(__file__).resolve().parents[2]
        root = _resolved_override("MIDGARD_PROJECT_ROOT", default_root)
        runtime_root = Path(sys.executable).resolve().parent if frozen else root
        user_config, user_data = _user_roots()
        config_dir = _resolved_override(
            "MIDGARD_CONFIG_DIR",
            user_config if frozen else runtime_root / "config",
        )
        data_dir = _resolved_override(
            "MIDGARD_DATA_DIR",
            user_data if frozen else root,
        )
        models_dir = _resolved_override(
            "MIDGARD_MODELS_DIR",
            data_dir / "models" if frozen else root / "backend" / "models",
        )
        return cls(
            project_root=root,
            config_dir=config_dir,
            data_dir=data_dir,
            updates_dir=data_dir / "updates",
            config_file=config_dir / "config.json",
            runtime_config_file=config_dir / "runtime.json",
            shipped_config_file=root / "config" / "defaults.json",
            models_dir=models_dir,
            runtime_file=(
                config_dir / "midgard_runtime.json"
                if frozen
                else runtime_root / "midgard_runtime.json"
            ),
        )


def _user_roots() -> tuple[Path, Path]:
    """Return writable per-user config/data roots without optional dependencies."""
    home = Path.home()
    if sys.platform == "win32":
        local = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        base = local / "Midgard"
        return base / "config", base
    if sys.platform == "darwin":
        base = home / "Library" / "Application Support" / "Midgard"
        return base / "config", base
    config = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config")) / "midgard"
    data = Path(os.environ.get("XDG_DATA_HOME", home / ".local" / "share")) / "midgard"
    return config, data


PATHS = AppPaths.resolve()
