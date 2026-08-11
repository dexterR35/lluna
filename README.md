<p align="center">
  <img src="frontend/assets/app-icon/lluna.png" alt="Lluna logo" width="112" height="112" />
</p>

<h1 align="center">Lluna</h1>

<p align="center">
  Local, node-based image and video AI workflows.
</p>

<p align="center">
  <img alt="Linux" src="https://img.shields.io/badge/Linux-supported-2ea44f?logo=linux&logoColor=white" />
  <img alt="Windows" src="https://img.shields.io/badge/Windows-supported-0078D6?logo=windows&logoColor=white" />
  <img alt="macOS" src="https://img.shields.io/badge/macOS-supported-000000?logo=apple&logoColor=white" />
  <img alt="Python" src="https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white" />
  <img alt="Node.js" src="https://img.shields.io/badge/Node.js-22%2B-339933?logo=nodedotjs&logoColor=white" />
</p>

Lluna is an Electron desktop app with a local Python backend. Build a workflow by connecting nodes, choose the models you want, and run the graph on your own machine. Workflows can also run headless from the command line.

Use it to:

- remove text, subtitles, watermarks, and backgrounds;
- upscale or restore images and videos;
- repair low-light photos and masked regions;
- select objects by click or text description;
- generate and edit images with FLUX.2, Qwen-Image, LoRA, and ControlNet;
- caption images with a compatible vision-language model.

<p align="center">
  <img src="example/test1.png" alt="Lluna workflow editor" width="49%" />
  <img src="example/test2.png" alt="Lluna model manager" width="49%" />
</p>

## Quick start

Requirements:

- 64-bit Python 3.12
- Node.js 22 or newer and npm 10 or newer
- Windows, Linux, or macOS
- an internet connection for installation and model downloads
- a compatible NVIDIA driver when using CUDA; the full CUDA Toolkit is not required

```bash
git clone https://github.com/dexterR35/lluna.git
cd lluna
./install.sh                 # Windows: .\install.bat
npm run dev
```

The installer detects CUDA, CPU, or Apple MPS automatically. It does not download optional model weights unless you ask it to:

```bash
./install.sh --schedule-default-models
```

That option queues the starter models after the first launch: Real-ESRGAN x2, MIRNet, and the small SAM2 + Grounding DINO pair.

To force a backend:

```bash
./install.sh --mode cpu
./install.sh --mode directml   # Windows only; useful for AMD/Intel GPUs
./install.sh --mode mps        # Apple silicon
```

On Windows, pass the same options to `install.bat`.

## Models and hardware

Models are optional and installed from **Settings → Models**. Lluna checks the selected backend, system RAM, graphics memory, disk space, and current free memory before enabling or running a model.

The values below are Lluna's declared compatibility floors. They are not peak-usage guarantees: larger images, video batches, ControlNet, LoRAs, and keeping other models loaded can require more free memory.

### What each model is used for

| Model | Used for | Supported backend | Declared minimum |
| --- | --- | --- | --- |
| **BiRefNet** | General image/video background removal | CPU, CUDA, MPS | 4 GB RAM |
| **BiRefNet Dynamic** | Background removal across mixed input resolutions | CPU, CUDA, MPS | 4 GB RAM |
| **BiRefNet HR** | High-resolution background removal | CPU, CUDA, MPS | 6 GB RAM |
| **BiRefNet HR Matting** | High-resolution soft alpha, hair, and fine edges | CPU, CUDA, MPS | 6 GB RAM |
| **BiRefNet Lite 2K** | Lower-memory 2K background removal | CPU, CUDA, MPS | 4 GB RAM |
| **BiRefNet Matting** | Trimap-free soft-alpha matting | CPU, CUDA, MPS | 4 GB RAM |
| **Real-ESRGAN x2 / x4** | Fast image and video enlargement | CPU, CUDA, DirectML, MPS | 2 GB / 4 GB RAM |
| **LaMa** | Masked image retouching and image text removal | CPU, CUDA, DirectML, MPS | 4 GB RAM |
| **MIRNet LOL** | Low-light photo restoration | CPU, CUDA, DirectML, MPS | 4 GB RAM |
| **PaddleOCR Server / Mobile** | Detecting text and subtitles before inpainting | CPU, CUDA | 2 GB / 1 GB RAM |
| **STTN Auto / Detection** | Video and subtitle inpainting | CUDA, DirectML, MPS | 4 GB graphics memory, 4 GB RAM |
| **ProPainter** | Motion-aware video inpainting | CUDA, DirectML, MPS | 8 GB graphics memory, 8 GB RAM |
| **SAM2 + Grounding DINO** | Selecting objects by click or text prompt | CUDA, DirectML, MPS | 4.5 GB graphics memory, 8 GB RAM |
| **SUPIR v0** | Diffusion-based photo restoration and upscaling | CUDA | 12 GB VRAM, 32 GB RAM, about 75.2 GB disk |
| **SeedVR2 3B** | One-step image/video restoration and upscaling | CUDA | 24 GB VRAM, 32 GB RAM, about 14.6 GB disk |
| **SeedVR2 7B** | Higher-capacity SeedVR2 restoration | CUDA | 48 GB VRAM, 64 GB RAM, about 66.9 GB disk |
| **FLUX.2 Klein 4B/9B and Base 4B/9B** | Local image generation and editing | CUDA | 12 GB VRAM, 16 GB RAM |
| **FLUX.2 Klein 9B FP8** | Lower-VRAM FLUX.2 generation | CUDA | 10 GB VRAM, 32 GB RAM |
| **FLUX.2 Dev** | Large non-commercial image generation/editing | CUDA | 12 GB VRAM, 64 GB RAM |
| **Qwen-Image** | Apache-2.0 image generation | CUDA | 12 GB VRAM, 64 GB RAM |



