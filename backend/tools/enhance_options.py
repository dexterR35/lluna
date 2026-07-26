"""Enhance pipeline options (denoise before Real-ESRGAN)."""

from __future__ import annotations

from dataclasses import dataclass

from backend.tools.constant import DenoiseStrength


@dataclass(frozen=True)
class EnhanceOptions:
    """Optional pre/post stages around Real-ESRGAN upscale."""

    denoise: bool = False
    denoise_strength: DenoiseStrength = DenoiseStrength.SAFE

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
        return cls(denoise=enabled, denoise_strength=strength)

    @classmethod
    def from_payload(cls, payload: dict) -> "EnhanceOptions":
        denoise = bool(payload.get("denoise", False))
        raw = payload.get("denoise_strength", DenoiseStrength.SAFE.value)
        try:
            strength = DenoiseStrength(str(raw))
        except ValueError:
            strength = DenoiseStrength.SAFE
        return cls(denoise=denoise, denoise_strength=strength)
