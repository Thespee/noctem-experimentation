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

// ─ Global Scale ──────────────────────────────────────────────────
//   1.0 = 1080×1920 native.  Reduce to fit your monitor (e.g. 0.5).
float globalScale = 0.5;

// ─ Canvas & Timing ───────────────────────────────────────────────
int   canvasW   = round(1080 * globalScale);
int   canvasH   = round(1920 * globalScale);
int   targetFPS = 30;
float bpm       = 120.0;       // 1 beat = 500 ms = 15 frames

// ─ Font Pools ────────────────────────────────────────────────────
// File paths are relative to the sketch folder (../fonts/…).
String[] font1Pool = {
  "../fonts/ClimateCrisis-Regular-VariableFont_YEAR.ttf",
  "../fonts/Honk-Regular-VariableFont_MORF,SHLN.ttf",
  "../fonts/Oi-Regular.ttf"
};   // Scene 1 word cycle
String[] font2Pool = { "../fonts/Monoton-Regular.ttf" };   // Scene 3 outro
int fontCreateSize = round(300 * globalScale);       // base size for createFont (higher = sharper)

// ─ Typography ────────────────────────────────────────────────────
float trackingPx  = 0;         // extra letter-spacing in pixels (0 = default)
float leadingMult = 0.85;      // line-height multiplier (< 1 = tight/negative)

// ─ Safe Zones (Meta vertical) ────────────────────────────────────
int safeTop       = round(270 * globalScale);       // top UI margin px
int safeBottom    = round(384 * globalScale);       // bottom caption/UI margin px
int safeLeft      = round(27  * globalScale);       // left margin px
int safeRight     = round(27  * globalScale);       // right margin px
int maxSafeHeight = canvasH - safeTop - safeBottom;   // auto-derived
int maxSafeWidth  = canvasW - safeLeft - safeRight;     // auto-derived

// ─ Effects ───────────────────────────────────────────────────────
int   chromaticOffsetPx      = round(12 * globalScale);     // 3D-glasses pixel split (per side)
float patternRotationPerBeat = 15.0;   // degrees added each beat
long  effectSeed             = 42069L;   // deterministic seed for Scene 1 mutations

// ─ Intro Phase 2 ────────────────────────────────────────────────
String[] introWords     = { "CITY", "GOVERNMENT", "NO FUN", "CITY", "???" };
int      introWordBeats = 2;           // beats each word stays on screen

// ─ Outro ─────────────────────────────────────────────────────────
String outroPhrase        = "FUN CULTURE FUN PEOPLE";
float  outroBpmMultiplier = 1.0;       // 1 = quarter-note, 0.25 = whole-note
int    outroCycleTotal    = 4;

// ─ Debug ─────────────────────────────────────────────────────────
boolean showDebug = false;              // press 'D' to toggle


// ═════════════════════════════════════════════════════════════════
// INTERNAL STATE (do not edit)
// ═════════════════════════════════════════════════════════════════

int framesPerBeat;
PFont fontCorUnum;
PFont[] fonts1, fonts2;
PImage funhouseLogo;
PImage funhouseLogoCropped;
PImage funhouseLogoWhite;
PGraphics textBuf, logoBuf;
String[] outroWords;
int outroFramesPerWord;

// Scene 1 persistent effect state
boolean chromaticEnabled;
int     currentFontIdx;
float   wobbleA, wobbleATarget, wobbleAStart;
float   wobbleFreq, wobbleFreqTarget, wobbleFreqStart;
int     lastHalfBeat = -1;
int     wobbleEffectStartFrame;

int scene       = 0;    // 0 intro-p1  1 intro-p2  2 middle  3 outro
int sceneFrame  = 0;
int globalFrame = 0;


// ═════════════════════════════════════════════════════════════════
// SETUP
// ═════════════════════════════════════════════════════════════════

void settings() {
  size(canvasW, canvasH);
}

