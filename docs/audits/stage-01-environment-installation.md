# Stage 1 — Environment and Source Installation Audit

## Audit rules and snapshot

This report audits the source repository identified by the user as
`https://github.com/dexterR35/midgard`.

- Audit date: 2026-07-27.
- Current branch: `main`.
- Inspected commit: `c7aa179` (`aupdate models`, 2026-07-27).
- Worktree at audit start: no tracked modifications. Pre-existing untracked audit
  and planning documents were preserved.
- Repository-local instructions: neither `AGENTS.md` nor `CONTRIBUTING.md`
  exists.
- Audit method: static source inspection plus read-only inspection of the existing
  ignored virtual environment. No installer, application, inference, test suite,
  dependency installation, or model download was run.
- Sole Stage 1 output: this report. No code, bundled model, configuration, or
  generated runtime file was changed.
- Distribution boundary: all recommendations retain a source checkout launched
  with Python, BAT, or SH. This report does not recommend standalone executable,
  native bundle, or binary auto-update mechanisms.
- Secret handling: ignored secret-bearing files were not opened, and no
  credential or private path is reproduced here.

Classification used throughout:

- **Verified fact** — directly established from the current branch or the
  read-only working-copy inspection.
- **Probable finding** — strongly indicated by static evidence but still needs a
  controlled runtime check.
- **Recommendation** — proposed source-installation direction.
- **Unknown** — requires platform, hardware, network, or runtime verification.

External compatibility references were checked on 2026-07-27. Repository
citations remain the authority for what Midgard currently does; vendor references
only qualify platform/package support.

## Executive assessment

### Verified facts

The current source installer is a monolithic imperative script. It supports only
`cpu`, `cuda`, and `auto`; it has no supported DirectML or macOS/MPS dependency
branch (`install.py:920-950`). It installs the same broad portable requirements
after separately installing Paddle, Torch, torchvision, and an ONNX Runtime
variant (`install.py:563-641`).

Python 3.12 is the only version exercised by the tracked automation
(`docker/Dockerfile:2`, `.github/workflows/build-windows-cpu.yml:37-40`).
Nevertheless, the installer accepts 3.11, 3.12, and 3.13 and can fall through to
an arbitrary unsupported current interpreter (`install.py:92-137`). The README
badge says “3.12+,” which is broader than either policy
(`README.md:12-15`).

There is one root `requirements.txt`, but no constraints file, lock file,
developer requirements file, `pyproject.toml`, `setup.py`, or `setup.cfg`.
Several requirements have no upper bound or no version at all
(`requirements.txt:1-21`). The installer upgrades unpinned packaging tools before
every individual package operation (`install.py:558-560`).

The checked working-copy environment is Python 3.12.13 in CPU mode. Its metadata
passes `pip check`, and it contains the intended Torch 2.7.0/torchvision 0.22.0,
Paddle 3.0.0, and CPU ONNX Runtime. It does not contain `diffusers` or
`accelerate`, although both are required by the installer and checked by its
post-install verifier (`install.py:640-641`, `install.py:648-674`). This proves
that an existing `midgardEnv` and runtime marker can drift from the current
installer contract. The environment and marker are intentionally ignored
(`.gitignore:1-8`).

The same environment resolved `transformers>=4.48.0` to 5.14.1 and
`huggingface_hub>=0.26.0` to 1.24.0. Those versions are not metadata conflicts,
but they demonstrate that the lower bounds permit major-version movement without
a source change (`requirements.txt:18-19`).

### Probable findings

- CPU source installation on Linux x86-64 is the most viable current path.
- Windows x86-64 CPU and NVIDIA CUDA paths are plausible but are not tested by
  source-install CI.
- DirectML is not currently supportable as documented automation: its pinned
  plugin belongs to an older Torch line, while Midgard fixes Torch at 2.7.0.
- The advertised macOS path is incomplete: the installer uses the Linux/Windows
  CPU-wheel index instead of PyTorch's macOS command, and the bundled macOS
  FFmpeg is x86-64 only.
- Re-running the installer after changing accelerator mode can leave mutually
  conflicting Paddle or ONNX Runtime distributions in one environment.

### Recommendations

Adopt Python 3.12 as the sole production version initially; split portable,
feature, developer, and mutually exclusive accelerator dependencies; generate
tested constraints per supported OS/backend tuple; and make installation a
transactional reconcile operation with an explicit validation command.

Treat DirectML and macOS/MPS as unsupported until dedicated constraints and
hardware CI/manual gates pass. Replace the existing native-build workflows with
source-install validation workflows, and remove native packaging instructions
from the supported setup documentation.

### Unknowns requiring runtime verification

No clean installation was performed on Windows, macOS, or a CUDA host. Actual
wheel resolution, model API compatibility, provider initialization, FFmpeg
execution, GUI startup, Unicode paths, interrupted-network recovery, and
accelerator inference remain unverified.

## 1. Current installation flow

### 1.1 Entry points and files

#### Verified facts

The only tracked installation entry point is `python install.py`. The requested
`install.bat` and `install.sh` files do not exist. `run_gui.bat` and `run_gui.sh`
are generated after a successful install and ignored by Git
(`install.py:896-917`, `.gitignore:2-5`). The current Linux working copy contains
an ignored `run_gui.sh`, but no `run_gui.bat`.

