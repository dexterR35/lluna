"""Standalone entry point executed inside Lluna's isolated BiRefNet environment.

Runs one full image or video job per invocation (mirrors supir_process.py's
contract) so ``trust_remote_code=True`` custom modeling code from the
downloaded HF snapshot never executes inside the main app's process or
dependency environment.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def _device(torch):
    if torch.cuda.is_available():
        return torch.device("cuda")
    mps = getattr(torch.backends, "mps", None)
    if mps is not None and mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def _load(root: Path, precision: str):
    import torch
    from transformers import AutoModelForImageSegmentation

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
    model = model.half() if dtype == torch.float16 else model.float()
    return model.eval(), device, dtype


def _predict_mask(model, device, dtype, image, resolution: int):
    import torch
    from torchvision import transforms

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
    autocast = (
        torch.autocast(device_type="cuda", dtype=dtype)
        if device.type == "cuda" and dtype != torch.float32
        else contextlib.nullcontext()
    )
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
    from PIL import Image

    values = (mask.clamp(0, 1).cpu().numpy() * 255).astype("uint8")
    return Image.fromarray(values, mode="L")


def _alpha_mask(mask, threshold: float, feather: int):
    from PIL import ImageFilter

    value = max(0.0, min(1.0, float(threshold)))
    if value > 0:
        # Keep a soft ramp so matting models retain hair and fur detail.
        mask = mask.point(lambda pixel: max(0, min(255, int((pixel / 255 - value) / max(1e-6, 1 - value) * 255))))
    if feather > 0:
        mask = mask.filter(ImageFilter.GaussianBlur(radius=min(32, int(feather))))
    return mask


def _background(output_mode: str, background_color: str):
    from PIL import ImageColor

    if output_mode == "white":
        return (255, 255, 255)
    if output_mode == "black":
        return (0, 0, 0)
    try:
        return ImageColor.getrgb(str(background_color or "#ffffff"))
    except ValueError:
        return (255, 255, 255)


def _process_image(request: dict, model, device, dtype) -> None:
    from PIL import Image

    source = Image.open(request["input_path"]).convert("RGB")
    raw_mask = _predict_mask(model, device, dtype, source, request["resolution"])
    mask = _alpha_mask(raw_mask, request["threshold"], request["feather"])
    if request.get("mask_output_path"):
        Path(request["mask_output_path"]).parent.mkdir(parents=True, exist_ok=True)
        raw_mask.save(request["mask_output_path"], format="PNG")
    if request.get("alpha_output_path"):
        Path(request["alpha_output_path"]).parent.mkdir(parents=True, exist_ok=True)
        mask.save(request["alpha_output_path"], format="PNG")
    output_mode = request["output_mode"]
    if output_mode == "transparent":
        result = source.convert("RGBA")
        result.putalpha(mask)
    else:
        result = Image.new(
            "RGB", source.size, _background(output_mode, request["background_color"])
        )
        result.paste(source, mask=mask)
    result.save(request["output_path"], format="PNG")


def _run_ffmpeg(ffmpeg_path: str, args: list[str]) -> None:
    completed = subprocess.run(  # noqa: S603 - managed ffmpeg path and fixed argv
        [ffmpeg_path, "-y", *args],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode:
        detail = completed.stderr.decode("utf-8", errors="replace")[-800:]
        raise RuntimeError(f"FFmpeg video encoding failed: {detail}")


def _process_video(request: dict, model, device, dtype) -> None:
    import cv2
    import numpy as np
    from PIL import Image

    ffmpeg_path = request["ffmpeg_path"]
    input_path = request["input_path"]
    output_path = request["output_path"]
    resolution = request["resolution"]
    threshold = request["threshold"]
    feather = request["feather"]
    output_mode = request["output_mode"]
    background_color = request["background_color"]

    capture = cv2.VideoCapture(input_path)
    if not capture.isOpened():
        raise RuntimeError(f"Could not open video: {input_path}")
    fps = float(capture.get(cv2.CAP_PROP_FPS) or 30.0)
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if width <= 0 or height <= 0:
        capture.release()
        raise RuntimeError("Video has invalid dimensions.")
    transparent = output_mode == "transparent"
    raw_suffix = ".mov" if transparent else ".mp4"
    with tempfile.TemporaryDirectory(prefix="lluna-birefnet-video-") as temp_dir:
        raw_path = str(Path(temp_dir) / f"foreground{raw_suffix}")
        pixel_format = "rgba" if transparent else "bgr24"
        codec_args = (
            ["-c:v", "qtrle", "-pix_fmt", "argb"]
            if transparent
            else ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "fast"]
        )
        encoder = subprocess.Popen(  # noqa: S603 - managed ffmpeg path and fixed argv
            [
                ffmpeg_path, "-y", "-f", "rawvideo", "-pix_fmt", pixel_format,
                "-s", f"{width}x{height}", "-r", str(fps), "-i", "-",
                *codec_args, "-an", raw_path,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        try:
            while True:
                ok, frame = capture.read()
                if not ok:
                    break
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                image = Image.fromarray(rgb, mode="RGB")
                mask = _alpha_mask(
                    _predict_mask(model, device, dtype, image, resolution), threshold, feather
                )
                if transparent:
                    rgba = np.asarray(image.convert("RGBA"))
                    rgba[:, :, 3] = np.asarray(mask)
                    encoder.stdin.write(rgba.tobytes())
                else:
                    background = Image.new(
                        "RGB", image.size, _background(output_mode, background_color)
                    )
                    background.paste(image, mask=mask)
                    bgr = cv2.cvtColor(np.asarray(background), cv2.COLOR_RGB2BGR)
                    encoder.stdin.write(bgr.tobytes())
        finally:
            capture.release()
            if encoder.stdin:
                encoder.stdin.close()
            encoder.wait(timeout=600)
        if encoder.returncode:
            detail = (encoder.stderr.read() if encoder.stderr else b"").decode(
                "utf-8", errors="replace"
            )[-800:]
            raise RuntimeError(f"BiRefNet video encoding failed: {detail}")
        # Keep source audio for ordinary video output and for players that support
        # audio alongside transparent MOV. A silent output remains valid if muxing fails.
        try:
            _run_ffmpeg(
                ffmpeg_path,
                ["-i", raw_path, "-i", input_path, "-map", "0:v:0", "-map", "1:a?",
                 "-c:v", "copy", "-c:a", "aac", "-shortest", output_path],
            )
        except RuntimeError:
            import os

            os.replace(raw_path, output_path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    args = parser.parse_args()
    request = json.loads(Path(args.request).read_text(encoding="utf-8"))
    root = Path(request["model_root"]).resolve()
    model, device, dtype = _load(root, request.get("precision", "auto"))
    if request["job"] == "video":
        _process_video(request, model, device, dtype)
    else:
        _process_image(request, model, device, dtype)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
