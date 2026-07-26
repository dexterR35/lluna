"""GUI-side client for the persistent shared inference worker."""

from __future__ import annotations

import atexit
import multiprocessing
import os
import tempfile
import threading
import time
import traceback
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from backend.tools.infer_protocol import (
    EvtMsg,
    JobType,
    cancel as proto_cancel,
    ping as proto_ping,
    shutdown as proto_shutdown,
    start_job as proto_start_job,
)
from backend.tools.process_manager import ProcessManager
from backend.tools import diag


ProgressCb = Optional[Callable[[int], None]]
LogCb = Optional[Callable[[str], None]]
ResultCb = Optional[Callable[[str], None]]
ErrorCb = Optional[Callable[[str], None]]


def _short_path(path: Any) -> str:
    if not path:
        return "—"
    try:
        return os.path.basename(str(path))
    except Exception:
        return str(path)


def _payload_route(job_type: str, payload: Dict[str, Any]) -> str:
    """One-line route for CLI: model / files / flags behind a job."""
    bits: list[str] = []
    mode = payload.get("mode")
    if mode:
        bits.append(f"model={mode}")
    model_path = payload.get("model_path")
    if model_path:
        bits.append(f"weights={_short_path(model_path)}")
    for key, label in (
        ("input_path", "in"),
        ("image_path", "img"),
        ("mask_path", "mask"),
        ("protect_mask_path", "protect"),
        ("output_path", "out"),
    ):
        if payload.get(key):
            bits.append(f"{label}={_short_path(payload[key])}")
    if "hardware_acceleration" in payload:
        bits.append(f"hw={bool(payload.get('hardware_acceleration'))}")
    if "scale" in payload:
        bits.append(f"scale={payload.get('scale')}")
    return "  ".join(bits) if bits else job_type
PreviewCb = Optional[Callable[..., None]]
DoneCb = Optional[Callable[[], None]]


@dataclass
class _JobCallbacks:
    run_id: int
    job_type: str
    on_progress: ProgressCb = None
    on_log: LogCb = None
    on_result: ResultCb = None
    on_error: ErrorCb = None
    on_preview: PreviewCb = None
    on_done: DoneCb = None
    hard_cancel: bool = False
    finished: bool = False


@dataclass
class _PendingJob:
    job_type: str
    payload: Dict[str, Any]
    callbacks: Dict[str, Any]
    hard_cancel: bool = False


