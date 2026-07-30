# Midgard Senior Engineering Roadmap and Codex Prompt Set

## Repository

```text
https://github.com/dexterR35/midgard
```

Canonical identity:

```text
Owner: dexterR35
Repository: midgard
```

## Product direction

Midgard is a source-based PySide6 desktop application.

Supported installation and launch methods:

```text
Windows:
  install.bat
  run_gui.bat

Linux/macOS:
  ./install.sh
  ./run_gui.sh

Direct Python:
  python install.py
  python gui.py
```

Do not create or recommend:

* EXE files;
* MSI installers;
* PyInstaller;
* Nuitka;
* QPT;
* Briefcase;
* AppImage;
* DEB or RPM packages;
* macOS application bundles;
* DMG files;
* bundled Python executables;
* binary self-updaters.

The public media-processing CLI should eventually be retired, but reusable backend services must remain.

Do not remove:

* backend processing services;
* inference workers;
* model management;
* hardware detection;
* model downloads;
* media pipelines;
* installation scripts;
* GUI startup scripts;
* internal worker entry points;
* diagnostic tools required by developers.

---

# Required execution order

Run each stage in a separate Codex session.

Do not ask Codex to perform all stages at once.

```text
Stage 0   Repository discovery
Stage 1   Environment and installation audit
Stage 2   Startup lifecycle
Stage 3   Configuration architecture
Stage 4   Hardware detection
Stage 5   AI model management
Stage 6   AI pipeline architecture
Stage 7A  Model settings and preset architecture
Stage 7B  User experience and interface audit
Stage 7C  First-run onboarding and model setup
Stage 7D  Accessibility and desktop usability
Stage 7   Python architecture review
Stage 8   Production bug audit
Stage 9   Security audit
Stage 10  Logging and error handling
Stage 11  Testing strategy
Stage 12  Performance audit
Stage 13  Source installation and launchers
Stage 14  Source-based update system
Stage 15  CI/CD pipeline
Stage 16  Future AI infrastructure
Stage 17  Production-readiness review
Stage 18  Consolidated implementation backlog
Stage 19  Implementation Phase A
Stage 20  Implementation Phase B
Stage 21  Implementation Phase C
Stage 22  Implementation Phase D
Stage 23  Implementation Phase E
Stage 24  Implementation Phase F
Stage 25  Implementation Phase G
Stage 26  Implementation Phase H
Stage 27  Final verification
```

Stages 7A–7D are additive labels inserted after Stage 6. Existing Stage 7–27
labels and report names remain unchanged.

Stages 0–18 are primarily read-only.

Stages 19–27 may modify code.

---

# Rules for all audit stages

Use these rules at the beginning of Stages 0–18:

```text
You are working on:

https://github.com/dexterR35/midgard

Do not modify code in this stage.

Inspect the current branch before making conclusions.

Read repository-local instructions such as AGENTS.md and CONTRIBUTING.md first.

Cite exact files, classes, functions, and line numbers.

Separate:
- verified facts;
- probable findings;
- recommendations;
- unknowns requiring runtime verification.

Do not download large AI models.

Do not expose tokens, credentials, environment secrets, or private paths.

Do not delete or alter bundled model files.

Do not recommend EXE, MSI, PyInstaller, Nuitka, QPT, Briefcase, AppImage, DMG, DEB, RPM, native application bundles, or binary auto-updaters.

Midgard must remain source-based and launch through Python, BAT, or SH scripts.

Save the report as:

docs/audits/stage-XX-<name>.md

At the end provide:
- files inspected;
- findings;
- risks;
- unresolved questions;
- recommended next stage.
```

---

# Stage 0 — Repository Discovery and Technical Mapping

```text
You are a principal Python and AI desktop-application architect.

Perform a complete read-only technical discovery of the Midgard repository.

Do not modify any file.

Inspect at minimum:

- README.md
- LICENSE
- gui.py
- install.py
- install.bat
- run_gui.bat
- install.sh
- run_gui.sh
- requirements.txt
- all requirements and constraints files
- pyproject.toml
- setup.py
- setup.cfg
- Docker files
- GitHub workflows
- backend/main.py
- backend/config.py
- all backend packages
- all UI packages
- inference client and worker modules
- hardware-detection modules
- model registries
- download managers
- update-checking code
- FFmpeg wrappers
- video and image I/O
- tests
- configuration files
- translation files
- model manifests
- packaging or obsolete executable-build scripts

Trace all entry points:

- python gui.py
- run_gui.bat
- run_gui.sh
- python install.py
- install.bat
- install.sh
- backend/main.py
- inference workers
- model download workers
- update checks
- shutdown paths

Produce:

1. Application overview.
2. Project purpose.
3. Current repository tree.
4. Entry-point map.
5. Module-responsibility table.
6. GUI startup sequence.
7. Installer sequence.
8. Inference job sequence.
9. Model download sequence.
10. Shutdown sequence.
11. Current architecture diagram in Mermaid.
12. Current architecture diagram in plain text.
13. Thread and process model.
14. Configuration source map.
15. Storage and filesystem map.
16. External service and download-host inventory.
17. Model inventory.
18. Dependency-direction map.
19. Top architecture risks.
20. Technical-debt register.
21. Unknowns requiring runtime verification.
22. Recommended audit order.

Do not propose implementation details beyond high-level recommendations.

Save as:

docs/audits/stage-00-repository-map.md
```

---

# Stage 1 — Environment and Installation Audit

```text
Act as a senior Python DevOps and packaging engineer.

Audit Midgard's source-based installation and development environment.

Do not modify code.

Analyze:

- supported Python versions;
- virtual-environment creation;
- dependency installation;
- CPU installation;
- CUDA installation;
- DirectML installation;
- MPS/macOS installation;
- Torch and torchvision selection;
- Paddle installation;
- ONNX Runtime variants;
- FFmpeg requirements;
- repeated installation;
- interrupted installation recovery;
- paths containing spaces;
- non-ASCII paths;
- platform compatibility;
- developer setup;
- user setup;
- production source deployment.

Inspect:

- install.py
- install.bat
- install.sh
- run_gui.bat
- run_gui.sh
- requirements.txt
- all requirement files
- pyproject.toml
- Docker files
- README instructions
- GitHub workflows
- packaging scripts
- obsolete EXE-build scripts

Identify:

- dependency conflicts;
- missing packages;
- undeclared runtime imports;
- unused dependencies;
- unpinned dependencies;
- overly broad constraints;
- platform-specific conflicts;
- unsupported Python versions;
- difficult setup steps;
- non-idempotent operations;
- unsafe cleanup;
- installer assumptions.

Design an improved source-based setup:

- canonical Python version;
- supported-version policy;
- dependency-group strategy;
- CPU dependency flow;
- CUDA dependency flow;
- DirectML dependency flow;
- macOS dependency flow;
- developer setup;
- ordinary-user setup;
- environment repair;
- offline limitations;
- post-install validation.

Do not recommend standalone executable packaging.

Produce:

1. Current installation flow.
2. Python compatibility matrix.
3. OS/backend compatibility matrix.
4. Dependency ownership table.
5. Reproducibility risks.
6. Recommended dependency structure.
7. Developer installation flow.
8. Windows installation flow.
9. Linux installation flow.
10. macOS installation flow.
11. Environment repair flow.
12. Migration plan.
13. Acceptance criteria.

Save as:

docs/audits/stage-01-environment-installation.md
```

