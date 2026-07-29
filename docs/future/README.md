# Midgard Studio future architecture

Status: planning source of truth  
Audience: product, UI, image/video, ML, platform, QA, and release engineering  
Scope: future work only; these documents do not claim that planned features already exist

This directory turns the complete image/video editing backlog into an implementable,
non-destructive architecture. It preserves the existing application and introduces
capabilities behind versioned contracts and feature flags.

## Reading order

1. [Charter and engineering principles](00-charter-and-principles.md)
2. [Current-state and gap audit](01-current-state-and-gap-audit.md)
3. [Complete feature inventory and traceability](02-feature-inventory-and-traceability.md)
4. [Implementation status and evidence](implementation-status.md)
5. [Target architecture](architecture/README.md)
6. [Non-destructive operation graph](architecture/operation-graph.md)
7. [Project format and recovery](architecture/project-format.md)
8. [Jobs, cache, performance, and cancellation](architecture/jobs-cache-recovery.md)
9. [Color, metadata, and precision](architecture/color-metadata-precision.md)
10. [Model capability contracts](architecture/model-capabilities.md)
11. [Image implementation](image/README.md)
12. [Video implementation](video/README.md)
13. [Delivery roadmap](delivery/roadmap.md)
14. [Implementation playbook](delivery/implementation-playbook.md)
15. [Testing and quality gates](delivery/testing-quality-gates.md)
16. [Model governance, security, and privacy](delivery/model-governance-security.md)
17. [Migration and rollout](delivery/migrations-rollout.md)
18. [Definition of done](delivery/definition-of-done.md)

## Status vocabulary

| Status | Meaning |
|---|---|
| `current` | A usable implementation exists in this repository today. |
| `foundation` | Part of the required primitive exists, but the feature is incomplete. |
| `planned-native` | Implement with deterministic image/video code and UI. |
| `planned-model` | Requires a model adapter, weights, provenance, and hardware policy. |
| `research` | Quality or product feasibility must be proven before commitment. |
| `blocked` | A named dependency or legal/product decision prevents implementation. |

Nothing becomes `current` merely because it is documented. Status changes require
the acceptance evidence defined in
[Definition of done](delivery/definition-of-done.md).

## Repository policy

- Existing tools remain functional while the editor engine is introduced.
- Existing mask and project data is migrated, never silently discarded.
- Source media is immutable. Every edit is an operation, parameter, mask, or asset.
- CPU is a first-class backend. CUDA, DirectML, and MPS are optional accelerators.
- Missing optional models/codecs degrade capabilities; they do not prevent startup.
- No idle one-second watchdog or model scan is part of this design. Health checks
  are event-driven, job-scoped, or explicitly requested by diagnostics.
- Preview output is explicitly labeled and never overwrites a full-resolution result.
- Every model-backed feature has a deterministic fallback or an unavailable state.

## How to use these documents

Each feature has a stable ID in the inventory. Pull requests and issues should cite
those IDs, the operation node or service contract they implement, and their
acceptance tests. A feature spanning UI, worker, persistence, and export is not
complete until all four surfaces are covered.
