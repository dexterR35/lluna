"""Model metadata, integrity, and execution policy.

Weight directories coexist below this package; importing this module never
loads or modifies model artifacts.
"""

from backend.models.metadata import ModelMetadata, ModelState
from backend.models.registry import MODEL_REGISTRY, get_model

__all__ = ["MODEL_REGISTRY", "ModelMetadata", "ModelState", "get_model"]
