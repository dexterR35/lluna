# Stage 18 — Consolidated Implementation Backlog

This backlog consolidates Stages 00–17. Priority: P0 release blocker, P1 pre-release, P2 post-release.

| ID | Pri | Depends | Exact scope | Behavior / acceptance / tests | Size; risk |
|---|---:|---|---|---|---|
| SAFE-01 | P0 | — | `pyproject.toml`, `tests/conftest.py` | markers, network/model/user-config isolation; suite passes CPU/offline | M; low |
| SAFE-02 | P0 | SAFE-01 | `tests/fakes`, hardware/update/model fixtures | required CUDA/DML/MPS/ORT profiles and deterministic fakes | M; low |
| META-01 | P0 | SAFE-01 | `backend/core/build_info.py`, config facade | canonical `dexterR35/midgard`, derived URLs, no Qt import | S; low |
| DML-01 | P0 | SAFE-02 | `hardware_accelerator.py` device path | no bare/unreachable code; failed DML marked unavailable; ordered fallback | S; medium/Windows |
| CONF-01 | P0 | META-01 | `backend/core/paths.py`, `environment.py` | absolute roots and explicit environment setup; facade compatibility | M; medium |
| CONF-02 | P1 | CONF-01 | config loader/migration/state writers | schema, validation, atomic write, corrupt backup, precedence | L; high |
| HW-01 | P0 | SAFE-02,CONF-01 | `backend/hardware/*` | immutable normalized profile; explicit CPU fallback/cache | L; medium/platform |
| SET-01 | P1 | HW-01 | `backend/settings/*` | typed feature schemas/metadata, legacy compatibility | L; medium |
| SET-02 | P1 | SET-01 | preset resolver | deterministic Fast/Balanced/Quality/Low Memory plus reasons | L; medium |
| POLICY-01 | P0 | HW-01,SET-01 | execution/model policy | configured/recommended/max/effective; visible clamps | L; high/quality |
| MODEL-01 | P0 | CONF-01 | model metadata/manifests | source/license/gating/files/size/hash/backend requirements | XL; high |
| MODEL-02 | P0 | MODEL-01 | downloader/verifier/state | atomic partial, disk/hash verify, corrupt recovery | XL; high/network |
| OBS-01 | P1 | CONF-01 | `backend/diagnostics/*`, `diag` facade | redacted structured session/job logs and typed errors | L; medium |
| JOB-01 | P0 | SAFE-01 | `infer_protocol.py` | typed, versioned requests/status/results/errors over compatible wire | L; medium |
| JOB-02 | P0 | JOB-01 | client/worker | handshake, stale events, crash restart, bounded shutdown tests | L; high/process |
| UX-01 | P1 | JOB-01 | shared job status/progress/error/empty models/widgets | visible phases/queue/error actions/output; accessibility properties | XL; medium |
| PIPE-01 | P1 | SAFE-01 | output path module | collision-safe, source-safe deterministic output names | S; low |
| PIPE-02 | P1 | PIPE-01 | workspace module | per-job temp ownership, quarantine/cleanup | M; medium |
| PIPE-03 | P1 | PIPE-02 | media lifecycle | validate/open/close capture/writer/subprocess | L; high/media |
| PIPE-04 | P1 | JOB-01 | progress/cancellation | structured phases and cooperative tokens | M; medium |
| PIPE-05 | P1 | POLICY-01 | model selection service | task/backend/model compatibility outside CLI/UI | M; medium |
| PIPE-06 | P1 | PIPE-03/04/05 | subtitle service/orchestrator | `SubtitleRemover` delegates; behavior preserved | XL; high |
| CLI-01 | P1 | PIPE-06 | backend main/README/callers | public media CLI removed; internal worker and services retained | M; medium |
| INST-01 | P0 | SAFE-01,META-01 | pyproject/requirements/constraints | Python 3.12 and separated groups | L; high/platform |
| INST-02 | P0 | INST-01 | `install.py` | backend decisions, repair/validate, idempotency, no default models | XL; high |
| LAUNCH-01 | P0 | INST-02 | tracked install/run BAT/SH | root/venv validation, quoted paths, diagnostics, exit status | M; medium |
| UPDATE-01 | P1 | META-01,OBS-01 | update client | non-Qt semantic/offline/rate-limit/channel result | M; medium |
| CI-01 | P0 | SAFE/INST/LAUNCH | GitHub workflows | three-OS quality/security CI, source-only release | L; medium |
| DOC-01 | P1 | CLI/INST/UPDATE | README/docs | GUI-only source flows, support/limitations/licenses | M; low |
| VERIFY-01 | P0 | all P0 | safe suite and Stage 27 | release gates, platform/manual matrix, rollback | M; low |

## Pull-request grouping and non-goals

Each row is independently reviewable; large/XL rows split by feature or extraction. No PR combines architecture with mass formatting, bundled model changes, visual redesign, binary packaging, or parallel-GPU scheduling. Compatibility facades remain until callers and tests migrate.

## Dependency order

```text
SAFE -> META/DML -> CONF -> HW -> SETTINGS/POLICY
     -> JOB + PIPE extractions -> GUI-only
MODEL integrity runs after paths and alongside pipeline work
OBS supports UX/update
INST -> LAUNCH -> CI -> DOC -> VERIFY
```

## Platform impact

Hardware, dependencies, installer, launchers, and process shutdown require Windows/Linux/macOS mocks plus manual target runs. Pure metadata/path/settings/protocol work runs everywhere. DirectML changes require Windows evidence; MPS requires Apple Silicon; CUDA requires NVIDIA Linux/Windows.

## Rollback policy

Old imports delegate to new modules; wire format stays compatible while typed wrappers land; pipeline extractions keep `backend.main` as a facade; installer state is additive; workflow replacement can be reverted independently. Never roll back by deleting user config, models, or outputs.

## Definition of complete

Acceptance tests in the table pass offline/CPU, no production model changes occur, source-only workflows replace packaging, relevant audit findings are closed or explicitly accepted, and Stage 27 records remaining manual platform gates.
