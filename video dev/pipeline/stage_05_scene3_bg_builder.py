from __future__ import annotations

import argparse
import random
from pathlib import Path

from common import StageResult, beats_to_seconds, ensure_parent, load_config, profile_ffmpeg, resolve_repo_path, run_cmd


def media_duration_seconds(path: Path) -> float:
    import subprocess
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to probe duration for {path}")
    return float(result.stdout.strip())


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 05: build Scene 3 background timeline.")
    parser.add_argument("--config", default=None)
    parser.add_argument("--profile", default="final")
    args = parser.parse_args()

    config = load_config(args.config)
    ffmpeg_profile = profile_ffmpeg(config, args.profile)
    global_cfg = config["global"]
    scene3_cfg = config["pipeline"]["scene3"]
    beats_per_background = int(scene3_cfg["beats_per_background"])
    black_tail_beats = int(scene3_cfg["black_tail_beats"])
    fps = float(global_cfg["fps"])
    bpm = float(global_cfg["bpm"])
    width = int(global_cfg["resolution"]["width"])
    height = int(global_cfg["resolution"]["height"])
    export_root = resolve_repo_path(config["paths"]["export_root"])
    output = resolve_repo_path(config["paths"]["scene3_bg_output"])
    temp_dir = export_root / "scene3_bg_parts"
    temp_dir.mkdir(parents=True, exist_ok=True)

    segment_duration = beats_to_seconds(beats_per_background, bpm)
    black_duration = beats_to_seconds(black_tail_beats, bpm)

    part_files: list[Path] = []
    scene3_assets_cfg = config["assets"]["scene3"]
    seed = int(config["global"].get("random_seed", 42069))
    random.seed(seed)
    bg_videos: list[Path]
    source_dir_value = scene3_assets_cfg.get("background_source_dir")
    if source_dir_value:
        source_dir = resolve_repo_path(source_dir_value)
        candidates = [
            p for p in source_dir.glob("*")
            if p.is_file() and p.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm", ".m4v"}
        ]
        if len(candidates) < 3:
            raise RuntimeError(f"Need at least 3 videos in {source_dir}, found {len(candidates)}")
        bg_videos = random.sample(candidates, 3)
    else:
        bg_videos = [resolve_repo_path(p) for p in scene3_assets_cfg["background_videos"]]

    selected_sections: list[dict] = []
    for idx, path in enumerate(bg_videos):
        out_part = temp_dir / f"scene3_bg_{idx + 1:02d}.mp4"
        dur = media_duration_seconds(path)
        max_start = max(0.0, dur - segment_duration)
        start = random.uniform(0.0, max_start) if max_start > 0 else 0.0
        run_cmd(
            [
                "ffmpeg",
                "-y",
                "-ss",
                str(start),
                "-i",
                str(path),
                "-t",
                str(segment_duration),
                "-vf",
                f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}",
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
                str(out_part),
            ]
        )
        selected_sections.append(
            {"file": str(path), "start_seconds": start, "duration_seconds": segment_duration}
        )
        part_files.append(out_part)

    black_part = temp_dir / "scene3_bg_black.mp4"
    run_cmd(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=black:s={width}x{height}:r={fps}:d={black_duration}",
            "-c:v",
            "libx264",
            "-preset",
            ffmpeg_profile["preset"],
            "-crf",
            str(ffmpeg_profile["crf"]),
            "-pix_fmt",
            ffmpeg_profile["pix_fmt"],
            str(black_part),
        ]
    )
    part_files.append(black_part)

    concat_file = temp_dir / "concat.txt"
    with concat_file.open("w", encoding="utf-8") as f:
        for p in part_files:
            f.write(f"file '{p.as_posix()}'\n")

    ensure_parent(output)
    run_cmd(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-c",
            "copy",
            str(output),
        ]
    )

    result = StageResult(
        stage="stage_05_scene3_bg_builder",
        outputs={"scene3_background": str(output)},
        metadata={
            "profile": args.profile,
            "seed": seed,
            "segment_duration": segment_duration,
            "black_duration": black_duration,
            "selected_sections": selected_sections,
            "parts": [str(p) for p in part_files],
        },
    )
    result.write(export_root / "stage_05_result.json")


if __name__ == "__main__":
    main()
