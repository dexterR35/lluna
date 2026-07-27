#!/usr/bin/env python3
"""
Midgard installer - detects CUDA vs CPU, lets you choose, then installs deps + verifies models.

GPU mode needs NVIDIA drivers (nvidia-smi). You do NOT need the NVIDIA CUDA Toolkit (full SDK) —
install.py pulls GPU PyTorch/Paddle wheels that bundle the CUDA runtime libs.

Usage:
  python install.py
  python install.py --mode cpu
  python install.py --mode cuda --yes
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
VENV_NAME = "midgardEnv"
RUNTIME_FILE = ROOT / "midgard_runtime.json"

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
ORT_CUDA11_INDEX = (
    "https://aiinfra.pkgs.visualstudio.com/PublicPackages/"
    "_packaging/onnxruntime-cuda-11/pypi/simple/"
)


# PyTorch CUDA wheel tags Midgard ships (see TORCH_INDEX). Highest first.
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
    """Prefer 3.12, then 3.13, 3.11; otherwise current interpreter if 3.11–3.13."""
    candidates = [
        "python3.12",
        "python3.13",
        "python3.11",
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
                [path, "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
            major, minor = map(int, out.split("."))
            if (major, minor) in {(3, 11), (3, 12), (3, 13)}:
                return path
        except (subprocess.CalledProcessError, FileNotFoundError, ValueError):
            continue

    vi = sys.version_info
    if (vi.major, vi.minor) in {(3, 11), (3, 12), (3, 13)}:
        return sys.executable

    log(
        f"Warning: preferred Python 3.11–3.13 not found. "
        f"Using {sys.executable} ({vi.major}.{vi.minor}). "
        f"Some packages may lack wheels."
    )
    return sys.executable


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
    """Human label for GeForce/RTX generations Midgard maps."""
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
        reason = (
            f"{series} (cc {cap:g} via {cap_source or 'detect'}) "
            f"→ torch cu128 (required)"
        )
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
    reason = (
        f"GPU series unknown → torch {driver_tag} "
        f"(driver CUDA {driver_cuda or 'unknown'})"
    )
    return driver_tag, reason, warning


def choose_mode_gui(default_cuda: bool, detect_msg: str) -> str:
    import tkinter as tk
    from tkinter import ttk

    result: dict[str, str] = {"mode": "cuda" if default_cuda else "cpu"}

    root = tk.Tk()
    root.title("Midgard Installer")
    root.resizable(False, False)
    root.attributes("-topmost", True)

    frame = ttk.Frame(root, padding=20)
    frame.grid()

    ttk.Label(frame, text="Midgard Installer", font=("Segoe UI", 14, "bold")).grid(
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

    if forced in {"cuda", "cpu"}:
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
        log(f"Non-interactive: installing {mode.upper()}" + (f" ({resolve_tag(mode)})" if mode == "cuda" else ""))
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
            __import__("urllib.request").request.urlopen(
                "https://bootstrap.pypa.io/get-pip.py", timeout=120
            ).read()
        )
        run([str(py), str(get_pip)])
        get_pip.unlink(missing_ok=True)
    return venv_dir


def pip_install(py: Path, args: list[str]) -> None:
    run([str(py), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"])
    run([str(py), "-m", "pip", "install", *args])


def install_packages(py: Path, mode: str, torch_tag: str) -> None:
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
        if platform.system() == "Linux":
            if torch_tag == "cu118":
                pip_install(
                    py,
                    [
                        "onnxruntime-gpu==1.20.1",
                        "--index-url",
                        ORT_CUDA11_INDEX,
                    ],
                )
            else:
                pip_install(py, ["onnxruntime-gpu==1.22.0"])
        elif platform.system() == "Windows":
            # rembg needs ORT; prefer GPU build when CUDA mode is selected
            pip_install(py, ["onnxruntime-gpu"])
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
        # CPU onnxruntime for rembg / OCR helpers
        pip_install(py, ["onnxruntime"])

    pip_install(py, ["-r", str(ROOT / "requirements.txt")])
    # Ensure rembg is present (also listed in requirements.txt)
    pip_install(py, ["rembg>=2.0.60"])
    # Select Object (SAM2 + Grounding DINO via Hugging Face transformers)
    pip_install(py, ["transformers>=4.48.0", "huggingface_hub>=0.26.0"])
    # Generate (FLUX.2 klein via Diffusers) — weights installed from Settings
    pip_install(py, ["diffusers>=0.37.1", "accelerate>=1.0.0"])


def verify_python_packages(py: Path) -> None:
    """Import-check runtime deps (including Select Object transformers APIs)."""
    log("\nVerifying Python packages…")
    script = r"""
