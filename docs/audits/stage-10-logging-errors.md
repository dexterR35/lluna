# Stage 10 — Logging and Error Handling

Baseline: `main` at `c7aa179`.

## Current state

`backend/tools/diag.py` provides elapsed-time, category, color, and throttled progress output. It is useful for interactive diagnosis but is print-based, process-local, unstructured, and disabled in common non-TTY launches. Framework code and services also print directly or call `traceback.print_exc()`. GUI pages translate exceptions ad hoc, while numerous broad handlers silently suppress failures.

Verified examples:

- `gui.py:68-99,239-248` has four startup/shutdown broad handlers, two silent.
- `hardware_accelerator.py:169-177` prints a DirectML traceback.
- `version_service.py:36-52` prints request errors.
- `backend/main.py:121-126` treats console printing as an output API.
- worker log/progress events are strings without stable codes or phase fields.

## Target

```text
backend/diagnostics/
  logging.py      configuration and queue/listener setup
  context.py      session/process/thread/job context
  events.py       typed operational events
  errors.py       domain exception hierarchy
  crash_report.py safe local report bundle
  health.py       startup/runtime checks
  redaction.py    secrets/URL/path filtering
```

Use standard `logging` with a process-safe queue and human-readable console sink. Optional rotating local files must live under user data, have bounded size/count, and be disclosed. Diagnostics remain local by default; telemetry is opt-in.

## Required structured fields

`timestamp`, `level`, `event`, `session_id`, `process_id`, `thread`, optional `job_id`, `feature`, `model_id`, `backend`, `device`, `phase`, `elapsed_ms`, safe RAM/VRAM samples, `exception_type`, stable `error_code`.

Never include tokens, authorization headers, environment dumps, raw proxy URLs, prompts/media content, or arbitrary file contents. User paths should be normalized/redacted in shareable reports.

## Typed error taxonomy

- `ConfigurationError` / `ConfigurationCorrupt`
- `DependencyError` / `DependencyUnavailable`
- `HardwareError` / `BackendInitializationError`
- `ModelNotInstalled`, `ModelVerificationError`, `ModelLoadError`
- `InferenceError`, `OutOfMemoryError`, `CancellationError`, `WorkerCrashed`
- `MediaDecodeError`, `InvalidMediaError`
- `OutputWriteError`, `OutputCollisionError`
- `DownloadError`, `OfflineError`
- `UpdateCheckError`

Each error carries a stable code, safe user message, developer detail/cause, retryability, suggested actions, and context IDs. Raw exceptions appear only in expandable diagnostics.

## Policy

| Condition | User surface | Log |
|---|---|---|
| expected cancellation | neutral completion state | INFO |
| offline update check | non-blocking status | INFO/WARNING once |
| optional dependency missing | disabled feature with reason | WARNING |
| unsafe setting clamped | configured/effective explanation | WARNING event |
| model/hash failure | installation blocked, retry/remove | ERROR |
| worker crash | job failed, retry after restart | ERROR with process exit |
| unhandled exception | friendly crash dialog, report location | CRITICAL |

Startup timing events: bootstrap, config, hardware snapshot, Qt creation, shell construction, worker spawn/handshake, window shown, deferred recovery/update, ready. Shutdown: cancel requested, download stop, worker acknowledgement, terminate escalation, workspace cleanup, event-loop exit.

## Migration

1. Add redaction and typed errors without changing UI.
2. Adapt `diag` functions to standard logging so callers remain compatible.
3. Add session/job context and worker queue transport.
4. Replace silent startup/shutdown handlers with logged degraded-mode outcomes.
5. Add shared error presenter and copy-diagnostics action.
6. Replace prints/tracebacks progressively; do not mass-format vendor code.

## Tests

Redaction corpus, no-secret assertions, log level behavior, cross-process job context, exception chaining, safe crash bundle, offline deduplication, and user/developer-message separation.

## Risks and unknowns

High-volume frame progress can flood logs unless sampled. Native crashes may bypass Python handlers. File logging needs Windows rotation tests and privacy review.

## Files inspected

Diagnostics/health/hooks, GUI startup and pages, worker protocol/client/worker, installer, version/download/model helpers, and `backend/main.py`.

Recommended next stage: testing strategy.