The README instructs users to run `python install.py`, followed by the generated
launcher (`README.md:204-220`, `README.md:273-283`). Its Windows instructions
require Python 3.12 on `PATH` (`README.md:250-259`). There is no equivalent
platform-specific Linux or macOS prerequisites section.

### 1.2 Selection and virtual environment

#### Verified facts

1. `main()` detects NVIDIA CUDA through `nvidia-smi`, selects CPU or CUDA, then
   finds an interpreter (`install.py:953-974`).
2. `find_python()` prefers 3.12, then 3.13, then 3.11. On Windows, the `py`
   launcher is queried only for 3.12 (`install.py:92-125`).
3. If none of those are found, the running interpreter is returned even when its
   version is outside the intended set; only a warning is emitted
   (`install.py:128-137`).
4. `ensure_venv()` creates the fixed directory `midgardEnv`. If the expected
   venv Python executable merely exists, the environment is accepted without
   checking Python version, pip, backend, or health (`install.py:526-540`).
5. If `venv`/`ensurepip` fails, the installer recursively deletes that exact
   environment, recreates it without pip, downloads `get-pip.py`, and executes it
   without a recorded digest (`install.py:541-554`).

#### Probable findings

The fallback bootstrap is not interruption-safe. If interruption occurs after
the `--without-pip` environment is created but before pip is installed, the next
run sees the Python executable, reuses the environment, and then fails because
pip is absent.

An existing 3.11 or 3.13 environment remains in use even if 3.12 later becomes
available. Moving the repository is unsupported because Python virtual
environments are generally non-relocatable; the generated launcher additionally
embeds the current venv interpreter path (`install.py:896-917`).

### 1.3 Dependency operations

#### Verified facts

Every `pip_install()` call first upgrades `pip`, `setuptools`, and `wheel`, then
runs the requested install (`install.py:558-560`). A normal install invokes this
wrapper repeatedly for Paddle, Torch/torchvision, ONNX Runtime, the root
requirements, rembg, Transformers/Hugging Face, and Diffusers/Accelerate
(`install.py:563-641`).

CPU mode installs:

- `paddlepaddle==3.0.0` from the Paddle CPU index;
- `torch==2.7.0` and `torchvision==0.22.0` from the PyTorch CPU index;
- unpinned `onnxruntime`;
- the root requirements and then duplicate feature requirements
  (`install.py:614-641`).

CUDA mode installs:

- CUDA 11.8 Paddle GPU, but CPU Paddle for CUDA 12.6/12.8;
- the exact Torch/torchvision pair from the selected CUDA wheel index;
- Linux CUDA 11.8 ORT GPU 1.20.1 from Microsoft's CUDA 11 feed;
- Linux CUDA 12.6/12.8 ORT GPU 1.22.0;
- unpinned ORT GPU on Windows;
- no ORT variant on macOS;
- the same portable and duplicate feature requirements
  (`install.py:563-641`).

The vendor-supported Torch 2.7 wheel combinations do match Midgard's CUDA tags:
the PyTorch 2.7 archive lists cu118, cu126, and cu128 for Linux/Windows, while its
macOS command intentionally has no CPU index:
<https://pytorch.org/get-started/previous-versions/>.

### 1.4 Verification and finalization

#### Verified facts

The post-install import check covers Torch, Transformers/Hugging Face,
Diffusers/Accelerate, rembg, ONNX Runtime, OpenCV, and Pillow
(`install.py:644-676`). It does **not** check PySide6/qfluentwidgets, Paddle,
PaddleOCR, PaddleX, torchvision, NumPy/SciPy, FFmpeg, the selected Torch device,
or the requested ONNX provider.

The installer then verifies/merges bundled model parts, resets pending download
state, seeds first-run model-download queue entries, writes
`midgard_runtime.json`, and writes a launcher (`install.py:978-1005`). The
installer does not download large defaults immediately in this final step; it
schedules them for the GUI (`install.py:870-879`, `README.md:248-248`).

### 1.5 Repeated and interrupted installation

#### Verified facts

- Repeated installs reuse any environment with a Python executable
  (`install.py:532-537`).
- Packaging tools are upgraded repeatedly rather than once
  (`install.py:558-560`).
- The script does not uninstall an existing `paddlepaddle`/
  `paddlepaddle-gpu` or `onnxruntime`/`onnxruntime-gpu` variant before changing
  modes (`install.py:563-641`).
- Failures are reduced to the subprocess exit code; there is no checkpoint,
  transaction record, or repair action (`install.py:1020-1025`).
- The temporary `get-pip.py` file is deleted only after successful execution
  (`install.py:547-554`), although it is ignored if left behind
  (`.gitignore:13`).

#### Probable findings

A repeated install is usually additive but is not idempotent. CPU-to-CUDA,
CUDA-to-CPU, or CUDA-11.8-to-CUDA-12.x transitions can leave two distributions
that provide the same `onnxruntime` import, or both Paddle CPU and GPU
distributions. Package file ownership and import behavior can then depend on
installation order.

## 2. Python compatibility matrix

### Current policy

| Python | Installer behavior | Automation evidence | Current assessment |
|---|---|---|---|
| 3.10 and older | Not selected as preferred, but the running interpreter can be used after a warning | None | Unsupported; installer should fail closed |
| 3.11 | Explicitly accepted | None | Plausible CPU/CUDA compatibility, untested |
| 3.12 | First preference | Docker and every Windows workflow | Canonical and only evidenced version |
| 3.13 | Explicitly accepted | None | CPU/CUDA plausible; DirectML 1.20.1/plugin wheel set does not cover it |
| 3.14+ | Not preferred, but fallback can still use it | None | Unsupported |

