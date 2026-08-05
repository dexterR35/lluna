"""Official BiRefNet inference for image cut-outs and video foregrounds."""

from __future__ import annotations

import contextlib
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

from PIL import Image, ImageColor, ImageFilter

from backend.tools.birefnet_models import is_model_installed, model_dir

_MODELS: dict[str, tuple[object, str, object]] = {}


def _device(torch):
    if torch.cuda.is_available():
        return torch.device("cuda")
    mps = getattr(torch.backends, "mps", None)
    if mps is not None and mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def _load(model_id: str, model_path: str | None = None, precision: str = "auto"):
    cache_key = f"{model_id}:{model_path or ''}:{precision}"
    cached = _MODELS.get(cache_key)
    if cached is not None:
        return cached
    root = Path(model_path) if model_path else model_dir(model_id)
    installed = (
        (root / "config.json").is_file()
        and bool(tuple(root.glob("*.safetensors")) + tuple(root.glob("*.bin")))
        if model_path
        else is_model_installed(model_id)
    )
    if not installed:
        raise RuntimeError(f"BiRefNet model '{model_id}' is not installed. Install it in Settings → Models.")
    try:
        import torch
        from transformers import AutoModelForImageSegmentation
    except ImportError as exc:
        raise RuntimeError(
            "BiRefNet needs PyTorch, Transformers, timm, kornia, and torchvision. "
            "Install the BiRefNet runtime from the Lluna installer."
        ) from exc
    device = _device(torch)
    requested = str(precision or "auto").lower()
    use_fp16 = device.type == "cuda" and requested in {"auto", "fp16"}
    dtype = torch.float16 if use_fp16 else torch.float32
    model = AutoModelForImageSegmentation.from_pretrained(
        str(root),
        trust_remote_code=True,
        local_files_only=True,
    )
    model = model.to(device)
    # Some official checkpoints advertise fp16 in their config. CPU kernels do
    # not consistently support half-precision convolutions, so keep CPU/MPS
    # inference in fp32 and reserve autocast fp16 for CUDA.
    if dtype == torch.float16:
        model = model.half()
    else:
        model = model.float()
    model = model.eval()
    value = (model, device, dtype)
    _MODELS[cache_key] = value
    return value


def release_models() -> None:
    values = tuple(_MODELS.values())
    _MODELS.clear()
    for model, _device_value, _dtype in values:
        del model
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass


def _predict_mask(model_id: str, image: Image.Image, resolution: int, model_path: str | None = None, precision: str = "auto") -> Image.Image:
    import torch
    from torchvision import transforms

    model, device, dtype = _load(model_id, model_path, precision)
    source = image.convert("RGB")
    width, height = source.size
    side = max(256, min(2304, int(resolution)))
    tensor = transforms.Compose(
        [
            transforms.Resize((side, side), interpolation=transforms.InterpolationMode.BILINEAR),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ]
    )(source).unsqueeze(0).to(device)
    autocast = torch.autocast(device_type="cuda", dtype=dtype) if device.type == "cuda" and dtype != torch.float32 else contextlib.nullcontext()
    with torch.no_grad(), autocast:
        output = model(tensor)
        if isinstance(output, (tuple, list)):
            output = output[-1]
        elif hasattr(output, "logits"):
            output = output.logits
        if output.ndim == 3:
            output = output.unsqueeze(1)
        mask = torch.sigmoid(output.float())
        mask = torch.nn.functional.interpolate(
            mask[:, :1], size=(height, width), mode="bilinear", align_corners=True
        )[0, 0]
    values = (mask.clamp(0, 1).cpu().numpy() * 255).astype("uint8")
    return Image.fromarray(values, mode="L")


def _alpha_mask(mask: Image.Image, threshold: float, feather: int) -> Image.Image:
    value = max(0.0, min(1.0, float(threshold)))
    if value > 0:
        # Keep a soft ramp so matting models retain hair and fur detail.
        mask = mask.point(lambda pixel: max(0, min(255, int((pixel / 255 - value) / max(1e-6, 1 - value) * 255))))
    if feather > 0:
        mask = mask.filter(ImageFilter.GaussianBlur(radius=min(32, int(feather))))
    return mask


def _background(params: dict) -> tuple[int, int, int]:
    mode = str(params.get("output_mode") or params.get("outputMode") or "transparent")
    if mode == "white":
        return (255, 255, 255)
    if mode == "black":
        return (0, 0, 0)
    try:
        return ImageColor.getrgb(str(params.get("background_color") or params.get("backgroundColor") or "#ffffff"))
    except ValueError:
        return (255, 255, 255)


