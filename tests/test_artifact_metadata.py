"""ArtifactStore.commit(): precomputed metadata pass-through, and the video
fallback prober that fills in width/height/duration/frame_count for media
the PIL-based image probe can't open (which used to mean video artifacts
were committed with no dimensions at all)."""

from __future__ import annotations

from PIL import Image

from backend.artifacts.store import ArtifactStore


def test_commit_uses_precomputed_metadata_without_reprobing(tmp_path, monkeypatch):
    store = ArtifactStore(tmp_path / "artifacts")
    source = tmp_path / "in.png"
    Image.new("RGBA", (4, 4), (1, 2, 3, 255)).save(source)

    def _boom(path):
        raise AssertionError("should not re-probe when metadata is precomputed")

    monkeypatch.setattr(store, "_image_metadata", _boom)

    record = store.commit(
        source,
        run_id="run-1",
        node_id="node-1",
        inputs=[],
        width=99,
        height=42,
        alpha=False,
    )

    assert (record.width, record.height, record.alpha) == (99, 42, False)


def test_commit_probes_image_metadata_when_not_supplied(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")
    source = tmp_path / "in.png"
    Image.new("RGBA", (5, 3), (1, 2, 3, 255)).save(source)

    record = store.commit(source, run_id="run-1", node_id="node-1", inputs=[])

    assert (record.width, record.height, record.alpha) == (5, 3, True)


def test_commit_falls_back_to_video_metadata_when_pil_cannot_open(tmp_path, monkeypatch):
    store = ArtifactStore(tmp_path / "artifacts")
    source = tmp_path / "in.mp4"
    source.write_bytes(b"not a real video, just needs to exist for the copy step")

    from backend.media.video import VideoMetadata

    class _FakeSource:
        def __init__(self):
            self.metadata = VideoMetadata(frame_count=48, fps=24.0, width=640, height=480)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(
        "backend.media.video.VideoSource.open", classmethod(lambda cls, path: _FakeSource())
    )

    record = store.commit(source, run_id="run-1", node_id="node-1", inputs=[])

    assert record.width == 640
    assert record.height == 480
    assert record.frame_count == 48
    assert record.duration == 2.0


def test_commit_still_works_when_neither_probe_can_read_the_file(tmp_path, monkeypatch):
    store = ArtifactStore(tmp_path / "artifacts")
    source = tmp_path / "in.bin"
    source.write_bytes(b"opaque bytes")

    record = store.commit(source, run_id="run-1", node_id="node-1", inputs=[])

    assert record.width is None
    assert record.height is None
    assert record.duration is None
    assert record.frame_count is None
