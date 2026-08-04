"""Thread-safe settings service used by the API and inference adapters."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable, Mapping

from backend.configuration.loader import ConfigurationLoader
from backend.configuration.models import ApplicationConfiguration

SettingsListener = Callable[[ApplicationConfiguration], None]


def _deep_merge(base: dict[str, Any], patch: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in patch.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
            merged[key] = _deep_merge(dict(merged[key]), value)
        else:
            merged[key] = value
    return merged


class ConfigurationService:
    _instance: "ConfigurationService | None" = None
    _instance_lock = threading.Lock()

    def __init__(self, loader: ConfigurationLoader | None = None) -> None:
        self._loader = loader or ConfigurationLoader()
        self._lock = threading.RLock()
        self._listeners: set[SettingsListener] = set()
        self._value = self._loader.load().value

    @classmethod
    def instance(cls) -> "ConfigurationService":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    @classmethod
    def reset_for_tests(cls) -> None:
        with cls._instance_lock:
            cls._instance = None

    def get(self) -> ApplicationConfiguration:
        with self._lock:
            return self._value

    def update(self, patch: Mapping[str, Any]) -> ApplicationConfiguration:
        with self._lock:
            merged = _deep_merge(self._value.to_dict(), patch)
            updated = ApplicationConfiguration.from_mapping(merged)
            self._loader.save(updated)
            self._value = updated
            listeners = tuple(self._listeners)
        for listener in listeners:
            listener(updated)
        return updated

    def replace(self, value: ApplicationConfiguration) -> ApplicationConfiguration:
        with self._lock:
            self._loader.save(value)
            self._value = value
            listeners = tuple(self._listeners)
        for listener in listeners:
            listener(value)
        return value

    def reset_section(self, section: str) -> ApplicationConfiguration:
        defaults = ApplicationConfiguration().to_dict()
        if section == "save_directory":
            return self.update({"save_directory": defaults["save_directory"]})
        if section not in defaults:
            raise KeyError(f"Unknown settings section: {section}")
        return self.update({section: defaults[section]})

    def subscribe(self, listener: SettingsListener) -> Callable[[], None]:
        with self._lock:
            self._listeners.add(listener)

        def unsubscribe() -> None:
            with self._lock:
                self._listeners.discard(listener)

        return unsubscribe

    @property
    def path(self) -> Path:
        return self._loader._paths.runtime_config_file


def get_settings() -> ApplicationConfiguration:
    return ConfigurationService.instance().get()


def update_settings(patch: Mapping[str, Any]) -> ApplicationConfiguration:
    return ConfigurationService.instance().update(patch)
