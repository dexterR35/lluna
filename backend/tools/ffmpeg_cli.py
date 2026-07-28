import logging
import stat

import platform
from pathlib import Path

from backend.core.paths import PATHS
from backend.diagnostics.errors import DependencyError
from .common_tools import merge_big_file_if_not_exists

logger = logging.getLogger(__name__)


def resolve_ffmpeg_path(base_dir: str | Path, system: str) -> Path:
    root = Path(base_dir)
    if system == "Windows":
        return root / "win_x64" / "ffmpeg.exe"
    if system == "Linux":
        return root / "linux_x64" / "ffmpeg"
    if system == "Darwin":
        return root / "macos" / "ffmpeg"
    raise DependencyError(f"FFmpeg is not bundled for {system}.")

class FFmpegCLI:
    
    """
    FFmpeg CLI singleton that resolves the platform-specific ffmpeg binary path
    """
    _instance = None
    
    @classmethod
    def instance(cls):
        """Get singleton instance"""
        if cls._instance is None:
            cls._instance = FFmpegCLI()
        return cls._instance
    
    def __init__(self):
        path = Path(self.ffmpeg_path)
        if not path.is_file():
            raise DependencyError(f"FFmpeg executable is missing: {path}")
        if platform.system() != "Windows":
            try:
                path.chmod(path.stat().st_mode | stat.S_IXUSR)
            except OSError as exc:
                logger.warning(
                    "Could not mark FFmpeg executable: %s", type(exc).__name__
                )
        
    @property
    def ffmpeg_path(self):
        system = platform.system()
        ffmpeg_root = PATHS.project_root / "backend" / "ffmpeg"
        if system == "Windows":
            directory = ffmpeg_root / "win_x64"
            merge_big_file_if_not_exists(str(directory), "ffmpeg.exe")
        return str(resolve_ffmpeg_path(ffmpeg_root, system))