The behavior above is defined at `install.py:92-137`; the README says both
“3.12+” and “3.12 with 3.11/3.13 fallback”
(`README.md:12-15`, `README.md:212-217`). `av==17.0.0`, one of the exact runtime
pins, declares Python 3.11 or newer:
<https://pypi.org/project/av/17.0.0/>.

The DirectML-specific pins narrow the matrix further. PyPI has
`torch-directml==0.2.5.dev240914` wheels through CPython 3.12, not 3.13, and
`onnxruntime-directml==1.20.1` has CPython 3.11/3.12 Windows x86-64 wheels:
<https://pypi.org/project/torch-directml/> and
<https://pypi.org/project/onnxruntime-directml/1.20.1/>.

### Recommended supported-version policy

#### Recommendation

- **Production/canonical:** latest security patch of CPython 3.12, 64-bit.
- **Compatibility candidates:** 3.11 and 3.13 only after every supported
  OS/backend lock resolves and the complete acceptance suite passes.
- **DirectML:** Python 3.12 x86-64 only while retaining the current legacy
  DirectML stack.
- **Rejected:** 32-bit Python and all versions outside an explicit
  `>=3.12,<3.13` production gate during the first migration.
- Publish one policy in README, installer validation, CI, Docker, and project
  metadata. Do not describe support as an open-ended “3.12+”.

## 3. OS/backend compatibility matrix

| Platform | CPU | NVIDIA CUDA | DirectML | MPS | Assessment |
|---|---|---|---|---|---|
| Windows 10/11 x86-64 | Implemented | Implemented | Runtime code exists, source setup absent | N/A | CPU/CUDA probable; DirectML unsupported today |
| Linux x86-64 | Implemented | Implemented | Not an appropriate production target | N/A | Best current source path; still lacks source-install CI |
| macOS Apple silicon | Installer falls into generic CPU path | N/A | N/A | Runtime detection exists | Incomplete/unsupported |
| macOS Intel | Installer falls into generic CPU path | N/A | N/A | Hardware-dependent | Incomplete/unsupported |
| Windows ARM64 | No architecture gate | No supported path | No pinned wheel set | N/A | Unsupported |
| Linux ARM64 | No architecture gate | No supported path | No | N/A | Unsupported by bundled media stack |
| Docker/Linux x86-64 | CPU branch | CUDA 11.8/12.6/12.8 | Incorrectly included in Linux matrix | N/A | CPU/CUDA build-only, not runtime-qualified |

### Evidence

#### Verified facts

The application runtime can detect CUDA, `torch_directml`, and MPS and can list
ONNX CUDA, DML, Metal, and CoreML providers
(`backend/tools/hardware_accelerator.py:29-73`). Torch device selection supports
DirectML, CUDA, MPS, then CPU (`backend/tools/hardware_accelerator.py:188-215`).
This runtime capability is broader than the installer.

DirectML only appears in the obsolete packaging workflow and Dockerfile:
`backend/tools/makedist.py:25-45`, `.github/workflows/build-windows-directml.yml:37-45`,
and `docker/Dockerfile:56-61`. The Windows workflow installs
`torch_directml` but does not explicitly install matching torchvision or
`onnxruntime-directml` (`.github/workflows/build-windows-directml.yml:41-45`).

The official Microsoft page currently states that `torch-directml` supports only
up to PyTorch 2.3.1, whereas Midgard fixes Torch 2.7.0
(`install.py:30-31`):
<https://learn.microsoft.com/en-us/windows/ai/directml/pytorch-windows>.
The plugin is therefore a separate, older compatibility island rather than
another backend for Midgard's current Torch lock.

The Docker workflow tries to build DirectML on `ubuntu-latest`
(`.github/workflows/build-docker.yml:24-40`), even though ONNX DirectML is a
Windows DirectX 12 provider:
<https://onnxruntime.ai/docs/execution-providers/DirectML-ExecutionProvider.html>.

PyTorch's official 2.7 instructions install macOS Torch/torchvision from the
default package index, not `https://download.pytorch.org/whl/cpu`; Midgard uses
the latter for every CPU platform (`install.py:623-630`). The runtime does detect
MPS (`backend/tools/hardware_accelerator.py:41-42`), but setup never selects or
validates it. PyTorch documents MPS as its macOS Metal backend:
<https://docs.pytorch.org/docs/stable/notes/mps.html>.

The bundled Linux FFmpeg is an x86-64 ELF and the bundled macOS FFmpeg is an
x86-64 Mach-O. `FFmpegCLI` selects these files solely by OS, with any non-Windows,
non-Linux system treated as macOS (`backend/tools/ffmpeg_cli.py:22-35`). Thus the
macOS Apple-silicon claim depends on Rosetta or replacement media tooling and is
not native end to end.

Paddle 3.0.0 does have Python 3.13 and macOS ARM64 artifacts on PyPI, but that
does not prove the combined PaddleOCR/PaddleX/Midgard path:
<https://pypi.org/project/paddlepaddle/3.0.0/>.

### Recommended backend policy

#### Recommendation

- Support Windows x86-64 CPU, Linux x86-64 CPU, and NVIDIA CUDA on those two
  platforms first.
- Keep each accelerator in a dedicated environment/constraint set.
- Mark DirectML as experimental and unavailable from the ordinary installer
  until a compatible Torch/torchvision/plugin set passes Midgard inference.
