"""Safety boundary for the standard Midgard test suite."""

from __future__ import annotations

import socket
from pathlib import Path

import pytest

_NETWORK_MARKERS = {"network", "model_download"}


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "network: explicitly allows network access")


@pytest.fixture(autouse=True)
def isolated_runtime(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, request):
    """Keep tests away from user state and external services by default."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    monkeypatch.setenv("MIDGARD_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("MIDGARD_TESTING", "1")
    monkeypatch.setenv("HF_HOME", str(tmp_path / "hf"))
    monkeypatch.setenv("U2NET_HOME", str(tmp_path / "u2net"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("MIDGARD_DISABLE_UPDATE_CHECK", "1")
    monkeypatch.setenv("MIDGARD_DISABLE_MODEL_DOWNLOADS", "1")

    marked = {marker.name for marker in request.node.iter_markers()}
    if marked & _NETWORK_MARKERS:
        yield
        return

    def blocked_connection(*args, **kwargs):
        raise AssertionError("Network access is blocked in standard tests")

    monkeypatch.setattr(socket, "create_connection", blocked_connection)
    monkeypatch.setattr(socket.socket, "connect", blocked_connection)
    yield
