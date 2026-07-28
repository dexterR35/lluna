# Stage 13 — Source Installation and Launcher Design

Baseline: `main` at `c7aa179`.

## Current flow

`python install.py` detects NVIDIA through `nvidia-smi`, asks for CPU/CUDA, locates Python 3.11–3.13, creates/reuses `midgardEnv`, installs framework wheels plus `requirements.txt`, verifies critical imports and bundled model parts, seeds deferred model downloads, writes runtime metadata, and generates one platform launcher.

Verified shortcomings:

- `install.bat` and `install.sh` are absent; `run_gui.bat` is absent from the tracked source.
- `run_gui.sh` assumes `midgardEnv/bin/python` exists and emits only the shell error.
- Python support is inconsistent: installer accepts 3.11–3.13 while roadmap and CI converge on 3.12.
- Existing environments are reused solely because their Python executable exists; interpreter version/backend integrity are not validated.
- Every package group repeatedly upgrades pip/setuptools/wheel.
- CPU/CUDA are supported; DirectML and macOS/MPS are not installer modes.
- broad dependency ranges and no constraints/lock make repeated installs non-reproducible.
- `verify_python_packages()` requires all large optional feature stacks, preventing a useful degraded install.
- installer writes launchers after the expensive install, so a failed install leaves no repair entry point.
- fallback pip bootstrap downloads executable Python code without a pinned hash.
- first launch can trigger multiple large model downloads despite the source-install requirement that optional models not download by default.
- `README.md` still documents QPT/Windows package builds and a public processing CLI.

## Compatibility matrix

| OS | CPU | CUDA | DirectML | MPS | Status |
|---|---|---|---|---|---|
| Windows 10/11 | intended | intended NVIDIA | code detects, installer absent | n/a | needs real matrix tests |
| Linux | intended | intended NVIDIA | n/a | n/a | current local launcher works |
| macOS | likely CPU | n/a | n/a | runtime detects | installer does not select/test MPS |

Python 3.12 is the canonical release version. Other versions may be developer best-effort only after CI proves framework wheels. A 64-bit interpreter is mandatory.

## Target user flows

### Windows

`install.bat` resolves `%~dp0`, locates `py -3.12`/`python`, invokes `install.py`, and returns its exit code. `run_gui.bat` resolves the root, validates `midgardEnv\Scripts\python.exe`, offers an actionable repair command, supports `--diag`, and preserves the app exit.

### Linux/macOS

`install.sh` resolves symlinks/script directory, finds Python 3.12, invokes `install.py`, and preserves status without requiring root. `run_gui.sh` performs the same environment validation and `exec`s the venv Python.

### Direct

`python install.py [--backend auto|cpu|cuda|directml|mps] [--yes] [--repair] [--validate-only]`, then `python gui.py` only when dependencies are installed in that interpreter.

## Dependency groups

- core runtime/UI/media;
- CPU frameworks;
- CUDA framework variants;
- Windows DirectML;
- macOS/MPS (standard Torch plus platform ORT);
- test;
- development/security.

Pin direct dependencies and publish constraints per supported platform/backend. Model downloads remain separate from Python installation and require user review.

## Idempotency and repair

Write an installation state file atomically with schema, Python ABI, OS/arch, backend, framework versions, and completion phase. On rerun, validate rather than assume; repair only failed/missing groups. Never delete a broad existing environment without explicit confirmation. Check disk, write access, FFmpeg, critical imports, and Qt offscreen startup. Interrupted dependency installs are rerunnable; pending model state is independent.

## Acceptance criteria

Quoted paths/non-ASCII roots, no admin/root, exact exit codes, actionable missing-Python/venv/FFmpeg errors, no automatic large models, repeat run is safe, offline limitations explicit, platform decisions unit-tested, and launchers tracked in source.

## Files inspected

`install.py`, `requirements.txt`, `run_gui.sh`, README, workflows, Dockerfile, FFmpeg/model assets, `.gitignore`.

Recommended next stage: source update design.
