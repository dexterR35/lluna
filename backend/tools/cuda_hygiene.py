"""CUDA allocator hygiene for inference workers."""

from __future__ import annotations

import gc
import os


def ensure_expandable_segments() -> None:
    """Prefer expandable CUDA allocator segments when not already configured."""
    key = "PYTORCH_CUDA_ALLOC_CONF"
    current = os.environ.get(key, "")
    if "expandable_segments" in current:
        return
    if current:
        os.environ[key] = f"{current},expandable_segments:True"
    else:
        os.environ[key] = "expandable_segments:True"


def empty_cuda_cache() -> None:
    """Best-effort free of cached CUDA blocks + Python GC."""
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            try:
                torch.cuda.empty_cache()
            except Exception:
                pass
    except Exception:
        pass
