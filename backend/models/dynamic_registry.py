"""Filesystem-backed registry for user models and manifests."""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from backend.core.atomic import atomic_write_json
from backend.core.paths import PATHS, AppPaths
from backend.models.manifest import (
    MANIFEST_FILENAME,
    ManifestError,
    ModelManifest,
    inferred_manifest,
    model_files,
)
from backend.models.runtime_profiles import runtime_status

logger = logging.getLogger(__name__)
RegistryListener = Callable[[], None]


@dataclass(frozen=True)
class DynamicModelRecord:
    manifest: ModelManifest
    path: Path
    installed: bool
    enabled: bool
    error: str = ""
    discovered: bool = False

    def to_inventory(self) -> dict:
        status = runtime_status(self.manifest)
        needs_configuration = not self.manifest.is_configured() or bool(self.error)
        state = (
            "needs_configuration"
            if needs_configuration
            else "incompatible"
            if not status["compatible"]
            else "installed"
            if self.installed
            else "not_installed"
        )
        return {
            "id": self.manifest.id,
            "display_name": self.manifest.name,
            "purpose": self.manifest.description or self.manifest.task.replace("-", " ").title(),
            "framework": self.manifest.adapter,
            "source": self.manifest.source.repo or self.manifest.source.url or self.manifest.source.type,
            "license": self.manifest.license,
            "gated": self.manifest.gated,
            "resolved_path": str(self.path),
            "installed": self.installed,
            "enabled": self.enabled and self.installed and not needs_configuration and status["compatible"],
            "state": state,
            "disk_usage_bytes": _disk_usage(self.path),
            "can_install": self.manifest.source.type in {"huggingface", "url"} and not self.installed,
            "can_uninstall": True,
            "can_toggle": not needs_configuration and status["compatible"],
            "dynamic": True,
            "discovered": self.discovered,
            "needs_configuration": needs_configuration,
            "manifest_error": self.error,
            "task": self.manifest.task,
            "adapter": self.manifest.adapter,
            "variant": self.manifest.variant.to_dict(),
            "capabilities": self.manifest.capabilities.to_dict(self.manifest.task),
            "runtime": status,
            "manifest": self.manifest.to_dict(),
        }


def _disk_usage(path: Path) -> int:
    try:
        if path.is_file():
            return path.stat().st_size
        return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())
    except OSError:
        return 0