void setup() {
  frameRate(targetFPS);
  framesPerBeat = round(targetFPS * 60.0 / bpm);   // 15

  fontCorUnum = createFont("../fonts/RammettoOne-Regular.ttf", fontCreateSize);
  fonts1 = loadFontPool(font1Pool);
  fonts2 = loadFontPool(font2Pool);

  funhouseLogo = loadImage("../FunHouse Logo (Black).png");
  funhouseLogoCropped = cropToOpaque(funhouseLogo);
  funhouseLogoWhite   = whiteSilhouette(funhouseLogoCropped);
  textBuf = createGraphics(width, height);
  logoBuf = createGraphics(width, height);

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
  chromaticEnabled = false;
  currentFontIdx   = 0;
  wobbleA          = 0.16;
  wobbleATarget    = 0.16;
  wobbleAStart     = 0.16;
  wobbleFreq       = 8.0;
  wobbleFreqTarget = 8.0;
  wobbleFreqStart  = 8.0;
  wobbleEffectStartFrame = -99999;
  lastHalfBeat     = -1;
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
  if (next == 1) lastHalfBeat = -1;
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
    drawCorUnum(progress, false, 0, 0);
  } else if (beat == 2) {
    float slide = chromaticSlide(sceneFrame % framesPerBeat);
    drawCorUnum(1.0, true, 1, slide);   // chromatic slides out/in over the beat
    drawLogoOverlay(true, #c858fc);
  } else {
    float slide = chromaticSlide(sceneFrame % framesPerBeat);
    drawCorUnum(1.0, true, -1, slide);  // swapped chromatic slides out/in
    drawLogoOverlay(true, #c858fc);
  }
}

/**
 * Draw stacked "COR / UNUM" block, optionally with chromatic split.
 * COR is sized so both words share the same rendered width.
 * @param progress  0→1 scale interpolation (1 = fills max safe zone)
 * @param chromatic whether to apply 3D-glasses colour split
 * @param chrDir    +1 or −1 for offset direction (0 = none)
 */
void drawCorUnum(float progress, boolean chromatic, int chrDir, float offsetMult) {
  drawCorUnum(g, progress, chromatic, chrDir, offsetMult);
}

void drawCorUnum(PGraphics pg, float progress, boolean chromatic, int chrDir, float offsetMult) {
  PGraphics ctx = (pg == null) ? g : pg;
  ctx.textFont(fontCorUnum);
  ctx.textAlign(CENTER, CENTER);

  // 1. Size UNUM to fit within safe width / half safe height
  float targetFsUnum = fitFontSize(ctx, fontCorUnum, "UNUM", maxSafeWidth, maxSafeHeight * 0.5);
  ctx.textSize(targetFsUnum);
  float targetW = ctx.textWidth("UNUM");

  // 2. Size COR to match UNUM width
  ctx.textSize(100);
  float wCor100 = ctx.textWidth("COR");
  float targetFsCor = 100.0 * targetW / wCor100;

  // 3. Ensure total block fits in safe height
  float lineGap = max(targetFsCor, targetFsUnum) * leadingMult;
  float totalH  = targetFsCor / 2.0 + lineGap + targetFsUnum / 2.0;
  if (totalH > maxSafeHeight) {
    float shrink = maxSafeHeight / totalH;
    targetFsCor  *= shrink;
    targetFsUnum *= shrink;
  }

  // 4. Animate
  float fsCor  = max(1, targetFsCor * progress);
  float fsUnum = max(1, targetFsUnum * progress);
  float curGap = max(fsCor, fsUnum) * leadingMult;

  // 5. Position
  float cx = width / 2.0;
  float cy = height / 2.0;
  float y1 = cy - curGap / 2.0;
  float y2 = cy + curGap / 2.0;

  // 6. Draw
  if (chromatic) {
    float off = chromaticOffsetPx * chrDir * offsetMult;
    ctx.blendMode(SCREEN);
    ctx.fill(0, 255, 255);
    ctx.textSize(fsCor);  drawTracked(ctx, "COR",  cx + off, y1, trackingPx);
    ctx.textSize(fsUnum); drawTracked(ctx, "UNUM", cx + off, y2, trackingPx);
    ctx.fill(255, 0, 0);
    ctx.textSize(fsCor);  drawTracked(ctx, "COR",  cx - off, y1, trackingPx);
    ctx.textSize(fsUnum); drawTracked(ctx, "UNUM", cx - off, y2, trackingPx);
    ctx.blendMode(BLEND);
  } else {
    ctx.fill(255);
    ctx.textSize(fsCor);  drawTracked(ctx, "COR",  cx, y1, trackingPx);
    ctx.textSize(fsUnum); drawTracked(ctx, "UNUM", cx, y2, trackingPx);
  }
}

/** 0 → 1 → 0 over one beat using a sine bell curve */
float chromaticSlide(int frameInBeat) {
  float p = frameInBeat / (float) framesPerBeat;
  return sin(p * PI);
}


void drawLogoOverlay(boolean useTint, int tintColor) {
  // 1. Render white text shape to off-screen buffer
  textBuf.beginDraw();
  textBuf.background(0);
  textBuf.resetMatrix();
  drawCorUnum(textBuf, 1.0, false, 0, 0);
  textBuf.endDraw();

  // 2. Render white logo mask to another buffer
  logoBuf.beginDraw();
  logoBuf.background(0);
  logoBuf.imageMode(CENTER);
  float textReachW = maxSafeWidth + chromaticOffsetPx * 2.0;
  float s = textReachW / funhouseLogoCropped.width;
  float imgW = funhouseLogoCropped.width * s;
  float imgH = funhouseLogoCropped.height * s;
  logoBuf.image(funhouseLogoWhite, width / 2.0, height / 2.0, imgW, imgH);
  logoBuf.endDraw();

  // 3. Multiply: only keep pixels where BOTH text and logo are present
  textBuf.blend(logoBuf, 0, 0, width, height, 0, 0, width, height, MULTIPLY);

  // 4. Convert pure-black to transparent so we only draw the intersection
  textBuf.loadPixels();
  for (int i = 0; i < textBuf.pixels.length; i++) {
    if ((textBuf.pixels[i] & 0xFFFFFF) == 0) {
      textBuf.pixels[i] = 0; // transparent
    }
  }
  textBuf.updatePixels();

  // 5. Draw the intersection on top of the existing canvas
  if (useTint) tint(tintColor);
  else         noTint();
  image(textBuf, 0, 0);
  noTint();
}

PImage cropToOpaque(PImage img) {
  img.loadPixels();
  int minX = img.width, minY = img.height, maxX = 0, maxY = 0;
  boolean found = false;
  for (int y = 0; y < img.height; y++) {
    for (int x = 0; x < img.width; x++) {
      int a = (img.pixels[y * img.width + x] >> 24) & 0xFF;
      if (a > 10) {
        minX = min(minX, x);
        minY = min(minY, y);
        maxX = max(maxX, x);
        maxY = max(maxY, y);
        found = true;
      }
    }
  }
  if (!found) return img;
  return img.get(minX, minY, maxX - minX + 1, maxY - minY + 1);
}

PImage whiteSilhouette(PImage img) {
  PImage out = createImage(img.width, img.height, ARGB);
  out.loadPixels();
  img.loadPixels();
  for (int i = 0; i < img.pixels.length; i++) {
    int a = (img.pixels[i] >> 24) & 0xFF;
    out.pixels[i] = (a > 10) ? color(255, 255) : color(0, 255);
  }
  out.updatePixels();
  return out;
}


// ═════════════════════════════════════════════════════════════════
// SCENE 1 — INTRO PHASE 2   word cycle with A/B effects
// ═════════════════════════════════════════════════════════════════
//   Each word: introWordBeats beats.  Even beats → Effect A,
//   odd beats → Effect B.  Font cycles through font1Pool.

void drawIntroPhase2() {
  background(0);

  // Half-beat index (one beat = framesPerBeat frames)
  int halfBeat = (int)(sceneFrame / (framesPerBeat / 2.0));

  // Apply one deterministic mutation on every half-beat boundary
  if (halfBeat != lastHalfBeat) {
    wobbleAStart     = wobbleA;
    wobbleFreqStart  = wobbleFreq;
    wobbleEffectStartFrame = sceneFrame;
    applyHalfBeatEffect(halfBeat);
    lastHalfBeat = halfBeat;
  }

  // Linearly smooth wobble parameters over the half-beat
  float hbFrames = framesPerBeat / 2.0;
  float progress = constrain((sceneFrame - wobbleEffectStartFrame) / hbFrames, 0, 1);
  wobbleA    = lerp(wobbleAStart, wobbleATarget, progress);
  wobbleFreq = lerp(wobbleFreqStart, wobbleFreqTarget, progress);

  int wordIdx = constrain(halfBeat / (introWordBeats * 2), 0, introWords.length - 1);
  String word = introWords[wordIdx];
  PFont  font = fonts1[currentFontIdx % fonts1.length];

  // Waves always behind the text
  drawRadialPattern();

  // Text with current persistent effects
  textFont(font);
  textAlign(CENTER, CENTER);
  float fs = fitFontSize(font, word, maxSafeWidth, maxSafeHeight * 0.5);
  textSize(fs);

  if (chromaticEnabled) {
    blendMode(SCREEN);
    fill(0, 255, 255);
    drawTracked(word, width / 2.0 + chromaticOffsetPx, height / 2.0, trackingPx);
    fill(255, 0, 0);
    drawTracked(word, width / 2.0 - chromaticOffsetPx, height / 2.0, trackingPx);
    blendMode(BLEND);
  } else {
    fill(255);
    drawTracked(word, width / 2.0, height / 2.0, trackingPx);
  }
}

/** Apply one deterministic mutation to Scene 1 state */
void applyHalfBeatEffect(int halfBeat) {
  randomSeed(effectSeed + halfBeat);

  int choice = (int)random(3);   // 0 = chromatic, 1 = font, 2 = wobble

  if (choice == 0) {
    chromaticEnabled = !chromaticEnabled;
  } else if (choice == 1) {
    currentFontIdx = (currentFontIdx + 1) % fonts1.length;
  } else {
    if (random(1) < 0.5) {
      wobbleATarget += random(-0.02, 0.02);
      wobbleATarget = constrain(wobbleATarget, 0.05, 0.30);
    } else {
      wobbleFreqTarget += random(-1.0, 1.0);
      wobbleFreqTarget = constrain(wobbleFreqTarget, 4.0, 12.0);
    }
  }
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
  float fs = fitFontSize(font, outroWords[wordIdx], maxSafeWidth, maxSafeHeight * 0.4);
  textSize(fs);

  // Flash colour every quarter-beat
  int wordFrame = sceneFrame % outroFramesPerWord;
  int quarter   = (wordFrame * 4 / outroFramesPerWord) % 4;
  if (quarter % 2 == 0) fill(#c858fc);
  else                  fill(#8702c4);

  drawTracked(outroWords[wordIdx], width / 2.0, height / 2.0, trackingPx);
}


// ═════════════════════════════════════════════════════════════════
// RADIAL BACKGROUND PATTERN  (used by Effect B)
// ═════════════════════════════════════════════════════════════════
//   x(n,t) = cos(2πn/12)·t − sin(2πn/12)·A(t)·W(t)
//   y(n,t) = sin(2πn/12)·t + cos(2πn/12)·A(t)·W(t)
//   A(t) = wobbleA·t      W(t) = sin(√t × wobbleFreq)
//   n = 1…12,  t ∈ [0, 10]
//   Amplification: ×96  (domain 10 → 960 px = half canvas height)
//   Rotates patternRotationPerBeat° every beat (discrete steps).

void drawRadialPattern() {
  // Discrete beat-driven angle (integer division gives stepped rotation)
  float angle = (globalFrame / framesPerBeat) * patternRotationPerBeat;
  float amp   = 106.0 * globalScale;   // +10 base → ~+100 px reach at t=10
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
      float A  = wobbleA * t;
      float W  = sin(sqrt(t) * wobbleFreq);
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
  return fitFontSize(g, f, txt, maxW, maxH);
}

float fitFontSize(PGraphics pg, PFont f, String txt, float maxW, float maxH) {
  PGraphics ctx = (pg == null) ? g : pg;
  ctx.textFont(f);
  float probe = 100;
  ctx.textSize(probe);
  float tw = ctx.textWidth(txt);
  float th = ctx.textAscent() + ctx.textDescent();
  return probe * min(maxW / tw, maxH / th);
}

/**
 * Draw text with custom letter-spacing (tracking).
 * cx, cy = centre position of the rendered string.
 * When trk == 0 it falls through to the native text() call.
 */
void drawTracked(String txt, float cx, float cy, float trk) {
  drawTracked(g, txt, cx, cy, trk);
}

void drawTracked(PGraphics pg, String txt, float cx, float cy, float trk) {
  PGraphics ctx = (pg == null) ? g : pg;
  if (trk == 0) {
    ctx.text(txt, cx, cy);
    return;
  }

  // Measure total width including tracking
  float totalW = 0;
  for (int i = 0; i < txt.length(); i++) {
    totalW += ctx.textWidth(txt.charAt(i));
    if (i < txt.length() - 1) totalW += trk;
  }

  ctx.textAlign(LEFT, CENTER);
  float x = cx - totalW / 2.0;
  for (int i = 0; i < txt.length(); i++) {
    char c = txt.charAt(i);
    ctx.text(c, x, cy);
    x += ctx.textWidth(c) + trk;
  }
  ctx.textAlign(CENTER, CENTER);   // restore
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
  rect(0, safeTop, safeLeft, maxSafeHeight);
  rect(width - safeRight, safeTop, safeRight, maxSafeHeight);

  // Usable zone border
  noFill();
  stroke(255, 0, 0, 120);
  strokeWeight(1);
  rect(safeLeft, safeTop, maxSafeWidth, maxSafeHeight);
  noStroke();
}
