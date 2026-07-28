"""Immutable model metadata and lifecycle states."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ModelState(str, Enum):
    NOT_INSTALLED = "not_installed"
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    VERIFYING = "verifying"
    INSTALLED = "installed"
    LOADING = "loading"
    READY = "ready"
    BUSY = "busy"
    UNLOADING = "unloading"
    BROKEN = "broken"
    INCOMPATIBLE = "incompatible"


@dataclass(frozen=True)
class ExpectedFile:
    relative_path: str
    size_bytes: int | None = None
    sha256: str | None = None
    required: bool = True


@dataclass(frozen=True)
class ModelMetadata:
    id: str
    display_name: str
    purpose: str
    framework: str
    source: str
    license: str
    gated: bool
    local_path: str
    expected_files: tuple[ExpectedFile, ...] = ()
    expected_size_bytes: int | None = None
    minimum_ram_mb: int = 0
    minimum_vram_mb: int = 0
    compatible_backends: tuple[str, ...] = ("cpu",)
    dtype: str = "auto"
    version: str = "unversioned"
    enabled_by_default: bool = False
    cache_policy: str = "bounded"
    unload_policy: str = "idle"
