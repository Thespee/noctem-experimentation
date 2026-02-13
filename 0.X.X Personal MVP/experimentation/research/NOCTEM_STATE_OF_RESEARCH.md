# Noctem: State of Research Synthesis
## Technical Foundations for Distributed AI Agent Identity, Efficiency, and Security

**Document Version:** 1.0  
**Generated:** 2026-02-11  
**Research Period:** 2023-2026

---

## Executive Summary

This synthesis report analyzes 25 academic sources across three critical research verticals relevant to the Noctem project: distributed identity persistence, low-specification AI optimization, and local-first security architectures. The analysis reveals a convergent trend toward **capability-based, content-addressed systems** that enable AI agents to maintain coherent identity across distributed nodes while operating efficiently on resource-constrained hardware.

Key findings:
1. **Merkle-CRDTs** provide the theoretical foundation for solving the "Cor Unum" (One Heart) problem of maintaining unified agent identity across partitioned networks.
2. **Sub-4-bit quantization** with knowledge distillation enables viable deployment of 1.5B parameter models on 8GB RAM systems with acceptable quality degradation.
3. **WebAssembly capability-based sandboxing** offers the strongest isolation guarantees for untrusted AI-generated code with minimal performance overhead (<6%).

---

## 1. The "Cor Unum" Problem: Distributed Identity Through CRDTs

### 1.1 Problem Statement

The Noctem architecture requires that an AI agent maintain a singular, coherent identity ("one heart") even when:
- Operating across multiple physical nodes
- Experiencing network partitions
- Undergoing state migrations between edge and cloud

Traditional distributed consensus mechanisms (Paxos, Raft) sacrifice availability during partitions—unacceptable for an always-on personal AI daemon. The CAP theorem forces a choice, but CRDTs offer an elegant escape.

### 1.2 CRDT Foundations

Conflict-free Replicated Data Types, formalized by Preguiça, Baquero, and Shapiro [2], guarantee **Strong Eventual Consistency (SEC)**: any two replicas that have received the same set of updates will be in identical states, regardless of operation ordering. This is achieved through mathematically-proven merge functions forming join-semilattices.

The 2024 tutorial by Almeida [1] clarifies the operational taxonomy:
- **State-based (CvRDTs):** Propagate full replica state; merge via semilattice join
- **Operation-based (CmRDTs):** Propagate operations; require causal delivery
- **Delta-state:** Hybrid approach propagating only state changes
- **Pure operation-based:** Operations with commutative effects

For Noctem's identity persistence, **delta-state CRDTs** are optimal: they minimize synchronization bandwidth while tolerating unreliable network conditions without requiring strict ordering guarantees.

### 1.3 Merkle-DAG State Synchronization

The critical innovation for Noctem comes from Sanjuán et al.'s Merkle-CRDTs [3], which combine content-addressed Merkle-DAGs with CRDT semantics. Key properties:

1. **Content Addressing:** Each state node is identified by its cryptographic hash (CID), enabling trustless verification
2. **DAG-Syncer Protocol:** Replicas fetch missing nodes by traversing from known roots, automatically discovering divergent state
3. **Merkle-Clock:** Logical clocks embedded in the DAG structure eliminate the need for vector clocks that scale poorly with replica count

The ConflictSync algorithm [4] further optimizes this by framing synchronization as set reconciliation of irredundant join decompositions, achieving bandwidth proportional to actual differences rather than total state size.

### 1.4 Cor Unum Architecture Proposal

Based on the literature, Noctem's identity layer should implement:

```
Agent Identity State = Merkle-CRDT(
  core_beliefs: AWSet<Belief>,           // Add-wins set for agent convictions
  episodic_memory: RGA<Episode>,         // Replicated growable array for experiences
  skill_registry: LWWMap<SkillID, Hash>, // Last-writer-wins for skill bindings
  trust_attestations: ORMap<AgentID, VCredential>  // Observed-remove map for peer trust
)
```

