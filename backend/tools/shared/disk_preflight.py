"""Disk-space preflight checks before starting a multi-GB model download.

Without this, an install could run for minutes (or hours) and only fail with
a raw ``OSError: no space left on device`` mid-transfer, or worse, silently
succeed with a truncated file. Checked once up front, with a margin for the
Hub's small per-download metadata overhead.
"""

from __future__ import annotations


def ensure_disk_space(bytes_needed: int, *, context: str, margin_ratio: float = 1.1) -> None:
    """Raise a clear error if the destination disk can't fit ``bytes_needed``.

    ``margin_ratio`` pads the requirement slightly for the small amount of
    per-download bookkeeping (Hub metadata, staging renames) that isn't
    counted in ``bytes_needed`` itself.
    """
    if bytes_needed <= 0:
        return
    from backend.hardware.detector import get_hardware_profile

    profile = get_hardware_profile(refresh=True)
    required_mb = bytes_needed * margin_ratio / (1024 * 1024)
    if profile.available_disk_mb < required_mb:
        raise RuntimeError(
            f"Not enough disk space to install {context}: "
            f"{required_mb:.0f} MB required, {profile.available_disk_mb:.0f} MB available."
        )
