"""Compatibility facade for the non-Qt source-release update service."""

from __future__ import annotations

from urllib.request import getproxies

from backend.core.build_info import BUILD_INFO
from backend.updates.service import UpdateResult, check_for_update


class VersionService:
    def __init__(self) -> None:
        self.current_version = BUILD_INFO.version
        self.latest_version = BUILD_INFO.version
        # Historical misspelling retained for current UI callers.
        self.lastest_version = BUILD_INFO.version
        self.last_result: UpdateResult | None = None

    def get_latest_version(self) -> str:
        self.last_result = check_for_update()
        if self.last_result.latest_version:
            self.latest_version = self.last_result.latest_version
            self.lastest_version = self.latest_version
        return self.latest_version

    def has_new_version(self) -> bool:
        self.get_latest_version()
        return bool(self.last_result and self.last_result.available)

    def get_system_proxy(self) -> str | None:
        proxies = getproxies()
        return proxies.get("https") or proxies.get("http")
