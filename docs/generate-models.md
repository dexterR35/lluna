# Generate model integration

Midgard installs Generate Image models only when the user chooses **Install**
in **Settings → Generate Models**. The source installer installs the Python
runtime (`diffusers`, `transformers`, `accelerate`, and Hugging Face Hub), but
does not automatically download tens or hundreds of gigabytes of optional
weights.

All inference is local after installation. Runtime loading uses
`local_files_only=True` and Safetensors. Only one generation pipeline is cached
at a time.

## Supported models

| Midgard model | Official repository | Diffusers pipeline | Inference policy | License/access |
|---|---|---|---|---|
| FLUX.2 Klein 4B distilled | [black-forest-labs/FLUX.2-klein-4B](https://huggingface.co/black-forest-labs/FLUX.2-klein-4B) | `Flux2KleinPipeline` | 4 steps; distilled guidance is ignored | Apache-2.0 |
| FLUX.2 Klein 9B distilled | [black-forest-labs/FLUX.2-klein-9B](https://huggingface.co/black-forest-labs/FLUX.2-klein-9B) | `Flux2KleinPipeline` | 4 steps; distilled guidance is ignored | FLUX Non-Commercial License; gated |
| FLUX.2 Klein 4B Base | [black-forest-labs/FLUX.2-klein-base-4B](https://huggingface.co/black-forest-labs/FLUX.2-klein-base-4B) | `Flux2KleinPipeline` | 50 steps; guidance 4.0 | Apache-2.0 |
| FLUX.2 Klein 9B Base | [black-forest-labs/FLUX.2-klein-base-9B](https://huggingface.co/black-forest-labs/FLUX.2-klein-base-9B) | `Flux2KleinPipeline` | 50 steps; guidance 4.0 | FLUX Non-Commercial License; gated |
| FLUX.2 Dev 32B | [black-forest-labs/FLUX.2-dev](https://huggingface.co/black-forest-labs/FLUX.2-dev) | `Flux2Pipeline` | 50 steps; guidance 4.0 | FLUX Non-Commercial License; gated |
| FLUX.2 Klein 9B FP8 | [black-forest-labs/FLUX.2-klein-9b-fp8](https://huggingface.co/black-forest-labs/FLUX.2-klein-9b-fp8) | `Flux2Transformer2DModel.from_single_file` + `Flux2KleinPipeline` | 4 steps; distilled guidance is ignored | FLUX Non-Commercial License; gated |
| Qwen-Image 20B | [Qwen/Qwen-Image](https://huggingface.co/Qwen/Qwen-Image) | `QwenImagePipeline` | 50 steps; `true_cfg_scale=4.0` with an empty negative prompt | Apache-2.0 |

The pipeline call conventions follow the official
[FLUX.2 Diffusers documentation](https://huggingface.co/docs/diffusers/api/pipelines/flux2)
and
[Qwen-Image Diffusers documentation](https://huggingface.co/docs/diffusers/api/pipelines/qwenimage).
Qwen-Image uses `true_cfg_scale`, not `guidance_scale`; the latter is ineffective
for the non-distilled model.

## Download layouts

Full Diffusers repositories are filtered to one runtime layout:

- `model_index.json`;
- scheduler configuration;
- text encoder configuration and Safetensors shards;
- tokenizer/processor files;
- transformer configuration and Safetensors shards;
- VAE configuration and Safetensors weights.

This excludes duplicate top-level checkpoints, previews, training files, and
unsafe weight formats.

The official Klein 9B FP8 repository is different: it contains only
`flux-2-klein-9b-fp8.safetensors`. Midgard therefore installs:

1. the 9.43 GB decimal / 8.79 GiB FP8 single-file transformer from the FP8
   repository; and
2. `model_index.json`, scheduler, tokenizer, text encoder, VAE, and
   `transformer/config.json` from the official full
   [Klein 9B repository](https://huggingface.co/black-forest-labs/FLUX.2-klein-9B),
   while explicitly excluding its BF16 transformer weights.

The combined FP8 install is about 24.2 GiB. The filtered FLUX.2 Dev install is
about 105.1 GiB, and Qwen-Image is about 53.7 GiB, based on authenticated
Hugging Face file metadata read on 2026-07-30.

Every install is validated before its installed marker is written. Missing
configuration, component weights, or the FP8 single-file checkpoint makes the
install fail and the partial directory is removed.

## Access, hardware, and memory

FLUX.2 Dev and both Klein 9B repositories require accepting the model terms on
Hugging Face and saving a read token in Midgard. The FP8 install requires access
to both its FP8 repository and the full Klein 9B repository used for components.

Generate Image requires CUDA. Midgard uses BF16 when the GPU supports it and
FP16 otherwise. Very large new models use Diffusers sequential CPU offload,
which reduces peak VRAM at a substantial speed and system-memory cost. The
official Diffusers
[memory guide](https://huggingface.co/docs/diffusers/optimization/memory)
warns that sequential CPU offload can be extremely slow. Installing a model
does not guarantee that a particular GPU/RAM combination can run it.

The FLUX license and acceptable-use conditions remain authoritative:

- [FLUX Non-Commercial License](https://huggingface.co/black-forest-labs/FLUX.2-dev/blob/main/LICENSE.md)
- [Black Forest Labs Acceptable Use Policy](https://bfl.ai/legal/usage-policy)
- [Qwen-Image Apache-2.0 license](https://huggingface.co/Qwen/Qwen-Image/blob/main/LICENSE)
