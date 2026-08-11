from __future__ import annotations

from backend.tools.media.common import get_readable_path


def test_readable_path_preserves_a_not_yet_created_output(tmp_path) -> None:
    output = tmp_path / "future output.mp4"

    assert get_readable_path(str(output))
    assert get_readable_path(str(output)) == str(output)
