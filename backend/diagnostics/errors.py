"""Typed domain errors separated from presentation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UserError:
    code: str
    title: str
    explanation: str
    actions: tuple[str, ...] = ()
    technical_details: str = ""
    retryable: bool = False


class LlunaError(RuntimeError):
    code = "LLUNA_ERROR"
    title = "Lluna could not complete the operation"
    actions: tuple[str, ...] = ()
    retryable = False

    def to_user_error(self) -> UserError:
        return UserError(
            code=self.code,
            title=self.title,
            explanation=str(self),
            actions=self.actions,
            technical_details=f"{type(self).__name__}: {self}",
            retryable=self.retryable,
        )


class ConfigurationError(LlunaError):
    code = "CONFIGURATION_ERROR"
    title = "Settings could not be loaded"


class DependencyError(LlunaError):
    code = "DEPENDENCY_UNAVAILABLE"
    title = "A required component is unavailable"


class InferenceError(LlunaError):
    code = "INFERENCE_ERROR"
    title = "Processing failed"
    retryable = True


class WorkerStartupError(InferenceError):
    code = "WORKER_STARTUP_ERROR"
    title = "The processing service could not start"
    actions = ("Retry startup.", "Open Diagnostics for technical details.")


class CancellationError(LlunaError):
    code = "CANCELLED"
    title = "Processing cancelled"


class InvalidMediaError(LlunaError):
    code = "INVALID_MEDIA"
    title = "This media file cannot be opened"
    actions = ("Choose another file.", "Check that FFmpeg can read the file.")


class OutputWriteError(LlunaError):
    code = "OUTPUT_WRITE_ERROR"
    title = "The result could not be saved"
    actions = ("Choose another output folder.", "Check available disk space.")