class InferClient:
    """
    Singleton parent-side controller.
    - One persistent worker process
    - At most one active job + one pending (coalesced)
    - Watchdog: silence → kill → CRASH → respawn
    """

    _instance: Optional["InferClient"] = None
    _lock = threading.Lock()

    HARD_CANCEL_TYPES = {
        JobType.BG_REMOVE.value,
        JobType.SUBTITLE.value,
        JobType.LAMA_RETOUCH.value,
    }

    def __init__(self):
        self._cmd_queue = None
        self._evt_queue = None
        self._process = None
        self._reader_thread: Optional[threading.Thread] = None
        self._watchdog_thread: Optional[threading.Thread] = None
        self._run_counter = 0
        self._active: Optional[_JobCallbacks] = None
        self._pending: Optional[_PendingJob] = None
        self._last_heartbeat = 0.0
        self._hw_accel: Optional[bool] = None
        self._stopping = False
        self._shutdown_done = False
        self._state_lock = threading.RLock()

    @classmethod
    def instance(cls) -> "InferClient":
        with cls._lock:
            if cls._instance is None:
                cls._instance = InferClient()
                atexit.register(cls._instance.shutdown)
            return cls._instance

    def _watchdog_sec(self) -> float:
        try:
            from backend.config import config

            return float(config.jobWatchdogSec.value)
        except Exception:
            return 90.0

    def _desired_hw(self) -> bool:
        try:
            from backend.config import config

            return bool(config.hardwareAcceleration.value)
        except Exception:
            return True

    def ensure_started(self) -> None:
        hw = self._desired_hw()
        with self._state_lock:
            if self._process is not None and self._process.is_alive():
                if self._hw_accel is not None and self._hw_accel != hw:
                    self._kill_worker_unlocked(reason="accel_toggle")
                else:
                    return
            self._spawn_unlocked(hw)

    def _spawn_unlocked(self, hw: bool) -> None:
        from backend.tools.infer_worker import infer_worker_main

        ctx = multiprocessing.get_context("spawn")
        self._cmd_queue = ctx.Queue()
        self._evt_queue = ctx.Queue()
        self._process = ctx.Process(
            target=infer_worker_main,
            args=(self._cmd_queue, self._evt_queue, hw),
            name="midgard-infer-worker",
            daemon=True,
        )
        self._process.start()
        self._hw_accel = hw
        ProcessManager.instance().add_process(self._process, name="infer-worker")
        diag.worker(
            f"START  infer-worker  pid={self._process.pid}  hw_accel={hw}"
        )
        self._last_heartbeat = time.monotonic()
        self._stopping = False
        if self._reader_thread is None or not self._reader_thread.is_alive():
            self._reader_thread = threading.Thread(
                target=self._read_events, daemon=True, name="infer-evt-reader"
            )
            self._reader_thread.start()
            diag.worker("START  infer-evt-reader thread")
        if self._watchdog_thread is None or not self._watchdog_thread.is_alive():
            self._watchdog_thread = threading.Thread(
                target=self._watchdog_loop, daemon=True, name="infer-watchdog"
            )
            self._watchdog_thread.start()
            diag.worker("START  infer-watchdog thread")

    def _read_events(self) -> None:
        while not self._stopping:
            q = self._evt_queue
            if q is None:
                time.sleep(0.1)
                continue
            try:
                msg, data = q.get(timeout=0.5)
            except Exception:
                # Process died?
                with self._state_lock:
                    proc = self._process
                    active = self._active
                    if proc is not None and not proc.is_alive() and active and not active.finished:
                        diag.error("infer-worker CRASH detected while job active")
                        self._fail_active_unlocked("CRASH", crash=True)
                        self._process = None
                continue
            self._last_heartbeat = time.monotonic()
            self._dispatch_event(msg, data or {})

    def _dispatch_event(self, msg: str, data: Dict[str, Any]) -> None:
        run_id = data.get("run_id")
        with self._state_lock:
            active = self._active
            if active is None:
                return
            if run_id is not None and int(run_id) != int(active.run_id):
                return  # stale

            if msg == EvtMsg.PROGRESS.value:
                p = int(data.get("p", 0))
                diag.progress(
                    f"run:{active.run_id}:{active.job_type}",
                    p,
                    f"job {active.job_type}#{active.run_id}",
                )
                if active.on_progress:
                    try:
                        active.on_progress(p)
                    except Exception:
                        pass
            elif msg == EvtMsg.LOG.value:
                text = str(data.get("msg", ""))
                diag.worker(f"{active.job_type}#{active.run_id}  {text}")
                if active.on_log:
                    try:
                        active.on_log(text)
                    except Exception:
                        pass
            elif msg == EvtMsg.PREVIEW.value:
                diag.worker(f"preview  {active.job_type}#{active.run_id}")
                if active.on_preview:
                    try:
                        active.on_preview(**{k: v for k, v in data.items() if k != "run_id"})
                    except Exception:
                        pass
            elif msg == EvtMsg.PONG.value:
                pass
            elif msg == EvtMsg.RESULT.value:
                path = str(data.get("path", ""))
                diag.run(
                    f"RESULT  {active.job_type}#{active.run_id}  out={_short_path(path)}"
                )
                active.finished = True
                cb = active.on_result
                done = active.on_done
                self._active = None
                if cb:
                    try:
                        cb(path)
                    except Exception:
                        traceback.print_exc()
                if done:
                    try:
                        done()
                    except Exception:
                        pass
                self._flush_pending_unlocked()
            elif msg == EvtMsg.ERROR.value:
                err = str(data.get("msg", "error"))
                diag.error(f"job ERROR  {active.job_type}#{active.run_id}  {err}")
                active.finished = True
                cb = active.on_error
                done = active.on_done
                self._active = None
                if cb:
                    try:
                        cb(err)
                    except Exception:
                        traceback.print_exc()
                if done:
                    try:
                        done()
                    except Exception:
                        pass
                self._flush_pending_unlocked()

    def _watchdog_loop(self) -> None:
        while not self._stopping:
            time.sleep(2.0)
            with self._state_lock:
                if self._active is None or self._active.finished:
                    continue
                silence = time.monotonic() - self._last_heartbeat
                if silence < self._watchdog_sec():
                    # Keepalive ping
                    if silence > 15 and self._cmd_queue is not None:
                        try:
                            self._cmd_queue.put(proto_ping(self._active.run_id))
                        except Exception:
                            pass
                    continue
                # Timeout
                diag.warn(f"watchdog TIMEOUT  silence={silence:.1f}s")
                self._fail_active_unlocked("TIMEOUT", crash=True)

    def _fail_active_unlocked(self, reason: str, crash: bool = False) -> None:
        active = self._active
        if active is None or active.finished:
            if crash:
                self._kill_worker_unlocked(reason=reason)
            return
        active.finished = True
        cb = active.on_error
        done = active.on_done
        self._active = None
        if crash:
            self._kill_worker_unlocked(reason=reason)
            try:
                self._spawn_unlocked(self._desired_hw())
            except Exception:
                traceback.print_exc()
        msg = "CRASH" if reason == "CRASH" else (
            "TIMEOUT" if reason == "TIMEOUT" else reason
        )
        if cb:
            try:
                cb(msg)
            except Exception:
                pass
        if done:
            try:
                done()
            except Exception:
                pass
        self._flush_pending_unlocked()

    def _kill_worker_unlocked(self, reason: str = "") -> None:
        proc = self._process
        self._process = None
        if proc is None:
            return
        pid = getattr(proc, "pid", "?")
        diag.worker(f"STOP  infer-worker  reason={reason or 'unknown'}  pid={pid}")
        try:
            if self._cmd_queue is not None:
                try:
                    self._cmd_queue.put(proto_shutdown())
                except Exception:
                    pass
            ProcessManager.instance().terminate_by_process(proc, quiet=True)
            ProcessManager.instance().remove_process("infer-worker")
        except Exception:
            traceback.print_exc()

    def is_busy(self) -> bool:
        with self._state_lock:
            return self._active is not None and not self._active.finished

    def start_job(
        self,
        job_type: JobType | str,
        payload: Dict[str, Any],
        *,
        on_progress: ProgressCb = None,
        on_log: LogCb = None,
        on_result: ResultCb = None,
        on_error: ErrorCb = None,
        on_preview: PreviewCb = None,
        on_done: DoneCb = None,
        coalesce: bool = True,
    ) -> int:
        """
        Start a job. If busy and coalesce=True, replace the single pending slot
        and soft/hard-cancel the active job as appropriate.
        Returns run_id (pending jobs get id assigned when flushed).
        """
        jt = job_type.value if isinstance(job_type, JobType) else str(job_type)
        hard = jt in self.HARD_CANCEL_TYPES
        self.ensure_started()

        with self._state_lock:
            if self._active is not None and not self._active.finished:
                if not coalesce:
                    if on_error:
                        on_error("BUSY")
                    return -1
                self._pending = _PendingJob(
                    job_type=jt,
                    payload=payload,
                    callbacks={
                        "on_progress": on_progress,
                        "on_log": on_log,
                        "on_result": on_result,
                        "on_error": on_error,
                        "on_preview": on_preview,
                        "on_done": on_done,
                    },
                    hard_cancel=hard,
                )
                self._cancel_active_unlocked()
                return self._run_counter  # provisional

            return self._start_unlocked(
                jt,
                payload,
                on_progress=on_progress,
                on_log=on_log,
                on_result=on_result,
                on_error=on_error,
                on_preview=on_preview,
                on_done=on_done,
                hard_cancel=hard,
            )

    def _start_unlocked(
        self,
        job_type: str,
        payload: Dict[str, Any],
        **cbs,
    ) -> int:
        hard = bool(cbs.pop("hard_cancel", False))
        self._run_counter += 1
        run_id = self._run_counter
        self._active = _JobCallbacks(
            run_id=run_id,
            job_type=job_type,
            hard_cancel=hard,
            **{k: v for k, v in cbs.items()},
        )
        self._last_heartbeat = time.monotonic()
        assert self._cmd_queue is not None
        self._cmd_queue.put(proto_start_job(run_id, job_type, payload))
        route = _payload_route(job_type, payload)
        diag.run(f"START job  {job_type}#{run_id}")
        diag.process(f"route  {job_type}#{run_id}  {route}")
        return run_id

    def _flush_pending_unlocked(self) -> None:
        pending = self._pending
        self._pending = None
        if pending is None:
            return
        self.ensure_started()
        self._start_unlocked(
            pending.job_type,
            pending.payload,
            hard_cancel=pending.hard_cancel,
            **pending.callbacks,
        )

    def cancel(self, run_id: Optional[int] = None) -> None:
        with self._state_lock:
            active = self._active
            if active and not active.finished:
                diag.run(f"CANCEL job  {active.job_type}#{active.run_id}")
            self._pending = None
            self._cancel_active_unlocked(run_id=run_id)

    def _cancel_active_unlocked(self, run_id: Optional[int] = None) -> None:
        active = self._active
        if active is None or active.finished:
            return
        if run_id is not None and int(run_id) != int(active.run_id):
            return
        if active.hard_cancel or active.job_type in self.HARD_CANCEL_TYPES:
            diag.worker(f"hard cancel  {active.job_type}#{active.run_id}")
            # Kill + restart; fail active as cancelled
            active.finished = True
            cb = active.on_error
            done = active.on_done
            self._active = None
            self._kill_worker_unlocked(reason="hard_cancel")
            try:
                self._spawn_unlocked(self._desired_hw())
            except Exception:
                traceback.print_exc()
            if cb:
                try:
                    cb("__cancelled__")
                except Exception:
                    pass
            if done:
                try:
                    done()
                except Exception:
                    pass
            return
        # Soft cancel
        diag.run(f"soft cancel  {active.job_type}#{active.run_id}")
        if self._cmd_queue is not None:
            try:
                self._cmd_queue.put(proto_cancel(active.run_id))
            except Exception:
                pass

    def status_snapshot(self) -> Dict[str, Any]:
        """Live worker / job queue state for the CLI health report."""
        with self._state_lock:
            proc = self._process
            alive = bool(proc is not None and proc.is_alive())
            active = None
            if self._active is not None:
                active = {
                    "run_id": self._active.run_id,
                    "job_type": self._active.job_type,
                    "finished": self._active.finished,
                    "hard_cancel": self._active.hard_cancel,
                }
            pending = None
            if self._pending is not None:
                pending = {
                    "job_type": self._pending.job_type,
                    "hard_cancel": self._pending.hard_cancel,
                }
            return {
                "pid": getattr(proc, "pid", None) if proc is not None else None,
                "alive": alive,
                "hw_accel": self._hw_accel,
                "active": active,
                "pending": pending,
                "run_counter": self._run_counter,
                "reader_alive": bool(
                    self._reader_thread is not None and self._reader_thread.is_alive()
                ),
                "watchdog_alive": bool(
                    self._watchdog_thread is not None and self._watchdog_thread.is_alive()
                ),
            }

    def shutdown(self) -> None:
        with self._state_lock:
            if self._shutdown_done:
                return
            self._shutdown_done = True
            self._stopping = True
            self._pending = None
            self._active = None
            diag.worker("shutdown InferClient")
            if self._cmd_queue is not None:
                try:
                    self._cmd_queue.put(proto_shutdown())
                except Exception:
                    pass
            self._kill_worker_unlocked(reason="shutdown")

    def temp_dir(self) -> str:
        d = os.path.join(tempfile.gettempdir(), "midgard_infer")
        os.makedirs(d, exist_ok=True)
        return d

    def make_temp_path(self, prefix: str, suffix: str = ".png") -> str:
        fd, path = tempfile.mkstemp(prefix=prefix, suffix=suffix, dir=self.temp_dir())
        os.close(fd)
        return path

    @staticmethod
    def unlink_quiet(path: Optional[str]) -> None:
        if not path:
            return
        try:
            if os.path.isfile(path):
                os.unlink(path)
        except OSError:
            pass