checks = [
    ("torch", "import torch"),
    ("transformers", "import transformers"),
    ("huggingface_hub", "import huggingface_hub"),
    ("diffusers", "import diffusers"),
    ("accelerate", "import accelerate"),
    ("Sam2Model", "from transformers import Sam2Model, Sam2Processor"),
    (
        "Grounding DINO",
        "from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor",
    ),
    ("rembg", "import rembg"),
    ("onnxruntime", "import onnxruntime"),
    ("cv2", "import cv2"),
    ("PIL", "from PIL import Image"),
]
failed = []
for name, stmt in checks:
    try:
        exec(stmt, {})
        print(f"  OK {name}")
    except Exception as e:
        print(f"  FAIL {name}: {e}")
        failed.append(name)
if failed:
    raise SystemExit("Missing or broken packages: " + ", ".join(failed))
print("  All package checks passed.")
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
            "Missing model files (copy the full Midgard folder including backend/models):\n  "
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


# Category defaults only on first install (must match BgRemoveMode / MODEL_CATALOG is_default).
# Optional models (BiRefNet Massive, BRIA, Lite, …) download from Settings → Remove BG Models.
REMBG_PREFETCH_MODELS = [
    "birefnet-general",  # General - app default
    "u2net_human_seg",   # People
    "isnet-anime",       # Anime
    "u2net_cloth_seg",   # Clothes
]


def prefetch_rembg_models(py: Path) -> None:
    """Download default Remove BG ONNX weights (optional models install from Settings)."""
    log("\nPrefetching default Remove BG models…")
    # JSON list avoids quoting issues across shells
    models_json = json.dumps(REMBG_PREFETCH_MODELS)
    script = r"""
import json, sys
models = json.loads(sys.argv[1])
from rembg.sessions import sessions_class

by_name = {}
for cls in sessions_class:
    try:
        n = cls.name() if callable(getattr(cls, "name", None)) else None
    except Exception:
        n = None
    if n:
        by_name[n] = cls

ok = fail = skip = 0
for name in models:
    cls = by_name.get(name)
    if cls is None:
        print(f"  SKIP {name} (not in rembg)")
        skip += 1
        continue
    try:
        print(f"  Downloading {name} …")
        path = cls.download_models()
        print(f"  OK {name} -> {path}")
        ok += 1
    except Exception as e:
        print(f"  WARN {name}: {e}")
        fail += 1
print(f"Remove BG models: ok={ok} warn={fail} skip={skip}")
"""
    run([str(py), "-c", script, models_json])


def prefetch_enhance_x2(py: Path) -> None:
    """Mandatory first-install: Real-ESRGAN ×2 (app default). ×4 stays Settings-only."""
    log("\nInstalling default Enhance model (Real-ESRGAN ×2)…")
    script = r"""
import sys
sys.path.insert(0, sys.argv[1])
from backend.tools.constant import EnhanceMode
from backend.tools.enhance_models import (
    ensure_model_installed,
    is_model_installed,
    model_file_path,
)

mode = EnhanceMode.X2PLUS
path = model_file_path(mode)
if is_model_installed(mode):
    print(f"  OK already present: {path}")
else:
    print("  Downloading RealESRGAN_x2plus …")
    path = ensure_model_installed(mode)
    print(f"  OK {path}")
"""
    run([str(py), "-c", script, str(ROOT)])


def prefetch_low_light_mirnet(py: Path) -> None:
    """Mandatory first-install: MIRNet LOL (Low Light page default). Leaves Settings On."""
    log("\nInstalling default Low Light model (MIRNet LOL)…")
    script = r"""
import sys
sys.path.insert(0, sys.argv[1])
from backend.config import config
from backend.tools.constant import LowLightMode
from backend.tools.low_light_models import (
    ensure_model_installed,
    is_model_installed,
    model_file_path,
    set_model_enabled,
)

mode = LowLightMode.MIRNET_LOL
path = model_file_path(mode)
if is_model_installed(mode):
    print(f"  OK already present: {path}")
else:
    print("  Downloading MIRNet_LOL …")
    path = ensure_model_installed(mode)
    print(f"  OK {path}")
# Default On after install (same as Settings Install button)
set_model_enabled(mode, True)
config.set(config.lowLightMode, mode)
print("  Enabled: On (default)")
"""
    run([str(py), "-c", script, str(ROOT)])


def prefetch_select_object_defaults(py: Path) -> None:
    """Install missing Select Object defaults only; skip models already on disk."""
    log("\nSelect Object models (install missing only)…")
    script = r"""
import sys
sys.path.insert(0, sys.argv[1])
from backend.tools.select_object_models import (
    PAIR_CATALOG,
    PAIR_MEMBERS,
    SelectObjectPairId,
    is_pair_installed,
    model_dir,
    prefetch_on_install,
)

for info in PAIR_CATALOG:
    pid = info.pair_id
    if is_pair_installed(pid):
        sam2, dino = PAIR_MEMBERS[pid]
        print(f"  OK already present: {model_dir(sam2)} + {model_dir(dino)}")

if not is_pair_installed(SelectObjectPairId.FAST):
    print("  Downloading standard pair (SAM2 Tiny + DINO Tiny) …")
prefetch_on_install()
if is_pair_installed(SelectObjectPairId.FAST):
    sam2, dino = PAIR_MEMBERS[SelectObjectPairId.FAST]
    print(f"  OK {model_dir(sam2)} + {model_dir(dino)}")
"""
    run([str(py), "-c", script, str(ROOT)])


