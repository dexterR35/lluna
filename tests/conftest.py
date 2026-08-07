"""Safety boundary for the standard Lluna test suite."""

from __future__ import annotations

import ipaddress
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
    monkeypatch.setenv("LLUNA_CONFIG_DIR", str(config_dir))
    # LLUNA_DATA_DIR/LLUNA_MODELS_DIR were previously unset here, so any
    # singleton whose *default* path fell back to `root / "backend" /
    # "models"` (DynamicModelRegistry, HardwareDetector's disk probe) wrote
    # into the real project directory instead of this test's tmp_path.
    monkeypatch.setenv("LLUNA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("LLUNA_MODELS_DIR", str(tmp_path / "models"))
    monkeypatch.setenv("LLUNA_TESTING", "1")
    monkeypatch.setenv("HF_HOME", str(tmp_path / "hf"))
    monkeypatch.setenv("U2NET_HOME", str(tmp_path / "u2net"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("LLUNA_DISABLE_UPDATE_CHECK", "1")
    monkeypatch.setenv("LLUNA_DISABLE_MODEL_DOWNLOADS", "1")

    # `backend.core.paths.PATHS` and the process-wide singletons whose
    # default paths are bound at construction time are reset *after* the env
    # vars above are set, so a fresh `.instance()` call resolves against this
    # test's isolated tmp_path instead of a stale (or real) location. Without
    # this, tests that call `get_settings()`/`update_settings()` or touch the
    # dynamic model registry without manually constructing an isolated
    # instance silently read/write the real project's `config/` directory.
    from backend.configuration.service import ConfigurationService
    from backend.models.dynamic_registry import DynamicModelRegistry

    ConfigurationService.reset_for_tests()
    DynamicModelRegistry.reset_for_tests()

    marked = {marker.name for marker in request.node.iter_markers()}
    if marked & _NETWORK_MARKERS:
        yield
        return

    real_create_connection = socket.create_connection
    real_socket_connect = socket.socket.connect

    def is_loopback(address) -> bool:
        if not isinstance(address, tuple) or not address:
            return False
        host = address[0]
        if isinstance(host, str) and host.lower() == "localhost":
            return True
        try:
            return ipaddress.ip_address(host).is_loopback
        except ValueError:
            return False

    def blocked_create_connection(address, *args, **kwargs):
        if is_loopback(address):
            return real_create_connection(address, *args, **kwargs)
        raise AssertionError("Network access is blocked in standard tests")

    def blocked_socket_connect(sock, address):
        if is_loopback(address):
            return real_socket_connect(sock, address)
        raise AssertionError("Network access is blocked in standard tests")

    monkeypatch.setattr(socket, "create_connection", blocked_create_connection)
    monkeypatch.setattr(socket.socket, "connect", blocked_socket_connect)
    yield
