# Stage 07B — User Experience and Interface Audit

**Audit date:** 2026-07-27  
**Scope:** installer/launchers, first launch, dashboard, all tool workspaces,
Settings/model cards, shared inference behavior, progress/errors, outputs, and
desktop interaction patterns.  
**Method:** static code and copy review; no production code was changed and no
claim below depends on a visual usability test.

## Executive assessment

Midgard has a coherent dark visual shell and reusable workspace components:
before/after preview, drag-and-drop, task table, action rail, logs, confirmation
dialogs, and per-tool model selectors. It also protects destructive reset and
uninstall actions and provides cancel paths for inference.

The product model is nevertheless fragmented:

- the landing page is both a system dashboard, a prompt router, and Generate;
- tool queues are local tables while the shared GPU queue is invisible;
- model downloads occur in Settings with text-only queue state and no byte
  progress;
- “installed,” “enabled,” “selected,” “loaded,” and “compatible” are not
  presented as distinct states;
- image tools generate temporary previews and require an extra Save action,
  whereas Generate writes immediately and video outputs are created directly;
- errors often fall back to raw exception text in logs or transient InfoBars;
- disabled controls usually do not explain why;
- first-launch downloads start after the window opens without onboarding or
  prior review.

The highest-value change is not a wholesale redesign. It is a persistent Jobs
and Models experience, a consistent output contract, structured progress/error
events, and progressive disclosure around tool settings.

## Current navigation

Current top navigation:

```text
Generate Image (dashboard/home)
Upscale
Remove BG
Remove Text
Low Light
Settings
```

Notable omissions:

- Select Object is embedded inside protect/retouch dialogs, not a discoverable
  standalone task;
- Jobs, Models, and Diagnostics have no routes;
- recent outputs and output history do not exist;
- “Home” in code is Generate, while `HomeInterface` is Remove Text, increasing
  implementation and product-language confusion.

## User-journey map

```text
Acquire source
  -> run install.py
  -> choose CUDA/CPU
  -> wait for package installation and import checks
  -> launcher generated
  -> launch GUI
  -> full window/pages constructed
  -> default model downloads begin
  -> discover tool
  -> select/drop input
  -> choose available model/settings
  -> Run
  -> wait through generic percentage/logs
  -> cancel or finish
  -> save/open/find output
  -> reset/requeue for another run
```

Critical breaks occur at model setup, shared-queue visibility, phase progress,
and output ownership.

## Installation journey

### Current strengths

- installer detects an NVIDIA CUDA candidate and offers CUDA/CPU;
- command output names each subprocess and import verification result;
- missing bundled core models are reported with paths;
- launchers are generated at the end;
- non-interactive flags exist for automation.

### Findings

| Severity | Finding |
|---|---|
| High | Installation is terminal-led with long raw pip output and no stable phase/progress summary. Users cannot distinguish slow from frozen. |
| High | The installer schedules several large first-launch downloads without showing total size, disk need, license, or consent. |
| High | Failure ends with process exit and often pip/subprocess detail; there is no “Retry phase,” repair, or copy-diagnostics workflow. |
| High | Unsupported DirectML/MPS/AMD/Intel cases are reduced to CPU/CUDA choice without a product-level explanation. |
| Medium | Missing Python selection is explained in console only; supported versions and install link are not a guided flow. |
| Medium | FFmpeg is verified only indirectly; missing/broken bundled FFmpeg is not a clear installer capability result. |
| Medium | Existing environment reuse is automatic; there is no health summary or “Repair environment.” |
| Medium | Generated launcher failure closes quickly under some double-click workflows; Windows launcher does not add a user-facing failure pause/report. |

Target installer phases:

```text
Checking Python
Checking hardware
Creating environment
Installing core dependencies
Installing acceleration support
Verifying environment
Checking bundled models
Creating launcher
Ready
```

Each phase needs status, elapsed time, concise failure, log location, retry, and
repair guidance.

## First launch

### Current behavior

- constructs every major page and Settings model card before show;
- shows a system summary on Generate;
- starts/handshakes the inference worker during window construction;
- runs startup health checks;
- seeds and restarts default downloads 800 ms after setup;
- applies one-time VRAM-based subtitle defaults silently;
- defaults output next to source for tasks, but Generate falls back to OS temp
  when no save directory is configured.

### Findings

