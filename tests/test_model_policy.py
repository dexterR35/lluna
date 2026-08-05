from backend.models.policy import evaluate_model_compatibility, video_frame_policy
from backend.models.reference.catalog import MODEL_REGISTRY
from tests.fakes.hardware import CPU_ONLY, CUDA, DIRECTML, profile


def test_low_memory_clamps_unsafe_video_frames() -> None:
    low = profile(cuda=True, vram_mb=4096, ram_mb=8192)
    value = video_frame_policy(low, configured=70, width=1920, height=1080, propainter=True)
    assert value.effective < value.configured
    assert value.reason


def test_high_memory_preserves_safe_override() -> None:
    value = video_frame_policy(CUDA, configured=16, width=1280, height=720, propainter=False)
    assert value.effective == 16


def test_model_compatibility_explains_backend_mismatch() -> None:
    decision = evaluate_model_compatibility(
        MODEL_REGISTRY["flux"],
        CPU_ONLY,
        installed=True,
    )
    assert not decision.compatible
    assert decision.backend == "cpu"
    assert any("does not support" in reason for reason in decision.reasons)


def test_model_compatibility_reports_missing_install() -> None:
    decision = evaluate_model_compatibility(
        MODEL_REGISTRY["sttn-auto"],
        CUDA,
        installed=False,
    )
    assert not decision.compatible
    assert "not installed" in decision.reasons[0]


def test_directml_without_vram_measurement_uses_low_memory_policy() -> None:
    value = video_frame_policy(
        DIRECTML,
        configured=70,
        width=1920,
        height=1080,
        propainter=True,
    )
    assert value.effective < 70
