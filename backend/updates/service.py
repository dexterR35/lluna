"""Non-Qt, source-only release checker with injectable transport."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable

from backend.core.build_info import BUILD_INFO

FetchJson = Callable[[str], dict[str, Any]]
_VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:[-+]([0-9A-Za-z.-]+))?$")


class UpdateState(str, Enum):
    UP_TO_DATE = "up_to_date"
    AVAILABLE = "available"
    OFFLINE = "offline"
    RATE_LIMITED = "rate_limited"
    INVALID_RESPONSE = "invalid_response"
    DISABLED = "disabled"


@dataclass(frozen=True)
class UpdateResult:
    state: UpdateState
    current_version: str
    latest_version: str = ""
    release_url: str = ""
    checked_at: str = ""
    message: str = ""

    @property
    def available(self) -> bool:
        return self.state is UpdateState.AVAILABLE


def parse_version(value: str) -> tuple[int, int, int, str]:
    match = _VERSION.match(value.strip())
    if not match:
        raise ValueError(f"Invalid semantic version: {value!r}")
    major, minor, patch, suffix = match.groups()
    return int(major), int(minor), int(patch), suffix or ""


def _default_fetch(url: str) -> dict[str, Any]:
    import requests

    response = requests.get(
        url,
        headers={"User-Agent": "Midgard-source-update-check"},
        timeout=5,
        allow_redirects=True,
    )
    if response.status_code == 403 and response.headers.get("X-RateLimit-Remaining") == "0":
        raise RateLimitError("GitHub API rate limit reached")
    response.raise_for_status()
    value = response.json()
    if not isinstance(value, dict):
        raise ValueError("Release response is not an object")
    return value


class RateLimitError(RuntimeError):
    pass


def check_for_update(fetch_json: FetchJson | None = None) -> UpdateResult:
    now = datetime.now(timezone.utc).isoformat()
    if os.environ.get("MIDGARD_DISABLE_UPDATE_CHECK") == "1":
        return UpdateResult(
            UpdateState.DISABLED, BUILD_INFO.version, checked_at=now
        )
    fetch = fetch_json or _default_fetch
    try:
        payload = fetch(BUILD_INFO.latest_release_api_url)
        tag = str(payload["tag_name"])
        latest = tag.removeprefix("v")
        current_parsed = parse_version(BUILD_INFO.version)
        latest_parsed = parse_version(latest)
        release_url = str(payload.get("html_url") or BUILD_INFO.releases_url)
        state = (
            UpdateState.AVAILABLE
            if latest_parsed > current_parsed
            else UpdateState.UP_TO_DATE
        )
        return UpdateResult(
            state,
            BUILD_INFO.version,
            latest,
            release_url,
            now,
        )
    except RateLimitError as exc:
        return UpdateResult(
            UpdateState.RATE_LIMITED,
            BUILD_INFO.version,
            checked_at=now,
            message=str(exc),
        )
    except (KeyError, TypeError, ValueError) as exc:
        return UpdateResult(
            UpdateState.INVALID_RESPONSE,
            BUILD_INFO.version,
            checked_at=now,
            message=str(exc),
        )
    except Exception as exc:
        return UpdateResult(
            UpdateState.OFFLINE,
            BUILD_INFO.version,
            checked_at=now,
            message=type(exc).__name__,
        )
