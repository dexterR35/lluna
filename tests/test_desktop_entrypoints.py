from pathlib import Path


def test_electron_is_the_only_desktop_entrypoint():
    assert Path("frontend/electron/main.js").is_file()
    assert Path("frontend/electron/preload.js").is_file()
    assert not Path("gui.py").exists()
    assert not Path("ui").exists()


def test_python_entrypoint_is_control_plane_only():
    source = Path("lluna.py").read_text(encoding="utf-8")
    assert "backend.api.app" in source
    assert "freeze_support" in source


def test_browser_window_security_is_explicit():
    source = Path("frontend/electron/main.js").read_text(encoding="utf-8")
    assert "nodeIntegration: false" in source
    assert "contextIsolation: true" in source
    assert "sandbox: true" in source
    assert "webSecurity: true" in source
