"""Persistent shared inference worker process (enhance / rembg / LAMA / subtitle)."""

from __future__ import annotations

import os
import tempfile
import threading
import time
import traceback
from typing import Any, Dict, Optional

from backend.tools.cuda_hygiene import empty_cuda_cache, ensure_expandable_segments
from backend.tools.infer_protocol import (
    CmdMsg,
    JobType,
    error,
    log,
    pong,
    preview,
    progress,
    result,
)


def _emit(evt_queue, msg) -> None:
    try:
        evt_queue.put(msg)
    except Exception:
        pass


def _release_all_except(keep: Optional[str] = None) -> None:
    """Drop every heavy modality except `keep` (JobType value or None = all)."""
    if keep != JobType.ENHANCE.value:
        try:
            from backend.tools.image_enhance import release_enhance_models

            release_enhance_models(blocking=True, timeout=5.0)
        except Exception:
            traceback.print_exc()
    if keep != JobType.BG_REMOVE.value:
        try:
            from backend.tools.bg_remove import release_bg_sessions

            release_bg_sessions()
        except Exception:
            traceback.print_exc()
    if keep not in (JobType.LAMA_RETOUCH.value, JobType.SUBTITLE.value):
        try:
            from backend.tools.inpaint_release import release_inpaint_models

            release_inpaint_models()
        except Exception:
            traceback.print_exc()
    elif keep == JobType.LAMA_RETOUCH.value:
        # Subtitle inpaint stacks differ; still drop video inpaint caches if any.
        try:
            from backend.tools.inpaint_release import release_video_inpaint_models

            release_video_inpaint_models()
        except Exception:
            pass
    elif keep == JobType.SUBTITLE.value:
        try:
            from backend.tools.inpaint_release import release_retouch_lama

            release_retouch_lama()
        except Exception:
            pass
    empty_cuda_cache()


def infer_worker_main(cmd_queue, evt_queue, hardware_accel: bool = True) -> None:
    """Child process entry: long-lived control loop."""
    ensure_expandable_segments()
    try:
        from backend.tools.paddle_cdn_patch import strip_paddle_cdn_hoster_check

        strip_paddle_cdn_hoster_check()
    except Exception:
        pass
    try:
        from backend.config import config

        config.set(config.hardwareAcceleration, bool(hardware_accel))
    except Exception:
        pass

    cancel_event = threading.Event()
    active_run_id: Optional[int] = None
    busy = False
    last_activity = time.monotonic()
    stop = False

    def heartbeat_log(run_id: int, msg: str) -> None:
        _emit(evt_queue, log(run_id, msg))
        nonlocal last_activity
        last_activity = time.monotonic()

    def on_progress(run_id: int, p: int) -> None:
        _emit(evt_queue, progress(run_id, p))
        nonlocal last_activity
        last_activity = time.monotonic()

    def run_job(run_id: int, job_type: str, payload: Dict[str, Any]) -> None:
        nonlocal busy, active_run_id, last_activity
        busy = True
        active_run_id = run_id
        cancel_event.clear()
        last_activity = time.monotonic()
        try:
            _release_all_except(keep=job_type)
            if job_type == JobType.ENHANCE.value:
                _job_enhance(run_id, payload, cancel_event, on_progress, heartbeat_log, evt_queue)
            elif job_type == JobType.BG_REMOVE.value:
                _job_bg_remove(run_id, payload, on_progress, heartbeat_log, evt_queue)
            elif job_type == JobType.LAMA_RETOUCH.value:
                _job_lama_retouch(run_id, payload, on_progress, heartbeat_log, evt_queue)
            elif job_type == JobType.SUBTITLE.value:
                _job_subtitle(run_id, payload, cancel_event, on_progress, heartbeat_log, evt_queue)
            else:
                _emit(evt_queue, error(run_id, f"Unknown job_type: {job_type}"))
        except Exception as e:
            traceback.print_exc()
            _emit(evt_queue, error(run_id, str(e)))
        finally:
            busy = False
            active_run_id = None
            last_activity = time.monotonic()
            empty_cuda_cache()

    while not stop:
        # Models stay warm while idle - parent Reset recycles the worker for RAM.
        try:
            msg, data = cmd_queue.get(timeout=0.5)
        except Exception:
            continue

        if msg == CmdMsg.SHUTDOWN.value:
            stop = True
            cancel_event.set()
            break

        if msg == CmdMsg.PING.value:
            _emit(evt_queue, pong(data.get("run_id")))
            last_activity = time.monotonic()
            continue

        if msg == CmdMsg.RELEASE.value:
            if not busy:
                _release_all_except(keep=None)
            last_activity = time.monotonic()
            continue

        if msg == CmdMsg.CANCEL.value:
            rid = data.get("run_id")
            if active_run_id is not None and (rid is None or int(rid) == int(active_run_id)):
                cancel_event.set()
                # Soft cancel only helps enhance; rembg/subtitle rely on process kill from parent.
                try:
                    from backend.tools.image_enhance import cancel_enhance

                    cancel_enhance()
                except Exception:
                    pass
            last_activity = time.monotonic()
            continue

        if msg == CmdMsg.START_JOB.value:
            run_id = int(data.get("run_id", 0))
            job_type = str(data.get("job_type", ""))
            payload = data.get("payload") or {}
            if busy:
                _emit(evt_queue, error(run_id, "Worker busy"))
                continue
            # Run job inline (single-flight). Parent must not double-start.
            run_job(run_id, job_type, payload)
            continue

    _release_all_except(keep=None)
    empty_cuda_cache()


