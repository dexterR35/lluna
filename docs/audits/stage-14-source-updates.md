# Stage 14 — Source-Based Update System

Baseline: `main` at `c7aa179`.

## Current state

`VersionService` synchronously queries a hardcoded GitHub latest-release endpoint, compares through Qt `QVersionNumber`, and lets the settings UI notify/open a release. It does not distinguish checkout/archive installs, use semantic prerelease/channel rules, cache rate-limit state, verify source archives, guide backup/repair, or migrate configuration. Application and model downloads are separate in code, but the user-facing lifecycle is not formalized.

The configured origin is incorrect (`midgard-app/midgard` instead of canonical `dexterR35/midgard`), making the current update gate unsafe.

## Target flow

```text
BuildInfo + InstallationKind
  -> cached GitHub release client
  -> semantic version/channel comparison
  -> non-blocking notification
  -> official release page OR verified source archive
  -> user-controlled source replacement while app is closed
  -> python install.py --yes --repair
  -> config migration and validation
```

### Git checkout

Show current branch/dirty-state guidance. The user closes Midgard, backs up local changes, runs `git pull --ff-only`, then `python install.py --yes --repair`. Midgard must never run `git reset`, discard changes, or overwrite the active checkout.

### Source archive

Download only from the canonical GitHub release, verify published SHA-256, unpack into a new sibling directory with traversal/symlink defenses, preserve user data/models outside the source tree or copy through an explicit migration, run validation, then let the user switch launch location. Do not overwrite running files.

## Policies

- Stable/beta channels are explicit; prereleases never replace stable by accident.
- HTTP uses conditional requests, a clear user agent, short timeout, cached last success, and rate-limit/backoff handling.
- Offline is a quiet stale/unknown status, not an error dialog loop.
- Update checks are deferred after ready and cancellable at shutdown.
- Model updates use the model manifest/state machine, never app-release version.
- User config has schema migration and atomic backup; tokens stay outside backup bundles by default.
- Rollback means retain the prior source directory/tag and config backup until the new version validates.

## Typed result

`UpdateStatus(current, latest, channel, checked_at, source_url, release_url, checksum_url, state, message)` where state is `UP_TO_DATE`, `AVAILABLE`, `OFFLINE`, `RATE_LIMITED`, `INVALID_RESPONSE`, or `DISABLED`.

## Acceptance criteria

Canonical origin only; no binary/self update; no source mutation while running; semantic comparison tests; mocked offline/rate-limit/malformed responses; checksum and safe-extraction tests; model/app update separation; user-data preservation and rollback checklist.

## Files inspected

`backend/tools/version_service.py`, config metadata, settings update UI, README, installer, model download modules, workflows.

Recommended next stage: source-only CI/CD design.
