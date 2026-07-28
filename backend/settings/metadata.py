"""User-facing metadata for typed settings."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class SettingsLevel(str, Enum):
    SIMPLE = "simple"
    ADVANCED = "advanced"
    EXPERT = "expert"


@dataclass(frozen=True)
class SettingMetadata:
    name: str
    value_type: type
    default: Any
    label: str
    description: str
    level: SettingsLevel
    minimum: float | int | None = None
    maximum: float | int | None = None
    choices: tuple[Any, ...] = ()
    compatible_models: tuple[str, ...] = ()
    compatible_backends: tuple[str, ...] = ("cpu", "cuda", "directml", "mps")
    restart_required: bool = False

    def validate(self, value: Any) -> Any:
        if self.value_type is bool:
            if not isinstance(value, bool):
                raise TypeError(f"{self.name} must be a boolean")
        elif not isinstance(value, self.value_type):
            raise TypeError(f"{self.name} must be {self.value_type.__name__}")
        if self.minimum is not None and value < self.minimum:
            raise ValueError(f"{self.name} must be at least {self.minimum}")
        if self.maximum is not None and value > self.maximum:
            raise ValueError(f"{self.name} must be at most {self.maximum}")
        if self.choices and value not in self.choices:
            raise ValueError(f"{self.name} must be one of {self.choices}")
        return value
