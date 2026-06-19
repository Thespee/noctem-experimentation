from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from common import StageResult, ensure_parent, load_config, profile_ffmpeg, resolve_repo_path, run_cmd


def video_duration_seconds(path: Path) -> float:
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
    parser = argparse.ArgumentParser(description="Stage 06: compose final visual timeline.")
    parser.add_argument("--config", default=None)
    parser.add_argument("--profile", default="final")
    args = parser.parse_args()

    config = load_config(args.config)
    ffmpeg_profile = profile_ffmpeg(config, args.profile)
    output = resolve_repo_path(config["paths"]["final_output"])
    export_root = resolve_repo_path(config["paths"]["export_root"])
    fps = float(config["global"]["fps"])
    width = int(config["global"]["resolution"]["width"])
    height = int(config["global"]["resolution"]["height"])

    # Inputs
    scene0_overlay = resolve_repo_path(config["paths"]["scene0_overlay_output"])
    scene0_bg = resolve_repo_path(config["paths"]["scene0_background_still"])
    scene1_setup_dir = export_root / "scene1_setup_dithered"
    scene1_text_segments_dir = resolve_repo_path(config["paths"]["scene1_text_segments_dir"])
    scene2_video = resolve_repo_path(config["paths"]["scene2_output"])
    scene3_bg = resolve_repo_path(config["paths"]["scene3_bg_output"])
    scene3_overlay = resolve_repo_path(config["paths"]["scene3_overlay_output"])
    scene3_composite = resolve_repo_path(config["paths"]["scene3_composite_output"])

    # Scene 0: dithered first frame background + scene0 processing animation overlay.
    scene0_composite = export_root / "scene0_composite.mp4"
    scene0_duration = video_duration_seconds(scene0_overlay) if scene0_overlay.exists() else 2.0
    if scene0_overlay.exists() and scene0_bg.exists():
        run_cmd(
            [
                "ffmpeg",
                "-y",
                "-loop",
                "1",
                "-i",
                str(scene0_bg),
                "-i",
                str(scene0_overlay),
                "-t",
                str(scene0_duration),
                "-filter_complex",
                f"[0:v]scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2[bg];"
                "[1:v]colorkey=0x000000:0.08:0.00[ol];[bg][ol]overlay=0:0:format=auto",
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
                str(scene0_composite),
            ]
        )
    elif scene0_bg.exists():
        run_cmd(
            [
                "ffmpeg",
                "-y",
                "-loop",
                "1",
                "-i",
                str(scene0_bg),
                "-t",
                "2.0",
                "-vf",
                f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
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
                str(scene0_composite),
            ]
        )
    else:
        raise RuntimeError("Missing Scene 0 sources: expected scene0 background still and/or overlay video.")

    # Scene 1: alternate dithered raw setup clips and processing text segments.
    scene1_sequence = export_root / "scene1_sequence.mp4"
    scene1_parts = export_root / "scene1_parts"
    scene1_parts.mkdir(parents=True, exist_ok=True)
    ordered_parts: list[Path] = []
    normalized_parts: list[Path] = []
    for i in range(1, 5):
        setup_clip = scene1_setup_dir / f"setup_{i:02d}.mp4"
        text_clip = scene1_text_segments_dir / f"seg_{i:02d}.mp4"
        if not setup_clip.exists():
            raise RuntimeError(f"Missing Scene 1 setup clip: {setup_clip}")
        if not text_clip.exists():
            raise RuntimeError(f"Missing Scene 1 text segment: {text_clip}")
        ordered_parts.append(setup_clip)
        ordered_parts.append(text_clip)
    for idx, src in enumerate(ordered_parts):
        norm = scene1_parts / f"norm_{idx + 1:02d}.mp4"
        run_cmd(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(src),
                "-vf",
                f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
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
                str(norm),
            ]
        )
        normalized_parts.append(norm)
    scene1_concat = scene1_parts / "concat.txt"
    with scene1_concat.open("w", encoding="utf-8") as f:
        for p in normalized_parts:
            f.write(f"file '{p.as_posix()}'\n")
    run_cmd(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(scene1_concat),
            "-c",
            "copy",
            str(scene1_sequence),
        ]
    )

    # Scene 3: overlay processing flashing text animation over built background timeline.
    if scene3_overlay.exists():
        run_cmd(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(scene3_bg),
                "-i",
                str(scene3_overlay),
                "-filter_complex",
                "[1:v]colorkey=0x000000:0.08:0.00[ol];[0:v][ol]overlay=0:0:format=auto",
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
                str(scene3_composite),
            ]
        )
    else:
        print(f"[WARN] Scene 3 overlay missing: {scene3_overlay}. Using scene3 background only.")
        run_cmd(["ffmpeg", "-y", "-i", str(scene3_bg), "-c", "copy", str(scene3_composite)])

    # Final: Scene0 + Scene1 + Scene2 + Scene3
    ensure_parent(output)
    run_cmd(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(scene0_composite),
            "-i",
            str(scene1_sequence),
            "-i",
            str(scene2_video),
            "-i",
            str(scene3_composite),
            "-filter_complex",
            f"[0:v]scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps},format=yuv420p[v0];"
            f"[1:v]scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps},format=yuv420p[v1];"
            f"[2:v]scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps},format=yuv420p[v2];"
            f"[3:v]scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps},format=yuv420p[v3];"
            "[v0][v1][v2][v3]concat=n=4:v=1:a=0[v]",
            "-map",
            "[v]",
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
            str(output),
        ]
    )

    result = StageResult(
        stage="stage_06_compositor",
        outputs={
            "final_output": str(output),
            "scene0_composite": str(scene0_composite),
            "scene1_sequence": str(scene1_sequence),
            "scene3_composite": str(scene3_composite),
        },
        metadata={"profile": args.profile},
    )
    result.write(export_root / "stage_06_result.json")


if __name__ == "__main__":
    main()