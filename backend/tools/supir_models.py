"""Reviewed SUPIR source, checkpoint, and isolated-runtime lifecycle."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from backend.core.atomic import atomic_write_json
from backend.core.paths import PATHS

SUPIR_COMMIT = "bda91af2000042f8bedfec8897d92917e67c1d88"
SUPIR_SOURCE_URL = f"https://github.com/Fanghua-Yu/SUPIR/archive/{SUPIR_COMMIT}.zip"
SUPIR_DOWNLOADS_URL = "https://drive.google.com/drive/folders/1yELzm5SvAi9e7kPcO_jPp2XkTs4vK6aR"
SUPIR_MIRROR_URL = "https://huggingface.co/XCogni/Supir"
SUPIR_MIRROR_REPO = "XCogni/Supir"
SUPIR_MIRROR_REVISION = "b13056f97b1f6e78cb76273330f5262d08455a6b"
SDXL_REPO = "stabilityai/stable-diffusion-xl-base-1.0"
SDXL_REVISION = "462165984030d82259a11f4367a4eed129e94a7b"
CHECKPOINT_DOWNLOADS = {
    "Q": {
        "repo": SUPIR_MIRROR_REPO,
        "revision": SUPIR_MIRROR_REVISION,
        "filename": "v0Q.ckpt",
        "size": 5_329_810_432,
        "sha256": "d7f418398bb024d0d3c779c4ee4e9f171eb072306093f5bcfb2bf096aa2738f8",
    },
    "F": {
        "repo": SUPIR_MIRROR_REPO,
        "revision": SUPIR_MIRROR_REVISION,
        "filename": "v0F.ckpt",
        "size": 5_329_719_950,
        "sha256": "9d8906255e2a2cc97b52d95d575461eca2a8971647d5e3e763291965c3a35314",
    },
    "sdxl": {
        "repo": SDXL_REPO,
        "revision": SDXL_REVISION,
        "filename": "sd_xl_base_1.0_0.9vae.safetensors",
        "size": 6_938_078_334,
        "sha256": "e6bb9ea85bbf7bf6478a7c6d18b71246f22e95d41bcdd80ed40aa212c33cfeff",
    },
}
SUPIR_PACKAGES = (
    "torch==2.1.2",
    "torchvision==0.16.2",
    "transformers==4.28.1",
    "accelerate==0.18.0",
    "numpy==1.24.2",
    "Pillow==9.4.0",
    "requests==2.28.2",
    "tokenizers==0.13.3",
    "wandb==0.14.0",
    "scikit-learn==1.2.2",
    "scikit-image==0.20.0",
    "fsspec[http]==2023.4.0",
    "huggingface-hub==0.14.1",
    "matplotlib==3.7.1",
    "ninja==1.11.1",
    "pandas==2.0.1",
    "tqdm==4.65.0",
    "urllib3==1.26.15",
    "webdataset==0.2.48",
    "facexlib==0.3.0",
    "protobuf==3.20.3",
    "numba==0.57.0",
    "llvmlite==0.40.0",
    "torchmetrics==1.2.0",
    "lightning-utilities==0.10.0",
    "einops==0.7.0",
    "einops-exts==0.0.4",
    "timm==0.9.8",
    "openai-clip==1.0.1",
    "kornia==0.6.9",
    "omegaconf==2.3.0",
    "open-clip-torch==2.17.1",
    "opencv-python==4.7.0.72",
    "pytorch-lightning==2.1.2",
    "PyYAML==6.0.1",
    "scipy==1.9.3",
    "safetensors==0.4.5",
    "k-diffusion==0.1.1.post1",
    "diffusers==0.16.1",
    "xformers==0.0.23.post1",
    "sentencepiece==0.1.99",
)


def supir_root() -> Path:
    return PATHS.models_dir / "supir"


def source_dir() -> Path:
    return supir_root() / "source"


def checkpoint_path(kind: str) -> Path:
    names = {
        "Q": "SUPIR-v0Q.ckpt",
        "F": "SUPIR-v0F.ckpt",
        "sdxl": "sd_xl_base_1.0_0.9vae.safetensors",
    }
    try:
        return supir_root() / "checkpoints" / names[kind]
    except KeyError as exc:
        raise ValueError("SUPIR checkpoint kind must be Q, F, or sdxl") from exc


def runtime_dir() -> Path:
    return PATHS.data_dir / "model-runtimes" / "supir-python"


def dependency_dir(name: str) -> Path:
    return supir_root() / "dependencies" / name


def runtime_python() -> Path:
    return runtime_dir() / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def readiness() -> dict:
    return {
        "source": (source_dir() / "SUPIR" / "util.py").is_file(),
        "runtime": runtime_python().is_file() and (runtime_dir() / "runtime.json").is_file(),
        "v0Q": checkpoint_path("Q").is_file(),
        "v0F": checkpoint_path("F").is_file(),
        "sdxl": checkpoint_path("sdxl").is_file(),
        "llava": (dependency_dir("llava-v1.5-13b") / "config.json").is_file(),
        "llavaClip": (dependency_dir("clip-vit-large-patch14-336") / "config.json").is_file(),
        "sdxlClip1": (dependency_dir("clip-vit-large-patch14") / "config.json").is_file(),
        "sdxlClip2": any(dependency_dir("clip-bigG").glob("*.bin")),
    }


def is_model_installed() -> bool:
    status = readiness()
    return all(status[key] for key in ("source", "runtime", "v0Q", "sdxl"))


def cuda_compatible() -> bool:
    from backend.hardware.detector import get_hardware_profile
    from backend.hardware.policy import select_execution_policy

    return select_execution_policy(get_hardware_profile()).backend == "cuda"


def _bootstrap_python() -> str:
    configured = os.environ.get("MIDGARD_SUPIR_PYTHON", "").strip()
    candidates: list[str | Path] = [configured] if configured else []
    versions = ("3.10", "3.9", "3.8")
    candidates.extend(f"python{version}" for version in versions)
    home = Path.home()
    if os.name == "nt":
        local = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        for version in versions:
            candidates.extend(
                sorted(
                    (local / "uv" / "python").glob(f"cpython-{version}*-*/python.exe"), reverse=True
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
        if result.returncode == 0 and result.stdout.strip() in versions:
            return executable
    raise RuntimeError(
        "SUPIR requires Python 3.8–3.10. Install Python 3.10 or set MIDGARD_SUPIR_PYTHON."
    )


def _safe_extract(archive: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive) as opened:
        root = destination.resolve()
        for item in opened.infolist():
            target = (destination / item.filename).resolve()
            if root != target and root not in target.parents:
                raise RuntimeError("The SUPIR source archive contains an unsafe path.")
        opened.extractall(destination)


def _install_source() -> None:
    if readiness()["source"]:
        return
    supir_root().mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="midgard-supir-") as raw:
        staging = Path(raw)
        archive = staging / "source.zip"
        urllib.request.urlretrieve(SUPIR_SOURCE_URL, archive)  # noqa: S310 - pinned HTTPS URL
        extracted = staging / "extracted"
        extracted.mkdir()
        _safe_extract(archive, extracted)
        candidates = [item for item in extracted.iterdir() if item.is_dir()]
        if len(candidates) != 1 or not (candidates[0] / "SUPIR" / "util.py").is_file():
            raise RuntimeError("The official SUPIR source archive has an unexpected layout.")
        target = source_dir()
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(candidates[0], target)


def _install_runtime() -> None:
    if readiness()["runtime"]:
        return
    python = _bootstrap_python()
    target = runtime_dir()
    staging = target.with_name(".supir-python.staging")
    if staging.exists():
        shutil.rmtree(staging)
    staging.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(  # noqa: S603 - reviewed Python executable and fixed arguments
        [python, "-m", "venv", str(staging)], check=True, timeout=300
    )
    runtime = staging / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    subprocess.run(  # noqa: S603 - managed venv and policy-controlled package pins
        [str(runtime), "-m", "pip", "install", "--disable-pip-version-check", *SUPIR_PACKAGES],
        check=True,
        timeout=3600,
    )
    atomic_write_json(
        staging / "runtime.json",
        {
            "profile": "supir-python",
            "sourceCommit": SUPIR_COMMIT,
            "packages": list(SUPIR_PACKAGES),
            "managedBy": "midgard",
        },
    )
    if target.exists():
        shutil.rmtree(target)
    staging.replace(target)


def _install_huggingface_dependencies() -> None:
    from backend.tools.hf_auth import snapshot_download_with_progress

    clip_patterns = [
        "config.json",
        "merges.txt",
        "preprocessor_config.json",
        "pytorch_model.bin",
        "special_tokens_map.json",
        "tokenizer.json",
        "tokenizer_config.json",
        "vocab.json",
    ]
    dependencies = (
        (
            "liuhaotian/llava-v1.5-13b",
            "901a44b9113dea67b976e71f58d4e372cf9de81a",
            "llava-v1.5-13b",
            [
                "config.json",
                "generation_config.json",
                "mm_projector.bin",
                "pytorch_model-*.bin",
                "pytorch_model.bin.index.json",
                "special_tokens_map.json",
                "tokenizer.model",
                "tokenizer_config.json",
            ],
        ),
        (
            "openai/clip-vit-large-patch14-336",
            "ce19dc912ca5cd21c8a653c79e251e808ccabcd1",
            "clip-vit-large-patch14-336",
            clip_patterns,
        ),
        (
            "openai/clip-vit-large-patch14",
            "32bd64288804d66eefd0ccbe215aa642df71cc41",
            "clip-vit-large-patch14",
            clip_patterns,
        ),
        (
            "laion/CLIP-ViT-bigG-14-laion2B-39B-b160k",
            "743c27bd53dfe508a0ade0f50698f99b39d03bec",
            "clip-bigG",
            ["open_clip_pytorch_model.bin"],
        ),
    )
    for repo, revision, name, allow_patterns in dependencies:
        target = dependency_dir(name)
        snapshot_download_with_progress(
            repo_id=repo,
            revision=revision,
            local_dir=str(target),
            allow_patterns=allow_patterns,
        )


def _checkpoint_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_checkpoint(path: Path, kind: str) -> None:
    try:
        expected = CHECKPOINT_DOWNLOADS[kind]
    except KeyError as exc:
        raise ValueError("SUPIR checkpoint kind must be Q, F, or sdxl") from exc
    actual_size = path.stat().st_size
    if actual_size != expected["size"]:
        raise ValueError(
            f"{path.name} has an unexpected size ({actual_size} bytes); expected {expected['size']}."
        )
    actual_digest = _checkpoint_digest(path)
    if actual_digest != expected["sha256"]:
        raise ValueError(f"{path.name} failed SHA-256 verification and was not installed.")


def download_checkpoint(kind: str) -> Path:
    from backend.tools.hf_auth import snapshot_download_with_progress

    try:
        download = CHECKPOINT_DOWNLOADS[kind]
    except KeyError as exc:
        raise ValueError("SUPIR checkpoint kind must be Q, F, or sdxl") from exc
    destination = checkpoint_path(kind)
    if destination.is_file():
        _verify_checkpoint(destination, kind)
        return destination
    staging = supir_root() / ".downloads" / kind
    snapshot_download_with_progress(
        repo_id=str(download["repo"]),
        revision=str(download["revision"]),
        local_dir=str(staging),
        allow_patterns=[str(download["filename"])],
    )
    downloaded = staging / str(download["filename"])
    if not downloaded.is_file():
        raise RuntimeError(f"Hugging Face did not provide {download['filename']}.")
    _verify_checkpoint(downloaded, kind)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    downloaded.replace(temporary)
    temporary.replace(destination)
    shutil.rmtree(staging, ignore_errors=True)
    return destination


def import_checkpoint(source: Path, kind: str) -> Path:
    source = source.expanduser().resolve()
    if not source.is_file() or source.stat().st_size <= 0:
        raise FileNotFoundError(source)
    expected_suffix = ".safetensors" if kind == "sdxl" else ".ckpt"
    if source.suffix.lower() != expected_suffix:
        raise ValueError(f"Choose a {expected_suffix} file for {kind}.")
    _verify_checkpoint(source, kind)
    destination = checkpoint_path(kind)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    shutil.copy2(source, temporary)
    temporary.replace(destination)
    return destination


def install_model() -> None:
    if not readiness()["runtime"]:
        _bootstrap_python()
    for kind in ("Q", "F", "sdxl"):
        download_checkpoint(kind)
    _install_source()
    _install_runtime()
    _install_huggingface_dependencies()


def uninstall_model() -> None:
    if supir_root().exists():
        shutil.rmtree(supir_root())
    if runtime_dir().exists():
        shutil.rmtree(runtime_dir())
