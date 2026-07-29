# Charter and engineering principles

## Product goal

Midgard Studio should become a local-first, professional image and video editor
whose AI features accelerate precise work without making edits opaque or
irreversible. The core is an editor engine, not a collection of buttons that
destructively rewrite files.

## Non-negotiable invariants

1. **Immutable source:** decoding normalizes orientation but never modifies the
   source asset.
2. **Non-destructive edits:** tools append or update operation nodes; users can
   reorder, disable, mask, change strength, and undo them.
3. **One coordinate system:** project coordinates use source pixels. Proxies,
   viewport transforms, tiles, and video frames map explicitly to that space.
4. **Alpha is data:** alpha stays straight or premultiplied only at declared
   boundaries. RGB decontamination must not silently destroy alpha.
5. **Color is declared:** buffers carry color space, transfer function, bit depth,
   alpha mode, and ICC provenance.
6. **Deterministic persistence:** project JSON and masks are versioned, bounded,
   validated, and saved atomically.
7. **Jobs are cancellable:** long loops check cancellation at bounded intervals.
   Pause and resume use checkpoints, not process suspension.
8. **Hardware is policy:** capability selection comes from the hardware profile;
   feature code does not assume CUDA.
9. **Models are adapters:** UI and graph nodes depend on capability contracts, not
   a specific checkpoint or framework.
10. **Truthful UI:** previews, approximate results, missing models, fallbacks, and
    destructive metadata choices are visible to the user.

## UX principles

- Manual tools always remain available when AI selection or generation is absent.
- The user can inspect original, result, alpha, masks, and edge errors at 100%.
- AI produces candidates; applying one is a distinct, undoable action.
- Protect masks are an explicit semantic role. Background removal runs normally
  with no protect mask. When a protect mask exists, its effective alpha is
  `max(model_alpha, protect_alpha)` after coordinate validation.
- Fill/retouch masks and protect/keep masks are never inferred from the same
  ambiguous boolean.
- Video corrections are authored on keyframes and propagated as editable data.

## Performance principles

- Interactive tools target a 16 ms paint feedback budget and a 100 ms control
  response budget; inference is asynchronous.
- Preview and final rendering have different profiles and cache namespaces.
- Masked operations render an expanded region of interest (ROI), then blend through
  a seam-safe overlap. Global operations declare that ROI is unsupported.
- Large images use overlap-aware tiles. Temporal video models use chunks with
  context frames and resumable manifests.
- Memory estimation happens before model load and before allocation.

## Reliability principles

- Project and queue state use write-temp, fsync, atomic-replace semantics.
- An append-only recovery journal records accepted edits between snapshots.
- A job result is published only after validation and atomic output commit.
- A process crash may lose in-flight compute, never the last committed project.
- Diagnostics are triggered on startup, device change, worker failure, or user
  request—not by an unconditional idle polling loop.

## Scope control

The inventory contains ambitious research features. Architecture support does not
mean all models should ship together. Every roadmap increment must leave the app
usable, testable, and releasable.
