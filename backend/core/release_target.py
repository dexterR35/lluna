"""Platform/profile identity used by packaged releases and update selection."""

from __future__ import annotations

import json
import os
import platform
import sys
from dataclasses import dataclass

from backend.core.paths import PATHS

_METADATA_NAME = "lluna_release.json"
_PROFILES = frozenset({"cpu", "cuda", "directml", "mps", "source"})


def _normalized_architecture(value: str) -> str:
    normalized = value.strip().lower().replace("amd64", "x64")
    normalized = normalized.replace("x86_64", "x64")
    normalized = normalized.replace("aarch64", "arm64")
    return normalized or "unknown"


def _platform_name() -> str:
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


@dataclass(frozen=True)
class ReleaseTarget:
    platform: str
    architecture: str
    profile: str

    @property
    def key(self) -> str:
        return f"{self.platform}-{self.architecture}-{self.profile}"

    @property
    def package_extension(self) -> str:
        return {
            "windows": "exe",
            "macos": "dmg",
            "linux": "tar.gz",
        }[self.platform]

    def asset_name(self, version: str) -> str:
        return (
            f"Lluna-{version}-{self.platform}-{self.architecture}-"
            f"{self.profile}.{self.package_extension}"
        )


def current_release_target() -> ReleaseTarget:
    """Read immutable build metadata, falling back to a source-install target."""
    metadata_path = PATHS.project_root / _METADATA_NAME
    if metadata_path.is_file():
        try:
            value = json.loads(metadata_path.read_text(encoding="utf-8"))
            target = ReleaseTarget(
                platform=str(value["platform"]),
                architecture=_normalized_architecture(str(value["architecture"])),
                profile=str(value["profile"]),
            )
            if target.profile in _PROFILES:
                return target
        except (OSError, UnicodeError, ValueError, KeyError, TypeError):
            pass
    profile_name = os.environ.get("LLUNA_BUILD_PROFILE", "source").lower()
    if profile_name not in _PROFILES:
        profile_name = "source"
    return ReleaseTarget(
        platform=_platform_name(),
        architecture=_normalized_architecture(platform.machine()),
        profile=profile_name,
    )
