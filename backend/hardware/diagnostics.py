"""Human-readable hardware diagnostics."""

from __future__ import annotations

from backend.hardware.policy import select_execution_policy
from backend.hardware.profile import HardwareProfile


def render_hardware_report(profile: HardwareProfile) -> str:
    gpu = profile.primary_gpu
    policy = select_execution_policy(profile)
    lines = [
        f"OS: {profile.os_name} {profile.os_version}",
        f"Architecture: {profile.architecture} ({profile.python_architecture} Python)",
        f"CPU: {profile.cpu_vendor} {profile.cpu_model}".strip(),
        f"CPU cores/threads: {profile.physical_cores}/{profile.logical_threads}",
        (
            f"RAM: {profile.memory.available_mb:.0f} MB available / "
            f"{profile.memory.total_mb:.0f} MB total"
        ),
        f"GPU: {gpu.vendor} {gpu.model}".strip() if gpu else "GPU: not detected",
        f"Recommended backend: {policy.backend}",
        f"ONNX providers: {', '.join(profile.capabilities.onnx_providers) or 'none'}",
        f"FFmpeg: {'available' if profile.ffmpeg_available else 'missing'}",
        f"Disk available: {profile.available_disk_mb:.0f} MB",
    ]
    lines.extend(f"Warning: {warning}" for warning in profile.warnings)
    return "\n".join(lines)
