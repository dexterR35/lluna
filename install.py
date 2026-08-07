#!/usr/bin/env python3
"""
Lluna installer - detects CUDA vs CPU, lets you choose, then installs deps + verifies models.

GPU mode needs NVIDIA drivers (nvidia-smi). You do NOT need the NVIDIA CUDA Toolkit (full SDK) —
install.py pulls GPU PyTorch/Paddle wheels that bundle the CUDA runtime libs.

Usage:
  python install.py
  python install.py --mode cpu
  python install.py --mode cuda --yes
  python install.py --mode directml --yes
  python install.py --mode mps --yes
"""

from __future__ import annotations

import argparse
import json
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent
VENV_NAME = "llunaEnv"
RUNTIME_FILE = ROOT / "lluna_runtime.json"
SUPPORTED_PYTHON = (3, 12)

TORCH_VERSION = "2.7.0"
TORCHVISION_VERSION = "0.22.0"
PADDLE_VERSION = "3.0.0"

PADDLE_CPU_INDEX = "https://www.paddlepaddle.org.cn/packages/stable/cpu/"
PADDLE_CU118_INDEX = "https://www.paddlepaddle.org.cn/packages/stable/cu118/"
TORCH_INDEX = {
    "cpu": "https://download.pytorch.org/whl/cpu",
    "cu118": "https://download.pytorch.org/whl/cu118",
    "cu126": "https://download.pytorch.org/whl/cu126",
    "cu128": "https://download.pytorch.org/whl/cu128",
}
# PyTorch CUDA wheel tags Lluna ships (see TORCH_INDEX). Highest first.
TORCH_CUDA_TAGS = ("cu128", "cu126", "cu118")
_TAG_RANK = {t: i for i, t in enumerate(reversed(TORCH_CUDA_TAGS))}

# Shown when GPU / CUDA mode is selected (no separate CUDA Toolkit install).
_NO_CUDA_TOOLKIT_NOTE = (
    "No NVIDIA CUDA Toolkit (SDK) required — only current GPU drivers. "
    "CUDA libraries come from the PyTorch/Paddle pip wheels."
)


class CudaInfo:
    def __init__(
        self,
        available: bool,
        gpu_name: str = "",
        driver_cuda: str = "",
        torch_tag: str = "",
        message: str = "",
        compute_cap: str = "",
        total_vram_mb: float = 0.0,
        tag_reason: str = "",
        warning: str = "",
    ):
        self.available = available
        self.gpu_name = gpu_name
        self.driver_cuda = driver_cuda
        self.torch_tag = torch_tag
        self.message = message
        self.compute_cap = compute_cap
        self.total_vram_mb = total_vram_mb
        self.tag_reason = tag_reason
        self.warning = warning


def log(msg: str = "") -> None:
    print(msg, flush=True)


def run(cmd: list[str], env: Optional[dict] = None) -> None:
    log(f"\n> {' '.join(cmd)}")
    subprocess.check_call(cmd, cwd=str(ROOT), env=env)