## Workflows

Workflows are saved as `*.lluna.json`.

```text
Load Image → Remove Background → Save Image
Load Video → Remove Text from Video → Save Video
Prompt → Generate Image → Upscale Image → Save Image
Load Image → Select Object → LaMa Retouch → Save Image
```

Generation nodes support compatible LoRAs and ControlNets. A Control Map node can create Canny, depth, or pose guidance, and Lluna rejects adapters whose declared base model does not match the generation model.

## Model management

Open **Settings → Models** to install, enable, disable, or remove built-in models. Downloads are queued and incomplete installs are staged separately from usable weights.

Use **Add model** for a Hugging Face repository, local directory, or supported weight file such as `.safetensors`, `.onnx`, `.pth`, `.pt`, `.ckpt`, or `.bin`. Lluna inspects model cards and declarative configuration without importing remote model code or loading weights merely to identify them. Unknown models remain **Needs configuration** until their task, runtime, and capabilities are reviewed.

SafeTensors is preferred. Pickle-capable formats and repository `requirements.txt` files are not trusted or installed automatically. See the [model reference](backend/models/reference/README.md) and [model platform guide](backend/models/reference/PLATFORM.md).

## Results

<p align="center">
  <img src="example/birefnet_ex2.png" alt="BiRefNet background removal examples" width="49%" />
  <img src="example/images_supir.jpeg" alt="SUPIR restoration example" width="49%" />
</p>

<p align="center">
  <img src="example/seed_vr2_image_upscale.png" alt="SeedVR2 image restoration example" width="49%" />
  <img src="example/flux2.avif" alt="FLUX.2 generation examples" width="49%" />
</p>

## Headless use

The same workflows can run without Electron:

```bash
lluna.py run graph.lluna.json --out ./results
lluna.py run --template cutout-transparent --out ./results
lluna.py templates
lluna.py serve --port 8765 --token <token>
```

`run` executes a workflow in-process and exits with code `0` on success, `1` after a failed or cancelled run, `2` for an invalid workflow, and `3` on timeout. `serve` starts the loopback API used by the desktop app.

Useful environment variables:

| Variable | Effect |
| --- | --- |
| `LLUNA_GRAPH_CONCURRENCY=0` | Run graph nodes one at a time |
| `LLUNA_INFER_DEVICES="cuda:0,cuda:1"` | Start one inference worker per listed GPU |
| `LLUNA_SUPIR_PYTHON` | Use an existing compatible Python for the SUPIR runtime |
| `LLUNA_SEEDVR_PYTHON` | Use an existing compatible Python for the SeedVR2 runtime |
| `LLUNA_BIREFNET_PYTHON` | Use an existing compatible Python for the BiRefNet runtime |
| `HF_TOKEN` | Authenticate gated Hugging Face downloads |

## Development

```bash
npm run dev             # desktop app with live reload
npm run build           # production renderer build
npm run lint            # frontend lint
npm run check           # type checks and static guards
npm test                # frontend and backend tests
```

Backend structure is documented in [backend/ARCHITECTURE.md](backend/ARCHITECTURE.md). Packaging starts in [packaging/build.py](packaging/build.py).

To update a source checkout:

```bash
git pull
./install.sh            # Windows: .\install.bat
npm install --allow-git=all
npm run dev
```

## Privacy and security

The desktop API binds to loopback and uses a token generated at launch. The Electron renderer is sandboxed. Media processing is local; network access is used when you request dependencies, model weights, or updates from an upstream provider.

## License

Lluna source code is licensed under [Apache License 2.0](LICENSE). Model weights and third-party components keep their own licenses. Review [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and the upstream model card before commercial use or redistribution.
