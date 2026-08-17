"""Shared helpers for installers that need an isolated Python runtime and/or
pinned, hash-verified downloads (SUPIR, SeedVR2, BiRefNet).

Extracted from supir.py, which was the first installer to implement this
pattern; other installers should call into this module instead of
duplicating it.
"""

from __future__ import annotations

import importlib
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence

from backend.artifacts.hashing import hash_file
from backend.core.atomic import atomic_write_json


def _uv_executable() -> str | None:
    """Return a usable ``uv`` binary, preferring one already on PATH.

    Falls back to the ``uv`` PyPI package installed into this interpreter, which
    ships the binary and exposes its path via ``uv.find_uv_bin()``.
    """
    found = shutil.which("uv")
    if found:
        return found
    for attempt in range(2):
        try:
            import uv  # noqa: PLC0415 - optional, resolved lazily

            binary = str(uv.find_uv_bin())
            if Path(binary).is_file():
                return binary
        except (ImportError, AttributeError, FileNotFoundError):
            pass
        if attempt:
            break
        result = subprocess.run(  # noqa: S603 - fixed argv, current interpreter
            [sys.executable, "-m", "pip", "install", "--quiet", "uv"],
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
        if result.returncode != 0:
            return None
        importlib.invalidate_caches()
    return None


def provision_python(version: str) -> str | None:
    """Download a managed CPython ``version`` with uv and return its path.

    Returns ``None`` when uv is unavailable or the download fails; callers treat
    that as "no interpreter" rather than a hard error.
    """
    uv_bin = _uv_executable()
    if uv_bin is None:
        return None
    try:
        subprocess.run(  # noqa: S603 - resolved uv binary, fixed argv
            [uv_bin, "python", "install", version],
            capture_output=True,
            text=True,
            timeout=1800,
            check=True,
        )
        found = subprocess.run(  # noqa: S603 - resolved uv binary, fixed argv
            [uv_bin, "python", "find", version],
            capture_output=True,
            text=True,
            timeout=120,
            check=True,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return None
    candidate = found.stdout.strip()
    return candidate if candidate and Path(candidate).is_file() else None


def bootstrap_reviewed_python(
    *,
    env_var: str,
    versions: tuple[str, ...],
    error_message: str,
    provision: bool = False,
) -> str:
    """Locate a Python interpreter matching one of ``versions``.

    Checks (in order): the interpreter pinned by ``env_var``, bare
    ``pythonX.Y`` on PATH, and any matching interpreter managed by ``uv``
    (``~/.local/share/uv/python`` on POSIX, ``%LOCALAPPDATA%\\uv\\python`` on
    Windows). When none match and ``provision`` is set, the first of
    ``versions`` is downloaded with uv, so a machine that has never installed
    that Python version still gets a working runtime. Raises
    ``RuntimeError(error_message)`` if every route fails.

    ``provision`` defaults to off so that merely *asking* which interpreter would
    be used never downloads one; installers opt in when they are about to build a
    runtime.
    """
    configured = os.environ.get(env_var, "").strip()
    candidates: list[str | Path] = [configured] if configured else []
    # In development Lluna already runs under a reviewed Python environment.
    # Prefer its real interpreter before PATH shims: managed Windows devices can
    # block unsigned uv shims with WinError 4551 even though the underlying
    # signed/allowed CPython executable is usable.
    if not getattr(sys, "frozen", False):
        candidates.append(sys.executable)
    candidates.extend(f"python{version}" for version in versions)
    home = Path.home()
    if os.name == "nt":
        local = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        roaming = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
        for uv_python in (local / "uv" / "python", roaming / "uv" / "python"):
            for version in versions:
                candidates.extend(
                    sorted(
                        uv_python.glob(f"cpython-{version}*-*/python.exe"),
                        reverse=True,
                    )
                )
    else:
        local_bin = home / ".local" / "bin"
        uv_python = (
            Path(os.environ.get("XDG_DATA_HOME", home / ".local" / "share")) / "uv" / "python"
        )
        for version in versions:
            candidates.append(local_bin / f"python{version}")
            candidates.extend(
                sorted(
                    uv_python.glob(f"cpython-{version}*-*/bin/python{version}"),
                    reverse=True,
                )
            )
    checked: set[str] = set()
    for candidate in candidates:
        candidate_path = Path(candidate).expanduser()
        executable = (
            str(candidate_path) if candidate_path.is_file() else shutil.which(str(candidate))
        )
        if not executable:
            continue
        executable = str(Path(executable).resolve())
        if executable in checked:
            continue
        checked.add(executable)
        try:
            result = subprocess.run(  # noqa: S603 - configured/detected Python executable
                [
                    executable,
                    "-c",
                    "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')",
                ],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            # Application Control commonly blocks an unsigned PATH shim while
            # allowing the actual interpreter found later in the candidate list.
            continue
        if result.returncode == 0 and result.stdout.strip() in versions:
            return executable
    if provision and versions:
        provisioned = provision_python(versions[0])
        if provisioned:
            return provisioned
    raise RuntimeError(error_message)


def create_isolated_venv(
    *,
    python_executable: str,
    target_dir: Path,
    staging_name: str,
    pip_install_steps: Sequence[Sequence[str]],
    runtime_metadata: dict,
    venv_timeout: int = 300,
    pip_timeout: int = 3600,
) -> Path:
    """Create an isolated venv in a staging dir, run each pip install step in
    order, write ``runtime.json``, then atomically replace ``target_dir``.

    Each entry in ``pip_install_steps`` is appended after
    ``python -m pip install --disable-pip-version-check`` (e.g. a package
    pin list, or ``["torch==...", "--index-url", "..."]``).
    """
    staging = target_dir.with_name(staging_name)
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    staging.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(  # noqa: S603 - reviewed Python executable and managed venv path
        [python_executable, "-m", "venv", str(staging)], check=True, timeout=venv_timeout
    )
    runtime_python = staging / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    # The venv's bundled pip (whatever version shipped with the source Python) can be
    # old enough to mis-normalize package names on some indexes -- e.g. pip 23.0.1
    # discards PyTorch's cu121 index wheels over a "Jinja2" vs "jinja2" / "typing_extensions"
    # vs "typing-extensions" casing mismatch and falls back to building from an sdist,
    # which then fails because build backends like flit_core aren't hosted on a
    # CUDA-only --index-url. Upgrading pip first avoids that class of failure.
    subprocess.run(  # noqa: S603 - managed venv, fixed pip upgrade command
        [str(runtime_python), "-m", "pip", "install", "--disable-pip-version-check", "--upgrade", "pip"],
        check=True,
        timeout=pip_timeout,
    )
    for step in pip_install_steps:
        subprocess.run(  # noqa: S603 - managed venv and policy-controlled package pins
            [str(runtime_python), "-m", "pip", "install", "--disable-pip-version-check", *step],
            check=True,
            timeout=pip_timeout,
        )
    atomic_write_json(staging / "runtime.json", runtime_metadata)
    if target_dir.exists():
        shutil.rmtree(target_dir, ignore_errors=True)
    staging.replace(target_dir)
    return target_dir


def sha256_of_file(path: Path, *, chunk_size: int = 8 * 1024 * 1024) -> str:
    return hash_file(path, chunk_size=chunk_size)


def verify_pinned_artifact(
    path: Path, *, expected_size: int | None, expected_sha256: str
) -> None:
    """Raise ``ValueError`` unless ``path`` matches the expected size/hash."""
    actual_size = path.stat().st_size
    if expected_size is not None and actual_size != expected_size:
        raise ValueError(
            f"{path.name} has an unexpected size ({actual_size} bytes); "
            f"expected {expected_size}."
        )
    actual_digest = sha256_of_file(path)
    if actual_digest.lower() != expected_sha256.lower():
        raise ValueError(f"{path.name} failed SHA-256 verification and was not installed.")


def safe_extract_zip(archive: Path, destination: Path) -> None:
    """Extract a zip archive, rejecting members that would escape ``destination``."""
    import zipfile

    with zipfile.ZipFile(archive) as opened:
        root = destination.resolve()
        for item in opened.infolist():
            target = (destination / item.filename).resolve()
            if root != target and root not in target.parents:
                raise RuntimeError("The archive contains an unsafe path.")
        opened.extractall(destination)