---

# Stage 2 — Application Startup Lifecycle

```text
Act as a senior Python desktop-application engineer.

Trace exactly what happens when Midgard starts.

Do not modify code.

Review:

- gui.py;
- run_gui.bat;
- run_gui.sh;
- QApplication creation;
- diagnostic initialization;
- configuration loading;
- translation loading;
- environment mutation;
- hardware detection;
- page construction;
- service initialization;
- inference worker startup;
- model manager startup;
- pending download recovery;
- update checks;
- startup health checks;
- shutdown hooks;
- worker cleanup;
- temporary-file cleanup.

Trace these scenarios:

- normal GUI startup;
- first startup after installation;
- CPU-only startup;
- CUDA startup;
- DirectML startup;
- MPS startup;
- missing configuration;
- corrupt configuration;
- missing optional dependencies;
- missing model files;
- offline startup;
- pending model downloads;
- worker startup failure;
- repeated startup in tests;
- shutdown during processing.

Identify:

- import-time side effects;
- slow startup operations;
- GUI-thread blocking;
- fragile initialization;
- silent failures;
- repeated hardware probing;
- missing validation;
- worker orphan risks;
- shutdown leaks;
- race conditions.

Design the target lifecycle:

Application Bootstrap
  -> Logging Initialization
  -> Environment Validation
  -> Path Resolution
  -> Configuration Loading
  -> Hardware Snapshot
  -> Dependency Validation
  -> QApplication Creation
  -> Lightweight Services
  -> Window Shell
  -> Lazy Feature Initialization
  -> Inference Worker Handshake
  -> Deferred Downloads and Update Check
  -> Application Ready

Provide:

- current sequence diagram;
- target sequence diagram;
- failure policy;
- degraded-mode policy;
- startup timing points;
- shutdown sequence;
- migration plan.

Save as:

docs/audits/stage-02-startup-lifecycle.md
```

---

# Stage 3 — Configuration and Settings Architecture

```text
Act as a principal Python architect.

Audit the complete Midgard configuration system.

Do not modify code.

Analyze:

- backend/config.py;
- config/config.json;
- qfluentwidgets configuration;
- translation configuration;
- environment variables;
- Hugging Face token handling;
- application URLs;
- version values;
- user paths;
- hardware settings;
- model settings;
- UI preferences;
- transient runtime state;
- defaults;
- migrations;
- concurrent access by GUI and workers.

Identify:

- Qt coupling;
- import-time side effects;
- hardcoded values;
- relative paths;
- missing validation;
- secrets mixed with ordinary settings;
- missing schema versions;
- atomic-write issues;
- process-safety issues;
- invalid-state handling;
- duplicated repository URLs;
- inconsistent setting types or units.

Design an incremental target structure:

backend/
  core/
    build_info.py
    paths.py
    environment.py
  config/
    models.py
    runtime.py
    hardware.py
    gui.py
    loader.py
    migrations.py
    secrets.py
  i18n/
    translations.py

Define precedence:

compiled defaults
  < shipped configuration
  < user configuration
  < environment variables
  < explicit runtime overrides

Separate:

- build metadata;
- repository metadata;
- paths;
- runtime settings;
- GUI preferences;
- model policy;
- hardware policy;
- secrets;
- transient state.

Include:

- type-safe configuration;
- validation;
- atomic writes;
- corrupt-file recovery;
- migration from current config.json;
- environment overrides;
- compatibility facade for backend.config;
- worker-safe configuration snapshots.

Save as:

docs/audits/stage-03-configuration.md
```

---

# Stage 4 — Hardware Detection Architecture

```text
Act as a senior heterogeneous-compute architect.

Audit Midgard hardware detection.

Do not modify code.

Inspect:

- backend/tools/hardware_accelerator.py;
- installer hardware detection;
- Torch CUDA detection;
- torch-directml;
- MPS;
- ONNX Runtime providers;
- Paddle GPU support;
- GPU memory queries;
- CPU fallback;
- model-specific hardware decisions.

Detect and normalize:

CPU:
- vendor;
- model;
- architecture;
- physical cores;
- logical threads.

Memory:
- total RAM;
- available RAM;
- swap.

GPU:
- vendor;
- model;
- total VRAM;
- available VRAM;
- driver version;
- CUDA driver/runtime;
- compute capability;
- DirectML availability;
- MPS availability.

Framework capabilities:
- Torch CUDA;
- Torch DirectML;
- Torch MPS;
- ONNX providers;
- Paddle GPU;
- CPU fallback.

System:
- OS;
- OS version;
- Python architecture;
- available disk space;
- FFmpeg availability.

Design:

backend/hardware/
  detector.py
  cpu.py
  memory.py
  gpu.py
  providers.py
  capabilities.py
  profile.py
  policy.py
  diagnostics.py

Define:

- immutable HardwareProfile;
- separate ExecutionPolicy;
- confidence levels;
- detection cache;
- cache invalidation;
- fallback behavior;
- human-readable diagnostic report;
- mocked test profiles.

Explicitly audit the DirectML unreachable code and bare exception.

Save as:

docs/audits/stage-04-hardware.md
```

---

# Stage 5 — AI Model Management

```text
Act as an AI infrastructure engineer.

Audit all Midgard model management.

Do not modify code.

Inventory:

- STTN Auto;
- STTN Detection;
- LaMa;
- ProPainter;
- PaddleOCR server;
- PaddleOCR mobile;
- rembg models;
- Real-ESRGAN x2;
- Real-ESRGAN x4;
- MIRNet;
- SAM2;
- Grounding DINO;
- FLUX.2 Klein distilled/base, FLUX.2 Dev, Klein 9B FP8, and Qwen-Image.

For every model document:

- ID;
- display name;
- purpose;
- framework;
- source;
- license;
- gated status;
- local path;
- expected files;
- expected size;
- checksum support;
- RAM requirement;
- VRAM requirement;
- compatible backends;
- dtype;
- version;
- default enablement;
- cache policy;
- unload policy.

Analyze:

- storage locations;
- loading;
- unloading;
- switching;
- caching;
- GPU allocation;
- partial downloads;
- interrupted downloads;
- checksum verification;
- corrupt models;
- disk-space validation;
- version handling;
- license handling;
- gated Hugging Face access.

Design:

backend/models/
  registry.py
  metadata.py
  manifest.py
  downloader.py
  verifier.py
  loader.py
  cache.py
  manager.py
  eviction.py
  exceptions.py
  manifests/

Define model states:

NOT_INSTALLED
QUEUED
DOWNLOADING
VERIFYING
INSTALLED
LOADING
READY
BUSY
UNLOADING
BROKEN
INCOMPATIBLE

Include migration steps.

Save as:

docs/audits/stage-05-model-management.md
```

---

# Additions to the Midgard Engineering Roadmap

Insert these audit stages after Stage 6 and before the general Python architecture review.

The updated section becomes:

```text
Stage 5   AI model management
Stage 6   AI pipeline architecture
Stage 7   Model settings and recommendation system
Stage 8   User experience and interface audit
Stage 9   Accessibility and usability
Stage 10  Python architecture review
```

Renumber later stages accordingly, or keep labels such as Stage 7A, Stage 7B, and Stage 7C to avoid changing existing report names.

