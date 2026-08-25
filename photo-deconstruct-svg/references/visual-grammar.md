# Visual Grammar

## Contents

- Reduction hierarchy
- Archetypes
- Color behavior
- Contour behavior
- Paper surface
- Parameter guide
- Visual checks

## Reduction hierarchy

Preserve evidence in this order:

1. Preserve the outer silhouette and occupied/empty-space ratio.
2. Preserve foreground/background order and the largest directional field.
3. Preserve two or three internal value roles.
4. Preserve one compact isolated subject when it is the only strong interruption inside a uniform field.
5. Preserve point highlights only when their distribution identifies the scene.
6. Remove texture, tiny edges, literal surface detail, and low-information objects.

Use a small number of large shapes. Minimalism is a hierarchy decision, not merely a small palette.

## Archetypes

The script selects an archetype from measured image properties.

### Night landscape

Detect a dark upper field and a warmer lower foreground. Build:

- one dark sky field;
- one low-contrast luminous atmospheric field;
- one coherent warm foreground silhouette;
- one broad light role clipped inside that silhouette; let the base silhouette carry shadows;
- zero to 32 isolated high points restricted to the sky.

Use the foreground silhouette as the identity lock. Do not allow internal tonal regions to alter its outer shape.

### Reflective horizontal fields

Activate this archetype only in a wide image when lightness, chroma, and edge
fields all agree after vertical opposition around one central horizontal axis.
Require the axis to remain away from the frame and require edge correlation so
a flat horizon or a smooth symmetric gradient cannot activate it. This is a
relationship test, not a semantic test for mountains, lakes, or water.

Trace one dynamic upper outer contour from source color jumps, edges, texture
change, and a restrained height prior. Regularize only compact downward valleys
that behave like internal texture boundaries, then fit the result with the same
four-pass curved contour policy used by large general fields. Build the lower
envelope from the measured vertical pairing, not from separately quantized
reflection fragments. Paint continuous sky and lower-field underlays first so
neither contour smoothing nor discarded texture can expose holes.

Divide the paired landform into only a few broad roles: terrain, vegetation,
rock, and an optional shore divider. Sample every upper and lower role from its
own source mask; do not reuse the upper color for the reflection because its
lightness and saturation often differ. Suppress point highlights, retain seven
to ten structural paths, and require the paired vertical area difference to
remain negligible after fitting.

### General color fields

Blur low-information detail, quantize the source palette, merge small connected regions, retain the largest component for each important color role, and rank optional regions by area and contrast. Use this fallback for bright landscapes, still life, architecture, and other scenes without the night-landscape relationship.

Large-field area thresholds can erase a small but composition-defining island.
Allow one protected exception when a compact component is detached from the
frame, has a non-linear two-dimensional footprint, differs clearly from its
local background, and is surrounded by one low-variation quantized field. A
second geometric case may straddle the junction of two or three stable fields:
model the surrounding ring with those roles, retain only compact pixels that
remain unlike every role, require the selected color to be globally rare, and
reject candidates in the lower fifth where ordinary foreground texture tends
to dominate. Treat this cross-field role as a fallback. In a globally
hue-restrained source, also allow one rare-chromatic
component when its color evidence is internally coherent and no existing
retained field already covers at least 80% of it. One immediately adjacent,
hue-aligned cap or spire may join that single role. Reject long thin marks,
diffuse color casts, texture fragments, and junctions without strong multi-role
coverage. Grow the retained island only through source pixels that remain
distinct from its local field model, sample a robust color from its own source
pixels, paint it after the broad fields, and fit it with two restrained contour
low-pass passes so its small identity is not rounded away. Apply the same rule
to any qualifying object; do not introduce semantic tests for clouds, moons,
boats, buildings, or trees.

When both the cross-field fallback and rare-chromatic role qualify, prefer the
rare-chromatic role so its independently measured luminous support field and
more specific source color remain intact.

