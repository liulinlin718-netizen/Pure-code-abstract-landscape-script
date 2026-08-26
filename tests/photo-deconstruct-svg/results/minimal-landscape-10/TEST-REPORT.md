# Minimal landscape regression test report

Date: 2026-08-24; updated 2026-08-25

This report begins from a blind baseline run of the offline Python/SVG program and records generalized revisions made after image 10 exposed a missing focal subject, image 08 exposed a fragmented horizontal reflection, and image 05 exposed a false enclosed background label inside the dune. No image-generation model, style transfer, manual tracing, semantic prompt, or per-image parameter tuning was used.

## Fixed parameters

```text
--detail 0.35
--paper 0.50
--paper-style rough
--paper-density 1.00
--grain-overlay 0.34
--gradient-strength 0.30
--color-mode source
--curve-smoothing 0.82
--min-negative-gap 0.018
--palette-size 6
--max-shapes 10
--seed 17
```

## Summary

- File/SVG validator: 10/10 pass.
- Exact repeat-run comparison: 10/10 deterministic SVG and JSON pairs.
- Visual composition pass without reservations: 8/10.
- Final flat-composite micro-hole audit: 10/10 pass.
- Compact-island detector activations: 1/10; only image 10 activates the rare-chromatic focal rule.
- Row-relative luminous support activations: 1/10; only image 10 activates it beneath that focal role.
- Perspective-accent-line detector activations: 0/10.
- Reflective-horizontal detector activations: 1/10; only image 08 passes the opposed lightness, chroma, and edge gates.
- Chromatic false-background cleanup activations: 1/10; only image 05 contains a compact enclosed background label whose source hue agrees with the enclosing field and opposes the background.

The structural validator proves that the files are native SVGs with the required metadata and texture order; a separate repeat run verifies determinism. Neither check proves that a composition-defining tiny subject survived, so visual and raster-coverage audits are reported separately.

## Per-image findings

Image | Shapes | Micro holes | Visual result | Finding
--- | ---: | ---: | --- | ---
01 lone tree haze | 10 | 0 | Pass | Tree location and mass survive, but the internal tonal rings are busier than ideal.
02 snow mountain | 7 | 0 | Pass | Main dark snow ridge remains legible; broad atmosphere is preserved.
03 dune sea | 6 | 0 | Pass | Horizon, dune, and shrub hierarchy survive with good reduction.
04 person dune | 5 | 0 | Fail | Dune and sky survive, but the tiny person—the only focal subject—is omitted.
05 Sahara dune | 5 | 0 | Pass after generalized revision | The isolated deep-brown source patch is now merged into the orange dune instead of becoming a cyan/background-labelled hole; the broad contour and palette remain unchanged.
06 snow cabin | 8 | 0 | Pass | Cabin remains as a recognizable compact dark mass.
07 layered mountains | 5 | 0 | Strong pass | Best result: clean five-band hierarchy, good source color, no clutter.
08 mountain lake | 9 | 0 | Pass after generalized revision | One regularized mountain envelope now organizes the upper terrain and its vertically paired reflection; independently sampled blue-gray, olive, and dark reflected roles replace the former cyan fragments and points.
09 lone sailboat | 9 | 0 | Fail | Sea and horizon survive, but the tiny sailboat is omitted.
10 lighthouse island | 8 | 0 | Pass after generalized revision | One coherent snow-island support mass now carries a compact warm building/lighthouse silhouette; final structural coverage has no enclosed background component.

## Generalized failure classes exposed

1. **Tiny focal subject omission** — a person or sailboat can still be compositionally essential even when it is too small or too narrow for the current compact-island rule. Image 10's rare-chromatic focal role is now recovered without activating on the other nine images.
2. **Enclosed background pockets after curve fitting or palette assignment** — the SVG metadata validator can pass while the final rendered structural composite still contains a small invented hole. Images 05 and 08 are now clear, and the complete suite has zero audited micro holes.
3. **Busy high-frequency scenes** — separately quantized reflections can spend the entire shape budget and still read as fragments; image 08 now uses one measured paired envelope instead.
4. **Over-segmentation inside a large subject** — the lone tree remains recognizable, but internal rings weaken the intended minimalism.

## Image 10 generalized revision

- A hue-restrained source may retain one rare-chromatic focal island only when its color evidence is coherent and no existing retained field already represents at least 80% of it.
- One immediately adjacent, hue-aligned cap or spire may join that same role; the rule does not inspect object names or fixed colors.
- A broad support field is retained only when it is consistently lighter than both side bands on the same rows, frame-connected, coherent, and adjacent to the focal role.
- The protected compact contour uses two restrained low-pass passes; general fields retain their four-pass smoothing.
- Regression result: images 01–09 do not activate the new exception; the old cloud, road-leading-line, and forced night branches also validate unchanged.

The revised image 10 output is shown separately in `comparisons/10-lighthouse-baseline.jpg`, and the complete updated suite remains in `comparisons/baseline-all.jpg`.

## Image 08 generalized revision

- A wide central reflective relationship activates only when vertically opposed lightness, chroma, and edge fields all correlate around the same measured axis; flat horizons, portrait compositions, and smooth symmetric gradients are rejected.
- One source-derived upper outer contour is regularized against compact internal texture valleys, then vertically paired into the lower field. Continuous sky and lower-field underlays eliminate the former detached fragments and enclosed background pockets.
- Upper terrain, vegetation, and rock colors are sampled separately from their reflected counterparts, preserving the source's blue-gray mountain, olive upper growth, and darker lower reflection without a named-object or fixed-color rule.
- Regression result: only image 08 activates this branch. Images 01–07 and 09–10 retain byte-identical SVG and JSON output, and the cloud, road-leading-line, and forced night branches continue to validate unchanged.

The revised image 08 output is shown separately in `comparisons/08-mountain-lake-baseline.jpg`.

## Image 05 generalized revision

- The source patch inside the dune is deep brown (`#6E3418` median at analysis scale), but the limited palette assigned it to the dark teal background because of lightness. The SVG therefore emitted it as an enclosed hole in the orange field.
- An enclosed background-labelled component is now merged only when it is compact, has meaningful source chroma, strongly agrees with the enclosing role's Oklab hue direction, and strongly opposes the background hue direction. Neutral openings, long passages, large openings, and hue-aligned background components remain protected.
- The rule merges one 306-pixel analysis component in image 05. Its final flat-composite audit changes from one 263-pixel background pocket to zero enclosed components.
- Regression result: images 01–04 and 06–10 retain byte-identical SVG and JSON output; only image 05 activates the new rule. The cloud, road-leading-line, and forced night branches also remain byte-identical and validate successfully.

The revised image 05 output is shown separately in `comparisons/05-sahara-dune-baseline.jpg`.
