---
name: photo-deconstruct-svg
description: Convert a user-supplied photograph into a sparse, source-derived SVG abstraction using deterministic Python image analysis and vector paths. Use when asked for programmatic photo deconstruction, minimal approximate silhouettes, flat editorial color fields, paper grain, or reproducible abstract art without Canvas, image generation, style transfer, or manual tracing. Supports JPG, PNG, and WebP inputs and produces SVG plus a visual-plan JSON file.
---

# Photo Deconstruct SVG

Turn one photograph into one full-frame SVG abstraction. Preserve the source aspect ratio, dominant silhouette, spatial weight, broad light direction, and color family while removing photographic detail.

Use only `scripts/deconstruct_photo.py`. Do not call an image-generation tool, draw with HTML Canvas, embed the source photograph in the SVG, or manually invent paths for a particular image.

## Workflow

1. Lock the exact local path of the photograph supplied in the current request.
2. Inspect the photograph and note the dominant silhouette, largest atmospheric or background field, foreground/background order, and any structurally meaningful point highlights.
3. Read `references/visual-grammar.md` when choosing or adjusting reduction parameters. Read `references/color-research.md` before changing color behavior or selecting a fallback palette.
4. Run the script with the default settings first:

```bash
python3 scripts/deconstruct_photo.py INPUT OUTPUT.svg
```

5. Inspect the generated SVG and its adjacent JSON plan. Judge identity by silhouette and spatial weight before judging texture or polish.
6. Adjust only source-independent parameters when revision is needed:

```bash
python3 scripts/deconstruct_photo.py INPUT OUTPUT.svg \
  --detail 0.35 --paper 0.50 --paper-style rough \
  --paper-density 1.00 --grain-overlay 0.34 \
  --gradient-strength 0.30 --color-mode source \
  --curve-smoothing 0.82 --min-negative-gap 0.018 \
  --palette-size 6 --max-shapes 10 --seed 17
```

7. Run the validator before delivery:

```bash
python3 scripts/validate_svg.py OUTPUT.svg --analysis OUTPUT.json
```

8. Return the SVG as the primary artwork. Return the JSON only when the user asks for the extracted plan or reproducibility details.

## Revision rules

