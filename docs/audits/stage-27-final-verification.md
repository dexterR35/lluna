# Stage 27 — Final Verification and Release Gate

Verification date: 2026-07-27. Baseline implementation branch: local `main` based on `c7aa179`.

## Verdict

**Internal alpha — not approved for a public production release.**

The roadmap’s audit set and implementation foundations are complete, and the local CPU/source workflow is materially safer. The release gate remains closed because model integrity metadata is incomplete, configuration is still partly Qt/global, full UX/onboarding is not wired across features, CI has not yet run remotely, and Windows/CUDA/DirectML/macOS/MPS behavior has not been exercised on target hardware.

Final readiness score: **6.3/10**, up from the Stage 17 baseline of 4.2/10.

## Final test results

| Check | Result | Evidence |
|---|---|---|
| focused pytest suite | Pass | 75 passed, 1 skipped, 1.25 s |
| skipped test | Expected local limitation | headless GUI pytest module skipped because host Python 3.14 lacks PySide6 |
| project-venv Qt smoke | Pass | Python 3.12, offscreen; repeated `create_application()` returned one instance |
| Python compilation | Pass | `gui.py`, `install.py`, `backend`, and `ui` |
| diff whitespace/errors | Pass | `git diff --check` |
| SH syntax | Pass | `bash -n install.sh run_gui.sh` |
| source environment validation | Pass with degraded features | all required imports passed; Diffusers and Accelerate reported optional/unavailable |
| GUI import in project venv | Pass | no window/event loop started |
| compatibility pipeline import | Pass | facade and worker pipeline imported; 15 model registry entries |
| hardware diagnostic | Pass on local CPU | Linux x86-64, 6 physical/12 logical, 32 GB RAM, CPU fallback, ORT CPU, FFmpeg |
| Ruff/mypy/Bandit/pip-audit | Not run locally | tools are not installed; workflows now require them |
| full GUI event loop | Not run | would require interactive display and could start services/download recovery |
| production model inference | Not run | no model processing/download was authorized for verification |

No bundled model file was changed or deleted. The existing merged LaMa and ProPainter files were detected but not rewritten.

## Implemented architecture and lifecycle

- Canonical non-Qt build metadata and repository URLs in `backend/core/build_info.py`.
- Absolute override-aware paths and explicit environment initialization.
- DirectML unreachable code/bare exception fixed with deterministic DirectML→CUDA→MPS→CPU behavior.
- Immutable normalized `HardwareProfile`, cached detector, execution policy, diagnostics, and mocked profiles.
- Typed per-feature settings, metadata/levels, validation, migrations, and Fast/Balanced/Quality/Low Memory resolver.
- Explicit default/recommended/configured/effective/clamped setting values and hardware-aware video frame policy.
- Upscale preset control with effective recommendation display; effective tile/output limits reach the worker.
- Shared typed job phases/status/protocol compatibility, typed errors, redaction, and accessible progress/error/empty widgets.
- Per-job subtitle workspace, safer output paths, invalid-video validation, shell-free FFmpeg calls, and stale workspace cleanup.
- Subtitle pipeline moved to `backend/pipelines/subtitle.py`; `backend/main.py` is an import-only deprecated facade.
- Public media CLI/parser and QPT/Docker packaging paths retired.
- Optional model downloads are no longer seeded automatically on ordinary startup.
- Atomic pending-download state writes and corrupt-file backup recovery.
- Typed model inventory, lifecycle states, and file size/SHA verifier.
- Deferred post-show service startup; idempotent close/`aboutToQuit` worker cleanup.
- Non-Qt typed canonical GitHub release check with offline/invalid/disabled states.
- Python 3.12 policy, CPU/CUDA/DirectML/MPS dependency groups, validation-only mode, tracked BAT/SH installers and launchers.
- Source-only quality/security/release workflows with a three-OS test matrix, CodeQL, dependency review, checksums, and SBOM generation.

## Remaining failures and release blockers

1. **Model integrity/provenance:** registry entries do not yet contain verified size/SHA-256/version/license data for every shipped/downloaded artifact. Pickle-capable weights remain a critical trust boundary.
2. **Configuration completion:** `backend.config` remains a Qt-bound global settings facade; full schema versioning, precedence, atomic qfluent writes, secrets storage, and user-data migration are not implemented.
3. **Model lifecycle wiring:** the typed registry/state/verifier foundation is not yet the sole path used by every model manager/downloader/loader.
4. **UX completeness:** shared widgets and Upscale presets exist, but Jobs, error/empty/output experiences, configured/effective display, and accessibility are not integrated across every feature.
5. **Onboarding completeness:** resumable state exists, but onboarding screens, license review, recommendation cards, and download review are not activated.
6. **Pipeline debt:** the subtitle implementation is in the correct package but remains a large class with model/detection/orchestration responsibilities.
7. **Shutdown proof:** cancellation/shutdown during real native inference, FFmpeg encoding, and model download needs target-platform tests.
8. **Dependency reproducibility:** direct dependencies/groups are separated, but fully resolved per-platform lock/constraint artifacts are not published.
9. **Remote CI:** new workflows are syntactically reviewed but have not run on GitHub.
10. **Security tools:** Ruff, mypy, Bandit, and pip-audit were unavailable locally; their first CI results may require remediation.