When that rare-chromatic role is retained, allow one supporting exception only
if a broad adjacent field is consistently lighter than both side bands on the
same rows, touches the frame, and forms one coherent mass. Close narrow breaks,
fill enclosed micro-holes, sample the support from its own source pixels, and
paint it immediately before the rare focal role. Reject disconnected bright
fragments, small highlights, and ordinary bright sky. This must remain a
row-relative lightness rule, never a semantic test for snow, islands, foam, or
architecture.

Area filtering can also erase a narrow line that organizes the entire foreground.
Allow one protected perspective accent only when it touches the bottom frame,
extends through a substantial portion of the lower central image, has stable
local chromatic and lightness contrast, follows a narrow fitted centerline, and
aligns toward independently measured central convergence. Replace broken source
segments with one restrained tapered field when the line's continuity is its
compositional role, sample the accent from its brighter source evidence, and
paint it after the broad fields. Extend its exact frame contact straight beyond
the clipped viewBox without spreading the contact laterally. Reject wires,
stems, cracks, edge markings, and other thin features that fail any of these
tests. Do not test for a named object, a road, or a fixed yellow hue.

When a non-background component is omitted by the shape budget, merge it into
the touching retained field with the strongest boundary contact. Use source
color distance only to break ambiguous contacts. Never expose the full-frame
background merely because a local green, earth, or shadow component was
discarded.

Background assignment can fail for a dark patch whose lightness is closer to
the background swatch even though its hue belongs to the surrounding material.
For a background-labelled island fully enclosed by one retained field, measure
the unquantized source median and compare its Oklab chroma direction with both
roles. Merge only a compact island no larger than 0.2% of the analysis frame and
no wider or taller than 7% of the short side, with meaningful chroma in all
three samples, source-to-enclosing hue cosine at least 0.80, and
source-to-background cosine at most -0.45. Do not merge a neutral component, a
long opening, a large opening, a hue-aligned background component, or a hole
occupied by another retained path. Record this exception only when it activates
so unaffected outputs remain byte-for-byte stable.

After the baseline labels are stable, score the four image quadrants privately.
Use palette-assignment margin, source-edge recall, local connected-component
coherence, label entropy, and gradient activity. These measurements are only a
gate; do not write them to the SVG or JSON plan. A weak quadrant may activate
one of three source-measured structural roles:

- a dark perspective corridor bounded by two strong edges that converge near
  the horizon;
- a compact dark silhouette separated from broad horizontal context, with a
  reflected continuation tapered away when a measured horizon is present;
- a cool, frame-connected shore field that extends from a horizontal boundary
  deep into a warmer lower foreground.

Add a role only when all its scale, position, continuity, and color tests pass.
Sample its color from the role itself (using its darker or cooler robust subset
where that property defines the role), reserve at most one extra large field
per detected structure, and prevent unrelated discarded components from being
merged into it. If no role passes, preserve the baseline labels byte-for-byte.

## Color behavior

- Use source pixels as the default color authority.
- Sample each color from its own structural mask instead of recoloring one base swatch.
- Extract more candidate colors than the final palette can hold. Lock the dominant
  source role and the strongest meaningful chromatic role, then select the
  remaining roles by population-weighted Oklab distance. A broad low-variation
  sky must not consume the palette and suppress a smaller warm mountain, tree,
  building, or other composition-defining accent.
- Keep a limited luminance hierarchy instead of matching every photographic color.
- Make perceptual lightness/chroma guardrails optional through `--color-mode balanced`.
- Use a fixed palette only when explicitly requested through `--color-mode curated-night`.
- Do not add an unrelated complementary accent merely for decoration.
- When `--gradient-strength` is nonzero, compare horizontal, vertical, and two
  diagonal source-color trends inside each structural mask. Use the strongest
  measured direction and blend its robust 18/50/82-percentile colors only
  slightly into the flat role color. Keep one gradient per existing path and
  do not create additional regions.
- Read `color-research.md` for the research basis and exact fallback color codes.

## Contour behavior

