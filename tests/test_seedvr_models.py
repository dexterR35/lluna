from __future__ import annotations

from backend.graph.registry import list_nodes
from backend.models.reference.catalog import MODEL_REGISTRY
from backend.tools.installers import seedvr2 as seedvr_models


def test_seedvr_variants_are_catalogued_as_cuda_upscalers() -> None:
    assert MODEL_REGISTRY["seedvr2-3b"].source == "ByteDance-Seed/SeedVR2-3B"
    assert MODEL_REGISTRY["seedvr2-7b"].source == "ByteDance-Seed/SeedVR2-7B"
    assert MODEL_REGISTRY["seedvr2-3b"].compatible_backends == ("cuda",)
    assert seedvr_models.MODEL_CONFIG["seedvr2-3b"]["checkpoint"] == "seedvr2_ema_3b.pth"
    assert seedvr_models.MODEL_CONFIG["seedvr2-7b"]["checkpoint"] == "seedvr2_ema_7b.pth"
    assert not hasattr(seedvr_models, "SEEDVR_SOURCE_URL")
    assert (seedvr_models.source_dir() / "projects" / "inference_seedvr2_3b.py").is_file()


def test_seedvr_readiness_requires_source_runtime_and_assets(tmp_path, monkeypatch) -> None:
    root = tmp_path / "seedvr2"
    source = root / "source"
    checkpoints = root / "ckpts"
    runtime = tmp_path / "runtime"
    monkeypatch.setattr(seedvr_models, "models_root", lambda: root)
    monkeypatch.setattr(seedvr_models, "source_dir", lambda: source)
    monkeypatch.setattr(seedvr_models, "checkpoints_dir", lambda: checkpoints)
    monkeypatch.setattr(seedvr_models, "runtime_dir", lambda: runtime)
    monkeypatch.setattr(seedvr_models, "runtime_python", lambda: runtime / "bin" / "python")

    assert not seedvr_models.is_model_installed("seedvr2-3b")
    for relative in (
        "projects/inference_seedvr2_3b.py",
        "projects/inference_seedvr2_7b.py",
        "configs_3b/main.yaml",
        "configs_7b/main.yaml",
        "pos_emb.pt",
        "neg_emb.pt",
    ):
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"asset")
    (checkpoints / "seedvr2_ema_3b.pth").parent.mkdir(parents=True, exist_ok=True)
    (checkpoints / "seedvr2_ema_3b.pth").write_bytes(b"weights")
    (checkpoints / "ema_vae.pth").write_bytes(b"vae")
    (runtime / "bin").mkdir(parents=True)
    (runtime / "bin" / "python").write_bytes(b"python")
    (runtime / "runtime.json").write_text("{}", encoding="utf-8")
    marker = root / "seedvr2-3b" / ".lluna-installed"
    marker.parent.mkdir(parents=True)
    marker.write_text("{}", encoding="utf-8")

    assert seedvr_models.is_model_installed("seedvr2-3b")


def test_seedvr_is_available_in_image_and_video_upscale_nodes() -> None:
    catalog = {item.schema_id: item for item in list_nodes()}
    image_model = next(
        parameter for parameter in catalog["lluna.image.upscale"].parameters if parameter.id == "model"
    )
    video_model = next(
        parameter for parameter in catalog["lluna.video.upscale"].parameters if parameter.id == "model"
    )
    assert {item["modelId"] for item in image_model.options} >= {"seedvr2-3b", "seedvr2-7b"}
    assert {item["modelId"] for item in video_model.options} == {"seedvr2-3b", "seedvr2-7b"}
