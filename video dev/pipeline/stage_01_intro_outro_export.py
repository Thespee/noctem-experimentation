from __future__ import annotations

import argparse
from pathlib import Path

from common import ROOT, StageResult, load_config, profile_ffmpeg, resolve_repo_path, run_cmd


def scene1_duration_frames(config: dict) -> int:
    processing_scene1 = config["processing"]["scene1"]
    words = processing_scene1["words"]
    word_beats = int(processing_scene1["word_beats"])
    cadence = [int(x) for x in config["global"].get("half_beat_cadence_frames", [7, 8])]
    total_half_beats = len(words) * word_beats * 2
    return sum(cadence[i % len(cadence)] for i in range(total_half_beats))


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 01: run/validate Processing export assets.")
    parser.add_argument("--config", default=None)
    parser.add_argument("--profile", default="final")
    args = parser.parse_args()

    config = load_config(args.config)
    ffmpeg_profile = profile_ffmpeg(config, args.profile)
    processing_cfg = config["processing"]
    export_cfg = processing_cfg["export"]
    processing_cli = config["pipeline"]["processing_cli"]
    global_cfg = config["global"]
    width = int(global_cfg["resolution"]["width"])
    height = int(global_cfg["resolution"]["height"])
    export_root = resolve_repo_path(config["paths"]["export_root"])

    intro_dir = export_root / export_cfg["intro_dir"]
    outro_dir = export_root / export_cfg["outro_dir"]
    scene1_text_dir = export_root / export_cfg["scene1_text_dir"]
    scene3_text_dir = export_root / export_cfg["scene3_text_dir"]
    scene0_overlay_output = resolve_repo_path(config["paths"]["scene0_overlay_output"])
    scene3_overlay_output = resolve_repo_path(config["paths"]["scene3_overlay_output"])
    scene1_segments_dir = resolve_repo_path(config["paths"]["scene1_text_segments_dir"])
    scene1_segments_dir.mkdir(parents=True, exist_ok=True)

    for d in [intro_dir, outro_dir, scene1_text_dir, scene3_text_dir]:
        d.mkdir(parents=True, exist_ok=True)

    if processing_cli.get("enabled", False):
        cmd = [
            processing_cli.get("command", "processing-java"),
            "--sketch",
            str(resolve_repo_path(processing_cli["sketch_path"])),
            *processing_cli.get("run_args", ["--run"]),
        ]
        run_cmd(cmd, cwd=ROOT)
    else:
        print("[INFO] processing_cli.enabled=false; skipping Processing CLI invocation.")
        print("[INFO] Run the Processing sketch manually in export mode before composition.")
    fps = float(global_cfg["fps"])
    bpm = float(global_cfg["bpm"])
    scene0_frames = int(round(4.0 * fps * 60.0 / bpm))
    intro_pattern = str(intro_dir / "%04d.png")
    outro_pattern = str(outro_dir / "%04d.png")

    run_cmd(
        [
            "ffmpeg",
            "-y",
            "-framerate",
            str(fps),
            "-start_number",
            "0",
            "-i",
            intro_pattern,
            "-frames:v",
            str(scene0_frames),
            "-vf",
            f"scale={width}:{height}",
            "-c:v",
            "libx264",
            "-preset",
            ffmpeg_profile["preset"],
            "-crf",
            str(ffmpeg_profile["crf"]),
            "-pix_fmt",
            ffmpeg_profile["pix_fmt"],
            str(scene0_overlay_output),
        ]
    )

    cadence = [int(x) for x in global_cfg.get("half_beat_cadence_frames", [7, 8])]
    processing_scene1 = processing_cfg["scene1"]
    scene1_words = processing_scene1["words"]
    word_beats = int(processing_scene1["word_beats"])
    half_beats_per_word = word_beats * 2
    scene1_start = scene0_frames
    for i, _word in enumerate(scene1_words):
        start_half_beat = i * half_beats_per_word
        end_half_beat = (i + 1) * half_beats_per_word
        seg_frames = sum(cadence[j % len(cadence)] for j in range(start_half_beat, end_half_beat))
        start_num = scene1_start + sum(cadence[j % len(cadence)] for j in range(start_half_beat))
        seg_out = scene1_segments_dir / f"seg_{i + 1:02d}.mp4"
        run_cmd(
            [
                "ffmpeg",
                "-y",
                "-framerate",
                str(fps),
                "-start_number",
                str(start_num),
                "-i",
                intro_pattern,
                "-frames:v",
                str(seg_frames),
                "-vf",
                f"scale={width}:{height}",
                "-c:v",
                "libx264",
                "-preset",
                ffmpeg_profile["preset"],
                "-crf",
                str(ffmpeg_profile["crf"]),
                "-pix_fmt",
                ffmpeg_profile["pix_fmt"],
                str(seg_out),
            ]
        )

    run_cmd(
        [
            "ffmpeg",
            "-y",
            "-framerate",
            str(fps),
            "-start_number",
            "0",
            "-i",
            outro_pattern,
            "-vf",
            f"scale={width}:{height}",
            "-c:v",
            "qtrle",
            "-pix_fmt",
            "argb",
            str(scene3_overlay_output),
        ]
    )

    result = StageResult(
        stage="stage_01_intro_outro_export",
        outputs={
            "intro_dir": str(intro_dir),
            "outro_dir": str(outro_dir),
            "scene1_text_dir": str(scene1_text_dir),
            "scene3_text_dir": str(scene3_text_dir),
            "scene0_overlay_output": str(scene0_overlay_output),
            "scene3_overlay_output": str(scene3_overlay_output),
            "scene1_text_segments_dir": str(scene1_segments_dir),
        },
        metadata={
            "profile": args.profile,
            "scene0_frames": scene0_frames,
            "scene1_duration_frames": scene1_duration_frames(config),
        },
    )
    result.write(export_root / "stage_01_result.json")


if __name__ == "__main__":
    main()
