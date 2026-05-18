/* ═══════════════════════════════════════════════════════════════
   VERTICAL VIDEO PROTOTYPE — Processing 4
   Generative BPM-driven visual fingerprint sandbox
   Canvas: 1080 × 1920  |  30 FPS  |  120 BPM

   SCENE FLOW (loops indefinitely):
     Scene 0 — Intro Phase 1   "COR UNUM" expansion       (4 beats)
     Scene 1 — Intro Phase 2   Word cycle A/B effects      (variable)
     Scene 2 — Middle           Pure green screen           (60 frames)
     Scene 3 — Outro            Word-by-word phrase ×4      (variable)

   FONTS:
     To load custom fonts, create a data/ folder inside this sketch
     folder, drop .ttf/.otf files there, then replace the pool
     entries below with the filenames (e.g. "MyFont.ttf").

   DEBUG:
     Press 'D' at any time to toggle the Meta safe-zone overlay.
   ═══════════════════════════════════════════════════════════════ */


// ═════════════════════════════════════════════════════════════════
// CONFIGURATION — edit these freely
// ═════════════════════════════════════════════════════════════════

// ─ Canvas & Timing ───────────────────────────────────────────────
int   canvasW   = 1080;
int   canvasH   = 1920;
int   targetFPS = 30;
float bpm       = 120.0;       // 1 beat = 500 ms = 15 frames

// ─ Font Pools ────────────────────────────────────────────────────
// System font names work as placeholders; swap for filenames later.
String[] font1Pool = { "Impact", "Arial Bold" };   // Intro (blocky)
String[] font2Pool = { "Arial", "Georgia" };         // Outro
int fontCreateSize = 300;       // base size for createFont (higher = sharper)

// ─ Typography ────────────────────────────────────────────────────
float trackingPx  = 0;         // extra letter-spacing in pixels (0 = default)
float leadingMult = 0.85;      // line-height multiplier (< 1 = tight/negative)

// ─ Safe Zones (Meta vertical) ────────────────────────────────────
int safeTop       = 270;       // top UI margin px
int safeBottom    = 384;       // bottom caption/UI margin px
int maxSafeHeight = 1266;      // usable: 1920 − 270 − 384

// ─ Effects ───────────────────────────────────────────────────────
int   chromaticOffsetPx      = 12;     // 3D-glasses pixel split (per side)
float patternRotationPerBeat = 15.0;   // degrees added each beat

// ─ Intro Phase 2 ────────────────────────────────────────────────
String[] introWords     = { "TRUTH", "VOID", "ECHO", "FLUX", "ZERO" };
int      introWordBeats = 2;           // beats each word stays on screen

// ─ Outro ─────────────────────────────────────────────────────────
String outroPhrase        = "THE ANSWER LIES WITHIN THE SEQUENCE";
float  outroBpmMultiplier = 1.0;       // 1 = quarter-note, 0.25 = whole-note
int    outroCycleTotal    = 4;

// ─ Debug ─────────────────────────────────────────────────────────
boolean showDebug = false;              // press 'D' to toggle


// ═════════════════════════════════════════════════════════════════
// INTERNAL STATE (do not edit)
// ═════════════════════════════════════════════════════════════════

int framesPerBeat;
PFont[] fonts1, fonts2;
String[] outroWords;
int outroFramesPerWord;

int scene       = 0;    // 0 intro-p1  1 intro-p2  2 middle  3 outro
int sceneFrame  = 0;
int globalFrame = 0;


// ═════════════════════════════════════════════════════════════════
// SETUP
// ═════════════════════════════════════════════════════════════════

void settings() {
  size(1080, 1920);
}

void setup() {
  frameRate(targetFPS);
  framesPerBeat = round(targetFPS * 60.0 / bpm);   // 15

  fonts1 = loadFontPool(font1Pool);
  fonts2 = loadFontPool(font2Pool);

  outroWords         = split(outroPhrase, ' ');
  outroFramesPerWord = round(framesPerBeat / outroBpmMultiplier);

  resetAll();
}

PFont[] loadFontPool(String[] names) {
  PFont[] pool = new PFont[names.length];
  for (int i = 0; i < names.length; i++)
    pool[i] = createFont(names[i], fontCreateSize);
  return pool;
}

void resetAll() {
  scene       = 0;
  sceneFrame  = 0;
  globalFrame = 0;
}


// ═════════════════════════════════════════════════════════════════
// MAIN LOOP
// ═════════════════════════════════════════════════════════════════

void draw() {
  blendMode(BLEND);          // safety reset each frame
  handleTransitions();       // advance scene when its duration expires

  switch (scene) {
    case 0: drawIntroPhase1(); break;
    case 1: drawIntroPhase2(); break;
    case 2: drawMiddle();      break;
    case 3: drawOutro();       break;
  }

  if (showDebug) drawSafeZoneOverlay();
  sceneFrame++;
  globalFrame++;
}

