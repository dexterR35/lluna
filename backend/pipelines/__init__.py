"""Feature pipelines used by the local inference worker."""

from backend.pipelines.subtitle import SubtitleRemover

__all__ = ["SubtitleRemover"]
