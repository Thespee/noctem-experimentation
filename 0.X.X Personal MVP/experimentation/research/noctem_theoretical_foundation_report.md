# Noctem Theoretical Foundation Report
*Generated: February 11, 2026*
*Version: v0.5 → v1.0 Safety Analysis*

---

## Executive Summary

This report synthesizes academic and technical research relevant to Noctem's evolution from a USB-portable AI assistant to a theoretically safe, self-improving system. It addresses four critical domains: distributed state management, kernel-level security ("Tree Bark"), self-improvement bounds, and resource-efficient inference on consumer hardware.

---

## Section 1: Distributed State - CRDTs vs. Vector Clocks for "Heart" Coherence

### Problem Statement
Noctem operates across async devices (USB flash drive → various hosts). The "heart" (persistent state in SQLite) must remain coherent when the agent migrates between machines without guaranteed network connectivity.

### Analysis

#### Vector Clocks
- **Mechanism**: Multi-dimensional Lamport clocks where each node maintains its own counter, updating on local events and merging on message receipt.
- **Strengths**: Can detect concurrent updates and establish causal ordering. Currently "one of the most efficient CvRDTs considering its payload and associated compare/merge functions."
- **Weaknesses**: 
  - Clocks can grow unbounded as nodes increase
  - Dynamo truncates vector clocks when too large, potentially losing reconciliation ability
  - Limited database support for indexing vector clocks

#### CRDTs (Conflict-free Replicated Data Types)
- **Mechanism**: Data structures designed for concurrent updates without coordination, providing "strong eventual consistency" through commutativity, associativity, and idempotence.
- **Strengths**:
  - No coordination required between replicas
  - Mathematically guaranteed convergence
  - Used by Amazon (shopping cart), TomTom, Redis, Cassandra, Riak
- **Weaknesses**:
  - "Not easy to model data as CRDTs" - requires careful domain modeling
  - Limited to specific data types (counters, sets, registers)
  - Composing CRDTs requires careful semantic design

#### Recommendation for Noctem
**Hybrid Approach**: Use CRDTs for Noctem's operational state (task queues as G-Sets, skill logs as append-only structures) combined with Hybrid Logical Clocks (HLC) for causal ordering of memory/conversation history.

```
Noctem State Architecture:
├── tasks      → OR-Set CRDT (concurrent add/remove)
├── memory     → LWW-Register with HLC timestamps
├── skill_log  → G-Set (append-only, no removal)
├── incidents  → G-Counter + LWW-Map hybrid
└── state      → LWW-Map with vector clock metadata
```

The key insight: "any two nodes that have received the same set of updates will see the same end result." For Noctem's USB-portable model, this means the "heart" can survive machine transitions without data loss.

---

## Section 2: Tree-Bark Security - Mandatory Access Control for Skills

### Problem Statement
Noctem executes skills (shell commands, file operations, Signal messaging) autonomously. Without proper sandboxing, a compromised or malicious skill could escalate privileges, exfiltrate data, or damage the host system.

### Theoretical Framework: Mandatory Access Control (MAC)

MAC is "a security strategy that restricts the ability individual resource owners have to grant or deny access to resource objects." Unlike DAC (Discretionary Access Control), MAC policies are:
- Centrally defined by administrators/developers
- Enforced by the OS/security kernel
- Cannot be altered by end users or processes

Key MAC principles relevant to Noctem:
1. **Security Labels**: Every resource and subject gets a classification label
2. **Clearance Levels**: Access granted only when clearance matches/exceeds classification
3. **Reference Monitor**: Evaluates all access requests against policy
4. **Non-Circumventable**: Enforced at kernel level, not application level

### Implementation: Bubblewrap + seccomp

**Bubblewrap** is a "low-level unprivileged sandboxing tool" that creates isolated environments through:
- Linux namespaces (PID, mount, network, user, cgroup)
- Empty mount namespace with selective bind-mounts
- Optional seccomp filter loading

**seccomp-BPF** provides syscall filtering with "single-digit nanosecond overhead."

Critical considerations from NVIDIA's security guidance for agentic workflows:
- "Many sandbox solutions (macOS Seatbelt, Windows AppContainer, Linux Bubblewrap, Dockerized dev containers) share the host kernel, leaving it exposed"
- "Because agentic tools often execute arbitrary code by design, kernel vulnerabilities can be directly targeted"
- Recommendation: "run agentic tools within a fully virtualized environment isolated from the host kernel"

### Proposed Tiered Approval Model for Noctem Skills

