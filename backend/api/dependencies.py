"""Shared API dependency aliases."""

from fastapi import Depends

from backend.api.auth import require_token

Authenticated = Depends(require_token)
