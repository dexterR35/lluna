# Definition of done

A feature is `current` only when every applicable item below has evidence.

## Product and UX

- Feature inventory ID and behavior are implemented without silently dropping
  requested modes.
- Empty/absent selections have defined behavior.
- Preview/final and generated/original content are clearly labeled.
- Manual fallback or explicit unavailable state exists.
- Undo/redo, before/after, reopen, and reset behavior are covered.
- Keyboard/accessibility and high-DPI viewport behavior are reviewed.

## Architecture

- Typed command, operation, parameter, buffer, mask, and result contracts exist.
- Coordinate, color, alpha, timebase, and metadata semantics are explicit.
- Operation declares ROI/tile/temporal behavior and identity/strength behavior.
- Capability is provider-independent; model fingerprint is recorded.
- Cache invalidation and project migration are defined.

## Performance and jobs

- Estimate, progress, cancel, error, retry, and cleanup paths work.
- Pause/resume/checkpoints are implemented where the roadmap promises them.
- Proxy and final caches cannot collide.
- Representative large image/video tests meet memory and responsiveness budgets.
- CPU and each claimed accelerator/encoder are tested.
- No new idle busy loop, repeated diagnostics, or unbounded restart behavior exists.

## Persistence and safety

- Source, prior project, and prior outputs are not overwritten unexpectedly.
- Save/output publishing is atomic and failure-tested.
- Autosave/recovery reopens after forced termination.
- Untrusted files/models are bounded and validated.
- Model license, source, hash, privacy, and network behavior are recorded.

## Quality

- Unit, property, integration, UI, and relevant golden tests pass.
- ROI/tile/chunk output matches reference within declared tolerance.
- Quality metrics meet the feature gate and human review is recorded where needed.
- Known limitations and unsupported formats/hardware are user-visible.
- Export round-trip validation passes for every advertised profile.

## Documentation and operations

- User-facing help, parameter units/defaults, and error recovery are documented.
- Developer docs name modules, contracts, migrations, and troubleshooting steps.
- Release notes identify model/download/storage implications.
- Feature flag owner, rollout stage, fallback, and removal plan are recorded.

## Evidence template

```text
Feature IDs:
Implementation PRs:
Schema/protocol versions:
Models/providers and hashes:
Hardware/codec matrix:
Test and corpus versions:
Quality/performance comparison:
Migration/recovery evidence:
Security/license/privacy review:
Known limitations:
Rollback flag and owner:
```

If evidence is incomplete, use `foundation`, `planned-*`, `research`, or `blocked`;
do not describe the feature as shipped.
