# Midgard Principal Engineering Implementation Prompt

You are a principal Python engineer and AI desktop-application architect working on the Midgard repository.

## Official repository

```text
https://github.com/dexterR35/midgard
```

The canonical repository identity is:

```text
Owner: dexterR35
Repository: midgard
```

Use this repository identity for:

* project metadata;
* issue links;
* release links;
* GitHub API calls;
* update checks;
* packaging metadata;
* documentation;
* diagnostics.

Do not use `midgard-app/midgard` unless repository evidence proves that it remains intentionally required for a specific compatibility purpose.

---

# Product direction

Midgard is a desktop GUI application built with PySide6.

The product will be distributed and maintained as a desktop application.

The public command-line interface is not part of the future product.

However, desktop-only does not mean backend-free.

Keep and improve the reusable backend systems required by the GUI, including:

* inference workers;
* AI pipelines;
* model loading;
* model unloading;
* model caching;
* hardware detection;
* media decoding;
* media encoding;
* video processing;
* image processing;
* download services;
* update services;
* job scheduling;
* progress reporting;
* cancellation;
* resource cleanup;
* configuration;
* logging;
* diagnostics.

Do not remove the entire `backend/` package.

Do not move backend processing logic directly into PySide6 widgets.

The required dependency direction is:

```text
PySide6 Desktop GUI
        |
        v
Application Services
        |
        v
Inference and Job Layer
        |
        v
Media and AI Pipelines
        |
        v
Model Management
        |
        v
CUDA / DirectML / MPS / ONNX / CPU
```

UI components must not directly own:

* model initialization;
* GPU allocation;
* video decoding;
* model download logic;
* temporary-file lifecycles;
* inference orchestration;
* subprocess management.

---

# Primary objective

Address verified architecture, reliability, packaging, configuration, hardware, and maintainability findings incrementally.

Do not perform a broad rewrite.

Do not replace working foundations unless a verified defect requires it.

Preserve and stabilize:

* the shared inference worker;
* GPU busy-state coordination;
* sequential model download queue;
* model download lifecycle management;
* OOM retry behavior;
* frame prefetching;
* CPU fallback;
* cancellation support;
* process registration;
* worker shutdown;
* application shutdown;
* current model-cache behavior where valid.

---

# General engineering rules

1. Inspect the current repository before changing anything.
2. Read `AGENTS.md`, `CONTRIBUTING.md`, and other repository-local instructions first.
3. Verify every reported issue against the current branch.
4. Do not assume a previously reported issue still exists.
5. State which findings were confirmed before editing.
6. Create or update tests before changing critical behavior.
7. Preserve desktop GUI behavior.
8. Preserve reusable backend behavior required by the GUI.
9. The public CLI does not need to remain supported.
10. Preserve Windows, Linux, and macOS behavior unless evidence shows a platform is unsupported.
11. Do not download large AI models.
12. Do not delete or alter bundled model files.
13. Do not expose Hugging Face tokens, secrets, credentials, or private environment values.
14. Avoid unrelated formatting or cleanup.
15. Use small, independently reviewable changes.
16. Do not combine unrelated architectural work into one pull request.
17. Run focused tests after each change.
18. Run broader safe tests before completing a phase.
19. Use mocks and fakes for GPU hardware, model loading, network calls, downloads, and update checks.
20. Do not claim hardware support was tested unless it was tested on real hardware.
21. Preserve compatibility adapters during migrations.
22. Do not introduce unnecessary frameworks.
23. Do not run destructive Git commands.
24. Do not modify generated virtual environments.
25. Do not modify user configuration during tests.
26. Prevent tests from performing network access by default.
27. Prevent tests from downloading production models.
28. Keep changes reversible.
29. Document pre-existing failures separately from regressions introduced by the change.
30. Do not silently bypass failing tests.

Before modifying code, report:

* verified findings;
* files to be changed;
* intended behavior;
* compatibility risks;
* planned tests;
* explicit non-goals.

After modifying code, report:

* files changed;
* behavior before and after;
* commands run;
* test results;
* platforms tested;
* platforms represented only by mocks;
* unresolved risks;
* recommended next pull request.

---

# Verified findings to investigate and address

## 1. Qt-coupled configuration

`backend.config` currently appears to combine multiple unrelated responsibilities:

* importing `qfluentwidgets`;
* loading `config/config.json`;
* loading translations;
* defining version information;
* defining repository URLs;
* setting environment variables;
* exposing runtime settings;
* exposing model settings;
* exposing hardware settings;
* exposing GUI preferences.

This may force backend services, inference workers, tests, and headless processing modules to depend on Qt.