When Noctem instances synchronize:
1. Exchange Merkle root CIDs
2. Traverse differing subtrees to identify divergent state
3. Apply CRDT merge semantics automatically
4. Result: All instances converge to identical identity state without coordination

This architecture directly addresses scenarios where a Noctem instance operates offline (e.g., on a mobile device) then rejoins the network—merges happen automatically without conflict resolution logic.

### 1.5 Decentralized Identifiers for Agent Discovery

Recent work on DIDs for multi-agent systems [6, 7, 8] provides the complementary discovery layer. The Agent Identity URI scheme [8] proposes:

```
agent://acme.org/finance/invoice-approval?version=2.1
```

This capability-addressed identifier enables:
- Topology-independent naming (agents survive migration)
- Capability-based discovery (find agents by what they can do)
- Cryptographically verifiable claims via Verifiable Credentials

The zero-trust IAM framework [6] emphasizes that traditional OAuth/SAML are fundamentally inadequate for multi-agent systems due to their coarse-grained, static permission models. Agent permissions must be:
- Fine-grained (task-specific)
- Context-aware (adjustable based on runtime conditions)
- Ephemeral (revocable without global coordination)

---

## 2. Low-Spec AI Optimization: Running Intelligence on 8GB RAM

### 2.1 The Resource Constraint

Noctem's design philosophy demands operation on consumer hardware without cloud dependencies. With a target of 8GB system RAM, we must accommodate:
- The quantized model weights
- KV-cache for context
- Operating system overhead (~2GB)
- Application code and data structures

This leaves approximately 5-6GB for the model, making 7B parameter models at full precision (14GB FP16) impossible. The solution lies in aggressive quantization and efficient fine-tuning.

### 2.2 Post-Training Quantization Landscape

The literature reveals rapid progress in sub-4-bit quantization:

| Method | Bits | LLaMA-7B PPL | Memory (7B) | Key Innovation |
|--------|------|--------------|-------------|----------------|
| FP16 Baseline | 16 | 5.68 | ~14GB | - |
| GPTQ [13] | 4 | 5.85 | ~3.5GB | Layer-wise OBS optimization |
| AWQ [13] | 4 | 5.78 | ~3.5GB | Activation-aware scaling |
| PTQTP [11] | 1.58 | 6.12 | ~1.4GB | Trit-plane decomposition |
| BiLLM [14] | 1+1 | 8.41 | ~1.8GB | Salient weight preservation |
| W2A4 [14] | 2 | 8.58 | ~2GB | Binary group quantization |

The PTQTP framework [11] is particularly relevant, achieving near-4-bit quality at 1.58 bits through decomposition into ternary planes {-1, 0, 1}. This enables multiplication-free inference suitable for FPGA/ASIC deployment.

### 2.3 1.5B vs 7B Model Tradeoffs

For Noctem's resource envelope, the choice between 1.5B and 7B parameter models involves nuanced tradeoffs:

| Dimension | 1.5B Model | 7B Model (Q4) | Analysis |
|-----------|------------|---------------|----------|
| **Memory (Q4)** | ~0.9GB | ~3.5GB | 1.5B leaves headroom for larger context |
| **Memory (Q2)** | ~0.4GB | ~1.8GB | Both viable at extreme quantization |
| **Inference Speed** | ~50 tok/s | ~15 tok/s | 1.5B enables real-time interaction |
| **MMLU Accuracy** | ~45% | ~58% | 7B significantly stronger on reasoning |
| **Context Length** | 8K viable | 4K practical | KV-cache dominates at long contexts |
| **Fine-tuning** | QLoRA feasible | QLoRA marginal | 1.5B allows local personalization |

The scaling analysis [18] reveals that smaller models can match larger ones on well-defined tasks through fine-tuning, but struggle with open-ended reasoning. For Noctem's use case—a personal daemon with specialized skills—**1.5B with heavy fine-tuning** may outperform **7B general-purpose** models.

