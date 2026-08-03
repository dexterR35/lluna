"""Strict graph port types and compatibility rules."""

from __future__ import annotations

from enum import Enum


class PortType(str, Enum):
    IMAGE = "IMAGE"
    MASK = "MASK"
    ALPHA = "ALPHA"
    VIDEO = "VIDEO"
    AUDIO = "AUDIO"
    FRAMES = "FRAMES"
    TEXT = "TEXT"
    PROMPT = "PROMPT"
    PATH = "PATH"
    DIRECTORY = "DIRECTORY"
    NUMBER = "NUMBER"
    INTEGER = "INTEGER"
    BOOLEAN = "BOOLEAN"
    ENUM = "ENUM"
    COLOR = "COLOR"
    SEED = "SEED"
    MODEL = "MODEL"
    METADATA = "METADATA"
    ARTIFACT = "ARTIFACT"


PORT_LABELS = {port: port.value.title() for port in PortType}
PORT_COLOR_TOKENS = {port: f"--mg-port-{port.value.lower()}" for port in PortType}
_SAFE_COERCIONS = {(PortType.INTEGER, PortType.NUMBER)}


def ports_compatible(source: PortType, target: PortType) -> bool:
    return source == target or (source, target) in _SAFE_COERCIONS
