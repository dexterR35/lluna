# Stage 2 — Startup and Application Lifecycle Audit

## Audit rules and snapshot

This report is a static audit of Midgard's startup and shutdown lifecycle at
commit `c7aa179` (`aupdate models`, 2026-07-27).

- No application, installer, inference job, model download, or update request was
  run.
- No source code, configuration, model, or runtime state was changed.
- The generated `run_gui.sh` and the installer's Windows launcher template were
  reviewed. `run_gui.bat` is absent in this Linux working copy because launchers
  are generated per platform and ignored by Git.
- Existing ignored `config/config.json` was reviewed as runtime state, not as a
  tracked shipped configuration.
- Findings marked **verified** follow directly from control flow. Platform timing
  and driver behavior remain runtime-validation items.

## Executive assessment

Midgard starts successfully by building almost the entire application eagerly.
The launchers normalize the working directory, `gui.py` performs multiple
process-wide side effects while it is imported, configuration and English
translations load before Qt application creation, all six pages and all settings
model managers are built synchronously, a hardware probe imports Torch and ONNX
Runtime on the GUI thread, and the shared inference process is spawned before the
window is shown.

The design has useful safety mechanisms: `spawn` avoids forking a Qt/Torch
process, one inference process serializes heavy jobs, update HTTP runs in a Qt
thread pool, downloads use a FIFO background thread, inference jobs have a
watchdog, and `ProcessManager` provides both window-close and `atexit` cleanup.
Those mechanisms are not yet assembled into one explicit lifecycle.

The highest-risk startup defects are:

1. Configuration is relative to the current working directory and loaded at
   import time.
2. Corrupt configuration and translation failures are silent and have no
   recovery artifact.
3. A first hardware scan, possible `nvidia-smi` call, full page construction,
   model scans, partial-download deletion, and diagnostic dependency imports can
   all run before first paint.
4. Worker startup has no READY handshake. A successful `Process.start()` is
   treated as readiness even if the child later fails during import or setup.
5. Shutdown cancels download state but does not stop or join the download thread;
   it can delete partial files while that thread is still writing.
6. Feature threads and temporary directories have no application-owned cleanup
   registry. Most per-task cleanup is happy-path or reset-driven.
7. `InferClient.shutdown()` is terminal for its process-wide singleton, which
   makes repeated in-process application startup unsafe.

## 1. Launch surfaces

### POSIX launcher

The present working-copy `run_gui.sh`:

1. enables `set -euo pipefail`;
2. changes to the repository directory;
3. replaces the shell with the checkout-relative
   `midgardEnv/bin/python gui.py "$@"`.

`exec` gives Python the launcher PID and allows normal signals to reach it. The
directory change happens to satisfy the relative configuration path. Relocating
the checkout keeps this particular launcher valid. The current `install.py`
template instead interpolates the resolved virtual-environment interpreter path,
so rerunning the installer can replace it with a machine-specific absolute path.

### Windows launcher

`run_gui.bat` is not present in this working copy. `install.py:896-915` generates
it only on Windows:

```bat
@echo off
cd /d "%~dp0"
"<absolute-venv-python>" gui.py %*
```

It also establishes the repository as the working directory and forwards
arguments. Unlike POSIX `exec`, the batch process remains a parent shell.
Quoting of the generated interpreter path is correct. Failure is not explicitly
reported or paused; the Python exit code naturally becomes the batch exit code.

Both launchers are ignored (`.gitignore:4-5`). A copied checkout can therefore
have neither launcher or a stale launcher from an older environment.

## 2. Import-time side effects

Importing `gui.py`, even without entering its `__main__` block, does the
following:

| Order | Side effect | Evidence and consequence |
|---|---|---|
| 1 | Starts the diagnostic epoch | `backend.tools.diag` initializes `_t0` at module import. Reported startup time includes all later imports. |
| 2 | Consumes CLI arguments | `parse_cli_flags()` removes `--diag` and `--no-diag` from `sys.argv` at `gui.py:10`. Importing the module from another runner mutates that runner's arguments. |
| 3 | Patches Paddle behavior | `strip_paddle_cdn_hoster_check()` runs at `gui.py:12-14`; it is not scoped to application bootstrap. |
| 4 | Imports Qt and every page | `gui.py:16-40` loads the full GUI dependency graph, including OpenCV from `ui/home_interface.py` and Pillow/NumPy from image pages. A missing mandatory import aborts before diagnostics or a GUI error surface exists. |
| 5 | Creates Qt configuration objects | `backend/config.py` imports qfluentwidgets under redirected stdout, creates a global `Config`, and calls `qconfig.load()` at `backend/config.py:249-251`. |
| 6 | Reads a relative user file | The path is literal `config/config.json`; direct execution from a different directory loads or later creates a different configuration tree. |
| 7 | Forces a theme in memory | Dark theme is applied globally through qfluentwidgets at `backend/config.py:253-254`. |
| 8 | Reads translations | `backend/interface/en.ini` is read into a global `ConfigParser` at `backend/config.py:256-259`. There is no completeness check. |
| 9 | Mutates the environment | `KMP_DUPLICATE_LIB_OK=True` is unconditionally assigned at `backend/config.py:264`, overriding an explicit caller choice and propagating to spawned children. |
| 10 | Registers eventual process cleanup | Importing `ProcessManager` does not create it; its singleton registers `atexit` only when first instantiated. Importing `InferClient` likewise does not register until `instance()`. |