```
Tier 0 (Unrestricted): Read-only operations
  - task_status, memory queries
  - No sandboxing required

Tier 1 (Sandboxed): Low-risk operations  
  - file_ops (read), signal_send
  - Bubblewrap: --ro-bind filesystem, --unshare-net

Tier 2 (Restricted): Medium-risk operations
  - shell (whitelisted commands), web_fetch
  - Bubblewrap + seccomp filter (syscall allowlist)
  - Network access through proxy only

Tier 3 (Approval Required): High-risk operations
  - shell (arbitrary), file_ops (write), code execution
  - Full sandboxing + human-in-the-loop approval
  - Audit logging with signed attestation

Tier 4 (Prohibited): Never executed
  - Kernel module loading, raw network sockets
  - Modification of Noctem core files
```

### Known Vulnerabilities to Address
- **CVE-2017-5226**: TIOCSTI command injection from sandbox escape. Mitigate with `--new-session` flag.
- **Indirect Prompt Injection**: Malicious content in ingested data influencing LLM actions. "84%+ failure rate" for prompt-only guardrails.
- **D-Bus Escalation**: If D-Bus socket is bind-mounted, can execute commands via systemd. Use xdg-dbus-proxy filtering.

---

## Section 3: Self-Improvement Bounds - Preventing Entropy Decay

### The Model Collapse Problem

A 2024 Nature paper established that "indiscriminate use of model-generated content in training causes irreversible defects in the resulting models, in which tails of the original content distribution disappear." This is known as **Model Collapse**.

Key findings:
- **Entropy Decay**: "finite sampling effects cause a monotonic loss of distributional diversity (mode collapse)"
- **Variance Amplification**: "loss of external grounding causes the model's representation of truth to drift as a random walk"
- "Model Autophagy Disorder" - successive generations exhibit "progressively diminishing quality"

### Mathematical Formalization

For recursive self-training with KL divergence objectives:
- Entropy contracts geometrically: the system undergoes "inevitably degenerative dynamics" as training data becomes increasingly self-generated
- "These behaviours are not contingent on architecture but are consequences of distributional learning on finite samples"

### Knowledge Collapse vs. Model Collapse
A distinct phenomenon where "factual accuracy deteriorates while surface fluency persists, creating 'confidently wrong' outputs." Three stages:
1. **Stage A**: Knowledge Preservation
2. **Stage B**: Knowledge Collapse (the "confidently wrong" transition)
3. **Stage C**: Instruction-following Collapse

### Drift Thresholds for Noctem

Based on the research, Noctem must implement **Entropy Reservoir Coupling**:

```python
# Theoretical bounds for self-training
DRIFT_THRESHOLDS = {
    "entropy_floor": 0.7,      # Minimum Shannon entropy vs. baseline
    "diversity_ratio": 0.85,   # Lexical/semantic diversity threshold
    "real_data_mix": 0.3,      # Minimum fraction of human-generated data
    "max_generations": 5,      # Generations before mandatory external data
}
```

**Mitigation Strategies**:
1. **Accumulate vs. Replace**: Mix synthetic with real data, don't fully replace
2. **Entropy Reservoir**: Maintain a frozen corpus of pre-AI human-generated text
3. **Diversity Monitoring**: Track word/concept diversity metrics over training iterations
4. **Domain-Specific Training**: Delays accuracy decay by "15× compared to general synthetic training"
5. **External Grounding**: Regular RAG from curated human sources

### Practical Implementation for Noctem

```
Nightly Fine-Tuning Safeguards:
1. Before training:
   - Compute baseline entropy of current model outputs
   - Verify real_data_mix >= 30%
   
2. During training:
   - Monitor per-batch entropy, halt if < entropy_floor
   - Validate against held-out human-generated test set
   
3. After training:
   - Compare output diversity to pre-training baseline
   - Revert if diversity_ratio < 0.85
   - Log all metrics to reports table for parent oversight
```

---

## Section 4: Resource Efficiency - 4-bit Quantized Inference

### Theoretical Memory Requirements

For a model with P parameters at B bits per parameter:
```
VRAM (GB) ≈ (P × B / 8) × 1.2
           └─ parameters ─┘   └─ 20% overhead for KV cache
```

### Empirical Requirements by Model Size

| Model Size | FP16 VRAM | 4-bit VRAM | Minimum GPU |
|------------|-----------|------------|-------------|
| 1.5B       | ~3 GB     | ~1 GB      | 4GB (RTX 3050) |
| 3B         | ~6 GB     | ~2 GB      | 4GB |
| 7B         | ~14 GB    | ~4-6 GB    | 6-8GB (RTX 4060) |
| 8B         | ~16 GB    | ~5-6 GB    | 8GB |
| 13B        | ~26 GB    | ~8 GB      | 12GB |