- Analyze at sufficient resolution to preserve narrow subject features.
- For night landscapes, start from reliable warm foreground seeds, recover only
  a fixed-width shell of nearby dark earth colors, and keep the result connected
  to the bottom frame. Flood open sky from the top edge so side-connected rock
  shadows are filled without closing real gaps between separate formations.
- Use periodic cubic B-spline-to-Bézier paths for organic night-landscape
  contours. This approximates the sampled mask instead of forcing the curve
  through every pixel fluctuation, provides curvature-continuous joins, and
  preserves genuinely collinear runs as straight segments.
- Before fitting the foreground contour, apply an additive morphological close
  with a small, short-side-relative kernel. Fill only the portion of an open sky
  bay narrower than `--min-negative-gap`; preserve wider valleys and all
  positive subject pixels. This removes needle-shaped negative space without
  blunting hoodoos or erasing meaningful gaps between formations.
- Independent smooth fits on neighboring masks can expose a background-colored
  hairline even when their raster boundaries touched. Where an atmospheric
  field comes within the minimum-gap band of the foreground, extend it locally
  underneath the foreground and let SVG paint order hide the overlap. Never add
  a separate patch shape, and never expand the atmospheric field's free edge.
- For general color fields, derive render masks in paint order. Extend each
  earlier retained mask only through the local contact band of the union of
  later retained masks, then fit the extended mask. Interpret the requested
  minimum clearance as the expansion radius and add a small fitting allowance;
  use one additional analysis pixel of allowance with the four-pass general
  contour low-pass so stronger smoothing cannot open a triple-junction dot;
  passing it directly as a morphology filter diameter provides only half the
  intended protection. This curve-fit-safe underlap closes short channels and
  triple-junction pockets while preserving all free edges against the true
  background. Do not solve seams with strokes, duplicate paths, or a
  background-colored cover shape.
- Before deriving those paint-order masks, consolidate the union of all retained
  non-background fields. Additively close negative channels below the minimum
  clearance and fill only union-level background pockets below the matching
  area. Assign each added component to the touching field with the longest
  shared boundary. This union pass handles small background lobes that a smooth
  fit could otherwise pinch into isolated dots; it must not fill a large
  intentional opening.
- A smooth closed fit can pull a raster contour inward where it touches the
  canvas frame. Extend only the touching rows or columns through a short guard
  band beyond the viewBox before fitting, including a small allowance around
  each contact endpoint. Clip root overflow. Do not move an interior edge or
  add a visible frame stroke.
- Fill enclosed micro-holes only when their area is no greater than the square
  of the minimum-clearance width. Preserve larger source-derived openings and
  never apply the rule to an open outer silhouette.
- If a larger enclosed hole contains only discarded non-background labels,
  merge it into the enclosing field instead of exposing the full-frame
  background. Protect holes that belong to the true background or another
  retained structural path.
- Resample contours at uniform arc length and apply a closed-loop low-pass
  filter before fitting. Use four restrained passes for general color fields
  so pixel-scale edge chatter is reduced without shifting the segmentation or
  erasing broad source bends. Use a larger point budget for the identity silhouette
  and much smaller budgets for atmospheric and internal value fields. For
  internal fields, blur at a broader scale than the silhouette detector so
  photographic ridges merge into a few designed masses.
- Keep internal fields clipped to the silhouette so they cannot alter identity.
- Give internal value fields stricter geometry than the identity silhouette.
  Apply a small morphological opening and extra closed-loop low-pass passes to
  remove non-structural positive tips. Enforce a minimum-clearance rule near the
  outer contour: either retain a visibly broad base-color interval or extend
  the internal field underneath the clip boundary. Do not allow a tapering
  sliver to terminate in an artificial point. Preserve sharpness only when it
  is carried by the source-derived outer contour.
- Increase `--curve-smoothing` for rough pixel edges; increase `--detail` when
  the silhouette itself has lost characteristic overhangs or narrow towers.

## Paper surface