The spawned inference child imports the main module as part of Python
multiprocessing bootstrap. The `if __name__ == "__main__"` body is protected, but
the side effects above are repeated in the child before it enters
`infer_worker_main`. The worker then imports `backend.config` in its own
interpreter and calls `config.set(config.hardwareAcceleration, ...)` without
`save=False` (`backend/tools/infer_worker.py:102-108`). Usually this is a no-op
because the value matches the parent's launch snapshot, but it leaves a child
process capable of writing the same user file.

## 3. Exact current normal startup

The verified normal sequence is:

1. The launcher changes to the project root and invokes its generated virtual
   environment Python.
2. Python imports `gui.py`; diagnostic flags are consumed and the Paddle patch is
   applied.
3. PySide6, qfluentwidgets, all page modules, service client modules, OpenCV,
   Pillow, and NumPy dependencies in those import graphs load.
4. `backend.config` constructs class-level `ConfigItem` objects, reads
   `config/config.json`, silently substitutes `{}` if the file cannot be opened
   or parsed, forces the in-memory dark theme, reads English translations, sets
   `BASE_DIR` to `backend/`, and sets `KMP_DUPLICATE_LIB_OK`.
5. The main block calls `multiprocessing.set_start_method("spawn")`. This raises
   `RuntimeError` if a start method was already selected in this interpreter.
6. The optional diagnostic banner prints.
7. The High-DPI rounding policy is set before application construction.
8. `QApplication(sys.argv)` is created; `AA_DontCreateNativeWidgetSiblings` is
   set afterward.
9. Application diagnostic hooks are installed only when diagnostics are enabled.
10. `SubtitleExtractorGUI` creates the `FluentWindow` shell and synchronously
    constructs, in order:
    `DashboardInterface`, `BgRemoveInterface`, `UpscaleInterface`,
    `LowLightInterface`, `HomeInterface`, and `AdvancedSettingInterface`.
11. Dashboard construction calls cached `collect_system_info()`. Its GPU branch
    creates `HardwareAccelerator`, imports Torch and ONNX Runtime, probes
    DirectML, CUDA, MPS, and ONNX providers, may initialize driver/runtime state,
    queries the CUDA device name and free VRAM, and reads OS CPU/RAM information.
12. Image page constructors scan model files and normalize selected modes.
    Several model path helpers create model directories while merely checking
    status. A selection correction uses `config.set()` and immediately rewrites
    all persistent configuration.
13. Settings constructs every model manager/card, scans installed model state,
    reads Hugging Face token presence, and registers a download-queue listener.
14. Routes, navigation, settings-to-page signals, the cross-tool busy gate, and
    shell styling are installed.
15. The Hugging Face token is read from environment or `config/hf_token`; if
    found, it is copied into both `HF_TOKEN` and
    `HUGGING_FACE_HUB_TOKEN`. All errors are swallowed.
16. A single-shot 2-second update timer is created if enabled. It cannot fire
    until the Qt event loop starts.
17. First-run soft defaults execute. If not already marked applied, they reuse
    the GUI hardware singleton, read `midgard_runtime.json`, can run
    `nvidia-smi` synchronously with a 10-second timeout, and perform several
    immediate full-file configuration writes plus a non-atomic runtime write.
18. `InferClient.instance().ensure_started()` creates multiprocessing queues,
    starts the daemon inference process, registers it with `ProcessManager`, and
    starts daemon reader and watchdog threads. There is no PING/READY wait.
19. With diagnostics enabled, `report_startup()` synchronously inventories
    hardware, all model families, optional Transformers symbols, Torch,
    Hugging Face Hub, rembg, ONNX Runtime, OpenCV, Pillow, worker state, and
    tracked processes. It can create model directories and adopt local model
    snapshots by touching marker files.
