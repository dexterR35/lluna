import argparse
from pathlib import Path

from .constant import BgRemoveMode, InpaintMode


def _bg_model_choices():
    return [mode.value for mode in BgRemoveMode]


def _inpaint_mode_choices():
    return [mode.name.lower().replace("_", "-") for mode in InpaintMode]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Midgard Command Line Tool"
    )
    parser.add_argument(
        "--task", "-t",
        type=str,
        default="remove-text",
        choices=["remove-text", "remove-bg"],
        help="Task to run: remove-text (default) or remove-bg (images only)",
    )
    parser.add_argument(
        "--input", "-i", required=True, type=str,
        help="Input file path (video/image for remove-text; image for remove-bg)",
    )
    parser.add_argument(
        "--output", "-o", required=False, type=str, default=None,
        help="Output file path (optional)",
    )
    parser.add_argument(
        "--subtitle-area-coords", "-c", action="append", nargs=4, type=int,
        metavar=("YMIN", "YMAX", "XMIN", "XMAX"),
        help="Subtitle area coordinates (ymin ymax xmin xmax). "
             "Can be specified multiple times for multiple areas. (remove-text)",
    )
    parser.add_argument(
        "--inpaint-mode", type=str, default="sttn-auto",
        choices=_inpaint_mode_choices(),
        help="Inpaint mode for remove-text, default is sttn-auto",
    )
    parser.add_argument(
        "--bg-model", type=str, default=BgRemoveMode.BIREFNET.value,
        choices=_bg_model_choices(),
        help="Background-removal model for remove-bg, "
             f"default is {BgRemoveMode.BIREFNET.value}",
    )
    parser.add_argument(
        "--protect-mask", type=str, default=None,
        help="Optional grayscale mask path: painted areas stay opaque after cutout (remove-bg)",
    )
    args = parser.parse_args()
    args.inpaint_mode = InpaintMode[args.inpaint_mode.replace("-", "_").upper()]
    args.bg_model = BgRemoveMode(args.bg_model)
    if args.subtitle_area_coords is None:
        args.subtitle_area_coords = []
    if args.output is None:
        args.output = _default_output(args.input, args.task)
    return args


def _default_output(input_path: str, task: str) -> str:
    path = Path(input_path)
    parent = path.parent
    if task == "remove-bg":
        return str(parent / f"{path.stem}_nobg.png")
    if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}:
        return str(parent / "no_sub" / f"{path.stem}{path.suffix}")
    return str(parent / f"{path.stem}_no_sub.mp4")
