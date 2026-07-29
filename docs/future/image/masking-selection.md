# Advanced masking and selection

## Mask document model

A mask stack contains stable layer IDs, name, role, visibility, opacity/density,
blend algebra, parent group, coordinate transform, and one or more sources:
raster tiles, vector paths, semantic prompts, range parameters, or derived nodes.
Multiple disconnected regions naturally coexist in one layer; users may split them.

## Paint and shape tools

- Brush: add, subtract/erase, protect, configurable size, hardness, opacity,
  spacing, pressure mapping, stabilizer, and optional edge-aware snapping.
- Rectangle/ellipse: live vector until committed; feather and corner controls.
- Lasso/polygon: add/subtract/protect modifier, close/cancel behavior, edge snapping.
- Magnetic lasso: cost combines gradient magnitude/direction and pointer distance;
  anchors are editable.
- Clear/invert operate on active layer or explicit selection, never all layers by
  ambiguous default.

Stroke samples are resampled by source-space spacing, not event frequency. Painting
remains responsive through an overlay texture; tile updates commit asynchronously.

## AI selection

Capability inputs may include:

- positive and negative points;
- boxes, rough masks, text/semantic prompt;
- prior mask and refinement iteration;
- target concepts such as sky, skin, hair, face, clothes, foreground, background,
  and individual objects.

Return candidates with confidence and object identity. Accepting a candidate stores
the raster mask, prompts, model fingerprint, and transform. Selecting nothing
leaves manual tools fully operational.

## Select similar and range masks

- Color range works in a declared perceptual color space with sampled colors,
  tolerance, locality, and skin protection.
- Luminosity range uses editable lower/upper rolloffs in scene/display luma.
- Texture similarity uses bounded feature resolution and returns an editable mask.
- Semantic similarity is model-backed and candidate-based.
- Depth range references a depth operation and has near/far feather controls.

## Algebra and groups

Derived masks support union, intersection, difference, XOR, and invert. Parent/child
groups apply transforms and density without rasterizing children. Adjustment layers
link by mask ID, so renaming or reordering cannot break the reference.

## Refinement

Feather, smooth, grow/shrink, edge-aware refine, density, edge contrast, hole fill,
and island cleanup remain parameter nodes where possible. A destructive “bake
mask” command creates a new raster source and keeps the previous derived version in
history.

## History and persistence

Each pointer gesture is one undo command composed of changed tile deltas. Vector
path edits store point-level commands. AI candidate acceptance is one command;
prompt changes do not discard the accepted candidate. Masks autosave through the
project journal and export to PNG plus optional sidecar metadata.

## Acceptance

- Brush output is invariant to pointer event frequency within sampling tolerance.
- Zoom/pan/rotation never change source-coordinate paint placement.
- Add/subtract/protect behavior is covered across overlapping layers.
- Undo/redo restores exact tile hashes and active-layer state.
- ROI bounds include hardness/feather/kernel padding.
- A 20k image can paint without allocating a full history copy per stroke.
- Disabled AI capability does not disable brush, lasso, polygon, or range selection.