20. Pending recovery clears the cancel flag, deletes every partial artifact
    named in the pending registry, seeds all missing default models, and persists
    registry changes. If anything is pending it schedules an 800 ms Qt timer.
21. The constructor reports “ready”; window diagnostic hooks are connected.
22. The window is shown, then resized and centered.
23. `app.exec()` begins. The first paint can now occur.
24. At 800 ms, pending downloads are dispatched into a process-global daemon FIFO
    thread. At 2 seconds, update checking is dispatched to the global Qt thread
    pool. These operations can overlap.

### Current sequence diagram

```mermaid
sequenceDiagram
    actor User
    participant L as run_gui.sh / run_gui.bat
    participant G as gui.py import/main
    participant C as backend.config globals
    participant Q as QApplication / GUI thread
    participant H as HardwareAccelerator
    participant W as Main window + six pages
    participant I as InferClient
    participant P as Spawned infer worker
    participant D as Download registry/queue
    participant U as Update task

    User->>L: launch
    L->>L: cd project root
    L->>G: venv Python gui.py args
    G->>G: consume diag flags; patch Paddle
    G->>C: import
    C->>C: load relative config.json
    C->>C: load en.ini; force dark theme
    C->>C: set KMP_DUPLICATE_LIB_OK
    G->>G: set multiprocessing start method
    G->>Q: create QApplication
    G->>W: construct window
    W->>W: construct Dashboard first
    W->>H: collect system/hardware info
    H->>H: import Torch/ORT; probe DML/CUDA/MPS/providers
    W->>W: construct five more pages and all managers
    W->>C: apply HF token and soft defaults
    W->>I: ensure_started()
    I->>P: Process.start() (no READY handshake)
    I->>I: start reader + watchdog daemon threads
    opt diagnostics enabled
        W->>H: reuse GUI snapshot
        W->>W: import dependencies and scan all models
    end
    W->>D: clear cancel; delete partials; seed pending
    W-->>G: constructor complete
    G->>Q: show, center, app.exec()
    Q-->>User: first paint
    par after 800 ms
        Q->>D: enqueue pending downloads
        D->>D: daemon FIFO download thread
    and after 2 seconds
        Q->>U: submit update task
        U->>U: HTTP request, 5 s timeout
    end
```

## 4. Startup execution context and blocking

| Operation | Current context | First-paint impact | Risk |
|---|---|---:|---|
| Python imports and Qt plugin loading | main/GUI thread | blocking | Mandatory missing module terminates with console traceback only. |
| JSON configuration and INI translation reads | main/GUI thread, import time | blocking | Small but path/corruption failures are silent. |
| All page/widget construction | GUI thread | blocking | Large widget tree, file scans, and config normalization happen before paint. |
| System CPU/RAM/hostname reads | GUI thread | blocking | Usually small; macOS subprocesses can vary. |
| Torch/DirectML/CUDA/MPS/ORT probe | GUI thread | blocking | Driver/runtime initialization can dominate cold startup. |
| Soft-default `nvidia-smi` | GUI thread | blocking, up to 10 s | Triggered on first/default startup if runtime metadata lacks capability. |
| Inference `Process.start()` | GUI thread | blocking | Spawn imports Python application modules; parent does not wait for readiness. |
| Diagnostic dependency/model inventory | GUI thread | blocking | Enabled by default only when stdout is a TTY, so interactive launch is slower than redirected launch. |
| Pending partial cleanup/seeding | GUI thread | blocking | Recursive HF directory deletion may be substantial. |
| Actual model downloads | daemon Python thread after 800 ms | non-blocking to GUI | Competes for disk/network; callbacks and cancellation are fragile. |
| Update request | global Qt thread pool after 2 s | non-blocking to GUI | Offline wait is up to 5 s but not a first-paint block. |

## 5. Scenario traces

### Normal GUI startup

The exact sequence in section 3 applies. “Ready” currently means that the window
tree exists and `Process.start()` returned, not that the event loop painted,
dependencies passed validation, the worker answered, or deferred work settled.

### First startup after installation

The installer creates an ignored runtime marker, a platform launcher, and may
seed missing default models in `config/pending_model_downloads.json`
(`install.py:864-879`, `install.py:896-915`). On first GUI startup:

- absent `config/config.json` becomes in-memory defaults;
- constructors may write it while correcting model selections;
- soft defaults synchronously detect VRAM/capability, then write several times;
- pending recovery scans for missing defaults and writes the registry once per
  scheduled item;
