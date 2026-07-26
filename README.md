<p align="center">
  <img src="docs/midgard.png" alt="Midgard" width="128" />
</p>

<h1 align="center">Midgard</h1>

<p align="center">
  Local AI studio for hard-subtitle / text removal and image background cutouts.<br/>
  No cloud API - runs on your machine and keeps original resolution.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12+-blue.svg" alt="Python 3.12+" />
  <img src="https://img.shields.io/badge/OS-Windows%20%7C%20macOS%20%7C%20Linux-green.svg" alt="OS" />
  <img src="https://img.shields.io/badge/version-1.4.0-orange.svg" alt="Version" />
</p>

---

## What Midgard can do

| Tool | What it does |
|------|----------------|
| **Remove Text** | Strip hardcoded subtitles and text watermarks from **video** and **images** with AI inpainting |
| **Remove BG** | Cut out image backgrounds (PNG with transparency), with protect-mask, retouch, and upscale |
| **Settings** | Tune OCR, STTN / ProPainter, hardware acceleration, and optional model installs |

Everything runs locally. Output keeps the source resolution. Video jobs keep the original audio when merge succeeds.

---

## Features

- **Hard subtitle & text watermark removal** (video + images)
  - Draw one or more subtitle regions, or process full-frame text
  - PP-OCRv5 detection (Precise Server / Fast Mobile)
  - Inpaint modes: STTN Smart, STTN Detection, LaMa, ProPainter, OpenCV
  - Scene-aware processing, batch queue, progress + log
- **Background removal** (images only)
  - Automatic cutout or **Protect areas** (paint regions to keep)
  - **Retouch** mask after preview
  - **Enhance** with Real-ESRGAN (2× default, 4× optional)
  - Multiple rembg / ONNX models (BiRefNet, U2-Net, IS-Net, …)
- **Hardware acceleration** - CUDA (NVIDIA) when available; CPU otherwise; DirectML on Windows packages
- **GUI** (Fluent / PySide6) + **CLI** for subtitle removal and image background cutouts
- **Installer** (`install.py`) creates `midgardEnv`, picks CUDA/CPU, merges model parts, prefetches default BG/Enhance weights

---

## Models

Weights live under `backend/models/` (~1 GB). Split files are merged by `install.py` / first run. No separate “download models” step for core inpaint/OCR.

### Subtitle / text removal (shipped)

| Model | Role | Best for |
|-------|------|----------|
| **STTN Auto** (`sttn-auto`) | Smart video/image inpaint (default) | Live-action, ~4 GB+ VRAM |
| **STTN Det** (`sttn-det`) | Inpaint with detection path | Video when you want detection without smart fill |
| **LaMa** (`big-lama`) | Frame inpaint | Animation, flat color, lower VRAM |
| **ProPainter** | Video inpaint | Strong motion / sports; ~8 GB+ VRAM |
| **OpenCV** | Classical inpaint | Fast preview, lowest quality |
| **PP-OCRv5** (`V5/ch_det`, `ch_det_fast`) | Subtitle / text detection | Precise (Server) or Fast (Mobile) |

### Background removal (ONNX via rembg)

Prefetched on install (or install later in **Settings → Remove BG Models**):

| Default on install | Category |
|--------------------|----------|
| `birefnet-general` | General photos (app default) |
| `u2net_human_seg` | People |
| `isnet-anime` | Anime |
| `u2net_cloth_seg` | Clothes |

Optional from Settings: BiRefNet Lite / Portrait / Massive / DIS / HRSOD / COD, BRIA RMBG, U2-Net, Silueta, IS-Net General, etc.

### Enhance (after Remove BG)

| Model | Notes |
|-------|--------|
| **RealESRGAN ×2** (`RealESRGAN_x2plus`) | Default - installed by `install.py` |
| **RealESRGAN ×4** (`RealESRGAN_x4plus`) | Optional - Settings → Enhance Models |

---

## Requirements

- **Python 3.12** recommended (3.11–3.13 supported)
- **Windows 10 / 11**, macOS, or Linux
- Optional: NVIDIA GPU + current drivers for CUDA
- Network once for `pip` (and for rembg / Real-ESRGAN downloads on first install)
- Keep `backend/models/` with the project. **Do not copy `midgardEnv/` between Linux and Windows** - recreate it per OS.

