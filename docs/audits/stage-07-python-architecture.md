# Stage 07 — Python Architecture Review

Baseline: `main` at `c7aa179`.

## Assessment

Midgard is a functional vertical-slice desktop application with a useful process boundary, but dependency direction is inconsistent. UI modules import backend globals; backend services import Qt configuration and translations; `backend/main.py` imports almost the whole subtitle stack; model helpers mix metadata, download, loading, policy, diagnostics, and filesystem operations.

```text
gui.py
 ├─ ui pages/components
 ├─ backend.config (Qt-bound global)
 ├─ InferClient ──spawn──> infer_worker
 └─ model download lifecycle

ui pages ──> tools/* ──> backend.config
infer_worker ──> feature tools ──> model/framework code
subtitle job ──> backend.main.SubtitleRemover ──> OCR/inpaint/media/FFmpeg
```

## Verified findings

### God modules/classes

- `backend/main.py:39-550`: `SubtitleRemover` owns media metadata, detection, models, batches, progress, output naming, FFmpeg, cleanup, and CLI execution.
- `install.py` (~1,000 lines): detection, dependency resolution, environment creation, model verification, launcher generation, and UX.
- `ui/home_interface.py` and `ui/bg_remove_interface.py`: view construction, state machines, file ownership, worker calls, error rendering, and save behavior.
- `ui/advanced_setting_interface.py`: settings presentation and five model managers.

### Global state

- `backend/config.py:249-264` loads and mutates global qfluent config, translation data, theme, and environment at import.
- `HardwareAccelerator._instance`, `InferClient._instance`, `ProcessManager`, download registry/queue, and model-module caches are process globals.
- `diag.py` stores global enablement, timer, and progress throttling state.

### Dependency violations

- Backend hardware imports `backend.config.tr`, coupling detection to Qt-backed configuration.
- `version_service.py` imports PySide `QVersionNumber` and backend translations for a network/domain service.
- `backend/main.py:13-15` mutates `sys.path` and wildcard-imports configuration.
- Several inpaint modules mutate `sys.path`.
- Worker-safe configuration is emulated by mutating the child’s global `config`.

### Circular-import candidates

No deterministic import cycle was observed during compilation, but risk clusters exist between UI model managers, download lifecycle/first-run modules, and model helpers; and between `backend.main`, config, hardware, and inpaint modules. Local imports currently mask some coupling.

### Stable foundations

- `infer_protocol.py` enum vocabulary;
- `ProcessManager`;
- `video_io.FramePrefetcher` and `FFmpegVideoWriter` concept;
- feature-specific constant enums;
- separate model-manager cards;
- download queue/registry separation;
- `vram_budget` bounded retry concept;
- the shared-worker process boundary.

## Target dependency rules

```text
core/config/hardware/models/media (no Qt)
        ↓
pipelines/framework adapters
        ↓
application use cases + scheduler
        ↓
GUI controllers/adapters
        ↓
PySide6 widgets
```

- Core modules do not import Qt, UI, `backend.config`, or concrete frameworks at module import.
- Configuration snapshots and job messages are immutable values.
- Filesystem/network/process actions enter through explicit adapters.
- UI imports use cases and presentation models, never framework loaders.
- Compatibility facades preserve old imports during migration.

## Refactoring sequence

| PR | Extraction | Tests | Rollback |
|---|---|---|---|
| 1 | repository/build metadata and project paths | import without Qt; URL identity | facade exports old names |
| 2 | normalized hardware profile | mocked profiles/failures | `HardwareAccelerator` delegates |
| 3 | typed settings and model policy | boundaries/presets/clamps | legacy config adapter |
| 4 | output path policy | collision/source safety | delegate from old method |
| 5 | job workspace | cleanup/retention | old temp behavior behind adapter |
| 6 | media context | invalid FPS/open/close | `SubtitleRemover` delegates |
| 7 | progress/cancellation values | terminal-event and cancel tests | serialize to old events |
| 8 | model selection | mode compatibility | old `ModelConfig` facade |
| 9 | subtitle service/pipeline | characterization with fakes | deprecated wrapper |
| 10 | remove public CLI | entry-point/caller scan | wrapper retained one release |

Do not move every file into a new package at once. New boundaries can coexist with `backend/tools` until callers migrate.

## Compatibility and rollback

Every old public symbol should re-export/delegate for at least one migration phase. Each extraction must be behavior-characterized first. Rollback is file-local: callers can switch back to the facade without reverting schema files or unrelated work.

## Risks

- Native framework imports make import-only tests expensive and environment-sensitive.
- Qt configuration writes can happen while attempting to test domain code.
- Split model files are repository data and must never be rewritten by tests/refactors.
- GUI and worker may run different in-memory setting values unless snapshots are versioned.

## Files inspected

All tracked Python modules were mapped; detailed review focused on `gui.py`, `backend/main.py`, `backend/config.py`, `backend/tools/*`, `ui/*.py`, and UI model managers.

## Unknowns

Static analysis cannot prove all lazy-import cycles, shutdown behavior after native-library faults, or whether every `backend.main` symbol has an external consumer.

Recommended next stage: production bug audit.
