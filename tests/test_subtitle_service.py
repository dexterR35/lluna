from __future__ import annotations

import threading

import pytest

from backend.configuration.models import SubtitleSettings
from backend.diagnostics.errors import CancellationError, InvalidMediaError
from backend.media.progress import CancellationToken
from backend.services.subtitle_removal import (
    SubtitleRemovalRequest,
    SubtitleRemovalService,
)


class FakeRemover:
    def __init__(self, path, interactive, *, settings, cancellation_token):
        self.path = path
        self.settings = settings
        self.token = cancellation_token
        self.video_out_path = ""
        self.sub_areas = []
        self.ab_sections = None
        self.append_output = lambda *args: None
        self.update_preview_with_comp = lambda *args: None
        self._listeners = []

    def add_progress_listener(self, callback):
        self._listeners.append(callback)

    def run(self):
        self.append_output("processing")
        for listener in self._listeners:
            listener(50, False)
            listener(100, True)


def test_subtitle_request_validates_and_normalizes(tmp_path) -> None:
    input_path = tmp_path / "input.mp4"
    input_path.write_bytes(b"video")
    output_path = tmp_path / "output.mp4"
    request = SubtitleRemovalRequest.from_payload(
        {
            "video_path": str(input_path),
            "output_path": str(output_path),
            "options": {
                "sub_areas": [(1, 2, 3, 4)],
                "ab_sections": [(0, 10)],
            },
        },
        SubtitleSettings(),
    )
    assert request.input_path == input_path
    assert request.subtitle_areas == ((1.0, 2.0, 3.0, 4.0),)
    assert request.ab_sections == (range(0, 10),)


def test_subtitle_request_rejects_unknown_options(tmp_path) -> None:
    input_path = tmp_path / "input.mp4"
    input_path.write_bytes(b"video")
    with pytest.raises(ValueError, match="Unsupported"):
        SubtitleRemovalRequest.from_payload(
            {
                "video_path": str(input_path),
                "options": {"arbitrary_attribute": True},
            },
            SubtitleSettings(),
        )


def test_subtitle_service_emits_structured_progress(tmp_path) -> None:
    input_path = tmp_path / "input.mp4"
    input_path.write_bytes(b"video")
    request = SubtitleRemovalRequest.from_payload(
        {"video_path": str(input_path), "output_path": str(tmp_path / "out.mp4")},
        SubtitleSettings(),
    )
    progress = []
    logs = []
    result = SubtitleRemovalService(FakeRemover).run(
        request,
        on_progress=progress.append,
        on_log=logs.append,
    )
    assert result.output_path.name == "out.mp4"
    assert [event.overall_progress for event in progress] == [50, 100]
    assert logs == ["processing"]


def test_subtitle_service_honors_pre_cancel(tmp_path) -> None:
    input_path = tmp_path / "input.mp4"
    input_path.write_bytes(b"video")
    request = SubtitleRemovalRequest.from_payload(
        {"video_path": str(input_path)},
        SubtitleSettings(),
    )
    event = threading.Event()
    event.set()
    with pytest.raises(CancellationError):
        SubtitleRemovalService(FakeRemover).run(
            request,
            cancellation_token=CancellationToken(event),
        )


def test_subtitle_request_rejects_missing_input(tmp_path) -> None:
    with pytest.raises(InvalidMediaError):
        SubtitleRemovalRequest.from_payload(
            {"video_path": str(tmp_path / "missing.mp4")},
            SubtitleSettings(),
        )
