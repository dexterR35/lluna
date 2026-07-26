"""Risk levels for numeric settings when values move away from app defaults."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional, Tuple

RiskLevel = Literal["none", "caution", "high"]


@dataclass(frozen=True)
class SettingRiskProfile:
    """How to score risk relative to ``defaultValue``."""

    higher_is_risky: bool = True
    caution_at: float = 0.22
    high_at: float = 0.50


DEFAULT_HIGHER = SettingRiskProfile()
VRAM_HEAVY = SettingRiskProfile(caution_at=0.12, high_at=0.30)
LOWER_IS_RISKY = SettingRiskProfile(higher_is_risky=False, caution_at=0.22, high_at=0.50)

_PROFILES: dict[str, SettingRiskProfile] = {
    "Main.SubtitleYXAxisDifferencePixel": DEFAULT_HIGHER,
    "Main.SubtitleAreaDeviationPixel": DEFAULT_HIGHER,
    "Main.SubtitleAreaYAxisDifferencePixel": DEFAULT_HIGHER,
    "Main.SubtitleAreaPixelToleranceYPixel": DEFAULT_HIGHER,
    "Main.SubtitleAreaPixelToleranceXPixel": DEFAULT_HIGHER,
    "Main.SubtitleTimelineBackwardFrameCount": SettingRiskProfile(
        caution_at=0.30, high_at=0.60
    ),
    "Main.SubtitleTimelineForwardFrameCount": SettingRiskProfile(
        caution_at=0.30, high_at=0.60
    ),
    "Sttn.NeighborStride": LOWER_IS_RISKY,
    "Sttn.ReferenceLength": VRAM_HEAVY,
    "Sttn.MaxLoadNum": VRAM_HEAVY,
    "ProPainter.MaxLoadNum": VRAM_HEAVY,
}


def config_item_key(config_item) -> str:
    return f"{config_item.group}.{config_item.name}"


def assess_setting_risk(config_item, value: Optional[int] = None) -> Tuple[RiskLevel, Optional[str]]:
    """Return (risk level, translation hint key under [Setting] or None)."""
    current = int(config_item.value if value is None else value)
    default = int(config_item.defaultValue)
    min_val, max_val = (int(config_item.range[0]), int(config_item.range[1]))
    profile = _PROFILES.get(config_item_key(config_item), DEFAULT_HIGHER)

    if profile.higher_is_risky:
        if current <= default:
            return "none", None
        span = max_val - default
        excess = current - default
    else:
        if current >= default:
            return "none", None
        span = default - min_val
        excess = default - current

    if span <= 0:
        return "none", None

    ratio = excess / span
    hint_key = f"SettingRiskHint{config_item.name}"
    if ratio >= profile.high_at:
        return "high", hint_key
    if ratio >= profile.caution_at:
        return "caution", hint_key
    return "none", None
