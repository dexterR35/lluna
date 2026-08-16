from __future__ import annotations

import hashlib
import json

from backend.models import service as model_service
from backend.models.reference.catalog import MODEL_REGISTRY
from backend.models.reference.metadata import ExpectedFile, ModelState
from backend.models.verifier import verify_file


def test_required_model_inventory_is_unique() -> None:
    required = {
        "sttn-auto",
        "sttn-detection",
        "lama",
        "propainter",
        "paddleocr-server",
        "paddleocr-mobile",
        "realesrgan-x2",
        "realesrgan-x4",
        "supir",
        "mirnet",
        "sam3.1",
        "flux",
        "flux2-dev",
        "flux2-klein-9b-fp8",
        "qwen-image",
        "qwen3-tts-customvoice",
        "birefnet",
        "birefnet-dynamic",
        "birefnet-hr",
        "birefnet-hr-matting",
        "birefnet-lite-2k",
        "birefnet-matting",
        "seedvr2-3b",
        "seedvr2-7b",
    }
    assert required == set(MODEL_REGISTRY)
    assert all(model.source and model.license for model in MODEL_REGISTRY.values())


def test_all_lifecycle_states_exist() -> None:
    assert len(ModelState) == 11
    assert ModelState.BROKEN.value == "broken"


def test_verifier_checks_hash_and_rejects_traversal(tmp_path) -> None:
    content = b"model"
    (tmp_path / "weight.bin").write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    assert verify_file(tmp_path, ExpectedFile("weight.bin", len(content), digest)).valid
    assert not verify_file(tmp_path, ExpectedFile("../outside.bin")).valid


def test_sam3_enables_and_disables(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLUNA_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(model_service, "_installed", lambda _model_id: True)

    model_service._action("sam3.1", "enable")
    state = json.loads((tmp_path / "model-lifecycle.json").read_text())
    assert state["sam3.1"] is True

    model_service._action("sam3.1", "disable")
    state = json.loads((tmp_path / "model-lifecycle.json").read_text())
    assert state["sam3.1"] is False