### 2.4 Knowledge Distillation Pipeline

The KD-LoRA framework [16] provides the blueprint for efficient specialization:

1. **Teacher Model:** Fine-tune a 7B+ model on target tasks using full resources
2. **Student Initialization:** 1.5B model with LoRA adapters (rank 8-32)
3. **Distillation:** Train student on teacher's soft labels using reverse KLD
4. **Result:** 98% of LoRA performance, 40% smaller, 30% faster inference

MiniLLM [15] introduces on-policy distillation that prevents the student from overestimating low-probability regions of the teacher distribution—critical for maintaining coherent behavior in dialogue.

### 2.5 Recommended Stack for Noctem

Based on the literature analysis:

```
Base Model: Qwen2.5-1.5B or LLaMA-3.2-1B
Quantization: PTQTP 1.58-bit for weights, INT8 for activations
Fine-tuning: QLoRA (rank 16, alpha 32) with KD from 7B teacher
Runtime: llama.cpp with custom WASM bindings
Memory Budget: ~1.5GB model + 2GB KV-cache + 1GB skills
```

This configuration fits comfortably within 8GB while leaving room for skill modules and the CRDT identity layer.

---

## 3. The "Tree Bark" Security Model: WASM Capability Isolation

### 3.1 Threat Model

Noctem's skill system allows dynamic loading of capabilities—effectively untrusted code from potentially adversarial sources. The threats include:
- **Prompt injection:** Malicious inputs causing unintended skill invocation
- **Sandbox escape:** Skills accessing unauthorized system resources
- **Data exfiltration:** Skills leaking sensitive user data
- **Resource exhaustion:** Skills consuming unbounded compute/memory

Traditional container isolation (Docker, VMs) is too heavyweight for per-skill sandboxing. WebAssembly offers a compelling alternative.

### 3.2 WebAssembly Security Foundations

The comprehensive WASM security review [19] identifies the core security properties:

1. **Memory Safety:** Linear memory is bounds-checked; no access outside allocated region
2. **Control Flow Integrity:** Indirect calls validated against type signatures
3. **Capability-Based I/O:** Modules have no intrinsic system access; all I/O via explicit imports
4. **Deterministic Execution:** Same inputs produce same outputs (absent explicit randomness)

The Cage system [21] extends WASM safety using ARM hardware features:
- **Memory Tagging Extension (MTE):** Spatial/temporal memory safety for heap/stack
- **Pointer Authentication (PAC):** Prevents control-flow hijacking
- **Overhead:** <5.8% runtime, <3.7% memory

### 3.3 Capability-Based Security for AI Skills

The IsolateGPT architecture [22] provides the blueprint for LLM app isolation:

```
┌─────────────────────────────────────────────┐
│           Noctem Core Runtime               │
├─────────────────────────────────────────────┤
│  ┌─────────┐  ┌─────────┐  ┌─────────┐     │
│  │ Skill A │  │ Skill B │  │ Skill C │     │
│  │ (WASM)  │  │ (WASM)  │  │ (WASM)  │     │
│  └────┬────┘  └────┬────┘  └────┬────┘     │
│       │            │            │          │
│  ┌────▼────────────▼────────────▼────┐     │
│  │     Capability Mediator (WASI)    │     │
│  │  - File: read-only /skills/*      │     │
│  │  - Network: allowed endpoints     │     │
│  │  - Memory: 64MB per skill         │     │
│  │  - CPU: 100ms per invocation      │     │
│  └───────────────────────────────────┘     │
└─────────────────────────────────────────────┘
```

Key properties of the Tree Bark model:

1. **Deny-by-Default:** Skills start with zero capabilities
2. **Explicit Grants:** Each capability (file, network, memory) explicitly provided
3. **Attenuation:** Skills can only delegate subsets of their own capabilities
4. **Revocation:** Capabilities can be invalidated without skill cooperation

### 3.4 MVVM Two-Way Sandboxing

