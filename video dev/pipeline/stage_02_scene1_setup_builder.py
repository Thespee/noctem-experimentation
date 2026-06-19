from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from common import StageResult, ensure_parent, load_config, profile_ffmpeg, resolve_repo_path, run_cmd


def shared_raw_dither_filter(width: int, height: int, factor: int, threshold: int) -> str:
    low_w = max(1, width // max(1, factor))
    low_h = max(1, height // max(1, factor))
    return (
        f"scale={low_w}:{low_h}:flags=neighbor,"
        f"scale={width}:{height}:flags=neighbor,"
        f"format=gray,lut=y='if(lt(val,{threshold}),0,255)'"
    )


def source_rotation(path: Path) -> int:
    result = subprocess.run(
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
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return 0
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("rotation="):
            try:
                return int(line.split("=", 1)[1])
            except ValueError:
                return 0
    return 0


def transpose_for_rotation(rotation: int) -> str:
    rot = rotation % 360
    if rot == 270:
        return "transpose=1,"
    if rot == 90:
        return "transpose=2,"
    if rot == 180:
        return "transpose=1,transpose=1,"
    return ""

def dither_raw_clip(input_path: Path, output_path: Path, fps: float, ffmpeg_profile: dict, dither_filter: str) -> None:
    ensure_parent(output_path)
    run_cmd(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(input_path),
            "-vf",
            dither_filter,
            "-r",
            str(fps),
            "-c:v",
            "libx264",
            "-preset",
            ffmpeg_profile["preset"],
            "-crf",
            str(ffmpeg_profile["crf"]),
            "-pix_fmt",
            ffmpeg_profile["pix_fmt"],
            str(output_path),
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 02: build Scene 1 setup clips.")
    parser.add_argument("--config", default=None)
    parser.add_argument("--profile", default="final")
    args = parser.parse_args()

    config = load_config(args.config)
    ffmpeg_profile = profile_ffmpeg(config, args.profile)
    global_cfg = config["global"]
    scene1_cfg = config["pipeline"]["scene1"]
    dither_cfg = config["dither"]

    source = resolve_repo_path(config["assets"]["scene1"]["setup_source_video"])
    export_root = resolve_repo_path(config["paths"]["export_root"])
    setup_raw_dir = export_root / "scene1_setup_raw"
    setup_final_dir = export_root / "scene1_setup_dithered"
    setup_raw_dir.mkdir(parents=True, exist_ok=True)
    setup_final_dir.mkdir(parents=True, exist_ok=True)

    fps = float(global_cfg["fps"])
    loops = int(scene1_cfg.get("loops", 4))
    cadence_frames = [int(x) for x in global_cfg.get("half_beat_cadence_frames", [7, 8])]
    if len(cadence_frames) < 2:
        cadence_frames = [7, 8]
    width = int(global_cfg["resolution"]["width"])
    height = int(global_cfg["resolution"]["height"])
    factor = int(config["dither"].get("pixelation_factor", 10))
    threshold = int(config["dither"].get("threshold", 128))
    dither_filter = shared_raw_dither_filter(width, height, factor, threshold)
    transpose_filter = transpose_for_rotation(source_rotation(source))

    raw_outputs: list[Path] = []
    final_outputs: list[Path] = []
    timeline_frame = 0
    for i in range(loops):
        half_beat_frames = cadence_frames[i % len(cadence_frames)]
        half_beat_seconds = half_beat_frames / fps
        raw_out = setup_raw_dir / f"setup_{i + 1:02d}.mp4"
        start = timeline_frame / fps
        run_cmd(
            [
                "ffmpeg",
                "-y",
                "-noautorotate",
                "-i",
                str(source),
                "-ss",
                str(start),
                "-t",
                str(half_beat_seconds),
                "-vf",
                f"{transpose_filter}scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
                "-r",
                str(fps),
                "-c:v",
                "libx264",
                "-preset",
                ffmpeg_profile["preset"],
                "-crf",
                str(ffmpeg_profile["crf"]),
                "-pix_fmt",
                ffmpeg_profile["pix_fmt"],
                "-map_metadata",
                "-1",
                "-metadata:s:v:0",
                "rotate=0",
                str(raw_out),
            ]
        )
        raw_outputs.append(raw_out)

        final_out = setup_final_dir / f"setup_{i + 1:02d}.mp4"
        if dither_cfg["enabled"] and dither_cfg["targets"].get("scene1_setup_clips", False):
            dither_raw_clip(raw_out, final_out, fps, ffmpeg_profile, dither_filter)
        else:
            run_cmd(["ffmpeg", "-y", "-i", str(raw_out), "-c", "copy", str(final_out)])
        final_outputs.append(final_out)
        timeline_frame += half_beat_frames

    result = StageResult(
        stage="stage_02_scene1_setup_builder",
        outputs={
            "setup_raw_dir": str(setup_raw_dir),
            "setup_dithered_dir": str(setup_final_dir),
        },
        metadata={
            "profile": args.profile,
            "loops": loops,
            "cadence_frames": cadence_frames,
            "files": [str(p) for p in final_outputs],
        },
    )
    result.write(export_root / "stage_02_result.json")


if __name__ == "__main__":
    main()