- Mark macOS/MPS as preview until native-architecture FFmpeg, PaddleOCR, Torch,
  ONNX CPU/CoreML behavior, and GUI startup all pass.
- Reject unsupported architecture/backend pairs before creating a venv.

## 4. Dependency ownership table

| Capability/import | Current owner | Pin quality | Finding |
|---|---|---|---|
| `torch`, `torchvision` | `install.py` constants and backend branch | Exact pair, index varies | Correct pair ownership, but absent from declarative manifests |
| `paddle`, `paddleocr`, `paddlex` | Paddle installed imperatively; PaddleOCR direct; PaddleX transitive | Paddle/PaddleOCR exact; PaddleX floats | Direct imports rely partly on a transitive dependency (`backend/tools/subtitle_detect.py:48-58`, `backend/tools/paddle_cdn_patch.py:16-21`) |
| `onnxruntime` | Imperative backend branch | CPU and Windows CUDA float; Linux CUDA partly exact | Backend variants are not mutually reconciled |
| `PySide6`, `qfluentwidgets`, `qframelesswindow` | Only `pyside6-fluent-widgets==1.7.7` declared | UI wrapper exact, its direct dependencies float | Midgard imports PySide6 directly (`gui.py:16-21`) and qframelesswindow directly (`gui.py:329`) but relies on transitive installation |
| OpenCV | `opencv-python==4.11.0.86` | Exact | Direct runtime dependency |
| Pillow | `Pillow` | Unpinned | Direct runtime dependency |
| NumPy/SciPy | `numpy>=2.2.5`, `scipy` | Broad/unpinned | Core numerical ABI is not constrained |
| PyAV | `av==17.0.0` | Exact | Optional vendored scene backend, but installed for everyone |
| MoviePy | Not declared | Missing/optional | Optional scene backend catches import failure (`backend/scenedetect/backends/__init__.py:92-100`) |
| imageio-ffmpeg | Not declared | Missing/optional | Optional vendored scene fallback (`backend/scenedetect/platform.py:244-266`) |
| rembg | `rembg>=2.0.60` in requirements and duplicated by installer | Broad | Backend-specific ORT is separately required |
| Transformers/HF | Lower bounds in requirements and duplicated by installer | No upper bounds | Current code contains 4.x/5.x compatibility branches (`backend/tools/grounded_sam2.py:223-277`) but no tested ceiling |
| Diffusers/Accelerate | Lower bounds in requirements and duplicated by installer | No upper bounds | Optional Generate feature; missing from inspected working environment |
| matplotlib/scikit-image | Root production requirements | Unpinned/broad | Used by inpaint/training utility code (`backend/inpaint/utils/sttn_utils.py:1-13`, `backend/inpaint/video/core/metrics.py:2-7`) |
| `pytest` | Not declared | Missing | Test suite imports it directly (`tests/test_enhance_denoise.py:1-10`) |
| `lpips`, `tensorboardX` | Commented out | Missing | Training code imports them (`backend/inpaint/video/core/loss.py:1-3`, `backend/tools/train/trainer_sttn.py:4-9`) |
| `click`, `platformdirs` | Not declared | Missing/optional | Used by vendored scene CLI, not the normal Midgard runtime (`backend/scenedetect/_cli/__init__.py:27`, `backend/scenedetect/_cli/config.py:25`) |
| `darkdetect` | Direct root requirement and UI-wrapper transitive | Unpinned | No direct repository import found; redundant unless intentionally owned |
| `requests` | Root requirement | Unpinned | Direct update-check dependency (`backend/tools/version_service.py:1-26`) |
| FFmpeg executable | Bundled under `backend/ffmpeg` | Binary provenance/version not declared in setup | Main media pipeline does not require system FFmpeg when the bundled binary runs |

### Missing, unused, and conflicting dependency conclusions

#### Verified facts

- Direct runtime imports of PySide6, qframelesswindow, and PaddleX are satisfied
  only transitively.
- Test and training dependencies are incomplete.
- Diffusers/Accelerate, rembg, Transformers, and Hugging Face Hub are declared
  twice (`requirements.txt:17-21`, `install.py:635-641`).
- Torch, torchvision, Paddle, and ONNX Runtime are not represented in a complete
  declarative environment.
- `darkdetect` has no direct repository import; the UI wrapper also declares it.

#### Probable findings

No dependency can be called safely removable solely from an import scan.
`darkdetect`, scikit-image, and media backends may be feature or transitive
requirements. Runtime import tracing and feature tests are needed before removal.

The most serious conflict is DirectML versus Torch 2.7. A second class of conflict
comes from co-installing multiple ORT or Paddle variants during mode changes.

## 5. Reproducibility and operational risks