---

# Stage 7A — Model Settings and Preset Architecture

Act as a senior AI product and inference-runtime architect.

Audit every model-related setting exposed by Midgard.

Do not modify code.

## Review settings for

### Image generation

* model selection;
* image width and height;
* aspect ratio;
* inference steps;
* guidance scale;
* seed;
* negative prompt;
* scheduler;
* precision;
* CPU offload;
* attention slicing;
* model caching;
* output format;
* output quality;
* safety constraints;
* memory mode.

### Subtitle and text removal

* inpainting model;
* subtitle-detection model;
* detection sensitivity;
* mask expansion;
* timeline expansion;
* reference frames;
* neighbor stride;
* batch size;
* frame-load count;
* scene splitting;
* preview quality;
* output codec;
* output quality.

### Background removal

* model;
* alpha matting;
* foreground threshold;
* background threshold;
* erosion size;
* edge refinement;
* output transparency;
* mask cleanup;
* model cache.

### Upscaling

* model;
* scale factor;
* tile size;
* tile overlap;
* denoise strength;
* face enhancement;
* output limit;
* precision;
* memory mode.

### Low-light enhancement

* model;
* strength;
* maximum processing resolution;
* color preservation;
* noise reduction;
* tile size;
* memory mode.

### Object selection

* SAM2 model;
* Grounding DINO model;
* text confidence;
* box confidence;
* mask threshold;
* refinement;
* fast versus quality mode.

## Identify

* settings that are hardcoded;
* settings exposed without validation;
* settings that ordinary users should not see;
* settings missing from the UI;
* duplicate settings;
* unsafe settings;
* settings whose names are too technical;
* settings that need descriptions or tooltips;
* values that should be calculated automatically;
* settings that should move into an Advanced section;
* settings requiring restart;
* settings that should apply immediately;
* per-model settings incorrectly shared globally.

## Design three settings levels

### Simple

For ordinary users:

* Fast;
* Balanced;
* Quality;
* Low Memory.

### Advanced

For experienced users:

* model;
* resolution;
* steps;
* batch size;
* memory strategy;
* detection thresholds;
* model-specific controls.

### Expert

For development and troubleshooting:

* backend override;
* precision;
* device;
* scheduler;
* tile sizes;
* worker timeouts;
* cache behavior;
* framework-specific settings.

Expert mode must be hidden by default.

## Design preset behavior

Create presets that are model- and hardware-aware.

Examples:

```text
Fast
- lower steps;
- smaller working resolution;
- lighter model;
- conservative memory allocation.

Balanced
- recommended default;
- moderate quality;
- moderate memory use.

Quality
- higher steps or stronger model;
- only offered when hardware supports it.

Low Memory
- CPU offload;
- smaller batches;
- tiling;
- lower concurrent frame count;
- aggressive model unloading.
```

Presets must not be simple hardcoded lists.

They should be derived from:

* selected task;
* selected model;
* hardware profile;
* available VRAM;
* available RAM;
* input dimensions;
* model installation state.

## Design a settings resolution system

```text
Application defaults
        |
        v
Model defaults
        |
        v
Hardware recommendations
        |
        v
Selected preset
        |
        v
User overrides
        |
        v
Safety validation
        |
        v
Effective settings
```

The system must distinguish:

* default value;
* recommended value;
* configured value;
* effective value;
* safety-clamped value.

## Model-specific configuration

Do not store all model options in one global settings class.

Design model-specific schemas, such as:

```text
GenerateSettings
ProPainterSettings
STTNSettings
LamaSettings
BackgroundRemovalSettings
UpscaleSettings
LowLightSettings
ObjectSelectionSettings
```

Include:

* type validation;
* allowed ranges;
* model compatibility;
* backend compatibility;
* restart requirements;
* user-readable descriptions;
* safe defaults;
* migrations.

## User-facing diagnostics

When Midgard changes a setting for safety, show:

```text
Configured value: 70 frames
Recommended value: 24 frames
Effective value: 24 frames

Reason:
Your available GPU memory is not sufficient for 70 frames at this resolution.
```

Do not silently clamp values.

## Deliverables

1. Complete settings inventory.
2. Missing-settings inventory.
3. Unsafe-settings inventory.
4. Model-specific setting schemas.
5. Simple, Advanced, and Expert division.
6. Preset design.
7. Settings-resolution algorithm.
8. Validation rules.
9. Hardware-aware recommendations.
10. UI presentation recommendations.
11. Configuration migration plan.
12. Testing requirements.

Save as:

```text
docs/audits/stage-07a-model-settings.md
```

---

# Stage 7B — User Experience and Interface Audit

Act as a senior desktop product designer and PySide6 UX engineer.

Perform a complete user-experience audit of Midgard.

Do not modify code.

## Review the complete user journey

### Installation

* clarity of installation steps;
* BAT and SH behavior;
* failure messages;
* missing Python;
* missing FFmpeg;
* unsupported hardware;
* dependency installation progress;
* environment repair.

### First launch

* startup duration;
* blank or frozen window risk;
* first-run explanation;
* hardware summary;
* model availability;
* default save directory;
* offline behavior;
* pending model downloads.

### Home screen

* clarity of available tools;
* task discoverability;
* model readiness;
* recent files;
* output location;
* shortcut behavior;
* empty states.

### Tool workflow

For every tool:

* selecting input;
* previewing input;
* selecting model;
* choosing settings;
* starting a job;
* viewing progress;
* cancelling;
* handling errors;
* comparing results;
* saving output;
* finding output afterward;
* repeating a job.

### Settings

* navigation;
* grouping;
* naming;
* descriptions;
* model installation;
* enabled versus installed state;
* destructive actions;
* restart requirements;
* advanced settings;
* reset behavior.

### Model installation

* model size before download;
* expected disk space;
* estimated hardware requirement;
* license;
* gated access;
* download progress;
* pause or cancel;
* retry;
* verification;
* corruption recovery;
* uninstall;
* currently loaded state.

## Identify UX problems

* unclear terminology;
* controls with no explanation;
* too many settings;
* settings shown before they are relevant;
* actions with no feedback;
* unclear disabled states;
* inconsistent button naming;
* hidden output files;
* accidental destructive actions;
* modal-dialog overuse;
* progress that appears frozen;
* cancellation that is not immediate;
* errors containing raw exceptions;
* settings requiring restart without explanation;
* model choices incompatible with hardware;
* inconsistent layouts between tools.

## Design UX principles

Midgard should follow:

1. Progressive disclosure.
2. Safe defaults.
3. Visible system status.
4. Immediate feedback.
5. Reversible actions.
6. Clear output ownership.
7. No silent failures.
8. Hardware-aware choices.
9. Consistent terminology.
10. Minimal required decisions.

## Proposed navigation

Evaluate a structure such as:

```text
Home
Generate Image
Remove Text
Remove Background
Upscale
Fix Low Light
Select Object
Jobs
Models
Settings
Diagnostics
```

Do not automatically implement this structure. Compare it to the current navigation and justify changes.

## Add a jobs experience

Design a Jobs panel showing:

* active job;
* queued jobs;
* completed jobs;
* failed jobs;
* cancelled jobs;
* task type;
* model;
* progress;
* elapsed time;
* output path;
* error summary;
* retry;
* open result;
* open folder.

