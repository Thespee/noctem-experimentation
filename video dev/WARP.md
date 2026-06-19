# Vertical Video Prototype — Warp Context
Modular visual pipeline for the `video dev` project. Target output is 1080×1920 at 30 FPS, synced to 120 BPM.

## Structure

- `VerticalVideoPrototype/VerticalVideoPrototype.pde` — main sketch
- `fonts/` — `.ttf`/`.otf` files loaded relative to sketch via `../fonts/…`
- `FunHouse Logo (Black).png` — logo mask for Scene 0 punch-through

## Scene Flow (authoritative target)
1. **Scene 0 (4 beats)**
   - Dithered first frame of the main raw video as background.
   - Processing intro animation (COR/UNUM + logo treatment) composited over that background.
2. **Scene 1 (4 word segments)**
   - Strict alternation: `clip_1 -> word_1 -> clip_2 -> word_2 -> clip_3 -> word_3 -> clip_4 -> word_4`.
   - Clips are short setup excerpts from the same main raw video and must be dithered.
   - Word segments are rendered from Processing intro frames, one segment per configured word.
3. **Scene 2 (main body)**
   - Starts with 4 random one-beat filler cutaways sourced from pre-start footage.
   - Main section: green-screen foreground is keyed, dithered/pixelated, and composited over a clean full-frame background image.
   - Background image should remain clean (not dithered); only the keyed foreground is dithered.
4. **Scene 3 (16 beats total)**
   - Processing outro text overlay over 3 background video blocks (4 beats each), then black background for final 4 beats.
   - Background videos are scaled/cropped to fully fill 1080×1920.

In normal preview mode, the Processing sketch can loop; in export mode it should render one cycle and stop.
Scene 2 processing remains FFmpeg-driven in `scene2_processor.py`.

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

## Scene 1 — Current Composition Contract
- Processing still generates the intro animation frames (including Scene 1 text content), but final Scene 1 in the pipeline is built by compositor assembly, not by playing the full raw Processing scene as-is.
- Exactly 4 text segments are expected for Scene 1, mapped one-to-one with configured words.
- The compositor must alternate setup clips and text segments in the fixed pattern above.
- Setup clips and Scene 0 background still must share the same raw-video dither look.

## Scene 2 — Current Composition Contract
- Input video orientation must be normalized before composition so output remains vertical (1080×1920) without sideways playback.
- Cutaway filler segments should use the same dither treatment as other raw-video excerpts.
- Foreground-only dither path must preserve alpha after keying (no alpha stripping before overlay).
- Final Scene 2 output should preserve the keyed foreground over the clean background image.

## Scene 3 — Outro

`outroPhrase` words appear one at a time for 1 beat each. Colour flashes between `#c858fc` and `#8702c4` every quarter-beat.

## Dither Intent (pipeline-level)
- Dithered:
  - Scene 0 raw-video background still
  - Scene 1 raw setup clips
  - Scene 2 raw cutaways
  - Scene 2 keyed foreground (foreground-only branch)
- Not dithered:
  - Scene 1 text overlays
  - Scene 2 background replacement image
  - Scene 3 background blocks and text overlay

## Debug

Press `D` to toggle red safe-zone overlay.

## Dependencies

- Processing 4
- Fonts installed in `fonts/` subdirectory (see list above)
- `FunHouse Logo (Black).png` in project root (for Scene 0)
