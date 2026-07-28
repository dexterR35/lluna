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


class MidgardError(RuntimeError):
    code = "MIDGARD_ERROR"
    title = "Midgard could not complete the operation"
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


class ConfigurationError(MidgardError):
    code = "CONFIGURATION_ERROR"
    title = "Settings could not be loaded"


class DependencyError(MidgardError):
    code = "DEPENDENCY_UNAVAILABLE"
    title = "A required component is unavailable"


class HardwareError(MidgardError):
    code = "HARDWARE_ERROR"
    title = "Hardware acceleration is unavailable"


class ModelError(MidgardError):
    code = "MODEL_ERROR"
    title = "The selected model is unavailable"


class InferenceError(MidgardError):
    code = "INFERENCE_ERROR"
    title = "Processing failed"
    retryable = True


class WorkerStartupError(InferenceError):
    code = "WORKER_STARTUP_ERROR"
    title = "The processing service could not start"
    actions = ("Retry startup.", "Open Diagnostics for technical details.")


class CancellationError(MidgardError):
    code = "CANCELLED"
    title = "Processing cancelled"


class InvalidMediaError(MidgardError):
    code = "INVALID_MEDIA"
    title = "This media file cannot be opened"
    actions = ("Choose another file.", "Check that FFmpeg can read the file.")


class OutputWriteError(MidgardError):
    code = "OUTPUT_WRITE_ERROR"
    title = "The result could not be saved"
    actions = ("Choose another output folder.", "Check available disk space.")


class DownloadError(MidgardError):
    code = "DOWNLOAD_ERROR"
    title = "The model could not be downloaded"
    retryable = True


class UpdateError(MidgardError):
    code = "UPDATE_ERROR"
    title = "The update check could not be completed"