The shared inference worker may still execute one GPU job at a time.

The UI should make this queue visible.

## Progress experience

Each long-running job should show:

* current phase;
* overall progress;
* elapsed time;
* safe estimated remaining time when reliable;
* selected model;
* device;
* cancel action;
* output destination.

Example phases:

```text
Preparing input
Loading model
Detecting text
Processing frames
Encoding video
Merging audio
Saving result
Cleaning up
```

Avoid displaying one generic progress bar for every phase.

## Error-message design

Create user-facing errors with:

* simple title;
* understandable explanation;
* recommended action;
* optional technical details;
* copy-diagnostics action.

Example:

```text
Not enough GPU memory

Midgard could not process this video with the selected settings.

Try:
- switching to Balanced or Low Memory;
- lowering concurrent frames;
- closing other GPU applications.

Technical details are available in Diagnostics.
```

Do not show raw tracebacks as the primary message.

## Empty and unavailable states

Design states for:

* no model installed;
* model downloading;
* model disabled;
* incompatible hardware;
* no input selected;
* missing FFmpeg;
* offline mode;
* no output yet;
* failed worker;
* corrupt model.

Every disabled action must explain why it is disabled.

## Save and output experience

Design:

* consistent output destination;
* output name preview;
* overwrite protection;
* automatic folder creation;
* open result;
* open containing folder;
* recent outputs;
* output history;
* failure cleanup;
* partial-output handling.

## Deliverables

1. User-journey map.
2. Screen-by-screen findings.
3. Severity-ranked UX issues.
4. Navigation recommendations.
5. Jobs-panel design.
6. Progress-state design.
7. Error-message framework.
8. Empty-state designs.
9. Model installation UX.
10. Settings UX.
11. Output workflow.
12. Incremental UX pull-request plan.
13. Usability acceptance criteria.

Save as:

```text
docs/audits/stage-07b-user-experience.md
```

---

# Stage 7C — First-Run Onboarding and Model Setup

Act as a senior desktop onboarding and AI-product engineer.

Design Midgard's first-run experience.

Do not modify code.

## First-run goals

A new user should understand:

* what Midgard does;
* that processing runs locally;
* where outputs are saved;
* which hardware was detected;
* which features are immediately available;
* which models require download;
* model sizes;
* model licenses;
* which model is recommended;
* how to change settings later.

## Design the first-run flow

```text
Welcome
  -> Storage and privacy
  -> Hardware detection
  -> Recommended operating mode
  -> Save directory
  -> Feature selection
  -> Recommended model downloads
  -> Download review
  -> Installation progress
  -> Ready screen
```

## Hardware summary

Show user-readable information:

```text
NVIDIA RTX 4070
12 GB VRAM
32 GB system memory
CUDA acceleration available

Recommended mode: Balanced
```

Avoid exposing unnecessary framework details on the main onboarding screen.

Place detailed Torch, ONNX, CUDA, driver, and provider information in Diagnostics.

## Model recommendation cards

Each model card should show:

* feature;
* model name;
* quality level;
* download size;
* estimated disk usage;
* minimum or recommended VRAM;
* license;
* installed state;
* recommended badge;
* optional badge;
* gated-access requirement.

## Download selection

Do not automatically download every model.

Offer:

```text
Recommended setup
Minimal setup
Full setup
Choose manually
```

Recommended setup must be based on hardware.

## Interrupted onboarding

The first-run process must resume safely.

Store:

* onboarding version;
* completed steps;
* selected save directory;
* accepted model licenses;
* pending downloads.

Do not leave the application in a permanently incomplete state.

## Offline behavior

When offline:

* explain that the app can still open;
* list installed features;
* show unavailable models;
* offer retry later;
* avoid repeated blocking dialogs.

## Deliverables

1. First-run state machine.
2. Screen sequence.
3. Hardware summary design.
4. Model recommendation rules.
5. Download-selection design.
6. Resume and recovery behavior.
7. Offline behavior.
8. Configuration fields required.
9. Test scenarios.
10. Incremental implementation plan.

Save as:

```text
docs/audits/stage-07c-onboarding.md
```

---

# Stage 7D — Accessibility and Desktop Usability

Act as a senior accessibility and Qt desktop usability engineer.

Audit Midgard for accessibility and general desktop usability.

Do not modify code.

## Review

* keyboard navigation;
* tab order;
* focus visibility;
* keyboard shortcuts;
* screen-reader labels;
* accessible names;
* accessible descriptions;
* color contrast;
* text scaling;
* high-DPI scaling;
* Windows display scaling;
* macOS Retina behavior;
* Linux desktop scaling;
* reduced-motion preference;
* minimum window size;
* responsive layout;
* touchpad and mouse behavior;
* drag-and-drop;
* file-dialog accessibility;
* tooltip usability;
* localization readiness.

## Required keyboard workflows

Users should be able to:

* move through navigation;
* select a file;
* choose a model;
* change a preset;
* start processing;
* cancel processing;
* open settings;
* access diagnostics;
* close dialogs;
* reach error details.

## Accessibility requirements

* every interactive control has an accessible name;
* icon-only controls have labels;
* disabled controls explain their state;
* focus never disappears;
* keyboard focus does not become trapped;
* status changes are announced where Qt supports it;
* progress can be understood without color;
* errors are not communicated only through color;
* text remains readable at increased scaling.

## Deliverables

1. Accessibility findings.
2. Keyboard-navigation map.
3. Focus-order issues.
4. Contrast issues.
5. High-DPI issues.
6. Screen-reader improvements.
7. Required Qt accessibility properties.
8. Accessibility test plan.
9. Incremental implementation backlog.

Save as:

```text
docs/audits/stage-07d-accessibility.md
```

---

# New Implementation Phase — Model Settings and Presets

Add this phase after the Hardware Profile implementation and before broad model-policy changes.

Act as a senior AI product engineer.

Implement the model-settings foundation incrementally.

## First pull request

Create typed model-specific setting schemas without changing visible UI behavior.

Include schemas for:

* Generate Image;
* ProPainter;
* STTN;
* background removal;
* upscaling;
* low-light restoration;
* object selection.

Each schema must define:

* type;
* default;
* range;
* model compatibility;
* backend compatibility;
* user-readable label;
* description;
* whether restart is required;
* whether it belongs to Simple, Advanced, or Expert settings.

Keep compatibility with current configuration.

## Second pull request

Implement preset resolution:

* Fast;
* Balanced;
* Quality;
* Low Memory.

The resolver must use:

* task;
* model;
* hardware profile;
* available VRAM;
* available RAM;
* input dimensions.

Return:

* recommended settings;
* reasons;
* warnings;
* effective settings.

Do not connect it to every UI screen yet.

## Third pull request

Add preset controls to one feature only.

Start with the most stable feature, such as image upscale or background removal.

Validate the interaction pattern before applying it to all features.

## Fourth pull request

Add:

* configured-versus-effective display;
* safety-clamp messages;
* reset to recommended;
* reset to model defaults;
* expert-mode toggle.

## Tests

Add tests covering:

* every preset;
* every hardware class;
* unsupported combinations;
* safe overrides;
* unsafe overrides;
* settings migration;
* deterministic resolution.

---

# New Implementation Phase — UX Foundations

Add this phase after model settings and before final CLI retirement.

Act as a senior PySide6 desktop-product engineer.

