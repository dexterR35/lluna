# Implementation status for `MIDGARD_CODEX_IMPLEMENTATION_PROMPT (1).md`

Checked items below are implemented and locally verified. Unchecked items are explicit release/product gaps; they are not silently represented as complete.

Last verified: 2026-07-31 with Electron 43.2.0 and Electron Forge 7.11.2.

## Desktop shell and security

- [x] Electron is the only desktop GUI; the old GUI package and launchers are deleted.
- [x] Python sidecar starts hidden on loopback, uses a random session token, and gates window display on readiness.
- [x] Sidecar and inference worker receive graceful shutdown with a forced termination deadline.
- [x] BrowserWindow uses no Node integration, context isolation, sandbox, web security, CSP, denied navigation/webviews, and fixed external URL IDs.
- [x] Preload is a narrow allowlist for files, grants, workflow persistence/recovery, menus, progress, and platform metadata.
- [x] Development renderer, production bundle, and Electron/sidecar Playwright smoke test pass locally.
- [ ] A signed/notarized packaged profile has passed a clean-machine smoke test on every target OS.

## GUI stack and custom system

- [x] React source is JavaScript/JSX only and `@xyflow/react` renders the canvas.
- [x] Tailwind is the only styling framework; the forbidden-framework guard passes.
- [x] All required Midgard component filenames exist with focus/disabled/ARIA behavior and modal focus trapping.
- [x] Semantic design tokens and reduced-motion handling are present.
- [x] Native menus, toolbar, searchable category library, per-node editors and previews, settings, models, drawer, and status bar are connected.
- [x] Layout visibility/sizes persist locally.
- [ ] Strict `checkJs` is enabled but does not yet pass because component props/state need complete JSDoc annotations.

## Qt removal

- [x] Production requirements contain no removed GUI toolkit dependency.
- [x] No production Python module imports the removed toolkit; static guard passes.
- [x] `gui.py`, `ui/`, old launchers, GUI PyInstaller spec, native wrappers, and GUI-only tests are deleted.
- [x] CI runs the removed-stack guard.
- [x] Functional settings use typed schema v2 with atomic one-way migration and backup.

## Node editor and workflow

- [x] Backend-owned catalog includes media/prompt inputs, all seven existing AI adapters, and preview/save outputs.
- [x] Nodes add, move, select, duplicate, copy/paste, delete, label, disable, collapse, and serialize.
- [x] Typed connections reject incompatible or occupied inputs with a user-facing explanation; edges select/delete.
- [x] Pan, zoom, fit, grid, snap, box/multi-select, minimap, file drop, search-to-add, and simple auto-layout work.
- [x] Undo/redo and groups are represented; workflow saves/loads and 30-second atomic recovery autosave are wired.
- [x] Python validates/compiles required inputs/parameters, ranges, ports, duplicates, dangling edges, cycles, schema versions, and outputs.
- [ ] Edge reconnection, loose-edge compatible search, modifier edge insertion, interactive group dragging, ungrouping, and ELK-quality layout remain.
- [ ] A measured 250-node/500-edge performance benchmark remains.

## Execution, artifacts, and existing tools

- [x] Runs execute topologically through adapters and preserve the existing single persistent worker scheduling boundary.
- [x] Generate, subtitle/text removal, background removal, upscale, low-light, object selection, and LaMa retouch adapters are registered.
- [x] Per-node and aggregate progress, logs, statuses, cancellation, safe-boundary pause/resume, watchdog errors, and OS progress are connected.
- [x] Artifacts use IDs, hashes, atomic commits, lineage, metadata, and authenticated binary endpoints.
- [x] Deterministic content-addressed cache and clear-cache endpoint are present.
- [x] Model list/install/enable/disable/remove and queue events are exposed through the control plane.
- [x] Model-free fake-worker vertical slice commits and previews a local artifact in tests.
- [ ] Selected-node/from-node run modes are accepted by the API but currently execute the full validated graph.
- [ ] Worker preview callback payloads are not yet forwarded as `node.preview` events.
- [ ] Full browser mask painting/lasso/feather/invert editor and advanced video overlay/timebase editor remain.
- [ ] Missing-model/file/hardware checks need richer validation remediation metadata.

## Packaging, tests, and quality

- [x] PyInstaller sidecar + Electron Forge packaging inputs validate.
- [x] Checked-in OpenAPI, node catalog, and workflow JSON Schema are generated from Python.
- [x] Full local results: 215 Python tests, 4 frontend tests, and 1 Electron Playwright smoke test passed.
- [x] Renderer production build passes and production npm audit reports 0 vulnerabilities.
- [x] CI covers Python, frontend tests/build, guards, lint, audit, and platform packaging.
- [x] The complete Python suite is green in the current environment without downloading production models.
- [x] Electron Playwright covers window launch, sidecar readiness, node-catalog rendering, and BrowserWindow security preferences.
- [ ] Golden media suites remain.
- [ ] Development-only Forge transitive dependencies currently report npm audit findings; production dependencies are clean. The current full audit reports 43 findings (3 low, 39 high, 1 critical) in build/test tooling.

## File impact summary

- Added `frontend/` Electron, React editor, component system, tests, and packaging configuration.
- Added `backend/api`, `backend/graph`, `backend/artifacts`, model facade, and typed configuration service.
- Reworked Python bootstrap/entrypoint and all direct settings consumers to remove GUI-global configuration.
- Replaced packaging/build and CI desktop paths with Electron plus frozen sidecar.
- Deleted the complete legacy desktop UI and its tests/launchers.

## Verification commands

```text
python scripts/static_guards.py                                      PASS
python -m compileall -q backend midgard.py                           PASS
python -m pytest -q (215)                                             PASS
npm run test:frontend (4)                                            PASS
npm run build                                                        PASS
npm run lint                                                         PASS
npm run test:e2e (1)                                                 PASS
npm audit --omit=dev                                                 PASS (0)
python packaging/build.py --validate-only                            PASS
npm run check                                                        FAIL (JSDoc/type errors)
```
