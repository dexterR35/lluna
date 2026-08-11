"""Filesystem-backed registry for user models and manifests."""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

from backend.core.atomic import atomic_write_json
from backend.core.paths import AppPaths
from backend.models.reference.manifest import (
    MANIFEST_FILENAME,
    ManifestError,
    ModelManifest,
    inferred_manifest,
    model_files,
    validate_custom_model_security,
)
from backend.models.reference.runtimes import runtime_status

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
        # Model installed, runtime installed and hardware compatible are three
        # independent facts; a model is only usable when all three hold.
        runnable = self.installed and not needs_configuration and status["runnable"]
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
            "enabled": self.enabled and runnable,
            "runtime_installed": status["installed"],
            "state": state,
            "disk_usage_bytes": _disk_usage(self.path),
            # Only "huggingface" has a working installer (importer.py's
            # install_huggingface). "url" is a valid ModelSource.type but no
            # registration path ever produces a dynamic record with it, and
            # install_huggingface rejects one outright - advertising it as
            # installable here would promise something that always fails.
            "can_install": self.manifest.source.type == "huggingface" and not self.installed,
            "can_uninstall": True,
            "can_toggle": not needs_configuration and status["runnable"],
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

    def __init__(self, paths: AppPaths | None = None) -> None:
        # See ConfigurationLoader.__init__ for why this isn't `= PATHS`: a
        # frozen default would ignore any LLUNA_MODELS_DIR/LLUNA_CONFIG_DIR
        # override set after this class was first imported.
        paths = paths if paths is not None else AppPaths.resolve()
        self.paths = paths
        self.root = paths.models_dir / "custom"
        self.staging_root = paths.models_dir / ".staging"
        self.quarantine_root = paths.models_dir / ".quarantine"
        self.state_path = paths.config_dir / "model-platform-state.json"
        self._lock = threading.RLock()
        self._listeners: set[RegistryListener] = set()
        self._records: dict[str, DynamicModelRecord] = {}
        self.ensure_layout()
        self._load_startup()

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
            record = self._records.get(model_id)
            if record is None:
                raise KeyError(model_id)
            values = self._enabled_state()
            values[model_id] = bool(enabled)
            atomic_write_json(self.state_path, {"schema": 1, "enabled": values})
            self._records[model_id] = replace(record, enabled=bool(enabled))
            listeners = tuple(self._listeners)
        self._notify(listeners)

    def _load_startup(self) -> None:
        self.ensure_layout()
        enabled = self._enabled_state()
        found: dict[str, DynamicModelRecord] = {}
        for item in sorted(self.root.iterdir(), key=lambda value: value.name.lower()):
            if item.name.startswith("."):
                continue
            try:
                record = self._scan_item(item, enabled)
            except ManifestError as exc:
                logger.warning(
                    "Skipping unsupported custom model %s: %s",
                    item.name,
                    exc,
                )
                continue
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
            self._records = found

    @staticmethod
    def _notify(listeners: tuple[RegistryListener, ...]) -> None:
        for listener in listeners:
            try:
                listener()
            except Exception:
                logger.exception("Dynamic model registry listener failed")

    def record_path(self, path: Path) -> DynamicModelRecord:
        """Update one path after a Lluna-owned filesystem mutation."""
        record = self._scan_item(path, self._enabled_state())
        with self._lock:
            self._records = {
                key: value
                for key, value in self._records.items()
                if value.path != path and key != record.manifest.id
            }
            self._records[record.manifest.id] = record
            listeners = tuple(self._listeners)
        self._notify(listeners)
        return record

    def remove(self, model_id: str) -> None:
        with self._lock:
            if self._records.pop(model_id, None) is None:
                raise KeyError(model_id)
            listeners = tuple(self._listeners)
        self._notify(listeners)

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
        try:
            validate_custom_model_security(manifest, item)
        except ManifestError as exc:
            error = error or str(exc)
        installed = _is_installed(item, manifest)
        return DynamicModelRecord(
            manifest,
            item,
            installed,
            enabled.get(manifest.id, False),
            error,
            discovered,
        )

    def records(self) -> list[DynamicModelRecord]:
        return list(self._records.values())

    def get(self, model_id: str) -> DynamicModelRecord:
        try:
            return self._records[model_id]
        except KeyError as exc:
            raise KeyError(model_id) from exc

    def revision_stamp(self, model_id: str) -> str:
        """Fingerprint of a custom model's on-disk files.

        Changes whenever the model's watched files are replaced (re-import,
        reconfigure) even though its id stays the same, so content-addressed
        node caches (see `backend.graph.cache.build_cache_key`) can tell a
        stale cached artifact apart from a genuinely-unchanged model.
        """
        try:
            record = self.get(model_id)
        except KeyError:
            return ""
        mtime_ns, size = _path_stamp(record.path, record.manifest.expected_files)
        return f"{mtime_ns}:{size}"

    def register(self, manifest: ModelManifest) -> Path:
        from backend.models.reference.catalog import MODEL_REGISTRY

        if manifest.id in MODEL_REGISTRY or manifest.id.startswith("generate:"):
            raise ManifestError(f"Model id {manifest.id!r} is reserved by Lluna.")
        target = self.root / manifest.id
        target.mkdir(parents=True, exist_ok=True)
        atomic_write_json(target / MANIFEST_FILENAME, manifest.to_dict())
        self.record_path(target)
        return target

    def configure(self, current_id: str, manifest: ModelManifest) -> Path:
        record = self.get(current_id)
        if manifest.id != current_id:
            raise ManifestError("A discovered model id cannot be changed in place.")
        if not record.path.is_dir():
            raise ManifestError("Import standalone model files with Add model before configuring them.")
        atomic_write_json(record.path / MANIFEST_FILENAME, manifest.to_dict())
        self.record_path(record.path)
        return record.path

    def subscribe(self, listener: RegistryListener) -> Callable[[], None]:
        with self._lock:
            self._listeners.add(listener)

        def unsubscribe() -> None:
            with self._lock:
                self._listeners.discard(listener)

        return unsubscribe

def _is_installed(path: Path, manifest: ModelManifest) -> bool:
    if path.is_file():
        return path.stat().st_size > 0
    if (path / ".lluna-installed").is_file():
        return True
    if manifest.expected_files:
        return all((path / relative).is_file() for relative in manifest.expected_files)
    return bool(model_files(path)) and manifest.source.type == "local"


def _path_stamp(path: Path, expected_files: tuple[str, ...]) -> tuple[int, int]:
    """Cheap fingerprint of everything that can change a model's output.

    Watches every recognized weight file on disk, not just the manifest's
    ``expected_files``: a discovered or hand-edited model may declare an
    incomplete list, and a weight file swapped in place keeps the directory's
    own mtime, so a stamp built only from the declared list would not move and
    node caches would serve artifacts produced by the previous weights.

    Metadata only (mtime plus size) - hashing multi-gigabyte weights on every
    inventory refresh would cost far more than it is worth here.
    """
    try:
        if path.is_file():
            stat = path.stat()
            return stat.st_mtime_ns, stat.st_size
        watched = {path / MANIFEST_FILENAME, path / ".lluna-installed"}
        watched.update(path / relative for relative in expected_files)
        watched.update(model_files(path))
        watched.update(item for item in path.glob("*.json"))
        stamps = [item.stat() for item in sorted(watched) if item.is_file()]
        root = path.stat()
        return max((stamp.st_mtime_ns for stamp in stamps), default=root.st_mtime_ns), sum(
            stamp.st_size for stamp in stamps
        )
    except OSError:
        return 0, 0
