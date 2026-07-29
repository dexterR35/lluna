# Non-destructive operation graph

## Model

The document contains an ordered DAG. The common path is linear, while groups,
shared masks, smart objects, candidates, and branches introduce explicit edges.

```text
Source → Lens correction → Background removal → Alpha refinement
       → Skin retouch → Color grade → Relight → Upscale → Export view
```

Export is a render target, not a destructive document mutation.

## Operation node schema

```json
{
  "id": "op_01J...",
  "type": "alpha.refine",
  "schema_version": 1,
  "enabled": true,
  "strength": 1.0,
  "inputs": {"image": "op_previous:image", "mask": "mask_subject"},
  "parameters": {"contract_px": 0.0, "feather_px": 1.5},
  "execution": {"roi": "mask_bounds", "quality": "final"},
  "provider": {"capability": "alpha_refine", "preferred_id": null},
  "created_at": "RFC3339 timestamp"
}
```

IDs are stable UUIDv7/ULID-style identifiers, never array indices. Parameters are
JSON-compatible and versioned by operation type. Unknown nodes remain preserved
and disabled rather than being discarded by an older app.

## Commands and undo/redo

Commands are semantic:

- add/remove/move/toggle operation;
- set one or several parameters;
- add/remove/reorder mask layer;
- commit mask tile diff;
- attach/detach mask;
- choose candidate;
- create/switch/merge version branch.

Undo stores inverse commands plus content-addressed tile deltas. Mask strokes do
not copy an entire full-resolution mask. A stroke transaction captures changed
tiles before/after, coalesces pointer movement, and commits once on pointer-up.
Memory history is bounded; older commands spill to the project journal.

## Masks

A node may consume zero or more named mask outputs. Mask algebra is graph data:
union, intersection, difference, XOR, invert, density, feather, grow/shrink, and
edge contrast are nodes, not permanently baked pixels. Raster paint is a mask
source with tile history. Semantic selections keep prompts and the accepted raster
snapshot so old results remain reproducible if a model changes.

Roles are explicit: `effect`, `protect`, `foreground`, `background`, `unknown`,
`clip`, `depth_range`, and `luminosity_range`.

## Render planning

For each target the planner:

1. validates graph and capabilities;
2. walks dependencies and computes cache keys;
3. propagates dirty rectangles downstream;
4. chooses proxy, ROI, tile, full-frame, or temporal execution;
5. estimates memory/time and selects provider/device;
6. schedules units with cancellation checkpoints;
7. validates and commits artifacts.

Operations declare:

- padding needed outside an ROI;
- tile overlap and safe crop;
- whether they are local, global, or temporal;
- deterministic/non-deterministic behavior and seed;
- supported proxy scales, dtypes, color spaces, and devices;
- whether masks affect computation or only final blending.

## Presets and batch pipelines

A preset is a graph fragment with typed input/output ports and exposed parameters.
Per-file overrides patch exposed parameters only. A batch instantiates the fragment
for each asset, records the resolved preset version, and resumes per operation.

The first reference preset is:

```text
Remove background
  → Refine edges
  → Upscale 2×
  → Enhance face
  → Export PNG
```

Preset validation catches missing models, unsupported alpha exports, memory limits,
and incompatible color profiles before the queue begins.

## Branches and smart objects

- A branch points to a document revision and shares immutable assets.
- A smart object is a nested document with its own source resolution and graph.
- Transforming a smart object changes its placement node, not source pixels.
- Merging branches is operation-aware; concurrent mask tile edits conflict only
  when they touch the same tile and base revision.

## Cache key

```text
SHA-256(
  operation type + schema version + canonical parameters +
  ordered input artifact hashes + mask hashes +
  provider/model fingerprint + engine version +
  render profile + buffer descriptor + deterministic seed
)
```

UI labels, timestamps, file paths, and disabled sibling nodes are excluded.
