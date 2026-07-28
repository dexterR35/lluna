from __future__ import annotations

from pathlib import Path

from backend.tools.model_download_registry import ModelDownloadRegistry


def test_corrupt_pending_state_is_backed_up(monkeypatch, tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir(exist_ok=True)
    monkeypatch.setenv("MIDGARD_CONFIG_DIR", str(config_dir))
    pending = config_dir / "pending_model_downloads.json"
    pending.write_text("{broken", encoding="utf-8")
    registry = ModelDownloadRegistry()
    assert registry.list_pending() == []
    assert not pending.exists()
    assert list(config_dir.glob("pending_model_downloads.json.corrupt-*"))