- after first paint, the 800 ms timer enqueues default downloads one at a time;
- update checking begins around 2 seconds if enabled.

This is not an explicit first-run state machine. “First run” is inferred from a
boolean inside the same config file, installed files, the runtime marker, and a
pending list. A partial installer or deleted config can replay pieces.

### CPU-only startup

Torch reports no CUDA, MPS is false, DirectML is normally absent, and CPU is the
fallback. ONNX may still expose OpenVINO or another provider and label the system
accelerated. If hardware acceleration is disabled in configuration,
`HardwareAccelerator` still performs all probes first and is only later disabled
by feature calls; the master switch does not make startup probing cheap.

Generate Image explicitly requires working CUDA and is disabled by
`cuda_ready_for_generate()`. Other installed models remain available with CPU
fallback. First-run soft defaults choose the smallest batches when no VRAM is
known.

### CUDA startup

The GUI probe calls `torch.cuda.is_available()`, then may query device name and
`mem_get_info()`. The worker is spawned with only the Boolean
`hardwareAcceleration` preference; it does not receive the GUI's detected
device/provider snapshot. The child probes independently when a job imports
`HardwareAccelerator`. Generate performs an additional tiny CUDA allocation and
synchronization each time its readiness gate refreshes.

If both `torch_directml` and CUDA are installed, `accelerator_name` and
`device` prioritize DirectML, while ONNX provider ordering prioritizes CUDA.
That is inconsistent device policy.

### DirectML startup

Detection is only `importlib.util.find_spec("torch_directml")`; the stored value
is a `ModuleSpec`, not a validated Boolean device. The GUI labels DirectML before
attempting to construct a device. Actual initialization is deferred until
`.device`, where a bare `except` prints a traceback and falls back to CUDA/MPS/CPU.
ONNX DirectML is detected independently. There is no capability handshake that
proves Torch DirectML and ONNX DirectML can coexist, despite comments documenting
known conflicts (`hardware_accelerator.py:188-200`).

The current installer has no DirectML mode, so this path depends on an externally
assembled environment.

### MPS startup

Torch checks both `is_available()` and `is_built()`. System info labels MPS.
VRAM policy runs `sysctl hw.memsize` and treats half of unified system RAM as
free GPU memory; this is a heuristic, not available MPS capacity. ONNX
Metal/CoreML discovery is independent. Generate remains disabled because it is
hard-gated to CUDA. The current installer has no macOS/MPS dependency mode.

### Missing configuration

qfluentwidgets catches file-open failure and uses `{}`. All defaults are accepted
without a warning. The file may then be created by any startup-time
`config.set()`. Because the path is relative, “missing” can mean either a true
first run or the wrong working directory.

### Corrupt configuration

Invalid JSON is silently treated as empty configuration. The corrupt file is not
backed up, quarantined, or reported and will be overwritten on the next saved
setting.

For syntactically valid JSON with an invalid enum, qfluentwidgets' decorated
`load()` swallows the exception and aborts the remainder of iteration. Values
loaded before the bad item remain applied; later values stay default. Outcome
therefore depends on JSON key order. Generic numeric/string items have
`ConfigValidator`, which accepts any type. Range validators can themselves raise
on incomparable types, producing the same partial-load behavior.

### Missing optional dependencies

- Dependencies imported by `gui.py`'s eager page graph are effectively
  mandatory; failure aborts before `QApplication`.
- Missing ONNX Runtime is caught by hardware detection and CPU provider fallback
  is reported, though ONNX-dependent features can still fail later.
- Missing Transformers/Hugging Face/rembg is only inventoried when diagnostics
  are enabled; otherwise it appears on download or inference use.
- Missing `torch_directml` simply disables DirectML.
- Missing update dependencies are not optional in practice because
  `AdvancedSettingInterface` imports `VersionService`, which imports `requests`
  eagerly.

There is no pre-Qt dependency report or degraded shell for a missing page
dependency.

### Missing model files

Page controls scan installed state and generally disable or empty choices.
Generate requires an installed marker/snapshot. Enhance and low-light
`selectable_modes()` intentionally allow their default selection even when the
weight is absent, so a user can reach inference and trigger `ensure_model_installed`
inside the worker. That can unexpectedly turn a Run action into a blocking worker
download. Diagnostics report missing files but do not influence readiness.

At every startup, missing default models are scheduled for automatic download,
even if the user is intentionally offline or does not use those features.

### Offline startup