def find_python() -> str:
    """Find the canonical supported Python 3.12 interpreter."""
    candidates = [
        "python3.12",
        "py",
    ]
    for name in candidates:
        path = shutil.which(name)
        if not path:
            continue
        if name == "py" and platform.system() == "Windows":
            try:
                out = subprocess.check_output(
                    [path, "-3.12", "-c", "import sys; print(sys.executable)"],
                    text=True,
                    stderr=subprocess.DEVNULL,
                ).strip()
                if out:
                    return out
            except (subprocess.CalledProcessError, FileNotFoundError):
                pass
            continue
        try:
            out = subprocess.check_output(
                [
                    path,
                    "-c",
                    "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')",
                ],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
            major, minor = map(int, out.split("."))
            if (major, minor) == SUPPORTED_PYTHON:
                return path
        except (subprocess.CalledProcessError, FileNotFoundError, ValueError):
            continue

    vi = sys.version_info
    if (vi.major, vi.minor) == SUPPORTED_PYTHON:
        return sys.executable

    raise SystemExit(
        "Lluna requires 64-bit Python 3.12. Install Python 3.12 and rerun this installer."
    )


def python_version(python_bin: str | Path) -> tuple[int, int, int]:
    output = subprocess.check_output(
        [
            str(python_bin),
            "-c",
            "import struct,sys; print(sys.version_info.major, "
            "sys.version_info.minor, struct.calcsize('P') * 8)",
        ],
        text=True,
        stderr=subprocess.STDOUT,
        timeout=15,
    ).strip()
    major, minor, bits = (int(part) for part in output.split())
    return major, minor, bits


def validate_python(python_bin: str | Path) -> None:
    major, minor, bits = python_version(python_bin)
    if (major, minor) != SUPPORTED_PYTHON or bits != 64:
        raise SystemExit(
            f"Unsupported interpreter: Python {major}.{minor} {bits}-bit. "
            "Lluna requires 64-bit Python 3.12."
        )


def detect_cuda() -> CudaInfo:
    smi = shutil.which("nvidia-smi")
    if not smi:
        return CudaInfo(
            False,
            message="No NVIDIA driver tools found (nvidia-smi missing). Default: CPU.",
        )
    try:
        out = subprocess.check_output(
            [
                smi,
                "--query-gpu=name,driver_version,compute_cap",
                "--format=csv,noheader",
            ],
            text=True,
            stderr=subprocess.STDOUT,
            timeout=15,
        ).strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        return CudaInfo(False, message=f"nvidia-smi failed ({exc}). Default: CPU.")

    if not out:
        return CudaInfo(False, message="nvidia-smi returned no GPUs. Default: CPU.")

    first = out.splitlines()[0]
    parts = [p.strip() for p in first.split(",")]
    gpu_name = parts[0] if parts else "NVIDIA GPU"
    compute_cap = parts[2] if len(parts) >= 3 else ""
    total_vram_mb = 0.0
    try:
        mem_out = subprocess.check_output(
            [smi, "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            text=True,
            stderr=subprocess.STDOUT,
            timeout=15,
        ).strip()
        if mem_out:
            total_vram_mb = float(mem_out.splitlines()[0].strip())
    except Exception:
        pass

    driver_cuda = ""
    try:
        ver_out = subprocess.check_output(
            [smi],
            text=True,
            stderr=subprocess.STDOUT,
            timeout=15,
        )
        m = re.search(r"CUDA Version:\s*([\d.]+)", ver_out)
        if m:
            driver_cuda = m.group(1)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        pass

    torch_tag, tag_reason, warning = map_cuda_tag(
        driver_cuda, compute_cap=compute_cap, gpu_name=gpu_name
    )
    msg = f"Detected GPU: {gpu_name}"
    if driver_cuda:
        msg += f" (driver supports CUDA {driver_cuda} → torch {torch_tag})"
    else:
        msg += f" (driver CUDA level unknown → torch {torch_tag})"
    if compute_cap:
        msg += f" [cc {compute_cap}]"
    if total_vram_mb:
        msg += f" {total_vram_mb:.0f}MB"
    if tag_reason:
        msg += f"\n  → {tag_reason}"
    return CudaInfo(
        True,
        gpu_name=gpu_name,
        driver_cuda=driver_cuda,
        torch_tag=torch_tag,
        message=msg,
        compute_cap=compute_cap,
        total_vram_mb=total_vram_mb,
        tag_reason=tag_reason,
        warning=warning,
    )


def _parse_driver_cuda(driver_cuda: str) -> float:
    if not driver_cuda:
        return 0.0
    try:
        return float(".".join(driver_cuda.split(".")[:2]))
    except ValueError:
        return 0.0


def _parse_compute_cap(compute_cap: str) -> float:
    if not compute_cap:
        return 0.0
    try:
        return float(str(compute_cap).strip())
    except ValueError:
        return 0.0


def infer_compute_cap_from_name(gpu_name: str) -> float:
    """
    Best-effort compute capability from marketing name when nvidia-smi
    omits compute_cap. Examples: GTX 1080→6.1, RTX 3060→8.6, RTX 5090→12.0.
    """
    name = (gpu_name or "").lower().replace("-", " ")
    m = re.search(r"\brtx\s*(\d{4})\b", name)
    if m:
        n = int(m.group(1))
        if 5000 <= n < 6000:  # Blackwell (sm_120)
            return 12.0
        if 4000 <= n < 5000:  # Ada (sm_89)
            return 8.9
        if 3000 <= n < 4000:  # Ampere (sm_86)
            return 8.6
        if 2000 <= n < 3000:  # Turing (sm_75)
            return 7.5
    m = re.search(r"\bgtx\s*(\d{4})\b", name)
    if m:
        n = int(m.group(1))
        if 1600 <= n < 1700:  # Turing
            return 7.5
        if 1000 <= n < 1100:  # Pascal (1080, 1070, …)
            return 6.1
        if 900 <= n < 1000:  # Maxwell
            return 5.2
    if "blackwell" in name:
        return 12.0
    if "ada" in name:
        return 8.9
    if "ampere" in name:
        return 8.6
    if "turing" in name:
        return 7.5
    if "pascal" in name:
        return 6.1
    return 0.0


def driver_max_torch_tag(driver_cuda: str) -> str:
    """Highest PyTorch CUDA tag this NVIDIA driver can load."""
    ver = _parse_driver_cuda(driver_cuda)
    if ver >= 12.8:
        return "cu128"
    if ver >= 12.6:
        return "cu126"
    if ver >= 11.8:
        return "cu118"
    # Unknown / very old: still try cu118 (needs a current Game Ready / Studio driver)
    return "cu118"


def gpu_series_label(cap: float) -> str:
    """Human label for GeForce/RTX generations Lluna maps."""
    if cap >= 12.0:
        return "5xxx (Blackwell)"
    if cap >= 8.9:
        return "4xxx (Ada)"
    if cap >= 8.0:
        return "3xxx (Ampere)"
    if cap >= 7.5:
        return "2xxx (Turing)"
    if cap >= 6.0:
        return "1xxx (Pascal)"
    if cap > 0:
        return "pre-1xxx"
    return "unknown"


def preferred_torch_tag_for_series(cap: float) -> str:
    """
    Preferred Torch CUDA wheel per GPU series (before driver clamp):

      1xxx (GTX 1080, …)  → cu118
      2xxx (RTX 2080, …)  → cu118
      3xxx (RTX 3060, …)  → cu126
      4xxx (RTX 4090, …)  → cu128
      5xxx (RTX 5090, …)  → cu128  (required)
    """
    if cap >= 12.0:  # 5xxx
        return "cu128"
    if cap >= 8.9:  # 4xxx
        return "cu128"
    if cap >= 8.0:  # 3xxx
        return "cu126"
    if cap >= 7.5:  # 2xxx / GTX 16xx
        return "cu118"
    if cap > 0:  # 1xxx / older
        return "cu118"
    return ""  # unknown — fall back to driver max


def _clamp_tag_to_driver(preferred: str, driver_tag: str) -> str:
    """Never install a wheel newer than the driver can load."""
    if not preferred:
        return driver_tag
    if _TAG_RANK[preferred] <= _TAG_RANK[driver_tag]:
        return preferred
    return driver_tag


def map_cuda_tag(
    driver_cuda: str,
    compute_cap: str = "",
    gpu_name: str = "",
) -> tuple[str, str, str]:
    """
    Pick the PyTorch CUDA wheel for this GPU series + driver.

    Returns (tag, reason, warning).

      1xxx → cu118 (clamped to driver)
      2xxx → cu118 (clamped to driver)
      3xxx → cu126 (clamped to driver)
      4xxx → cu128 (clamped to driver)
      5xxx → cu128 required (sm_120); warns if driver < 12.8
    """
    driver_tag = driver_max_torch_tag(driver_cuda)
    cap = _parse_compute_cap(compute_cap)
    cap_source = "compute_cap"
    if cap <= 0:
        cap = infer_compute_cap_from_name(gpu_name)
        cap_source = "gpu name" if cap > 0 else ""

    warning = ""
    series = gpu_series_label(cap)
    preferred = preferred_torch_tag_for_series(cap)

    # 5xxx / Blackwell: cu128 is mandatory
    if cap >= 12.0:
        reason = f"{series} (cc {cap:g} via {cap_source or 'detect'}) → torch cu128 (required)"
        if _parse_driver_cuda(driver_cuda) < 12.8:
            warning = (
                "RTX 50-series needs an NVIDIA driver that reports CUDA 12.8+. "
                f"Driver currently reports CUDA {driver_cuda or 'unknown'}. "
                "Update the driver, then re-run install.py."
            )
        return "cu128", reason, warning

    if preferred:
        tag = _clamp_tag_to_driver(preferred, driver_tag)
        reason = (
            f"{series} (cc {cap:g} via {cap_source}) "
            f"→ torch {tag} (pref {preferred}, driver max {driver_tag})"
        )
        return tag, reason, warning

    # Unknown GPU: newest the driver supports
    reason = f"GPU series unknown → torch {driver_tag} (driver CUDA {driver_cuda or 'unknown'})"
    return driver_tag, reason, warning


def choose_mode_gui(default_cuda: bool, detect_msg: str) -> str:
    import tkinter as tk
    from tkinter import ttk

    result: dict[str, str] = {"mode": "cuda" if default_cuda else "cpu"}

    root = tk.Tk()
    root.title("Lluna Installer")
    root.resizable(False, False)
    root.attributes("-topmost", True)

    frame = ttk.Frame(root, padding=20)
    frame.grid()

    ttk.Label(frame, text="Lluna Installer", font=("Segoe UI", 14, "bold")).grid(
        row=0, column=0, columnspan=2, sticky="w", pady=(0, 8)
    )
    ttk.Label(frame, text=detect_msg, wraplength=420).grid(
        row=1, column=0, columnspan=2, sticky="w", pady=(0, 8)
    )
    ttk.Label(frame, text=_NO_CUDA_TOOLKIT_NOTE, wraplength=420).grid(
        row=2, column=0, columnspan=2, sticky="w", pady=(0, 16)
    )
    ttk.Label(frame, text="Choose acceleration:").grid(
        row=3, column=0, columnspan=2, sticky="w", pady=(0, 8)
    )

    def pick(mode: str) -> None:
        result["mode"] = mode
        root.destroy()

    cuda_btn = ttk.Button(frame, text="CUDA (NVIDIA GPU)", command=lambda: pick("cuda"))
    cpu_btn = ttk.Button(frame, text="CPU", command=lambda: pick("cpu"))
    cuda_btn.grid(row=4, column=0, padx=(0, 8), sticky="ew")
    cpu_btn.grid(row=4, column=1, sticky="ew")

    if default_cuda:
        cuda_btn.focus_set()
    else:
        cpu_btn.focus_set()

    root.update_idletasks()
    w, h = root.winfo_width(), root.winfo_height()
    x = (root.winfo_screenwidth() - w) // 2
    y = (root.winfo_screenheight() - h) // 3
    root.geometry(f"+{x}+{y}")
    root.mainloop()
    return result["mode"]


def choose_mode_cli(default_cuda: bool, detect_msg: str, allow_cuda: bool) -> str:
    log(detect_msg)
    log("")
    log(f"  {_NO_CUDA_TOOLKIT_NOTE}")
    log("")
    log("  1) CUDA (NVIDIA GPU)")
    log("  2) CPU")
    default = "1" if default_cuda else "2"
    prompt = f"Select [1/2] (default {default}): "
    while True:
        choice = input(prompt).strip() or default
        if choice in {"1", "cuda", "CUDA"}:
            return "cuda"
        if choice in {"2", "cpu", "CPU"}:
            return "cpu"
        log("Please enter 1 or 2.")


def choose_mode(
    cuda: CudaInfo,
    forced: Optional[str],
    yes: bool,
    cuda_tag_override: Optional[str] = None,
) -> tuple[str, str]:
    """Return (mode, torch_tag). mode is 'cuda' or 'cpu'."""
    default_cuda = cuda.available
    detect_msg = cuda.message
    if cuda.warning:
        detect_msg = f"{detect_msg}\n  WARNING: {cuda.warning}"

    def resolve_tag(mode: str) -> str:
        if mode != "cuda":
            return ""
        if cuda_tag_override:
            if cuda_tag_override not in TORCH_INDEX:
                raise SystemExit(
                    f"Unknown --cuda-tag {cuda_tag_override!r}. "
                    f"Use one of: {', '.join(TORCH_CUDA_TAGS)}"
                )
            log(f"Using forced CUDA tag: {cuda_tag_override}")
            return cuda_tag_override
        return cuda.torch_tag or "cu118"

    if forced in {"cuda", "cpu", "directml", "mps"}:
        mode = forced
        if mode == "cuda" and not cuda.available:
            log("CUDA was requested but not detected. Falling back to CPU.")
            return "cpu", ""
        if cuda.warning and mode == "cuda":
            log(f"WARNING: {cuda.warning}")
        return mode, resolve_tag(mode)

    if yes:
        mode = "cuda" if default_cuda else "cpu"
        log(detect_msg)
        if cuda.warning and mode == "cuda":
            log(f"WARNING: {cuda.warning}")
        log(
            f"Non-interactive: installing {mode.upper()}"
            + (f" ({resolve_tag(mode)})" if mode == "cuda" else "")
        )
        return mode, resolve_tag(mode)

    mode = None
    try:
        mode = choose_mode_gui(default_cuda, detect_msg)
    except Exception:
        mode = None

    if mode is None:
        mode = choose_mode_cli(default_cuda, detect_msg, allow_cuda=cuda.available)

    if mode == "cuda" and not cuda.available:
        log("CUDA selected but not available. Falling back to CPU.")
        return "cpu", ""

    if cuda.warning and mode == "cuda":
        log(f"WARNING: {cuda.warning}")
    return mode, resolve_tag(mode)


def venv_python(venv_dir: Path) -> Path:
    if platform.system() == "Windows":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def ensure_venv(python_bin: str) -> Path:
    venv_dir = ROOT / VENV_NAME
    py = venv_python(venv_dir)
    if py.exists():
        validate_python(py)
        log(f"Using existing venv: {venv_dir}")
        return venv_dir
    log(f"Creating venv with {python_bin} → {venv_dir}")
    try:
        run([python_bin, "-m", "venv", str(venv_dir)])
    except subprocess.CalledProcessError:
        log("venv with ensurepip failed; creating without pip and bootstrapping…")
        if venv_dir.exists():
            shutil.rmtree(venv_dir)
        run([python_bin, "-m", "venv", "--without-pip", str(venv_dir)])
        py = venv_python(venv_dir)
        get_pip = ROOT / ".cache_get_pip.py"
        get_pip.write_bytes(
            __import__("urllib.request")
            .request.urlopen("https://bootstrap.pypa.io/get-pip.py", timeout=120)
            .read()
        )
        run([str(py), str(get_pip)])
        get_pip.unlink(missing_ok=True)
    return venv_dir


def pip_install(py: Path, args: list[str]) -> None:
    run([str(py), "-m", "pip", "install", *args])


def pip_uninstall(py: Path, packages: list[str]) -> None:
    run([str(py), "-m", "pip", "uninstall", "--yes", *packages])


def installed_torch_backend(py: Path) -> tuple[str, str]:
    """Return (backend, CUDA tag) for the environment's current Torch build."""
    script = (
        "import importlib.util, torch; "
        "cuda = str(torch.version.cuda or ''); "
        "tag = ('cu' + cuda.replace('.', '')) if cuda else ''; "
        "dml = importlib.util.find_spec('torch_directml') is not None; "
        "print(('directml' if dml else ('cuda' if cuda else 'cpu')) + '|' + tag)"
    )
    try:
        output = subprocess.check_output(
            [str(py), "-c", script],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=30,
        ).strip()
        backend, _, tag = output.partition("|")
        return backend, tag
    except (
        OSError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        ValueError,
    ):
        return "", ""


def torch_backend_matches(py: Path, mode: str, torch_tag: str) -> bool:
    backend, installed_tag = installed_torch_backend(py)
    if mode == "cuda":
        return backend == "cuda" and installed_tag == torch_tag
    if mode == "directml":
        return backend == "directml"
    # CPU and MPS use the platform's standard non-CUDA Torch wheel.
    return backend == "cpu"


def prepare_pip(py: Path) -> None:
    """Upgrade installer tooling once, not before every dependency group."""
    run(
        [
            str(py),
            "-m",
            "pip",
            "install",
            "--upgrade",
            "pip",
            "setuptools",
            "wheel",
        ]
    )


def install_packages(py: Path, mode: str, torch_tag: str) -> None:
    prepare_pip(py)
    if not torch_backend_matches(py, mode, torch_tag):
        pip_uninstall(py, ["torch", "torchvision", "torch-directml"])
    if mode == "cuda" and torch_tag == "cu118":
        pip_uninstall(py, ["paddlepaddle"])
    else:
        pip_uninstall(py, ["paddlepaddle-gpu"])
    if mode == "cuda":
        log(f"\n{_NO_CUDA_TOOLKIT_NOTE}")
        if torch_tag not in TORCH_INDEX or torch_tag == "cpu":
            raise SystemExit(
                f"Invalid CUDA tag {torch_tag!r}. Expected one of: {', '.join(TORCH_CUDA_TAGS)}"
            )
        # Prefer paddle GPU for cu118; for newer CUDA use CPU paddle + CUDA torch
        # (matches Docker/CI practice for 12.x).
        if torch_tag == "cu118":
            pip_install(
                py,
                [
                    f"paddlepaddle-gpu=={PADDLE_VERSION}",
                    "-i",
                    PADDLE_CU118_INDEX,
                ],
            )
        else:
            pip_install(
                py,
                [
                    f"paddlepaddle=={PADDLE_VERSION}",
                    "-i",
                    PADDLE_CPU_INDEX,
                ],
            )
        pip_install(
            py,
            [
                f"torch=={TORCH_VERSION}",
                f"torchvision=={TORCHVISION_VERSION}",
                "--index-url",
                TORCH_INDEX[torch_tag],
            ],
        )
    elif mode == "directml":
        if platform.system() != "Windows":
            raise SystemExit("DirectML installation is supported only on Windows.")
        pip_install(py, [f"paddlepaddle=={PADDLE_VERSION}", "-i", PADDLE_CPU_INDEX])
        pip_install(py, ["torch-directml==0.2.5.dev240914"])
    elif mode == "mps":
        if platform.system() != "Darwin":
            raise SystemExit("MPS installation is supported only on macOS.")
        pip_install(py, [f"paddlepaddle=={PADDLE_VERSION}", "-i", PADDLE_CPU_INDEX])
        pip_install(
            py,
            [f"torch=={TORCH_VERSION}", f"torchvision=={TORCHVISION_VERSION}"],
        )
    else:
        pip_install(
            py,
            [
                f"paddlepaddle=={PADDLE_VERSION}",
                "-i",
                PADDLE_CPU_INDEX,
            ],
        )
        pip_install(
            py,
            [
                f"torch=={TORCH_VERSION}",
                f"torchvision=={TORCHVISION_VERSION}",
                "--index-url",
                TORCH_INDEX["cpu"],
            ],
        )

    # requirements-cuda.txt pulls in requirements.txt plus bitsandbytes, which
    # 4/8-bit quantized custom Diffusers models need (backend/models/adapters.py)
    # and which is otherwise never installed by any install.py path.
    common_requirements = "requirements-cuda.txt" if mode == "cuda" else "requirements.txt"
    pip_install(
        py,
        [
            "-r",
            str(ROOT / common_requirements),
            "-c",
            str(ROOT / "constraints.txt"),
        ],
    )


def verify_python_packages(py: Path) -> None:
    """Import-check runtime deps (including Select Object transformers APIs)."""
    log("\nVerifying Python packages…")
    script = r"""
checks = [
    ("torch", "import torch", True),
    ("cv2", "import cv2", True),
    ("PIL", "from PIL import Image", True),
    ("paddle", "import paddle", True),
    ("transformers", "import transformers", False),
    ("huggingface_hub", "import huggingface_hub", False),
    ("diffusers", "import diffusers", False),
    ("Flux2Pipeline", "from diffusers import Flux2Pipeline", False),
    ("Flux2KleinPipeline", "from diffusers import Flux2KleinPipeline", False),
    (
        "Flux2Transformer2DModel",
        "from diffusers import Flux2Transformer2DModel",
        False,
    ),
    ("QwenImagePipeline", "from diffusers import QwenImagePipeline", False),
    ("accelerate", "import accelerate", False),
    ("Sam2Model", "from transformers import Sam2Model, Sam2Processor", False),
    (
        "Grounding DINO",
        "from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor",
        False,
    ),
]
failed = []
for name, stmt, required in checks:
    try:
        exec(stmt, {})
        print(f"  OK {name}")
    except Exception as e:
        level = "FAIL" if required else "OPTIONAL"
        print(f"  {level} {name}: {e}")
        if required:
            failed.append(name)
if failed:
    raise SystemExit("Missing or broken packages: " + ", ".join(failed))
print("  All required package checks passed.")
"""
    run([str(py), "-c", script])


def verify_models() -> None:
    models = ROOT / "backend" / "models"
    required = [
        models / "sttn-auto" / "infer_model.pth",
        models / "sttn-det" / "sttn.pth",
        models / "V5" / "ch_det" / "inference.pdiparams",
        models / "V5" / "ch_det_fast" / "inference.pdiparams",
        models / "propainter" / "raft-things.pth",
        models / "propainter" / "recurrent_flow_completion.pth",
    ]
    missing = [str(p.relative_to(ROOT)) for p in required if not p.exists()]
    if missing:
        raise SystemExit(
            "Missing model files (copy the full Lluna folder including backend/models):\n  "
            + "\n  ".join(missing)
        )

    # Merge split weights if needed (filesplit)
    try:
        from fsplit.filesplit import Filesplit
    except ImportError:
        log("filesplit not importable yet; skip merge (will merge on first app run).")
        return

    def merge_if_needed(directory: Path, target_name: str) -> None:
        target = directory / target_name
        if target.exists():
            log(f"OK: {target.relative_to(ROOT)}")
            return
        parts = list(directory.glob(f"{Path(target_name).stem}_*.*"))
        manifest = directory / "fs_manifest.csv"
        if not parts and not manifest.exists():
            log(f"Warning: cannot merge {target_name} - parts not found.")
            return
        log(f"Merging {target_name} …")
        fs = Filesplit()
        fs.merge(input_dir=str(directory))
        if target.exists():
            log(f"OK: {target.relative_to(ROOT)}")
        else:
            # typo workaround: bit-lama vs big-lama
            alt = directory / "bit-lama.pt"
            if target_name == "big-lama.pt" and alt.exists():
                alt.rename(target)
                log(f"OK: renamed bit-lama.pt → {target.relative_to(ROOT)}")
            else:
                log(f"Warning: merge finished but {target.name} still missing.")

    merge_if_needed(models / "big-lama", "big-lama.pt")
    merge_if_needed(models / "propainter", "ProPainter.pth")
    log("Model check complete.")


def seed_default_model_downloads(py: Path) -> None:
    """Schedule default models for the Electron model queue on first launch."""
    log("\nScheduling default model downloads for first Electron launch…")
    script = r"""
import sys
sys.path.insert(0, sys.argv[1])
from backend.tools.installers.first_run import seed_first_run_downloads

n = seed_first_run_downloads()
print(f"  Scheduled {n} default model(s) for the model download queue.")
"""
    run([str(py), "-c", script, str(ROOT)])


def write_runtime(
    mode: str, torch_tag: str, gpu_name: str, compute_cap: str = "", total_vram_mb: float = 0.0
) -> None:
    data = {
        "product": "Lluna",
        "accel": mode,
        "torch_cuda_tag": torch_tag or None,
        "gpu_name": gpu_name or None,
        "compute_cap": compute_cap or None,
        "total_vram_mb": total_vram_mb or None,
        "venv": VENV_NAME,
    }
    RUNTIME_FILE.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    log(f"Wrote {RUNTIME_FILE.name}")


def install_desktop_dependencies() -> None:
    """Install the Electron renderer and packaging dependencies."""
    npm = shutil.which("npm")
    if not npm:
        raise SystemExit("Node.js 22+ and npm are required for source development.")
    run([npm, "install", "--allow-git=all"])


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Lluna installer (CUDA auto-detect + CPU/CUDA choice)",
        epilog=_NO_CUDA_TOOLKIT_NOTE,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--mode",
        choices=["cuda", "cpu", "directml", "mps", "auto"],
        default="auto",
        help="Force install mode (default: auto-detect then prompt)",
    )
    p.add_argument(
        "--cuda-tag",
        choices=list(TORCH_CUDA_TAGS),
        default=None,
        help="Force PyTorch CUDA wheel (cu128/cu126/cu118). Default: auto by GPU series "
        "(1xxx/2xxx→cu118, 3xxx→cu126, 4xxx/5xxx→cu128), clamped to the driver",
    )
    p.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Non-interactive: use detected default (CUDA if available, else CPU)",
    )
    p.add_argument(
        "--schedule-default-models",
        action="store_true",
        help="Schedule recommended models for first launch (default: no model downloads)",
    )
    p.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate an existing environment without installing packages",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    log("=" * 60)
    log("  Lluna Installer")
    log("=" * 60)
    log(f"  {_NO_CUDA_TOOLKIT_NOTE}")
    log("")

    cuda = detect_cuda()
    forced = None if args.mode == "auto" else args.mode
    if forced is None and platform.system() == "Darwin":
        forced = "mps"
    mode, torch_tag = choose_mode(cuda, forced, args.yes, cuda_tag_override=args.cuda_tag)

    python_bin = find_python()
    validate_python(python_bin)
    log(f"\nPython: {python_bin}")
    log(f"Install mode: {mode.upper()}" + (f" ({torch_tag})" if torch_tag else ""))
    if mode == "cuda" and cuda.tag_reason and not args.cuda_tag:
        log(f"  {cuda.tag_reason}")

    venv_dir = ensure_venv(python_bin)
    py = venv_python(venv_dir)
    if not py.exists():
        raise SystemExit(f"venv python missing: {py}")

    if not args.validate_only:
        install_packages(py, mode, torch_tag or "cu118")
    verify_python_packages(py)
    if args.validate_only:
        log("\nExisting environment validation passed.")
        return 0
    merge_script = (
        "import sys; sys.path.insert(0, %r); from install import verify_models; verify_models()"
    ) % str(ROOT)
    run([str(py), "-c", merge_script])

    try:
        from backend.tools.shared.download_lifecycle import cli_stop_and_revert_downloads

        cli_stop_and_revert_downloads()
    except Exception as e:
        log(f"  (model download cancel hook: {e})")

    if args.schedule_default_models:
        seed_default_model_downloads(py)
        log("  Recommended models will download one at a time after first launch.")
    else:
        log("  No optional models scheduled. Install models from the Models settings.")

    write_runtime(
        mode,
        torch_tag,
        cuda.gpu_name,
        compute_cap=getattr(cuda, "compute_cap", "") or "",
        total_vram_mb=float(getattr(cuda, "total_vram_mb", 0) or 0),
    )
    install_desktop_dependencies()

    log("\n" + "=" * 60)
    log("  Lluna install complete.")
    log("=" * 60)
    log("  Desktop: npm run dev")
    log("")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        log(f"\nInstall failed (exit {exc.returncode}).")
        raise SystemExit(exc.returncode)
