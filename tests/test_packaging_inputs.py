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
