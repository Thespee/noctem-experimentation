# Moltbot Skill: Optimizer

## Purpose
Detect hardware capabilities and configure the system for optimal performance. Run once after setup, or when hardware changes (e.g., booting on a different machine).

## When to Run
- After initial setup (`00-MINIMAL-SETUP-GUIDE.md`)
- When booting on new/different hardware
- After hardware upgrades
- User-initiated via `moltbot optimize` or direct script call

## NOT Automatic
This skill does NOT run automatically. User must explicitly trigger it. This ensures:
- No surprise model downloads
- No unexpected resource usage
- User stays in control

---

## Design Overview

### Detection Phase
1. **RAM**: Total and available memory
2. **CPU**: Core count, thread count, AVX/AVX2 support
3. **GPU**: NVIDIA detection, VRAM amount
4. **Disk**: Available space for models
5. **Current models**: What's already pulled in Ollama

### Decision Phase
Based on detected hardware, determine:
1. Best model size (1.5B, 3B, 7B, 13B)
2. Optimal quantization (Q2, Q4, Q8)
3. Thread count for inference
4. Context window size
5. Whether GPU offload is viable

### Configuration Phase
1. Pull recommended model (if not present)
2. Create/update Modelfile with optimal parameters
3. Update `~/.clawdbot/clawdbot.json`
4. Write hardware profile to `~/moltbot-system/config/hardware.json`
5. Report changes to user

---

## Hardware Tiers

### Tier 1: Minimal (8GB RAM, 2 cores, no GPU)
- Model: `qwen2.5:1.5b-instruct-q4_K_M`
- Context: 2048
- Threads: 2
- Expected: 2-8 t/s

### Tier 2: Basic (12GB RAM, 4 cores, no GPU)
- Model: `qwen2.5:3b-instruct-q4_K_M`
- Context: 4096
- Threads: 4
- Expected: 4-10 t/s

### Tier 3: Standard (16GB RAM, 4+ cores, no GPU)
- Model: `qwen2.5:7b-instruct-q4_K_M`
- Context: 8192
- Threads: 6
- Expected: 3-5 t/s

### Tier 4: Enhanced (32GB RAM, 8+ cores, no GPU)
- Model: `qwen2.5:14b-instruct-q4_K_M` or dual 7B
- Context: 16384
- Threads: 8
- Expected: 2-4 t/s (larger model, similar speed)

### Tier 5: GPU-Accelerated (any RAM, NVIDIA GPU)
- Model: Largest that fits in VRAM
- 4GB VRAM → 7B Q4
- 8GB VRAM → 13B Q4
- 12GB+ VRAM → 14B+ or Q8 quantization
- Expected: 15-100+ t/s depending on GPU

---

## Implementation Approach

### File: `~/moltbot-system/skills/optimizer.py`

```
optimizer.py detect     # Show detected hardware, suggest tier
optimizer.py recommend  # Show recommended configuration
optimizer.py apply      # Apply recommended configuration
optimizer.py status     # Show current configuration
optimizer.py benchmark  # Run quick inference benchmark
```

### Core Functions Needed

1. **detect_ram()**
   - Read `/proc/meminfo` or use `psutil`
   - Return total GB, available GB

2. **detect_cpu()**
   - Core count: `nproc` or `/proc/cpuinfo`
   - AVX support: Check CPU flags
   - Return cores, threads, has_avx, has_avx2

3. **detect_gpu()**
   - Check for `nvidia-smi`
   - Parse VRAM amount
   - Return gpu_name, vram_gb, or None

4. **detect_disk_space()**
   - Check space in Ollama model directory
   - Return available GB

5. **get_current_models()**
   - Query `ollama list`
   - Return list of installed models with sizes

6. **calculate_tier(hardware)**
   - Apply tier logic
   - Return tier number and reasoning

7. **get_recommendation(tier, hardware)**
   - Return specific model, parameters, config

8. **apply_configuration(recommendation)**
   - Pull model if needed
   - Write Modelfile
   - Update clawdbot.json
   - Write hardware.json

9. **run_benchmark()**
   - Simple prompt, measure tokens/second
   - Return speed metric

---

## Output Format: hardware.json

```json
{
  "detected_at": "2026-02-08T01:50:00Z",
  "hardware": {
    "ram_total_gb": 16,
    "ram_available_gb": 12,
    "cpu_cores": 4,
    "cpu_threads": 8,
    "cpu_has_avx2": true,
    "gpu": null,
    "disk_available_gb": 200
  },
  "tier": 3,
  "tier_name": "Standard",
  "configuration": {
    "model": "qwen2.5:7b-instruct-q4_K_M",
    "custom_model_name": "qwen-agentic",
    "num_ctx": 8192,
    "num_thread": 6,
    "temperature": 0.7
  },
  "benchmark": {
    "tokens_per_second": 4.2,
    "measured_at": "2026-02-08T01:52:00Z"
  }
}
```

---

## User Interaction Flow

### First Run
```
$ python3 ~/moltbot-system/skills/optimizer.py detect

=== Hardware Detection ===
RAM:     16 GB total, 12 GB available
CPU:     4 cores, 8 threads, AVX2 supported
GPU:     None detected
Disk:    200 GB available

=== Recommendation ===
Tier:    3 (Standard)
Model:   qwen2.5:7b-instruct-q4_K_M
Context: 8192 tokens
Threads: 6
Speed:   ~3-5 tokens/sec expected

Run 'optimizer.py apply' to configure.
```

### Apply
```
$ python3 ~/moltbot-system/skills/optimizer.py apply

Pulling qwen2.5:7b-instruct-q4_K_M... (this may take a while)
[████████████████████████████████] 100%

Creating optimized Modelfile...
Updating clawdbot.json...
Writing hardware profile...

Running benchmark...
Measured: 4.2 tokens/sec

=== Configuration Complete ===
Your system is now optimized for Tier 3 (Standard).
Primary model: qwen-agentic (7B)
Router model: router (1.5B) [unchanged]
```

---

## Integration with Router

After optimization, both models are available:
- **router** (1.5B): Fast, always loaded, handles routing
- **qwen-agentic** (7B or whatever tier): Loaded on demand for complex tasks

The Router skill (separate doc) will dispatch to the appropriate model.

---

## Edge Cases

### Multiple GPUs
- Detect all, use the one with most VRAM
- Future: support multi-GPU

### Laptop with integrated + discrete GPU
- Prefer discrete NVIDIA if present
- Fall back to integrated or CPU

### RAM but no disk space
- Warn user
- Suggest smaller model or cleanup

### Better hardware than any tier
- Cap at highest tier
- Suggest user explore larger models manually

### Worse hardware than Tier 1
- Warn that experience will be degraded
- Suggest cloud-primary mode
- Still install smallest model for basic routing

---

## Future Enhancements

1. **Auto-detect on boot** (optional, user-enabled)
2. **Model caching strategy** for multi-machine use
3. **Power profile detection** (laptop on battery vs plugged in)
4. **Thermal throttling detection**
5. **Network speed detection** for cloud burst decisions

---

## Dependencies

```bash
pip3 install psutil  # For cross-platform hardware detection
```

Or use pure bash/Linux commands for zero dependencies.

---

## Security Notes

- No network access required for detection
- Model pulls go through standard Ollama (HTTPS)
- Hardware profile stored locally only
- No telemetry or external reporting

---

*Run once, run right. Optimize for what you have.*
