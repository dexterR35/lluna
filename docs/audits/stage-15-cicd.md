# Stage 15 — CI/CD Pipeline

Baseline: `main` at `c7aa179`.

## Current state and blockers

Six tracked workflows are packaging/build flows, not quality gates. Windows jobs install QPT, patch its site-packages, mutate `requirements.txt` with `pip freeze`, create bundled releases, and grant `contents: write`. Docker builds prefetch models and push on branch activity. This directly conflicts with Midgard’s source-only product direction.

There is no PR syntax/lint/type/test/security/headless-GUI matrix, concurrency cancellation, minimal permission baseline, dependency review, CodeQL, SBOM, or source-archive checksum release workflow.

## Target pull-request workflow

Matrix: Ubuntu, Windows, macOS; Python 3.12; CPU/no network/no models.

1. checkout with least privilege;
2. setup Python and dependency cache keyed by lock/constraints;
3. install test/dev and minimum CPU runtime groups;
4. repository/metadata/config schema validation;
5. `compileall`;
6. Ruff lint and format check;
7. type check scoped to new core boundaries, expanding over time;
8. unit and safe integration tests;
9. offscreen Qt startup/shutdown smoke;
10. installer decision and BAT/SH static tests;
11. Bandit and `pip-audit`;
12. separate CodeQL, secret scanning, dependency review.

Use workflow concurrency by PR/ref with cancel-in-progress. Standard CI sets network/model-download guards and cannot access production credentials.

## Release workflow

Trigger only on protected semantic version tags:

- verify tag equals `BuildInfo.version`;
- rerun quality/security gates;
- generate changelog from reviewed release notes;
- build clean source archives only;
- exclude venv, user config/token, caches, pending state, generated models, and partials;
- create SHA-256 manifest and CycloneDX/SPDX SBOM;
- attach source, checksums, dependency manifests, and model-manifest metadata to a protected GitHub release.

No EXE, QPT, bundled Python, native app package, Docker release, or model prefetch.

## Permissions and provenance

Default `contents: read`; PR jobs no write token. Release job alone gets `contents: write` in a protected environment. Pin third-party actions by reviewed major or SHA policy, enable artifact attestations where available, retain test reports briefly and release artifacts per release policy.

## Rollback

Do not delete a bad release; mark withdrawn, publish a corrective source tag, preserve checksum history, and document checkout of the prior tag plus `install.py --repair`.

## Acceptance criteria

All three OSes pass Python 3.12 safe tests; no network/models/GPU in standard jobs; no production packaging; least privilege; cached but reproducible dependencies; source archive contents validated; hashes/SBOM published.

## Files inspected

All `.github/workflows/*.yml`, requirements, installer, README, QPT maker, Dockerfile, version metadata, and tests.

Recommended next stage: future AI infrastructure after desktop gates exist.
