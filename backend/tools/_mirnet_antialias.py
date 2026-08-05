"""Compatibility module alias for :mod:`backend.ai.architectures.mirnet_antialias`."""

import sys

from backend.ai.architectures import mirnet_antialias as _implementation

sys.modules[__name__] = _implementation
