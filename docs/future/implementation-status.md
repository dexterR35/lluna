# Implementation status and evidence

Last updated: 2026-08-04

This file records code that exists now. The feature inventory remains the complete
roadmap; undocumented plans are not treated as shipped.

## Implemented in the first future vertical slice

| Area | Evidence | Status boundary |
|---|---|---|
| Protect semantics | Binary keep mode guarantees any painted pixel remains opaque; soft max mode exists in the engine. Empty/absent masks are exact no-ops. | Current and regression-tested. |
| Remove Background UI | Professional refinement toggle, contract/expand, feather, edge smoothing, and spill cleanup are passed through worker IPC. | Current basic control set. |
| Worker lifecycle | Periodic watchdog thread and keepalive loop were removed. Process exit/IPC failure and explicit cancellation remain. | Current; there is no idle/job watchdog polling thread. |

## Tests

Run the current verification commands documented in `docs/IMPLEMENTATION_STATUS.md`.

The skipped test is the GUI smoke test because PySide6 is not installed in the
current test interpreter. New deterministic tests cover:

- buffer and operation contract validation;
- alpha identity, protect modes, morphology, cleanup, feather/smoothing, and RGB
  decontamination;
- BackgroundRemover integration;
- graph round-trip, fingerprint, unknown fields, dependencies, and cycles;
- project round-trip, embedded hash verification, atomic-failure preservation,
  path traversal rejection, graph tamper detection, and future-field preservation;
- absence of the periodic watchdog;
- checkerboard/compositing math, alpha view, black/white backgrounds, red overlay,
  difference heatmap, wipe position, and mismatched-size alignment.

## Next implementation slice

1. Document revisions plus tile-diff mask history.
2. Project mask tiles, autosave journal, recovery, and UI open/save.
3. Render planner with proxy/final cache separation and cancellable ROI jobs.
4. Batch preset graph execution and durable queue checkpoints.