def _job_enhance(run_id, payload, cancel_event, on_progress, heartbeat_log, evt_queue) -> None:
    from PIL import Image

    from backend.tools.constant import EnhanceMode
    from backend.tools.enhance_models import ensure_model_installed
    from backend.tools.image_enhance import EnhanceCancelled, enhance_rgba
    from backend.tools.job_config import apply_hardware_from_payload
    from backend.tools.vram_budget import VramBudgetError

    apply_hardware_from_payload(payload)

    input_path = payload["input_path"]
    output_path = payload.get("output_path") or _temp_png("enhance")
    mode_value = payload.get("mode")
    if not mode_value:
        _emit(evt_queue, error(run_id, "Enhance mode was not selected."))
        return
    mode = EnhanceMode(mode_value)

    heartbeat_log(run_id, f"Enhance model: {mode.value}")
    on_progress(run_id, 5)
    heartbeat_log(run_id, "Ensuring model installed…")
    ensure_model_installed(mode)
    if cancel_event.is_set():
        _emit(evt_queue, error(run_id, "__cancelled__"))
        return

    heartbeat_log(run_id, "Loading Real-ESRGAN…")
    on_progress(run_id, 15)
    img = Image.open(input_path).convert("RGBA")

    def prog(v: int):
        on_progress(run_id, 20 + int(max(0, min(100, v)) * 0.75))

    try:
        out = enhance_rgba(img, mode, progress=prog, cancel_event=cancel_event)
    except EnhanceCancelled:
        _emit(evt_queue, error(run_id, "__cancelled__"))
        return
    except VramBudgetError as e:
        _emit(evt_queue, error(run_id, str(e)))
        return

    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
    out.save(output_path, format="PNG")
    on_progress(run_id, 100)
    _emit(evt_queue, result(run_id, output_path))


def _job_bg_remove(run_id, payload, on_progress, heartbeat_log, evt_queue) -> None:
    from backend.tools.bg_remove import run_bg_remove_job
    from backend.tools.constant import BgRemoveMode
    from backend.tools.job_config import apply_hardware_from_payload
    from backend.tools.vram_budget import VramBudgetError, preflight_rembg
    from PIL import Image

    apply_hardware_from_payload(payload)

    input_path = payload["input_path"]
    output_path = payload["output_path"]
    mode_value = payload.get("mode")
    if not mode_value:
        _emit(evt_queue, error(run_id, "Background-remove model was not selected."))
        return
    mode = BgRemoveMode(mode_value)

    heartbeat_log(run_id, f"Preparing background removal ({mode.value})…")
    on_progress(run_id, 5)
    try:
        with Image.open(input_path) as im:
            w, h = im.size
        preflight_rembg(h, w)
    except VramBudgetError as e:
        _emit(evt_queue, error(run_id, str(e)))
        return

    def prog(p: int):
        on_progress(run_id, int(p))

    def on_log(msg: str):
        heartbeat_log(run_id, msg)

    protect_mask_path = payload.get("protect_mask_path") or None
    if protect_mask_path and not os.path.isfile(protect_mask_path):
        _emit(evt_queue, error(run_id, f"Protect mask missing: {protect_mask_path}"))
        return

    try:
        run_bg_remove_job(
            input_path,
            output_path,
            mode=mode,
            progress=prog,
            log=on_log,
            protect_mask_path=protect_mask_path,
        )
    except Exception as e:
        traceback.print_exc()
        _emit(evt_queue, error(run_id, str(e)))
        return
    on_progress(run_id, 100)
    _emit(evt_queue, result(run_id, output_path))


