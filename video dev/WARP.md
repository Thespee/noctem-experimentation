# Vertical Video Prototype — Warp Context

Processing 4 generative video sketch. 1080×1920 vertical canvas, 30 FPS, 120 BPM.

## Structure

- `VerticalVideoPrototype/VerticalVideoPrototype.pde` — main sketch
- `fonts/` — `.ttf`/`.otf` files loaded relative to sketch via `../fonts/…`
- `FunHouse Logo (Black).png` — logo mask for Scene 0 punch-through

## Scene Flow

| Scene | Duration | Content |
|-------|----------|---------|
| 0 — Intro P1 | 4 beats | "COR / UNUM" expansion → chromatic aberration → logo punch-through |
| 1 — Intro P2 | variable | Word cycle with half-beat mutations (font, chromatic, wobble) |
| 2 — Middle | variable | Raw video with 4× random 1-beat filler cutaways + chroma-keyed green screen |
| 3 — Outro | variable | Word-by-word phrase, 4 cycles, quarter-beat colour flash |

In normal (preview) mode the sketch loops indefinitely.
In export mode it renders one full cycle and stops.
Scene 2 is generated separately by `scene2_processor.py`.

## Global Scale

Edit `globalScale` at the top of the sketch (default `0.5`) to fit your monitor. `canvasW`, `canvasH`, `fontCreateSize`, safe zones, and chromatic offset all scale proportionally from the native 1080×1920.

## Fonts

- **Scene 0 "COR / UNUM"**: `RammettoOne-Regular.ttf`
- **Scene 1 word cycle**: `ClimateCrisis`, `Honk`, `Oi` (pools through deterministically)
- **Scene 3 outro**: `Monoton-Regular.ttf`

All font paths are relative (`../fonts/…`). Files must exist or Processing falls back to a default sans.

## Safe Zones

- `safeTop` / `safeBottom` / `safeLeft` / `safeRight` — red in debug overlay (`D` key)
- Text auto-fits to `maxSafeWidth` and `maxSafeHeight`
- Effects (radial pattern, chromatic bleed) can extend past margins

## Scene 0 — COR UNUM

1. Beats 1–2: linear scale expansion from 1 px to full safe height
2. Beat 3: chromatic aberration slides in/out over the beat + `#c858fc` logo intersection overlay
3. Beat 4: swapped chromatic direction + same logo overlay

Logo uses a multiply-mask: black PNG is auto-cropped and converted to white silhouette, scaled to text reach, then multiplied against white text so only the intersection is drawn.

## Scene 1 — Word Cycle Mutations

Words change every 2 beats. On every **half-beat boundary**, one of three mutations fires (seed `42069`):

1. **Chromatic toggle** — 3D-glasses split on/off
2. **Font shift** — cycles through `font1Pool`
3. **Wobble tweak** — `wobbleA` or `wobbleFreq` drifts ±small amount (clamped)

All mutations are **persistent** across word changes. Radial pattern waves always render behind text. Wobble parameters smoothly interpolate over each half-beat via linear lerp.

## Scene 3 — Outro

`outroPhrase` words appear one at a time for 1 beat each. Colour flashes between `#c858fc` and `#8702c4` every quarter-beat.

## Debug

Press `D` to toggle red safe-zone overlay.

## Dependencies

- Processing 4
- Fonts installed in `fonts/` subdirectory (see list above)
- `FunHouse Logo (Black).png` in project root (for Scene 0)
