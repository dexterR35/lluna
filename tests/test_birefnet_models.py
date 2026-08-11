from __future__ import annotations

import json

import pytest

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
    monkeypatch.setattr(birefnet_models, "_torch_index_url", lambda: "")

    assert not birefnet_models.is_model_installed("birefnet")

    model_path = birefnet_models.model_dir("birefnet")
    model_path.mkdir(parents=True)
    (model_path / "config.json").write_text("{}", encoding="utf-8")
    (model_path / "model.safetensors").write_bytes(b"weights")

    # Snapshot alone (no isolated runtime yet) must not count as installed -
    # trust_remote_code code must never run outside the isolated venv.
    assert not birefnet_models.is_model_installed("birefnet")

    runtime.mkdir(parents=True)
    runtime_executable = birefnet_models.runtime_python()
    runtime_executable.parent.mkdir(parents=True)
    runtime_executable.write_bytes(b"python")
    (runtime / "runtime.json").write_text('{"torchIndex": ""}', encoding="utf-8")

    assert birefnet_models.is_model_installed("birefnet")


def test_birefnet_cuda_runtime_uses_official_torch_index(monkeypatch) -> None:
    index = "https://download.pytorch.org/whl/cu118"
    monkeypatch.setattr(birefnet_models, "_torch_index_url", lambda: index)
    steps = birefnet_models._pip_install_steps()
    assert steps[0] == [
        "torch==2.5.1",
        "torchvision==0.20.1",
        "--index-url",
        index,
    ]
    assert not any(package.startswith("torch") for package in steps[1])


def test_birefnet_runtime_python_can_reference_application_environment(
    tmp_path, monkeypatch
) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    application_python = tmp_path / "trusted-python.exe"
    application_python.write_bytes(b"python")
    (runtime / "runtime.json").write_text(
        json.dumps(
            {
                "runtimeMode": "application-environment",
                "pythonExecutable": str(application_python),
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(birefnet_models, "runtime_dir", lambda: runtime)

    assert birefnet_models.runtime_python() == application_python
    assert birefnet_models._runtime_ready()


def test_birefnet_install_uses_trusted_application_environment(
    tmp_path, monkeypatch
) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / "blocked-runtime.dll").write_bytes(b"blocked")
    application_python = tmp_path / "trusted-python.exe"
    application_python.write_bytes(b"python")
    monkeypatch.setattr(birefnet_models, "runtime_dir", lambda: runtime)
    monkeypatch.setattr(
        birefnet_models,
        "_application_runtime_python",
        lambda: application_python,
    )
    monkeypatch.setattr(
        birefnet_models,
        "create_isolated_venv",
        lambda **_kwargs: pytest.fail("isolated runtime should not be created"),
    )

    birefnet_models._install_runtime()

    metadata = json.loads((runtime / "runtime.json").read_text(encoding="utf-8"))
    assert metadata["runtimeMode"] == "application-environment"
    assert metadata["pythonExecutable"] == str(application_python)
    assert not (runtime / "blocked-runtime.dll").exists()


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
