# Professional retouching

## Native retouch tools

### Healing brush

Store destination stroke, optional source anchor, sampling policy, radius, hardness,
texture scale, and blend strength. Automatic sampling searches nearby patches while
avoiding protected/face-feature regions. Final render uses gradient-domain or
frequency-aware blending; preview may use a faster patch blend.

### Clone stamp

Support aligned, fixed, mirrored, and rotating source modes. Store the source anchor
and transform in source coordinates. Clone is deterministic and works across smart
objects only through an explicit source reference.

### Patch tool

Store source/destination vector regions and transform. The user can move/scale the
source before commit. Blend choices include seamless, texture-only, and direct copy.

### Frequency separation

Create non-destructive low-frequency color/tone and high-frequency texture outputs
from one operation group. Radius is source-pixel based. Painting color or texture
creates child retouch nodes; recombining in linear light must reconstruct the
identity image within numeric tolerance.

### Dodge and burn

Adjustment nodes target shadows, midtones, or highlights through a luma range mask.
Brush flow accumulates in a bounded float mask. Strength is editable and never
baked into source pixels.

### Liquify

Store a resolution-independent displacement mesh for push, pull, pinch, expand, and
reconstruct. Face-aware controls generate constrained mesh edits but expose guides
and preserve manual reconstruction. Render tiles include displacement bounds.

## Model-backed retouch

Providers may produce:

- content-aware removal candidates;
- face restoration with identity strength and skin-detail preservation;
- texture-preserving skin smoothing;
- blemish, acne, wrinkle, and under-eye regions;
- stray-hair/flyaway candidates;
- teeth, eyes, catchlights, and natural-strength enhancements;
- pore-preserving skin-tone unification;
- clothing wrinkle cleanup.

Detection masks are shown before application. “Enhance” never silently changes all
faces: group photos expose per-face IDs and settings. Identity-sensitive outputs
use a blend/identity slider and difference preview.

## Selective sharpening

Separate capture sharpening, creative masked sharpening, and output sharpening.
Eyes, hair, fabric, and product detail presets are parameter starting points, not
semantic claims. Detect and warn about halos/ringing.

## Object removal alternatives

One operation owns the mask, context crop, prompt/options, seed set, and candidates.
Candidate generation is asynchronous and cancellable. The chosen asset is pinned;
unselected candidates follow a configurable cache/retention policy. Seams are
validated at full resolution.

## Face guides

Symmetry and facial-proportion guides are non-exporting overlays derived from face
landmarks. They are versioned with the detector fingerprint and can be adjusted
manually. Guides inform edits but do not assert aesthetic correctness.

## Acceptance

- Clone/heal anchors survive zoom, crop, and operation reorder.
- Frequency separation identity round-trip stays within the color tolerance.
- Liquify inverse/reconstruct returns the undeformed mesh.
- Face restoration does not alter unselected faces.
- Retouch nodes have adjustable strength and independent masks.
- Candidate choice, undo, reopen, and offline rerender preserve the accepted asset.
- Skin fixtures detect pore loss and excessive smoothing.