## Platform matrix

| Platform/backend | Install decision | Import/smoke | Real inference | Gate |
|---|---:|---:|---:|---|
| Linux x86-64 CPU | verified locally | verified | not run | internal testing only |
| Linux NVIDIA CUDA | mocked | not run | not run | blocked |
| Windows CPU | decision/static BAT tests | not run | not run | blocked |
| Windows CUDA | mocked/installer decision | not run | not run | blocked |
| Windows DirectML | success/failure mocked | not run | not run | blocked |
| macOS Intel CPU | installer/static design | not run | not run | blocked |
| Apple Silicon MPS | mocked/installer decision | not run | not run | blocked |

## Installation matrix

- `python install.py --validate-only --yes`: passed against existing Python 3.12 environment.
- `install.sh` and `run_gui.sh`: executable and shell-syntax valid.
- `install.bat` and `run_gui.bat`: present, quoted repository-root logic and exit-code behavior statically tested.
- Clean install, repair after interruption, paths with spaces/non-ASCII, offline wheelhouse, DirectML, CUDA variants, and macOS must still run in their OS CI/manual environments.
- Default installation does not schedule optional model downloads. `--schedule-default-models` is explicit.

## Security gate

**Fail for public release.** Improvements include canonical update origin, no shell-enabled subtitle FFmpeg calls, private workspaces, diagnostic redaction, source-only release workflows, dependency review, and CodeQL. Blocking work is complete model/binary provenance and checksums, dependency audit results, secrets/history review, safe archive update implementation if archive downloads are offered, and review of remaining broad exception/deletion paths.

## Source-installation gate

**Conditional pass for internal Linux CPU use; fail for public multi-platform support.** Required imports and launchers pass locally. Optional generation packages are missing in the current environment, so Generate Image must remain visibly unavailable until installed. Clean target-OS runs remain mandatory.

## Documentation gate

**Conditional pass.** All Stage 00–18 plus 7A–7D and this report exist. README no longer advertises QPT/binary packaging or a public media CLI and points version ownership to the core module. User-facing onboarding, model license/provenance, platform certification, diagnostics sharing, update rollback, and accessibility documentation remain incomplete.

## Manual hardware tests still required

- DirectML install/init/failure and ONNX coexistence on supported Windows versions.
- CUDA 11.8/12.6/12.8 wheel decisions and inference on supported NVIDIA generations.
- MPS model load, unified-memory policy, cancellation, and cleanup on Apple Silicon.
- CPU-only full workflows with missing ORT/Paddle/optional packages.
- low/medium/high VRAM presets at 720p/1080p/large images;
- worker native crash, OOM retry, cancellation during load/inference/encode, and shutdown;
- interrupted/corrupt/insufficient-disk/gated/offline model downloads;
- Windows file locking and non-ASCII/space-containing source and media paths.

## Launch checklist

- [ ] Populate and verify every model/bundled-binary manifest digest/license/version.
- [ ] Run quality, security, and source-release workflows on a protected branch/tag.
- [ ] Pass the platform/hardware matrix above.
- [ ] Complete config migration and corrupt-write recovery for qfluent settings.
- [ ] Integrate shared job/error/empty/output UX into all features.
- [ ] Complete first-run model/license/download onboarding.
- [ ] Validate WCAG/Qt keyboard, focus, screen-reader, contrast, and scaling criteria.
- [ ] Run performance baselines and set budgets for startup, model switch, jobs, and shutdown.
- [ ] Confirm source archives exclude user config, tokens, cache, generated weights, and partial files.
- [ ] Publish checksums, SBOM, model manifest, release notes, known limitations, and rollback steps.

## Rollback checklist

1. Stop Midgard and confirm the worker/process tree has exited.
2. Preserve user media, outputs, model cache, and config backup.
3. Switch to the previous source tag/archive; never reset a dirty user checkout.
4. Run that version’s `python install.py --yes` or documented repair path.
5. Restore only a schema-compatible config backup.
6. Validate required imports and launch with diagnostics.
7. Do not delete models unless a verified manifest declares them incompatible/corrupt.

## Known limitations

One GPU job executes at a time; native cancellation can be delayed; Generate Image is unavailable without optional dependencies and suitable CUDA hardware; advanced/shared UX is incomplete; model license/integrity facts require owner verification; only local Linux CPU bootstrap was exercised.

## Final evidence files

All reports under `docs/audits/`; implementation primarily in `backend/core`, `hardware`, `settings`, `models`, `application`, `diagnostics`, `media`, `onboarding`, `updates`, `pipelines`, GUI/worker compatibility modules, installer/launchers, tests, and `.github/workflows`.
