"""Canonical, declarative model references used by Lluna.

This package contains model metadata, manifests, capability contracts, and
runtime profiles. It deliberately contains no model weights and performs no
downloads when imported.
"""

from backend.models.reference.catalog import MODEL_REGISTRY, get_model
from backend.models.reference.metadata import ModelMetadata, ModelState

__all__ = ["MODEL_REGISTRY", "ModelMetadata", "ModelState", "get_model"]
