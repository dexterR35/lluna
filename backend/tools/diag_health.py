# -*- coding: utf-8 -*-
"""Startup / live health report for the diagnostic CLI.

Prints model install status (OK / MISSING), selected modes, workers,
active/pending jobs, and tracked processes - the pipeline behind the UI.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from backend.tools import diag


def _ok(flag: bool) -> str:
    return "OK" if flag else "MISSING"


def _file_ok(path: str | Path) -> bool:
    try:
        p = Path(path)
        return p.is_file() and p.stat().st_size > 0
    except OSError:
        return False


def _dir_has_weights(path: str | Path) -> bool:
    try:
        p = Path(path)
        if not p.is_dir():
            return False
        for name in p.iterdir():
            if name.is_file() and name.suffix.lower() in (".pth", ".pt", ".onnx", ".pdiparams"):
                if name.stat().st_size > 0:
                    return True
        return False
    except OSError:
        return False


def _line(label: str, status: str, detail: str = "") -> None:
    extra = f"  {detail}" if detail else ""
    if status == "OK":
        diag.model(f"{label:<28}  {_ok(True)}{extra}")
    elif status == "MISSING":
        diag.warn(f"{label:<28}  {_ok(False)}{extra}")
    else:
        diag.model(f"{label:<28}  {status}{extra}")


def _report_hardware() -> None:
    diag.start("── hardware ──")
    try:
        from backend.tools.hardware_accelerator import HardwareAccelerator

        hw = HardwareAccelerator.instance()
        accel = getattr(hw, "accelerator_name", "?")
        cuda = hw.has_cuda()
        diag.model(f"{'accelerator':<28}  {accel}  cuda={cuda}")
        if cuda:
            free_mb, total_mb = hw.get_vram_mb()
            if total_mb > 0:
                used = max(0.0, total_mb - free_mb)
                diag.model(
                    f"{'vram':<28}  {used/1024:.1f}G used / {total_mb/1024:.1f}G total"
                )
    except Exception as e:
        diag.warn(f"hardware check failed  {e}")
    try:
        from backend.configuration.service import get_settings

        diag.model(
            f"{'hardwareAcceleration':<28}  {bool(get_settings().subtitle.hardware_acceleration)}"
        )
    except Exception:
        pass


def _report_bg_remove_models() -> None:
    diag.start("── models: background remove ──")
    try:
        from backend.configuration.service import get_settings
        from backend.i18n.translations import get_translations
        from backend.tools import bg_remove_models as bgm

        settings = get_settings().background_removal
        tr = get_translations()
        enabled = bgm.parse_enabled_values(settings.enabled_models)
        selected = settings.mode
        ok_n = miss_n = 0
        for info in bgm.MODEL_CATALOG:
            mode = info.mode
            installed = bgm.is_model_installed(mode)
            if installed:
                ok_n += 1
            else:
                miss_n += 1
            name = tr["BgRemoveMode"].get(mode.name, mode.value)
            flags = []
            if mode.value in enabled:
                flags.append("on")
            else:
                flags.append("off")
            if mode.value == selected:
                flags.append("selected")
            if info.is_default:
                flags.append("default")
            path = bgm.model_file_path(mode)
            _line(
                name,
                "OK" if installed else "MISSING",
                f"[{', '.join(flags)}]  {path.name}",
            )
        diag.model(f"{'bg-remove summary':<28}  {ok_n} OK / {miss_n} MISSING")
    except Exception as e:
        diag.warn(f"bg-remove model check failed  {e}")


def _report_enhance_models() -> None:
    diag.start("── models: enhance (Real-ESRGAN) ──")
    try:
        from backend.configuration.service import get_settings
        from backend.i18n.translations import get_translations
        from backend.tools import enhance_models as em

        settings = get_settings().enhancement
        tr = get_translations()
        enabled = em.parse_enabled_values(settings.enabled_models)
        selected = settings.mode
        ok_n = miss_n = 0
        for info in em.MODEL_CATALOG:
            mode = info.mode
            installed = em.is_model_installed(mode)
            if installed:
                ok_n += 1
            else:
                miss_n += 1
            name = tr["EnhanceMode"].get(mode.name, mode.value)
            flags = []
            if mode.value in enabled:
                flags.append("on")
            else:
                flags.append("off")
            if mode.value == selected:
                flags.append("selected")
            path = em.model_file_path(mode)
            _line(
                name,
                "OK" if installed else "MISSING",
                f"[{', '.join(flags)}]  {path.name}",
            )
        diag.model(f"{'enhance summary':<28}  {ok_n} OK / {miss_n} MISSING")
    except Exception as e:
        diag.warn(f"enhance model check failed  {e}")


def _report_video_models() -> None:
    diag.start("── models: video / retouch / detect ──")
    try:
        from backend.configuration.service import get_settings
        from backend.core.paths import PATHS

        base_dir = PATHS.project_root / "backend"
        checks = [
            ("LAMA (retouch/inpaint)", base_dir / "models" / "big-lama" / "big-lama.pt"),
            ("STTN auto", base_dir / "models" / "sttn-auto" / "infer_model.pth"),
            ("STTN det", base_dir / "models" / "sttn-det" / "sttn.pth"),
            ("ProPainter", base_dir / "models" / "propainter" / "ProPainter.pth"),
        ]
        for label, path in checks:
            _line(label, "OK" if _file_ok(path) else "MISSING", str(path.name))

        # OCR det dirs
        for label, rel in (
            ("PP-OCRv5 mobile det", Path("models") / "V5" / "ch_det_fast"),
            ("PP-OCRv5 server det", Path("models") / "V5" / "ch_det"),
        ):
            path = base_dir / rel
            _line(label, "OK" if _dir_has_weights(path) else "MISSING", str(rel))

        try:
            settings = get_settings().subtitle
            inpaint = settings.inpaint_mode
            detect = settings.subtitle_detect_mode
            diag.model(f"{'selected inpaintMode':<28}  {inpaint}")
            diag.model(f"{'selected subtitleDetect':<28}  {detect}")
        except Exception:
            pass
    except Exception as e:
        diag.warn(f"video model check failed  {e}")


def _report_workers() -> None:
    diag.start("── workers / processes ──")
    try:
        from backend.tools.infer_client import InferClient

        snap = InferClient.instance().status_snapshot()
        diag.worker(
            f"infer-worker  pid={snap.get('pid')}  alive={snap.get('alive')}  "
            f"hw={snap.get('hw_accel')}"
        )
        active = snap.get("active")
        pending = snap.get("pending")
        wait_queue = snap.get("wait_queue") or []
        if active:
            diag.run(
                f"active job  {active.get('job_type')}#{active.get('run_id')}  "
                f"finished={active.get('finished')}"
            )
        else:
            diag.run("active job  none  (idle)")
        if pending:
            diag.run(f"pending job  {pending.get('job_type')}  (coalesce)")
        else:
            diag.run("pending job  none")
        if wait_queue:
            parts = [
                f"{j.get('job_type')}#{j.get('run_id')}" for j in wait_queue
            ]
            diag.run(f"wait queue  {len(wait_queue)}  [{' → '.join(parts)}]")
        else:
            diag.run("wait queue  empty")
        diag.run(f"run counter  {snap.get('run_counter', 0)}")
    except Exception as e:
        diag.warn(f"infer worker status failed  {e}")

    try:
        from backend.tools.process_manager import ProcessManager

        procs = list(ProcessManager.instance().processes.items())
        if not procs:
            diag.process("tracked processes  none")
        else:
            for name, proc in procs:
                if isinstance(proc, int):
                    diag.process(f"tracked  {name}  pid={proc}")
                else:
                    pid = getattr(proc, "pid", "?")
                    alive = True
                    if hasattr(proc, "is_alive"):
                        try:
                            alive = bool(proc.is_alive())
                        except Exception:
                            alive = "?"
                    elif hasattr(proc, "poll"):
                        try:
                            alive = proc.poll() is None
                        except Exception:
                            alive = "?"
                    diag.process(f"tracked  {name}  pid={pid}  alive={alive}")
    except Exception as e:
        diag.warn(f"process manager check failed  {e}")


def _check_transformers_stack() -> None:
    try:
        import transformers
        from transformers import (
            AutoModelForZeroShotObjectDetection,
            AutoProcessor,
            Sam2Model,
            Sam2Processor,
        )

        _ = (Sam2Model, Sam2Processor, AutoModelForZeroShotObjectDetection, AutoProcessor)
        ver = getattr(transformers, "__version__", "?")
        _line("transformers (Select Object)", "OK", f"v{ver}")
    except Exception as e:
        _line("transformers (Select Object)", "MISSING", str(e).split("\n")[0][:60])


def _report_select_object_models() -> None:
    diag.start("── models: select object (SAM2 + DINO) ──")
    try:
        from backend.configuration.service import get_settings
        from backend.i18n.translations import get_translations
        from backend.tools import select_object_models as som

        tr = get_translations()
        ok_n = miss_n = 0
        for info in som.PAIR_CATALOG:
            installed = som.is_pair_installed(info.pair_id)
            if installed:
                ok_n += 1
            else:
                miss_n += 1
            name = tr["SelectObjectPair"].get(info.desc_key, info.pair_id.value)
            state = som.pair_install_state(info.pair_id)
            flags = []
            if info.is_default:
                flags.append("default")
            if state == "partial":
                flags.append("partial")
            sam2_id, dino_id = som.PAIR_MEMBERS[info.pair_id]
            _line(
                name,
                "OK" if installed else "MISSING",
                f"[{', '.join(flags) or 'optional'}]  {sam2_id.value} + {dino_id.value}",
            )
        diag.model(f"{'select-object summary':<28}  {ok_n} OK / {miss_n} MISSING")
        try:
            more_complex = bool(get_settings().object_selection.more_complex)
            diag.model(f"{'selectObjectMoreComplex':<28}  {more_complex}")
        except Exception:
            pass
        _check_transformers_stack()
    except Exception as e:
        diag.warn(f"select object model check failed  {e}")


def _report_runtime_errors() -> None:
    diag.start("── quick dependency checks ──")
    deps = [
        ("torch", "torch"),
        ("huggingface_hub", "huggingface_hub"),
        ("rembg", "rembg"),
        ("onnxruntime", "onnxruntime"),
        ("cv2", "cv2"),
        ("PIL", "PIL"),
    ]
    for label, mod in deps:
        try:
            __import__(mod)
            _line(label, "OK")
        except Exception as e:
            _line(label, "MISSING", str(e).split("\n")[0][:60])


def report_startup(*, include_deps: bool = True) -> None:
    """Full startup inventory for the CLI (models + workers + queue)."""
    if not diag.is_enabled():
        return
    diag.start("════════════════════════════════════════")
    diag.start("startup health check")
    diag.start("════════════════════════════════════════")
    _report_hardware()
    _report_bg_remove_models()
    _report_enhance_models()
    _report_select_object_models()
    _report_video_models()
    if include_deps:
        _report_runtime_errors()
    _report_workers()
    diag.start("════════════════════════════════════════")
    diag.start("startup health check DONE")
    diag.start("════════════════════════════════════════")


def report_job_state(label: str = "job state") -> None:
    """Compact active/pending/worker dump (call around Run / Stop)."""
    if not diag.is_enabled():
        return
    diag.start(f"── {label} ──")
    _report_workers()
