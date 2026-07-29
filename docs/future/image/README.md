# Image editor implementation

## Editor surface

The image workspace is a document view, not a tool-specific page:

```text
┌ tools ─┬──────── canvas / comparison ────────┬ properties ┐
│select  │ viewport, guides, checkerboard      │ operation  │
│mask    │ original/result/split/alpha/edge    │ layer/mask │
│retouch │ proxy badge + render status         │ parameters │
├────────┴──────────────────────────────────────┴────────────┤
│ layers / operation graph      history / versions / jobs   │
└────────────────────────────────────────────────────────────┘
```

Comparison modes use the same viewport transform and synchronized mip level:
draggable wipe, vertical/horizontal split, original/result toggle, side-by-side,
alpha-only, checkerboard, black/white, red overlay, difference, and 100% pixels.
At 100%, one source pixel maps to one device-independent image pixel before display
scaling; interpolation is disabled for edge inspection.

## Command path

1. Pointer/control input updates transient overlay.
2. Accepted interaction emits a typed editor command.
3. The document creates a revision and dirty region.
4. The render planner cancels a superseded interactive job.
5. The viewport receives proxy/ROI tiles tagged with revision and render profile.
6. Stale revision results are discarded.
7. Idle/high-quality preview and explicit export render from persisted state.

## Feature areas

- [Alpha matting and edge refinement](alpha-matting.md)
- [Masking and selection](masking-selection.md)
- [Professional retouching](retouching.md)
- [Compositing and relighting](compositing-relighting.md)
- [Color, restoration, computational photography](color-restoration-computational.md)
- [Generative, product, portrait, and geometry](advanced-domains.md)

## Shared image operation contract

Every operation specifies:

- input/output buffer and color descriptors;
- parameter schema, defaults, bounds, and units;
- mask interpretation and empty-mask behavior;
- ROI padding, tile overlap, and locality;
- proxy quality behavior;
- deterministic seed or candidate semantics;
- identity output and strength blending;
- CPU reference implementation or declared provider requirement;
- quality metrics and golden fixtures.

## First vertical slice

Implement source → background removal → protect-mask union → alpha refinement →
comparison/edge inspection → PNG export as the reference slice. It exercises
document state, mask roles, proxies, ROI, model adapters, alpha/color contracts,
history, cache, project persistence, and export without requiring the entire editor.
