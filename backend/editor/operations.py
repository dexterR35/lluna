"""Versioned operation execution contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from backend.editor.buffers import BufferKind


class RenderProfile(str, Enum):
    INTERACTIVE = "interactive"
    HIGH_QUALITY_PREVIEW = "high_quality_preview"
    FINAL = "final"


class Locality(str, Enum):
    LOCAL = "local"
    GLOBAL = "global"
    TEMPORAL = "temporal"


@dataclass(frozen=True)
class OperationContract:
    """Static facts used by render planning and validation."""

    operation_type: str
    schema_version: int
    input_kinds: tuple[BufferKind, ...]
    output_kinds: tuple[BufferKind, ...]
    locality: Locality
    padding_px: int = 0
    tile_overlap_px: int = 0
    deterministic: bool = True
    supports_cpu: bool = True
    supports_proxy: bool = True

    def __post_init__(self) -> None:
        if "." not in self.operation_type:
            raise ValueError("operation type must be namespaced, for example alpha.refine")
        if self.schema_version < 1:
            raise ValueError("operation schema version must be positive")
        if not self.input_kinds:
            raise ValueError("operation must declare at least one input")
        if not self.output_kinds:
            raise ValueError("operation must declare at least one output")
        if self.padding_px < 0 or self.tile_overlap_px < 0:
            raise ValueError("operation padding and overlap cannot be negative")
