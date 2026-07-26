# Midgard

AI-based hard subtitle and text watermark remover for images and videos. Runs locally — no third-party API required. Keeps the original resolution when writing output.

![Python 3.12+](https://img.shields.io/badge/Python-3.12+-blue.svg)
![OS](https://img.shields.io/badge/OS-Windows%20%7C%20macOS%20%7C%20Linux-green.svg)

## Features

- Remove hardcoded subtitles from video with AI inpainting (STTN, LaMa, ProPainter)
- Custom subtitle regions or full-frame automatic text removal
- Batch remove watermark text from images
- CUDA acceleration when an NVIDIA GPU is available; CPU otherwise

## Requirements

- **Python 3.12** recommended (3.11–3.13 supported)
- **Windows 10 / Windows 11**, macOS, or Linux (one Midgard build covers Win10 and Win11)
- Optional: NVIDIA GPU + drivers for CUDA mode
- Network access once for `pip` (models are already in `backend/models/`)

## Quick start

Copy or clone this project folder onto the machine (include `backend/models/`).  
**Do not copy `midgardEnv/` between Linux and Windows** — recreate it on each OS.

```shell
python install.py
```

The installer will:

1. Detect whether CUDA is available (`nvidia-smi`)
2. Default to **CUDA** if a suitable NVIDIA GPU is found, otherwise **CPU**
3. Show **CUDA / CPU** choices so you can override
4. Create a `midgardEnv` virtual environment and install the matching Paddle / Torch / dependencies
5. Verify and merge model weights
6. Write `run_gui.sh` (Linux/macOS) or `run_gui.bat` (Windows)

Non-interactive (use detected default):

```shell
python install.py --yes
```

Force a mode:

```shell
python install.py --mode cpu --yes
python install.py --mode cuda --yes
```

### Windows 10 / 11

1. Install [Python 3.12](https://www.python.org/downloads/) and enable **Add python.exe to PATH**
2. Copy the Midgard project folder to the PC (with `backend/models/`, without a Linux `midgardEnv/`)
3. Open **Command Prompt** or **PowerShell** in that folder:

```bat
python install.py
run_gui.bat
```

CLI on Windows:

```bat
midgardEnv\Scripts\python.exe backend\main.py -i input.mp4 -o output.mp4
```

Same steps work on **Windows 10 and Windows 11**. For NVIDIA GPUs, install a current Game Ready / Studio driver first so `install.py` can pick CUDA.

### Optional: Windows packaged app (no Python for end users)

On a Windows machine (or via GitHub Actions `build-windows-*.yml`):

```bat
pip install QPT==1.0b8 setuptools
python backend\tools\makedist.py
```

CUDA examples: `makedist.py --cuda 11.8`, `--cuda 12.6`, `--cuda 12.8`, or `--directml`.  
Output is under `midgard_out/` (Release folder). Ship that folder to Win10/Win11 PCs.

## Run

**GUI**

```shell
./run_gui.sh                        # Linux / macOS
run_gui.bat                         # Windows 10 / 11
# or:
midgardEnv/bin/python gui.py        # Linux / macOS
midgardEnv\Scripts\python.exe gui.py
```

**CLI**

```shell
midgardEnv/bin/python backend/main.py -i input.mp4 -o output.mp4
midgardEnv\Scripts\python.exe backend\main.py -i input.mp4 -o output.mp4
```

Useful options:

```text
-i / --input PATH
-o / --output PATH
-c / --subtitle-area-coords YMIN YMAX XMIN XMAX   (repeatable)
--inpaint-mode {sttn-auto,sttn-det,lama,propainter,opencv}
```

## Models included

Weights ship under `backend/models/` (~600 MB): STTN, LaMa, ProPainter, and PP-OCRv5 detectors. Large files are stored as split parts and merged on install / first run. No separate model download is required.

## Troubleshooting

**Slow removal** — prefer STTN and tune settings in the GUI (Advanced / STTN), or edit `backend/config.py`.

**Quality** — try another inpaint mode:

- **STTN** — good for live-action, faster
- **LaMa** — strong on animation / stills
- **ProPainter** — heavy VRAM, better for strong motion

**CUDA selected but install falls back to CPU** — NVIDIA drivers / `nvidia-smi` were not available on that machine.

## License

See [LICENSE](LICENSE). Replace or update it with your Midgard license as needed.
