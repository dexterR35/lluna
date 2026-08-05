from __future__ import annotations

import hashlib

import pytest

from backend.models.artifacts import (
    ArtifactVerificationError,
    promote_verified_artifact,
)
from backend.models.metadata import ExpectedFile
from backend.models.registry import MODEL_REGISTRY
from backend.tools import enhance_models
from backend.tools.constant import EnhanceMode
from backend.tools.enhance_models import catalog_info
from backend.tools.select_object_models import MODEL_CATALOG as SELECT_OBJECT_CATALOG


def test_verified_artifact_replaces_destination_only_after_validation(tmp_path) -> None:
    destination = tmp_path / "model.pth"
    destination.write_bytes(b"previous verified model")
    partial = tmp_path / "model.pth.part"
    content = b"new verified model"
    partial.write_bytes(content)
    expected = ExpectedFile(
        "model.pth",
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
    )

    result = promote_verified_artifact(partial, destination, expected)

    assert result.valid
    assert result.sha256 == expected.sha256
    assert destination.read_bytes() == content
    assert not partial.exists()


def test_hash_mismatch_preserves_existing_destination(tmp_path) -> None:
    destination = tmp_path / "model.pth"
    destination.write_bytes(b"previous verified model")
    partial = tmp_path / "model.pth.part"
    partial.write_bytes(b"tampered download")
    expected = ExpectedFile(
        "model.pth",
        size_bytes=17,
        sha256=hashlib.sha256(b"different content").hexdigest(),
    )

    with pytest.raises(ArtifactVerificationError, match="SHA-256"):
        promote_verified_artifact(partial, destination, expected)

    assert destination.read_bytes() == b"previous verified model"
    assert partial.read_bytes() == b"tampered download"


def test_promotion_fails_closed_without_complete_integrity_metadata(tmp_path) -> None:
    partial = tmp_path / "model.pth.part"
    partial.write_bytes(b"download")

    with pytest.raises(ArtifactVerificationError, match="size and SHA-256"):
        promote_verified_artifact(
            partial,
            tmp_path / "model.pth",
            ExpectedFile("model.pth"),
        )


def test_realesrgan_download_catalog_has_pinned_artifact_integrity() -> None:
    registry_ids = {
        EnhanceMode.X2PLUS: "realesrgan-x2",
        EnhanceMode.X4PLUS: "realesrgan-x4",
    }
    for mode, registry_id in registry_ids.items():
        info = catalog_info(mode)
        assert info is not None
        assert info.version.startswith("v")
        assert info.artifact.size_bytes
        assert info.artifact.sha256
        assert len(info.artifact.sha256) == 64
        registered = MODEL_REGISTRY[registry_id]
        assert registered.version == info.version
        assert registered.expected_files == (info.artifact,)


def test_select_object_downloads_only_transformers_safetensors_layout() -> None:
    for info in SELECT_OBJECT_CATALOG:
        assert "model.safetensors" in info.download_allow_patterns
        assert not any(
            pattern.endswith((".bin", ".pt")) for pattern in info.download_allow_patterns
        )


def test_realesrgan_installer_rejects_tampered_download(tmp_path, monkeypatch) -> None:
    class FakeRegistry:
        def begin(self, *_args) -> None:
            pass

        def check_cancelled(self) -> None:
            pass

        def fail(self, *_args, **_kwargs) -> None:
            pass

    destination = tmp_path / "RealESRGAN_x2plus.pth"
    destination.write_bytes(b"existing model remains available")

    def fake_download(_url, filename, reporthook=None) -> None:
        del reporthook
        with open(filename, "wb") as stream:
            stream.write(b"tampered")

    from backend.tools import model_download_registry

    monkeypatch.setattr(enhance_models, "models_dir", lambda: tmp_path)
    monkeypatch.setattr(enhance_models.urllib.request, "urlretrieve", fake_download)
    monkeypatch.setattr(
        model_download_registry.ModelDownloadRegistry,
        "instance",
        classmethod(lambda cls: FakeRegistry()),
    )

    with pytest.raises(ArtifactVerificationError, match="size"):
        enhance_models.install_model(EnhanceMode.X2PLUS)

    assert destination.read_bytes() == b"existing model remains available"
    assert not (tmp_path / "RealESRGAN_x2plus.pth.part").exists()


def test_existing_realesrgan_weight_is_verified_before_load(tmp_path, monkeypatch) -> None:
    content = b"locally installed weight"
    artifact = ExpectedFile(
        "RealESRGAN_x2plus.pth",
        len(content),
        hashlib.sha256(content).hexdigest(),
    )
    info = enhance_models.EnhanceModelInfo(
        EnhanceMode.X2PLUS,
        scale=2,
        download_url="https://example.invalid/model",
        version="test",
        artifact=artifact,
    )
    monkeypatch.setitem(enhance_models._CATALOG_BY_MODE, EnhanceMode.X2PLUS, info)
    monkeypatch.setattr(enhance_models, "models_dir", lambda: tmp_path)
    destination = tmp_path / artifact.relative_path
    destination.write_bytes(content)

    assert enhance_models.ensure_model_installed(EnhanceMode.X2PLUS) == destination

    destination.write_bytes(b"x" * len(content))
    with pytest.raises(ArtifactVerificationError, match="SHA-256"):
        enhance_models.ensure_model_installed(EnhanceMode.X2PLUS)
