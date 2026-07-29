# Model governance, security, privacy, and licensing

## Model admission

Before a model provider is enabled outside development, record:

- upstream source/model card and exact revision;
- artifact filename, byte size, SHA-256, and signature if available;
- code and weight licenses separately;
- redistribution and commercial-use interpretation approved by the project owner;
- training/data restrictions and required attribution;
- supported hardware/dtype and measured memory;
- quality/safety corpus results;
- network behavior and whether user media leaves the machine.

“See upstream” is a tracking state, not release approval.

## Artifact handling

- Download only through explicit model management.
- Use HTTPS plus pinned hash; write temporary, verify, then atomically install.
- Never execute code from a weight package or trust remote custom code by default.
- Load safer tensor formats when supported; isolate legacy loaders.
- Bound decompression and parsing; keep weights outside project packages unless an
  explicit portable-project policy permits redistribution.
- Do not scan all optional model paths every second.

## Provider isolation

Untrusted or crash-prone native/model providers run in a worker with:

- narrow IPC messages and validated paths;
- private temporary workspace;
- resource/time limits where the platform supports them;
- no implicit network;
- bounded output size and descriptor validation;
- restart limit and structured crash report.

## Privacy

Local processing is the default. Any cloud capability requires a separate provider
with an explicit preflight showing what media, masks, prompts, metadata, and account
identifiers are sent, retention terms, and estimated cost. Consent is per provider
and can be revoked.

Strip or preserve metadata only according to the export policy. Faces, identity
embeddings, and biometric landmarks remain project-local assets unless the user
explicitly invokes a disclosed remote provider.

## Generative/identity safeguards

- Label generated/invented regions in project history.
- Keep source and accepted candidate provenance.
- Require explicit user action for identity-consistent or expression/gaze changes.
- Do not infer sensitive traits.
- Provide candidate deletion and project consolidation controls.
- Research features remain off by default until misuse/privacy review passes.

## Project/input security

Apply the package constraints in
[Project format](../architecture/project-format.md). Media decoders and FFmpeg are
external attack surfaces: use supported builds, safe argument arrays without shell
interpolation, bounded probes, private workspaces, and regression fixtures for
malformed files.

## Release gate

A capability may be compiled but unavailable when model provenance, license,
privacy, hash, or quality evidence is incomplete. UI reports the exact gate without
encouraging users to bypass it.
