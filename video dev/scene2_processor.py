#!/usr/bin/env python3
"""
scene2_processor.py
===================
Processes raw footage for Scene 2 of the vertical video.

Workflow:
1. Extracts 4 random 1-beat segments from the filler portion
   (between 0 and ACTUAL_START_SECONDS)
2. Trims the main content from ACTUAL_START_SECONDS to CUT_FROM_END
3. Replaces green screen in the main content with INPUT_PHOTO
4. Concatenates: filler1 + filler2 + filler3 + filler4 + processed_main
5. Renders to OUTPUT_VIDEO

Dependencies:
  - ffmpeg (must be on PATH)
  - ffprobe (must be on PATH)
"""

import subprocess
import os
import sys
import random
import tempfile
import shutil

# ═════════════════════════════════════════════════════════════════
# USER CONFIGURATION — edit everything below this line
# ═════════════════════════════════════════════════════════════════

# ─ Paths ────────────────────────────────────────────────────────
# ← YOUR RAW VIDEO FILE (replace with actual path)
#    Use r"..." for Windows paths so backslashes aren't treated as escapes.
INPUT_VIDEO = r"C:\Users\Rage4\Documents\GitHub\noctem\video dev\videos\test videos\VID_20260520_152333.mp4"

# ← YOUR PHOTO TO OVERLAY ON THE GREEN SCREEN (replace with actual path)
INPUT_PHOTO = r"C:\Users\Rage4\Documents\GitHub\noctem\video dev\videos\IMG_0724.JPG"

# ← WHERE TO SAVE THE RESULTING SCENE 2 VIDEO
OUTPUT_VIDEO = "../export/scene2.mp4"

# ─ Timing ─────────────────────────────────────────────────────────
# These should match your Processing sketch:
BPM = 120.0
FPS = 30.0

# Mark when your actual video content starts (seconds).
# Random 1-beat cutaways will be pulled from [0, ACTUAL_START_SECONDS).
ACTUAL_START_SECONDS = 50

# Cut this many seconds from the end of the main content.
# Set to 0 to use everything from ACTUAL_START_SECONDS to the end.
CUT_FROM_END_SECONDS = 3

# ─ Green Screen Parameters ────────────────────────────────────────
# Hex color to key out. Default is pure green (#00FF00).
# If your green screen is a different shade, use a color picker
# and set it here (format: 0xRRGGBB).
CHROMA_KEY_COLOR = "0x4D7B5A"

# Similarity: how close a pixel must be to the key color to be removed.
# Range: 0.01 (very strict, leaves edges) to 1.0 (very loose, may eat non-green).
# Default 0.15. Increase if green edges remain; decrease if non-green areas disappear.
CHROMA_SIMILARITY = 0.15

# Blend: edge softness. 0.0 = hard edges, higher = softer feather.
# Range: 0.0 to 1.0. Default 0.0.
CHROMA_BLEND = 0.0

# ─ Output Resolution ───────────────────────────────────────────────
# Hard-coded to match the Processing canvas. The input video MUST already be
# this resolution or the script will abort. Convert it beforehand if needed.
OUTPUT_RESOLUTION = (1080, 1920)

# ─ Random Seed ───────────────────────────────────────────────────
# Change this to get different random cutaway segments.
RANDOM_SEED = 42069

# ─ Debug ───────────────────────────────────────────────────────────
# Set True to keep temporary files after rendering (for inspection).
KEEP_TEMP = False

# ═════════════════════════════════════════════════════════════════
# INTERNALS — do not edit below unless you know what you're doing
# ═════════════════════════════════════════════════════════════════

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def resolve_path(path):
    """Resolve relative paths against the script's directory."""
    if not path or os.path.isabs(path):
        return path
    return os.path.join(_SCRIPT_DIR, path)


