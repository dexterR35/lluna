"""Standalone entry point executed inside Lluna's isolated Qwen3-TTS environment.

Mirrors the documented `qwen-tts` usage from the model card
(https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice): load
`Qwen3TTSModel` from the locally pinned checkpoint directory, call
`generate_custom_voice`, and write the first returned waveform to disk.
`attn_implementation="sdpa"` is used instead of the optional
`flash_attention_2` so this runtime doesn't need a separately pinned
flash-attn wheel (see backend/tools/installers/qwen_tts.py).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    args = parser.parse_args()
    request = json.loads(Path(args.request).read_text(encoding="utf-8"))

    import soundfile as sf
    import torch
    from qwen_tts import Qwen3TTSModel

    device = request.get("device") or "cpu"
    model = Qwen3TTSModel.from_pretrained(
        request["checkpoint_dir"],
        device_map=device,
        dtype=torch.bfloat16,
        attn_implementation="sdpa",
    )

    instruct = str(request.get("instruct") or "").strip() or None
    wavs, sample_rate = model.generate_custom_voice(
        text=request["text"],
        language=request["language"],
        speaker=request["speaker"],
        instruct=instruct,
    )
    if not wavs:
        raise RuntimeError("Qwen3-TTS returned no audio.")
    sf.write(request["output_path"], wavs[0], sample_rate)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
