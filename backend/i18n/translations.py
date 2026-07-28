"""Validated translation catalog loading without Qt."""

from __future__ import annotations

import configparser
from functools import lru_cache
from pathlib import Path

from backend.core.paths import PATHS
from backend.diagnostics.errors import ConfigurationError


def load_translations(path: str | Path = PATHS.translation_file) -> configparser.ConfigParser:
    source = Path(path)
    parser = configparser.ConfigParser(interpolation=None)
    try:
        loaded = parser.read(source, encoding="utf-8")
    except (OSError, UnicodeError, configparser.Error) as exc:
        raise ConfigurationError(
            f"Could not load translations from {source}: {type(exc).__name__}"
        ) from exc
    if not loaded:
        raise ConfigurationError(f"Translation file is missing: {source}")
    required = {"Main", "InpaintMode", "SubtitleDetectMode"}
    missing = sorted(required.difference(parser.sections()))
    if missing:
        raise ConfigurationError(
            "Translation file is missing sections: " + ", ".join(missing)
        )
    return parser


@lru_cache(maxsize=1)
def get_translations() -> configparser.ConfigParser:
    return load_translations()