### QLoRA for Consumer Hardware Fine-Tuning

QLoRA "introduces innovations to save memory without sacrificing performance":
1. **4-bit NormalFloat (NF4)**: Information-theoretically optimal for normally distributed weights
2. **Double Quantization**: Quantizes the quantization constants themselves
3. **Paged Optimizers**: Manages memory spikes during training

Hardware requirements from research:
- **7B models**: "GPU with 6-8GB memory (like RTX 3060, RTX 4060)"
- A "33B Guanaco can be trained on 24 GB consumer GPUs in less than 12 hours"

### Noctem-Specific Recommendations

Given Noctem's target (1TB USB flash drive on variable hardware):

```yaml
# Recommended configuration for Noctem v1.0
inference:
  primary_model: "qwen2.5:7b-instruct-q4_K_M"  # ~5GB VRAM
  router_model: "qwen2.5:1.5b-instruct-q4_K_M" # ~1GB VRAM
  minimum_vram: 6GB
  fallback: "CPU with 16GB+ RAM (30x slower)"
  
training:
  method: "QLoRA"
  quantization: "4-bit NF4"
  optimizer: "paged_adamw_8bit"
  rank: 16
  alpha: 32
  target_modules: ["q_proj", "v_proj"]
  minimum_vram: 8GB
  
active_lora_adapters:
  max_concurrent: 3  # ~100MB each at rank=16
  hot_swap_latency: "<100ms"
```

### LoRA Skill Adapters for Cross-Architecture Transfer

Research on modular LoRA shows:
- **Dynamic Selection**: "best-suited adapter(s) are selected for each input instance"
- **Cross-LoRA Transfer**: Framework for "transferring a LoRA adapter from a source model to a target model" using SVD decomposition and subspace alignment
- **L-MoE**: Mixture of LoRA Experts with "dynamic skill composition" via gating networks

For Noctem's "skill" concept, each skill domain could be a LoRA adapter:
```
skills/
├── shell_adapter.safetensors      # System administration skills
├── signal_adapter.safetensors     # Messaging/communication
├── code_adapter.safetensors       # Programming assistance
└── research_adapter.safetensors   # Web research/synthesis
```

Benefits:
- Modular updates without full retraining
- Hot-swap capabilities for different task contexts
- Portable adapters (~50-200MB each)

---

## Section 5: State of the Project - Gap Analysis

### Current State (v0.5)
- ✅ SQLite persistence for tasks, memory, skills
- ✅ Signal integration for remote messaging
- ✅ Basic skill system with shell, file_ops, signal_send
- ✅ Two-tier model routing (1.5B quick chat, 7B tasks)
- ⚠️ No sandboxing for skill execution
- ⚠️ No distributed state handling for multi-machine
- ⚠️ No self-improvement safeguards
- ⚠️ Limited parent oversight mechanisms

### Required for v1.0 Safety

| Component | Current | Required | Priority |
|-----------|---------|----------|----------|
| Skill Sandboxing | None | Bubblewrap+seccomp | CRITICAL |
| MAC for Skills | None | Tiered approval model | CRITICAL |
| State Sync | SQLite only | CRDT-based sync | HIGH |
| Entropy Monitoring | None | Pre/post training checks | HIGH |
| Real Data Reservoir | None | Curated human corpus | HIGH |
| LoRA Skill Adapters | None | Modular adapter system | MEDIUM |
| Parent Attestation | Basic reports | Signed audit logs | MEDIUM |
| Drift Detection | None | Diversity metrics | MEDIUM |

### Critical Path to v1.0

1. **Phase 1 (Security Foundation)**
   - Implement Bubblewrap sandboxing for all skills
   - Define and enforce tiered MAC policy
   - Add skill execution audit logging

2. **Phase 2 (State Coherence)**
   - Refactor state.py for CRDT primitives
   - Implement HLC for memory ordering
   - Add conflict resolution for multi-machine scenarios

3. **Phase 3 (Safe Self-Improvement)**
   - Build entropy monitoring infrastructure
   - Create curated real-data reservoir
   - Implement training safeguards and rollback

4. **Phase 4 (Modular Adaptation)**
   - Design LoRA skill adapter architecture
   - Implement hot-swap adapter loading
   - Test cross-hardware portability

---

## Bibliography