class DynamicModelRegistry:
    _instance: "DynamicModelRegistry | None" = None
    _instance_lock = threading.Lock()

    def __init__(self, paths: AppPaths = PATHS) -> None:
        self.paths = paths
        self.root = paths.models_dir / "custom"
        self.staging_root = paths.models_dir / ".staging"
        self.quarantine_root = paths.models_dir / ".quarantine"
        self.state_path = paths.config_dir / "model-platform-state.json"
        self._lock = threading.RLock()
        self._listeners: set[RegistryListener] = set()
        self._records: dict[str, DynamicModelRecord] = {}
        self._watcher: threading.Thread | None = None
        self._stop_watcher = threading.Event()
        self.ensure_layout()
        self.scan()

    @classmethod
    def instance(cls) -> "DynamicModelRegistry":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    @classmethod
    def reset_for_tests(cls) -> None:
        with cls._instance_lock:
            cls._instance = None

    def ensure_layout(self) -> None:
        for path in (self.root, self.staging_root, self.quarantine_root):
            path.mkdir(parents=True, exist_ok=True)

    def _enabled_state(self) -> dict[str, bool]:
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
            values = raw.get("enabled", {}) if isinstance(raw, dict) else {}
            return {str(key): bool(value) for key, value in values.items()}
        except (OSError, ValueError, TypeError):
            return {}

    def set_enabled(self, model_id: str, enabled: bool) -> None:
        with self._lock:
            if model_id not in self._records:
                raise KeyError(model_id)
            values = self._enabled_state()
            values[model_id] = bool(enabled)
            atomic_write_json(self.state_path, {"schema": 1, "enabled": values})
            self.scan()

    def scan(self) -> list[DynamicModelRecord]:
        self.ensure_layout()
        enabled = self._enabled_state()
        found: dict[str, DynamicModelRecord] = {}
        for item in sorted(self.root.iterdir(), key=lambda value: value.name.lower()):
            if item.name.startswith("."):
                continue
            record = self._scan_item(item, enabled)
            identifier = record.manifest.id
            if identifier in found:
                duplicate = DynamicModelRecord(
                    record.manifest,
                    record.path,
                    record.installed,
                    False,
                    f"Duplicate model id: {identifier}",
                    record.discovered,
                )
                found[f"{identifier}--duplicate-{item.name}"] = duplicate
            else:
                found[identifier] = record
        with self._lock:
            changed = _fingerprint(self._records) != _fingerprint(found)
            self._records = found
            listeners = tuple(self._listeners) if changed else ()
        for listener in listeners:
            try:
                listener()
            except Exception:
                logger.exception("Dynamic model registry listener failed")
        return list(found.values())

    def _scan_item(self, item: Path, enabled: dict[str, bool]) -> DynamicModelRecord:
        manifest_path = item / MANIFEST_FILENAME if item.is_dir() else None
        error = ""
        discovered = not bool(manifest_path and manifest_path.is_file())
        try:
            manifest = (
                ModelManifest.from_file(manifest_path)
                if manifest_path and manifest_path.is_file()
                else inferred_manifest(item)
            )
        except ManifestError as exc:
            manifest = inferred_manifest(item)
            error = str(exc)
        installed = _is_installed(item, manifest)
        return DynamicModelRecord(
            manifest,
            item,
            installed,
            enabled.get(manifest.id, False),
            error,
            discovered,
        )

    def records(self, *, refresh: bool = True) -> list[DynamicModelRecord]:
        return self.scan() if refresh else list(self._records.values())

    def get(self, model_id: str, *, refresh: bool = True) -> DynamicModelRecord:
        if refresh:
            self.scan()
        try:
            return self._records[model_id]
        except KeyError as exc:
            raise KeyError(model_id) from exc

    def register(self, manifest: ModelManifest) -> Path:
        from backend.models.registry import MODEL_REGISTRY

        if manifest.id in MODEL_REGISTRY or manifest.id.startswith(("generate:", "bg-remove:")):
            raise ManifestError(f"Model id {manifest.id!r} is reserved by Midgard.")
        target = self.root / manifest.id
        target.mkdir(parents=True, exist_ok=True)
        atomic_write_json(target / MANIFEST_FILENAME, manifest.to_dict())
        self.scan()
        return target

    def configure(self, current_id: str, manifest: ModelManifest) -> Path:
        record = self.get(current_id)
        if manifest.id != current_id:
            raise ManifestError("A discovered model id cannot be changed in place.")
        if not record.path.is_dir():
            raise ManifestError("Import standalone model files with Add model before configuring them.")
        atomic_write_json(record.path / MANIFEST_FILENAME, manifest.to_dict())
        self.scan()
        return record.path

    def subscribe(self, listener: RegistryListener) -> Callable[[], None]:
        with self._lock:
            self._listeners.add(listener)

        def unsubscribe() -> None:
            with self._lock:
                self._listeners.discard(listener)

        return unsubscribe

    def start_watcher(self, *, interval_seconds: float = 2.0) -> None:
        """Poll the user model folder without adding a native watcher dependency."""
        with self._lock:
            if self._watcher is not None and self._watcher.is_alive():
                return
            self._stop_watcher.clear()

            def watch() -> None:
                while not self._stop_watcher.wait(max(0.5, interval_seconds)):
                    try:
                        self.scan()
                    except OSError:
                        logger.exception("Could not rescan the custom model folder")

            self._watcher = threading.Thread(
                target=watch, name="midgard-model-watcher", daemon=True
            )
            self._watcher.start()

    def stop_watcher(self) -> None:
        self._stop_watcher.set()
        watcher = self._watcher
        if watcher is not None and watcher is not threading.current_thread():
            watcher.join(timeout=3.0)
        with self._lock:
            if self._watcher is watcher:
                self._watcher = None


def _is_installed(path: Path, manifest: ModelManifest) -> bool:
    if path.is_file():
        return path.stat().st_size > 0
    if (path / ".midgard-installed").is_file():
        return True
    if manifest.expected_files:
        return all((path / relative).is_file() for relative in manifest.expected_files)
    return bool(model_files(path)) and manifest.source.type == "local"


def _fingerprint(records: dict[str, DynamicModelRecord]) -> tuple:
    return tuple(
        sorted(
            (
                key,
                str(record.path),
                record.installed,
                record.enabled,
                record.error,
                _path_stamp(record.path, record.manifest.expected_files),
            )
            for key, record in records.items()
        )
    )


def _path_stamp(path: Path, expected_files: tuple[str, ...]) -> tuple[int, int]:
    try:
        if path.is_file():
            stat = path.stat()
            return stat.st_mtime_ns, stat.st_size
        watched = [path / MANIFEST_FILENAME, path / ".midgard-installed"]
        watched.extend(path / relative for relative in expected_files)
        stamps = [item.stat() for item in watched if item.is_file()]
        root = path.stat()
        return max((stamp.st_mtime_ns for stamp in stamps), default=root.st_mtime_ns), sum(
            stamp.st_size for stamp in stamps
        )
    except OSError:
        return 0, 0
