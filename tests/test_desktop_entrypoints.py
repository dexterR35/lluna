from pathlib import Path


def test_electron_is_the_only_desktop_entrypoint():
    assert Path("frontend/electron/main.js").is_file()
    assert Path("frontend/electron/preload.js").is_file()
    assert not Path("gui.py").exists()
    assert not Path("ui").exists()


def test_python_entrypoint_is_control_plane_only():
    """The Python entry point serves the API and runs graphs — it never draws UI.

    It dispatches through backend.cli (serve / run / templates), which forwards
    to backend.api.app; both are checked so the indirection cannot become a way
    to smuggle a second UI stack into the sidecar.
    """
    source = Path("lluna.py").read_text(encoding="utf-8")
    assert "backend.cli" in source
    assert "freeze_support" in source

    cli = Path("backend/cli.py").read_text(encoding="utf-8")
    assert "backend.api.app" in cli
    for forbidden in ("tkinter", "PyQt", "PySide", "wx"):
        assert forbidden not in cli and forbidden not in source


def test_headless_entry_points_are_documented_in_the_parser():
    """`serve` keeps the desktop app working; `run` is what automation uses."""
    from backend.cli import build_parser

    parser = build_parser()
    subcommands = {
        name
        for action in parser._subparsers._group_actions  # noqa: SLF001 - argparse has no public API
        for name in action.choices
    }

    assert {"serve", "run", "templates"} <= subcommands


def test_browser_window_security_is_explicit():
    source = Path("frontend/electron/main.js").read_text(encoding="utf-8")
    assert "nodeIntegration: false" in source
    assert "contextIsolation: true" in source
    assert "sandbox: true" in source
    assert "webSecurity: true" in source
