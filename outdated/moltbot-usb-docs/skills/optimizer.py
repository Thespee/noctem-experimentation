#!/usr/bin/env python3
"""
Moltbot Optimizer (Minimal MVP)
Detects hardware, pulls the best model, writes config for other scripts.

Usage:
    python3 optimizer.py detect  - Show hardware and recommendation
    python3 optimizer.py apply   - Pull best model and save config
"""

import subprocess
import sys
from pathlib import Path

HOME = Path.home()
MODEL_FILE = HOME / ".moltbot-model"  # Simple file with model name

# Tiers: (min_ram_gb, model, tier_name)
TIERS = [
    (32, "qwen2.5:14b-instruct-q4_K_M", "Enhanced (14B)"),
    (16, "qwen2.5:7b-instruct-q4_K_M", "Standard (7B)"),
    (12, "qwen2.5:3b-instruct-q4_K_M", "Basic (3B)"),
    (0,  "qwen2.5:1.5b-instruct-q4_K_M", "Minimal (1.5B)"),
]


def get_ram_gb():
    """Get total RAM in GB."""
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    return round(kb / 1024 / 1024, 1)
    except:
        pass
    return 8  # Assume minimal


def get_gpu_vram():
    """Check for NVIDIA GPU and return VRAM in GB, or None."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            return round(int(result.stdout.strip()) / 1024, 1)
    except:
        pass
    return None


def get_best_model(ram_gb, gpu_vram):
    """Determine best model based on hardware."""
    # GPU overrides RAM-based selection if present
    if gpu_vram and gpu_vram >= 8:
        return "qwen2.5:14b-instruct-q4_K_M", "GPU-Accelerated (14B)"
    elif gpu_vram and gpu_vram >= 4:
        return "qwen2.5:7b-instruct-q4_K_M", "GPU-Accelerated (7B)"
    
    # RAM-based selection
    for min_ram, model, tier_name in TIERS:
        if ram_gb >= min_ram:
            return model, tier_name
    
    return TIERS[-1][1], TIERS[-1][2]  # Fallback to minimal


def detect():
    """Detect hardware and show recommendation."""
    ram = get_ram_gb()
    gpu = get_gpu_vram()
    model, tier = get_best_model(ram, gpu)
    
    print(f"\n=== Hardware Detection ===")
    print(f"RAM:  {ram} GB")
    print(f"GPU:  {f'{gpu} GB VRAM' if gpu else 'None detected'}")
    print(f"\n=== Recommendation ===")
    print(f"Tier:  {tier}")
    print(f"Model: {model}")
    print(f"\nRun 'python3 optimizer.py apply' to install.")
    
    return model, tier


def apply():
    """Pull the best model and save config."""
    ram = get_ram_gb()
    gpu = get_gpu_vram()
    model, tier = get_best_model(ram, gpu)
    
    print(f"\n=== Applying {tier} ===\n")
    
    # Check if already installed
    result = subprocess.run(["ollama", "list"], capture_output=True, text=True)
    if model in result.stdout:
        print(f"✓ Model {model} already installed")
    else:
        print(f"Pulling {model}... (this may take several minutes)")
        subprocess.run(["ollama", "pull", model])
    
    # Write model name to config file
    MODEL_FILE.write_text(model)
    print(f"✓ Saved model config to {MODEL_FILE}")
    
    print(f"\n=== Done ===")
    print(f"Model '{model}' is now the default.")
    print(f"Restart the Signal service to use it: ~/moltbot-start.sh")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    cmd = sys.argv[1].lower()
    
    if cmd == "detect":
        detect()
    elif cmd == "apply":
        apply()
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
