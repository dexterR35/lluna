from __future__ import annotations

from backend.tools.installers import enhance as enhance_models
from backend.tools.installers import low_light as low_light_models
from backend.tools.installers import sam3 as sam3_models
from backend.tools.shared import huggingface as hf_auth
from backend.tools.shared.constants import EnhanceMode, LowLightMode


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
    monkeypatch.setenv("LLUNA_MODELS_DIR", str(models))
    monkeypatch.setenv("HF_HOME", str(shared))
    monkeypatch.delenv("HF_HUB_CACHE", raising=False)
    monkeypatch.delenv("HUGGINGFACE_HUB_CACHE", raising=False)

    repo_id = "facebook/sam3.1"
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
    monkeypatch.setenv("LLUNA_MODELS_DIR", str(tmp_path / "models"))
    monkeypatch.setattr(hf_auth, "apply_hf_token_to_env", lambda: None)

    kwargs = hf_auth.snapshot_download_kwargs()

    assert kwargs == {
        "cache_dir": str(tmp_path / "models" / ".download_cache" / "huggingface" / "hub")
    }


def test_sam3_uninstall_removes_checkpoint_and_runtime(tmp_path, monkeypatch) -> None:
    # PATHS (backend/core/paths.py) is resolved once at import time, before
    # pytest's env-var fixtures run - LLUNA_MODELS_DIR/LLUNA_DATA_DIR
    # monkeypatches arrive too late to affect it. Point sam3_root/runtime_dir
    # at tmp_path directly instead, so this test can't touch the real
    # backend/models/sam3 directory on disk.
    model_root = tmp_path / "models" / "sam3"
    runtime_root = tmp_path / "data" / "model-runtimes" / "sam3-python"
    monkeypatch.setattr(sam3_models, "sam3_root", lambda: model_root)
    monkeypatch.setattr(sam3_models, "runtime_dir", lambda: runtime_root)

    checkpoint = sam3_models.checkpoint_dir()
    checkpoint.mkdir(parents=True)
    (checkpoint / "sam3.1.pt").write_bytes(b"runtime weights")
    runtime = sam3_models.runtime_dir()
    runtime.mkdir(parents=True)
    (runtime / "runtime.json").write_text("{}", encoding="utf-8")

    sam3_models.uninstall_model()

    assert not sam3_models.sam3_root().exists()
    assert not runtime.exists()


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