---

## Install

```shell
python install.py
```

The installer will:

1. Prefer Python 3.12 (falls back to 3.11 / 3.13)
2. Detect CUDA via `nvidia-smi` (default CUDA if found, else CPU)
3. Let you choose **CUDA / CPU**
4. Create `midgardEnv` and install Paddle, Torch, and `requirements.txt`
5. Verify / merge core model weights
6. Prefetch default Remove BG + Real-ESRGAN ×2 models
7. Write `run_gui.sh` (Linux/macOS) or `run_gui.bat` (Windows)

Non-interactive:

```shell
python install.py --yes
```

Force a mode:

```shell
python install.py --mode cpu --yes
python install.py --mode cuda --yes
```

Skip rembg prefetch (install those later from Settings):

```shell
python install.py --skip-rembg-models --yes
```

### Windows 10 / 11

1. Install [Python 3.12](https://www.python.org/downloads/) with **Add python.exe to PATH**
2. Copy the Midgard folder (include `backend/models/`, exclude a Linux `midgardEnv/`)
3. In Command Prompt or PowerShell:

```bat
python install.py
run_gui.bat
```

For NVIDIA GPUs, install a current Game Ready / Studio driver first so CUDA can be selected.

### Optional: Windows packaged build (no Python for end users)

```bat
pip install QPT==1.0b8 setuptools
python backend\tools\makedist.py
```

CUDA examples: `makedist.py --cuda 11.8`, `--cuda 12.6`, `--cuda 12.8`, or `--directml`.  
Output is under `midgard_out/`. Ship that folder to Win10/Win11 PCs.

GitHub Actions workflows: `build-windows-cpu.yml`, `build-windows-cuda-*.yml`, `build-windows-directml.yml`.

---

## Run

### GUI

```shell
./run_gui.sh                        # Linux / macOS
run_gui.bat                         # Windows
# or:
midgardEnv/bin/python gui.py
midgardEnv\Scripts\python.exe gui.py
```

### CLI (subtitle / text removal)

```shell
midgardEnv/bin/python backend/main.py -i input.mp4 -o output.mp4
midgardEnv\Scripts\python.exe backend\main.py -i input.mp4 -o output.mp4
```

Options:

```text
-t / --task remove-text                 (default)
-i / --input PATH
-o / --output PATH
-c / --subtitle-area-coords YMIN YMAX XMIN XMAX   (repeatable)
--inpaint-mode {sttn-auto,sttn-det,lama,propainter,opencv}
```

### CLI (image background removal)

Images only. Writes a transparent PNG.

```shell
midgardEnv/bin/python backend/main.py -t remove-bg -i input.png -o output.png
midgardEnv\Scripts\python.exe backend\main.py -t remove-bg -i input.png -o output.png
```

Options:

```text
-t / --task remove-bg
-i / --input PATH
-o / --output PATH                      (default: <stem>_nobg.png)
--bg-model {birefnet-general,u2net_human_seg,isnet-anime,...}
--protect-mask PATH                     (optional grayscale keep-mask)
```

Examples:

```shell
# Default BiRefNet general model
midgardEnv/bin/python backend/main.py -t remove-bg -i photo.jpg -o cutout.png

# People / anime / clothes models
midgardEnv/bin/python backend/main.py -t remove-bg -i person.jpg -o out.png --bg-model u2net_human_seg
midgardEnv/bin/python backend/main.py -t remove-bg -i anime.png -o out.png --bg-model isnet-anime
```

---

## Quick tips

| Goal | Suggestion |
|------|------------|
| Most live-action video | **STTN Smart Inpainting** |
| Anime / flat color | **LaMa** |
| Heavy camera motion | **ProPainter** (more VRAM) |
| Fast rough preview | **OpenCV** |
| Better OCR boxes | PP-OCRv5 **Precise (Server)** |
| Out of memory | Lower Max Concurrent Frames, use LaMa/OpenCV, or close other apps |
| CUDA install falls back to CPU | Drivers / `nvidia-smi` not available on that machine |

---

## License

See [LICENSE](LICENSE).
