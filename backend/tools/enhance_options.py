"""Enhance pipeline options (denoise before Real-ESRGAN)."""

from __future__ import annotations

from dataclasses import dataclass

from backend.tools.constant import DenoiseStrength


@dataclass(frozen=True)
class EnhanceOptions:
    """Optional pre/post stages around Real-ESRGAN upscale."""

    denoise: bool = False
    denoise_strength: DenoiseStrength = DenoiseStrength.SAFE
    max_long_edge: int = 0
    tile_size: int = 0

    @classmethod
    def from_config(cls) -> "EnhanceOptions":
        from backend.config import config

        enabled = bool(config.enhanceDenoiseEnabled.value)
        raw = config.enhanceDenoiseStrength.value
        try:
            strength = (
                raw
                if isinstance(raw, DenoiseStrength)
                else DenoiseStrength(str(raw))
            )
        except (TypeError, ValueError):
            strength = DenoiseStrength.SAFE
        try:
            max_long_edge = int(config.enhanceMaxLongEdge.value)
        except (TypeError, ValueError):
            max_long_edge = 0
        return cls(
            denoise=enabled,
            denoise_strength=strength,
            max_long_edge=max_long_edge,
        )

    @classmethod
    def from_payload(cls, payload: dict) -> "EnhanceOptions":
        denoise = bool(payload.get("denoise", False))
        raw = payload.get("denoise_strength", DenoiseStrength.SAFE.value)
        try:
            strength = DenoiseStrength(str(raw))
        except ValueError:
            strength = DenoiseStrength.SAFE
        effective = payload.get("effective_settings") or {}
        try:
            max_long_edge = int(effective.get("max_long_edge") or 0)
            tile_size = int(effective.get("tile_size") or 0)
        except (TypeError, ValueError):
            max_long_edge = tile_size = 0
        return cls(
            denoise=denoise,
            denoise_strength=strength,
            max_long_edge=max_long_edge,
            tile_size=tile_size,
        )
