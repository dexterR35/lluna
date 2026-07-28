"""Resolved model artifact paths, separate from model preparation policy."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend.configuration.models import SubtitleSettings
from backend.core.paths import PATHS, AppPaths


@dataclass(frozen=True)
class SubtitleModelPaths:
    lama_dir: Path
    sttn_auto_path: Path
    sttn_detection_path: Path
    propainter_dir: Path
    detection_dir: Path
    detection_model_name: str

    @classmethod
    def resolve(
        cls,
        settings: SubtitleSettings,
        paths: AppPaths = PATHS,
    ) -> "SubtitleModelPaths":
        detection_fast = settings.subtitle_detect_mode == "PP_OCRv5_MOBILE"
        return cls(
            lama_dir=paths.models_dir / "big-lama",
            sttn_auto_path=paths.models_dir / "sttn-auto" / "infer_model.pth",
            sttn_detection_path=paths.models_dir / "sttn-det" / "sttn.pth",
            propainter_dir=paths.models_dir / "propainter",
            detection_dir=paths.models_dir
            / "V5"
            / ("ch_det_fast" if detection_fast else "ch_det"),
            detection_model_name=(
                "PP-OCRv5_mobile_det"
                if detection_fast
                else "PP-OCRv5_server_det"
            ),
        )


def prepare_bundled_subtitle_models(paths: SubtitleModelPaths) -> None:
    """Merge repository-shipped chunks explicitly before model loading."""
    from backend.tools.common_tools import merge_big_file_if_not_exists

    merge_big_file_if_not_exists(str(paths.lama_dir), "big-lama.pt")
    merge_big_file_if_not_exists(str(paths.propainter_dir), "ProPainter.pth")