| Severity | Risk | Evidence and effect |
|---|---|---|
| Critical | Docker can ingest ignored secrets and local state | There is no `.dockerignore`; `ADD . /midgard` copies the build context (`docker/Dockerfile:15`). `.gitignore` identifies local environments, config, and secret-bearing paths but does not protect Docker context (`.gitignore:1-45`). |
| High | No lock/constraints or hashes | Broad and unpinned root requirements (`requirements.txt:3-21`) and unpinned packaging-tool upgrades (`install.py:558-560`) make identical commits resolve differently over time. |
| High | Cross-backend environment contamination | Installer never reconciles mutually exclusive Paddle/ORT variants (`install.py:563-641`). |
| High | Interrupted venv bootstrap cannot self-heal | Existence of the venv Python is treated as sufficient, including after a failed `get-pip` bootstrap (`install.py:532-554`). |
| High | DirectML dependency line conflicts with core Torch | Runtime can use DML, but source installer cannot create it; vendor Torch support is older than Midgard's 2.7 baseline. |
| High | macOS support is advertised but incomplete | Generic CPU Torch index, no MPS setup/validation, no macOS CI, x86-64-only bundled FFmpeg (`README.md:12-15`, `install.py:623-630`, `backend/tools/ffmpeg_cli.py:32-35`). |
| High | Docker DirectML target is platform-invalid | Linux runner builds the DirectML branch (`.github/workflows/build-docker.yml:27-40`, `docker/Dockerfile:56-61`). |
| High | Docker default command cannot start useful work | It launches `backend/main.py` without required `--input` (`docker/Dockerfile:107`, `backend/tools/args_handler.py:15-32`). |
| High | Docker image build downloads model weights by default | `PREFETCH_MODELS=1` and the workflow force prefetch (`docker/Dockerfile:85-100`, `.github/workflows/build-docker.yml:90-93`), coupling image builds to large mutable external artifacts. |
| Medium | Supply-chain bootstrap is unverified | `get-pip.py` is downloaded and executed without a pinned digest (`install.py:547-554`). Alternate indexes and GitHub Actions are not locked by artifact hash/commit. |
| Medium | Repeated network and resolver work | Packaging tools are upgraded before each install group; feature packages are installed twice (`install.py:558-560`, `install.py:635-641`). |
| Medium | Validation can report success without usable GUI/OCR/FFmpeg/backend | Important imports and provider/device checks are absent (`install.py:644-676`). |
| Medium | Generated launchers and env are non-relocatable/drift-prone | Generator embeds a venv path (`install.py:896-917`); the ignored working-copy launcher already differs from current generator output. |
| Medium | Path compatibility is untested | No tracked path contains spaces or non-ASCII characters, and no workflow tests either case. |
| Medium | Windows media invocation is fragile | FFmpeg argument lists are passed with `shell=True` on Windows (`backend/main.py:431-455`), which changes quoting/executable semantics. |
| Medium | Windows Unicode fallback can return an empty short path | `GetShortPathNameW` return status is ignored (`backend/tools/common_tools.py:47-52`). Systems with disabled 8.3 names need runtime validation. |
| Medium | Docker base and system libraries float | `python:3.12` and apt packages are not digest/version pinned (`docker/Dockerfile:2-13`). |
| Medium | No source-install/test CI | Tracked Windows jobs build obsolete native deliverables; Docker job only builds/pushes. No workflow runs `install.py`, `pip check`, tests, or GUI/import smoke checks. |
| Low | Installer cleanup is scoped but destructive | On ensurepip failure it recursively removes all of `midgardEnv` (`install.py:541-545`), with no backup or identity check beyond the fixed path. |

### Paths with spaces and non-ASCII characters

#### Verified facts

Most installer subprocesses use argument lists and `pathlib`, and generated
launchers quote the working directory/interpreter (`install.py:87-89`,
`install.py:896-917`). This is positive static evidence for spaces.

The current tracked tree contains no path with spaces and no non-ASCII path, so
neither condition is exercised. OpenCV input handling uses `np.fromfile` for
images and attempts a Windows short path for video/OpenCV
(`backend/tools/common_tools.py:47-60`). FFmpeg writer commands use argument
lists (`backend/tools/video_io.py:58-81`).

#### Unknown

Installation, GUI launch, model cache operations, PaddleOCR, FFmpeg audio merge,
and output creation must be tested from paths containing spaces, accented
characters, CJK characters, and supplementary Unicode characters on each
supported OS.

## 6. Recommended dependency structure

### Recommendation

Use one source-of-truth input layer and generated, reviewable constraints:

```text
pyproject.toml                  Python policy and development-tool configuration
requirements/
  base.in                       portable direct runtime dependencies
  ui.in                         PySide6, fluent widgets, frameless window
  feature-ocr.in                PaddleOCR/PaddleX API ownership
  feature-remove-bg.in          rembg
  feature-select-object.in      transformers + Hugging Face Hub
  feature-generate.in           diffusers + accelerate
  backend-cpu.in                Paddle CPU, Torch CPU, torchvision, ORT CPU
  backend-cuda118.in            CUDA 11.8 Paddle/Torch/ORT tuple
  backend-cuda126.in            CUDA 12.6 Paddle/Torch/ORT tuple
  backend-cuda128.in            CUDA 12.8 Paddle/Torch/ORT tuple
  backend-directml.in           isolated Windows/Python 3.12 compatibility tuple
  backend-macos.in              macOS Torch/Paddle/ORT CPU tuple
  dev.in                        pytest and development tooling
  train.in                      lpips, tensorboardX, training-only dependencies
constraints/
  <os>-py312-<backend>.txt       generated complete constraints, preferably hashes
```

Principles:

1. Every direct import has one declared owner; do not rely on transitive
   installation for PySide6, qframelesswindow, or PaddleX.
2. Keep exactly one ORT distribution and one Paddle distribution per
   environment.
3. Keep Torch and torchvision as an inseparable tested pair.
4. Put optional heavyweight features in explicit groups; the ordinary
   application profile can still select all supported features.
5. Bound major versions until compatibility tests deliberately admit the next
   major.
