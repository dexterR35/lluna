"""Deprecated compatibility adapter for subtitle model paths."""

class ModelConfig:
    def __init__(self, settings=None):
        if settings is None:
            from backend.configuration.service import get_settings

            settings = get_settings().subtitle
        from backend.models.paths import (
            SubtitleModelPaths,
            prepare_bundled_subtitle_models,
        )

        resolved = SubtitleModelPaths.resolve(settings)
        prepare_bundled_subtitle_models(resolved)
        self.LAMA_MODEL_DIR = str(resolved.lama_dir)
        self.STTN_AUTO_MODEL_PATH = str(resolved.sttn_auto_path)
        self.STTN_DET_MODEL_PATH = str(resolved.sttn_detection_path)
        self.PROPAINTER_MODEL_DIR = str(resolved.propainter_dir)
        self.DET_MODEL_DIR = str(resolved.detection_dir)
        self.DET_MODEL_NAME = resolved.detection_model_name
