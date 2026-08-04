from __future__ import annotations

from backend.core.build_info import BUILD_INFO
from backend.updates.service import UpdateState, check_for_update, parse_version


def test_semantic_version_comparison() -> None:
    assert parse_version("v2.0.0") > parse_version("1.99.99")


def test_update_available_uses_canonical_endpoint(monkeypatch) -> None:
    monkeypatch.delenv("MIDGARD_DISABLE_UPDATE_CHECK", raising=False)
    seen: list[str] = []

    def fetch(url: str):
        seen.append(url)
        return {"tag_name": "v9.0.0", "html_url": BUILD_INFO.releases_url}

    result = check_for_update(fetch)
    assert result.state is UpdateState.AVAILABLE
    assert seen == [BUILD_INFO.latest_release_api_url]


def test_offline_and_invalid_responses_are_typed(monkeypatch) -> None:
    monkeypatch.delenv("MIDGARD_DISABLE_UPDATE_CHECK", raising=False)
    offline = check_for_update(lambda url: (_ for _ in ()).throw(OSError("offline")))
    invalid = check_for_update(lambda url: {"tag_name": "not-a-version"})
    assert offline.state is UpdateState.OFFLINE
    assert invalid.state is UpdateState.INVALID_RESPONSE


def test_update_check_can_be_disabled(monkeypatch) -> None:
    monkeypatch.setenv("MIDGARD_DISABLE_UPDATE_CHECK", "1")
    assert check_for_update().state is UpdateState.DISABLED
