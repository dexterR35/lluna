# Stage 17 — Production Readiness Review

Baseline verdict before implementation: **internal alpha**, 4.2/10.

## Weighted scorecard

| Category | /10 | Evidence/classification |
|---|---:|---|
| Architecture | 5 | useful shared worker, but god modules and implicit schemas |
| Code quality | 4 | many broad/silent handlers and global coupling |
| Configuration | 3 | Qt/import side effects, relative path, no schema/atomic recovery |
| Startup reliability | 4 | eager pages and synchronous construction; weak degraded mode |
| Hardware compatibility | 4 | CUDA/MPS/ORT probes exist; DirectML defect and no normalized snapshot |
| Model lifecycle | 4 | queue/recovery exists; incomplete manifest/checksum/license/state model |
| Security | 3 | pickle-capable models, plaintext token, origin mismatch, weak provenance |
| Privacy | 6 | local-first, but temp/log/token policies incomplete |
| Dependencies | 3 | broad ranges, platform conflicts, no constraints |
| Testing | 2 | seven tests, no isolation/lifecycle/GUI matrix |
| Performance | 4 | prefetch/cache concepts, no baselines |
| Cleanup | 4 | shutdown sweep exists; daemon download/temp leak risks |
| Source installation | 4 | substantial installer; wrappers/backend/platform gaps |
| BAT/SH launchers | 3 | only SH tracked; minimal validation |
| Source updates | 3 | notification exists with wrong origin; no verified archive flow |
| CI/CD | 1 | workflows violate source-only direction and omit quality gates |
| Diagnostics | 5 | useful interactive diagnostic categories; no structured persistence/errors |
| Documentation | 4 | detailed README but stale package/CLI direction |
| Licensing | 3 | repository license present; per-model/binary provenance incomplete |
| Supportability | 3 | insufficient tests, diagnostics, and platform matrix |

Security, startup reliability, data/model integrity, and install reproducibility are weighted most heavily.

## Release blockers

1. Wrong repository/update identity.
2. DirectML unreachable/bare-exception path.
3. No safe test isolation or CI quality gate.
4. Model artifacts lack complete verification/provenance/license manifests.
5. Configuration/pending state are non-atomic and source-tree/user-state boundaries are weak.
6. Binary/QPT workflows conflict with declared product direction.
7. Missing tracked install/BAT wrappers and incomplete DirectML/MPS install paths.
8. Resource/temp/shutdown behavior is not regression-tested.

## Pre-release requirements

Typed non-Qt metadata/paths; normalized hardware profile; deterministic model policy; protocol and shutdown characterization; verified source-only launchers/CI; safe error/redaction; model download integrity; configuration recovery; GUI offscreen tests; documented platform limitations.

## Supported platform claim

At baseline, only development Linux CPU behavior is evidenced locally. Windows CPU/CUDA, Windows DirectML, Linux CUDA, and Apple Silicon MPS are **intended, not release-verified**. Do not advertise full support until matrix/manual evidence exists.

## Gates

- Security: fail—origin, model integrity, secrets/provenance.
- Installation: fail—reproducibility and wrapper/platform matrix.
- Model license: fail—complete per-model license/gating acceptance absent.
- Data integrity: conditional—source overwrite is avoided, but partial/temp/atomic behavior needs tests.

## Known limitations

One GPU job at a time; cancellation can wait on native calls; first launch may queue large downloads; generation is CUDA-constrained; offline features depend on installed models; DirectML/ONNX coexistence uncertain; no public accessibility validation.

## Launch/rollback

Launch only after Stage 27 passes. Tag source, publish checksums/SBOM/model manifest, retain prior source tag/config backup, and document environment repair. Rollback switches to the prior source checkout/archive and restores the compatible config backup; models/user media are never deleted.

## First 30 days

Collect opt-in, content-free crash/error codes; monitor install failures, startup/worker handshake, model verification, OOM/cancellation/shutdown, and platform/provider distribution. Publish known issues and rapid source patch guidance.

## Six-month direction

Months 1–2: safety/config/hardware/model integrity. Months 2–3: typed jobs and pipeline extraction. Months 3–4: UX/onboarding/accessibility. Months 4–5: installer/update/CI hardening. Month 6: platform certification and performance budgets.

## Reports used

Stages 00–16, including 7A–7D.

Recommended next stage: dependency-aware implementation backlog.