Implement UX improvements incrementally.

## Pull request sequence

### PR 1 — Shared job status model

Create a shared job status representation:

* queued;
* preparing;
* loading model;
* processing;
* postprocessing;
* saving;
* completed;
* failed;
* cancelled.

Do not redesign the entire worker protocol unless required.

### PR 2 — Consistent progress component

Create a reusable progress UI containing:

* phase;
* percentage;
* elapsed time;
* model;
* device;
* cancel button;
* output destination.

### PR 3 — Error presentation

Create a reusable user-facing error component:

* title;
* explanation;
* suggested actions;
* expandable technical details;
* copy diagnostics.

### PR 4 — Empty and unavailable states

Create reusable states for:

* missing model;
* model downloading;
* incompatible hardware;
* missing dependency;
* offline;
* no input;
* no output.

### PR 5 — Output completion experience

Add:

* open result;
* open folder;
* copy output path;
* retry job;
* recent outputs where appropriate.

### PR 6 — Settings organization

Group settings into:

* General;
* Models;
* Performance;
* Storage;
* Updates;
* Advanced;
* Diagnostics.

Do not expose every internal setting.

### PR 7 — First-run onboarding

Implement onboarding only after model metadata and hardware profiles are reliable.

### PR 8 — Accessibility

Implement:

* keyboard navigation;
* focus corrections;
* accessible labels;
* contrast fixes;
* high-DPI validation.

## UX acceptance criteria

* users always know whether a job is queued, running, failed, or completed;
* every disabled action explains why;
* every long operation can be cancelled where technically safe;
* model requirements are visible before download;
* errors provide an action, not only a failure statement;
* output location is always visible;
* ordinary users do not need to understand CUDA, ONNX, dtype, or batch size;
* advanced users can access detailed controls;
* expert controls are hidden by default.



# Stage 6 — AI Pipeline Architecture

```text
Act as a principal AI systems architect.

Audit the complete Midgard AI-processing pipeline.

Do not modify code.

For each feature trace:

- input validation;
- preprocessing;
- model selection;
- model acquisition;
- inference;
- progress reporting;
- cancellation;
- postprocessing;
- output writing;
- cleanup;
- error propagation.

Features:

- Remove Text;
- Remove Background;
- Image Upscale;
- Low-Light Restore;
- Select Object;
- Image Generation.

Review:

- GUI-to-service calls;
- inference client;
- worker protocol;
- GPU busy gate;
- queues;
- model reuse;
- CPU jobs;
- GPU jobs;
- serialization;
- temporary files;
- media ownership;
- caching;
- batching;
- OOM retries;
- watchdog behavior;
- worker restart;
- stale jobs;
- cancellation.

Design:

PySide6 GUI
  -> Application Use Cases
  -> AI Service Layer
  -> Job Scheduler
  -> Model Manager
  -> Feature Pipeline
  -> Framework Adapter
  -> CUDA / DirectML / MPS / ONNX / CPU

Define a typed job protocol:

- job ID;
- task;
- input references;
- normalized options;
- progress;
- cancellation;
- result;
- structured error;
- timing;
- memory metrics.

Evaluate whether the existing single shared worker should remain.

Prefer stabilizing it unless evidence proves a redesign is necessary.

Save as:

docs/audits/stage-06-ai-pipeline.md
```

---

# Stage 7 — Python Architecture Review

```text
Act as a principal Python software architect.

Perform a complete architecture review.

Do not modify code.

Analyze:

- module organization;
- class responsibilities;
- dependency direction;
- global state;
- singletons;
- wildcard imports;
- sys.path mutation;
- circular imports;
- Qt coupling;
- duplicated code;
- UI/business-logic mixing;
- service boundaries;
- process boundaries;
- maintainability;
- testability.

Pay special attention to backend/main.py.

Map its responsibilities:

- CLI parsing;
- media opening;
- video decoding;
- temporary files;
- output paths;
- subtitle detection;
- model selection;
- inference;
- batching;
- progress;
- audio merging;
- cleanup.

Propose an incremental target:

backend/
  application/
  core/
  config/
  hardware/
  inference/
  models/
  pipelines/
  media/
  services/
  storage/
  updates/
  diagnostics/
  ui/

Do not impose a full repository move immediately.

Provide:

1. Current dependency graph.
2. Circular-import candidates.
3. God modules.
4. God classes.
5. Global-state inventory.
6. Qt-bound backend modules.
7. Stable modules that should remain.
8. Target dependency rules.
9. Small refactoring pull requests.
10. Compatibility-adapter plan.
11. Rollback plan.
12. Required tests per refactor.

Save as:

docs/audits/stage-07-python-architecture.md
```

---

# Stage 8 — Production Bug Audit

```text
Act as a senior Python reliability engineer.

Perform a complete production bug audit.

Do not modify code.

Review:

- GUI lifecycle;
- threads;
- multiprocessing;
- queues;
- worker shutdown;
- temporary files;
- video capture;
- video writers;
- FFmpeg subprocesses;
- model loading;
- model unloading;
- GPU memory;
- OOM recovery;
- downloads;
- update checks;
- paths;
- Windows file locking;
- cancellation;
- invalid media;
- corrupt configuration;
- missing dependencies;
- missing models;
- offline operation.

Search for:

- bare except;
- except Exception with pass;
- unreachable code;
- missing finally;
- unclosed resources;
- duplicate progress updates;
- deadlocks;
- races;
- division by zero;
- invalid FPS;
- invalid frame count;
- stale worker state;
- GUI updates from worker threads;
- partial output corruption;
- unsafe cleanup;
- invalid assumptions.

For every issue provide:

- ID;
- severity;
- confidence;
- exact location;
- reproduction scenario;
- explanation;
- impact;
- root cause;
- recommended fix;
- required regression test.

Severity:

Critical
High
Medium
Low

Save as:

docs/audits/stage-08-bug-audit.md
```

---

# Stage 9 — Security Audit

```text
Act as a senior application-security engineer.

Perform a production security audit.

Do not modify code.

Review:

- Hugging Face tokens;
- environment variables;
- configuration secrets;
- logs;
- model downloads;
- GitHub update checks;
- TLS verification;
- checksums;
- model integrity;
- unsafe Torch or pickle deserialization;
- archive extraction;
- path traversal;
- symlinks;
- arbitrary deletion;
- subprocess execution;
- shell usage;
- FFmpeg inputs;
- output paths;
- temporary-file permissions;
- dependency vulnerabilities;
- bundled binaries;
- bundled model files;
- release provenance;
- model licenses.

Recommend:

- Bandit;
- pip-audit;
- Ruff security rules;
- Semgrep;
- CodeQL;
- secret scanning;
- SBOM generation;
- dependency review;
- source-archive checksums.

Produce:

1. Threat model.
2. Trust boundaries.
3. Attack-surface map.
4. Findings register.
5. Dependency risks.
6. Model-file risks.
7. Update risks.
8. Secret-handling risks.
9. Remediation order.
10. Security acceptance criteria.

Save as:

docs/audits/stage-09-security.md
```

---

# Stage 10 — Logging and Error Handling