Midgard is desktop-only, but its backend services and worker processes should still remain independent from GUI frameworks where possible.

### Required investigation

Map every import of:

```python
backend.config
```

Classify each consumer as:

* UI;
* application service;
* inference worker;
* model manager;
* download manager;
* media pipeline;
* installer;
* packaging;
* update service;
* test;
* other.

Identify which values belong to:

* build metadata;
* repository metadata;
* paths;
* runtime settings;
* model policy;
* hardware policy;
* GUI preferences;
* translations;
* secrets;
* transient state;
* environment setup.

### Target design

Separate concerns incrementally:

```text
backend/
  core/
    build_info.py
    paths.py
    environment.py
  config/
    runtime.py
    models.py
    hardware.py
    gui.py
    loader.py
    migrations.py
  i18n/
    translations.py
```

Adapt the names to the repository’s existing conventions.

Do not migrate all settings in one pull request.

Keep `backend.config` temporarily as a compatibility facade if needed.

Backend services that need only paths, version information, or repository metadata must not import Qt.

---

## 2. Canonical repository identity

The official repository is:

```text
https://github.com/dexterR35/midgard
```

Canonical metadata must be derived from:

```python
GITHUB_OWNER = "dexterR35"
GITHUB_REPOSITORY = "midgard"
```

Expected derived URLs:

```python
PROJECT_HOME_URL = "https://github.com/dexterR35/midgard"
PROJECT_ISSUES_URL = "https://github.com/dexterR35/midgard/issues"
PROJECT_RELEASES_URL = "https://github.com/dexterR35/midgard/releases"
LATEST_RELEASE_API_URL = (
    "https://api.github.com/repos/"
    "dexterR35/midgard/releases/latest"
)
```

### Required work

Search the repository for:

* `midgard-app/midgard`;
* `dexterR35/midgard`;
* hardcoded GitHub API URLs;
* hardcoded releases URLs;
* hardcoded issues URLs;
* repository references in packaging;
* repository references in documentation;
* repository references in updater code.

Centralize repository metadata in one non-Qt module.

Derive URLs rather than duplicating strings.

Add tests for all generated URLs.

Do not redesign the entire updater during this change.

---

## 3. Dependency reproducibility

Current dependency handling appears split across:

* `requirements.txt`;
* `install.py`;
* Docker files;
* packaging scripts;
* dynamic installer logic;
* backend-specific package installation.

Some dependencies are pinned while others are not.

Torch, torchvision, Paddle, and ONNX Runtime variants may be selected outside the main requirements file.

### Required audit

Inspect:

* `requirements.txt`;
* all other requirements files;
* `pyproject.toml`;
* `setup.py`;
* `setup.cfg`;
* `install.py`;
* Docker files;
* QPT or PyInstaller files;
* Nuitka files;
* build scripts;
* launch scripts;
* GitHub workflows;
* runtime imports.

Identify:

* unpinned dependencies;
* broad lower bounds;
* imported but undeclared packages;
* declared but unused packages;
* dynamically installed packages;
* platform-specific packages;
* packaging-only dependencies;
* test dependencies;
* Torch variants;
* Paddle variants;
* ONNX Runtime CPU/GPU/DirectML variants;
* CUDA wheel selection;
* macOS dependencies;
* FFmpeg assumptions.

### Target direction

Introduce a professional but incremental dependency structure.

Possible structure:

```text
pyproject.toml
requirements/
  base.in
  test.in
  dev.in
  packaging.in
  cpu.in
  cuda.in
  directml.in
  macos.in
constraints/
  python312.txt
```

Use another layout if better suited to the repository.

Separate:

* base runtime dependencies;
* backend-specific dependencies;
* platform-specific dependencies;
* test dependencies;
* development dependencies;
* packaging dependencies.

Do not blindly upgrade packages.

Do not remove the existing installer until its replacement is tested.

---

## 4. Python-version compatibility

The README may advertise Python 3.12+, while the installer may fall back to Python 3.11 or Python 3.13.

Determine actual support using:

* dependency metadata;
* available wheels;
* CI;
* installer logic;
* PySide6 compatibility;
* Paddle compatibility;
* Torch compatibility;
* ONNX Runtime compatibility;
* Diffusers compatibility;
* Transformers compatibility;
* PyAV compatibility;
* native build requirements.

### Required result

Classify Python versions as:

* officially supported;
* experimentally supported;
* unsupported;
* untested.

Prefer Python 3.12 as the canonical development and release version unless evidence shows otherwise.

Do not claim support for Python 3.11 or Python 3.13 without verification.

