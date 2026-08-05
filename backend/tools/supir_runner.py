"""Standalone entry point executed inside Lluna's isolated SUPIR environment."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    args = parser.parse_args()
    request = json.loads(Path(args.request).read_text(encoding="utf-8"))
    source = Path(request["source_dir"]).resolve()
    sys.path.insert(0, str(source))

    import CKPT_PTH

    CKPT_PTH.LLAVA_CLIP_PATH = request.get("llava_clip_path")
    CKPT_PTH.LLAVA_MODEL_PATH = request.get("llava_model_path")
    CKPT_PTH.SDXL_CLIP1_PATH = request.get("sdxl_clip1_path")
    CKPT_PTH.SDXL_CLIP2_CKPT_PTH = request.get("sdxl_clip2_path")

    import numpy as np  # noqa: I001 - imports must follow the managed sys.path insertion
    import torch
    from omegaconf import OmegaConf
    from PIL import Image

    from SUPIR.util import PIL2Tensor, Tensor2PIL, convert_dtype, create_SUPIR_model

    if not torch.cuda.is_available():
        raise RuntimeError("The official SUPIR runtime supports CUDA only.")
    device = "cuda:0"
    config = OmegaConf.load(source / "options" / "SUPIR_v0.yaml")
    config.SDXL_CKPT = request["sdxl_checkpoint"]
    config.SUPIR_CKPT_Q = request["q_checkpoint"]
    config.SUPIR_CKPT_F = request.get("f_checkpoint") or request["q_checkpoint"]
    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as handle:
        config_path = Path(handle.name)
    OmegaConf.save(config, config_path)
    try:
        model = create_SUPIR_model(str(config_path), SUPIR_sign=request.get("variant", "Q"))
    finally:
        config_path.unlink(missing_ok=True)
    if request.get("loading_half_params"):
        model = model.half()
    if request.get("use_tile_vae"):
        model.init_tile_vae(
            encoder_tile_size=int(request.get("encoder_tile_size", 512)),
            decoder_tile_size=int(request.get("decoder_tile_size", 64)),
        )
    model.ae_dtype = convert_dtype(request.get("ae_dtype", "bf16"))
    model.model.dtype = convert_dtype(request.get("diff_dtype", "fp16"))
    model = model.to(device)

    image = Image.open(request["input_path"]).convert("RGB")
    gamma = float(request.get("gamma_correction", 1.0))
    if gamma != 1.0:
        values = np.asarray(image, dtype=np.float32) / 255.0
        image = Image.fromarray(
            (np.power(values, gamma) * 255).round().clip(0, 255).astype(np.uint8)
        )
    upscale = int(request.get("upscale", 1))
    minimum = int(request.get("min_size", 1024))
    low_quality, height, width = PIL2Tensor(image, upsacle=upscale, min_size=minimum)
    low_quality = low_quality.unsqueeze(0).to(device)[:, :3]

    caption = str(request.get("prompt") or "")
    if request.get("use_llava"):
        from llava.llava_agent import LLavaAgent

        preview, preview_height, preview_width = PIL2Tensor(
            image, upsacle=upscale, min_size=minimum, fix_resize=512
        )
        preview = preview.unsqueeze(0).to(device)[:, :3]
        clean = model.batchify_denoise(preview)
        clean_image = Tensor2PIL(clean[0], preview_height, preview_width)
        agent = LLavaAgent(
            CKPT_PTH.LLAVA_MODEL_PATH,
            device=device,
            load_8bit=bool(request.get("load_8bit_llava")),
            load_4bit=False,
        )
        caption = agent.gen_image_caption(
            [clean_image],
            temperature=float(request.get("llava_temperature", 0.2)),
            top_p=float(request.get("llava_top_p", 0.7)),
            qs=str(request.get("llava_question") or "") or None,
        )[0]

    samples = model.batchify_sample(
        low_quality,
        [caption],
        num_steps=int(request.get("edm_steps", 50)),
        restoration_scale=float(request.get("s_stage1", -1)),
        s_churn=float(request.get("s_churn", 5)),
        s_noise=float(request.get("s_noise", 1.01)),
        cfg_scale=float(request.get("s_cfg", 4.0)),
        control_scale=float(request.get("s_stage2", 1.0)),
        seed=int(request.get("seed", 1234)),
        num_samples=1,
        p_p=str(request.get("positive_prompt") or ""),
        n_p=str(request.get("negative_prompt") or ""),
        color_fix_type=str(request.get("color_fix_type", "Wavelet")),
        use_linear_CFG=bool(request.get("linear_cfg", True)),
        use_linear_control_scale=bool(request.get("linear_s_stage2", False)),
        cfg_scale_start=float(request.get("spt_linear_cfg", 1.0)),
        control_scale_start=float(request.get("spt_linear_s_stage2", 0.0)),
    )
    Tensor2PIL(samples[0], height, width).save(request["output_path"], format="PNG")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
