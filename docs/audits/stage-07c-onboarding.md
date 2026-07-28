# Stage 07C — First-Run Onboarding and Model Setup

**Audit date:** 2026-07-27  
**Scope:** first application launch, hardware summary, storage/output choices,
feature/model recommendation, download review, interruption recovery, offline
operation, and migration from the current first-run queue.  
**Constraint:** design and audit only; no production code was changed.

## Current-state assessment

Midgard has no first-run UI or onboarding state machine. `install.py` writes
runtime hardware hints and schedules missing default models. On each GUI start,
`restart_pending_downloads()`:

1. clears cancellation;
2. deletes pending partial artifacts;
3. calls `seed_first_run_downloads()` again;
4. starts the queue 800 ms later.

The user sees the ordinary application while downloads run. A banner exists
inside Settings, but there is no prior explanation of local processing,
storage, output paths, download sizes, licenses, hardware fit, or feature
readiness. “First run” is inferred from missing files and one
`softDefaultsApplied` boolean rather than a versioned product state.

This creates four product risks:

- network and disk use without informed selection;
- licensing terms not accepted before model acquisition;
- interrupted/offline launches repeatedly attempting setup;
- no stable distinction between onboarding incomplete and application unusable.

Onboarding must be optional to resume and never gate access to already usable
features.

## Goals and non-goals

After onboarding, a user should know:

- Midgard processes media locally;
- what data can still leave the device (model/update downloads);
- where outputs and model files will be stored;
- which hardware was detected in plain language;
- which features work immediately;
- which selected features require downloads;
- size, disk footprint, license, access, and hardware fit for each model;
- how to change choices later in Models and Settings.

Non-goals:

- explain Torch, ONNX, CUDA runtimes, providers, dtype, or driver internals;
- force every model to install before the application opens;
- guarantee download time estimates before useful throughput exists;
- treat an incomplete optional download as failed onboarding.

## First-run state machine

```text
NOT_STARTED
  -> WELCOME
  -> STORAGE_PRIVACY
  -> DETECTING_HARDWARE
  -> HARDWARE_REVIEW
  -> OPERATING_MODE
  -> OUTPUT_DIRECTORY
  -> FEATURE_SELECTION
  -> MODEL_RECOMMENDATIONS
  -> DOWNLOAD_REVIEW
  -> LICENSE_ACTION_REQUIRED (conditional)
  -> INSTALLING
  -> READY
  -> COMPLETE
```

Interruptible branches:

```text
any completed screen
  -> save checkpoint atomically
  -> application close
  -> RESUME_AVAILABLE
       ├─ Continue setup
       ├─ Use app with installed features
       └─ Start over (preserve verified models/licenses unless explicitly reset)

DETECTING_HARDWARE
  -> detection partial failure
  -> HARDWARE_REVIEW with degraded/unknown facts

DOWNLOAD_REVIEW / INSTALLING
  -> OFFLINE_PAUSED
  -> READY_WITH_LIMITATIONS
       └─ retry later from Models/Onboarding

one model download fails
  -> INSTALLING with failed card
       ├─ Retry
       ├─ Skip
       └─ Continue with other models
```

`COMPLETE` means the user reached Ready and acknowledged the setup, not that all
optional downloads succeeded.

## Screen sequence

### 1. Welcome

```text
Welcome to Midgard

Remove text, isolate subjects, improve images, and generate images using
models that run on your computer.

Your media stays on this device during processing.
Internet is used only for model downloads and optional update checks.

[Set up Midgard] [Use defaults later]
```

Include application version and Privacy details. “Use defaults later” opens the
app in limited mode and records a deliberate deferral, avoiding a prompt on
every launch.

### 2. Storage and privacy

Show two separate locations:

- **Outputs:** user-owned results;
- **AI models:** potentially tens of gigabytes.

Display available disk, estimated selected use (initially zero), change buttons,
and a statement that uninstalling models does not remove outputs. Validate
writability and reserve free space. Explain update checking separately.

Do not expose full environment variables or technical cache paths in the main
view.

### 3. Hardware detection

Use an indeterminate phase list:

```text
Checking processor and memory
Checking graphics acceleration
Checking AI runtimes
Checking FFmpeg and storage
```

This is cancellable only as “Continue with basic detection,” not by terminating
the app. Optional backend failure becomes a warning, not a blocking dialog.

### 4. Hardware summary

Example:

```text
NVIDIA GeForce RTX 4070
12 GB graphics memory
32 GB system memory
CUDA acceleration available

Recommended mode: Balanced

Your PC is a good fit for:
✓ Remove Text
✓ Remove Background
✓ Upscale
✓ Fix Low Light
✓ Select Object — Fast
✓ Generate Image — FLUX 4B

Quality Select Object and FLUX 9B are not recommended for this memory.
```

CPU-only example:

```text
CPU processing
16 threads · 32 GB system memory

Recommended mode: Low Memory

Image and video tools are available but may be slow.
Generate Image is unavailable because this Midgard version requires
an NVIDIA CUDA GPU.
```

