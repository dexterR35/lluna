from __future__ import annotations

import hashlib

from backend.models.metadata import ExpectedFile, ModelState
from backend.models.registry import MODEL_REGISTRY
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
        "sam2",
        "grounding-dino",
        "flux",
        "flux2-dev",
        "flux2-klein-9b-fp8",
        "qwen-image",
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
