from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_packaging_inputs_validate_without_building():
    subprocess.run(  # noqa: S603
        [sys.executable, "packaging/build.py", "--validate-only"],
        check=True,
    )


def test_sidecar_spec_excludes_removed_gui_and_user_model_roots():
    source = Path("packaging/backend-sidecar.spec").read_text(encoding="utf-8")
    assert '(ROOT / "backend/models").rglob' not in source
    assert "backend/models/generate" not in source
    assert "config/config.json" not in source
    assert "hf_token" not in source
    assert 'name="midgard-backend"' in source


def test_forge_embeds_only_the_frozen_sidecar():
    source = Path("frontend/forge.config.js").read_text(encoding="utf-8")
    assert '"build", "backend-sidecar", "midgard-backend"' in source
    assert (
        'rename(path.join(resourcesPath, "midgard-backend"), path.join(resourcesPath, "backend-sidecar"))'
        in source
    )
    assert '"..", "backend"' not in source
    assert "@electron-forge/plugin-vite" in source


def test_python_process_uses_hidden_packaged_sidecar():
    source = Path("frontend/electron/python-process.js").read_text(encoding="utf-8")
    assert "windowsHide: true" in source
    assert 'path.join(process.resourcesPath, "backend-sidecar", executable)' in source
