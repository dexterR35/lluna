"""Bundled SeedVR2 inference and isolated-runtime lifecycle.

The reviewed SeedVR2 inference source is shipped in ``backend/ai/seedvr2``.
Installation downloads only the optional Hugging Face weights and creates the
isolated CUDA runtime required by the upstream implementation.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path

from backend.core.atomic import atomic_write_json
from backend.core.paths import PATHS
from backend.tools.installers._shared import (
    bootstrap_reviewed_python,
    create_isolated_venv,
    verify_pinned_artifact,
)

KIND_SEEDVR = "seedvr2"
SEEDVR_COMMIT = "e4de8c24441a67e1b7df56abea10645059bb1185"
SEEDVR_SOURCE_REPO = "ByteDance-Seed/SeedVR"
SEEDVR_RUNTIME_PROFILE = "seedvr-python"

MODEL_CONFIG = {
    "seedvr2-3b": {
        "repo": "ByteDance-Seed/SeedVR2-3B",
        "revision": "37255ff8cccfb01071b87f635a5948ca8d53117c",
        "checkpoint": "seedvr2_ema_3b.pth",
        "checkpoint_size": 13566090228,
        "checkpoint_sha256": "6bcc5ac59447e97b100477480aebb01be2ec724c8340bb83faae21f64848604b",
        "minimum_vram_mb": 24576,
    },
    "seedvr2-7b": {
        "repo": "ByteDance-Seed/SeedVR2-7B",
        "revision": "eb0c4281d41ba3767d4f14370f0e37e9e9180c16",
        "checkpoint": "seedvr2_ema_7b.pth",
        "checkpoint_size": 32958774606,
        "checkpoint_sha256": "e1b2ae25505607e61f2a7dc7967ba778aaf3e3626d9969ce6e24c52d9ddebfcd",
        "minimum_vram_mb": 49152,
    },
    # GGUF-quantized 3B variants: same architecture and (verified) identical
    # state_dict tensor names as "seedvr2-3b" above, loaded through
    # backend/ai/seedvr2/common/gguf_loader.py instead of a plain torch.load. Only
    # the 2D weight matrix of each Linear-like layer is quantized; the compressed
    # bytes stay on CPU and are dequantized just-in-time per forward pass, so the
    # resident VRAM footprint is far below the fp16/bf16 checkpoint's 24576 MB
    # floor -- the minimum_vram_mb values below are engineering estimates pending
    # confirmation on real hardware, not measured floors like the entry above.
    "seedvr2-3b-gguf-q3": {
        "repo": "cmeka/SeedVR2-GGUF",
        "revision": "de058a1261f2fc4bb41f39e9ddf313877e4ebf0d",
        "checkpoint": "seedvr2_ema_3b-Q3_K_M.gguf",
        "checkpoint_size": 1553006944,
        "checkpoint_sha256": "44b67c65b272cb778cef68c67370a5703a4e1ab09e2cd5b9a8e2a4eb4e3bdb8c",
        "minimum_vram_mb": 8192,
    },
    "seedvr2-3b-gguf-q4": {
        "repo": "cmeka/SeedVR2-GGUF",
        "revision": "de058a1261f2fc4bb41f39e9ddf313877e4ebf0d",
        "checkpoint": "seedvr2_ema_3b-Q4_K_M.gguf",
        "checkpoint_size": 1995344224,
        "checkpoint_sha256": "e665e3909de1a8c88a69c609bca9d43ff5a134647face2ce4497640cc3597f0e",
        "minimum_vram_mb": 9216,
    },
    "seedvr2-3b-gguf-q8": {
        "repo": "cmeka/SeedVR2-GGUF",
        "revision": "de058a1261f2fc4bb41f39e9ddf313877e4ebf0d",
        "checkpoint": "seedvr2_ema_3b-Q8_0.gguf",
        "checkpoint_size": 3660613984,
        "checkpoint_sha256": "be0d60083a2051a265eb4b77f28edf494e6db67ffc250216f32b72292e5cbd96",
        "minimum_vram_mb": 11264,
    },
}

# The VAE is byte-identical across the official 3B/7B repos (same lfs oid on both),
# so any of those two downloads can supply it -- but the GGUF repo above doesn't
# host it at all, so it's always sourced from the canonical 3B repo/revision
# regardless of which variant is being installed.
VAE_SOURCE_REPO = MODEL_CONFIG["seedvr2-3b"]["repo"]
VAE_SOURCE_REVISION = MODEL_CONFIG["seedvr2-3b"]["revision"]
VAE_ARTIFACT = {
    "filename": "ema_vae.pth",
    "size": 1002691902,
    "sha256": "c7df8a67e68b7f9aca3d5d2153d2ce8ab4373687741a0f9ce87cb356ace51cac",
}

# Apex is only published (as a prebuilt wheel) in the 3B repo, pinned to
# MODEL_CONFIG["seedvr2-3b"]["revision"] above; both wheels are downloaded
# from there regardless of which SeedVR2 model was installed.
APEX_WHEEL_REPO = "ByteDance-Seed/SeedVR2-3B"
APEX_WHEELS = {
    "cp310": {
        "filename": "apex-0.1-cp310-cp310-linux_x86_64.whl",
        "size": 4857175,
        "sha256": "9f4b44a79c37203140c26a2a8c566179ced06685786bc2a0c3cb16e06f0c3522",
    },
    "cp39": {
        "filename": "apex-0.1-cp39-cp39-linux_x86_64.whl",
        "size": 4839299,
        "sha256": "a960427deced65f2d68908a80b671ff9fa0c2c3e7f02693b690b6126c178667f",
    },
}

# flash-attn publishes no wheels on PyPI, so `pip install flash_attn` compiles from
# source: a CUDA Toolkit, ~10 GB of RAM and up to two hours on the user's machine.
# The project's own GitHub releases carry prebuilt wheels keyed by CUDA line, torch
# minor, C++ ABI and Python tag; the entry below is the one matching this runtime's
# torch 2.4.1+cu121 (cu122 wheels are the CUDA 12.x line, and torch's own wheels are
# built with _GLIBCXX_USE_CXX11_ABI=0 -> abiFALSE). Upstream publishes no Windows
# wheel, and neither does Apex; both are skipped outside Linux and the runtime
# falls back to SDPA attention / plain PyTorch normalization instead (see
# models/dit{,_v2}/attention.py and normalization.py).
FLASH_ATTN_VERSION = "2.5.9.post1"
FLASH_ATTN_WHEELS = {
    ("cp310", "linux"): {
        "filename": (
            f"flash_attn-{FLASH_ATTN_VERSION}+cu122torch2.4cxx11abiFALSE"
            "-cp310-cp310-linux_x86_64.whl"
        ),
        "size": 120906339,
        "sha256": "d9f38b3e4527a96ff11a2362f12c66e362f003f45c00d6d35af71914ebb1b7fa",
    },
}
FLASH_ATTN_RELEASE_URL = (
    "https://github.com/Dao-AILab/flash-attention/releases/download/v" + FLASH_ATTN_VERSION
)

SEEDVR_PACKAGES = (
    "einops==0.7.0",
    # torch==2.4.0's Windows cu121 wheel ships fbgemm.dll without a DLL it needs
    # (libomp140.x86_64.dll), so `import torch` itself fails with WinError 126.
    # 2.4.1 is the same minor line (ABI-compatible with the flash-attn wheel
    # below, which is tagged for the 2.4.x line generically) with that packaging
    # bug fixed; torchvision 0.19.1 is the version pytorch.org pairs with it.
    "torch==2.4.1",
    "torchvision==0.19.1",
    "omegaconf==2.3.0",
    "opencv-python==4.9.0.80",
    "diffusers==0.33.1",
    "rotary-embedding-torch==0.5.3",
    "transformers==4.46.2",
    "mediapy==1.2.0",
    "accelerate==0.33.0",
    "numpy==1.24.4",
    "pillow==10.3.0",
    "scipy==1.13.1",
    "safetensors==0.4.3",
    "pyyaml==6.0.1",
    "av==12.0.0",
    "timm==1.0.11",
    "tqdm",
    "ninja",
    "gguf",
)


def models_root() -> Path:
    root = PATHS.models_dir / "seedvr2"
    root.mkdir(parents=True, exist_ok=True)
    return root


def source_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "ai" / "seedvr2"


def checkpoints_dir() -> Path:
    return models_root() / "ckpts"


def model_dir(model_id: str) -> Path:
    if model_id not in MODEL_CONFIG:
        raise ValueError(f"Unknown SeedVR2 model: {model_id}")
    return models_root() / model_id


def runtime_dir() -> Path:
    return PATHS.data_dir / "model-runtimes" / SEEDVR_RUNTIME_PROFILE


def runtime_python() -> Path:
    return runtime_dir() / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _source_ready() -> bool:
    return all(
        (
            (source_dir() / "projects" / "inference_seedvr2_3b.py").is_file(),
            (source_dir() / "projects" / "inference_seedvr2_7b.py").is_file(),
            (source_dir() / "configs_3b" / "main.yaml").is_file(),
            (source_dir() / "configs_7b" / "main.yaml").is_file(),
            (source_dir() / "pos_emb.pt").is_file(),
            (source_dir() / "neg_emb.pt").is_file(),
        )
    )


def readiness(model_id: str) -> dict[str, bool]:
    config = MODEL_CONFIG[model_id]
    return {
        "source": _source_ready(),
        "runtime": runtime_python().is_file() and (runtime_dir() / "runtime.json").is_file(),
        "checkpoint": (checkpoints_dir() / config["checkpoint"]).is_file(),
        "vae": (checkpoints_dir() / VAE_ARTIFACT["filename"]).is_file(),
        "model": (model_dir(model_id) / ".lluna-installed").is_file(),
    }


def is_model_installed(model_id: str) -> bool:
    status = readiness(model_id)
    return all(status.values())


def cuda_compatible() -> bool:
    from backend.hardware.detector import get_hardware_profile
    from backend.hardware.policy import select_execution_policy

    return select_execution_policy(get_hardware_profile()).backend == "cuda"


def _bootstrap_python() -> str:
    return bootstrap_reviewed_python(
        env_var="LLUNA_SEEDVR_PYTHON",
        versions=("3.10", "3.9"),
        error_message=(
            "SeedVR2 requires Python 3.10 or 3.9, and one could not be found or downloaded. "
            "Install Python 3.10 or point LLUNA_SEEDVR_PYTHON at an existing one."
        ),
        provision=True,
    )


def _platform_tag() -> str:
    return "windows" if os.name == "nt" else "linux"


def _ensure_flash_attn_wheel(python_tag: str) -> Path:
    """Download and verify the pinned flash-attn wheel.

    flash-attn is an optional accelerator, not a hard requirement: the vendored DiT
    (``models/dit{,_v2}/attention.py``) falls back to a PyTorch SDPA attention
    implementation when flash-attn isn't importable. It's only worth installing
    where a prebuilt wheel exists (Linux); callers gate on that before calling this.
    """
    expected = FLASH_ATTN_WHEELS.get((python_tag, _platform_tag()))
    if expected is None:
        raise RuntimeError(
            "SeedVR2 needs a prebuilt flash-attn wheel, and none is published for "
            f"{_platform_tag()} / {python_tag}. Reviewed combinations: "
            + ", ".join(f"{tag} on {system}" for tag, system in sorted(FLASH_ATTN_WHEELS))
            + "."
        )
    destination = checkpoints_dir() / expected["filename"]
    if destination.is_file():
        try:
            verify_pinned_artifact(
                destination, expected_size=expected["size"], expected_sha256=expected["sha256"]
            )
            return destination
        except ValueError:
            destination.unlink(missing_ok=True)

    from backend.tools.shared.download_registry import urllib_cancel_reporthook

    checkpoints_dir().mkdir(parents=True, exist_ok=True)
    staging = models_root() / ".downloads" / "flash-attn"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)
    downloaded = staging / expected["filename"]
    url = f"{FLASH_ATTN_RELEASE_URL}/{urllib.parse.quote(expected['filename'])}"
    try:
        urllib.request.urlretrieve(  # noqa: S310 - pinned HTTPS URL, hash-verified below
            url, downloaded, reporthook=urllib_cancel_reporthook
        )
        verify_pinned_artifact(
            downloaded, expected_size=expected["size"], expected_sha256=expected["sha256"]
        )
    except (OSError, ValueError) as exc:
        shutil.rmtree(staging, ignore_errors=True)
        raise RuntimeError(f"The pinned flash-attn wheel could not be installed: {exc}") from exc
    temporary = destination.with_suffix(destination.suffix + ".part")
    downloaded.replace(temporary)
    temporary.replace(destination)
    shutil.rmtree(staging, ignore_errors=True)
    return destination


def _ensure_apex_wheel(python_tag: str) -> Path:
    """Download (if needed) and verify the pinned Apex wheel for ``python_tag``.

    Apex is an optional accelerator, not a hard requirement: the shipped SeedVR2
    configs ask for ``fusedrms``/``fusedln`` normalization, but
    ``models/dit{,_v2}/normalization.py`` falls back to plain RMSNorm/LayerNorm when
    apex isn't importable. Apex publishes Linux wheels only, so it's only worth
    installing there; callers gate on that before calling this.
    """
    expected = APEX_WHEELS.get(python_tag) if _platform_tag() == "linux" else None
    if expected is None:
        raise RuntimeError(
            "SeedVR2 needs the prebuilt Apex wheel, which upstream publishes for "
            f"Linux only (Python tags: {', '.join(sorted(APEX_WHEELS))}); this is "
            f"{_platform_tag()} / {python_tag}."
        )
    destination = checkpoints_dir() / expected["filename"]
    if destination.is_file():
        try:
            verify_pinned_artifact(
                destination, expected_size=expected["size"], expected_sha256=expected["sha256"]
            )
            return destination
        except ValueError:
            destination.unlink(missing_ok=True)

    from backend.tools.shared.huggingface import snapshot_download_with_progress

    staging = models_root() / ".downloads" / "apex"
    shutil.rmtree(staging, ignore_errors=True)
    snapshot_download_with_progress(
        repo_id=APEX_WHEEL_REPO,
        revision=MODEL_CONFIG["seedvr2-3b"]["revision"],
        local_dir=str(staging),
        allow_patterns=[expected["filename"]],
    )
    downloaded = staging / expected["filename"]
    if not downloaded.is_file():
        raise RuntimeError(f"Hugging Face did not provide {expected['filename']}.")
    verify_pinned_artifact(
        downloaded, expected_size=expected["size"], expected_sha256=expected["sha256"]
    )
    checkpoints_dir().mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    downloaded.replace(temporary)
    temporary.replace(destination)
    shutil.rmtree(staging, ignore_errors=True)
    return destination


def _install_runtime() -> None:
    if runtime_python().is_file() and (runtime_dir() / "runtime.json").is_file():
        return
    python = _bootstrap_python()
    version_probe = subprocess.run(  # noqa: S603 - reviewed Python executable and fixed probe
        [python, "-c", "import sys; print(f'cp{sys.version_info.major}{sys.version_info.minor}')"],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    python_tag = version_probe.stdout.strip()
    # flash-attn and Apex are optional accelerators (see models/dit{,_v2}/attention.py
    # and normalization.py for the SDPA / plain-norm fallbacks they use when absent).
    # Both publish prebuilt wheels for Linux only, so they're attempted there when a
    # matching wheel is pinned and skipped everywhere else, rather than failing the
    # install outright.
    pip_install_steps = [
        [
            "torch==2.4.1",
            "torchvision==0.19.1",
            "--index-url",
            "https://download.pytorch.org/whl/cu121",
        ],
        list(SEEDVR_PACKAGES),
    ]
    runtime_metadata = {
        "profile": SEEDVR_RUNTIME_PROFILE,
        "bundledSource": SEEDVR_SOURCE_REPO,
        "sourceCommit": SEEDVR_COMMIT,
        "packages": list(SEEDVR_PACKAGES),
        "flashAttention": None,
        "fusedNorm": None,
        "managedBy": "lluna",
    }
    if _platform_tag() == "linux" and (python_tag, "linux") in FLASH_ATTN_WHEELS:
        flash_attn_wheel = _ensure_flash_attn_wheel(python_tag)
        pip_install_steps.append([str(flash_attn_wheel)])
        runtime_metadata["flashAttention"] = flash_attn_wheel.name
    if _platform_tag() == "linux" and python_tag in APEX_WHEELS:
        apex_wheel = _ensure_apex_wheel(python_tag)
        pip_install_steps.append([str(apex_wheel)])
        runtime_metadata["fusedNorm"] = apex_wheel.name
    create_isolated_venv(
        python_executable=python,
        target_dir=runtime_dir(),
        staging_name=".seedvr-python.staging",
        pip_install_steps=pip_install_steps,
        runtime_metadata=runtime_metadata,
    )


def _download_checkpoint(model_id: str) -> None:
    from backend.tools.shared.huggingface import snapshot_download_with_progress

    config = MODEL_CONFIG[model_id]
    staging = models_root() / ".downloads" / model_id
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)

    # The VAE is shared across every SeedVR2 variant; skip re-downloading it once
    # any prior install has already placed it in the shared checkpoints dir.
    need_vae = not (checkpoints_dir() / VAE_ARTIFACT["filename"]).is_file()

    snapshot_download_with_progress(
        repo_id=config["repo"],
        revision=config["revision"],
        local_dir=str(staging),
        allow_patterns=[config["checkpoint"]],
    )
    checkpoint_file = staging / config["checkpoint"]
    if not checkpoint_file.is_file():
        raise RuntimeError(f"Hugging Face did not provide the SeedVR2 {model_id} checkpoint.")
    verify_pinned_artifact(
        checkpoint_file,
        expected_size=config["checkpoint_size"],
        expected_sha256=config["checkpoint_sha256"],
    )

    if need_vae:
        # config["repo"] may be a GGUF-only repo that doesn't host the VAE at all
        # (e.g. cmeka/SeedVR2-GGUF), so it's always fetched from the canonical
        # ByteDance 3B repo regardless of which variant's checkpoint this is.
        snapshot_download_with_progress(
            repo_id=VAE_SOURCE_REPO,
            revision=VAE_SOURCE_REVISION,
            local_dir=str(staging),
            allow_patterns=[VAE_ARTIFACT["filename"]],
        )
        vae_file = staging / VAE_ARTIFACT["filename"]
        if not vae_file.is_file():
            raise RuntimeError("Hugging Face did not provide the SeedVR2 shared VAE.")
        verify_pinned_artifact(
            vae_file, expected_size=VAE_ARTIFACT["size"], expected_sha256=VAE_ARTIFACT["sha256"]
        )

    checkpoints_dir().mkdir(parents=True, exist_ok=True)
    filenames = [config["checkpoint"]] + ([VAE_ARTIFACT["filename"]] if need_vae else [])
    for filename in filenames:
        source = staging / filename
        target = checkpoints_dir() / filename
        temporary = target.with_suffix(target.suffix + ".part")
        source.replace(temporary)
        temporary.replace(target)
    shutil.rmtree(staging, ignore_errors=True)


def install_model(model_id: str) -> Path:
    """Install one official SeedVR2 variant and its shared runtime assets."""
    if model_id not in MODEL_CONFIG:
        raise ValueError(f"Unknown SeedVR2 model: {model_id}")
    if not cuda_compatible():
        raise RuntimeError("SeedVR2 requires an NVIDIA CUDA GPU. Model files were not installed.")
    from backend.tools.shared.download_registry import DownloadCancelled, ModelDownloadRegistry

    registry = ModelDownloadRegistry.instance()
    registry.begin(KIND_SEEDVR, model_id)
    try:
        registry.check_cancelled()
        _download_checkpoint(model_id)
        registry.check_cancelled()
        _install_runtime()
        marker = model_dir(model_id) / ".lluna-installed"
        marker.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(
            marker,
            {"modelId": model_id, "repo": MODEL_CONFIG[model_id]["repo"], "managedBy": "lluna"},
        )
        registry.complete(KIND_SEEDVR, model_id)
        return model_dir(model_id)
    except DownloadCancelled:
        discard_partial(model_id)
        registry.fail(KIND_SEEDVR, model_id, keep_pending=True)
        raise
    except Exception:
        discard_partial(model_id)
        registry.fail(KIND_SEEDVR, model_id, keep_pending=False)
        raise


def discard_partial(model_id: str) -> None:
    staging = models_root() / ".downloads" / model_id
    shutil.rmtree(staging, ignore_errors=True)


def uninstall_model(model_id: str) -> None:
    if model_id not in MODEL_CONFIG:
        raise ValueError(f"Unknown SeedVR2 model: {model_id}")
    config = MODEL_CONFIG[model_id]
    discard_partial(model_id)
    (checkpoints_dir() / config["checkpoint"]).unlink(missing_ok=True)
    # Remove this model's own marker dir first so the "any other model still
    # installed" check below isn't fooled by its own stale marker - otherwise
    # the shared checkpoints/runtime dirs would never be reclaimed even after
    # every SeedVR2 model was uninstalled.
    shutil.rmtree(model_dir(model_id), ignore_errors=True)
    if not any((model_dir(item) / ".lluna-installed").is_file() for item in MODEL_CONFIG):
        shutil.rmtree(checkpoints_dir(), ignore_errors=True)
        shutil.rmtree(runtime_dir(), ignore_errors=True)