```text
Act as a senior observability engineer.

Audit Midgard logging, diagnostics, and error handling.

Do not modify code.

Review:

- diagnostic modules;
- print calls;
- traceback calls;
- startup messages;
- worker logs;
- installer output;
- model logs;
- download logs;
- performance timing;
- GUI error messages;
- shutdown diagnostics;
- crash handling.

Design:

backend/diagnostics/
  logging.py
  context.py
  events.py
  errors.py
  crash_report.py
  health.py
  redaction.py

Required levels:

DEBUG
INFO
WARNING
ERROR
CRITICAL

Structured fields:

- session ID;
- process ID;
- thread;
- job ID;
- feature;
- model ID;
- backend;
- device;
- elapsed time;
- safe memory statistics;
- exception type.

Define typed errors for:

- configuration;
- dependency;
- hardware;
- model installation;
- model verification;
- model loading;
- inference;
- cancellation;
- media decoding;
- output writing;
- download;
- update.

Separate user-facing messages from developer diagnostics.

Never log tokens or secrets.

Save as:

docs/audits/stage-10-logging-errors.md
```

---

# Stage 11 — Testing Strategy

```text
Act as a senior Python test architect.

Create a complete Midgard testing strategy.

Do not modify code.

Analyze testability of:

- configuration;
- repository metadata;
- hardware detection;
- model manifests;
- model loading;
- inference protocol;
- worker lifecycle;
- downloads;
- update checks;
- video processing;
- image processing;
- output paths;
- temporary files;
- cancellation;
- OOM fallback;
- CPU fallback;
- GUI startup;
- GUI shutdown;
- installer logic;
- BAT and SH launcher logic.

Design:

tests/
  unit/
  integration/
  characterization/
  gui/
  inference/
  hardware/
  models/
  media/
  installer/
  performance/
  fixtures/
  fakes/

Recommend where justified:

- pytest;
- pytest-cov;
- pytest-qt;
- pytest-timeout;
- pytest-mock;
- pytest-xdist;
- pytest-benchmark.

Standard tests must:

- run without a GPU;
- block network access;
- avoid model downloads;
- avoid user configuration;
- mock update checks;
- use tiny generated media;
- use fake models.

Define markers:

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
installer

Provide:

- current test inventory;
- missing-test matrix;
- fixture design;
- fake service design;
- CI test set;
- manual hardware test set;
- coverage goals;
- quality gates.

Save as:

docs/audits/stage-11-testing.md
```

---

# Stage 12 — Performance Audit

```text
Act as a Python, video, and GPU performance engineer.

Create a measurement-first performance report.

Do not optimize code yet.

Investigate:

- import time;
- GUI startup;
- eager page construction;
- worker startup;
- model loading;
- model unloading;
- model switching;
- VRAM fragmentation;
- frame decoding;
- frame copies;
- color conversions;
- mask generation;
- OCR;
- batching;
- IPC serialization;
- output encoding;
- audio merge;
- preview rendering;
- downloads;
- memory growth;
- resource leaks.

Use or recommend:

- cProfile;
- py-spy;
- scalene;
- tracemalloc;
- memray;
- psutil;
- torch.profiler;
- CUDA memory statistics;
- FFmpeg benchmark output;
- Qt startup timers.

Define benchmarks for:

- Remove BG;
- x2 upscale;
- low-light image;
- 10-second 720p video;
- 10-second 1080p video;
- image generation at supported sizes;
- model switch;
- startup;
- shutdown.

For every recommendation include:

- baseline metric;
- target metric;
- measurement method;
- expected trade-off;
- regression test.

Save as:

docs/audits/stage-12-performance.md
```

---

# Stage 13 — Source Installation and Launcher Design

```text
Act as a senior Python installation engineer.

Midgard must remain source-based.

Do not recommend or implement standalone executable packaging.

Audit:

- install.py;
- install.bat;
- install.sh;
- run_gui.bat;
- run_gui.sh;
- virtual-environment creation;
- Python detection;
- backend selection;
- dependency installation;
- environment repair;
- repeated installation;
- path quoting;
- exit-code handling;
- diagnostic startup;
- source releases.

Required user flow:

Windows:
  install.bat
  run_gui.bat

Linux/macOS:
  ./install.sh
  ./run_gui.sh

Direct:
  python install.py
  python gui.py

Design requirements:

install.bat and install.sh:
- resolve repository root;
- locate supported Python;
- call install.py;
- preserve exit code;
- show clear success or failure;
- support paths containing spaces;
- avoid administrator/root requirements.

run_gui.bat and run_gui.sh:
- validate virtual environment;
- use virtual-environment Python;
- resolve repository root;
- support diagnostic mode;
- show actionable startup errors;
- preserve exit codes.

install.py:
- validate Python;
- create or repair environment;
- install backend-specific dependencies;
- avoid optional large model downloads by default;
- validate critical imports;
- validate directories;
- validate FFmpeg;
- remain idempotent;
- recover from interruption.

Identify obsolete EXE-related files and documentation, but do not delete them in this audit.

Save as:

docs/audits/stage-13-source-installation.md
```

---

# Stage 14 — Source-Based Update System

```text
Act as a senior update-system architect.

Design a source-based update system.

Do not design a binary self-updater.

Current allowed update methods:

Git checkout:
  git pull
  python install.py --yes

Downloaded source release:
  download source archive
  replace or update source files safely
  preserve user data
  run install.py again

The application may:

- read current version;
- check the latest GitHub release;
- compare semantic versions;
- notify the user;
- open the official release page;
- verify source-archive checksums;
- preserve model and user-data directories.

The application must not:

- overwrite running files;
- install an EXE;
- replace Python;
- execute arbitrary downloaded binaries;
- perform unattended binary updates.

Design:

Version Reader
  -> GitHub Release Checker
  -> Semantic Version Comparison
  -> User Notification
  -> Release Page or Source Download
  -> Checksum Verification
  -> Backup Guidance
  -> install.py Environment Repair

Keep application updates separate from model updates.

Include:

- rollback;
- interrupted source update recovery;
- release channels;
- offline behavior;
- GitHub rate limits;
- configuration migrations;
- user-data preservation;
- source-checkout detection;
- archive-install detection.

Save as:

docs/audits/stage-14-source-updates.md
```

---

# Stage 15 — CI/CD Pipeline

```text
Act as a senior CI/CD engineer.

Design GitHub Actions for the source-based Midgard application.

Do not build executable packages.

On pull request:

- validate repository structure;
- validate Python syntax;
- run Ruff;
- run formatting check;
- run type checking;
- run unit tests;
- run safe integration tests;
- run headless GUI tests;
- run installer-decision tests;
- validate BAT scripts;
- validate SH scripts;
- run Bandit;
- run pip-audit;
- run CodeQL;
- run secret scanning;
- run dependency review.

Matrix:

- Ubuntu + Python 3.12;
- Windows + Python 3.12;
- macOS + Python 3.12.

Add other Python versions only if officially supported.

Standard CI must not:

- download production models;
- require a GPU;
- contact external services without explicit markers;
- create EXE or native packages.

On release:

- validate version and tag;
- generate changelog;
- create source archives;
- generate SHA-256 checksums;
- generate SBOM;
- create GitHub release;
- upload source archives;
- upload dependency manifests;
- upload model-manifest metadata.

Include:

- caching;
- concurrency cancellation;
- least-privilege permissions;
- artifact retention;
- protected release environments;
- release rollback procedure.

Save as:

docs/audits/stage-15-cicd.md
```

---

