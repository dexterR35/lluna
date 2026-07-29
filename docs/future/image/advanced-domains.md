# Generative, product, portrait, and geometry domains

## Generative editing

Supported operation families:

- fill and outpaint in any direction with multiple candidates;
- object replacement preserving position and lighting;
- clothing, material, color, and texture changes;
- controlled background generation;
- reconstruction of cropped subject portions;
- structure-preserving variation and reference style transfer with strength;
- sketch-, depth-, edge-, and pose-guided edits;
- identity-consistent editing across images;
- alternate facial expressions;
- text removal/replacement with surface reconstruction;
- seamless textures/patterns and seam-free tiled generation.

Each request stores source hash, mask/control inputs, prompt/negative prompt, model
fingerprint, seed, safety settings, and candidates. Invented pixels are inspectable
through a generated-region mask. Identity and expression features remain research
until consent, privacy, and fidelity requirements pass.

Outpaint extends the document canvas through a separate canvas-size operation.
High-resolution generation uses overlapping latent/image tiles with deterministic
noise fields and seam tests.

## Product photography

Build a product workflow from normal editor nodes:

- translucent-edge cutout;
- studio background presets;
- ground plane, contact/cast shadow, reflection;
- fingerprint, dust, scratch, label-imperfection cleanup;
- material-preserving recolor;
- perspective-warped packaging label replacement;
- marketplace aspect-ratio variants;
- consistent batch framing;
- background compliance, empty margin, and subject-coverage checks;
- possible 360° presentation frames from supplied views;
- logo and printed-text detection/protection.

Compliance profiles are versioned data with jurisdiction/marketplace/source dates;
they are not hard-coded forever. Product recolor separates reflectance from
illumination as confidence allows.

## Portrait photography

Face-instance masks cover skin, lips, teeth, eyes, brows, hair, and facial hair.
Features include pore-preserving retouch, makeup add/remove, strand-preserving hair
recolor, portrait/background lighting, catchlights, glasses-glare reduction,
red-eye correction, expression/gaze adjustment, portrait relight, depth-aware
background replacement, clothing cleanup, and wrinkle reduction.

Group photos assign stable face IDs within the document and independent settings.
ID/passport preparation uses versioned size, crop, pose, expression, and background
guides; it warns rather than claiming official acceptance.

## Geometry and transformations

Native operation nodes:

- perspective and mesh warp;
- puppet pins;
- content-aware scaling and seam carving;
- curved-document straightening;
- cylindrical and spherical warp;
- automatic object alignment;
- cross-image size/position matching;
- symmetry and kaleidoscope;
- repeat-pattern construction and seamless texture generation;
- intelligent crop based on faces, subjects, text, and composition.

Transforms expose forward/inverse coordinate mapping so masks, clone anchors,
guides, depth, and downstream operations remain aligned. Content-aware scale stores
its energy/protect/remove masks and seam decisions for reproducibility.

## Acceptance

- Candidate operations remain reproducible or pin accepted assets when providers
  are non-deterministic.
- Generated-region and confidence masks reopen correctly.
- Logo/text protection is opt-in visible state and is tested against small print.
- Marketplace variants share edits without cumulative resampling.
- Face IDs survive reopen and report ambiguity after major geometry changes.
- Warp inverse mapping meets control-point error tolerance.
- Intelligent crop never silently cuts protected subjects/text.