| Severity | Finding |
|---|---|
| Critical | Default model downloads start without a review screen, size/license/disk disclosure, or explicit user selection. |
| High | Startup can appear blank/frozen because all pages and model cards plus several probes are constructed before the window is shown. |
| High | Generate with no save directory writes to a temporary location while its success copy says “saved”; ownership and retention are unclear. |
| High | Offline first launch emits a sequence of install failures and can discard pending intent rather than provide one stable offline state. |
| Medium | Hardware summary uses technical “Acceleration” and can misreport package/provider presence as usable hardware. |
| Medium | No first-run explanation says processing is local, where models live, or what works before downloads finish. |
| Medium | Pending downloads are visible only as a Settings banner; the landing page does not explain unavailable tools. |

Stage 07C defines the target onboarding flow.

## Screen-by-screen findings

### Generate / dashboard

Strengths:

- concise prompt, model/size/step choices, Enter-to-run, Stop, result preview;
- system summary gives immediate context;
- no-model/CUDA gates provide tooltips and InfoBars.

Problems:

- intent-parsing the prompt for words such as “model,” “video,” or “background”
  can navigate away instead of generating the requested concept;
- only two of four installable generation models appear;
- all sizes are square;
- system cards consume prime workflow space on every visit;
- no negative prompt, seed/result seed, output name preview, or history;
- percentage has no phase/model/device/elapsed time;
- Stop has no visible “cancelling” state;
- “Open” opens the file, not its containing folder;
- failures can display raw worker text and disappear after a timed InfoBar.

Recommendation: make Home a task launcher/recent-work page and Generate a
dedicated route. Remove natural-language navigation from the generation
prompt.

### Remove Text

Strengths:

- accepts images/video, per-task areas and A/B sections;
- visible task list and output status;
- model/detection selectors have detailed descriptions;
- compare output is supported for video;
- cancel/reset confirmations are present.

Problems:

- dense video-selection interactions and punctuation shortcuts are poorly
  discoverable;
- progress merges OCR, inpainting, encoding, audio, and cleanup into one
  percentage/log stream;
- queued shared-worker state is a log line, not an actionable queue row;
- output codec/quality/path are not previewed;
- static images force LaMa through hidden global setting mutation;
- raw exception fallback remains possible;
- completed task repeat semantics differ from other tools.

### Remove Background

Strengths:

- before/after preview, multi-file task list, transparent PNG save;
- Automatic/Protect mode, keep-mask editor, object selection, and retouch;
- re-run after mask changes is supported;
- uninstall/download activity locks processing.

Problems:

- “Protect” is powerful but requires a modal editor and several concepts before
  Run;
- no alpha-matting/refinement controls or explanation of model differences;
- completion creates an unsaved temp preview—closing/resetting can discard it;
- Save/Open Folder/result history are inconsistent;
- error details live primarily in logs;
- model unavailable state yields a log string rather than a model action card.

### Upscale

Strengths:

- simple model/scale selector, denoise switch, batch task list, OOM tile retry.

Problems:

- “Scale” is actually a model selector;
- denoise strength exists in config but UI exposes only On/Off;
- maximum output dimension, automatically selected tile, and estimated output
  dimensions/file size are invisible;
- save defaults to a bare filename rather than configured destination;
- JPEG quality is hardcoded;
- no face enhancement support, which should be clearly absent rather than
  implied by generic “enhance.”

### Fix Low Light

Strengths:

- very simple workflow and before/after preview.

Problems:

- a model selector is shown despite only one choice;
- inputs above 2048 long edge are processed smaller and enlarged back without
  disclosure;
- no strength/color/noise controls;
- output/save inconsistencies match Upscale;
- no indication whether the result is model-restored at native resolution.

### Select Object

Current behavior is an embedded tool in keep-mask/retouch dialogs. It accepts a
click or object name, can add to the mask, and uses the globally selected fast
or complex pair.

Problems:

- not discoverable as a primary capability;
- model download failures direct users to Settings but cannot open the exact
  model card;
- fast/complex is globally configured away from the task;
- confidence/refinement is not visible;
- progress has only loading/running text;
- no standalone output/mask history.

### Settings

Strengths:

- grouped cards, descriptive copy, section reset confirmation, install/on/off/
  uninstall controls, risk badges, output folder, update control.

Problems:

- one long scroll combines expert OCR thresholds, model management, secrets,
  output, updates, and About;
- group descriptions are tooltips on headers rather than persistently readable;
- cards truncate rich descriptions to one line and require hover;
- install cards omit download size, disk footprint, license, hardware fit,
  version, verification, and loaded state;
- text buttons show “Installing…” but not byte progress, speed, ETA, pause, or
  cancel;
- a global queue locks unrelated install/uninstall controls without explaining
  why;
- “On” can be confused with installed, loaded, selected, or running;
- Hugging Face token lives beside ordinary models with failures potentially
  containing raw errors;