void handleTransitions() {
  if (scene == 0 && sceneFrame >= 4 * framesPerBeat) {
    advanceTo(1);
  } else if (scene == 1 && sceneFrame >= introWords.length * introWordBeats * framesPerBeat) {
    advanceTo(2);
  } else if (scene == 2 && sceneFrame >= 2 * targetFPS) {
    advanceTo(3);
  } else if (scene == 3 && sceneFrame >= outroWords.length * outroFramesPerWord * outroCycleTotal) {
    resetAll();
  }
}

void advanceTo(int next) {
  scene      = next;
  sceneFrame = 0;
}

void keyPressed() {
  if (key == 'd' || key == 'D') showDebug = !showDebug;
}


// ═════════════════════════════════════════════════════════════════
// SCENE 0 — INTRO PHASE 1   "COR UNUM" expansion (4 beats)
// ═════════════════════════════════════════════════════════════════
//   Beats 1–2  linear scale from 1 px → maxSafeHeight
//   Beat  3    chromatic aberration (normal)
//   Beat  4    chromatic aberration (swapped)

void drawIntroPhase1() {
  background(0);
  int beat = sceneFrame / framesPerBeat;       // 0-indexed: 0 1 2 3

  if (beat < 2) {
    // Constant-rate expansion over 30 frames (frames 0–29)
    float progress = (float) sceneFrame / (2 * framesPerBeat - 1);
    drawCorUnum(progress, false, 0);
  } else if (beat == 2) {
    drawCorUnum(1.0, true, 1);                 // chromatic normal
  } else {
    drawCorUnum(1.0, true, -1);                // chromatic swapped
  }
}

/**
 * Draw stacked "COR / UNUM" block, optionally with chromatic split.
 * @param progress  0→1 scale interpolation (1 = fills max safe zone)
 * @param chromatic whether to apply 3D-glasses colour split
 * @param chrDir    +1 or −1 for offset direction (0 = none)
 */
void drawCorUnum(float progress, boolean chromatic, int chrDir) {
  PFont font = fonts1[0];
  textFont(font);
  textSize(fontCreateSize);
  textAlign(CENTER, CENTER);

  // Two-line block geometry (in local / pre-scale coords)
  float lineGap = fontCreateSize * leadingMult;     // baseline-to-baseline
  float blockH  = fontCreateSize + lineGap;          // approx total height
  float y1      = -lineGap / 2.0;
  float y2      =  lineGap / 2.0;

  // Scale: 1 px at progress=0, maxSafeHeight at progress=1
  float scaleMin = 1.0 / blockH;
  float scaleMax = (float) maxSafeHeight / blockH;
  float s        = lerp(scaleMin, scaleMax, progress);

  pushMatrix();
  translate(width / 2.0, height / 2.0);
  scale(s);

  if (chromatic) {
    // Offset in screen px → divide by current scale for local coords
    float off = chromaticOffsetPx * chrDir / s;
    blendMode(SCREEN);
    fill(0, 255, 255);
    drawTracked("COR",   off, y1, trackingPx);
    drawTracked("UNUM",  off, y2, trackingPx);
    fill(255, 0, 0);
    drawTracked("COR",  -off, y1, trackingPx);
    drawTracked("UNUM", -off, y2, trackingPx);
    blendMode(BLEND);
  } else {
    fill(255);
    drawTracked("COR",  0, y1, trackingPx);
    drawTracked("UNUM", 0, y2, trackingPx);
  }

  popMatrix();
}


// ═════════════════════════════════════════════════════════════════
// SCENE 1 — INTRO PHASE 2   word cycle with A/B effects
// ═════════════════════════════════════════════════════════════════
//   Each word: introWordBeats beats.  Even beats → Effect A,
//   odd beats → Effect B.  Font cycles through font1Pool.

void drawIntroPhase2() {
  background(0);

  int beatInScene    = sceneFrame / framesPerBeat;
  int wordIdx        = constrain(beatInScene / introWordBeats, 0, introWords.length - 1);
  int beatWithinWord = beatInScene % introWordBeats;

  String word = introWords[wordIdx];
  PFont  font = fonts1[wordIdx % fonts1.length];

  if (beatWithinWord % 2 == 0) {
    drawEffectA(word, font);
  } else {
    drawEffectB(word, font);
  }
}

/** Effect A — chromatic 3D-glasses text */
void drawEffectA(String word, PFont font) {
  textFont(font);
  textAlign(CENTER, CENTER);
  float fs = fitFontSize(font, word, width * 0.85, maxSafeHeight * 0.5);
  textSize(fs);

  blendMode(SCREEN);
  fill(0, 255, 255);
  drawTracked(word, width / 2.0 + chromaticOffsetPx, height / 2.0, trackingPx);
  fill(255, 0, 0);
  drawTracked(word, width / 2.0 - chromaticOffsetPx, height / 2.0, trackingPx);
  blendMode(BLEND);
}

