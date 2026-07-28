"""Video capture/writer lifecycle used by processing pipelines."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from backend.diagnostics.errors import InvalidMediaError, OutputWriteError


@dataclass(frozen=True)
class VideoMetadata:
    frame_count: int
    fps: float
    width: int
    height: int

    def __post_init__(self) -> None:
        if self.frame_count < 0:
            raise InvalidMediaError("Video frame count cannot be negative.")
        if self.fps <= 0 or self.width <= 0 or self.height <= 0:
            raise InvalidMediaError(
                f"Invalid video dimensions or frame rate: "
                f"{self.width}x{self.height} at {self.fps} fps"
            )

    @property
    def size(self) -> tuple[int, int]:
        return self.width, self.height


class VideoSource:
    def __init__(self, capture: Any, metadata: VideoMetadata) -> None:
        self.capture = capture
        self.metadata = metadata
        self._closed = False

    @classmethod
    def open(
        cls,
        path: str,
        *,
        capture_factory: Callable[[str], Any] | None = None,
    ) -> "VideoSource":
        import cv2

        factory = capture_factory or cv2.VideoCapture
        capture = factory(path)
        if not capture.isOpened():
            capture.release()
            raise InvalidMediaError(f"Could not open media: {path}")
        try:
            metadata = VideoMetadata(
                frame_count=int(capture.get(cv2.CAP_PROP_FRAME_COUNT) + 0.5),
                fps=float(capture.get(cv2.CAP_PROP_FPS)),
                width=int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)),
                height=int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            )
        except BaseException:
            capture.release()
            raise
        return cls(capture, metadata)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.capture.release()

    def __enter__(self) -> "VideoSource":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()


def create_video_writer(path: str, fps: float, size: tuple[int, int]):
    """Prefer FFmpeg/libx264, with a validated OpenCV fallback."""
    import cv2

    from backend.tools.common_tools import get_readable_path
    from backend.tools.video_io import FFmpegVideoWriter

    try:
        return FFmpegVideoWriter(get_readable_path(path), fps, size)
    except (OSError, RuntimeError, ValueError):
        writer = cv2.VideoWriter(
            get_readable_path(path),
            cv2.VideoWriter_fourcc(*"mp4v"),
            fps,
            size,
        )
        if hasattr(writer, "isOpened") and not writer.isOpened():
            writer.release()
            raise OutputWriteError(f"Could not create video output: {path}")
        return writer
