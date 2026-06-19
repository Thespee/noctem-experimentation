from __future__ import annotations

import argparse
import sys
from pathlib import Path

from common import ROOT, StageResult, load_config, resolve_repo_path, run_cmd


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 03: build Scene 2 via scene2_processor.py")
    parser.add_argument("--config", default=None)
    parser.add_argument("--profile", default="final")
    args = parser.parse_args()

    config = load_config(args.config)
    scene2_output = resolve_repo_path(config["paths"]["scene2_output"])
    export_root = resolve_repo_path(config["paths"]["export_root"])

    run_cmd(
        [
            sys.executable,
            str(ROOT / "scene2_processor.py"),
            "--config",
            str(resolve_repo_path(args.config) if args.config else (ROOT / "pipeline" / "config" / "visual_pipeline.json")),
            "--profile",
            args.profile,
        ],
        cwd=ROOT,
    )

    result = StageResult(
        stage="stage_03_scene2_builder",
        outputs={"scene2_output": str(scene2_output)},
        metadata={"profile": args.profile},
    )
    result.write(export_root / "stage_03_result.json")


if __name__ == "__main__":
    main()
