"""First-launch validation for frozen desktop installations."""

from __future__ import annotations

import os
import platform
import struct
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from backend.core.build_info import VERSION
from backend.core.paths import AppPaths
from backend.core.release_target import ReleaseTarget, current_release_target
from backend.diagnostics.errors import DependencyError


@dataclass(frozen=True)
class PreflightReport:
    log_file: Path
    target: ReleaseTarget
    checks: tuple[str, ...]


def validate_python_runtime() -> None:
    """Require the single Python runtime supported by Midgard."""
    bits = struct.calcsize("P") * 8
    if sys.version_info[:2] != (3, 12) or bits != 64:
        raise DependencyError(
            "Midgard requires 64-bit Python 3.12; received "
            f"{sys.version_info[0]}.{sys.version_info[1]} {bits}-bit."
        )


def _ffmpeg_path(root: Path, target_platform: str) -> Path:
    if target_platform == "windows":
        return root / "backend" / "ffmpeg" / "win_x64" / "ffmpeg.exe"
    if target_platform == "macos":
        return root / "backend" / "ffmpeg" / "macos" / "ffmpeg"
    return root / "backend" / "ffmpeg" / "linux_x64" / "ffmpeg"


def _probe_writable(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".midgard-write-", dir=directory)
    try:
        os.close(descriptor)
    finally:
        Path(name).unlink(missing_ok=True)


def validate_packaged_runtime(
    paths: AppPaths,
    *,
    target: ReleaseTarget | None = None,
) -> PreflightReport | None:
    """Validate the embedded Python/resources and writable per-user state."""
    if not getattr(sys, "frozen", False):
        return None
    selected = target or current_release_target()
    checks: list[str] = []
    errors: list[str] = []
    try:
        validate_python_runtime()
    except DependencyError as exc:
        errors.append(str(exc).replace("Midgard requires", "embedded Python must be"))
    else:
        checks.append("embedded Python 3.12 64-bit")
    if selected.profile == "source":
        errors.append("packaged release metadata is missing")
    else:
        checks.append(f"release target {selected.key}")

    required = (
        paths.translation_file,
        _ffmpeg_path(paths.project_root, selected.platform),
        paths.project_root / "backend/models/V5/ch_det/inference.pdiparams",
        paths.project_root / "backend/models/V5/ch_det_fast/inference.pdiparams",
        paths.project_root / "backend/models/sttn-auto/infer_model.pth",
        paths.project_root / "backend/models/sttn-det/sttn.pth",
        paths.project_root / "backend/models/big-lama/fs_manifest.csv",
        paths.project_root / "backend/models/propainter/fs_manifest.csv",
    )
    missing = [path for path in required if not path.is_file()]
    if missing:
        errors.append("missing packaged resources: " + ", ".join(path.name for path in missing))
    else:
        checks.append(f"{len(required)} packaged resources")

    for label, directory in (
        ("configuration", paths.config_dir),
        ("application data", paths.data_dir),
        ("models", paths.models_dir),
        ("updates", paths.updates_dir),
    ):
        try:
            _probe_writable(directory)
            checks.append(f"writable {label}")
        except OSError as exc:
            errors.append(f"{label} directory is not writable: {type(exc).__name__}")

    log_file = paths.config_dir / "logs" / "install.log"
    lines = [
        f"[{datetime.now(timezone.utc).isoformat()}] Midgard {VERSION}",
        f"platform={platform.platform()}",
        f"target={selected.key}",
        f"python={sys.version.split()[0]} embedded=true",
        *(f"OK {check}" for check in checks),
        *(f"FAIL {error}" for error in errors),
        "",
    ]
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with log_file.open("a", encoding="utf-8") as stream:
            stream.write("\n".join(lines))
    except OSError:
        if not errors:
            errors.append("installation log directory is not writable")
    if errors:
        raise DependencyError("Packaged installation validation failed: " + "; ".join(errors))
    return PreflightReport(log_file, selected, tuple(checks))
