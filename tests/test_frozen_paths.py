from __future__ import annotations

from pathlib import Path

from backend.core.paths import AppPaths


def test_source_paths_remain_inside_checkout(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    monkeypatch.setenv("MIDGARD_PROJECT_ROOT", str(root))
    monkeypatch.delenv("MIDGARD_CONFIG_DIR", raising=False)
    monkeypatch.delenv("MIDGARD_DATA_DIR", raising=False)
    monkeypatch.delenv("MIDGARD_MODELS_DIR", raising=False)
    monkeypatch.delattr("sys.frozen", raising=False)

    paths = AppPaths.resolve()

    assert paths.config_dir == root / "config"
    assert paths.models_dir == root / "backend" / "models"


def test_frozen_linux_paths_are_user_writable(monkeypatch, tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    config_home = tmp_path / "config-home"
    data_home = tmp_path / "data-home"
    monkeypatch.setattr("sys.frozen", True, raising=False)
    monkeypatch.setattr("sys._MEIPASS", str(bundle), raising=False)
    monkeypatch.setattr("sys.executable", str(bundle / "Midgard"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    monkeypatch.setenv("XDG_DATA_HOME", str(data_home))
    monkeypatch.delenv("MIDGARD_PROJECT_ROOT", raising=False)
    monkeypatch.delenv("MIDGARD_CONFIG_DIR", raising=False)
    monkeypatch.delenv("MIDGARD_DATA_DIR", raising=False)
    monkeypatch.delenv("MIDGARD_MODELS_DIR", raising=False)

    paths = AppPaths.resolve()

    assert paths.project_root == bundle
    assert paths.config_dir == config_home / "midgard"
    assert paths.data_dir == data_home / "midgard"
    assert paths.models_dir == data_home / "midgard" / "models"
    assert paths.updates_dir == data_home / "midgard" / "updates"
    assert bundle not in paths.config_file.parents
    assert bundle not in paths.models_dir.parents
