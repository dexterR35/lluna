"""Deprecated compatibility facade.

Midgard no longer exposes a public media-processing CLI. Import reusable
pipeline services from :mod:`backend.pipelines` in new code.
"""

from backend.pipelines.subtitle import SubtitleRemover

__all__ = ["SubtitleRemover"]