- restart requirements are not represented per setting.

## Severity-ranked cross-product issues

### Critical

1. Unreviewed automatic first-launch model downloads and license/disk opacity.
2. Generation safety behavior is not disclosed; SD 1.5 disables its safety
   checker.
3. Output ownership is inconsistent; Generate may store “saved” results in
   temporary storage.

### High

4. Shared inference queue is invisible across tools.
5. Long jobs lack phase-aware progress and reliable cancellation state.
6. Errors frequently degrade to raw exception text or transient notifications.
7. Disabled controls usually lack an adjacent reason/action.
8. Model states and hardware incompatibility are conflated.
9. Unsaved image previews are vulnerable to reset/close without a clear dirty
   state or recovery.
10. Settings expose expert subtitle internals by default.

### Medium

11. Navigation conflates Home and Generate and hides Select Object/Diagnostics.
12. Save dialogs, naming, formats, and action availability differ across tools.
13. Tool repeat/requeue semantics differ.
14. Fixed layout widths and long Settings cards reduce small-screen usability.
15. Prompt keyword routing can surprise users.
16. Logs are used as primary product feedback.

## Navigation recommendation

Evaluate the proposed structure as:

```text
Home
Create
  Generate Image
Edit
  Remove Text
  Remove Background
  Upscale
  Fix Low Light
  Select Object
Manage
  Jobs
  Models
Bottom
  Settings
  Diagnostics
```

Comparison:

| Change | Justification | Caution |
|---|---|---|
| Separate Home and Generate | Home can show readiness, recent work, and task entry; prompt becomes unambiguous | Avoid adding a redundant click for returning users; remember last tool |
| Add Jobs | Makes the single-worker queue and history visible | Do not imply parallel GPU execution |
| Add Models | Removes installation/licensing from general Settings | Keep direct “Install required model” links from tools |
| Add Select Object | Makes a real capability discoverable | Scope standalone output workflow before exposing |
| Add Diagnostics | Central location for technical details/errors | Keep ordinary error messages understandable without it |

Do not implement all routes at once. Jobs and Models provide the most immediate
clarity; Home/Generate separation can follow after history exists.

## Jobs panel design

### Data model

```text
JobRow
  id
  state: queued | preparing | running | cancelling | completed | failed | cancelled
  task_type
  input summary
  model
  effective preset/settings
  device
  phase
  phase_progress
  overall_progress
  queued/started/finished timestamps
  elapsed/estimated remaining
  output paths
  error summary + diagnostic id
```

### UI

- Active job pinned at top with phase, progress, elapsed, device, output target,
  and Cancel.
- Queued rows show position, why waiting, Reorder where safe, and Remove.
- History filters: Completed, Failed, Cancelled.
- Completed actions: Open Result, Open Folder, Repeat, View Settings.
- Failed actions: Retry, Adjust Settings, Copy Diagnostics.
- The panel states clearly: “Midgard runs one accelerator job at a time.”
- CPU-only jobs may run concurrently only after the scheduler intentionally
  supports and communicates it.

Local per-tool input batches can remain, but each dispatched task must map to a
visible application job. One queue is the source of truth.

## Progress-state design

Use structured phases rather than parsing logs:

```text
QUEUED
PREPARING_INPUT
VALIDATING_SETTINGS
ACQUIRING_MODEL
LOADING_MODEL
DETECTING_TEXT / SEGMENTING / GENERATING / ENHANCING
PROCESSING_FRAMES
ENCODING_VIDEO
MERGING_AUDIO
SAVING_RESULT
CLEANING_UP
COMPLETED
```

Presentation:

- phase label and phase-specific progress;
- monotonic overall progress only when phase weights are known;
- indeterminate animation when model load/download duration is unknown;
- elapsed time always;
- remaining time only after enough samples and with a confidence label;
- model and friendly device;
- cancellation changes immediately to “Cancelling safely…”;
- heartbeat detail in an expandable panel, not the primary status.

Never reset a visible bar from 90% to 10% between phases without labeling the
phase. Do not display a fabricated ETA.

## Error-message framework

Structured error:

```text
UserError(
  code,
  title_key,
  explanation_key,
  actions[],
  severity,
  retryable,
  technical_detail,
  diagnostic_id
)
```

Primary card:

```text
Not enough GPU memory

Midgard could not process this video with the selected settings.

Try:
- switching to Balanced or Low Memory;
- lowering Frames processed together;
- closing other GPU applications.

[Use Low Memory and Retry] [Open Settings] [Technical details]
```

Rules:

