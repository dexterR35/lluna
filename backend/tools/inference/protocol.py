"""Shared inference worker IPC contract (parent ↔ child)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, unique
from typing import Any, Dict, Optional, Tuple

from backend.application.jobs import JobPhase


@unique
class JobType(str, Enum):
    ENHANCE = "enhance"
    SUPIR = "supir"
    LOW_LIGHT = "low_light"
    GENERATE = "generate"
    LAMA_RETOUCH = "lama_retouch"
    SELECT_SUBJECT = "select_subject"
    SUBTITLE = "subtitle"
    BIREFNET = "birefnet"
    SEEDVR = "seedvr"


@unique
class CmdMsg(str, Enum):
    """Parent → child."""

    START_JOB = "START_JOB"
    CANCEL = "CANCEL"
    PING = "PING"
    RELEASE = "RELEASE"  # drop cached models now (idle / workspace reset)
    SHUTDOWN = "SHUTDOWN"


@unique
class EvtMsg(str, Enum):
    """Child → parent."""

    PROGRESS = "PROGRESS"
    LOG = "LOG"
    RESULT = "RESULT"
    ERROR = "ERROR"
    PONG = "PONG"
    PREVIEW = "PREVIEW"  # optional frame / path preview (subtitle, etc.)
    # Parent-only synthetic event when the process dies unexpectedly.
    CRASH = "CRASH"


# Wire format: (msg: str, payload: dict)
Msg = Tuple[str, Dict[str, Any]]
PROTOCOL_VERSION = 1


@dataclass(frozen=True)
class JobRequest:
    job_id: int
    task: JobType
    payload: Dict[str, Any]
    protocol_version: int = PROTOCOL_VERSION

    def to_wire(self) -> Msg:
        return start_job(self.job_id, self.task, self.payload)


@dataclass(frozen=True)
class JobProgress:
    job_id: int
    phase: JobPhase
    overall: int
    message: str = ""

    def to_payload(self) -> Dict[str, Any]:
        return {
            "run_id": self.job_id,
            "phase": self.phase.value,
            "p": max(0, min(100, int(self.overall))),
            "message": self.message,
        }


@dataclass(frozen=True)
class JobResult:
    job_id: int
    output_paths: tuple[str, ...]
    warnings: tuple[str, ...] = ()
    timings_ms: Dict[str, int] | None = None


@dataclass(frozen=True)
class JobError:
    job_id: int
    code: str
    message: str
    retryable: bool = False
    actions: tuple[str, ...] = ()


def cmd(kind: CmdMsg, **payload: Any) -> Msg:
    return (kind.value, payload)


def evt(kind: EvtMsg, **payload: Any) -> Msg:
    return (kind.value, payload)


def start_job(run_id: int, job_type: JobType | str, payload: Optional[Dict[str, Any]] = None) -> Msg:
    jt = job_type.value if isinstance(job_type, JobType) else str(job_type)
    return cmd(CmdMsg.START_JOB, run_id=int(run_id), job_type=jt, payload=payload or {})


def cancel(run_id: int) -> Msg:
    return cmd(CmdMsg.CANCEL, run_id=int(run_id))


def ping(run_id: Optional[int] = None) -> Msg:
    return cmd(CmdMsg.PING, run_id=run_id)


def release() -> Msg:
    """Ask the worker to drop cached ML weights immediately."""
    return cmd(CmdMsg.RELEASE)


def shutdown() -> Msg:
    return cmd(CmdMsg.SHUTDOWN)


def progress(run_id: int, p: int) -> Msg:
    return evt(EvtMsg.PROGRESS, run_id=int(run_id), p=int(max(0, min(100, p))))


def log(run_id: int, msg: str) -> Msg:
    return evt(EvtMsg.LOG, run_id=int(run_id), msg=str(msg))


def result(run_id: int, path: str, **extra: Any) -> Msg:
    return evt(EvtMsg.RESULT, run_id=int(run_id), path=str(path), **extra)


def error(run_id: int, msg: str) -> Msg:
    return evt(EvtMsg.ERROR, run_id=int(run_id), msg=str(msg))


def pong(run_id: Optional[int] = None) -> Msg:
    return evt(EvtMsg.PONG, run_id=run_id)


def preview(run_id: int, **extra: Any) -> Msg:
    return evt(EvtMsg.PREVIEW, run_id=int(run_id), **extra)
