from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_packaging_inputs_validate_without_building() -> None:
    subprocess.run(
        [sys.executable, "packaging/build.py", "--validate-only"],
        check=True,
    )


def test_spec_does_not_recursively_bundle_user_model_root() -> None:
    source = Path("packaging/midgard.spec").read_text(encoding="utf-8")
    assert '(ROOT / "backend/models").rglob' not in source
    assert "backend/models/generate" not in source
    assert "backend/models/select_object" not in source
    assert "config/config.json" not in source
    assert "hf_token" not in source


def test_desktop_packaging_metadata_is_present() -> None:
    desktop = Path("packaging/linux/midgard.desktop").read_text(encoding="utf-8")
    spec = Path("packaging/midgard.spec").read_text(encoding="utf-8")
    assert "Type=Application" in desktop
    assert "Exec=Midgard" in desktop
    assert 'name="Midgard.app"' in spec


def test_release_workflow_has_platform_profiles_and_security_gates() -> None:
    workflow = Path(".github/workflows/desktop-build.yml").read_text(
        encoding="utf-8"
    )
    for target in (
        "windows-x64-cpu",
        "windows-x64-cuda",
        "windows-x64-directml",
        "linux-x64-cpu",
        "linux-x64-cuda",
        "macos-x64-mps",
    ):
        assert target in workflow
    assert "signtool" in workflow.lower()
    assert "notarytool" in workflow
    assert "MIDGARD_UPDATE_PRIVATE_KEY_B64" in workflow
    assert "attest-build-provenance" in workflow


def test_native_package_definitions_are_present() -> None:
    assert Path("packaging/windows/Midgard.iss").is_file()
    assert Path("packaging/linux/package.py").is_file()
    assert Path("packaging/macos/create_dmg.sh").is_file()


def test_declared_release_versions_are_consistent() -> None:
    subprocess.run(
        [sys.executable, "packaging/verify_release.py", "--tag", "v1.4.0"],
        check=True,
    )
