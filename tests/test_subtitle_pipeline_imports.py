"""Regression tests for names used by the subtitle pipeline."""

import ast
from pathlib import Path


def test_subtitle_detector_module_imports():
    from backend.tools.media.subtitles import SubtitleDetect

    assert SubtitleDetect.__name__ == "SubtitleDetect"


def test_subtitle_pipeline_imports_is_image_file():
    pipeline_path = Path(__file__).resolve().parents[1] / "backend" / "pipelines" / "subtitle.py"
    module = ast.parse(pipeline_path.read_text(encoding="utf-8"))

    common_tools_imports = {
        alias.name
        for node in module.body
        if isinstance(node, ast.ImportFrom) and node.module == "backend.tools.media.common"
        for alias in node.names
    }

    assert "is_image_file" in common_tools_imports
