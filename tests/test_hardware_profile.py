from __future__ import annotations

from backend.hardware.detector import HardwareDetector
from backend.hardware.diagnostics import render_hardware_report
from backend.hardware.policy import select_execution_policy
from tests.fakes.hardware import CPU_ONLY, CUDA, DIRECTML, MPS


def test_execution_fallback_order() -> None:
    assert select_execution_policy(DIRECTML).backend == "directml"
    assert select_execution_policy(CUDA).backend == "cuda"
    assert select_execution_policy(MPS).backend == "mps"
    assert select_execution_policy(CPU_ONLY).backend == "cpu"


def test_acceleration_can_be_disabled() -> None:
    policy = select_execution_policy(CUDA, acceleration_enabled=False)
    assert policy.backend == "cpu"
    assert "disabled" in policy.reasons[0].lower()


def test_profile_is_immutable() -> None:
    try:
        CPU_ONLY.os_name = "changed"
    except AttributeError:
        pass
    else:
        raise AssertionError("HardwareProfile must be immutable")


def test_detector_caches_and_invalidates(monkeypatch) -> None:
    detector = HardwareDetector()
    first = detector.detect()
    assert detector.detect() is first
    detector.invalidate()
    assert detector.detect() is not first


def test_human_report_contains_fallback() -> None:
    report = render_hardware_report(CPU_ONLY)
    assert "Recommended backend: cpu" in report
    assert "FFmpeg: available" in report
