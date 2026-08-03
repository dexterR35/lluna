"""Layered configuration loading with validation and corrupt-file recovery."""

from __future__ import annotations

import json
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from backend.configuration.migrations import migrate_mapping
from backend.configuration.models import ApplicationConfiguration
from backend.configuration.recovery import backup_if_corrupt_json
from backend.core.atomic import atomic_write_json
from backend.core.paths import PATHS, AppPaths
from backend.diagnostics.errors import ConfigurationError


_ENVIRONMENT_KEYS: dict[str, tuple[str, str, type]] = {
    "MIDGARD_HARDWARE_ACCELERATION": (
        "subtitle",
        "hardware_acceleration",
        bool,
    ),
    "MIDGARD_INPAINT_MODE": ("subtitle", "inpaint_mode", str),
    "MIDGARD_SUBTITLE_DETECT_MODE": (
        "subtitle",
        "subtitle_detect_mode",
        str,
    ),
    "MIDGARD_JOB_WATCHDOG_SECONDS": (
        "runtime",
        "job_watchdog_seconds",
        float,
    ),
    "MIDGARD_IDLE_RELEASE_SECONDS": (
        "runtime",
        "idle_release_seconds",
        float,
    ),
    "MIDGARD_SAVE_DIRECTORY": ("root", "save_directory", str),
}


@dataclass(frozen=True)
class LoadedConfiguration:
    value: ApplicationConfiguration
    provenance: tuple[str, ...]
    warnings: tuple[str, ...] = ()
    recovered_files: tuple[Path, ...] = ()
    migrated_files: tuple[Path, ...] = ()


def _merge(base: dict[str, Any], overlay: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in overlay.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), Mapping):
            result[key] = _merge(dict(result[key]), value)
        else:
            result[key] = value
    return result


def _parse_bool(raw: str) -> bool:
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"expected a boolean, received {raw!r}")


class ConfigurationLoader:
    def __init__(self, paths: AppPaths = PATHS) -> None:
        self._paths = paths

    def load(
        self,
        *,
        shipped_file: str | Path | None = None,
        user_file: str | Path | None = None,
        legacy_file: str | Path | None = None,
        environ: Mapping[str, str] | None = None,
        overrides: Mapping[str, Any] | None = None,
    ) -> LoadedConfiguration:
        merged = ApplicationConfiguration().to_dict()
        provenance = ["compiled defaults"]
        warnings: list[str] = []
        recovered: list[Path] = []
        migrated: list[Path] = []
        migrated_legacy: Path | None = None
        shipped = Path(shipped_file or self._paths.shipped_config_file)
        user = Path(user_file or self._paths.runtime_config_file)
        legacy = Path(legacy_file or self._paths.config_file)

        shipped_data = self._read_layer(shipped, recover=False, warnings=warnings)
        if shipped_data is not None:
            merged = _merge(merged, migrate_mapping(shipped_data))
            provenance.append(f"shipped:{shipped}")

        user_data, backup = self._read_user_layer(user, warnings)
        if backup is not None:
            recovered.append(backup)
        if user_data is not None:
            merged = _merge(merged, migrate_mapping(user_data))
            provenance.append(f"user:{user}")
        elif legacy != user:
            legacy_data = self._read_layer(legacy, recover=False, warnings=warnings)
            if legacy_data is not None:
                merged = _merge(merged, migrate_mapping(legacy_data))
                provenance.append(f"legacy:{legacy}")
                migrated_legacy = legacy

        environment_overlay = self._environment_overlay(environ or os.environ)
        if environment_overlay:
            merged = _merge(merged, environment_overlay)
            provenance.append("environment")
        if overrides:
            merged = _merge(merged, migrate_mapping(overrides))
            provenance.append("runtime overrides")

        try:
            value = ApplicationConfiguration.from_mapping(merged)
        except (TypeError, ValueError) as exc:
            raise ConfigurationError(f"Invalid configuration: {exc}") from exc
        if migrated_legacy is not None:
            backup = migrated_legacy.with_name(
                f"{migrated_legacy.name}.legacy-v1-{int(time.time())}.bak"
            )
            try:
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(migrated_legacy, backup)
                self.save(value, path=user)
                migrated.extend((backup, user))
            except OSError as exc:
                warnings.append(f"Could not persist settings migration: {exc}")

        return LoadedConfiguration(
            value=value,
            provenance=tuple(provenance),
            warnings=tuple(warnings),
            recovered_files=tuple(recovered),
            migrated_files=tuple(migrated),
        )

    def save(
        self,
        value: ApplicationConfiguration,
        *,
        path: str | Path | None = None,
    ) -> Path:
        target = Path(path or self._paths.runtime_config_file)
        atomic_write_json(target, value.to_dict())
        return target

    @staticmethod
    def _read_layer(
        path: Path,
        *,
        recover: bool,
        warnings: list[str],
    ) -> Mapping[str, Any] | None:
        if not path.is_file():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            warnings.append(f"Could not read {path.name}: {type(exc).__name__}")
            return None
        if not isinstance(value, dict):
            warnings.append(f"Ignored {path.name}: top-level value must be an object")
            return None
        return value

    @staticmethod
    def _read_user_layer(
        path: Path, warnings: list[str]
    ) -> tuple[Mapping[str, Any] | None, Path | None]:
        if not path.is_file():
            return None, None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise ValueError("top-level value must be an object")
            return value, None
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            backup = backup_if_corrupt_json(path)
            warnings.append(f"Recovered corrupt {path.name}: {type(exc).__name__}")
            return None, backup

    @staticmethod
    def _environment_overlay(environ: Mapping[str, str]) -> dict[str, Any]:
        overlay: dict[str, Any] = {}
        for env_name, (section, key, converter) in _ENVIRONMENT_KEYS.items():
            if env_name not in environ:
                continue
            raw = environ[env_name]
            try:
                value = _parse_bool(raw) if converter is bool else converter(raw)
            except (TypeError, ValueError) as exc:
                raise ConfigurationError(f"Invalid {env_name}: {exc}") from exc
            if section == "root":
                overlay[key] = value
            else:
                overlay.setdefault(section, {})[key] = value
        return overlay
