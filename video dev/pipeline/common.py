from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "pipeline" / "config" / "visual_pipeline.json"


def load_config(config_path: str | None = None) -> dict[str, Any]:
    path = Path(config_path).resolve() if config_path else DEFAULT_CONFIG
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def resolve_repo_path(path_value: str | Path) -> Path:
    path = Path(path_value)
    return (ROOT / path).resolve() if not path.is_absolute() else path.resolve()


def profile_ffmpeg(config: dict[str, Any], profile: str) -> dict[str, Any]:
    profiles = config.get("profiles", {})
    if profile not in profiles:
        raise KeyError(f"Unknown profile '{profile}'. Available: {', '.join(sorted(profiles))}")
    return profiles[profile]["ffmpeg"]


def beats_to_seconds(beats: float, bpm: float) -> float:
    return (60.0 / bpm) * beats


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def run_cmd(cmd: list[str], cwd: Path | None = None) -> None:
    print(f"[CMD] {' '.join(cmd)}")
    completed = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if completed.returncode != 0:
        if completed.stdout:
            print(completed.stdout)
        if completed.stderr:
            print(completed.stderr)
        raise RuntimeError(f"Command failed ({completed.returncode}): {' '.join(cmd)}")
    if completed.stdout.strip():
        print(completed.stdout.strip())


@dataclass
class StageResult:
    stage: str
    outputs: dict[str, str]
    metadata: dict[str, Any]

    def write(self, output_path: Path) -> None:
        ensure_parent(output_path)
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(
                {
                    "stage": self.stage,
                    "outputs": self.outputs,
                    "metadata": self.metadata,
                },
                f,
                indent=2,
            )
