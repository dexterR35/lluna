"""Session-token authentication for HTTP and WebSocket boundaries."""

from __future__ import annotations

import hmac
import os

from fastapi import Header, HTTPException, WebSocket, status

_SESSION_TOKEN = ""


def configure_token(token: str | None) -> None:
    global _SESSION_TOKEN
    token = token or os.environ.get("LLUNA_SESSION_TOKEN", "")
    if len(token) < 32:
        raise ValueError("LLUNA session token must contain at least 32 characters")
    _SESSION_TOKEN = token


def session_token() -> str:
    if not _SESSION_TOKEN:
        configure_token(None)
    return _SESSION_TOKEN


def require_token(
    x_lluna_token: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> None:
    candidate = x_lluna_token
    if authorization and authorization.lower().startswith("bearer "):
        candidate = authorization[7:]
    if not candidate or not hmac.compare_digest(candidate, session_token()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Lluna session token"
        )


async def accept_authenticated_websocket(websocket: WebSocket) -> bool:
    candidate = websocket.headers.get("x-lluna-token") or websocket.query_params.get("token")
    if not candidate or not hmac.compare_digest(candidate, session_token()):
        await websocket.close(code=4401, reason="Invalid Lluna session token")
        return False
    await websocket.accept()
    return True