# Stage 16 — Future AI Infrastructure

```text
Act as a principal AI infrastructure architect.

Design Midgard's future AI infrastructure.

Do not force server infrastructure onto ordinary desktop users.

Primary local mode:

PySide6 Desktop
  -> Local AI Gateway
  -> Local Scheduler
  -> Local Model Manager
  -> Local Worker
  -> CUDA / DirectML / MPS / CPU

Optional future workstation mode:

Desktop Clients
  -> Authenticated Local-Network Gateway
  -> Job Queue
  -> Scheduler
  -> GPU Workers
  -> Shared Model Store
  -> Result Store

Evaluate:

- Diffusers;
- ONNX Runtime;
- TensorRT;
- torch.compile;
- llama.cpp;
- Ollama;
- vLLM;
- embeddings;
- vector search;
- RAG;
- agents.

Do not add LLM, RAG, or agent systems without a concrete Midgard workflow.

Cover:

- warm models;
- job priorities;
- resource limits;
- cancellation;
- worker health;
- model versioning;
- result transfer;
- authentication;
- TLS;
- privacy;
- telemetry opt-in;
- horizontal scaling.

Provide three horizons:

1. Local desktop stabilization.
2. Multi-worker local workstation.
3. Optional studio-LAN deployment.

Save as:

docs/audits/stage-16-future-ai.md
```

---

# Stage 17 — Production Readiness Review

```text
Act as an independent principal engineer.

Perform a final production-readiness assessment using all previous reports.

Do not modify code.

Score 0–10:

- architecture;
- code quality;
- configuration;
- startup reliability;
- hardware compatibility;
- model lifecycle;
- security;
- privacy;
- dependencies;
- testing;
- performance;
- cleanup;
- source installation;
- BAT/SH launchers;
- source updates;
- CI/CD;
- diagnostics;
- documentation;
- licensing;
- supportability.

Use higher weights for:

- security;
- startup reliability;
- data integrity;
- model integrity;
- installation reproducibility.

Classify issues:

- release blocker;
- pre-release requirement;
- post-release priority;
- accepted risk.

Produce:

1. Overall score.
2. Evidence per category.
3. Blocking issues.
4. Supported platform matrix.
5. Known limitations.
6. Security gate.
7. Installation gate.
8. Model-license gate.
9. Launch checklist.
10. Rollback plan.
11. First 30-day monitoring plan.
12. Six-month roadmap.
13. Final verdict:
   - not ready;
   - internal alpha;
   - public alpha;
   - public beta;
   - production ready with limitations;
   - production ready.

Save as:

docs/audits/stage-17-production-readiness.md
```

---

# Stage 18 — Consolidated Implementation Backlog

```text
Act as the Midgard technical lead.

Read all reports from docs/audits/.

Do not modify production code.

Create a dependency-aware implementation backlog.

Epics:

1. Test safety baseline.
2. Repository metadata.
3. DirectML reliability.
4. Logging and typed errors.
5. Configuration boundary.
6. Hardware profile.
7. Model policy.
8. Model registry and integrity.
9. Inference protocol.
10. backend/main.py decomposition.
11. GUI-only CLI retirement.
12. Dependency modernization.
13. Installer reliability.
14. BAT/SH launcher reliability.
15. Source-based updates.
16. CI/CD.
17. Documentation.
18. Final verification.

For every task provide:

- task ID;
- priority;
- dependencies;
- exact files and symbols;
- intended behavior;
- non-goals;
- acceptance criteria;
- tests;
- platform impact;
- migration risk;
- estimated size: XS, S, M, L, XL.

Organize work into small pull requests.

No pull request should combine unrelated architecture changes.

Save as:

docs/audits/stage-18-implementation-backlog.md
```

---

# Rules for implementation stages

Use these rules for Stages 19–27:

```text
You are working on:

https://github.com/dexterR35/midgard

Read all relevant reports in docs/audits/ before editing.

Verify the issue still exists.

Before editing, report:

- selected task IDs;
- verified findings;
- files to change;
- behavior affected;
- compatibility risks;
- planned tests;
- non-goals;
- rollback approach.

Do not download large models.

Do not expose secrets.

Do not alter bundled model files.

Do not perform unrelated formatting.

Keep the pull request small and independently reviewable.

Preserve:

- PySide6 GUI;
- shared inference worker;
- GPU busy gate;
- model download lifecycle;
- OOM retry behavior;
- frame prefetching;
- CPU fallback;
- cancellation;
- shutdown behavior.

Do not create:

- EXE;
- MSI;
- PyInstaller;
- Nuitka;
- QPT;
- Briefcase;
- AppImage;
- DMG;
- DEB;
- RPM;
- native application bundles;
- binary self-updaters.

Run focused tests after changes.

Report:

- files changed;
- before and after behavior;
- commands run;
- test results;
- platforms tested;
- platforms mocked;
- remaining risks;
- next pull request.
```

---

# Stage 19 — Implementation Phase A: Safety Baseline

```text
Act as a senior Python test engineer.

Implement only the safety baseline.

Tasks:

- create or improve pytest configuration;
- block network access in normal tests;
- prevent production model downloads;
- avoid user configuration;
- create fake hardware profiles;
- create fake model loaders;
- create update-check mocks;
- add repository metadata tests;
- add DirectML behavior tests;
- add configuration import-boundary tests;
- add safe model-policy test scaffolding;
- add small generated media fixtures where required.

Required mocked hardware cases:

- CUDA unavailable;
- CUDA available;
- DirectML package unavailable;
- DirectML initialization success;
- DirectML initialization failure;
- MPS unavailable;
- MPS available;
- ONNX Runtime unavailable;
- ONNX CPU provider only;
- ONNX accelerator provider available.

Do not modify:

- backend/main.py;
- model defaults;
- ProPainter values;
- dependency versions;
- installer behavior;
- CLI behavior;
- configuration architecture.

Completion criteria:

- tests run without a GPU;
- tests run without model downloads;
- tests run without network access;
- tests do not touch user config;
- focused suite passes.

Use a small pull request.
```

---

# Stage 20 — Implementation Phase B: Low-Risk Reliability Fixes

```text
Act as a senior Python reliability engineer.

Implement only confirmed low-risk fixes.

Scope:

1. Fix DirectML unreachable code.
2. Replace the DirectML bare exception.
3. Ensure deterministic fallback:
   DirectML -> CUDA -> MPS -> CPU,
   unless current verified priority differs.
4. Mark DirectML unavailable after initialization failure.
5. Log a safe warning.
6. Centralize canonical repository metadata:
   owner = dexterR35
   repository = midgard
7. Derive:
   project URL;
   issues URL;
   releases URL;
   latest-release API URL.
8. Keep compatibility imports for current callers.
9. Correct documentation references supported by evidence.

Do not:

- redesign the updater;
- change dependencies;
- change model defaults;
- remove CLI;
- decompose backend/main.py;
- redesign configuration;
- replace hardware detection.

Add regression tests.

Use a small pull request.
```

---

# Stage 21 — Implementation Phase C: Configuration Boundary

