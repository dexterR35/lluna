# Midgard Implementation Evidence

Date: 2026-07-28  
Baseline: local `main` at `c7aa179`

This report records implementation and verification against
`implementation-after-stages.md`. The audit reports were not rewritten.

## Result

The implementation reference is complete through Phases A–I:

| Phase | Implemented result |
|---|---|
| A — Safety baseline | Isolated pytest configuration, network/download blocking, fake hardware and model facilities, update mocks, and focused DirectML/configuration/model-policy tests. |
| B — Low-risk fixes | Reachable DirectML initialization with logged failure, deterministic DirectML → CUDA → MPS → CPU fallback, and canonical repository metadata. |
| C — Configuration boundary | Non-Qt build information, paths, environment, typed runtime configuration, precedence, migrations, schema validation, corrupt-file recovery, and atomic persistence. `backend.config` remains the GUI compatibility facade. |
| D — Hardware profile | Immutable normalized CPU, memory, GPU, provider, disk, FFmpeg, and framework-capability snapshot with caching, diagnostics, explicit confidence, and CPU fallback. |
| E — Execution/model policy | Hardware-aware backend selection, compatibility decisions, per-feature typed settings, presets, and visible configured/recommended/effective safety resolution. |
| F — Backend decomposition | Output, workspace, media, progress, model-path, subtitle-service, and pipeline responsibilities extracted. `backend/main.py` is now a deprecated import-only facade. |
| G — Desktop-only migration | GUI and worker callers use services; the public processing CLI/parser, CLI examples, obsolete QPT builder, and Docker packaging path were retired. |
| H — Dependency modernization | Python 3.12 policy, dependency groups, constraints, installer validation/repair, and quoted BAT/SH launchers with preserved exit codes. |
| I — Packaging/release | `midgard.py` desktop entry point, PyInstaller onedir specification, platform FFmpeg/resource selection, Linux desktop metadata, macOS bundle definition, and Windows/Linux/macOS build workflow. User-downloaded models are excluded. |

## Post-reference continuation

MODEL-02 is now partially implemented for direct Real-ESRGAN downloads:

- the central registry owns the pinned v0.2.1 x2 and v0.1.0 x4 artifact names,
  byte sizes, and SHA-256 digests;
- staged downloads must match both size and digest before atomic promotion;
- a failed verification cannot overwrite an existing model;
- installed Real-ESRGAN weights are verified again before PyTorch loads them;
- download cancellation and `.part` cleanup behavior remains compatible.

This does not close MODEL-01/MODEL-02. MIRNet, Hugging Face snapshots, rembg,
bundled weights/chunks, licenses, and source revisions still require reviewed
manifests and lifecycle integration. Real-ESRGAN release tags identify the
upstream assets, but upstream release notes do not provide a signed checksum
attestation.

## Verified and unconfirmed findings

Verified before implementation:

- `backend.config` mixed Qt settings, build metadata, paths, translations, and
  persistence at import time.
- DirectML detection contained unreachable behavior and suppressed its
  initialization failure.
- hardware probing and feature construction could repeat or block GUI startup;
- worker configuration depended on mutable process-global Qt state;
- `backend/main.py` combined pipeline, media, output, workspace, and CLI
  responsibilities;
- cancellation could not be consumed while the worker control loop was inside
  a synchronous job;
- dependency/backend variants and desktop release inputs were not separated.

Unconfirmed locally:

- real CUDA, DirectML, and MPS framework behavior;
- target-OS installer and package behavior;
- native cancellation latency inside each third-party model/framework;
- performance and integrity of production-size model artifacts.

The current verified backend priority is:
DirectML → CUDA → MPS → CPU. Disabling acceleration selects CPU explicitly.

## Implementation plan followed

Work followed Phases A through I in dependency order: safety tests, low-risk
metadata/DirectML fixes, pure configuration and path boundaries, normalized
hardware, model policy, backend service extraction, GUI-only migration,
dependency/installer modernization, then packaging/release definitions.
Compatibility facades were retained until callers had moved.

## Files changed

The implementation is grouped in:

- `backend/core`, `backend/configuration`, and `backend/diagnostics`;
- `backend/hardware`, `backend/models`, and `backend/settings`;
- `backend/application`, `backend/media`, `backend/services`, and
  `backend/pipelines`;
- worker/client, model download, hardware adapter, FFmpeg, update, onboarding,
  and legacy compatibility modules under `backend/tools`;
- `gui.py`, lazy/shared UI components, and migrated feature callers;
- `install.py`, BAT/SH installers and launchers, dependency/constraint files,
  and `pyproject.toml`;
- `.github/workflows`, `packaging`, README cleanup, and the safe test suite.

## Important behavior changes

- Importing core metadata, paths, configuration models, hardware models, or
  update logic does not initialize Qt or mutate user configuration.
- GUI startup creates a lightweight window shell first. Hardware probing,
  worker startup, health checks, stale-workspace cleanup, downloads, and
  update checks are deferred.
- Feature pages are constructed lazily.
- The inference client requires a worker handshake and reports startup
  failure. Cancellation and shutdown remain responsive while a job runs,
  and shutdown joins worker/control threads before forced termination.
- Subtitle jobs receive immutable validated settings snapshots rather than
  reading or mutating the Qt configuration in the worker.
