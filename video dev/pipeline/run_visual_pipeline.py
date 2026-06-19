from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from common import DEFAULT_CONFIG, ROOT, ensure_parent, load_config, resolve_repo_path


STAGES = [
    "stage_01_intro_outro_export.py",
    "stage_02_scene1_setup_builder.py",
    "stage_03_scene2_builder.py",
    "stage_04_dither_pass.py",
    "stage_05_scene3_bg_builder.py",
    "stage_06_compositor.py",
]


def run_stage(stage_script: str, config_path: Path, profile: str) -> None:
    cmd = [sys.executable, str(ROOT / "pipeline" / stage_script), "--config", str(config_path), "--profile", profile]
    print(f"[RUN] {' '.join(cmd)}")
    completed = subprocess.run(cmd, cwd=ROOT)
    if completed.returncode != 0:
        raise RuntimeError(f"Stage failed: {stage_script}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run full visual pipeline stages.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--profile", default="final", choices=["preview", "final"])
    parser.add_argument("--from-stage", default=None, help="Run starting from this stage filename.")
    args = parser.parse_args()

    config_path = resolve_repo_path(args.config)
    config = load_config(str(config_path))
    export_root = resolve_repo_path(config["paths"]["export_root"])
    runs_root = resolve_repo_path(config["paths"]["runs_root"])
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = runs_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    stages = STAGES
    if args.from_stage:
        if args.from_stage not in STAGES:
            raise KeyError(f"--from-stage must be one of: {', '.join(STAGES)}")
        stages = STAGES[STAGES.index(args.from_stage) :]

    for stage in stages:
        run_stage(stage, config_path, args.profile)

    manifest = {
        "run_id": run_id,
        "profile": args.profile,
        "config_path": str(config_path),
        "stages": stages,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    manifest_path = run_dir / "manifest.json"
    ensure_parent(manifest_path)
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    latest = export_root / "latest_run_manifest.json"
    with latest.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(f"[DONE] Pipeline run complete. Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