Update installer validation and README claims only after completing the compatibility audit.

---

## 5. Silent exception suppression

Search the entire repository for:

```python
except:
    pass
```

```python
except Exception:
    pass
```

```python
except Exception as exc:
    pass
```

Also inspect exception handling in:

* GUI startup;
* GUI shutdown;
* inference workers;
* model downloads;
* update checks;
* hardware detection;
* model unloading;
* temporary-file deletion;
* video capture;
* video writers;
* FFmpeg subprocesses;
* token handling;
* model authentication;
* model cache cleanup.

Classify each instance as:

* intentional best effort;
* optional-feature failure;
* user-visible failure;
* developer diagnostic;
* worker failure;
* shutdown cleanup;
* security-sensitive failure.

### Required behavior

For best-effort operations:

* log at DEBUG or WARNING;
* include safe context;
* avoid repeated noise.

For user-impacting failures:

* raise or propagate a typed error;
* show a user-readable message;
* keep detailed logs for developers.

Never log tokens or secrets.

Do not replace every broad exception in one pull request.

---

## 6. Desktop-only product and CLI retirement

Midgard will be GUI-only.

The public CLI must be retired.

However, `backend/main.py` may contain both CLI behavior and reusable processing code.

Do not delete it until reusable logic has been extracted.

### Required investigation

Map all responsibilities in `backend/main.py`:

* CLI argument parsing;
* task selection;
* input validation;
* media opening;
* video decoding;
* temporary files;
* output paths;
* subtitle detection;
* model selection;
* model initialization;
* inference;
* batching;
* progress reporting;
* cancellation;
* preview callbacks;
* audio merging;
* result writing;
* cleanup;
* `sys.path` modification;
* wildcard imports.

Locate every use of:

```python
backend.main
```

and:

```python
SubtitleRemover
```

Determine whether callers include:

* GUI widgets;
* application controllers;
* threads;
* inference workers;
* services;
* tests;
* packaging scripts.

### Target architecture

Extract reusable processing into backend services.

A possible incremental structure:

```text
backend/
  services/
    subtitle_removal.py
  media/
    video_reader.py
    video_writer.py
    output_paths.py
    workspace.py
  pipelines/
    remove_text.py
  inference/
    jobs.py
    progress.py
```

The final structure must fit the repository rather than being imposed mechanically.

The extracted processing service must not:

* parse CLI arguments;
* call `sys.exit`;
* modify `sys.path`;
* require a terminal;
* rely on `tqdm` as its main progress interface;
* directly manipulate PySide6 widgets;
* require a running `QApplication`;
* print directly as its main reporting mechanism.

Use:

* structured callbacks;
* progress events;
* cancellation tokens;
* job IDs;
* typed results;
* typed errors.

### Safe extraction sequence

1. Output-path generation.
2. Temporary workspace lifecycle.
3. Media resource lifecycle.
4. Progress reporting.
5. Model selection.
6. Subtitle-removal orchestration.
7. GUI and worker caller migration.
8. CLI parser removal.
9. CLI documentation removal.
10. `backend/main.py` deletion or conversion into a compatibility wrapper.

### CLI removal requirements

After reusable processing is extracted:

* remove CLI argument parsing;
* remove CLI examples from README;
* remove CLI launcher references;
* remove CLI packaging entry points;
* remove terminal-specific progress behavior;
* stop testing CLI compatibility;
* remove `backend/main.py` if it no longer contains runtime logic.

Do not remove backend application services.

---

## 7. Broad responsibilities in `backend/main.py`

Even apart from CLI retirement, `backend/main.py` appears to act as a large orchestration module.

It may own:

* media I/O;
* model lifecycle;
* subtitle detection;
* temporary files;
* batching;
* output paths;
* progress;
* audio merging;
* cleanup;
* pipeline selection.

### Required improvement

Decompose the module incrementally.

One coherent responsibility per pull request.

Do not rewrite everything at once.

Each extraction must have characterization tests before moving code.

Remove wildcard imports only when direct imports are validated.

Remove `sys.path` modification only when package execution and packaging still work.

Preserve existing output behavior and media quality.

---

## 8. Normalized hardware profile

Current hardware detection appears capability-oriented but incomplete.

Introduce an immutable normalized profile.

Example:

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class HardwareProfile:
    os_name: str
    os_version: str
    architecture: str
    cpu_model: str | None
    physical_cores: int | None
    logical_threads: int | None
    total_ram_mb: int | None
    available_ram_mb: int | None
    gpu_vendor: str | None
    gpu_model: str | None
    total_vram_mb: int | None
    available_vram_mb: int | None
    gpu_driver_version: str | None
    cuda_available: bool
    torch_cuda_version: str | None
    directml_available: bool
    mps_available: bool
    onnx_providers: tuple[str, ...]
    supported_backends: tuple[str, ...]