6. Pin packaging bootstrap tools once per constraints release.
7. Treat vendor indexes as explicit artifact sources, not general dependency
   mirrors.
8. Generate locks in clean environments for every supported tuple and run
   `pip check` on the result.
9. Keep model manifests and model downloads separate from Python dependency
   resolution.

### Backend-specific flows

- **CPU:** exact Paddle CPU + exact Torch/torchvision CPU pair + exact ORT CPU.
- **CUDA:** choose one of cu118/cu126/cu128; resolve the entire tuple under one
  constraints file; validate both Torch CUDA and ORT CUDA providers. Document
  that Paddle is CPU-only for the 12.x profiles if that remains intentional.
- **DirectML:** dedicated Python 3.12 environment. Resolve the plugin's required
  Torch and matching torchvision first, then exact ORT DirectML. Do not combine
  it with the Torch 2.7 locks. Keep unavailable until Midgard feature tests pass.
- **macOS/MPS:** install the official macOS Torch wheels from the default index,
  exact CPU Paddle and ORT, then detect MPS at runtime. MPS is a Torch device;
  it is not a distinct ORT package. Validate CoreML separately before selecting
  that provider.

ONNX Runtime's official install guide distinguishes CPU, CUDA, and DirectML
Python distributions and notes the CUDA/cuDNN compatibility requirements:
<https://onnxruntime.ai/docs/install/>.

## 7. Recommended developer installation flow

### Recommendation

1. Clone or update a clean source checkout and confirm the exact commit.
2. Verify 64-bit CPython 3.12 before creating anything.
3. Select one explicit backend; never infer a developer environment silently.
4. Create `midgardEnv` with the chosen interpreter.
5. Install the pinned packaging bootstrap once.
6. Install one generated backend constraints set plus portable/UI/selected
   feature groups.
7. Install `dev` and, only when needed, `train`.
8. Run the environment validator: Python version/architecture, `pip check`,
   direct imports, Torch/torchvision pair, Paddle check, ORT provider, FFmpeg
   version/codec check, and a no-model GUI import smoke test.
9. Run unit tests that do not require large models.
10. Launch from source with the venv Python or generated SH/BAT launcher.

Developer setup must not rewrite `requirements.txt` with `pip freeze`. The
tracked Windows workflows currently do exactly that in their ephemeral checkout
(`.github/workflows/build-windows-cpu.yml:44-48` and corresponding CUDA/DirectML
workflows). Lock generation should be an explicit reviewed maintenance task.

## 8. Recommended Windows installation flow

### Ordinary user

1. Require 64-bit Python 3.12 and Windows 10/11 x86-64.
2. Run one source installer entry point from Command Prompt or PowerShell.
3. Offer explicit `cpu`, `cuda118`, `cuda126`, `cuda128`, and—only when
   qualified—`directml`; show the detected choice but require a deterministic
   noninteractive value for automation.
4. Create/reconcile `midgardEnv` transactionally.
5. Validate Microsoft Visual C++ runtime requirements for ORT and validate the
   bundled FFmpeg before declaring success. ONNX Runtime documents the Visual
   C++ 2019 runtime requirement: <https://onnxruntime.ai/docs/install/>.
6. Write a path-relative `run_gui.bat` that invokes the source checkout.
7. Seed model queue metadata only; make actual model downloads an explicit
   online first-run action.

### Backend notes

- CPU and CUDA must install mutually exclusive ORT variants.
- CUDA validation must compare the selected wheel, available driver, Torch
  device, and ORT provider.
- DirectML requires a DirectX 12-capable adapter and a dedicated older Torch
  lock. Midgard must not advertise it until full inference validation passes.
- Test both `cmd.exe` and PowerShell invocation, spaces, Unicode, and a user
  account without administrator rights.

## 9. Recommended Linux installation flow

### Ordinary user and production source checkout

1. Require 64-bit CPython 3.12 and a documented glibc/distribution baseline.
2. Document required Qt runtime libraries separately from Python packages. The
   Dockerfile currently installs `libgl1`, GLib, EGL, XKB, DBus, and XCB cursor
   libraries (`docker/Dockerfile:4-13`), but the README does not.
3. Select CPU or one NVIDIA CUDA tuple and install its complete constraints set.
4. Verify executable permission, architecture, version, and required codecs of
   the bundled FFmpeg.
5. Run post-install validation before writing the launcher/runtime success
   marker.
6. Launch the GUI with `run_gui.sh` or the CLI with the venv Python.

For production source deployment, use an immutable commit, a pre-resolved
wheelhouse or approved indexes, a non-root service account, explicit writable
config/output/model directories, and a supervised Python command. Do not make
Docker model prefetch part of the environment layer.

The current Dockerfile should not be considered a production source reference
until it has a `.dockerignore`, a non-root runtime user, a valid command contract,
model-download separation, immutable base selection, and source-install
validation (`docker/Dockerfile:2-15`, `docker/Dockerfile:82-107`).

## 10. Recommended macOS installation flow

### Recommendation

1. Initially label macOS unsupported/preview rather than generally supported.
2. Qualify Apple silicon and Intel separately; never select media binaries by OS
   alone.
3. Require Python 3.12 with architecture matching the intended dependency set.
4. Install Torch/torchvision using the official macOS/default-index pair, not
   the PyTorch Linux/Windows CPU index.