def _job_lama_retouch(run_id, payload, on_progress, heartbeat_log, evt_queue) -> None:
    import numpy as np
    from PIL import Image

    from backend.tools.inpaint_release import get_retouch_lama, release_retouch_lama
    from backend.tools.job_config import apply_hardware_from_payload
    from backend.tools.vram_budget import VramBudgetError, preflight_lama

    apply_hardware_from_payload(payload)

    image_path = payload["image_path"]
    mask_path = payload["mask_path"]
    output_path = payload.get("output_path") or _temp_png("lama")
    model_path = payload.get("model_path")

    heartbeat_log(run_id, "Loading LAMA…")
    on_progress(run_id, 10)
    rgba = Image.open(image_path).convert("RGBA")
    w, h = rgba.size
    try:
        preflight_lama(h, w)
    except VramBudgetError as e:
        _emit(evt_queue, error(run_id, str(e)))
        return

    mask = np.array(Image.open(mask_path).convert("L"))
    arr = np.asarray(rgba)
    alpha = arr[:, :, 3:4].astype(np.float32) / 255.0
    rgb = (arr[:, :, :3].astype(np.float32) * alpha + 255.0 * (1.0 - alpha)).astype(np.uint8)
    lama_mask = (mask > 32).astype(np.uint8) * 255

    on_progress(run_id, 40)
    heartbeat_log(run_id, "LAMA inpainting…")
    try:
        lama = get_retouch_lama(model_path)
        out_rgb = lama.inpaint(rgb, lama_mask)
    except Exception as e:
        traceback.print_exc()
        empty_cuda_cache()
        _emit(evt_queue, error(run_id, str(e)))
        return

    out = Image.fromarray(out_rgb, "RGB").convert("RGBA")
    # restore alpha from source where not masked
    out_arr = np.asarray(out).copy()
    out_arr[:, :, 3] = arr[:, :, 3]
    Image.fromarray(out_arr, "RGBA").save(output_path, format="PNG")
    on_progress(run_id, 100)
    _emit(evt_queue, result(run_id, output_path))


def _job_subtitle(run_id, payload, cancel_event, on_progress, heartbeat_log, evt_queue) -> None:
    import cv2

    from backend.main import SubtitleRemover
    from backend.tools.job_config import apply_subtitle_job_config
    from backend.tools.vram_budget import VramBudgetError, pick_video_load_num

    # Use the GUI's selected models for this job (worker config is otherwise stale)
    apply_subtitle_job_config(payload)

    video_path = payload["video_path"]
    output_path = payload["output_path"]
    options = payload.get("options") or {}

    try:
        from backend.config import config as _cfg

        heartbeat_log(
            run_id,
            "Starting subtitle removal "
            f"(inpaint={_cfg.inpaintMode.value.value}, "
            f"detect={_cfg.subtitleDetectMode.value.value})…",
        )
    except Exception:
        heartbeat_log(run_id, "Starting subtitle removal…")
    on_progress(run_id, 1)

    # VRAM preflight from video resolution before loading heavy models
    try:
        from backend.config import config
        from backend.tools.constant import InpaintMode

        cap = cv2.VideoCapture(video_path)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        cap.release()
        if h > 0 and w > 0:
            mode = config.inpaintMode.value
            if mode == InpaintMode.PROPAINTER:
                bud = pick_video_load_num(
                    h, w, int(config.propainterMaxLoadNum.value), propainter=True
                )
                if bud.param is not None:
                    options = dict(options)
                    heartbeat_log(run_id, f"VRAM budget: propainterMaxLoadNum={bud.param}")
            elif mode in (InpaintMode.STTN_AUTO, InpaintMode.STTN_DET):
                bud = pick_video_load_num(
                    h, w, int(config.getSttnMaxLoadNum()), propainter=False
                )
                if bud.param is not None:
                    heartbeat_log(run_id, f"VRAM budget: sttn load~{bud.param}")
    except VramBudgetError as e:
        _emit(evt_queue, error(run_id, str(e)))
        return
    except Exception:
        traceback.print_exc()

    sr = SubtitleRemover(video_path, True)
    sr.video_out_path = output_path
    for key, val in options.items():
        setattr(sr, key, val)

    def prog(p, is_finished=False):
        if cancel_event.is_set():
            return
        on_progress(run_id, int(p) if not is_finished else 100)

    sr.add_progress_listener(lambda p, fin: prog(p, fin))
    sr.append_output = lambda *args: heartbeat_log(run_id, " ".join(str(a) for a in args))
    sr.manage_process = lambda pid: heartbeat_log(run_id, f"child_pid={pid}")
    sr.update_preview_with_comp = lambda *args: _emit(
        evt_queue, preview(run_id, args=args)
    )

    try:
        sr.run()
    except Exception as e:
        traceback.print_exc()
        _emit(evt_queue, error(run_id, str(e)))
        return
    finally:
        try:
            from backend.tools.inpaint_release import release_inpaint_models

            release_inpaint_models()
        except Exception:
            pass
        empty_cuda_cache()

    on_progress(run_id, 100)
    _emit(evt_queue, result(run_id, output_path))


def _temp_png(prefix: str) -> str:
    fd, path = tempfile.mkstemp(prefix=f"midgard_{prefix}_", suffix=".png")
    os.close(fd)
    return path