```

Adapt fields based on actual repository needs.

### Required detection

CPU:

* vendor;
* model;
* physical cores;
* logical threads.

Memory:

* total RAM;
* available RAM;
* swap if safely available.

GPU:

* vendor;
* model;
* VRAM;
* free VRAM;
* driver;
* CUDA capability;
* DirectML;
* MPS;
* ONNX providers.

System:

* operating system;
* architecture;
* Python architecture;
* disk availability;
* FFmpeg availability.

### Design rule

Separate detection from policy.

```text
HardwareDetector
        |
        v
HardwareProfile
        |
        v
ExecutionPolicy
```

The detector reports facts.

The policy makes recommendations.

Do not break current `HardwareAccelerator` callers.

Use an adapter during migration.

Detection failure must degrade to an explicit CPU profile.

---

## 9. DirectML unreachable code

Inspect the DirectML device path.

Verify whether code appears after an unconditional return:

```python
return torch_directml.device(torch_directml.default_device())
self.__dml = True
```

Also inspect the bare exception handler.

### If confirmed

* remove unreachable code;
* replace the bare exception with appropriate exceptions;
* log safe diagnostic context;
* mark DirectML unavailable after initialization failure;
* continue fallback evaluation;
* preserve existing backend priority unless evidence supports changing it.

Expected behavior:

```text
DirectML initializes
    -> DirectML device

DirectML detected but initialization fails
    -> log warning
    -> disable DirectML for current process
    -> try CUDA
    -> try MPS
    -> use CPU

DirectML unavailable
    -> try CUDA
    -> try MPS
    -> use CPU
```

Add tests using mocked modules.

Do not require DirectML hardware in CI.

---

## 10. Hardware-aware model settings

Current defaults may be unsafe for common hardware.

ProPainter may default to a high frame count even though documented memory use can exceed the VRAM available on consumer GPUs.

Audit memory-sensitive options for:

* ProPainter;
* STTN;
* image generation;
* Real-ESRGAN;
* MIRNet;
* SAM2;
* Grounding DINO;
* PaddleOCR;
* rembg;
* model caching.

### Required policy

Distinguish between:

* configured value;
* recommended value;
* maximum safe value;
* effective value.

Example:

```text
Configured: 70
Recommended: 24
Maximum safe: 32
Effective: 32
Reason: available VRAM is below the requirement for 70 frames
```

Consider:

* total VRAM;
* available VRAM;
* input dimensions;
* selected model;
* precision;
* cached models;
* execution backend;
* user override.

Do not silently change safe user choices.

If a value must be clamped:

* log the reason;
* display a user-readable message;
* make the behavior deterministic;
* add tests.

Test profiles:

* CPU-only;
* unknown hardware;
* low VRAM;
* medium VRAM;
* high VRAM;
* DirectML;
* MPS;
* explicit safe override;
* explicit unsafe override;
* different video resolutions.

---

## 11. Logging and error handling

Design a professional logging layer before large refactoring.

Required levels:

* DEBUG;
* INFO;
* WARNING;
* ERROR;
* CRITICAL.

Structured context may include:

* session ID;
* process ID;
* thread;
* job ID;
* feature;
* model ID;
* backend;
* device;
* elapsed time;
* safe memory statistics;
* error type.

Do not log:

* tokens;
* secrets;
* complete private environment values;
* sensitive file contents.

Create a typed exception hierarchy for:

* configuration;
* dependency;
* hardware;
* model installation;
* model verification;
* model loading;
* inference;
* cancellation;
* media decoding;
* output writing;
* download;
* update.

Separate user-facing errors from developer diagnostics.

---

## 12. Test architecture

Create a reliable safety baseline before major structural changes.

Recommended structure:

```text
tests/
  unit/
  integration/
  characterization/
  gui/
  inference/
  hardware/
  models/
  media/
  packaging/
  fixtures/
  fakes/