```text
Act as a principal Python architect.

Implement the first configuration boundary only.

Extract from Qt-bound backend.config:

- build version;
- repository identity;
- derived repository URLs;
- project paths;
- environment initialization that does not require Qt.

Create non-Qt modules consistent with repository conventions, for example:

backend/core/build_info.py
backend/core/paths.py
backend/core/environment.py

Keep backend.config as a compatibility facade.

Update only modules that need metadata or paths and do not need Qt settings.

Add tests proving these modules can import without:

- QApplication;
- qfluentwidgets initialization;
- user configuration mutation.

Do not migrate all settings.

Do not change GUI preferences.

Do not change model defaults.

Use a small pull request.
```

---

# Stage 22 — Implementation Phase D: Hardware Profile

```text
Act as a senior hardware-platform engineer.

Implement a normalized immutable HardwareProfile.

Include verified fields for:

- OS;
- architecture;
- CPU model;
- physical cores;
- logical threads;
- total RAM;
- available RAM;
- GPU vendor;
- GPU model;
- total VRAM;
- available VRAM;
- driver;
- CUDA;
- DirectML;
- MPS;
- ONNX providers;
- supported backends;
- FFmpeg availability;
- disk availability where practical.

Separate:

- detection facts;
- execution recommendations.

Keep HardwareAccelerator compatibility.

Detection failures must produce an explicit CPU profile.

Add mocked tests for:

- CPU-only;
- CUDA;
- DirectML;
- MPS;
- missing optional libraries;
- partial detection failures.

Do not replace every caller in this pull request.
```

---

# Stage 23 — Implementation Phase E: Hardware-Aware Model Policy

```text
Act as an AI runtime engineer.

Implement a separate execution and model policy using HardwareProfile.

Start with memory-sensitive settings only.

Distinguish:

- configured value;
- recommended value;
- maximum safe value;
- effective value.

Apply to:

- ProPainter frame count;
- STTN load count;
- image-generation size or precision where appropriate;
- other verified memory-sensitive settings.

Consider:

- total VRAM;
- free VRAM;
- input resolution;
- backend;
- model;
- cached models;
- user override.

Do not silently change safe user settings.

When clamping:

- produce a diagnostic event;
- show a clear user message where relevant;
- explain configured and effective values.

Add tests for:

- CPU-only;
- unknown hardware;
- low VRAM;
- medium VRAM;
- high VRAM;
- DirectML;
- MPS;
- safe override;
- unsafe override;
- different resolutions.

Keep this independent from model-registry work.
```

---

# Stage 24 — Implementation Phase F: backend/main.py Decomposition

```text
Act as a principal Python maintainer.

Decompose backend/main.py incrementally.

Do not remove it immediately.

Complete one coherent extraction per pull request.

Recommended order:

PR 1:
- output-path generation;
- tests.

PR 2:
- temporary workspace lifecycle;
- cleanup tests.

PR 3:
- media resource lifecycle;
- capture/writer cleanup tests.

PR 4:
- progress events;
- cancellation behavior.

PR 5:
- model-selection logic.

PR 6:
- subtitle-removal service.

PR 7:
- pipeline orchestration.

The extracted services must not:

- parse CLI arguments;
- call sys.exit;
- modify sys.path;
- require a terminal;
- require QApplication;
- print as their primary reporting mechanism;
- use tqdm as the core progress API.

Use:

- callbacks;
- structured events;
- typed results;
- typed errors;
- cancellation tokens.

Preserve media quality and current output behavior.

Do not combine all extractions in one pull request.
```

---

# Stage 25 — Implementation Phase G: GUI-Only Migration and CLI Retirement

```text
Act as a senior desktop-application engineer.

Retire the public media-processing CLI only after all reusable logic has been extracted.

Update:

- GUI callers;
- inference-worker callers;
- controllers;
- services;
- tests;
- README.

Remove:

- public CLI parser;
- public CLI examples;
- public CLI launch commands;
- terminal-only media-processing progress;
- CLI-specific packaging metadata;
- CLI compatibility tests.

Do not remove:

- install.py;
- gui.py;
- install.bat;
- run_gui.bat;
- install.sh;
- run_gui.sh;
- internal worker entry points;
- diagnostic tools;
- backend services.

Delete backend/main.py only if it contains no runtime logic and no callers.

Otherwise convert it to a temporary deprecated wrapper with no business logic.

The final user workflow must be GUI-based.
```

---

# Stage 26 — Implementation Phase H: Dependencies, Installer, BAT and SH

```text
Act as a senior Python DevOps engineer.

Modernize dependencies and source installation incrementally.

Implement:

1. Canonical supported Python version.
2. pyproject.toml where justified.
3. Separate dependency groups:
   - runtime;
   - test;
   - development;
   - CPU;
   - CUDA;
   - DirectML;
   - macOS.
4. Constraints or lock-generation process.
5. Preserve install.py during migration.
6. Improve install.py idempotency.
7. Improve environment repair.
8. Improve post-install validation.
9. Improve install.bat.
10. Improve run_gui.bat.
11. Improve install.sh.
12. Improve run_gui.sh.
13. Support paths containing spaces.
14. Preserve exit codes.
15. Add diagnostic launch mode.
16. Remove obsolete EXE-build documentation and scripts only after confirming they are unused.

Required source workflow:

Windows:
  install.bat
  run_gui.bat

Linux/macOS:
  ./install.sh
  ./run_gui.sh

Direct:
  python install.py
  python gui.py

Do not create binary packages.

Do not bundle Python.

Do not add a binary updater.

Add installer-decision and launcher tests where practical.
```

---

# Stage 27 — Final Verification and Release Gate

```text
Act as an independent principal engineer.

Perform final verification after implementation.

Review:

- architecture;
- configuration;
- startup;
- DirectML;
- CUDA fallback;
- MPS fallback;
- CPU fallback;
- hardware profile;
- model policy;
- model downloads;
- inference worker;
- backend decomposition;
- GUI-only migration;
- dependency reproducibility;
- install.py;
- BAT launchers;
- SH launchers;
- source updates;
- tests;
- security;
- logging;
- performance;
- documentation.

Run all safe tests.

Do not download large models automatically.

Produce:

1. Final test results.
2. Remaining failures.
3. Platform matrix.
4. Installation matrix.
5. Manual hardware tests still required.
6. Known limitations.
7. Security gate.
8. Source-installation gate.
9. Documentation gate.
10. Release blockers.
11. Final readiness score.
12. Launch checklist.
13. Rollback checklist.
14. Final verdict.

Save as:

docs/audits/stage-27-final-verification.md
```

---

# Recommended branch and pull-request order

```text
audit/stage-00-repository-map
audit/stage-01-environment
audit/stage-02-startup
audit/stage-03-configuration
audit/stage-04-hardware
audit/stage-05-models
audit/stage-06-pipeline
audit/stage-07-architecture
audit/stage-08-bugs
audit/stage-09-security
audit/stage-10-logging
audit/stage-11-testing
audit/stage-12-performance
audit/stage-13-installation
audit/stage-14-updates
audit/stage-15-cicd
audit/stage-16-future-ai
audit/stage-17-readiness
plan/stage-18-backlog

test/safety-baseline
fix/directml-metadata
refactor/config-boundary
feat/hardware-profile
feat/model-policy
refactor/output-paths
refactor/workspace
refactor/media-lifecycle
refactor/progress-events
refactor/model-selection
refactor/subtitle-service
refactor/pipeline-orchestration
refactor/gui-only
build/dependency-modernization
build/source-installer
ci/source-release
verify/production-gate
```

---
