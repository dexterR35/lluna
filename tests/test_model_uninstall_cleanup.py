from __future__ import annotations

from backend.tools import (
    enhance_models,
    hf_auth,
    low_light_models,
    select_object_models,
)
from backend.tools.constant import EnhanceMode, LowLightMode, SelectObjectModelId


def _make_repo_cache(root, repo_id: str):
    folder = "models--" + repo_id.replace("/", "--")
    repo = root / folder
    (repo / "blobs").mkdir(parents=True)
    (repo / "blobs" / "weights").write_bytes(b"cached weights")
    lock = root / ".locks" / folder
    lock.mkdir(parents=True)
    (lock / "download.lock").touch()
    return repo, lock


def test_hf_cache_cleanup_removes_private_and_legacy_copies_only(tmp_path, monkeypatch) -> None:
    models = tmp_path / "models"
    shared = tmp_path / "shared-hf"
    monkeypatch.setenv("MIDGARD_MODELS_DIR", str(models))
    monkeypatch.setenv("HF_HOME", str(shared))
    monkeypatch.delenv("HF_HUB_CACHE", raising=False)
    monkeypatch.delenv("HUGGINGFACE_HUB_CACHE", raising=False)

    repo_id = "facebook/sam2-hiera-tiny"
    private_repo, private_lock = _make_repo_cache(hf_auth.hf_download_cache_dir(), repo_id)
    shared_repo, shared_lock = _make_repo_cache(shared / "hub", repo_id)
    unrelated, _ = _make_repo_cache(shared / "hub", "someone/other-model")

    hf_auth.remove_hf_repo_cache(repo_id)

    assert not private_repo.exists()
    assert not private_lock.exists()
    assert not shared_repo.exists()
    assert not shared_lock.exists()
    assert unrelated.is_dir()


def test_snapshot_download_uses_disposable_app_cache(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MIDGARD_MODELS_DIR", str(tmp_path / "models"))
    monkeypatch.setattr(hf_auth, "apply_hf_token_to_env", lambda: None)

    kwargs = hf_auth.snapshot_download_kwargs()

    assert kwargs == {
        "cache_dir": str(tmp_path / "models" / ".download_cache" / "huggingface" / "hub")
    }


def test_select_object_uninstall_removes_model_and_legacy_cache(tmp_path, monkeypatch) -> None:
    model_root = tmp_path / "models"
    shared = tmp_path / "shared-hf"
    monkeypatch.setattr(select_object_models, "models_root", lambda: model_root)
    monkeypatch.setenv("MIDGARD_MODELS_DIR", str(tmp_path / "app-models"))
    monkeypatch.setenv("HF_HOME", str(shared))
    monkeypatch.delenv("HF_HUB_CACHE", raising=False)
    monkeypatch.delenv("HUGGINGFACE_HUB_CACHE", raising=False)

    model_id = SelectObjectModelId.SAM2_TINY
    model = select_object_models.model_dir(model_id)
    model.mkdir(parents=True)
    (model / "model.safetensors").write_bytes(b"runtime weights")
    info = select_object_models.catalog_info(model_id)
    assert info is not None
    legacy_repo, _ = _make_repo_cache(shared / "hub", info.hf_repo)

    select_object_models.uninstall_model(model_id)

    assert not model.exists()
    assert not legacy_repo.exists()


def test_missing_default_models_are_not_selectable(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        enhance_models,
        "get_enabled_values",
        lambda: {EnhanceMode.X2PLUS.value},
    )
    monkeypatch.setattr(enhance_models, "is_model_installed", lambda _mode: False)
    monkeypatch.setattr(
        low_light_models,
        "get_enabled_values",
        lambda: {LowLightMode.MIRNET_LOL.value},
    )
    monkeypatch.setattr(low_light_models, "is_model_installed", lambda _mode: False)

    assert enhance_models.selectable_modes() == []
    assert low_light_models.selectable_modes() == []