def process_image(
    input_path: str,
    output_path: str,
    *,
    model_id: str,
    resolution: int = 1024,
    threshold: float = 0.5,
    feather: int = 0,
    output_mode: str = "transparent",
    background_color: str = "#ffffff",
    model_path: str | None = None,
    precision: str = "auto",
    mask_output_path: str | None = None,
    alpha_output_path: str | None = None,
) -> None:
    source = Image.open(input_path).convert("RGB")
    raw_mask = _predict_mask(model_id, source, resolution, model_path, precision)
    mask = _alpha_mask(raw_mask, threshold, feather)
    if mask_output_path:
        Path(mask_output_path).parent.mkdir(parents=True, exist_ok=True)
        raw_mask.save(mask_output_path, format="PNG")
    if alpha_output_path:
        Path(alpha_output_path).parent.mkdir(parents=True, exist_ok=True)
        mask.save(alpha_output_path, format="PNG")
    if output_mode == "transparent":
        result = source.convert("RGBA")
        result.putalpha(mask)
    else:
        result = Image.new("RGB", source.size, _background({"output_mode": output_mode, "background_color": background_color}))
        result.paste(source, mask=mask)
    result.save(output_path, format="PNG")


def _run_ffmpeg(args: list[str]) -> None:
    from backend.tools.ffmpeg_cli import FFmpegCLI

    completed = subprocess.run(
        [FFmpegCLI.instance().ffmpeg_path, "-y", *args],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode:
        detail = completed.stderr.decode("utf-8", errors="replace")[-800:]
        raise RuntimeError(f"FFmpeg video encoding failed: {detail}")


def process_video(
    input_path: str,
    output_path: str,
    *,
    model_id: str,
    resolution: int = 1024,
    threshold: float = 0.5,
    feather: int = 0,
    output_mode: str = "transparent",
    background_color: str = "#ffffff",
    model_path: str | None = None,
    precision: str = "auto",
    progress: Callable[[int], None] | None = None,
    cancel_event=None,
) -> None:
    import cv2
    import numpy as np

    capture = cv2.VideoCapture(input_path)
    if not capture.isOpened():
        raise RuntimeError(f"Could not open video: {input_path}")
    fps = float(capture.get(cv2.CAP_PROP_FPS) or 30.0)
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total = max(0, int(capture.get(cv2.CAP_PROP_FRAME_COUNT)))
    if width <= 0 or height <= 0:
        capture.release()
        raise RuntimeError("Video has invalid dimensions.")
    transparent = output_mode == "transparent"
    raw_suffix = ".mov" if transparent else ".mp4"
    with tempfile.TemporaryDirectory(prefix="lluna-birefnet-video-") as temp_dir:
        raw_path = str(Path(temp_dir) / f"foreground{raw_suffix}")
        pixel_format = "rgba" if transparent else "bgr24"
        codec_args = ["-c:v", "qtrle", "-pix_fmt", "argb"] if transparent else ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "fast"]
        from backend.tools.ffmpeg_cli import FFmpegCLI

        encoder = subprocess.Popen(
            [FFmpegCLI.instance().ffmpeg_path, "-y", "-f", "rawvideo", "-pix_fmt", pixel_format, "-s", f"{width}x{height}", "-r", str(fps), "-i", "-", *codec_args, "-an", raw_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        index = 0
        try:
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    raise RuntimeError("__cancelled__")
                ok, frame = capture.read()
                if not ok:
                    break
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                image = Image.fromarray(rgb, mode="RGB")
                mask = _alpha_mask(_predict_mask(model_id, image, resolution, model_path, precision), threshold, feather)
                if transparent:
                    rgba = np.asarray(image.convert("RGBA"))
                    rgba[:, :, 3] = np.asarray(mask)
                    encoder.stdin.write(rgba.tobytes())
                else:
                    background = Image.new("RGB", image.size, _background({"output_mode": output_mode, "background_color": background_color}))
                    background.paste(image, mask=mask)
                    bgr = cv2.cvtColor(np.asarray(background), cv2.COLOR_RGB2BGR)
                    encoder.stdin.write(bgr.tobytes())
                index += 1
                if progress and total:
                    progress(min(98, int(index * 98 / total)))
        finally:
            capture.release()
            if encoder.stdin:
                encoder.stdin.close()
            encoder.wait(timeout=600)
        if encoder.returncode:
            detail = (encoder.stderr.read() if encoder.stderr else b"").decode("utf-8", errors="replace")[-800:]
            raise RuntimeError(f"BiRefNet video encoding failed: {detail}")
        # Keep source audio for ordinary video output and for players that support
        # audio alongside transparent MOV. A silent output remains valid if muxing fails.
        try:
            _run_ffmpeg(["-i", raw_path, "-i", input_path, "-map", "0:v:0", "-map", "1:a?", "-c:v", "copy", "-c:a", "aac", "-shortest", output_path])
        except RuntimeError:
            os.replace(raw_path, output_path)
    if progress:
        progress(100)