- Increase `--detail` when the primary silhouette loses identity; decrease it when the result becomes illustrative or busy.
- Keep `--color-mode source` as the default. Extract extra robust candidates first, retain the dominant color and the strongest meaningful chromatic role, then select the remaining roles by frequency-weighted Oklab diversity. This prevents a large smooth sky from consuming the palette and erasing a smaller warm or cool subject accent. Use `balanced` only for extreme source samples and `curated-night` only when a fixed fallback is explicitly wanted.
- Preserve at most one compact source-defining island when ordinary large-field quantization would erase it. First accept a detached, non-linear component that is locally contrasted and embedded in one stable surrounding field. Also measure a compact, globally rare interruption that straddles the junction of two or three stable surrounding roles when its pixels remain unlike every role; cap the candidate above the lower fifth of the frame so ordinary foreground texture cannot activate the exception. In a globally hue-restrained image, additionally allow one rare-chromatic focal component only when no existing color field already represents at least 80% of it coherently; one immediately adjacent, hue-aligned cap or spire may join the same role. Prefer that rare-chromatic role and its measured support field when it also qualifies, using the cross-field candidate only as a fallback. Reject ridgelines, texture fragments, narrow marks, diffuse color casts, and junction candidates without strong multi-role coverage. Sample a robust source color from the selected pixels, paint it after the broad fields, and fit its identity contour with two low-pass passes rather than the general four. This is a geometry-and-color-coherence rule, not an object-name rule.
- Beneath a retained rare-chromatic focal island, preserve at most one broad luminous support field when its row-relative lightness clearly exceeds both side bands, it is frame-connected, and it forms one coherent mass adjacent to the focal role. Close only narrow breaks, fill enclosed micro-holes, sample the support color from its own source pixels, and paint it before the focal island. Reject small highlights, disconnected snow or foam fragments, and ordinary bright sky. This is a relative-lightness relationship, not an island, snow, or building detector.
- Preserve at most one narrow perspective accent when ordinary area filtering would erase a composition-defining leading line. Require bottom-frame contact, substantial vertical reach through the lower center, clear local chromatic and lightness separation, a stable narrow centerline, and alignment toward central convergent evidence. Render it as one source-colored tapered path after the broad fields, with straight frame bleed at its contact so smoothing cannot widen the endpoint. Reject wires, stems, cracks, road-edge fragments, and any thin mark that lacks the complete geometry. This is a perspective-and-contrast rule, not a road or color name rule.
- When a wide image contains a strong central horizontal pairing, allow one reflective-horizontal reduction. Require opposed lightness, chroma, and edge fields to correlate around the same measured axis; reject portrait images, axes near the frame, flat horizons, and smooth symmetric gradients that lack paired edge evidence. Trace one regularized upper outer contour, derive the lower field by measured vertical pairing, and use continuous underlay fields so reflection texture cannot become detached islands or holes. Sample the upper and lower terrain, vegetation, and rock roles independently because a reflection may be darker or less saturated than its source. Keep this branch sparse and suppress point highlights. This is a relational image-structure rule, not a detector for mountains, lakes, or water.
- Keep `--gradient-strength 0.30` as the default for a visible but light three-stop gradient whose direction and relative stop colors are measured independently inside each source mask. Use `0` only when explicitly requesting flat color; keep ordinary subtle variations within `0.20–0.34`.
- Increase `--curve-smoothing` when contour steps are visible; night landscapes use periodic cubic B-spline-to-Bézier fitting so organic contours remain curvature-continuous while collinear runs remain straight. Do not lower analysis resolution to make the SVG smaller.
- For general color fields, keep four restrained closed-loop low-pass passes before cubic fitting. This removes pixel-scale edge chatter while preserving broad bends, source-given straight runs, and the existing region layout; do not blur or re-quantize the masks merely to hide contour noise.
- Keep `--min-negative-gap` near `0.018` to close needle-like sky bays and pinched crevices before fitting. Raise it slightly when thin negative-space slivers remain; lower it when a real narrow passage carries identity. The closure is additive and must not erode positive subject features.
- When independently fitted atmospheric and foreground paths nearly touch, extend only the atmospheric path's local contact band underneath the later-painted foreground. Use render-order overlap to prevent background-colored hairlines; do not add a seam-covering shape or alter the atmospheric field's free edge.
- Apply the same render-order underlap to retained general color fields. Treat the minimum-clearance value as a dilation radius, not a filter diameter, and add a curve-fitting margin one analysis pixel wider when four-pass contour smoothing is active. Extend each earlier field only inside the proximity band of later-painted retained fields so the overlap closes short gaps and triple-junction pockets while every true free edge remains unchanged. Never add a seam-colored patch or a stroke.
- Before fitting separate general fields, close negative-space channels narrower than `--min-negative-gap` on their combined union and fill only union-level background pockets below the matching clearance area. Assign every added component to the touching retained field with the strongest boundary contact, then apply paint-order underlap. This prevents a narrow background lobe from becoming a detached dot after curve fitting without inventing a new color or extra SVG shape.
- Before fitting any structural mask that touches the canvas boundary, extend only that contact segment several analysis pixels beyond the viewBox and clip overflow at the SVG root. This prevents Bézier smoothing from pulling a nominal x=0/y=0 edge inward while leaving all interior contours unchanged.
- After underlap, merge only enclosed micro-holes below the same minimum-clearance scale. Inspect the final flat structural composite as well as the raster masks: a tiny background-colored dash, wedge, or island created by curve fitting is still a failure. Preserve large intentional openings and every free outer contour.
- When a larger enclosed island belongs to a discarded non-background label and no retained path will cover it, merge it into the enclosing field. Preserve true background openings and holes occupied by another retained field; never let an omitted green or earth island reveal an unrelated sky-colored canvas.
- Do not protect every enclosed component merely because quantization assigned it the background label. Merge a compact background-labelled island into its enclosing field only when its measured source color has meaningful chroma, its hue strongly agrees with the enclosing role, and its hue strongly opposes the actual background role. Preserve neutral holes, hue-aligned background openings, long passages, large openings, and holes occupied by another retained field. This repairs dark same-material patches that were assigned by lightness without naming the material or object.
- Treat the foreground silhouette and internal value fields differently. Preserve source-given corners on the outer identity contour. On an internal field, remove narrow positive tips, use extra closed-loop low-pass passes, and enforce a minimum clearance from the outer contour: keep a clearly open interval or extend the internal field through the foreground clip boundary. Never leave a tapering base-color sliver between them.
- Reduce `--max-shapes` before reducing palette size when the composition feels fragmented.
- Treat omitted non-background regions as simplification material, not as transparent holes. Merge a discarded component into the touching retained field with the strongest boundary contact, using source-color distance to resolve ambiguous contacts; keep the full-frame background exclusive to pixels genuinely assigned to the background role.
- Keep `--paper` between `0.24` and `0.45` for the ordinary `grain` surface. Use `--paper-style rough` around `0.44–0.54` when the paper should be clearly tactile. Keep `--paper-density 1.0` unless the user explicitly asks for more vector pores or fibers. When the user asks to cover rough paper with the traditional fine noise, add `--grain-overlay 0.20–0.36`; do not substitute higher particle density. Rough mode uses one faint continuous undulation filter plus seeded vector fibers and pores, with the optional traditional noise painted last. Keep the complete surface group topmost and never displace structural paths.
- Use `--no-points` when point highlights do not carry structural information.
- Keep `--analysis-size` near `520`; raise it moderately for narrow architectural edges, but do not use it to recover photographic texture.
- Keep the four-quadrant confidence pass private. It combines palette-assignment margin, retained edge energy, connected-component coherence, and local gradient activity; never serialize quadrant names, scores, thresholds, or confidence flags into the SVG or JSON plan.
- When that private pass finds a weak quadrant, allow only measured, source-independent spatial roles: a dark field between paired converging boundaries, a compact silhouette that is darker than its horizontal context, or a cool horizontal shore field that reaches the frame and crosses deeply into a warm foreground. Sample any added role from its own source pixels. Protect it from absorbing unrelated discarded components, and add nothing when the strict geometry is absent.
- Preserve the seed across revisions that should differ only in structural parameters.
- Regenerate from the original photograph for every revision. Never feed a generated SVG or preview back as input.

