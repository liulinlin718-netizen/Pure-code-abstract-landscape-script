# Color Research and Palettes

## Default policy

Treat the photograph as the color authority. Extract colors from the pixels
inside each structural mask and assign them by role:

1. background or sky;
2. atmospheric field;
3. subject base;
4. subject shadow;
5. subject light;
6. point highlight.

Do not rotate source hues or impose a global tint by default. `--color-mode
source` returns sampled sRGB values unchanged. `--color-mode balanced` keeps
the same OKLCH hue and only limits extreme lightness, chroma, or out-of-gamut
values. `--color-mode curated-night` is an explicit fallback, never an
automatic replacement for a usable source palette.

Before final assignment, extract twice the requested number of robust source
candidates. Preserve the dominant candidate and the strongest chromatic
candidate with meaningful area, then choose the remaining roles by
population-weighted Oklab separation. Recompute every final swatch as the
median of the source pixels assigned to that role. This keeps small but
composition-defining warm/cool accents without inventing saturation.

## Research basis

- [W3C CSS Color Module Level 4](https://www.w3.org/TR/css-color-4/) describes
  Oklab/OKLCH as more perceptually uniform than older HSL-style workflows and
  recommends Oklab for perceptually even interpolation. Use it for small
  guardrail adjustments, not for inventing a new hue.
- [Android Dynamic Color](https://developer.android.com/develop/ui/views/theming/dynamic-colors)
  extracts a source color from an image and expands it into tonal roles. The
  implementation here borrows the source-first, role-based principle without
  reproducing Material UI palettes.
- [Adobe Color FAQ](https://helpx.adobe.com/in/creative-cloud/adobe-color.html)
  supports extracting a theme from an image and then controlling it with a
  base color and harmony rule. For minimal abstract work, prefer source-derived
  monochromatic or analogous relationships over unrelated complementary
  accents.

## Optional fallback palettes

These are project presets designed for restrained editorial abstraction. They
are not substitutes for image sampling.

### Night rock

Role | Hex
--- | ---
Sky | `#151918`
Outer atmospheric field | `#6D5D63`
Inner atmospheric field | `#968087`
Rock base | `#704832`
Rock shadow | `#3B251F`
Rock light | `#B77D50`
Star / pale accent | `#E8D7CF`

### Warm paper landscape

Role | Hex
--- | ---
Paper | `#F1ECE2`
Ink | `#24231F`
Earth shadow | `#5A4033`
Earth base | `#8A5F46`
Sand light | `#C58B5E`
Pale light | `#D6B18A`
Neutral haze | `#7D7771`

### Cool-warm landscape

Role | Hex
--- | ---
Deep cool | `#172326`
Cool midtone | `#45636B`
Cool light | `#7FA0A4`
Warm shadow | `#704A3B`
Warm midtone | `#A66B4F`
Warm light | `#D3A174`
Pale neutral | `#EFE7D8`

## Acceptance checks

- In `source` mode, every structural hex value must come from a robust source
  sample inside its corresponding mask.
- Shadow and light may differ in hue when the photograph genuinely contains
  colored illumination; do not force them into one synthetic hue family.
- The atmospheric field must remain translucent and subordinate to the sky and
  subject silhouette.
- Paper grain must not visibly recolor the source-derived palette.
- Record both the sampled palette and the final structural palette in JSON.