/** Effect B — rotating radial pattern background + centred white text */
void drawEffectB(String word, PFont font) {
  drawRadialPattern();

  textFont(font);
  textAlign(CENTER, CENTER);
  float fs = fitFontSize(font, word, width * 0.85, maxSafeHeight * 0.5);
  textSize(fs);
  fill(255);
  drawTracked(word, width / 2.0, height / 2.0, trackingPx);
}


// ═════════════════════════════════════════════════════════════════
// SCENE 2 — MIDDLE   pure green screen (exactly 60 frames / 2 s)
// ═════════════════════════════════════════════════════════════════

void drawMiddle() {
  background(0, 255, 0);
}


// ═════════════════════════════════════════════════════════════════
// SCENE 3 — OUTRO   word-by-word phrase, 4 full cycles
// ═════════════════════════════════════════════════════════════════

void drawOutro() {
  background(0);

  int wordsInPhrase = outroWords.length;
  int cycleIdx      = sceneFrame / (wordsInPhrase * outroFramesPerWord);
  int wordIdx       = (sceneFrame / outroFramesPerWord) % wordsInPhrase;

  // Cycle font per cycle through font2Pool
  PFont font = fonts2[cycleIdx % fonts2.length];
  textFont(font);
  textAlign(CENTER, CENTER);
  float fs = fitFontSize(font, outroWords[wordIdx], width * 0.85, maxSafeHeight * 0.4);
  textSize(fs);
  fill(255);
  drawTracked(outroWords[wordIdx], width / 2.0, height / 2.0, trackingPx);
}


// ═════════════════════════════════════════════════════════════════
// RADIAL BACKGROUND PATTERN  (used by Effect B)
// ═════════════════════════════════════════════════════════════════
//   x(n,t) = cos(2πn/12)·t − sin(2πn/12)·A(t)·W(t)
//   y(n,t) = sin(2πn/12)·t + cos(2πn/12)·A(t)·W(t)
//   A(t) = 0.16·t      W(t) = sin(√t × 8)
//   n = 1…12,  t ∈ [0, 10]
//   Amplification: ×96  (domain 10 → 960 px = half canvas height)
//   Rotates patternRotationPerBeat° every beat (discrete steps).

void drawRadialPattern() {
  // Discrete beat-driven angle (integer division gives stepped rotation)
  float angle = (globalFrame / framesPerBeat) * patternRotationPerBeat;
  float amp   = 96.0;
  float tStep = 0.05;

  pushMatrix();
  translate(width / 2.0, height / 2.0);
  rotate(radians(angle));

  stroke(255, 160);
  strokeWeight(1.5);
  noFill();

  for (int n = 1; n <= 12; n++) {
    float theta = TWO_PI * n / 12.0;
    float cn    = cos(theta);
    float sn    = sin(theta);

    beginShape();
    for (float t = 0; t <= 10; t += tStep) {
      float A  = 0.16 * t;
      float W  = sin(sqrt(t) * 8.0);
      float px = (cn * t - sn * A * W) * amp;
      float py = (sn * t + cn * A * W) * amp;
      vertex(px, py);
    }
    endShape();
  }

  popMatrix();
  noStroke();
}


// ═════════════════════════════════════════════════════════════════
// HELPERS
// ═════════════════════════════════════════════════════════════════

/** Compute the largest font size that fits `txt` inside maxW × maxH. */
float fitFontSize(PFont f, String txt, float maxW, float maxH) {
  textFont(f);
  float probe = 100;
  textSize(probe);
  float tw = textWidth(txt);
  float th = textAscent() + textDescent();
  return probe * min(maxW / tw, maxH / th);
}

/**
 * Draw text with custom letter-spacing (tracking).
 * cx, cy = centre position of the rendered string.
 * When trk == 0 it falls through to the native text() call.
 */
void drawTracked(String txt, float cx, float cy, float trk) {
  if (trk == 0) {
    text(txt, cx, cy);
    return;
  }

  // Measure total width including tracking
  float totalW = 0;
  for (int i = 0; i < txt.length(); i++) {
    totalW += textWidth(txt.charAt(i));
    if (i < txt.length() - 1) totalW += trk;
  }

  textAlign(LEFT, CENTER);
  float x = cx - totalW / 2.0;
  for (int i = 0; i < txt.length(); i++) {
    char c = txt.charAt(i);
    text(c, x, cy);
    x += textWidth(c) + trk;
  }
  textAlign(CENTER, CENTER);   // restore
}


// ═════════════════════════════════════════════════════════════════
// DEBUG — safe-zone overlay (toggle with 'D')
// ═════════════════════════════════════════════════════════════════

void drawSafeZoneOverlay() {
  blendMode(BLEND);
  noStroke();

  // Blocked-out margins (semi-transparent red)
  fill(255, 0, 0, 80);
  rect(0, 0, width, safeTop);
  rect(0, height - safeBottom, width, safeBottom);

  // Usable zone border
  noFill();
  stroke(255, 0, 0, 120);
  strokeWeight(1);
  rect(0, safeTop, width, maxSafeHeight);
  noStroke();
}
