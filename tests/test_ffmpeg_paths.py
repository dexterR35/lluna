from __future__ import annotations

import pytest

from backend.diagnostics.errors import DependencyError
from backend.tools.ffmpeg_cli import resolve_ffmpeg_path


@pytest.mark.parametrize(
    ("system", "expected"),
    [
        ("Windows", "win_x64/ffmpeg.exe"),
        ("Linux", "linux_x64/ffmpeg"),
        ("Darwin", "macos/ffmpeg"),
    ],
)
def test_ffmpeg_path_is_platform_specific(tmp_path, system, expected) -> None:
    assert resolve_ffmpeg_path(tmp_path, system) == tmp_path / expected


def test_unsupported_ffmpeg_platform_is_explicit(tmp_path) -> None:
    with pytest.raises(DependencyError):
        resolve_ffmpeg_path(tmp_path, "Haiku")