5. Install and validate a compatible Paddle/PaddleOCR/PaddleX CPU tuple and ORT
   CPU. Select MPS only when Torch reports both built and available, matching
   `HardwareAccelerator.check_mps_available()`
   (`backend/tools/hardware_accelerator.py:41-42`).
6. Supply or require a native FFmpeg for the host architecture and validate
   codecs before application success.
7. Test PySide6 GUI startup, file dialogs, model paths, subprocesses, image/video
   operations, and shutdown on both architectures.
8. Use the generated `run_gui.sh`; retain source execution.

### Unknown

PaddleOCR behavior, MPS operator coverage for every Midgard model, ORT CoreML
compatibility, and the feasibility/licensing of the current bundled FFmpeg need
controlled macOS validation.

## 11. Environment repair flow

### Recommended repair algorithm

1. Read the requested backend, interpreter version, architecture, and installed
   distributions without importing heavyweight models.
2. Classify the environment as healthy, incomplete, wrong Python, wrong backend,
   conflicting variants, or unknown.
3. If only a resumable package step is missing, reinstall from the exact
   constraints set and revalidate.
4. If Python, backend, ORT, Paddle, or Torch tuple differs, do not mutate the
   environment in place. Move the old environment to a clearly scoped backup,
   create a fresh `midgardEnv`, and retain the backup until validation succeeds.
5. Never delete configuration, output, downloaded models, or bundled model
   files during Python-environment repair.
6. Write the runtime marker and launcher only after every validation gate passes.
7. On failure, preserve a redacted diagnostic record and restore/retain the last
   known-good environment.

### Interrupted-install requirements

- Record stages such as `venv-created`, `pip-ready`, `deps-installed`,
  `validated`, and `launcher-written`.
- A venv Python executable alone must not count as health.
- Download bootstrap artifacts to a temporary file, verify a pinned digest, and
  clean them in `finally`.
- A repeated install against an already healthy environment must make no
  dependency changes.
- An interrupted run at every stage must either resume deterministically or
  explain that a clean environment rebuild is required.

### Offline limitations

Python dependencies can be installed offline only from a wheelhouse built for the
exact OS, architecture, Python, and backend tuple. CUDA/vendor-index artifacts
must be mirrored with hashes. Source distributions that require compilers or
system FFmpeg development libraries should be rejected from the ordinary
offline flow.

Model availability is separate. A dependency-only install can be offline, but
features whose weights are not already bundled or pre-provisioned cannot run.
The validator must report them as “model unavailable,” not “environment broken.”
No repair operation should silently begin a large model download.

## 12. Migration plan

### Phase 0 — Declare reality

- Make Python 3.12 x86-64 the initial production baseline.
- Document Windows/Linux CPU and NVIDIA CUDA as the first supported tuples.
- Mark DirectML and macOS/MPS preview/unsupported pending qualification.
- Remove native-build instructions from the supported source setup path
  (`README.md:261-269`).

### Phase 1 — Establish dependency ownership

- Introduce portable, feature, backend, development, and training input groups.
- Declare all direct imports.
- Generate exact constraints for each supported tuple.
- Establish upper bounds through compatibility evidence, not arbitrary latest
  resolution.

### Phase 2 — Make installation deterministic

- Validate version/OS/architecture/backend before venv creation.
- Bootstrap tooling once.
- Reconcile or rebuild incompatible environments instead of layering variants.
- Add an explicit `validate` and `repair` flow.
- Keep queue seeding separate from dependency installation and keep large model
  transfer opt-in.

### Phase 3 — Replace automation

- Add clean source-install CI for Python 3.12 on Windows and Linux CPU.
- Add dependency-resolution jobs for CUDA profiles and controlled hardware
  runtime gates.
- Add macOS Apple-silicon and DirectML jobs only when those profiles have
  coherent locks.
- Retire the tracked QPT/native-build jobs and `backend/tools/makedist.py` from
  supported automation. This is retirement of obsolete binary packaging, not a
  recommendation for a replacement binary format.

### Phase 4 — Harden deployment

- Add `.dockerignore` before any further container build.
- Separate dependency image layers from optional models.
- Pin base image digest and actions, run as non-root, and give the container a
  valid Python source command contract.
- Publish a support matrix and constraints provenance with each source release.

### Phase 5 — Expand support only through evidence

Promote Python 3.11/3.13, macOS/MPS, or DirectML only after the full acceptance
suite passes on representative hardware. Do not infer support from wheel
resolution alone.

## 13. Acceptance criteria

### Python and resolution

- [ ] The installer rejects every Python outside the documented range before
      creating or changing an environment.
- [ ] Python 3.12 latest patch is exercised on every supported OS/backend tuple.
- [ ] Every tuple installs from a complete reviewed constraints file.
- [ ] A second install produces no package change and performs no packaging-tool
      upgrade.
- [ ] `pip check` succeeds, and installed Torch/torchvision, Paddle, and ORT
      variants exactly match the selected tuple.
- [ ] Exactly one `onnxruntime*` and one `paddlepaddle*` distribution is present.

### Runtime validation

- [ ] GUI core imports, qfluentwidgets, qframelesswindow, PaddleOCR/PaddleX,
      Torch/torchvision, selected optional features, and FFmpeg validate.
- [ ] CPU validation proves CPU execution.
- [ ] CUDA validation proves both `torch.cuda.is_available()` and the expected ORT
      CUDA provider on representative hardware.
- [ ] DirectML validation, if offered, proves Torch DML and ORT DML can coexist
      for Midgard's actual workload.
