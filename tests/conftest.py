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
    monkeypatch.setenv("LLUNA_TESTING", "1")
    monkeypatch.setenv("HF_HOME", str(tmp_path / "hf"))
    monkeypatch.setenv("U2NET_HOME", str(tmp_path / "u2net"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("LLUNA_DISABLE_UPDATE_CHECK", "1")
    monkeypatch.setenv("LLUNA_DISABLE_MODEL_DOWNLOADS", "1")

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
