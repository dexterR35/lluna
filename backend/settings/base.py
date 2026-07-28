"""Base validation and serialization for model-specific settings."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any, ClassVar

from backend.settings.metadata import SettingMetadata


@dataclass(frozen=True)
class ModelSettings:
    SCHEMA_VERSION: ClassVar[int] = 1
    METADATA: ClassVar[dict[str, SettingMetadata]] = {}

    def __post_init__(self) -> None:
        for field in fields(self):
            spec = self.METADATA.get(field.name)
            if spec:
                spec.validate(getattr(self, field.name))

    def to_snapshot(self) -> dict[str, Any]:
        return {"schema_version": self.SCHEMA_VERSION, **asdict(self)}

    @classmethod
    def from_mapping(cls, values: dict[str, Any]) -> "ModelSettings":
        allowed = {field.name for field in fields(cls)}
        return cls(**{key: value for key, value in values.items() if key in allowed})