- never lead with traceback, Python class, provider name, or raw path;
- preserve technical detail in Diagnostics;
- offer at most two primary actions;
- distinguish model missing, downloading, corrupt, incompatible, and disabled;
- keep the error in job history after transient InfoBars vanish;
- use stable codes for support and automated tests.

## Empty and unavailable states

| State | Message and action |
|---|---|
| No input | Describe accepted media and provide Select Files; drop zone remains keyboard operable |
| No model installed | “This tool needs X (size).” Install Model / View Models |
| Downloading | Model, bytes/progress, queue position, Cancel; tool may prepare input but Run explains wait |
| Model disabled | “Installed but turned off.” Enable / Choose another |
| Incompatible hardware | Friendly requirement and compatible alternatives; Diagnostics link |
| Missing FFmpeg | Video processing unavailable; Repair Environment / Diagnostics |
| Offline | Installed features remain enabled; downloads show Paused—Offline / Retry |
| No output yet | Explain where finished results will appear |
| Worker failed | Job retained; Restart Worker and Retry |
| Corrupt model | Disable Run for that model; Verify/Repair/Choose another |

Every disabled primary button needs an accessible description and nearby text
or tooltip explaining the state and remediation.

## Model installation UX

Move model management to a dedicated page organized by feature. Each card:

```text
Model name                      Recommended / Optional / Incompatible
Purpose and quality tier
Download: 1.4 GB · Installed disk: 1.5 GB
Recommended: 8 GB VRAM · This PC: 12 GB (Good)
License: Apache-2.0 [View]
Access: Public / Sign in / Accept terms
State: Not installed / Queued / Downloading 42% / Verifying / Ready / Broken
[Install] [Pause/Cancel] [Repair] [Uninstall]
```

Confirm uninstall with size freed and loaded/job impact. Never uninstall while
a job lease exists. Show verification as a real phase. A failed download keeps
a retryable row and clear offline/auth/disk reason.

## Settings UX

- General: output destination, overwrite policy, startup/update behavior.
- Models: route to Models page, not full cards inline.
- Performance: preset defaults and cache/memory strategy.
- Advanced: task-specific advanced controls.
- Expert: hidden framework/worker controls.
- About: version, releases, feedback.

Reset is scoped, previews changed values, and states whether models/files are
affected. Setting rows show “Applies immediately,” “Next job,” “Restart
worker,” or “Restart app.”

## Output workflow

Unify all tools around an `OutputPlan` chosen before Run:

```text
root directory
filename template / preview
format and quality
overwrite policy: Ask | Rename | Replace
retain partials: Never by default
```

Requirements:

- create directories before admission and validate writability/free space;
- show the exact destination beside Run;
- write to a staging file, then atomically finalize;
- never call an OS temp file “saved output”;
- completed jobs offer Open Result and Open Folder;
- keep recent output history with missing-file detection;
- use consistent suffixes and collision-safe names;
- retain a failed partial only through explicit recovery/debug policy;
- prompt before discarding an unsaved preview on close/reset/delete;
- Repeat creates a new job with the prior effective-settings snapshot.

## Incremental pull-request plan

1. **Structured states:** define job phases, user error codes, model state labels,
   and output plan without changing layouts.
2. **Persistent feedback:** replace raw/transient errors with reusable error
   cards and technical-detail links.
3. **Output consistency:** configure output before Run, atomic finalize, Open
   Folder, recent outputs, dirty-preview warnings.
4. **Jobs page:** expose shared scheduler state/history and map tool tasks to
   job IDs.
5. **Models page:** add metadata, progress, license, capacity, repair, and deep
   links from unavailable tools.
6. **Progress phases:** instrument each pipeline and replace generic bars/logs.
7. **Settings disclosure:** move expert controls, add preset summary and apply
   scope badges.
8. **Navigation/onboarding:** separate Home/Generate, expose Diagnostics and
   Select Object when their workflows are ready.

Each PR should preserve existing routes or provide redirects and include
keyboard/accessibility acceptance tests.

## Usability acceptance criteria

- A new user can identify an available tool and produce/find an output without
  visiting raw logs.
- No model download begins without size/license/destination review.
- Users always know queued/running/cancelling/completed/failed state.
- One shared worker and queue are visible and understandable.
- Every long task reports meaningful phases and elapsed time.
- Every disabled action explains why and offers a next step where possible.
- No primary error contains a raw traceback.
- Outputs have a visible destination before work and consistent result actions.
- Model installed/enabled/selected/loaded/compatible states are distinct.
- Destructive and dirty-state actions are confirmed and recoverable.
- Simple workflows do not require CUDA, ONNX, dtype, tile, or batch vocabulary.

