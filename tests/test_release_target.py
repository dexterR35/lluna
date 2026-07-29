from __future__ import annotations

import json

from backend.core.release_target import ReleaseTarget


def test_release_asset_names_are_unambiguous() -> None:
    assert (
        ReleaseTarget("windows", "x64", "cuda").asset_name("1.5.0")
        == "Midgard-1.5.0-windows-x64-cuda.exe"
    )
    assert (
        ReleaseTarget("linux", "x64", "cpu").asset_name("1.5.0")
        == "Midgard-1.5.0-linux-x64-cpu.tar.gz"
    )
    assert (
        ReleaseTarget("macos", "arm64", "mps").asset_name("1.5.0")
        == "Midgard-1.5.0-macos-arm64-mps.dmg"
    )


def test_release_metadata_is_valid_json_shape(tmp_path) -> None:
    value = {
        "platform": "windows",
        "architecture": "x64",
        "profile": "directml",
    }
    path = tmp_path / "midgard_release.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    assert json.loads(path.read_text(encoding="utf-8")) == value
