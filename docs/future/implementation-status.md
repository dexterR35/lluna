# Implementation status and evidence

Last updated: 2026-07-28

This file records code that exists now. The feature inventory remains the complete
roadmap; undocumented plans are not treated as shipped.

## Implemented in the first future vertical slice

| Area | Evidence | Status boundary |
|---|---|---|
| Typed media buffers | `backend/editor/buffers.py` declares kind, dimensions, dtype, color, transfer, alpha mode, and source transform with validation. | Foundation for image/video operations; it does not yet replace every legacy buffer. |
| Operation contracts | `backend/editor/operations.py` declares locality, ROI padding, tile overlap, render profile, CPU/proxy support, and determinism. | Foundation; render planner is still planned. |
| Alpha refinement | `backend/editor/alpha_refinement.py` implements CPU expand/contract, feather, guided edge smoothing, island/hole cleanup, RGB decontamination, ROI reporting, and protect union. | Current in Remove Background for the exposed controls; trimap/hair/glass model matting remains planned/research. |
| Protect semantics | Binary keep mode guarantees any painted pixel remains opaque; soft max mode exists in the engine. Empty/absent masks are exact no-ops. | Current and regression-tested. |
| Remove Background UI | Professional refinement toggle, contract/expand, feather, edge smoothing, and spill cleanup are passed through worker IPC. | Current basic control set. |
| Comparison and alpha inspection | `backend/editor/inspection.py` and `ui/component/preview/before_after_preview.py` provide synchronized side-by-side zoom/pan, draggable wipe, original/result, alpha, checkerboard, black, white, red-overlay, difference, and existing 100% views. | Current for reusable image previews. Different-sized inputs align to result pixels for combined views while native side-by-side retains their own resolution. |
| Worker lifecycle | Periodic watchdog thread and keepalive loop were removed. Process exit/IPC failure and explicit cancellation remain. | Current; there is no idle/job watchdog polling thread. |
| Operation graph | `backend/editor/graph.py` provides immutable nodes, JSON-safe parameters, dependency/cycle validation, editing methods, deterministic fingerprints, and unknown-field preservation. | Foundation; document revisions/history and render planning remain planned. |
| Project package | `backend/projects/package.py` provides version-1 atomic `.midgard` snapshots, graph persistence, linked/embedded asset records, content verification, bounded safe ZIP reads, and unknown-field preservation. | Foundation; mask tiles, journal/autosave, candidates, previews, and UI integration remain planned. |

## Tests

The standard local suite passes:

```text
153 passed, 1 skipped
```

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