Expandable “Technical details” links to Diagnostics with Torch, DirectML, MPS,
ONNX providers, Paddle, versions, driver, and failure evidence.

### 5. Recommended operating mode

Four cards:

- Fast;
- Balanced (recommended where supported);
- Quality (only enabled when feasible);
- Low Memory.

Each says what changes in product terms, not numerical internals. This chooses
the initial preset intent; it does not overwrite model-specific user settings
or permanently lock the app.

### 6. Save directory

Show a real output filename preview:

```text
Outputs folder
/Users/Ada/Videos/Midgard

Example:
movie_no_text.mp4
portrait_no_background.png

[Choose folder] [Use source folder]
```

Warn before choosing an unwritable/removable/network path. “Use source folder”
is a defined output policy, not an empty-string implementation detail.

### 7. Feature selection

Cards:

```text
[✓] Remove Text          Models included / download required
[✓] Remove Background    Recommended model download
[✓] Upscale              64 MB
[ ] Fix Low Light        365 MB
[ ] Select Object        ~1.6 GB
[ ] Generate Image       ~13+ GB
```

Sizes come from reviewed manifests, never local guesses. A feature can have
“Available now” when bundled/verified.

### 8. Recommended model downloads

For each selected feature, show one recommended model or compatible pair plus
alternatives. Model card fields:

- feature and model display name;
- quality tier and plain purpose;
- download and installed disk size;
- recommended/minimum RAM/VRAM;
- current hardware fit: Good / May be slow / Incompatible / Unknown;
- license name with View link;
- public/gated status and required action;
- installed/verified state;
- Recommended or Optional badge.

Never equate repository license with model-weight license.

### 9. Download review

Offer:

#### Recommended setup

Best fit for selected features and hardware. Prefer verified bundled models and
one sensible model per feature.

#### Minimal setup

Smallest usable set for selected features. Avoid large optional generation or
quality pairs.

#### Full setup

All compatible, license-eligible models only. Display total size prominently.
Do not offer incompatible/gated-unaccepted items as checked.

#### Choose manually

Per-model selection with compatibility and license filters.

Review includes total download, final disk use, remaining disk, install
location, license actions, and whether the app can be used during download.
Nothing starts until **Download selected models** is pressed.

### 10. Installation progress

One global queue with cards:

```text
Real-ESRGAN x2
Downloading 42% · 27 MB of 64 MB · 8.2 MB/s
[Cancel]

SAM2 Tiny + Grounding DINO Tiny
Queued · 1 model ahead
[Remove from queue]
```

Phases: queued, resolving access, downloading, verifying, installing, ready,
paused offline, failed. Overall setup progress is based on known bytes plus
verification stages, not item count alone.

Buttons:

- Continue in background;
- Pause downloads;
- Retry failed;
- Continue with installed features.

### 11. Ready

```text
Midgard is ready

Available now
✓ Remove Text
✓ Remove Background
✓ Upscale

Downloading in background
• Select Object — 63%

Outputs: …
Models: …
Mode: Balanced

[Start with Remove Text] [Open Midgard]
```

Include links to Models, Settings, and “Run setup again.”

## Hardware-summary design rules

- Use full friendly GPU model, discrete VRAM when reliable, and total RAM.
- Use “graphics memory” and “system memory” in primary copy.
- Say “Apple acceleration,” “Windows graphics acceleration,” or “NVIDIA CUDA
  acceleration” only when confirmed.
- Report multiple GPUs only in a chooser if policy supports device selection;
  otherwise show the selected adapter plus “Other adapters detected.”
- Never fabricate MPS “free VRAM”; describe unified memory.
- Separate “detected” from “tested and ready.”
- If evidence is partial, say “Could not verify acceleration; CPU mode is
  available” and offer Diagnostics/Rescan.

## Model recommendation rules

Inputs:

```text
selected features
HardwareProfile + confidence
ExecutionPolicy
available RAM/VRAM and disk
model manifests and installation state
license/gated prerequisites
selected operating mode
```

Rules:

1. Exclude models incompatible with confirmed hardware/framework capabilities.
2. Exclude models whose license blocks the intended distribution/use until
   accepted.
3. Prefer already verified installed models when quality difference is modest.
4. Choose one default model/pair per selected feature.
5. Respect disk reserve and show alternatives rather than overcommitting.
6. Prefer mobile OCR on constrained CPU/low-memory setups; server OCR for
   Balanced/Quality when RAM and latency allow.
7. Prefer STTN/LaMa according to media intent only after input exists; onboarding
   sets a general default, not a universal answer.
8. Select Object Fast is default; offer Complex only when its calibrated
   resource envelope passes.
9. Generation models are never automatically selected for download solely
   because CUDA exists; feature selection and size/license consent are required.
10. If the ideal model is unavailable offline, recommend the best installed
    alternative and remember the desired download separately.
11. Mark heuristic resource decisions as “estimated”; never claim unsupported
    exact minima.

Recommendation result includes reason codes so UI can explain:

```text
Recommended because it fits your 8 GB graphics memory and uses 1.6 GB less
storage than the Quality pair.
```

## Resume and recovery behavior

Persist an atomic onboarding record after each completed step:

```text
schema_version
onboarding_version
status
last_completed_step
started_at / updated_at / completed_at
privacy_ack_version
output_policy + directory
model_root
hardware_profile_fingerprint
selected_operating_mode
selected_features
selected_setup_kind
selected_model_versions
accepted_license_digests
download_transaction_ids
deferred_reason
```

Do not store credentials or token values in this record.

Recovery:

- validate stored directories and hardware fingerprint on resume;
- preserve verified models;
- reconcile transaction journal before presenting progress;
- if a recommendation changed, show the difference; do not silently replace
  selections;
- if onboarding schema is corrupt, back it up, reconstruct from verified
  durable facts, and resume at the earliest safe screen;
- “Start over” resets onboarding choices, not models, licenses, or outputs
  unless separately selected;
- a new onboarding version can show only new required screens.

## Offline behavior

Detect offline status asynchronously and conservatively; a single failed host
is not proof the entire device is offline.

When downloads cannot connect:

```text
You're offline

Midgard can still use models already installed on this computer.
3 selected models will download when a connection is available.

[Continue with available features] [Retry] [Review models]
```

Requirements:

- no repeated blocking dialogs;
- no startup delay waiting for network;
- pending items remain paused/retryable with backoff;
- installed tools remain usable;
- gated/license pages can be deferred;
- update checks fail silently into Diagnostics, not onboarding errors;
- Ready lists exact available and unavailable features.

## Required configuration/state fields

Application configuration:

```text
output_policy
output_root
model_root
default_preset_intent
updates_enabled
```

Onboarding state:

```text
onboarding_schema_version
onboarding_content_version
status / last_completed_step
selected_features / setup_kind
hardware_fingerprint_at_choice
deferred/completed timestamps
```

License ledger:

```text
model_id
model_version/revision
license_id
license_digest
accepted_at
acceptance_source
```

Download manager owns pending/active transaction state; onboarding stores only
transaction IDs. Secrets remain in the secrets subsystem. Hardware facts remain
in the hardware profile, not duplicated into preferences.

## Migration from current behavior

1. Stop reseeding default downloads on every startup once onboarding version 1
   is active.
2. Import current verified installed models into the model registry.
3. Import pending items as “Previous setup downloads” but do not start them
   until the user reviews the migration screen.
4. Convert `softDefaultsApplied` into an initial recommendation receipt; do not
   reapply it.
5. Convert empty `saveDirectory` to explicit `SOURCE_DIRECTORY` output policy.
   Treat current Generate temp behavior as a migration warning requiring an
   output choice.
6. Existing users see a short “Complete setup” review, not the full welcome
   unless they choose it.

## Test scenarios

- clean install: CPU-only, CUDA, DirectML, MPS;
- low/high RAM/VRAM and insufficient disk;
- no network before launch, loss during each model, recovery after reconnect;
- public, gated, rejected/unaccepted, and changed-license models;
- all four setup choices and manual deselection;
- user closes/crashes at every screen and every download phase;
- corrupt onboarding record, pending record, manifest, and model;
- model already installed, partially staged, or installed by another process;
- output/model directory permission loss or removable drive disappearance;
- hardware/driver changes between interruption and resume;
- installer seeded legacy pending downloads;
- “skip for now,” later resume, and new onboarding content version;
- screen reader/keyboard-only completion at 100–200% scaling;
- multiple application instances attempt onboarding concurrently.

Assertions:

- no unapproved download begins;
- completed verified models survive cancellation/restart;
- the app opens with available features even when onboarding/downloads fail;
- accepted license is bound to exact digest/revision;
- secrets never enter diagnostics/state;
- Ready accurately reflects model and hardware state.

## Incremental implementation plan

1. Add versioned onboarding state and explicit “deferred/complete” semantics.
2. Add reliable HardwareProfile, model manifests, license metadata, and disk
   estimates; onboarding must not invent these.
3. Stop automatic first-launch dispatch; migrate pending items to review.
4. Build Welcome, Storage/Privacy, Hardware, Mode, and Output screens.
5. Build feature selection, recommendation service, and download review.
6. Integrate transactional downloads and structured progress.
7. Add Ready/limited mode, background continuation, and deep links.
8. Add legacy-user migration and onboarding-version upgrade flow.
9. Validate accessibility, interruption at every transition, and offline
   behavior before making onboarding the default.

## Acceptance criteria

- First launch explains local processing, network use, outputs, and models.
- No model download starts without explicit reviewed selection.
- Hardware summary is plain-language and evidence-based.
- Recommendations account for hardware, disk, license, installation, feature,
  and chosen mode.
- Onboarding can be interrupted or deferred without trapping the application.
- Offline launch remains fast and useful.
- Every completed step and download transaction resumes safely.
- Ready shows exactly what is available now and what remains pending.