- [ ] macOS validation proves native FFmpeg execution and MPS fallback behavior.
- [ ] No validation step downloads a large model.

### Reliability and paths

- [ ] Interrupting each installer stage leaves a state that either resumes or is
      safely rebuilt without touching models/config/output.
- [ ] Repair from CPU to CUDA and CUDA to CPU produces a clean tuple, not an
      overlaid environment.
- [ ] Install, launcher, GUI, image I/O, video/audio I/O, model cache, and output
      tests pass from paths containing spaces and representative non-ASCII text.
- [ ] Generated BAT/SH launchers remain source-based and use the selected local
      environment.
- [ ] Moving a checkout either triggers an explicit environment rebuild or
      continues only when validated; stale embedded paths are not accepted.

### CI, deployment, and security

- [ ] Linux and Windows source-install CI runs validation and model-free tests.
- [ ] Developer CI installs `pytest`; training CI installs its separate group.
- [ ] Docker build context excludes environments, configs, credentials, outputs,
      local media, and downloaded models.
- [ ] Docker dependency builds do not prefetch model weights and do not attempt
      DirectML on Linux.
- [ ] Production source deployment runs as a non-privileged account from an
      immutable source revision.
- [ ] No supported workflow produces or recommends a standalone executable,
      native bundle, or binary updater.

## Files inspected

### Present files

- `README.md`
- `.gitignore`
- `install.py`
- ignored generated `run_gui.sh`
- `requirements.txt`
- `docker/Dockerfile`
- `.github/workflows/build-docker.yml`
- `.github/workflows/build-windows-cpu.yml`
- `.github/workflows/build-windows-cuda-11.8.yml`
- `.github/workflows/build-windows-cuda-12.6.yml`
- `.github/workflows/build-windows-cuda-12.8.yml`
- `.github/workflows/build-windows-directml.yml`
- `backend/tools/makedist.py`
- `backend/main.py`
- `backend/config.py`
- `backend/tools/args_handler.py`
- `backend/tools/hardware_accelerator.py`
- `backend/tools/ffmpeg_cli.py`
- `backend/tools/video_io.py`
- `backend/tools/common_tools.py`
- `backend/tools/subtitle_detect.py`
- `backend/tools/paddle_cdn_patch.py`
- `backend/tools/grounded_sam2.py`
- `backend/tools/image_generate.py`
- `backend/tools/select_object_models.py`
- `backend/tools/generate_models.py`
- `backend/tools/version_service.py`
- `backend/tools/diag_health.py`
- vendored scene backend/FFmpeg resolution modules under `backend/scenedetect/`
- direct import sites under `backend/`, `ui/`, `gui.py`, and `tests/`
- bundled FFmpeg file formats/architectures under `backend/ffmpeg/`
- ignored virtual-environment version, selected installed-package metadata, and
  `pip check` result

### Requested files confirmed absent

- `AGENTS.md`
- `CONTRIBUTING.md`
- `install.bat`
- `install.sh`
- `run_gui.bat` in this Linux working copy
- `pyproject.toml`
- `setup.py`
- `setup.cfg`
- `.dockerignore`
- constraints, lock, developer-requirements, Pipfile, and Conda environment files

## Findings

1. Python 3.12 is the de facto baseline, but policy and enforcement disagree.
2. Installation is imperative, repeatedly upgrades its own tooling, and has no
   reproducible complete lock.
3. Existing environments are trusted by executable presence rather than health
   and can drift from current requirements.
4. CPU/CUDA transitions are not reconciled and can mix incompatible variants.
5. DirectML runtime code exists, but no coherent supported source dependency
   flow exists.
6. macOS/MPS is advertised without a validated installer or native media stack.
7. Direct runtime and development imports are missing from declared ownership.
8. Validation omits GUI, OCR, FFmpeg, and actual backend/provider checks.
9. Docker and tracked automation do not represent a safe, tested source
   deployment.

## Risks

The leading risks are non-reproducible resolution, wrong-backend imports after a
rerun, unrecoverable partial venv bootstrap, false install success, DirectML/Torch
incompatibility, incomplete macOS support, untested Unicode paths, and Docker
build-context exposure caused by the absent `.dockerignore`.

## Unresolved questions

1. Which OS/architecture/backend tuples does the project owner intend to support
   contractually for the next release?
2. Do all Midgard Torch models run correctly on the older Torch line required by
   `torch-directml`?
3. Can Torch DirectML and ORT DirectML 1.20.1 coexist reliably for subtitle
   detection and inpainting on both Windows 10 and 11?
4. Which exact Paddle/PaddleOCR/PaddleX versions are validated together for each
   Python and OS?
5. Does the bundled FFmpeg have documented version, codec, architecture, license,
   and reproducible provenance?
6. Can every feature run under the admitted Transformers 5.x and future
   Diffusers/rembg major versions?
7. What is the intended production Docker command and input/output volume
   contract?
8. Are Intel macOS systems a support target, or only Apple silicon?
9. Which dependencies are intentionally optional versus accidentally transitive?
10. What offline artifact retention and model-provisioning policy is required?

## Recommended next stage

Proceed to **Stage 2 — Dependency Resolution, Runtime Import, and Compatibility
Validation**. It should define the intended support tuples, build resolution-only
locks in clean temporary environments without downloading models, reconcile
direct imports with dependency ownership, and produce a model-free validation
matrix before any installer implementation is changed.
