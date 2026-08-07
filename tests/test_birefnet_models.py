from __future__ import annotations

from backend.tools.installers import birefnet as birefnet_models


def test_birefnet_repos_pin_a_reviewed_revision_for_every_model() -> None:
    assert set(birefnet_models.MODEL_REVISIONS) == set(birefnet_models.MODEL_REPOS)
    for revision in birefnet_models.MODEL_REVISIONS.values():
        assert len(revision) == 40
        assert all(char in "0123456789abcdef" for char in revision)


def test_birefnet_is_model_installed_requires_snapshot_and_runtime(tmp_path, monkeypatch) -> None:
    snapshot_root = tmp_path / "models"
    runtime = tmp_path / "runtime"
    monkeypatch.setattr(birefnet_models, "models_root", lambda: snapshot_root)
    monkeypatch.setattr(birefnet_models, "runtime_dir", lambda: runtime)

    assert not birefnet_models.is_model_installed("birefnet")

    model_path = birefnet_models.model_dir("birefnet")
    model_path.mkdir(parents=True)
    (model_path / "config.json").write_text("{}", encoding="utf-8")
    (model_path / "model.safetensors").write_bytes(b"weights")

    # Snapshot alone (no isolated runtime yet) must not count as installed -
    # trust_remote_code code must never run outside the isolated venv.
    assert not birefnet_models.is_model_installed("birefnet")

    runtime.mkdir(parents=True)
    (runtime / "bin").mkdir()
    (runtime / "bin" / "python").write_bytes(b"python")
    (runtime / "runtime.json").write_text("{}", encoding="utf-8")

    assert birefnet_models.is_model_installed("birefnet")


def test_birefnet_uninstall_keeps_shared_runtime_until_last_model_removed(
    tmp_path, monkeypatch
) -> None:
    snapshot_root = tmp_path / "models"
    runtime = tmp_path / "runtime"
    monkeypatch.setattr(birefnet_models, "models_root", lambda: snapshot_root)
    monkeypatch.setattr(birefnet_models, "runtime_dir", lambda: runtime)

    for model_id in ("birefnet", "birefnet-hr"):
        path = birefnet_models.model_dir(model_id)
        path.mkdir(parents=True)
        (path / "config.json").write_text("{}", encoding="utf-8")
        (path / "model.safetensors").write_bytes(b"weights")
    runtime.mkdir(parents=True)

    birefnet_models.uninstall_model("birefnet")
    assert not birefnet_models.is_model_installed_at(birefnet_models.model_dir("birefnet"))
    assert runtime.is_dir()

    birefnet_models.uninstall_model("birefnet-hr")
    assert not runtime.is_dir()
