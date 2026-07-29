# Senior developer implementation playbook

This is the repeatable build process for every feature ID. It prevents UI-first
features that cannot persist, cancel, recover, or export correctly.

## 1. Write the contract first

Create or extend:

- operation parameter schema with units, bounds, defaults, and version;
- typed input/output media descriptors;
- mask roles and empty-mask behavior;
- capability request/result when a model is required;
- stable structured errors;
- acceptance fixtures and metrics.

Reject ambiguous booleans such as `use_mask`. Prefer explicit fields such as
`effect_mask_id`, `protect_mask_id`, `trimap_id`, and `mask_space`.

## 2. Build a CPU reference where practical

Deterministic operations—mask algebra, morphology, curves, transforms, blending,
ROI composition, timebase math—get a small correct CPU implementation before
optimization. It becomes the oracle for tiles, GPU kernels, and providers.

Model-only features get a fake provider that produces deterministic fixtures so
document, worker, UI, persistence, and cancellation can be built without weights.

## 3. Add the operation node

For a new node:

1. assign a namespaced type and schema version;
2. validate parameters and references;
3. declare locality, padding, tile/context requirements, and proxy behavior;
4. implement identity/strength blending;
5. canonicalize cache-key inputs;
6. serialize unknown future fields losslessly;
7. add graph and migration tests.

Do not put device selection or concrete model paths in the node.

## 4. Add provider adapters

Wrap current tools first where possible. The adapter converts typed buffers to the
provider format, performs inference, converts back, validates output, and reports
metrics. It owns framework/device details. It does not own project state or write
the final destination.

Provider review checklist:

- model registry entry and exact fingerprint;
- CPU/accelerator matrix and dtype;
- memory estimate and tile/chunk behavior;
- cooperative cancellation boundaries;
- license/provenance/privacy record;
- output validation and actionable failures;
- deterministic seed/candidate behavior.

## 5. Integrate rendering, ROI, and cache

Add the operation to the planner, including dirty-region propagation and dependency
hashing. Test full-frame first, then ROI/tile/proxy equivalence. Include transforms
and padding; never crop only to the visible mask if the model needs context.

Cache only validated immutable artifacts. A cancelled or stale-revision result may
be cleaned up but never attached to the document.

## 6. Persist and migrate

Store operation parameters and stable asset/mask references in the project. Add:

- round-trip test;
- older-version migration fixture;
- unknown-field preservation test;
- missing-model/missing-linked-asset open behavior;
- autosave journal replay test.

Never change existing source or mask files during import.

## 7. Implement UI through commands

The controller turns UI intent into commands and subscribes to revision-tagged
render results. Widgets do not call backend tools directly. Required states:

- unavailable/missing dependency;
- idle and editable;
- preview queued/running/cancelling;
- preview approximate/stale;
- final queued/running/paused;
- failed with action;
- completed with inspect/export options.

Every operation exposes before/after and reset. AI candidates require preview,
choose, regenerate, keep, and delete flows.

## 8. Add job semantics

Define progress stages and weighted units. Add cancel before/after provider calls,
pause/checkpoint at safe units, resume validation, resource estimates, and atomic
publish. Induce worker death, OOM, disk full, and user cancellation in tests.

## 9. Export and validate

Export renders from source/full profile, not the last viewport preview. Preserve or
strip color/metadata/audio according to policy. Reopen the output and validate its
declared invariants before publish.

## 10. Ship behind a gate

Update the traceability status only after the
[definition of done](definition-of-done.md). Attach:

- tests and golden comparisons;
- measured RAM/VRAM/time;
- supported hardware/codec matrix;
- project migration and recovery evidence;
- model/license/privacy review;
- known limitations and rollback flag.

## Suggested first code changes

Keep initial PRs narrow:

1. `backend/editor/buffers.py` and tests for color/alpha/coordinate descriptors.
2. `backend/editor/graph.py` and tests for a linear graph plus unknown-node round trip.
3. `backend/capabilities/contracts.py` plus a fake segmentation provider.
4. adapt current background removal as `segment.background`.
5. adapt protect masks as `mask.protect_union`.
6. adapt current RGB cleanup as `rgb.decontaminate`.
7. add revision-tagged comparison/alpha inspection UI.
8. add version-1 project snapshot and recovery journal.

Each step should leave existing direct pages operational until parity is proven.

## Review anti-patterns

Reject changes that:

- modify pixels in UI event handlers;
- silently rescale a mask with no stored transform;
- call CUDA directly outside hardware/provider policy;
- use one cache for proxy and final output;
- swallow cancellation or worker errors;
- write final output before validation;
- load untrusted pickle/project content;
- promise a codec/model capability without probing;
- copy a whole 20k mask for every brush event;
- poll an idle worker or model directory every second;
- describe a planned feature as already implemented.
