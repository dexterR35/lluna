"""Strip PaddleX CDN model-hoster connectivity (Midgard ships PP-OCR locally).

PaddleX builds ``official_models`` at import time and probes HuggingFace / BOS /
ModelScope / AIStudio. Midgard always passes ``model_dir`` under
``backend/models/V5/``, so that probe is removed — not merely env-disabled.
"""

from __future__ import annotations

import importlib.abc
import importlib.util
import sys
from pathlib import Path

_PATCHED = False
_TARGET = "paddlex.inference.utils.official_models"


def _build_hosters_local_only(self):
    """Register hoster classes without any network / healthcheck."""
    import paddlex.inference.utils.official_models as om

    hosters = []
    for hoster_cls in self.hoster_candidates:
        hoster = hoster_cls(self._save_dir)
        if hoster_cls.alias == om.MODEL_SOURCE:
            hosters.insert(0, hoster)
        else:
            hosters.append(hoster)
    return hosters


def _apply_to_module(mod) -> None:
    mod._ModelManager._build_hosters = _build_hosters_local_only
    mod._BaseModelHoster.is_available = classmethod(lambda cls: True)
    # Rebuild singleton without CDN probe (or first create if we deferred it)
    mod.official_models = mod._ModelManager()


class _OfficialModelsLoader(importlib.abc.Loader):
    def __init__(self, origin: str):
        self.origin = origin

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        source = Path(self.origin).read_text(encoding="utf-8")
        # Defer singleton so we can replace _build_hosters first
        source = source.replace(
            "official_models = _ModelManager()",
            "official_models = None  # Midgard: created after CDN strip",
            1,
        )
        exec(compile(source, self.origin, "exec"), module.__dict__)
        _apply_to_module(module)


class _OfficialModelsFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname != _TARGET:
            return None
        if fullname in sys.modules:
            return None
        # Resolve file via parent package path
        try:
            import paddlex.inference.utils as parent
        except Exception:
            return None
        origin = str(Path(parent.__path__[0]) / "official_models.py")
        if not Path(origin).is_file():
            return None
        return importlib.util.spec_from_file_location(
            fullname,
            origin,
            loader=_OfficialModelsLoader(origin),
            submodule_search_locations=None,
        )


def strip_paddle_cdn_hoster_check() -> None:
    """Remove PaddleX model-hoster CDN connectivity check (call before paddleocr)."""
    global _PATCHED
    if _PATCHED:
        return

    # If already imported (e.g. earlier in process), strip in place
    if _TARGET in sys.modules:
        _apply_to_module(sys.modules[_TARGET])
        _PATCHED = True
        return

    # Intercept first import so _ModelManager never runs the CDN probe
    if not any(isinstance(f, _OfficialModelsFinder) for f in sys.meta_path):
        sys.meta_path.insert(0, _OfficialModelsFinder())

    _PATCHED = True