- GUI configuration writes are atomic and malformed JSON is moved aside
  before defaults are loaded.
- Pending download state and tokens use application runtime paths and atomic
  writes. Partial downloads are recovered or cleaned by the lifecycle layer.
- Hardware facts are detected once per cached snapshot; execution policy is
  derived separately.

## Tests added

Coverage now includes:

- atomic state and corrupt-file recovery;
- configuration precedence, validation, migration, and Qt-free boundaries;
- DirectML success, absence, initialization failure, and fallback;
- CPU, CUDA, DirectML, MPS, ONNX, GPU fact, and diagnostic profiles;
- model inventory, integrity checks, download policy/recovery, settings, and
  hardware-aware policy, including fail-closed Real-ESRGAN promotion and
  pre-load verification;
- job protocol, worker handshake, startup failure, cancellation, repeated
  startup, shutdown, and callback cleanup;
- subtitle service validation/cancellation and FFmpeg/path boundaries;
- workspace cleanup, update states, onboarding state, launcher behavior,
  GUI-only entry points, packaging inputs, and lazy GUI shell behavior.

## Commands and results

| Command/check | Result |
|---|---|
| `python -m pytest -q` | **107 passed, 1 skipped** in 1.36 s. The skipped module is the host-interpreter GUI smoke because that interpreter has no PySide6. |
| Focused model-integrity/registry/policy suite | **14 passed** in 0.06 s. |
| Installed Real-ESRGAN x2 manifest verification | Passed against the local 67,061,725-byte artifact. |
| Focused configuration/hardware/worker/service/package suite | **32 passed** in 1.16 s. |
| Project Python 3.12 offscreen repeated QApplication/window smoke | Passed; two sequential windows, one QApplication, lazy pages initially unloaded; 1.27 s. |
| Project Python 3.12 offscreen lazy Upscale page smoke | Passed; page loaded on demand in 0.14 s. |
| Isolated qfluent configuration save | Passed; schema version 1 persisted atomically outside the repository/user configuration. |
| `python install.py --validate-only --yes` | Passed using the existing Python 3.12 environment. Required imports passed; Diffusers and Accelerate remain optional and unavailable locally. |
| `python packaging/build.py --validate-only` | Passed. |
| `midgardEnv/bin/python -m pip check` | Passed; no broken requirements. |
| `bash -n install.sh run_gui.sh` | Passed. |
| TOML parse and canonical version comparison | Passed; project and build version are both 1.4.0. |
| Workflow YAML parse | Passed. |
| `python -m compileall -q ...` | Passed. |
| `git diff --check` | Passed. |
| Ruff and pip-audit | Not available in the local host interpreter; both are defined in CI. |

No network access, large model download, model rewrite, production inference,
or native package creation was performed.

## Platform evidence

Real local coverage:

- Linux x86-64;
- CPU fallback;
- Python 3.12 project environment for Qt/application smoke tests;
- host Python for the safe non-GUI test suite;
- FFmpeg discovery and source-installer validation.

Mocked deterministic coverage:

- CUDA unavailable and available;
- DirectML absent, successful, and initialization failure;
- MPS unavailable and available;
- ONNX Runtime absent, CPU-only, and accelerator-provider states;
- low, medium, high, unknown, and partially detected hardware resources;
- worker startup failure, cancellation, and shutdown while work is active;
- missing/corrupt configuration, missing models, pending downloads, offline
  updates, and optional dependency absence.

Still requires target-platform execution:

- Windows CPU, CUDA, and DirectML installation and real inference;
- NVIDIA CUDA inference and OOM behavior on supported driver generations;
- Apple Silicon MPS installation, inference, memory pressure, and cleanup;
- actual Windows, Linux, and macOS package builds/signing;
- clean-machine and path-with-spaces installation;
- remote CI execution.

## Compatibility and remaining risks

- The Qt `backend.config` facade intentionally remains for existing GUI
  callers; new worker/core code uses immutable snapshots.
- Model managers are not yet fully unified behind one transactional manager,
  and verified SHA-256/license/version metadata is incomplete for several
  third-party artifacts.
- Native framework calls may not stop immediately after cancellation; the
  control plane remains responsive and shutdown has a forced-termination
  fallback.
- Some legacy UI/model modules still contain broad exception handlers.
  Lifecycle boundaries now log actionable failures, but a separate focused
  cleanup is still warranted.
- The full Jobs/onboarding/accessibility designs are not part of the A–I
  implementation reference and are not presented as complete UI features.
- Packaging definitions are validated statically and in tests, but no local
  native artifact was produced because PyInstaller is not installed.

Remaining canonical Midgard repository URL inconsistencies: none found.
Third-party source and model URLs remain intentionally local to their
respective integrations.

## Rollback

The work is separable by boundary:

1. Keep `backend.config`, `backend.main`, and model-config compatibility
   facades while reverting individual consumers.
2. Revert `midgard.py`/launcher entry changes independently from service code.
3. Revert deferred/lazy GUI construction without changing worker protocol.
4. Revert worker handshake/control changes together with their protocol tests.
5. Remove packaging definitions without affecting the source workflow.

User configuration, installed models, tokens, downloads, and output media
must be preserved during any rollback.

## Release position

The implementation-reference scope is complete and locally verified.
Multi-platform production certification remains conditional on target
hardware tests, remote CI, model provenance/checksums, and signed package
builds.
