"""Persistent shared inference worker process (enhance / generate / LAMA / subtitle)."""

from __future__ import annotations

import os
import tempfile
import threading
import time
import traceback
from typing import Any, Dict, Optional

from backend.tools.shared.cuda import empty_cuda_cache, ensure_expandable_segments
from backend.tools.inference.protocol import (
    CmdMsg,
    EvtMsg,
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


class _DeferredTerminalQueue:
    """Forward live events, but hold RESULT/ERROR until worker cleanup finishes."""

    _TERMINAL_EVENTS = {EvtMsg.RESULT.value, EvtMsg.ERROR.value}

    def __init__(self, target_queue) -> None:
        self._target_queue = target_queue
        self._terminal_msg = None

    def put(self, msg) -> None:
        try:
            kind = msg[0]
        except (IndexError, TypeError):
            self._target_queue.put(msg)
            return
        if kind in self._TERMINAL_EVENTS:
            # A job must have exactly one terminal outcome. Keep the first one
            # so a later cleanup/secondary error cannot replace the real cause.
            if self._terminal_msg is None:
                self._terminal_msg = msg
            return
        self._target_queue.put(msg)

    def flush_terminal(self) -> None:
        if self._terminal_msg is not None:
            _emit(self._target_queue, self._terminal_msg)
            self._terminal_msg = None


def _release_all_except(keep: Optional[str] = None) -> None:
    """Drop every heavy modality except `keep` (JobType value or None = all)."""
    if keep != JobType.ENHANCE.value:
        try:
            from backend.ai.runtimes.realesrgan import release_enhance_models

            release_enhance_models(blocking=True, timeout=5.0)
        except Exception:
            traceback.print_exc()
    if keep != JobType.LOW_LIGHT.value:
        try:
            from backend.ai.runtimes.mirnet import release_low_light_models

            release_low_light_models(blocking=True, timeout=5.0)
        except Exception:
            traceback.print_exc()
    if keep != JobType.GENERATE.value:
        try:
            from backend.ai.runtimes.diffusion import release_generate_models

            release_generate_models(blocking=True, timeout=5.0)
        except Exception:
            traceback.print_exc()
    if keep not in (JobType.LAMA_RETOUCH.value, JobType.SUBTITLE.value):
        try:
            from backend.ai.runtimes.inpaint import release_inpaint_models

            release_inpaint_models()
        except Exception:
            traceback.print_exc()
    elif keep == JobType.LAMA_RETOUCH.value:
        # Subtitle inpaint stacks differ; still drop video inpaint caches if any.
        try:
            from backend.ai.runtimes.inpaint import release_video_inpaint_models

            release_video_inpaint_models()
        except Exception:
            pass
    elif keep == JobType.SUBTITLE.value:
        try:
            from backend.ai.runtimes.inpaint import release_retouch_lama

            release_retouch_lama()
        except Exception:
            pass
    if keep != JobType.SELECT_SUBJECT.value:
        try:
            from backend.ai.runtimes.segmentation import release_select_object_models

            release_select_object_models(blocking=True, timeout=5.0)
        except Exception:
            traceback.print_exc()
    if keep != JobType.BIREFNET.value:
        try:
            from backend.ai.runtimes.birefnet import release_models

            release_models()
        except Exception:
            traceback.print_exc()
    empty_cuda_cache()


def infer_worker_main(cmd_queue, evt_queue, hardware_accel: bool = True) -> None:
    """Child process entry: long-lived control loop."""
    from backend.ai.runtimes.paddle import disable_paddle_background_services

    # Must happen before hardware/framework detection can import native code.
    disable_paddle_background_services()
    ensure_expandable_segments()
    try:
        from backend.ai.runtimes.paddle_cdn import strip_paddle_cdn_hoster_check

        strip_paddle_cdn_hoster_check()
    except Exception:
        pass
    try:
        from backend.tools.shared.hardware import HardwareAccelerator

        HardwareAccelerator.instance().set_enabled(bool(hardware_accel))
    except (ImportError, RuntimeError) as exc:
        _emit(evt_queue, log(0, f"Hardware initialization degraded: {type(exc).__name__}"))

    cancel_event = threading.Event()
    active_run_id: Optional[int] = None
    busy = False
    state_lock = threading.RLock()
    job_thread: Optional[threading.Thread] = None
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
        last_activity = time.monotonic()
        job_evt_queue = _DeferredTerminalQueue(evt_queue)
        release_after_job = bool(payload.get("release_after_job", False))
        try:
            _release_all_except(keep=job_type)
            if job_type == JobType.ENHANCE.value:
                _job_enhance(
                    run_id,
                    payload,
                    cancel_event,
                    on_progress,
                    heartbeat_log,
                    job_evt_queue,
                )
            elif job_type == JobType.SUPIR.value:
                _job_supir(
                    run_id,
                    payload,
                    cancel_event,
                    on_progress,
                    heartbeat_log,
                    job_evt_queue,
                )
            elif job_type == JobType.LOW_LIGHT.value:
                _job_low_light(
                    run_id,
                    payload,
                    cancel_event,
                    on_progress,
                    heartbeat_log,
                    job_evt_queue,
                )
            elif job_type == JobType.GENERATE.value:
                _job_generate(
                    run_id,
                    payload,
                    cancel_event,
                    on_progress,
                    heartbeat_log,
                    job_evt_queue,
                )
            elif job_type == JobType.LAMA_RETOUCH.value:
                _job_lama_retouch(
                    run_id, payload, on_progress, heartbeat_log, job_evt_queue
                )
            elif job_type == JobType.SELECT_SUBJECT.value:
                _job_select_subject(
                    run_id, payload, on_progress, heartbeat_log, job_evt_queue
                )
            elif job_type == JobType.SUBTITLE.value:
                _job_subtitle(
                    run_id,
                    payload,
                    cancel_event,
                    on_progress,
                    heartbeat_log,
                    job_evt_queue,
                )
            elif job_type == JobType.BIREFNET.value:
                _job_birefnet(
                    run_id,
                    payload,
                    cancel_event,
                    on_progress,
                    heartbeat_log,
                    job_evt_queue,
                )
            elif job_type == JobType.SEEDVR.value:
                _job_seedvr(
                    run_id,
                    payload,
                    cancel_event,
                    on_progress,
                    heartbeat_log,
                    job_evt_queue,
                )
            else:
                _emit(
                    job_evt_queue,
                    error(run_id, f"Unknown job_type: {job_type}"),
                )
        except Exception as e:
            traceback.print_exc()
            _emit(job_evt_queue, error(run_id, str(e)))
        finally:
            if release_after_job:
                _emit(job_evt_queue, log(run_id, "Releasing model and GPU memory..."))
                _release_all_except(keep=None)
            else:
                empty_cuda_cache()
            with state_lock:
                busy = False
                active_run_id = None
            last_activity = time.monotonic()
            # RESULT/ERROR is deliberately last. The parent may enqueue the
            # next image as soon as it receives this terminal event.
            job_evt_queue.flush_terminal()

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
            with state_lock:
                can_release = not busy
            if can_release:
                _release_all_except(keep=None)
            last_activity = time.monotonic()
            continue

        if msg == CmdMsg.CANCEL.value:
            rid = data.get("run_id")
            with state_lock:
                current_run_id = active_run_id
            if current_run_id is not None and (
                rid is None or int(rid) == int(current_run_id)
            ):
                cancel_event.set()
                try:
                    from backend.ai.runtimes.realesrgan import cancel_enhance

                    cancel_enhance()
                except Exception:
                    pass
                try:
                    from backend.ai.runtimes.mirnet import cancel_low_light

                    cancel_low_light()
                except Exception:
                    pass
                try:
                    from backend.ai.runtimes.diffusion import cancel_generate

                    cancel_generate()
                except Exception:
                    pass
            last_activity = time.monotonic()
            continue

        if msg == CmdMsg.START_JOB.value:
            run_id = int(data.get("run_id", 0))
            job_type = str(data.get("job_type", ""))
            payload = data.get("payload") or {}
            with state_lock:
                if busy:
                    rejected = True
                else:
                    rejected = False
                    busy = True
                    active_run_id = run_id
                    cancel_event.clear()
                    job_thread = threading.Thread(
                        target=run_job,
                        args=(run_id, job_type, payload),
                        daemon=True,
                        name=f"infer-job-{run_id}",
                    )
                    job_thread.start()
            if rejected:
                _emit(evt_queue, error(run_id, "Worker busy"))
            continue

    cancel_event.set()
    if job_thread is not None and job_thread.is_alive():
        job_thread.join(timeout=3.0)
    if job_thread is None or not job_thread.is_alive():
        _release_all_except(keep=None)
    empty_cuda_cache()


def _job_enhance(run_id, payload, cancel_event, on_progress, heartbeat_log, evt_queue) -> None:
    from PIL import Image

    from backend.tools.shared.constants import EnhanceMode
    from backend.tools.installers.enhance import ensure_model_installed
    from backend.tools.options.enhance import EnhanceOptions
    from backend.ai.runtimes.realesrgan import EnhanceCancelled, enhance_rgba
    from backend.tools.shared.jobs import apply_hardware_from_payload
    from backend.tools.shared.memory import VramBudgetError

    apply_hardware_from_payload(payload)

    input_path = payload["input_path"]
    output_path = payload.get("output_path") or _temp_png("enhance")
    mode_value = payload.get("mode")
    if not mode_value:
        _emit(evt_queue, error(run_id, "Enhance mode was not selected."))
        return
    mode = EnhanceMode(mode_value)
    options = EnhanceOptions.from_payload(payload)

    heartbeat_log(run_id, f"Enhance model: {mode.value}")
    on_progress(run_id, 5)
    heartbeat_log(run_id, "Ensuring model installed…")
    ensure_model_installed(mode)
    if cancel_event.is_set():
        _emit(evt_queue, error(run_id, "__cancelled__"))
        return

    if options.denoise:
        heartbeat_log(run_id, "Denoising…")
    else:
        heartbeat_log(run_id, "Loading Real-ESRGAN…")
    on_progress(run_id, 15)
    img = Image.open(input_path).convert("RGBA")

    def prog(v: int):
        on_progress(run_id, 20 + int(max(0, min(100, v)) * 0.75))

    try:
        out = enhance_rgba(
            img,
            mode,
            progress=prog,
            cancel_event=cancel_event,
            options=options,
        )
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


def _job_supir(run_id, payload, cancel_event, on_progress, heartbeat_log, evt_queue) -> None:
    from backend.ai.runtimes.supir import SupirCancelled, run_supir
    from backend.tools.shared.memory import VramBudgetError, preflight_supir

    try:
        preflight_supir(
            use_llava=bool(payload.get("use_llava")),
            load_8bit_llava=bool(payload.get("load_8bit_llava")),
        )
    except VramBudgetError as e:
        _emit(evt_queue, error(run_id, str(e)))
        return

    try:
        output_path = run_supir(
            payload,
            cancel_event=cancel_event,
            progress=lambda value: on_progress(run_id, value),
            log=lambda message: heartbeat_log(run_id, message),
        )
    except SupirCancelled:
        _emit(evt_queue, error(run_id, "__cancelled__"))
        return
    _emit(evt_queue, result(run_id, output_path))


def _job_low_light(run_id, payload, cancel_event, on_progress, heartbeat_log, evt_queue) -> None:
    from PIL import Image, ImageOps

    from backend.tools.shared.constants import LowLightMode
    from backend.ai.runtimes.mirnet import (
        LowLightCancelled,
        enhance_rgb,
        preflight_low_light,
    )
    from backend.tools.shared.jobs import apply_hardware_from_payload
    from backend.tools.installers.low_light import ensure_model_installed
    from backend.tools.shared.memory import VramBudgetError

    apply_hardware_from_payload(payload)

    input_path = payload["input_path"]
    output_path = payload.get("output_path") or _temp_png("low_light")
    mode_value = payload.get("mode")
    if not mode_value:
        _emit(evt_queue, error(run_id, "Low-light model was not selected."))
        return
    mode = LowLightMode(mode_value)

    heartbeat_log(run_id, f"Low-light model: {mode.value}")
    on_progress(run_id, 3)
    try:
        with Image.open(input_path) as im:
            w, h = im.size
        preflight_low_light(h, w)
    except VramBudgetError as e:
        _emit(evt_queue, error(run_id, str(e)))
        return

    heartbeat_log(run_id, "Ensuring MIRNet weights installed…")
    ensure_model_installed(mode)
    if cancel_event.is_set():
        _emit(evt_queue, error(run_id, "__cancelled__"))
        return

    heartbeat_log(run_id, "Loading MIRNet (PyTorch)…")
    on_progress(run_id, 12)
    img = ImageOps.exif_transpose(Image.open(input_path))
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA" if "A" in img.getbands() else "RGB")

    def prog(v: int):
        on_progress(run_id, 15 + int(max(0, min(100, v)) * 0.8))

    try:
        out = enhance_rgb(
            img,
            mode,
            progress=prog,
            cancel_event=cancel_event,
        )
    except LowLightCancelled:
        _emit(evt_queue, error(run_id, "__cancelled__"))
        return
    except VramBudgetError as e:
        _emit(evt_queue, error(run_id, str(e)))
        return

    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
    # Prefer PNG to preserve quality; JPEG inputs still get PNG preview (Save can convert).
    out.save(output_path, format="PNG")
    on_progress(run_id, 100)
    _emit(evt_queue, result(run_id, output_path))


def _job_generate(run_id, payload, cancel_event, on_progress, heartbeat_log, evt_queue) -> None:
    from backend.tools.shared.constants import GenerateMode
    from backend.tools.installers.generate import (
        cuda_ready_for_generate,
        ensure_model_installed,
    )
    from backend.tools.options.generate import (
        default_size_preset_for_mode,
        default_step_preset_for_mode,
        resolve_guidance,
    )
    from backend.ai.runtimes.diffusion import (
        GenerateCancelled,
        GenerateCudaError,
        generate_image,
    )
    from backend.tools.shared.jobs import apply_hardware_from_payload

    apply_hardware_from_payload(payload)

    prompt = str(payload.get("prompt") or "").strip()
    if not prompt:
        _emit(evt_queue, error(run_id, "Prompt is empty."))
        return

    output_path = payload.get("output_path") or _temp_png("generate")
    mode_value = payload.get("mode")
    if not mode_value:
        _emit(evt_queue, error(run_id, "Generate model was not selected."))
        return

    from backend.tools.shared.memory import VramBudgetError, preflight_minimum

    try:
        preflight_minimum(
            str(mode_value),
            float(payload.get("minimum_vram_mb") or 0),
            hint="Try a smaller or quantized model, or free up GPU memory.",
        )
    except VramBudgetError as e:
        _emit(evt_queue, error(run_id, str(e)))
        return

    if str(mode_value).startswith("custom:"):
        from backend.models.adapters import AdapterError, generate_with_custom_model

        model_id = str(mode_value).removeprefix("custom:")
        width = int(payload.get("width") or 768)
        height = int(payload.get("height") or 768)
        steps = int(payload.get("steps") or 20)
        seed = payload.get("seed")
        seed_i = int(seed) if seed is not None and str(seed).strip() != "" else None
        heartbeat_log(run_id, f"Loading custom model: {model_id}")
        on_progress(run_id, 2)
        stop_custom_hb = threading.Event()

        def custom_heartbeat():
            while not stop_custom_hb.wait(20.0):
                heartbeat_log(run_id, "Custom model is still working…")

        custom_hb = threading.Thread(target=custom_heartbeat, daemon=True)
        custom_hb.start()
        try:
            output = generate_with_custom_model(
                model_id,
                prompt,
                width=width,
                height=height,
                steps=steps,
                seed=seed_i,
                guidance=(float(payload["guidance"]) if payload.get("guidance") is not None else None),
                negative_prompt=str(payload.get("negative_prompt") or ""),
                progress=lambda value: on_progress(run_id, max(5, min(99, int(value)))),
                cancel_event=cancel_event,
            )
        except AdapterError as exc:
            _emit(evt_queue, error(run_id, "__cancelled__" if str(exc) == "__cancelled__" else str(exc)))
            return
        finally:
            stop_custom_hb.set()
        os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
        output.save(output_path, format="PNG")
        on_progress(run_id, 100)
        _emit(evt_queue, result(run_id, output_path))
        return

    ok, reason = cuda_ready_for_generate()
    if not ok:
        _emit(evt_queue, error(run_id, reason))
        return
    mode = GenerateMode(mode_value)

    default_size = default_size_preset_for_mode(mode)
    default_steps = default_step_preset_for_mode(mode)
    width = int(payload.get("width") or default_size.width)
    height = int(payload.get("height") or default_size.height)
    steps = int(payload.get("steps") or default_steps.steps)
    guidance_value = payload.get("guidance")
    guidance = (
        resolve_guidance(mode)
        if guidance_value is None
        else float(guidance_value)
    )
    seed = payload.get("seed")
    seed_i = int(seed) if seed is not None and str(seed).strip() != "" else None
    source_image = None
    input_path = str(payload.get("input_path") or "").strip()
    if input_path:
        try:
            from PIL import Image

            with Image.open(input_path) as source:
                source_image = source.convert("RGB")
        except (OSError, ValueError) as exc:
            _emit(evt_queue, error(run_id, f"Could not load image-to-image input: {exc}"))
            return
    if payload.get("strength") is not None and source_image is None:
        _emit(evt_queue, error(run_id, "Edit Image needs a source image."))
        return

    heartbeat_log(run_id, f"Generate model: {mode.value}")
    on_progress(run_id, 2)

    stop_hb = threading.Event()

    def _keep_alive():
        while not stop_hb.wait(20.0):
            heartbeat_log(run_id, "Loading generate model (still working)…")

    hb_thread = threading.Thread(target=_keep_alive, daemon=True)
    hb_thread.start()
    out = None
    try:
        heartbeat_log(run_id, "Ensuring generate weights installed…")
        ensure_model_installed(mode)
        if cancel_event.is_set():
            _emit(evt_queue, error(run_id, "__cancelled__"))
            return

        heartbeat_log(run_id, "Loading generate model (Diffusers)…")
        on_progress(run_id, 10)

        def prog(v: int):
            on_progress(run_id, max(10, min(99, int(v))))

        try:
            out = generate_image(
                prompt,
                mode,
                width=width,
                height=height,
                steps=steps,
                guidance=guidance,
                seed=seed_i,
                negative_prompt=str(payload.get("negative_prompt") or "").strip() or None,
                image=source_image,
                strength=(float(payload["strength"]) if payload.get("strength") is not None else None),
                progress=prog,
                cancel_event=cancel_event,
            )
        except GenerateCancelled:
            _emit(evt_queue, error(run_id, "__cancelled__"))
            return
        except GenerateCudaError as e:
            _emit(evt_queue, error(run_id, str(e)))
            return
    finally:
        stop_hb.set()

    if out is None:
        return

    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
    out.save(output_path, format="PNG")
    on_progress(run_id, 100)
    _emit(evt_queue, result(run_id, output_path))


def _lama_rgb_context(rgba_arr):
    """
    Build RGB for LaMa when the input contains transparency.

    Transparent pixels are usually RGB=0. Never composite onto white (that made
    Fill paint white). Voids are filled with the visible-pixel mean
    so the model treats removed BG as empty, not as a real scene.
    """
    import numpy as np

    rgb = rgba_arr[:, :, :3].astype(np.uint8, copy=True)
    opaque = rgba_arr[:, :, 3] > 32
    if not np.any(~opaque):
        return rgb
    if np.any(opaque):
        mean = np.round(rgb[opaque].mean(axis=0)).astype(np.uint8)
    else:
        mean = np.array([128, 128, 128], dtype=np.uint8)
    rgb[~opaque] = mean
    return rgb


def _job_lama_retouch(run_id, payload, on_progress, heartbeat_log, evt_queue) -> None:
    import numpy as np
    from PIL import Image

    from backend.media.mask_layers import mask_roi
    from backend.ai.runtimes.inpaint import get_retouch_lama
    from backend.tools.shared.jobs import apply_hardware_from_payload
    from backend.tools.shared.memory import VramBudgetError, preflight_lama

    apply_hardware_from_payload(payload)

    image_path = payload["image_path"]
    mask_path = payload["mask_path"]
    output_path = payload.get("output_path") or _temp_png("lama")
    model_path = payload.get("model_path")

    heartbeat_log(run_id, "Loading LAMA…")
    on_progress(run_id, 10)
    rgba = Image.open(image_path).convert("RGBA")
    w, h = rgba.size
    mask = np.array(Image.open(mask_path).convert("L"))
    lama_mask = (mask > 32).astype(np.uint8) * 255
    roi = mask_roi(
        lama_mask,
        padding=int(payload.get("roi_padding", 96)),
        align=8,
    )
    if roi is None:
        _emit(evt_queue, error(run_id, "Retouch mask is empty"))
        return
    left, top, right, bottom = roi
    roi_w, roi_h = right - left, bottom - top
    try:
        preflight_lama(roi_h, roi_w)
    except VramBudgetError as e:
        _emit(evt_queue, error(run_id, str(e)))
        return

    arr = np.asarray(rgba)
    # Cutout-aware: subject only — do not use original photo BG.
    rgb = _lama_rgb_context(arr)
    rgb_roi = np.ascontiguousarray(rgb[top:bottom, left:right])
    mask_roi_arr = np.ascontiguousarray(lama_mask[top:bottom, left:right])

    on_progress(run_id, 40)
    heartbeat_log(
        run_id,
        f"LAMA inpainting ROI {roi_w}×{roi_h} of {w}×{h}…",
    )
    try:
        lama = get_retouch_lama(model_path)
        out_rgb_roi = lama.inpaint(rgb_roi, mask_roi_arr)
    except Exception as e:
        traceback.print_exc()
        empty_cuda_cache()
        _emit(evt_queue, error(run_id, str(e)))
        return

    out_arr = arr.copy()
    fill = lama_mask > 0
    roi_fill = mask_roi_arr > 0
    out_patch = out_arr[top:bottom, left:right, :3]
    out_patch[roi_fill] = out_rgb_roi[roi_fill]
    # Keep source alpha outside the fill; filled region becomes opaque.
    out_arr[fill, 3] = 255
    Image.fromarray(out_arr, "RGBA").save(output_path, format="PNG")
    on_progress(run_id, 100)
    _emit(evt_queue, result(run_id, output_path))


def _job_select_subject(run_id, payload, on_progress, heartbeat_log, evt_queue) -> None:
    from backend.ai.runtimes.segmentation import (
        run_select_object,
        select_object_models_ready,
    )
    from backend.tools.shared.jobs import apply_hardware_from_payload
    from backend.tools.installers.select_object import (
        ensure_active_pair_installed,
        resolve_pair,
    )
    from backend.tools.shared.memory import VramBudgetError, preflight_select_subject
    from PIL import Image

    apply_hardware_from_payload(payload)

    image_path = payload["image_path"]
    output_path = payload.get("output_mask_path") or _temp_png("select_mask")
    points = payload.get("points") or None
    labels = payload.get("labels") or None
    text = payload.get("text") or None
    box_threshold = float(payload.get("box_threshold") or 0.25)
    text_threshold = float(payload.get("text_threshold") or 0.25)
    more_complex = payload.get("more_complex")
    if more_complex is not None:
        more_complex = bool(more_complex)

    if not points and not (text and str(text).strip()):
        _emit(evt_queue, error(run_id, "Select Object needs a click or object name."))
        return

    sam2_id, dino_id = resolve_pair(more_complex)
    heartbeat_log(run_id, f"Select Object: {sam2_id.value} + {dino_id.value}")
    on_progress(run_id, 5)

    try:
        with Image.open(image_path) as im:
            w, h = im.size
        preflight_select_subject(h, w, complex_pair=sam2_id.value.endswith("large"))
    except VramBudgetError as e:
        _emit(evt_queue, error(run_id, str(e)))
        return

    try:
        ensure_active_pair_installed(more_complex)
    except Exception as e:
        _emit(evt_queue, error(run_id, f"Select Object models missing: {e}"))
        return

    on_progress(run_id, 15)
    need_dino = bool(text and str(text).strip())
    if select_object_models_ready(sam2_id, dino_id, need_dino=need_dino):
        heartbeat_log(run_id, "Running Select Object…")
    else:
        heartbeat_log(run_id, "Loading Select Object models…")
    try:
        run_select_object(
            image_path,
            output_path,
            points=points,
            labels=labels,
            text=text,
            box_threshold=box_threshold,
            text_threshold=text_threshold,
            more_complex=more_complex,
        )
    except Exception as e:
        traceback.print_exc()
        _emit(evt_queue, error(run_id, str(e)))
        return

    on_progress(run_id, 100)
    _emit(evt_queue, result(run_id, output_path))


def _job_birefnet(run_id, payload, cancel_event, on_progress, heartbeat_log, evt_queue) -> None:
    from backend.ai.runtimes.birefnet import process_image, process_video

    model_id = str(payload.get("model_id") or "birefnet")
    input_path = str(payload.get("input_path") or "")
    output_path = str(payload.get("output_path") or _temp_png("birefnet"))
    params = {
        "resolution": int(payload.get("resolution") or 1024),
        "precision": str(payload.get("precision") or "auto"),
        "threshold": float(payload.get("threshold", 0.5)),
        "feather": int(payload.get("feather") or 0),
        "output_mode": str(payload.get("output_mode") or "transparent"),
        "background_color": str(payload.get("background_color") or "#ffffff"),
        "model_path": payload.get("model_path"),
    }
    if not input_path:
        _emit(evt_queue, error(run_id, "BiRefNet input is missing."))
        return
    heartbeat_log(run_id, f"BiRefNet model: {model_id}")
    on_progress(run_id, 5)
    try:
        if payload.get("media_type") == "video":
            process_video(
                input_path,
                output_path,
                model_id=model_id,
                progress=lambda value: on_progress(run_id, 10 + int(value * 0.85)),
                cancel_event=cancel_event,
                **params,
            )
        else:
            process_image(
                input_path,
                output_path,
                model_id=model_id,
                mask_output_path=f"{output_path}.mask.png",
                alpha_output_path=f"{output_path}.alpha.png",
                **params,
            )
            on_progress(run_id, 95)
    except RuntimeError as exc:
        if str(exc) == "__cancelled__":
            _emit(evt_queue, error(run_id, "__cancelled__"))
            return
        traceback.print_exc()
        _emit(evt_queue, error(run_id, str(exc)))
        return
    except Exception as exc:
        traceback.print_exc()
        _emit(evt_queue, error(run_id, str(exc)))
        return
    on_progress(run_id, 100)
    _emit(evt_queue, result(run_id, output_path))


def _job_seedvr(run_id, payload, cancel_event, on_progress, heartbeat_log, evt_queue) -> None:
    from backend.ai.runtimes.seedvr2 import SeedVRCancelled, run_seedvr
    from backend.tools.shared.memory import VramBudgetError, preflight_seedvr

    model_id = str(payload.get("model_id") or "seedvr2-3b")
    heartbeat_log(run_id, f"SeedVR2 model: {model_id}")
    try:
        preflight_seedvr(model_id)
    except VramBudgetError as e:
        _emit(evt_queue, error(run_id, str(e)))
        return
    try:
        run_seedvr(
            payload,
            cancel_event=cancel_event,
            progress=lambda value: on_progress(run_id, value),
            log=lambda message: heartbeat_log(run_id, message),
        )
    except SeedVRCancelled:
        _emit(evt_queue, error(run_id, "__cancelled__"))
        return
    except Exception as exc:
        traceback.print_exc()
        _emit(evt_queue, error(run_id, str(exc)))
        return
    on_progress(run_id, 100)
    _emit(evt_queue, result(run_id, str(payload["output_path"])))


def _job_subtitle(run_id, payload, cancel_event, on_progress, heartbeat_log, evt_queue) -> None:
    import cv2
    from dataclasses import replace

    from backend.tools.shared.jobs import apply_subtitle_job_config
    from backend.tools.shared.memory import VramBudgetError
    from backend.configuration.models import SubtitleSettings
    from backend.diagnostics.errors import CancellationError
    from backend.media.progress import CancellationToken
    from backend.services.subtitle_removal import (
        SubtitleRemovalRequest,
        SubtitleRemovalService,
    )

    settings = apply_subtitle_job_config(payload)
    request = SubtitleRemovalRequest.from_payload(payload, settings)
    heartbeat_log(
        run_id,
        "Starting subtitle removal "
        f"(inpaint={settings.inpaint_mode}, "
        f"detect={settings.subtitle_detect_mode})…",
    )
    on_progress(run_id, 1)

    # VRAM preflight from video resolution before loading heavy models
    try:
        cap = cv2.VideoCapture(str(request.input_path))
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        cap.release()
        if h > 0 and w > 0:
            from backend.hardware.detector import get_hardware_profile
            from backend.models.policy import video_frame_policy

            profile = get_hardware_profile()
            if settings.inpaint_mode == "propainter":
                configured = settings.propainter_max_load_num
                policy = video_frame_policy(
                    profile,
                    configured=configured,
                    width=w,
                    height=h,
                    propainter=True,
                )
                settings = replace(
                    settings,
                    propainter_max_load_num=policy.effective,
                )
                heartbeat_log(
                    run_id,
                    "Frame policy: "
                    f"configured={policy.configured}, "
                    f"recommended={policy.recommended}, "
                    f"effective={policy.effective}"
                    + (f" ({policy.reason})" if policy.reason else ""),
                )
            elif settings.inpaint_mode in {"sttn-auto", "sttn-det"}:
                configured = settings.sttn_max_load_num
                policy = video_frame_policy(
                    profile,
                    configured=configured,
                    width=w,
                    height=h,
                    propainter=False,
                )
                settings = replace(
                    settings,
                    sttn_max_load_num=policy.effective,
                )
                heartbeat_log(
                    run_id,
                    "Frame policy: "
                    f"configured={policy.configured}, "
                    f"recommended={policy.recommended}, "
                    f"effective={policy.effective}"
                    + (f" ({policy.reason})" if policy.reason else ""),
                )
    except VramBudgetError as e:
        _emit(evt_queue, error(run_id, str(e)))
        return
    except Exception:
        traceback.print_exc()

    request = SubtitleRemovalRequest(
        input_path=request.input_path,
        output_path=request.output_path,
        settings=settings,
        subtitle_areas=request.subtitle_areas,
        ab_sections=request.ab_sections,
    )
    try:
        service = SubtitleRemovalService()
        service.run(
            request,
            cancellation_token=CancellationToken(cancel_event),
            on_progress=lambda event: on_progress(
                run_id, event.overall_progress
            ),
            on_log=lambda message: heartbeat_log(run_id, message),
            on_preview=lambda *args: _emit(
                evt_queue, preview(run_id, args=args)
            ),
        )
    except CancellationError:
        _emit(evt_queue, error(run_id, "__cancelled__"))
        return
    except Exception as e:
        traceback.print_exc()
        _emit(evt_queue, error(run_id, str(e)))
        return
    finally:
        try:
            from backend.ai.runtimes.inpaint import release_inpaint_models

            release_inpaint_models()
        except Exception:
            pass
        empty_cuda_cache()

    on_progress(run_id, 100)
    _emit(evt_queue, result(run_id, str(request.output_path)))


def _temp_png(prefix: str) -> str:
    fd, path = tempfile.mkstemp(prefix=f"lluna_{prefix}_", suffix=".png")
    os.close(fd)
    return path
