# Compositing and relighting

## Layer compositor

Implement image layers, groups, clipping masks, adjustment layers, opacity, and a
documented blend-mode set. Compositing occurs in premultiplied linear light. Modes
whose common creative definition is display-referred declare the conversion.

Smart objects retain original resolution and nested operations. Placement is a
transform node with scale, rotation, perspective, warp, crop, and resampling policy.

## Subject/background integration

An assisted composite produces suggestions, each as editable nodes:

1. estimate subject/background horizon, depth, and camera cues;
2. suggest scale and perspective placement;
3. harmonize exposure, white balance, and grade through adjustment layers;
4. match depth-of-field and bokeh;
5. generate contact/cast shadow and optional reflection;
6. add edge light-wrap and atmospheric depth;
7. match grain/noise.

No step is baked into the pasted subject. The user can disable or mask each result.

## Blending

- Poisson blending handles smooth illumination transitions but must protect text,
  logos, and high-frequency product details.
- Multiband blending exposes band count and seam width.
- Edge light-wrap samples the new background in a bounded outside edge band.
- Atmospheric perspective uses depth and environment color with an editable falloff.
- Grain matching estimates spectrum/strength and adds seeded synthetic grain.

## Shadows and reflections

Contact shadow inputs: subject alpha, estimated contact plane/points, light
direction, source depth, softness, density, color, and spread. Directional cast
shadow projects a deformable silhouette onto a ground plane. Reflection transforms
the subject relative to a plane, applies roughness/blur/falloff, and clips by depth.

Generated outputs are layers, not pixels inserted into the background.

## Relighting architecture

Relighting is gated behind research benchmarks. A provider may estimate depth,
surface normals, albedo, illumination, and material confidence. The UI exposes
virtual key, fill, rim, and background lights with position/direction, size,
temperature, color, and intensity. Presets include softbox, ring, and window light.

Operations include:

- harsh facial-shadow recovery;
- mixed-lighting correction;
- selected-object relighting;
- subject-to-background light matching;
- albedo/illumination separation;
- depth-derived shadow map generation.

Low-confidence geometry/material regions retain more original illumination. Show a
relight confidence overlay and allow mask correction.

## Background blur

Use an editable depth map, lens model, focus distance, aperture strength, bokeh
shape, highlight response, and edge-aware foreground handling. Prevent foreground
color bleeding by dilating foreground color before background convolution and
compositing with a refined alpha.

## Acceptance

- Blend-mode CPU reference fixtures pass in linear light.
- Smart-object scaling back up renders from its source, not a downscaled preview.
- Composite helpers create independent editable nodes.
- Shadow remains attached under subject transform or clearly reports unlinking.
- Text/logo protection prevents unacceptable Poisson smearing.
- Relighting preserves identity and material cues on the benchmark corpus and is
  labeled experimental until thresholds are met.