## Delivery contract

- Require a valid SVG with no `<image>`, `<canvas>`, or `<foreignObject>` element.
- Require a matching JSON visual plan and a successful validator result.
- Require the JSON plan to omit all private quadrant/confidence state. The analysis may use that state internally, but exported artwork and plans must remain free of it.
- Keep the source file unchanged.
- Prefer three to ten large fields and no more than 32 meaningful point highlights. A night landscape should normally use only three structural paths: one atmospheric field, one foreground silhouette, and one foreground light field.
- Treat surface noise as topmost modulation, never as a substitute for shape. A rough-paper surface may contain one filtered undulation rectangle plus two rectangles filled by deterministic full-frame vector patterns inside one topmost group. When `--grain-overlay` is nonzero, allow one fourth rectangle using the ordinary high-frequency filter and require it to be last. Texture paths and ellipses must remain inside pattern definitions and must not count as structural fields.
- Allow at most one source-derived gradient per structural path. Never invent a decorative gradient direction or unrelated endpoint hue.
- Reject an output when the dominant silhouette is no longer approximately recognizable, source mode changes sampled hues, visible stair steps remain, or small regions overwhelm the large composition.
- Reject a source-mode palette when a meaningful chromatic accent visible at thumbnail size is absent from every structural field.
- Reject hairline or needle-shaped negative space between large fields unless the source feature is both intentional and structurally important.
- Reject any background-colored seam between retained general color fields that touched or came within `--min-negative-gap` in the analyzed segmentation.
- Reject every enclosed background-colored component at or below the minimum-clearance area in the final structural composite, including small wedges at triple junctions.
- Reject small enclosed background dashes left by discarded color regions; keep a large enclosed opening when it carries source structure.
- Reject a compact enclosed background-labelled hole when its source hue belongs to the enclosing field and opposes the background hue; this is an omitted same-material shadow, not intentional negative space.
- Reject a result that omits the only compact, locally contrasted island in an otherwise uniform field, a compact globally rare subject crossing a stable two- or three-field junction, or the only coherent rare-chromatic focal island in a hue-restrained scene, when it remains compositionally visible at thumbnail size. Do not add a protected focal role when an existing field already represents it coherently, and do not use this exception to restore texture or multiple small objects.
- Reject a result that retains a rare-chromatic focal role but breaks its broad row-relative luminous support into scattered holes or unrelated strips. Keep one coherent support mass only when the measured side-band relationship is present.
- Reject a result that omits a thumbnail-visible center-leading accent when it touches the lower frame, spans a substantial part of the foreground, remains locally distinct, and converges with the scene geometry. Do not use this exception to restore unrelated thin marks.
- Reject a reflective-horizontal result when the paired landform is broken into texture islands, its upper and lower outer envelopes do not agree around the measured axis, or source-distinct upper and lower colors are collapsed into one swatch. Require continuous sky and lower-field underlays, zero structural point highlights, and no enclosed background pocket inside the paired composition.
- Reject any background-colored sliver between a frame-touching structural field and the corresponding canvas edge. Require the fitted path to bleed past that viewBox edge and keep root overflow clipped.
- Reject acute or needle-like corners on internal tonal fields. Allow them only when they belong to the source-derived outer silhouette.

## Dependencies

Require Python 3, Pillow, and NumPy. The full pipeline is deterministic and offline: it makes no network calls, invokes no image model, and embeds no source raster in the SVG.
