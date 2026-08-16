"""Subprocess bridge from Lluna's inference worker to isolated Qwen3-TTS."""

from __future__ import annotations

import json
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Callable

from backend.tools.installers import qwen_tts as qwen_tts_models
from backend.tools.shared.process import ProcessManager


class QwenTtsCancelled(RuntimeError):
    pass


def run_custom_voice(
    text: str,
    language: str,
    speaker: str,
    output_wav_path: str,
    *,
    instruct: str | None = None,
    cancel_event: threading.Event | None = None,
    progress: Callable[[int], None] | None = None,
) -> str:
    if not qwen_tts_models.is_model_installed():
        raise RuntimeError("Qwen3-TTS (CustomVoice) is not fully installed.")
    request = {
        "checkpoint_dir": str(qwen_tts_models.models_root()),
        "text": text,
        "language": language,
        "speaker": speaker,
        "instruct": instruct or "",
        "output_path": output_wav_path,
        "device": "cuda" if qwen_tts_models.cuda_compatible() else "cpu",
    }
    runner = Path(__file__).with_name("qwen_tts_process.py")
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", encoding="utf-8", delete=False
    ) as handle:
        json.dump(request, handle)
        request_path = Path(handle.name)
    if progress:
        progress(5)
    with tempfile.NamedTemporaryFile(mode="w+", encoding="utf-8") as output_log:
        process = subprocess.Popen(  # noqa: S603 - executable and runner are managed paths
            [str(qwen_tts_models.runtime_python()), str(runner), "--request", str(request_path)],
            stdout=output_log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        ProcessManager.instance().add_process(process, name="qwen-tts-worker")
        try:
            while process.poll() is None:
                if cancel_event is not None and cancel_event.wait(0.2):
                    ProcessManager.instance().terminate_by_process(process, quiet=True)
                    raise QwenTtsCancelled("__cancelled__")
            output_log.seek(0)
            output = output_log.read()
            if process.returncode:
                raise RuntimeError(output.strip()[-4000:] or "Qwen3-TTS inference failed.")
            if progress:
                progress(100)
            return output_wav_path
        finally:
            ProcessManager.instance().remove_process("qwen-tts-worker")
            request_path.unlink(missing_ok=True)
