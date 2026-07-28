"""Canonical build and repository metadata.

This module must stay importable in installers, workers, and tests without Qt.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BuildInfo:
    version: str
    repository_owner: str
    repository_name: str

    @property
    def project_url(self) -> str:
        return f"https://github.com/{self.repository_owner}/{self.repository_name}"

    @property
    def issues_url(self) -> str:
        return f"{self.project_url}/issues"

    @property
    def releases_url(self) -> str:
        return f"{self.project_url}/releases"

    @property
    def latest_release_api_url(self) -> str:
        return (
            "https://api.github.com/repos/"
            f"{self.repository_owner}/{self.repository_name}/releases/latest"
        )


BUILD_INFO = BuildInfo(
    version="1.4.0",
    repository_owner="dexterR35",
    repository_name="midgard",
)

VERSION = BUILD_INFO.version
REPOSITORY_OWNER = BUILD_INFO.repository_owner
REPOSITORY_NAME = BUILD_INFO.repository_name
PROJECT_HOME_URL = BUILD_INFO.project_url
PROJECT_ISSUES_URL = BUILD_INFO.issues_url
PROJECT_RELEASES_URL = BUILD_INFO.releases_url
PROJECT_UPDATE_URLS = (BUILD_INFO.latest_release_api_url,)
