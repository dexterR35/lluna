from __future__ import annotations

from pathlib import Path

from backend.tools.model_download_lifecycle import prepare_restart_pending
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


def test_idle_shutdown_does_not_leave_download_cancel_flag(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir(exist_ok=True)
    monkeypatch.setenv("MIDGARD_CONFIG_DIR", str(config_dir))
    cancel = config_dir / "model_download_cancel.flag"
    cancel.write_text("1", encoding="utf-8")

    registry = ModelDownloadRegistry()
    assert registry.abort_all_and_revert() == []

    assert not cancel.exists()


def test_startup_recovery_clears_stale_cancel_and_keeps_retry_items(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir(exist_ok=True)
    monkeypatch.setenv("MIDGARD_CONFIG_DIR", str(config_dir))
    (config_dir / "model_download_cancel.flag").write_text("1", encoding="utf-8")
    (config_dir / "pending_model_downloads.json").write_text(
        '[{"kind":"enhance","key":"RealESRGAN_x2plus"}]',
        encoding="utf-8",
    )
    registry = ModelDownloadRegistry()
    monkeypatch.setattr(ModelDownloadRegistry, "_instance", registry)

    recovered = prepare_restart_pending()

    assert [(item.kind, item.key) for item in recovered] == [
        ("enhance", "RealESRGAN_x2plus")
    ]
    assert not registry.is_cancelled()
    assert [(item.kind, item.key) for item in registry.list_pending()] == [
        ("enhance", "RealESRGAN_x2plus")
    ]