def seed_default_model_downloads(py: Path, *, skip_rembg: bool = False) -> None:
    """Schedule default models for the GUI download queue (one at a time on first open)."""
    log("\nScheduling default model downloads for first GUI open…")
    script = r"""
import sys
sys.path.insert(0, sys.argv[1])
from backend.tools.first_run_downloads import seed_first_run_downloads

n = seed_first_run_downloads(skip_rembg=sys.argv[2] == "1")
print(f"  Scheduled {n} default model(s) for the Settings download queue.")
"""
    run([str(py), "-c", script, str(ROOT), "1" if skip_rembg else "0"])


def write_runtime(mode: str, torch_tag: str, gpu_name: str, compute_cap: str = "", total_vram_mb: float = 0.0) -> None:
    data = {
        "product": "Midgard",
        "accel": mode,
        "torch_cuda_tag": torch_tag or None,
        "gpu_name": gpu_name or None,
        "compute_cap": compute_cap or None,
        "total_vram_mb": total_vram_mb or None,
        "venv": VENV_NAME,
    }
    RUNTIME_FILE.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    log(f"Wrote {RUNTIME_FILE.name}")


def write_launchers(venv_dir: Path) -> None:
    py = venv_python(venv_dir)
    if platform.system() == "Windows":
        bat = ROOT / "run_gui.bat"
        bat.write_text(
            f'@echo off\r\n'
            f'cd /d "%~dp0"\r\n'
            f'"{py}" gui.py %*\r\n',
            encoding="utf-8",
        )
        log(f"Wrote {bat.name}")
    else:
        sh = ROOT / "run_gui.sh"
        sh.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            f'cd "$(dirname "$0")"\n'
            f'exec "{py}" gui.py "$@"\n',
            encoding="utf-8",
        )
        sh.chmod(sh.stat().st_mode | 0o111)
        log(f"Wrote {sh.name}")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Midgard installer (CUDA auto-detect + CPU/CUDA choice)",
        epilog=_NO_CUDA_TOOLKIT_NOTE,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--mode",
        choices=["cuda", "cpu", "auto"],
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
        "--skip-rembg-models",
        action="store_true",
        help="Skip downloading default Remove BG weights (install defaults or optionals from Settings)",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    log("=" * 60)
    log("  Midgard Installer")
    log("=" * 60)
    log(f"  {_NO_CUDA_TOOLKIT_NOTE}")
    log("")

    cuda = detect_cuda()
    forced = None if args.mode == "auto" else args.mode
    mode, torch_tag = choose_mode(
        cuda, forced, args.yes, cuda_tag_override=args.cuda_tag
    )

    python_bin = find_python()
    log(f"\nPython: {python_bin}")
    log(f"Install mode: {mode.upper()}" + (f" ({torch_tag})" if torch_tag else ""))
    if mode == "cuda" and cuda.tag_reason and not args.cuda_tag:
        log(f"  {cuda.tag_reason}")

    venv_dir = ensure_venv(python_bin)
    py = venv_python(venv_dir)
    if not py.exists():
        raise SystemExit(f"venv python missing: {py}")

    install_packages(py, mode, torch_tag or "cu118")
    verify_python_packages(py)
    merge_script = (
        "import sys; sys.path.insert(0, %r); "
        "from install import verify_models; verify_models()"
    ) % str(ROOT)
    run([str(py), "-c", merge_script])

    try:
        from backend.tools.model_download_lifecycle import cli_stop_and_revert_downloads

        cli_stop_and_revert_downloads()
    except Exception as e:
        log(f"  (model download cancel hook: {e})")

    seed_default_model_downloads(py, skip_rembg=args.skip_rembg_models)
    if args.skip_rembg_models:
        log("  Remove BG defaults skipped (--skip-rembg-models) — install from Settings.")
    log("  Default models (incl. Real-ESRGAN ×2) download one at a time when you open the GUI.")

    write_runtime(
        mode,
        torch_tag,
        cuda.gpu_name,
        compute_cap=getattr(cuda, "compute_cap", "") or "",
        total_vram_mb=float(getattr(cuda, "total_vram_mb", 0) or 0),
    )
    write_launchers(venv_dir)

    log("\n" + "=" * 60)
    log("  Midgard install complete.")
    log("=" * 60)
    if platform.system() == "Windows":
        log("  GUI:  run_gui.bat")
        log(f"  CLI:  {py} backend\\main.py -i video.mp4")
    else:
        log("  GUI:  ./run_gui.sh")
        log(f"  CLI:  {py} backend/main.py -i video.mp4")
    log("")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        log(f"\nInstall failed (exit {exc.returncode}).")
        raise SystemExit(exc.returncode)