```

Recommended tools where appropriate:

* pytest;
* pytest-cov;
* pytest-qt;
* pytest-timeout;
* pytest-mock;
* pytest-xdist;
* pytest-benchmark.

Standard tests must:

* run without a GPU;
* run without model downloads;
* block network access;
* avoid user configuration;
* avoid real update checks;
* use small generated fixtures;
* mock heavy models.

Add markers:

```text
unit
integration
gui
hardware
network
gpu
cuda
directml
mps
slow
model_download
packaging
```

Hardware-specific tests must be separate from normal CI.

---

# Required implementation phases

## Phase A — Safety baseline

Implement:

* test infrastructure;
* network blocking;
* fake hardware profiles;
* model-loading fakes;
* update-check mocks;
* DirectML tests;
* repository metadata tests;
* configuration import-boundary tests;
* safe model-policy tests.

Do not begin major refactoring until this phase is stable.

---

## Phase B — Low-risk fixes

Implement only confirmed low-risk fixes:

* DirectML unreachable code;
* DirectML exception handling;
* deterministic fallback behavior;
* canonical repository metadata;
* derived GitHub URLs;
* targeted logging for silent failures;
* documentation corrections backed by evidence.

---

## Phase C — Configuration boundary

Extract:

* build metadata;
* repository metadata;
* application paths;
* environment initialization;
* non-GUI runtime settings.

Keep compatibility imports.

Do not migrate all GUI settings at once.

---

## Phase D — Hardware profile

Introduce:

* normalized hardware profile;
* hardware detector;
* compatibility adapter;
* explicit CPU fallback;
* diagnostic output.

---

## Phase E — Execution and model policy

Add:

* hardware-aware recommendations;
* safe limits;
* user override validation;
* diagnostic explanations;
* model compatibility decisions.

---

## Phase F — Backend decomposition

Extract responsibilities from `backend/main.py` one at a time:

1. output paths;
2. workspace handling;
3. media lifecycle;
4. progress events;
5. model selection;
6. subtitle-removal service;
7. pipeline orchestration.

---

## Phase G — Desktop-only migration

After backend callers have migrated:

* update GUI callers;
* update inference-worker callers;
* remove CLI parser;
* remove CLI documentation;
* remove CLI packaging;
* remove CLI launch commands;
* delete or deprecate `backend/main.py`.

---

## Phase H — Dependency modernization

After tests and boundaries are stable:

* add or improve `pyproject.toml`;
* separate dependency groups;
* define supported Python versions;
* create backend-specific constraints;
* add lock-generation documentation;
* preserve installer compatibility during migration.

---

## Phase I — Packaging and release

Design and implement incrementally:

* desktop entry point;
* Windows package;
* Linux package;
* macOS package;
* assets handling;
* FFmpeg handling;
* versioning;
* release metadata;
* update compatibility.

Do not combine this with model-pipeline refactoring.

---

# First implementation session

Complete only:

* Phase A;
* the DirectML portion of Phase B;
* canonical repository metadata from Phase B.

Do not begin:

* CLI removal;
* `backend/main.py` decomposition;
* full configuration migration;
* dependency modernization;
* model-default changes;
* packaging redesign;
* updater redesign.

## Exact first-session tasks

1. Inspect repository-local instructions.
2. Inspect the current test structure.
3. Map current hardware backend priority.
4. Map all DirectML-related code.
5. Verify unreachable code.
6. Verify bare exception usage.
7. Inspect existing logging utilities.
8. Locate every repository URL and GitHub API URL.
9. Add safe test fixtures and mocks.
10. Create a concise implementation plan.
11. Implement only the confirmed low-risk changes.
12. Run focused tests.
13. Run safe broader tests.

## DirectML tests

Mock:

* DirectML package missing;
* DirectML available;
* DirectML initialization succeeds;
* DirectML initialization fails;
* CUDA unavailable;
* CUDA available;
* MPS unavailable;
* MPS available;
* ONNX Runtime unavailable;
* ONNX CPU provider only;
* ONNX accelerator provider available.

Tests must run without real GPU hardware.

## Metadata tests

Test:

* GitHub owner;
* repository name;
* project URL;
* issue URL;
* release URL;
* latest-release API URL.

## Explicit non-goals for the first session

Do not:

* remove CLI code;
* delete `backend/main.py`;
* change model defaults;
* change ProPainter values;
* alter dependency files;
* redesign configuration;
* create a new installer;
* migrate into a `src/` layout;
* replace the inference worker;
* change GPU queue behavior;
* change download behavior;
* update unrelated exception handlers;
* download models;
* broadly reformat files.

---

# Completion report format

Provide:

1. Verified findings.
2. Unconfirmed findings.
3. Current backend priority.
4. Implementation plan followed.
5. Files changed.
6. Tests added.
7. Behavior before.
8. Behavior after.
9. Commands run.
10. Test results.
11. Real platforms tested.
12. Mocked platforms tested.
13. Known limitations.
14. Remaining repository URL inconsistencies.
15. Remaining silent exception handlers.
16. Recommended next pull request.

Keep the change small, focused, reversible, and reviewable.
