#!/usr/bin/env python3
"""
scene2_processor.py
===================
Config-driven Scene 2 processor for the vertical visual pipeline.

Workflow:
1) Extract 4 random 1-beat filler cutaways from [0, actual_start_seconds)
2) Trim main content from actual_start_seconds to (duration - cut_from_end_seconds)
3) Chroma-key green screen and composite over configured background photo
4) Optional foreground-only dithering branch
5) Concatenate filler cutaways + processed main into output video
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = SCRIPT_DIR / "pipeline" / "config" / "visual_pipeline.json"


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def resolve_repo_path(path_value: str) -> Path:
    path = Path(path_value)
    return (SCRIPT_DIR / path).resolve() if not path.is_absolute() else path.resolve()


def run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    print(f"[CMD] {' '.join(cmd)}")
    completed = subprocess.run(cmd, capture_output=True, text=True, **kwargs)
    if completed.returncode != 0:
        if completed.stdout:
            print(completed.stdout)
        if completed.stderr:
            print(completed.stderr, file=sys.stderr)
        raise RuntimeError(f"Command failed ({completed.returncode}): {' '.join(cmd)}")
    return completed


def get_video_duration(path: Path) -> float:
    result = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
    )
    return float(result.stdout.strip())


def get_video_info(path: Path) -> tuple[int, int, int]:
    result_wh = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
    )
    lines = [ln for ln in result_wh.stdout.splitlines() if ln.strip()]
    if len(lines) < 2:
        raise RuntimeError(f"Unexpected ffprobe resolution output: {result_wh.stdout!r}")
    w, h = int(lines[0].strip()), int(lines[1].strip())

    result_rot = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream_side_data_list",
            "-of",
            "default=noprint_wrappers=1",
            str(path),
        ]
    )
    rotation = 0
    for line in result_rot.stdout.splitlines():
        line = line.strip()
        if line.startswith("rotation="):
            try:
                rotation = int(line.split("=", 1)[1])
            except ValueError:
                rotation = 0
            break
    return w, h, rotation


def get_transpose_for_rotation(rotation: int) -> tuple[str, int]:
    rot = rotation % 360
    if rot == 270:
        return "transpose=1,", 270
    if rot == 90:
        return "transpose=2,", 90
    if rot == 180:
        return "transpose=1,transpose=1,", 180
    return "", 0


def shared_raw_dither_filter(width: int, height: int, factor: int, threshold: int) -> str:
    low_w = max(1, width // max(1, factor))
    low_h = max(1, height // max(1, factor))
    return (
        f"scale={low_w}:{low_h}:flags=neighbor,"
        f"scale={width}:{height}:flags=neighbor,"
        f"format=gray,lut=y='if(lt(val,{threshold}),0,255)'"
    )


def alpha_preserving_dither_filtergraph(input_label: str, output_label: str, width: int, height: int, factor: int, threshold: int) -> str:
    low_w = max(1, width // max(1, factor))
    low_h = max(1, height // max(1, factor))
    return (
        f"[{input_label}]format=rgba,split=2[fg_color][fg_alpha_src];"
        f"[fg_alpha_src]alphaextract[fg_alpha];"
        f"[fg_color]scale={low_w}:{low_h}:flags=neighbor,"
        f"scale={width}:{height}:flags=neighbor,"
        f"format=gray,lut=y='if(lt(val,{threshold}),0,255)',format=rgb24[fg_bw];"
        f"[fg_bw][fg_alpha]alphamerge[{output_label}]"
    )


def build_from_config(config: dict[str, Any], profile: str) -> dict[str, Any]:
    global_cfg = config["global"]
    scene2_cfg = config["scene2"]
    assets_cfg = config["assets"]["scene2"]
    paths_cfg = config["paths"]
    ffmpeg_profile = config["profiles"][profile]["ffmpeg"]
    dither_cfg = config.get("dither", {})

    input_video = resolve_repo_path(assets_cfg["input_video"])
    input_photo = resolve_repo_path(assets_cfg["input_photo"])
    output_video = resolve_repo_path(paths_cfg["scene2_output"])
    output_video.parent.mkdir(parents=True, exist_ok=True)

    bpm = float(global_cfg["bpm"])
    fps = float(global_cfg["fps"])
    ow = int(global_cfg["resolution"]["width"])
    oh = int(global_cfg["resolution"]["height"])
    actual_start_seconds = float(scene2_cfg["timing"]["actual_start_seconds"])
    cut_from_end_seconds = float(scene2_cfg["timing"]["cut_from_end_seconds"])
    chroma_key_color = str(scene2_cfg["chroma"]["key_color"])
    chroma_similarity = float(scene2_cfg["chroma"]["similarity"])
    chroma_blend = float(scene2_cfg["chroma"]["blend"])
    random_seed = int(global_cfg["random_seed"])
    keep_temp = bool(scene2_cfg.get("keep_temp", False))
    preset = str(ffmpeg_profile["preset"])
    crf = int(ffmpeg_profile["crf"])
    pix_fmt = str(ffmpeg_profile["pix_fmt"])
    dither_factor = int(dither_cfg.get("pixelation_factor", 10))
    dither_threshold = int(dither_cfg.get("threshold", 128))

    for dep in ["ffmpeg", "ffprobe"]:
        if shutil.which(dep) is None:
            raise RuntimeError(f"'{dep}' is required on PATH")
    if not input_video.exists():
        raise FileNotFoundError(f"Missing input video: {input_video}")
    if not input_photo.exists():
        raise FileNotFoundError(f"Missing input photo: {input_photo}")

    beat_duration = 60.0 / bpm
    beat_frames = int(fps * beat_duration)
    total_duration = get_video_duration(input_video)
    v_w, v_h, rotation = get_video_info(input_video)

    transpose_filter, normalized_rotation = get_transpose_for_rotation(rotation)
    effective_w, effective_h = (v_h, v_w) if normalized_rotation in (90, 270) else (v_w, v_h)
    if (effective_w, effective_h) != (ow, oh):
        raise RuntimeError(
            f"Input effective size {effective_w}x{effective_h} does not match configured {ow}x{oh} "
            f"(raw={v_w}x{v_h}, rotation={rotation})"
        )

    main_start = actual_start_seconds
    main_end = total_duration - cut_from_end_seconds if cut_from_end_seconds > 0 else total_duration
    main_duration = main_end - main_start
    if main_duration <= 0:
        raise RuntimeError("Main content duration <= 0. Check start/cut settings.")

    random.seed(random_seed)
    max_start = max(0.0, actual_start_seconds - beat_duration)
    segment_starts: list[float] = []
    for _ in range(4):
        segment_starts.append(random.uniform(0, max_start) if max_start > 0 else 0.0)
    segment_starts.sort()

    tmpdir = Path(tempfile.mkdtemp(prefix="scene2_"))
    try:
        segment_files: list[Path] = []
        cutaway_dither_filter = shared_raw_dither_filter(ow, oh, dither_factor, dither_threshold)
        for i, start in enumerate(segment_starts):
            outpath = tmpdir / f"segment_{i:02d}.mp4"
            run(
                [
                    "ffmpeg",
                    "-y",
                    "-display_rotation",
                    "0",
                    "-noautorotate",
                    "-ss",
                    str(start),
                    "-t",
                    str(beat_duration),
                    "-i",
                    str(input_video),
                    "-vf",
                    f"{transpose_filter}scale={ow}:{oh}:force_original_aspect_ratio=decrease,pad={ow}:{oh}:(ow-iw)/2:(oh-ih)/2,{cutaway_dither_filter}",
                    "-r",
                    str(fps),
                    "-c:v",
                    "libx264",
                    "-preset",
                    preset,
                    "-crf",
                    str(crf),
                    "-an",
                    "-pix_fmt",
                    pix_fmt,
                    "-map_metadata",
                    "-1",
                    "-metadata:s:v:0",
                    "rotate=0",
                    str(outpath),
                ]
            )
            segment_files.append(outpath)

        keyed_main = tmpdir / "main_keyed.mp4"
        video_branch = (
            f"[0:v]{transpose_filter}scale={ow}:{oh}:force_original_aspect_ratio=decrease,"
            f"pad={ow}:{oh}:(ow-iw)/2:(oh-ih)/2,"
            f"trim=start={main_start}:end={main_end},setpts=PTS-STARTPTS,"
            f"colorkey={chroma_key_color}:{chroma_similarity}:{chroma_blend}[fg]"
        )
        photo_branch = (
            f"[1:v]scale=iw*{oh}/ih:{oh},"
            f"crop=min(iw\\,{ow}):min(ih\\,{oh}):(iw-min(iw\\,{ow}))/2:(ih-min(ih\\,{oh}))/2,"
            f"pad={ow}:{oh}:(ow-iw)/2:(oh-ih)/2[photo]"
        )
        fg_dither_branch = alpha_preserving_dither_filtergraph("fg", "fgd", ow, oh, dither_factor, dither_threshold)
        overlay = "[photo][fgd]overlay=0:0:format=auto"
        filtergraph = f"{video_branch};{photo_branch};{fg_dither_branch};{overlay}"
        run(
            [
                "ffmpeg",
                "-y",
                    "-display_rotation",
                    "0",
                "-noautorotate",
                "-i",
                str(input_video),
                "-i",
                str(input_photo),
                "-filter_complex",
                filtergraph,
                "-r",
                str(fps),
                "-c:v",
                "libx264",
                "-preset",
                preset,
                "-crf",
                str(crf),
                "-an",
                "-pix_fmt",
                pix_fmt,
                "-map_metadata",
                "-1",
                "-metadata:s:v:0",
                "rotate=0",
                str(keyed_main),
            ]
        )

        main_processed = keyed_main

        concat_list = tmpdir / "concat_list.txt"
        with concat_list.open("w", encoding="utf-8") as f:
            for seg in segment_files:
                f.write(f"file '{seg.as_posix()}'\n")
            f.write(f"file '{main_processed.as_posix()}'\n")

        run(
            [
                "ffmpeg",
                "-y",
                "-noautorotate",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_list),
                "-vf",
                f"scale={ow}:{oh}:force_original_aspect_ratio=decrease,pad={ow}:{oh}:(ow-iw)/2:(oh-ih)/2",
                "-r",
                str(fps),
                "-c:v",
                "libx264",
                "-preset",
                preset,
                "-crf",
                str(crf),
                "-pix_fmt",
                pix_fmt,
                "-map_metadata",
                "-1",
                "-metadata:s:v:0",
                "rotate=0",
                str(output_video),
            ]
        )

        return {
            "output_video": str(output_video),
            "profile": profile,
            "bpm": bpm,
            "fps": fps,
            "beat_duration": beat_duration,
            "beat_frames": beat_frames,
            "segment_starts": segment_starts,
            "main_start": main_start,
            "main_end": main_end,
            "main_duration": main_duration,
            "final_duration": 4 * beat_duration + main_duration,
            "resolution": [ow, oh],
            "rotation": rotation,
            "dither_scene2_foreground": bool(dither_cfg.get("targets", {}).get("scene2_foreground", False)),
        }
    finally:
        if keep_temp:
            print(f"[DEBUG] Keeping temp dir: {tmpdir}")
        else:
            shutil.rmtree(tmpdir, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Scene 2 from unified pipeline config.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--profile", default="final", choices=["preview", "final"])
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    config = load_json(config_path)
    summary = build_from_config(config, args.profile)
    print("=" * 60)
    print("[SUCCESS] Scene 2 complete")
    print(f"Output: {summary['output_video']}")
    print(f"Duration: {summary['final_duration']:.3f}s")
    print(f"Cutaways: {summary['segment_starts']}")
    print("=" * 60)


if __name__ == "__main__":
    main()