The window can start because startup itself performs no synchronous network
request. At 800 ms, pending/default downloads begin and fail according to each
backend's timeout behavior. Ordinary download exceptions call `fail(...,
keep_pending=False)`, so transient offline failure often removes automatic retry
state. At 2 seconds, update checking waits up to five seconds in a Qt-pool thread,
prints a request error, and reports “no update” because failure returns the
current version. Offline and up-to-date are indistinguishable to the caller.

### Pending model downloads

Startup first creates a cancellation-free state, recursively removes partial
artifacts for all pending items, then seeds defaults. After 800 ms it translates
pending entries into model-manager jobs and starts a daemon FIFO thread. Entries
are neither schema-versioned nor atomically written. Invalid entries are silently
dropped from reads or removed on dispatch exceptions.

“Recovery” always starts over; it is destructive cleanup, not resume. Two app
instances have independent locks over the same registry and model paths.

### Worker startup failure

Synchronous failures creating queues or starting the process are logged and
startup continues. Failures after `Process.start()` but before a job are silent:
the reader only treats a dead process as a crash when an active job exists.
There is no startup timeout, READY event, dependency validation, or user-visible
degraded state. The first job may enqueue to a dead worker and wait until its
watchdog timeout.

### Repeated startup in tests

Several global states make same-process repetition unsafe:

- `multiprocessing.set_start_method("spawn")` without `force=True` raises on the
  second main-block execution;
- Qt permits one `QApplication` per process and deleting it does not reset all
  imported Qt/qfluentwidgets globals;
- `ConfigItem` objects, qconfig, translation data, diagnostic caches,
  `collect_system_info()`'s LRU cache, and singleton instances survive module
  reuse;
- `InferClient.shutdown()` sets `_shutdown_done=True` and leaves the singleton in
  place; `ensure_started()` can spawn again but later shutdown becomes a no-op;
- `ProcessManager` and download queue listeners remain process-global;
- daemon reader/watchdog loops are not joined or reset;
- first-run soft defaults and registries modify ignored files, making tests
  order-dependent unless isolated.

Separate-process tests are currently much safer than repeated in-process app
fixtures.

### Shutdown during processing

The main window's `closeEvent`:

1. requests model-download cancellation, persists a cancel flag, records active
   downloads as pending, and deletes partial artifacts;
2. clears inference callback/job state and synchronously terminates the inference
   process;
3. asks `ProcessManager` to concurrently terminate every remaining tracked
   process;
4. accepts the Qt close through the superclass.

For inference, this is hard termination, not a graceful job completion. The
client discards callbacks before terminating, so pages receive no final
cancel/done state. For downloads, cancellation is cooperative and the queue
thread is neither stopped nor joined. Deleting a partial while the worker writes
it is a race. Feature-level daemon threads are not centrally joined. The
`HomeInterface.closeEvent` cleanup is a child-widget handler and should not be
relied upon to run when only the top-level window closes.

### Current shutdown-hook coverage

There are three independent cleanup paths:

- `SubtitleExtractorGUI.closeEvent` handles downloads, inference, and the broad
  process sweep;
- `InferClient.instance()` registers its `shutdown()` with `atexit`;
- first construction of `ProcessManager` registers `terminate_all()` with
  `atexit`.

There is no `QApplication.aboutToQuit` lifecycle hook, explicit SIGINT/SIGTERM
handler, download-queue `atexit` handler, or unified exception hook. The
window-level Ctrl+C handler only receives a Qt key event while the window has
focus; it is not an operating-system signal policy. Consequently, normal window
close gets the fullest cleanup, while interpreter error, terminal signal, forced
quit, and test teardown take different paths. `atexit` can terminate tracked
processes but does not persist download cancellation intent, join feature
threads, release media handles, or sweep temporary files.

## 6. Detailed findings

### Fragile initialization and silent failure

- Broad `except Exception: pass` protects HF environment setup, soft defaults,
  download abort, and inference shutdown. It also removes evidence needed to
  distinguish an expected degraded feature from state corruption.
- qfluentwidgets' `exceptionHandler` swallows every `BaseException` during load,
  including programming errors and interrupts.
- Translation lookup uses direct section/key indexing throughout constructors.
  A missing INI, section, or key can abort window construction with no fallback.
- `APP_ICON`, backend model paths, configuration, runtime metadata, temp
  directories, and user-selected output paths have different path policies.
- Startup has no rollback. If page five fails, already-created singletons,
  threads, file writes, and widgets remain until interpreter exit.

### Repeated and inconsistent hardware probing

The GUI `HardwareAccelerator` singleton prevents repetition inside one
interpreter, but:

- the GUI and spawned worker each probe independently;
- Generate separately calls `torch.cuda.is_available()` and allocates a tensor;
- soft defaults can separately invoke `nvidia-smi`;
- install-time runtime metadata is read only by soft defaults, not treated as a
  versioned detection snapshot;
- changing the hardware preference toggles enabled state, but detection and
  displayed system information can remain cached;
- DirectML/CUDA/MPS and ONNX provider precedence differ.

### Missing validation

- No supported-Python, Qt platform plugin, writable user directory, FFmpeg,
  translation completeness, schema, model-manifest, disk-space, or network-state
  validation exists before the window.
- A model “installed” check is frequently only file size or marker presence.
- Worker readiness is inferred from process liveness.
- “Application ready” has no single state or signal.
- Multiple instances are neither prevented nor made process-safe.

### Worker orphan and shutdown-leak risks

- `ProcessManager` is helpful but its registry is an unlocked mutable dictionary
  accessed from multiple threads.
- `terminate_all()` blocks the GUI thread and each process termination can spend
  several seconds before force kill.
- reader/watchdog threads are daemon threads and are not joined; multiprocessing
  queues are not closed or `join_thread()`ed.
- inference hard cancel immediately respawns a worker, including during awkward
  races near application close.
- download and page worker threads are daemon threads with no application-owned
  cancellation token/join deadline.
- model manager listeners retain bound widget methods and are not unregistered
  on shutdown.

### Temporary-file cleanup

Midgard uses at least:

- `/tmp/midgard_infer` for inference payloads;
- `/tmp/midgard_upscale`;
- `/tmp/midgard_low_light`;
- background-removal preview/protect directories;
- inference worker `_temp_png()` results;
- video comparison/intermediate outputs and model `.part`/partial directories.

Per-task code removes many files on result, error, task deletion, or reset, but
there is no startup sweep by age/ownership and no shutdown manifest. Killing the
worker or interpreter between creation and callback leaves files behind.
Shutdown does not remove preview temp files belonging to retained task objects.

### Race conditions

1. GUI, worker, installer snippets, and a second app instance can non-atomically
   rewrite `config/config.json`.
2. Registry writes are only thread-safe inside one process, not process-safe or
   atomic.
3. Shutdown deletes download partials while the daemon downloader can still be
   writing them.
4. Queue listeners and `on_done` callbacks may address Qt objects during or after
   their destruction.
5. Inference callbacks execute on the Python event-reader thread. Many page
   callbacks correctly emit Qt signals, but this safety relies on each caller;
   the client contract does not enforce GUI-thread dispatch.
6. Worker death while idle is not detected. A job can race with stale process
   state.
7. The watchdog can kill/respawn while another caller enters cancellation or
   shutdown; the `RLock` serializes client state but external callbacks run while
   it is held, allowing reentrant and latency hazards.
8. Automatic downloads and the update request start close together and contend
   for network resources without a startup policy.

## 7. Target lifecycle

The target should be one explicit, testable state machine:

```text
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
```

“Application Ready” should mean:

- the shell is visible and has painted at least once;
- validated configuration and translation snapshots exist;
- core paths are usable;
- feature capability states are known;
- the inference worker is READY or explicitly degraded/unavailable;
- deferred work has been scheduled, not necessarily completed.

### Target sequence diagram

```mermaid
sequenceDiagram
    actor User
    participant B as Bootstrap
    participant L as Structured log
    participant E as Env/paths/config
    participant H as Hardware probe task
    participant Q as QApplication
    participant S as Window shell
    participant F as Lazy feature registry
    participant I as Inference supervisor
    participant P as Worker
    participant D as Deferred work

    User->>B: launch
    B->>L: initialize stderr + rotating file log
    B->>E: validate interpreter/environment
    E->>E: resolve immutable app and user paths
    E->>E: load, migrate, validate config
    B->>H: collect one immutable hardware snapshot
    H-->>B: capabilities + warnings
    B->>E: validate core and optional dependencies
    B->>Q: create QApplication
    Q->>S: create minimal shell + loading route
    S-->>User: first paint
    S->>F: register feature descriptors
    F->>F: build only initial page; lazy-load others
    S->>I: start worker with config + hardware snapshot
    I->>P: spawn
    P-->>I: READY(protocol, capabilities, pid)
    alt worker ready
        I-->>S: inference available
    else timeout/failure
        I-->>S: degraded mode + retry action
    end
    S->>D: schedule download recovery
    S->>D: schedule conditional update check
    S-->>User: Application Ready
