"""Validated subtitle-removal orchestration independent of Qt and IPC."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import Any, Callable, Mapping, Protocol

from backend.application.jobs import JobPhase
from backend.configuration.models import SubtitleSettings
from backend.diagnostics.errors import InvalidMediaError, OutputWriteError
from backend.media.output_paths import default_output_path
from backend.media.progress import CancellationToken, ProgressEvent


ProgressCallback = Callable[[ProgressEvent], None]
LogCallback = Callable[[str], None]
PreviewCallback = Callable[..., None]


class RemoverFactory(Protocol):
    def __call__(self, *args: Any, **kwargs: Any) -> Any: ...


def _regions(
    raw: Any,
    *,
    name: str,
) -> tuple[tuple[float, float, float, float], ...]:
    if raw is None:
        return ()
    if not isinstance(raw, (list, tuple)):
        raise ValueError(f"{name} must be a list of four-value regions")
    result: list[tuple[float, float, float, float]] = []
    for entry in raw:
        if not isinstance(entry, (list, tuple)) or len(entry) != 4:
            raise ValueError(f"{name} contains an invalid region")
        values = tuple(float(value) for value in entry)
        result.append(values)
    return tuple(result)


def _sections(raw: Any) -> tuple[range, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, (list, tuple)):
        raise ValueError("ab_sections must be a list")
    result: list[range] = []
    for entry in raw:
        if isinstance(entry, range):
            result.append(entry)
            continue
        if not isinstance(entry, (list, tuple)) or len(entry) != 2:
            raise ValueError("ab_sections contains an invalid range")
        start, stop = (int(value) for value in entry)
        if start < 0 or stop < start:
            raise ValueError("ab_sections contains an invalid range")
        result.append(range(start, stop))
    return tuple(result)


@dataclass(frozen=True)
class SubtitleRemovalRequest:
    input_path: Path
    output_path: Path
    settings: SubtitleSettings
    subtitle_areas: tuple[tuple[float, float, float, float], ...] = ()
    ab_sections: tuple[range, ...] = ()

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, Any],
        settings: SubtitleSettings,
    ) -> "SubtitleRemovalRequest":
        raw_input = payload.get("video_path")
        if not raw_input:
            raise InvalidMediaError("No input media path was supplied.")
        input_path = Path(str(raw_input)).expanduser().resolve()
        if not input_path.is_file():
            raise InvalidMediaError(f"Input media does not exist: {input_path}")
        raw_output = payload.get("output_path")
        output_path = (
            Path(str(raw_output)).expanduser().resolve()
            if raw_output
            else default_output_path(
                input_path,
                suffix="_no_sub",
                extension=".mp4",
            )
        )
        if output_path == input_path:
            raise OutputWriteError("Output path must not overwrite the input.")
        options = payload.get("options") or {}
        if not isinstance(options, Mapping):
            raise ValueError("options must be an object")
        unknown = set(options).difference({"sub_areas", "ab_sections"})
        if unknown:
            raise ValueError(
                "Unsupported subtitle options: " + ", ".join(sorted(unknown))
            )
        return cls(
            input_path=input_path,
            output_path=output_path,
            settings=settings,
            subtitle_areas=_regions(options.get("sub_areas"), name="sub_areas"),
            ab_sections=_sections(options.get("ab_sections")),
        )


@dataclass(frozen=True)
class SubtitleRemovalResult:
    output_path: Path
    elapsed_seconds: float


class SubtitleRemovalService:
    def __init__(self, remover_factory: RemoverFactory | None = None) -> None:
        self._remover_factory = remover_factory

    def run(
        self,
        request: SubtitleRemovalRequest,
        *,
        cancellation_token: CancellationToken | None = None,
        on_progress: ProgressCallback | None = None,
        on_log: LogCallback | None = None,
        on_preview: PreviewCallback | None = None,
    ) -> SubtitleRemovalResult:
        token = cancellation_token or CancellationToken()
        token.raise_if_cancelled()
        factory = self._remover_factory
        if factory is None:
            from backend.pipelines.subtitle import SubtitleRemover

            factory = SubtitleRemover
        started = monotonic()
        remover = factory(
            str(request.input_path),
            True,
            settings=request.settings,
            cancellation_token=token,
        )
        remover.video_out_path = str(request.output_path)
        remover.sub_areas = list(request.subtitle_areas)
        remover.ab_sections = list(request.ab_sections) or None
        if on_log is not None:
            remover.append_output = lambda *args: on_log(
                " ".join(str(arg) for arg in args)
            )
        if on_preview is not None:
            remover.update_preview_with_comp = on_preview

        def progress(value: int, finished: bool) -> None:
            token.raise_if_cancelled()
            if on_progress is not None:
                on_progress(
                    ProgressEvent(
                        phase=(
                            JobPhase.COMPLETED
                            if finished
                            else JobPhase.PROCESSING
                        ),
                        phase_progress=int(value),
                        overall_progress=int(value),
                    )
                )

        remover.add_progress_listener(progress)
        remover.run()
        token.raise_if_cancelled()
        return SubtitleRemovalResult(
            output_path=request.output_path,
            elapsed_seconds=monotonic() - started,
        )
