# Color, metadata, alpha, and precision

## Internal representation

- Decode to a declared scene/display-referred working space.
- Use float16/float32 linear-light buffers for composites, relighting, blur, blend
  modes, and HDR; allow uint16 for lossless integer operations.
- Avoid repeated 8-bit encode/decode between nodes.
- Keep RGB channel order explicit at OpenCV/Pillow/Qt/model boundaries.
- Perform geometric resampling on straight color with correct alpha handling;
  composite in premultiplied linear light, then unpremultiply safely when needed.

Default SDR working space may be linear sRGB, but the project records the choice.
HDR requires explicit Rec.2020/PQ or HLG handling and a calibrated preview path.

## Alpha contract

Every RGBA buffer declares `straight` or `premultiplied`. Alpha refinement operations
may change alpha only when their contract says so. RGB spill removal reads alpha
but does not modify it.

For background removal:

```text
model_alpha = segment(source)
effective_alpha =
    model_alpha                             if no protect mask exists
    max(model_alpha, aligned_protect_mask)  otherwise
result = source RGB + effective_alpha
```

An empty mask behaves exactly like no mask. Fill/retouch masks never implicitly
become protect masks.

## ICC and metadata

On import retain:

- embedded ICC bytes and parsed profile identity;
- EXIF orientation and whether it was normalized;
- DPI/resolution units;
- timestamps, camera/lens fields, and user metadata policy;
- video color primaries, transfer, matrix, range, rotation, SAR/DAR, and HDR data.

Export offers `preserve safe`, `strip privacy-sensitive`, and `custom`. GPS,
serial numbers, thumbnails, and maker notes are called out explicitly. Orientation
is normally baked into pixels and exported as orientation 1.

ICC conversion uses a color-management library, never a profile-name guess. Warn
for out-of-gamut colors and provide soft proofing for printer profiles.

## Color operations

Curves, levels, wheels, HSL/HSV/LAB, selective color, gradient maps, white balance,
LUTs, and tone mapping are parameterized graph nodes. Define:

- domain/range and interpolation;
- channel/color-space semantics;
- mask and blend behavior;
- clipping policy;
- GPU/CPU numeric tolerance;
- identity behavior for zero strength.

`.cube` LUT import validates dimensions, domain, finite values, and bounded size.
Export includes the working-space assumption.

## HDR and tone mapping

HDR merge aligns inputs, rejects severe motion or exposes deghost masks, estimates
camera response when required, and produces a float scene-referred result. Tone
mapping is a separate editable node. SDR export never silently clips HDR.

## Verification

- round-trip ICC fixtures and known color patches;
- Delta E thresholds for identity/preserve operations;
- straight/premultiplied alpha edge fixtures;
- 8/16-bit and float gradient banding tests;
- CPU/GPU tolerance tests;
- metadata preservation/stripping matrices;
- video range/transfer round trips through supported codecs.