```

### Ownership model

Create an `ApplicationLifecycle` composition root. It owns, in dependency order:

- resolved `AppPaths`;
- structured logger and startup timer;
- immutable validated configuration;
- immutable `HardwareSnapshot`;
- capability/dependency report;
- Qt application;
- service registry;
- window shell and lazy page registry;
- inference supervisor;
- download supervisor;
- update service;
- temporary-artifact registry.

No service should create its own global configuration, hardware, path, or
shutdown policy.

## 8. Failure policy

| Failure | Policy | User surface | Exit behavior |
|---|---|---|---|
| Unsupported Python, missing PySide6/platform plugin, unreadable application resources | Fatal before shell | stderr plus native/Qt fatal dialog when possible; diagnostic ID and log path | Non-zero, no worker/download start |
| User path not writable | Fatal unless a safe temporary read-only profile is explicitly supported | Clear path and remediation | Non-zero or intentional read-only profile |
| Missing/corrupt config | Recoverable | Quarantine original, load defaults/migrated values, persistent warning with “open backup” | Continue |
| Invalid individual setting | Recoverable | Default only that field; log source, key, rejected value type, and rule | Continue |
| Missing translation/key | Recoverable for non-core locales | Fall back key-by-key to bundled English; report locale issue | Continue |
| Hardware probe failure | Recoverable | CPU mode and a capability warning | Continue |
| Missing optional feature dependency/model | Feature-local | Page remains navigable with install/repair explanation | Continue |
| Missing core dependency | Fatal or shell-only repair mode, defined in manifest | Dependency report and repair command | Policy-driven |
| Worker READY timeout/crash | Recoverable | Inference unavailable badge, retry and diagnostics; never wait for first job watchdog | Continue |
| Offline update/download | Recoverable/transient | Offline/paused state, retain retry intent with backoff | Continue |
| Corrupt pending registry | Recoverable | Quarantine registry; reconstruct from verified partial manifests | Continue |
| Unhandled GUI exception | Fatal-safe | Crash report path; initiate idempotent lifecycle shutdown | Non-zero |

Every caught exception should become one of: debug record, startup warning,
feature-disabled reason, retryable service failure, or fatal error. Bare silence
is not a policy.

## 9. Degraded-mode policy

Capabilities should be explicit values, not inferred ad hoc by pages:

```text
AVAILABLE
UNAVAILABLE_DEPENDENCY
UNAVAILABLE_MODEL
UNAVAILABLE_HARDWARE
DISABLED_BY_POLICY
OFFLINE
STARTING
FAILED_RETRYABLE
FAILED_FATAL
```

- The shell, Settings, diagnostics, file browsing, and safe CPU features should
  remain usable whenever Qt and core resources load.
- CPU fallback is permitted only for feature/model combinations declared to
  support it. Generate remains a declared CUDA-only capability until its
  implementation changes.
- DirectML, CUDA, and MPS are separate capability records, each with backend,
  device, provider versions, test result, and reason. Do not label a found module
  as a working accelerator.
- Missing models never trigger an implicit network download from Run. A feature
  shows “model required” and delegates to the download supervisor.
- Offline mode pauses update checks and automatic downloads without discarding
  pending intent. Manual retry remains available.
- A worker failure disables processing but does not destroy user workspaces or
  the window.

## 10. Startup timing points

Use `time.perf_counter_ns()` and one startup correlation ID. Emit structured
begin/end events for:

| Point | Meaning |
|---|---|
| `process.entry` | First executable statement, before application imports |
| `logging.ready` | stderr/file logging usable |
| `environment.validated` | Python, Qt runtime, key native libraries checked |
| `paths.resolved` | application/user/cache/model/temp paths frozen |
| `config.read`, `.migrated`, `.validated` | Separate I/O, migration, validation cost |
| `i18n.loaded` | requested locale plus English fallback ready |
| `hardware.started`, `.completed` | One probe, with per-backend child spans |
| `dependencies.validated` | Core/feature capability matrix ready |
| `qt.created` | `QApplication` constructed |
| `shell.created` | Minimal top-level widget exists |
| `window.shown` | `show()` returned |
| `first.paint` | First top-level paint event |
| `initial_page.ready` | Initial page usable |
| `worker.spawned`, `.ready` | Distinguish OS process start from protocol READY |
| `deferred.scheduled` | Download/update tasks scheduled |
| `application.ready` | Readiness contract satisfied |

Record cold/warm flag, platform, Python/Qt versions, selected hardware policy,
detected backend, diagnostics mode, first-run/migration status, and pending count.
Never log tokens, prompts, full user paths, or environment contents. Establish
budgets after measurement; a reasonable initial objective is first paint under
1.5 s warm / 3 s cold on reference hardware, with worker readiness and optional
features allowed to follow.

## 11. Target shutdown sequence

Shutdown must be idempotent and stateful:

```mermaid
sequenceDiagram
    actor User
    participant S as Window shell
    participant L as Lifecycle
    participant F as Feature controllers
    participant D as Download supervisor
    participant I as Inference supervisor
    participant P as Child processes
    participant T as Temp registry
    participant C as Config/logs

    User->>S: close
    S->>L: request_shutdown(reason)
    L->>S: enter CLOSING; disable new work
    L->>F: cancel jobs; detach UI callbacks
    L->>D: pause queue; cancel active; join deadline
    L->>I: CANCEL active; await terminal event
    L->>I: SHUTDOWN
    I->>P: graceful stop
    alt deadline exceeded
        I->>P: terminate, then kill
    end
    L->>F: join feature threads / close media
    L->>T: remove owned artifacts; retain resumable manifests
    L->>C: atomic final save; flush logs
    L->>S: accept close and quit