The MVVM framework [23] introduces **bidirectional protection**:
- **Host Protection:** WASM sandbox prevents malicious skills from accessing host
- **Skill Protection:** Hardware enclaves (SGX/TDX) protect skill IP from malicious hosts

This is relevant for Noctem when skills contain proprietary logic that users want to protect even from the agent itself. The WASI interface mediates all interactions through cryptographically-authenticated capability tokens.

### 3.5 Implementation Recommendations

For Noctem's Tree Bark security layer:

1. **Runtime:** Wasmtime (Rust, security-focused, Bytecode Alliance backing)
2. **Interface:** WASI Preview 2 with custom capability extensions
3. **Skill Format:** WASM Components with signed manifests
4. **Resource Limits:**
   - Memory: 64MB per skill instance
   - CPU: 100ms per invocation (configurable)
   - Network: Explicit allowlist per skill
   - Filesystem: Read-only access to skill-specific directories

5. **Verification Pipeline:**
   ```
   Skill Package → Signature Check → Manifest Parse → 
   Capability Extraction → Policy Evaluation → Instantiation
   ```

---

## 4. Integration: The Unified Noctem Architecture

### 4.1 Synthesis

The three research verticals converge on a coherent architecture:

```
┌────────────────────────────────────────────────────────┐
│                    NOCTEM AGENT                        │
├────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────┐  │
│  │           IDENTITY LAYER (Cor Unum)              │  │
│  │  • Merkle-CRDT state persistence                 │  │
│  │  • DID-based discovery & authentication          │  │
│  │  • Verifiable Credentials for trust attestation  │  │
│  └──────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────┐  │
│  │          INFERENCE LAYER (Low-Spec)              │  │
│  │  • 1.5B model @ 1.58-bit quantization            │  │
│  │  • KD-LoRA fine-tuned on personalization         │  │
│  │  • ~1.5GB memory footprint                       │  │
│  └──────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────┐  │
│  │          SKILL LAYER (Tree Bark)                 │  │
│  │  • WASM capability-isolated modules              │  │
│  │  • Deny-by-default permission model              │  │
│  │  • <6% overhead hardware-accelerated safety      │  │
│  └──────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────┘
```

### 4.2 Open Research Questions

1. **CRDT Garbage Collection:** How to bound metadata growth in long-running Merkle-CRDTs?
2. **Quantization-Aware Distillation:** Can we co-optimize quantization and distillation end-to-end?
3. **Capability Inference:** Can the agent automatically determine minimal required capabilities for skills?
4. **Cross-Instance Learning:** How to merge fine-tuning updates across distributed Noctem instances?

### 4.3 Recommended Next Steps

1. **Prototype:** Implement Merkle-CRDT identity layer using `automerge-rs`
2. **Benchmark:** Evaluate PTQTP vs QLoRA-4bit on Noctem-specific tasks
3. **Integrate:** Build WASM skill loader with Wasmtime + custom WASI
4. **Validate:** Security audit of capability mediation layer

---

## 5. Conclusion

The academic literature from 2023-2026 provides robust foundations for Noctem's core challenges. CRDTs solve distributed identity without coordination, sub-4-bit quantization enables local inference, and WASM capability isolation secures the skill layer. The convergence of these technologies creates a viable path toward a truly local-first, privacy-preserving AI daemon.

The "Cor Unum" problem—maintaining one heart across many bodies—is solvable through content-addressed, conflict-free state replication. The agent can exist simultaneously on phone, laptop, and cloud while remaining a singular entity.

The "Tree Bark" model—protective layers that permit growth while preventing intrusion—is achievable through WebAssembly's capability-based security. Skills can extend the agent's abilities without compromising its integrity.

Noctem is technically feasible. The research foundation is solid. What remains is engineering.

---

## References

See BIBLIOGRAPHY.md for complete IEEE citations and BibTeX entries for all 25 sources.

---

*Document prepared for the Noctem AI Project*  
*Research synthesis by automated analysis pipeline*