def run(cmd, **kwargs):
    """Run a shell command, print it, and raise on failure."""
    print(f"[CMD] {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, **kwargs)
    if result.returncode != 0:
        print(f"[STDERR] {result.stderr}", file=sys.stderr)
        raise RuntimeError(f"Command failed: {' '.join(cmd)}")
    return result


def get_video_duration(path):
    """Get duration in seconds using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path,
    ]
    result = run(cmd)
    return float(result.stdout.strip())


def get_video_info(path):
    """Get raw (width, height) and rotation metadata using ffprobe."""
    # --- raw width / height ---
    cmd_wh = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path,
    ]
    result_wh = run(cmd_wh)
    lines = [ln for ln in result_wh.stdout.splitlines() if ln.strip()]
    if len(lines) < 2:
        raise RuntimeError(f"Unexpected ffprobe resolution output: {result_wh.stdout!r}")
    w, h = int(lines[0].strip()), int(lines[1].strip())

    # --- rotation from Display Matrix side data ---
    cmd_rot = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream_side_data_list",
        "-of", "default=noprint_wrappers=1",
        path,
    ]
    result_rot = run(cmd_rot)
    rotation = 0
    for line in result_rot.stdout.splitlines():
        line = line.strip()
        if line.startswith("rotation="):
            try:
                rotation = int(line.split("=", 1)[1])
            except ValueError:
                pass
            break
    return w, h, rotation


def main():
    # ─ Dependency checks ──────────────────────────────────────────
    for bin_name in ["ffmpeg", "ffprobe"]:
        if shutil.which(bin_name) is None:
            print(f"[FATAL] '{bin_name}' not found on PATH. Install FFmpeg and try again.")
            sys.exit(1)

    # ─ Input validation ───────────────────────────────────────────
    if not os.path.exists(INPUT_VIDEO):
        print(f"[FATAL] INPUT_VIDEO not found: {INPUT_VIDEO}")
        print("Hint: edit the INPUT_VIDEO path at the top of this script.")
        sys.exit(1)
    if not os.path.exists(INPUT_PHOTO):
        print(f"[FATAL] INPUT_PHOTO not found: {INPUT_PHOTO}")
        print("Hint: edit the INPUT_PHOTO path at the top of this script.")
        sys.exit(1)

    # ─ Timing calculations ──────────────────────────────────────
    beat_duration = 60.0 / BPM
    beat_frames = int(FPS * beat_duration)

    print(f"=" * 60)
    print(f"Scene 2 Processor")
    print(f"=" * 60)
    print(f"Beat duration : {beat_duration:.3f}s ({beat_frames} frames)")
    print(f"Filler range  : 0s → {ACTUAL_START_SECONDS}s")

    # ─ Video metadata ─────────────────────────────────────────────
    total_duration = get_video_duration(INPUT_VIDEO)
    v_w, v_h, rotation = get_video_info(INPUT_VIDEO)
    print(f"Video raw size : {v_w}x{v_h}  (rotation={rotation})")
    print(f"Video duration : {total_duration:.3f}s")

    # ─ Resolution enforcement (account for rotation metadata) ─────
    ow, oh = OUTPUT_RESOLUTION

    # Normalize rotation to 0-359 range for robust matching
    rot = rotation % 360

    # Compute effective (displayed) dimensions after player applies rotation
    effective_w, effective_h = v_w, v_h
    transpose_filter = ""
    if rot in (90, 270):
        effective_w, effective_h = v_h, v_w
        # FFmpeg auto-rotates by default; we suppress it with -noautorotate
        # and manually transpose the raw pixels once to bake the rotation in.
        #
        # For raw landscape 1920×1080 with rotation=-90 (camera held 90° clockwise):
        #   Raw pixels have content rotated 90° clockwise.
        #   transpose=2 (90° counter-clockwise) makes content upright.
        # For rotation=+90 (camera held 90° counter-clockwise):
        #   Raw pixels have content rotated 90° counter-clockwise.
        #   transpose=1 (90° clockwise) makes content upright.
        if rot == 270:   # 270° = -90°
            transpose_filter = "transpose=1,"   # 90° clockwise
        else:            # rot == 90°
            transpose_filter = "transpose=2,"   # 90° counter-clockwise
    elif rot == 180:
        effective_w, effective_h = v_w, v_h
        transpose_filter = "transpose=1,transpose=1,"  # 180°
    if (effective_w, effective_h) != (ow, oh):
        print(f"[FATAL] Input video effective size is {effective_w}x{effective_h}, must be {ow}x{oh}.")
        print(f"        Raw size: {v_w}x{v_h}, rotation: {rotation} (normalized={rot})")
        print("        Convert it first if the dimensions are simply wrong.")
        sys.exit(1)

    # ─ Main content range ─────────────────────────────────────────
    main_start = ACTUAL_START_SECONDS
    if CUT_FROM_END_SECONDS > 0:
        main_end = total_duration - CUT_FROM_END_SECONDS
    else:
        main_end = total_duration
    main_duration = main_end - main_start

    if main_duration <= 0:
        print("[FATAL] Main content duration is <= 0. Check ACTUAL_START_SECONDS and CUT_FROM_END_SECONDS.")
        sys.exit(1)

    print(f"Main content  : {main_start:.3f}s → {main_end:.3f}s ({main_duration:.3f}s)")

    # ─ Validate filler length ─────────────────────────────────────
    needed_filler = 4 * beat_duration
    if ACTUAL_START_SECONDS < needed_filler:
        print(f"[WARNING] Filler portion ({ACTUAL_START_SECONDS:.3f}s) is shorter than 4 beats ({needed_filler:.3f}s).")
        print("          Segments may overlap or all start at 0s.")

    # ─ Pick 4 random 1-beat segment starts ────────────────────────
    random.seed(RANDOM_SEED)
    max_start = max(0.0, ACTUAL_START_SECONDS - beat_duration)
    segment_starts = []
    for i in range(4):
        if max_start > 0:
            start = random.uniform(0, max_start)
        else:
            start = 0.0
        segment_starts.append(start)
    segment_starts.sort()  # chronological order for the final video

    print(f"Filler cutaways (each {beat_duration:.3f}s, chronological):")
    for i, s in enumerate(segment_starts):
        print(f"  Segment {i+1}: {s:.3f}s → {s + beat_duration:.3f}s")

    # ─ Create temp workspace ──────────────────────────────────────
    tmpdir = tempfile.mkdtemp(prefix="scene2_")
    print(f"Temp dir      : {tmpdir}")

    try:
        # ─ Extract filler segments (scale to output res so concat is clean) ─
        segment_files = []
        for i, start in enumerate(segment_starts):
            outpath = os.path.join(tmpdir, f"segment_{i:02d}.mp4")
            cmd = [
                "ffmpeg", "-y",
                "-noautorotate",
                "-ss", str(start),
                "-t", str(beat_duration),
                "-i", INPUT_VIDEO,
                "-vf", f"{transpose_filter}scale={ow}:{oh}:force_original_aspect_ratio=decrease,pad={ow}:{oh}:(ow-iw)/2:(oh-ih)/2",
                "-r", str(FPS),
                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                "-an",
                "-pix_fmt", "yuv420p",
                outpath,
            ]
            run(cmd)
            segment_files.append(outpath)

        # ─ Process main content: trim + chroma key + photo overlay ──
        main_processed = os.path.join(tmpdir, "main_processed.mp4")

        # Filtergraph breakdown:
        #   [0:v] video → scale to output res, pad, trim, colorkey → [keyed]
        #   [1:v] photo → scale to fill full height (oh), pad/crop to output res → [photo]
        #   [photo][keyed] overlay at (0,0) because both are exactly ow×oh
        #
        # Photo fills the full canvas height; width is proportional.
        # If the photo is wider than ow, sides are cropped by pad.
        # If narrower, black bars appear on the sides.

        video_branch = (
            f"[0:v]{transpose_filter}scale={ow}:{oh}:force_original_aspect_ratio=decrease,"
            f"pad={ow}:{oh}:(ow-iw)/2:(oh-ih)/2,"
            f"trim=start={main_start}:end={main_end},setpts=PTS-STARTPTS,"
            f"colorkey={CHROMA_KEY_COLOR}:{CHROMA_SIMILARITY}:{CHROMA_BLEND}[keyed]"
        )

        # Scale photo to full height, rotate 180° (upside-down fix),
        # then crop/pad to exact output resolution.
        photo_branch = (
            f"scale=iw*{oh}/ih:{oh}," #[1:v]transpose=1,transpose=1,
            f"crop=min(iw\,{ow}):min(ih\,{oh}):(iw-min(iw\,{ow}))/2:(ih-min(ih\,{oh}))/2,"
            f"pad={ow}:{oh}:(ow-iw)/2:(oh-ih)/2[photo]"
        )

        overlay = "[photo][keyed]overlay=0:0:format=auto"

        filtergraph = f"{video_branch};{photo_branch};{overlay}"

        cmd = [
            "ffmpeg", "-y",
            "-noautorotate",
            "-i", INPUT_VIDEO,
            "-i", INPUT_PHOTO,
            "-filter_complex", filtergraph,
            "-r", str(FPS),
            "-c:v", "libx264", "-preset", "slow", "-crf", "18",
            "-an",
            "-pix_fmt", "yuv420p",
            main_processed,
        ]
        run(cmd)

        # ─ Build concat list ──────────────────────────────────────
        concat_list = os.path.join(tmpdir, "concat_list.txt")
        with open(concat_list, "w") as f:
            for seg in segment_files:
                abs_path = os.path.abspath(seg).replace(os.sep, "/")
                f.write(f"file '{abs_path}'\n")
            abs_main = os.path.abspath(main_processed).replace(os.sep, "/")
            f.write(f"file '{abs_main}'\n")

    # ─ Ensure output directory exists ─────────────────────────
        output_video = resolve_path(OUTPUT_VIDEO)
        out_dir = os.path.dirname(os.path.abspath(output_video))
        if out_dir and not os.path.exists(out_dir):
            os.makedirs(out_dir)

        # ─ Concatenate all parts ──────────────────────────────────
        # -noautorotate prevents any rotation metadata in intermediates
        # from being re-applied. -vf ensures exact output resolution.
        cmd = [
            "ffmpeg", "-y",
            "-noautorotate",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_list,
            "-vf", f"scale={ow}:{oh}:force_original_aspect_ratio=decrease,pad={ow}:{oh}:(ow-iw)/2:(oh-ih)/2",
            "-r", str(FPS),
            "-c:v", "libx264", "-preset", "slow", "-crf", "18",
            "-pix_fmt", "yuv420p",
            output_video,
        ]
        run(cmd)

        # ─ Summary ────────────────────────────────────────────────
        final_duration = 4 * beat_duration + main_duration
        print(f"\n{'=' * 60}")
        print(f"[SUCCESS] Scene 2 rendered to:")
        print(f"  {output_video}")
        print(f"")
        print(f"Duration breakdown:")
        print(f"  4 filler cutaways : {4 * beat_duration:.3f}s")
        print(f"  Main content      : {main_duration:.3f}s")
        print(f"  Total             : {final_duration:.3f}s")
        print(f"{'=' * 60}")

    finally:
        if KEEP_TEMP:
            print(f"[DEBUG] Keeping temp dir: {tmpdir}")
        else:
            print(f"Cleaning up temp dir: {tmpdir}")
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main()