Create surface character with native SVG filters and low-opacity overlays. Keep
it independent from structural paths and place one surface group last in the
SVG so it modulates sky, shapes, and point highlights consistently. Do not
rasterize, embed a texture image, or displace the Bézier artwork.

Use `grain` for one high-frequency `feTurbulence` layer. Use `rough` as a hybrid
surface: one faint, single-octave `feTurbulence` field for broad sheet
undulation; seeded quadratic paths for pulp fibers; and seeded ellipses for
dark and light pores. Define both particle sets in full-frame SVG patterns so
they stay hard-edged and do not visibly repeat inside the canvas. Apply
`soft-light` only to the broad undulation. Render the fiber and pore patterns
normally at restrained opacity; applying `soft-light` to them weakens their
edges and recreates the hazy failure mode. Judge the rough profile at 100%
zoom: individual grains should remain distinct while the silhouette still
dominates at thumbnail size.

Use `--paper-density` independently from `--paper`. Density controls only how
many vector pores and fibers cover the frame; paper controls their opacity.
Keep density at `1.0` unless the request explicitly asks for more physical
particles. Scale particle radii downward as density rises so the result becomes
finer rather than dirtier.

Use `--grain-overlay` when the request asks for the earlier or traditional fine
noise *on top of* the rough-paper treatment. Reuse the ordinary high-frequency
three-octave `fractalNoise` filter, paint it after the fiber and pore patterns,
and combine it with `soft-light`. Keep this overlay separate from particle
density; use `0.20–0.36` for visible continuous coverage.

Use `--paper 0` for perfectly flat output. Use `0.24–0.45` for ordinary grain
and `0.44–0.54` for clearly visible rough paper. Values above `0.55` are
intentionally forceful and can weaken the shape hierarchy.

## Parameter guide

Parameter | Effect | Useful range
--- | --- | ---
`--detail` | Contour retention and minimum region size | `0.20–0.55`
`--palette-size` | Candidate source color roles | `5–7`
`--max-shapes` | Maximum general-archetype regions | `8–14`
`--paper` | Topmost SVG surface strength | `0.24–0.45` grain; `0.44–0.54` rough
`--paper-style` | Single-filter grain or hybrid vector-particle rough paper | `grain`, `rough`
`--paper-density` | Rough-paper vector pore/fiber count | `1.0` default; raise only when explicitly requested
`--grain-overlay` | Traditional fine fractal-noise layer above rough paper | `0.20–0.36`; `0` disables
`--gradient-strength` | Source-measured three-stop variation mixed into each path | `0.20–0.34`; default `0.30`
`--min-negative-gap` | Minimum retained negative-space width as a short-side fraction | `0.012–0.028`
`--analysis-size` | Segmentation resolution | `420–640`
`--color-mode` | Source fidelity or optional palette behavior | `source`, `balanced`, `curated-night`
`--curve-smoothing` | Arc-length resampling, low-pass smoothing, and cubic rounding | `0.70–0.90`
`--seed` | Reproducible texture/highlight variation | Any integer
`--no-points` | Remove isolated point highlights | Flag

## Visual checks

- Compare the source and SVG at thumbnail size. Confirm the main occupied shape has the same approximate location, height, width, and left/right weight.
- Squint at both images. Confirm the large light/dark organization remains related.
- Confirm every retained point group corresponds to a real high-frequency highlight population.
- Confirm no region exists only to fill an empty area.
- Confirm the output reads first as an abstract composition and second as a memory of the source.
- Confirm the top surface noise is visible at 100% but does not weaken the large-shape hierarchy.
- Confirm every structural field that reaches the source frame remains flush to the matching SVG edge at 100% zoom, with no line of the full-frame background showing through.
- Temporarily render the background in a diagnostic color and all structural paths in one solid color. Confirm that no enclosed diagnostic-color component at or below the minimum-clearance area remains inside the structural union.
- Confirm exported SVG and JSON text contains no quadrant labels, confidence score, confidence threshold, or low-confidence flag.
