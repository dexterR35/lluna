# Stage 08 — Production Bug Audit

Baseline: `main` at `c7aa179`. Severity reflects user/data impact; confidence is static-analysis confidence.

## Findings register

| ID | Sev. | Conf. | Location | Reproduction and impact | Root cause / fix / regression test |
|---|---|---:|---|---|---|
| BUG-001 | High | High | `backend/tools/hardware_accelerator.py:169-177` | Install `torch-directml`; access `device`; the success branch returns before assigning state and catches every exception bare. Failed initialization falls through unpredictably and leaks a traceback. | Unreachable assignment and bare `except`; catch `Exception`, mark DML unavailable, structured warning, deterministic CUDA→MPS→CPU fallback; mock import/device failure. |
| BUG-002 | High | High | `backend/config.py:24-29` | Update checks target `midgard-app/midgard`, not canonical `dexterR35/midgard`; users can miss updates or trust the wrong endpoint. | Duplicated wrong metadata; centralize identity and derive URLs; exact URL tests. |
| BUG-003 | High | High | `backend/main.py:55-73` | Open corrupt/unsupported media or a still image; FPS/size may be zero before writer creation. Encoding can fail or create corrupt output. | No capture-open, dimension, frame-count, or FPS precondition; validate before temp/writer allocation; invalid-media tests. |
| BUG-004 | High | High | `backend/main.py:68`, `433-464`, `483-494` | Failure/cancel during audio extraction or merge can leave open temp handles/files; Windows can retain locks. | Scattered cleanup and `stdin=open(...)` without context manager; job workspace/context managers; injected subprocess failures. |
| BUG-005 | High | Medium | `gui.py:235-250`; `infer_client.py` shutdown path | Close while native inference or download blocks. The window performs synchronous shutdown/terminate on the GUI thread and may freeze or kill before cleanup acknowledgement. | No bounded staged shutdown UI/state; add cancellation deadline, worker acknowledgement, terminate/kill escalation and test hung fake worker. |
| BUG-006 | High | High | `model_download_registry.py:143-150` | Process interruption while writing pending downloads can truncate JSON; next startup silently treats it as empty and loses recovery state. | Non-atomic write and silent error; temp+fsync+replace, corrupt backup, schema validation; interruption tests. |
| BUG-007 | Medium | High | `model_download_queue.py:72-91,119-145` | Listener calls execute while the queue lock is held. A listener that queries queue state deadlocks. | `_notify()` invoked inside lock; snapshot under lock and notify outside; reentrant-listener test. |
| BUG-008 | Medium | High | `gui.py:68-80,239-248` | HF token/default/config/shutdown failures disappear. User sees missing behavior with no explanation. | `except Exception: pass`; emit safe diagnostics and degraded state; failure-injection tests. |
| BUG-009 | Medium | High | `gui.py:338` and `backend/main.py:543` | Repeated entry-point execution in one interpreter raises `RuntimeError: context has already been set`. | Unconditional `multiprocessing.set_start_method`; use `allow_none`/`force` policy in a bootstrap helper; repeated-start test. |
| BUG-010 | Medium | High | `version_service.py:18-57` | Offline/startup request blocks its calling thread up to endpoint timeout and prints raw network details. | Qt-coupled synchronous network service; run deferred worker, typed result, quiet offline state; timeout/offline tests. |
| BUG-011 | Medium | Medium | feature pages’ `_temp_*` helpers | Repeated completed/cancelled jobs accumulate `midgard_*` files under system temp. | No centralized ownership or age cleanup; workspace manifest/retention policy; lifecycle test. |
| BUG-012 | Medium | High | `backend/main.py:114-118` | A zero-length progress total causes division by zero. | Assumes `tbar.total > 0`; safe denominator/unknown progress; zero-work test. |
| BUG-013 | Medium | High | `backend/config.py:249-264` | Import from a different working directory reads/writes a relative `config/config.json` and mutates `KMP_DUPLICATE_LIB_OK`. | CWD-relative path and import side effects; absolute path module and explicit environment bootstrap; chdir/import test. |
| BUG-014 | Medium | Medium | `restart_pending_downloads()` plus first-run seeding | Closing during background installation deletes partials and restarts full downloads; repeated startup can requeue unexpected large work. | Pending state lacks bytes/checksum/state/version and UI consent; explicit queue states, no auto-full-redownload without notice. |
| BUG-015 | Low | High | `version_service.py:16,63-73` | Typo `lastest_version`, bare exception, and `os.popen` reduce diagnosability. | Replace Qt comparison with semantic parser and safe platform proxy adapter. |

## Race and orphan analysis

- `InferClient` centralizes worker ownership and registers `atexit`, reducing orphan risk, but native hangs still require bounded termination verification.
- Download work uses daemon threads; interpreter exit can cut writes/downloads at arbitrary points.
- UI model-manager callbacks can outlive widgets during shutdown unless disconnected or guarded.
- Worker events arriving after cancellation/restart must be rejected by run ID; this exists conceptually but needs characterization.
- `ProcessManager.terminate_all()` is a broad final sweep and can conceal ownership errors.

## Fix order

1. Safety tests and deterministic network/model isolation.
2. BUG-001/002/006/007/009.
3. Typed config/path boundary and atomic state.
4. Job workspace/media validation and resource contexts.
5. Staged shutdown and stale-event tests.

## Files inspected

`gui.py`, `backend/main.py`, hardware, inference client/worker/protocol, downloads, version checks, video I/O, feature pages, model helpers, installer.

## Unresolved runtime questions

Native cancellation time, DirectML/ONNX coexistence, Windows lock behavior, CUDA OOM recovery, MPS memory reporting, and corrupted media behavior need platform runs.

Recommended next stage: security audit.
