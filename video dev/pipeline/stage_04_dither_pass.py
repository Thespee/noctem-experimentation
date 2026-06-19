from __future__ import annotations

import argparse
from pathlib import Path

from common import StageResult, ensure_parent, load_config, profile_ffmpeg, resolve_repo_path, run_cmd


def dither_still(input_path: Path, output_path: Path, width: int, height: int, factor: int, threshold: int) -> None:
    low_w = max(1, width // max(1, factor))
    low_h = max(1, height // max(1, factor))
    dither_filter = (
        f"scale={low_w}:{low_h}:flags=neighbor,"
        f"scale={width}:{height}:flags=neighbor,"
        f"format=gray,lut=y='if(lt(val,{threshold}),0,255)'"
    )
    ensure_parent(output_path)
    run_cmd(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(input_path),
            "-vf",
            dither_filter,
            "-frames:v",
            "1",
            str(output_path),
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 04: run dither pass for configured targets.")
    parser.add_argument("--config", default=None)
    parser.add_argument("--profile", default="final")
    args = parser.parse_args()

    config = load_config(args.config)
    ffmpeg_profile = profile_ffmpeg(config, args.profile)
    dither_cfg = config["dither"]
    export_root = resolve_repo_path(config["paths"]["export_root"])
    width = int(config["global"]["resolution"]["width"])
    height = int(config["global"]["resolution"]["height"])
    factor = int(dither_cfg.get("pixelation_factor", 10))
    threshold = int(dither_cfg.get("threshold", 128))

    scene2_input_video = resolve_repo_path(config["assets"]["scene2"]["input_video"])
    scene0_still = resolve_repo_path(config["paths"]["scene0_background_still"])

    if dither_cfg["targets"].get("scene0_background", False):
        raw_still = export_root / "scene0_bg_raw.png"
        run_cmd(["ffmpeg", "-y", "-i", str(scene2_input_video), "-frames:v", "1", str(raw_still)])
        dither_still(raw_still, scene0_still, width, height, factor, threshold)

    # Scene 2 foreground dithering is currently handled inside scene2_processor.py optional path.
    # This stage intentionally keeps a narrow responsibility around shared dither assets.

    result = StageResult(
        stage="stage_04_dither_pass",
        outputs={"scene0_background_still": str(scene0_still)},
        metadata={
            "profile": args.profile,
            "algorithm": dither_cfg.get("algorithm"),
            "palette": dither_cfg.get("palette"),
            "ffmpeg_profile": ffmpeg_profile,
        },
    )
    result.write(export_root / "stage_04_result.json")


if __name__ == "__main__":
    main()