### Distributed State & CRDTs
1. Shapiro, M., Preguiça, N., Baquero, C., & Zawirski, M. (2011). "A Comprehensive Study of Convergent and Commutative Replicated Data Types." INRIA Technical Report.
2. ljwagerfield/crdt - "CRDT Tutorial for Beginners" (GitHub). https://github.com/ljwagerfield/crdt
3. Sypytkowski, B. "An Introduction to State-based CRDTs" (2022). https://www.bartoszsypytkowski.com/the-state-of-a-state-based-crdts/
4. Martyanov, D. "CRDT for Data Consistency in Distributed Environment" (Medium, 2017).
5. Wulf, A. "Distributed Clocks and CRDTs" (2021). https://adamwulf.me/2021/05/distributed-clocks-and-crdts/

### Sandboxing & Security
6. containers/bubblewrap - "Low-level unprivileged sandboxing tool" (GitHub). https://github.com/containers/bubblewrap
7. NVIDIA. "Practical Security Guidance for Sandboxing Agentic Workflows" (Feb 2026). https://developer.nvidia.com/blog/practical-security-guidance-for-sandboxing-agentic-workflows/
8. ikangai. "The Complete Guide to Sandboxing Autonomous Agents" (Dec 2025). https://www.ikangai.com/the-complete-guide-to-sandboxing-autonomous-agents/
9. restyler/awesome-sandbox - "Awesome Code Sandboxing for AI" (GitHub).
10. ArchWiki. "Bubblewrap." https://wiki.archlinux.org/title/Bubblewrap

### Model Collapse & Self-Improvement
11. Shumailov, I., et al. (2024). "AI models collapse when trained on recursively generated data." Nature 631, 755–759. https://doi.org/10.1038/s41586-024-07566-y
12. arXiv:2601.05280 - "On the Limits of Self-Improving in LLMs" (Jan 2026). Formalizes entropy decay and variance amplification.
13. arXiv:2509.04796 - "Knowledge Collapse in LLMs: When Fluency Survives but Facts Fail" (Sep 2025).
14. arXiv:2511.05535 - "Future of AI Models: A Computational perspective on Model collapse."
15. arXiv:2503.03150 - "Position: Model Collapse Does Not Mean What You Think."
16. winssolutions.org - "The AI Model Collapse Risk is Not Solved in 2025."

### QLoRA & Efficient Fine-Tuning
17. Dettmers, T., Pagnoni, A., et al. (2023). "QLoRA: Efficient Finetuning of Quantized LLMs." arXiv:2305.14314.
18. arXiv:2509.12229 - "Profiling LoRA/QLoRA Fine-Tuning Efficiency on Consumer GPUs" (Sep 2025).
19. index.dev - "LoRA vs QLoRA: Best AI Model Fine-Tuning Platforms & Tools 2026."
20. Medium/matteo28 - "QLoRA Fine-Tuning with Unsloth: A Complete Guide" (Dec 2025).
21. deepfa.ir - "QLoRA: Fine-Tuning 65-Billion Parameter Models on a Single Consumer GPU."

### LoRA Adapters & Modularity
22. ACL Anthology - "Cross-domains and Multi-tasks LoRA Modules Integration" (COLING 2025).
23. arXiv:2510.17898 - "L-MoE: End-to-End Training of a Lightweight Mixture of LoRA Experts."
24. arXiv:2508.05232 - "Cross-LoRA: A Data-Free LoRA Transfer Framework across Heterogeneous LLMs."
25. emergentmind.com - "LoRA-Based Hypernetworks," "Dynamic LoRA Adapters."
26. IBM Research - "Trans-LoRA: towards data-free Transferable Parameter Efficient Finetuning" (NeurIPS 2024).
27. OpenReview - "LoRA-Mixer: Coordinate Modular LoRA Experts Through Serial Attention Routing."

### Memory Requirements
28. Modal. "How much VRAM do I need for LLM inference?" https://modal.com/blog/how-much-vram-need-inference
29. LocalLLM.in - "Ollama VRAM Requirements: Complete 2026 Guide."
30. LocalLLM.in - "LM Studio VRAM Requirements for Local LLMs" (Oct 2025).
31. bacloud.com - "Guide to GPU Requirements for Running AI Models."

### Mandatory Access Control
32. NIST CSRC. "Mandatory Access Control (MAC)." https://csrc.nist.gov/glossary/term/mandatory_access_control
33. TechTarget. "What is mandatory access control (MAC)?"
34. ScienceDirect. "Mandatory Access Control - an overview."
35. Cornell CS5430. "Mandatory Access Control" lecture notes.

---

*Report prepared for Noctem v1.0 development planning.*
*Co-Authored-By: Warp <agent@warp.dev>*