```

Required mechanics:

- one cancellation tree rooted in the lifecycle;
- no new jobs once state is `CLOSING`;
- bounded graceful deadlines followed by targeted force termination;
- download queue `stop()`, cooperative cancellation, and `join()`;
- reader/watchdog thread joins and multiprocessing queue
  `close()/join_thread()`;
- callbacks detached before widgets are destroyed;
- every temporary artifact registered with owner, purpose, retention policy, and
  cleanup state;
- stale artifact sweep on next startup using age and ownership manifests;
- `aboutToQuit` plus `atexit` as fallbacks, not the primary cleanup path;
- final exit code reflects clean, degraded, or crash shutdown.

## 12. Migration plan

### Phase 1 — Instrument and make cleanup observable

- Add structured lifecycle logging and the timing points above without changing
  startup order.
- Inventory every thread, process, queue, timer, temp artifact, and callback in a
  runtime status snapshot.
- Add tests for missing/corrupt config, idle worker death, shutdown during each
  job type, shutdown during a download, and repeated subprocess startup.
- Keep existing launch commands and compatibility imports.

### Phase 2 — Extract pure bootstrap inputs

- Implement the Stage 3 path/config/i18n architecture.
- Move diagnostic flag parsing, Paddle patching, environment mutation, and
  configuration loading out of module import into explicit bootstrap functions.
- Resolve paths independently of the working directory.
- Replace global hardware lookups with one immutable `HardwareSnapshot`.

### Phase 3 — Establish capability and readiness contracts

- Define a feature manifest of required packages, models, hardware backends, and
  CPU-fallback policy.
- Add a versioned inference protocol with `HELLO`, `READY`, `FAILED`, heartbeat,
  and capability/config hashes.
- Pass the hardware/config snapshots to the child; prevent child writes to user
  configuration.
- Surface worker degraded state and retry in the shell.

### Phase 4 — First paint before features

- Construct only `QApplication`, the shell, navigation placeholders, and the
  initial lightweight dashboard.
- Move system information and hardware probing to a bounded bootstrap task or
  cache validated by environment fingerprint.
- Lazy-create feature pages on first navigation and show capability placeholders
  while initializing.
- Move soft-default calculation into configuration migration/policy, with one
  atomic commit.

### Phase 5 — Supervise deferred services

- Replace the daemon download singleton with a lifecycle-owned supervisor that
  supports pause, retry/backoff, offline state, atomic manifests, cancellation,
  and join.
- Run partial validation/cleanup off the GUI thread after first paint.
- Run update checks only after readiness and network policy evaluation; represent
  error separately from “no update.”

### Phase 6 — Harden shutdown and multi-instance behavior

- Implement the target shutdown sequence and temp registry.
- Either enforce a single application instance or add file locks and
  process-safe atomic state merges.
- Remove `ProcessManager` broad sweeps once every child has a typed owner.
- Make bootstrap/lifecycle factories disposable so repeated in-process tests can
  create fresh state; retain subprocess integration tests for native libraries.

### Acceptance gates

The migration is complete when:

- importing application modules performs no CLI, file, environment, Qt-global,
  process, or network mutation;
- first paint occurs before hardware, worker, download, and update completion;
- startup produces exactly one configuration and hardware snapshot;
- the worker either sends READY within its deadline or the UI enters an explicit
  degraded state;
- corrupt state is preserved and recoverable;
- no owned non-resumable temp artifacts, threads, queues, or child processes
  remain after tested shutdown paths;
- repeated startup tests are deterministic with isolated user directories;
- CPU, CUDA, DirectML, and MPS capability results are independently testable.
