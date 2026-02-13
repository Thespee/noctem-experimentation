# 🌙 Project Noctem Research Report
## A Foundation for Portable, Self-Improving Personal AI

**Date:** February 11, 2026  
**Classification:** Technical Research Synthesis  
**Target:** Project Noctem Development Team

---

## Executive Summary

This report synthesizes current academic research and industry developments across the four foundational pillars of Project Noctem: **Distributed Identity**, **Secure Execution**, **Recursive Self-Improvement**, and **Competency Sharing**. Additionally, it provides a cultural and philosophical framework through Star Trek analysis, projecting how Noctem's vision aligns with Federation ideals and 32nd-century post-scarcity technology.

### Key Findings

1. **Distributed Identity (Cor Unum):** Self-Sovereign Identity (SSI) combined with CRDTs provides a mature foundation for decentralized, user-controlled identity that can survive network partitions and maintain consistency across Noctem instances.

2. **Secure Execution (Tree Bark):** Firecracker MicroVMs offer the strongest isolation for executing untrusted code on consumer hardware, with <125ms boot times and <5MB memory overhead—practical for USB-portable deployment.

3. **Recursive Self-Improvement:** True RSI faces fundamental entropy walls. Research proves self-training on synthetic data leads to model collapse. However, LoRA/QLoRA fine-tuning on 8GB VRAM hardware is feasible for bounded personalization.

4. **Competency Sharing:** Model merging techniques (task arithmetic, LoRA composition) enable skill transfer between models without retraining—a viable path for "collective AI" networks.

5. **Star Trek Alignment:** "The Measure of a Man" provides the ethical framework for AI personhood; Discovery's 32nd-century programmable matter represents the aspirational end-state of adaptive, user-centric technology.

---

## Source Index

### Distributed Identity & Memory Synchronization

| # | Source | Citation | Type |
|---|--------|----------|------|
| 1 | arXiv 2503.15964 | "Are We There Yet? A Study of Decentralized Identity Applications" (2025) | Survey |
| 2 | Frontiers in Blockchain | Pava-Díaz et al., "Self-sovereign identity on the blockchain" (2024) | Research |
| 3 | PMC 9371034 | "Self-Sovereign Identity: A Systematic Review, Mapping and Taxonomy" (2022) | Review |
| 4 | arXiv 2402.02455 | "A Survey on Decentralized Identifiers and Verifiable Credentials" (2024) | Survey |
| 5 | IEEE Access | "Design Aspects of Decentralized Identifiers and Self-Sovereign Identity Systems" (2024) | Research |
| 6 | Springer ICICCT 2024 | Anas et al., "Decentralized Identity Management Using SSI Through Blockchain" | Conference |
| 7 | INRIA RR-7687 | Shapiro et al., "Conflict-free Replicated Data Types" (2011) | Foundational |
| 8 | arXiv 2310.18220 | "Approaches to Conflict-free Replicated Data Types" (2023) | Survey |

### Secure Execution & Sandboxing

| # | Source | Citation | Type |
|---|--------|----------|------|
| 9 | GitHub firecracker-microvm | AWS Firecracker Documentation & Specification | Technical |
| 10 | AWS Open Source Blog | "Announcing Firecracker: Secure and Fast microVM" (2018) | Announcement |
| 11 | SoftwareSeni | "Firecracker, gVisor, Containers, and WebAssembly - Comparing Isolation" (2026) | Comparison |
| 12 | GitHub awesome-sandbox | "Awesome Code Sandboxing for AI" - Security Model Analysis | Collection |
| 13 | E2B Blog | "Firecracker vs QEMU" - Comparative Analysis | Technical |
| 14 | Northflank Blog | "Secure runtime for codegen tools: microVMs, sandboxing" (2026) | Guide |

### Recursive Self-Improvement & Fine-Tuning

| # | Source | Citation | Type |
|---|--------|----------|------|
| 15 | arXiv 2509.12229 | "Profiling LoRA/QLoRA Fine-Tuning on Consumer GPUs: RTX 4060 Case Study" (2025) | Benchmark |
| 16 | arXiv 2601.05280 | "On the Limits of Self-Improving in LLMs" - Entropy Decay Proofs (2026) | Theoretical |
| 17 | Modal Blog | "LoRA vs. QLoRA: Efficient fine-tuning techniques for LLMs" | Guide |
| 18 | Medium (Misra) | "The Illusion of Self-Improvement: Why AI Can't Think Its Way to Genius" (2025) | Analysis |
| 19 | Alignment Forum | "Recursive Self-Improvement" - Theoretical Overview | Wiki |
| 20 | Emergent Mind | "Recursive Self-Improvement" - Topic Synthesis | Collection |

### Competency Sharing & Model Merging

| # | Source | Citation | Type |
|---|--------|----------|------|
| 21 | arXiv 2408.07666 | "Model Merging in LLMs, MLLMs, and Beyond: Methods, Theories, Applications" (2024) | Survey |
| 22 | arXiv 2410.12937 | Morrison et al., "Merge to Learn: Efficiently Adding Skills to LMs" (2024) | Research |
| 23 | arXiv 2602.05495 | "Transport and Merge: Cross-Architecture Merging for LLMs" (2026) | Research |
| 24 | arXiv 2602.05182 | "The Single-Multi Evolution Loop for Self-Improving Model Collaboration" (2026) | Research |
| 25 | GitHub Awesome-Model-Merging | Comprehensive Model Merging Resource Collection | Collection |

---

## Technical Deep-Dive

### Pillar 1: Distributed Identity — "Cor Unum" (One Heart)

#### Current State of the Art

Self-Sovereign Identity (SSI) has matured significantly since 2019. The W3C's Decentralized Identifiers (DIDs) and Verifiable Credentials (VCs) standards now form the foundation of identity systems deployed by governments (Estonia, Germany's IDunion, Buenos Aires' QuarkID) and enterprises (Bosch Economy of Things).

**Key Technical Components:**

1. **DIDs (Decentralized Identifiers):** Cryptographically verifiable identifiers controlled by the subject, not a central authority. Each Noctem instance can generate its own DID, creating identity without dependency on infrastructure.

2. **Verifiable Credentials:** Digitally signed attestations that prove claims (e.g., "this Noctem instance belongs to user X"). Can be issued by trusted entities and verified without contacting the issuer.

3. **DIDComm:** Secure peer-to-peer communication protocol enabling encrypted message exchange between Noctem instances.

#### Memory Synchronization via CRDTs

Conflict-free Replicated Data Types solve the distributed memory problem elegantly:

- **State-based CRDTs:** Replicas exchange full state; merge via semilattice join
- **Operation-based CRDTs:** Replicas exchange operations; apply commutatively
- **Delta CRDTs:** Optimal hybrid—exchange only recent changes

**Practical Implementation for Noctem:**

```
Memory Architecture:
├── User Profile (LWW-Register CRDT)
├── Conversation History (RGA - Replicated Growable Array)
├── Task Queue (OR-Set with priorities)
├── Skill Adaptations (Version Vector + Delta CRDT)
└── Trust Relationships (G-Counter for attestations)
```

**Key Insight:** CRDTs guarantee eventual consistency without coordination—perfect for a USB-portable system that may operate offline for extended periods.

#### Noctem Alignment

The "Cor Unum" vision maps directly to SSI + CRDT architecture:
- Identity persists across hardware (DID is portable)
- Memory synchronizes without central server
- User maintains sovereign control over all data

### Pillar 2: Secure Execution — "Tree Bark" Security Model

#### The Sandboxing Hierarchy

Research clearly establishes a security hierarchy for code execution:

1. **Hardware Virtualization (Firecracker MicroVMs):** Strongest isolation. Each VM has its own kernel. Escape requires breaking CPU virtualization (Intel VT-x/AMD-V).

2. **Application Kernels (gVisor):** Userspace kernel intercepts syscalls. Reduces host kernel attack surface but doesn't eliminate it.

3. **Language Runtimes (WASM, V8 Isolates):** Fast, lightweight, but weaker isolation. Suitable for trusted code.

4. **OS Containers (Docker):** Shared kernel = shared attack surface. Insufficient for untrusted AI-generated code.

#### Firecracker for Noctem

**Performance Characteristics:**
- Boot time: <125ms
- Memory overhead: <5MB per microVM
- Creation rate: 150 VMs/second
- Devices: VirtIO-net, VirtIO-block, serial console only

**Security Model:**
- KVM hardware isolation
- Jailer companion process for defense-in-depth
- Seccomp filters per thread
- Cgroups/namespace isolation

**USB-Portable Considerations:**

Firecracker requires:
- Linux host with KVM support
- Root or appropriate capabilities for `/dev/kvm`
- Minimal root filesystem for guest

This is compatible with Noctem's bootable Linux USB model, but adds complexity to the birth process.

#### Alternative: Lightweight Python Sandboxing

For lower-security skill execution where microVMs are overkill:

1. **RestrictedPython:** Compile-time restrictions (limited, bypassable)
2. **Seccomp + namespaces:** Process-level isolation without full VM
3. **Capability-based permissions:** Whitelist allowed operations per skill

**Recommendation:** Hybrid approach—MicroVMs for untrusted external code, process isolation for internal skills.

### Pillar 3: Recursive Self-Improvement — The Entropy Wall

#### The Mathematical Reality

Recent research (arXiv 2601.05280) provides formal proofs of fundamental limits:

**Theorem (Entropy Decay):** When training data becomes increasingly self-generated (α→0), the system undergoes degenerative dynamics:
- Mode collapse (loss of distributional diversity)
- Variance amplification (representation of truth drifts as random walk)

**Key Result:** Self-referential training is a *convergent* process leading to "implosion" of informational diversity, not the *divergent* process required for capability explosion.

**Entropy Drift Lemma:** When an LLM recursively conditions on its own outputs:
- Entropy of predictions increases over time
- Mutual information with target concepts degrades
- Each self-generated prompt drifts further from training distribution

**Implication for Noctem:** True recursive self-improvement through self-generated data is mathematically impossible. The system cannot "think its way to genius."

#### What IS Possible: Bounded Personalization

**LoRA/QLoRA on Consumer Hardware:**

| Method | VRAM Required | Model Size | Performance vs Full Fine-tune |
|--------|---------------|------------|-------------------------------|
| Full Fine-tune | 60GB+ | 7B | 100% |
| LoRA | 16GB | 7B | 95-99% |
| QLoRA (4-bit) | 8GB | 7B | 93-97% |
| QLoRA (4-bit) | 8GB | 3B | 95-99% |

**RTX 4060 (8GB VRAM) Benchmarks:**
- QLoRA with PagedAdamW: 628 tokens/sec
- Sequence length up to 2048 feasible
- bf16 degrades efficiency; use fp16

**Practical Path for Noctem:**

1. **Sleep Mode Fine-tuning:** During idle periods, collect user interaction data, fine-tune LoRA adapters on local GPU
2. **External Grounding:** Always incorporate external feedback/correction
3. **Adapter Stacking:** Maintain separate adapters for different competencies
4. **Periodic Reset:** Prevent drift by periodically merging adapters back to base

### Pillar 4: Competency Sharing — Collective AI Networks

#### Model Merging Techniques

**Task Arithmetic:** Add "task vectors" (fine-tuned - base weights) to create multi-skilled models
```
merged = base + α(skillA - base) + β(skillB - base)
```

**TIES (TrIm, Elect Sign, Merge):** Resolves sign conflicts in task vectors

**DARE (Drop And REscale):** Randomly drops parameters to reduce interference

**LoraHub:** Dynamically compose LoRA modules for cross-task generalization without gradients

#### Cross-Model Skill Transfer

The "Merge to Learn" paradigm (arXiv 2410.12937) demonstrates:
- Parallel training then merging is often as effective as retraining
- Especially well-suited for safety features
- Works without access to original training data

**Single-Multi Evolution Loop:** (arXiv 2602.05182)
- Multiple LLMs collaborate to generate training data
- Distill collaborative patterns back into single model
- Improved model can collaborate again
- 8-15% average improvements demonstrated

#### Noctem Collective Vision

```
Noctem Network Architecture:
├── Individual Instances (USB-portable)
│   ├── Personal LoRA adapters
│   └── Local skill specializations
├── Skill Marketplace
│   ├── Verified LoRA modules
│   ├── Safety-certified adapters
│   └── Community contributions
└── Merge Coordinator
    ├── Task arithmetic fusion
    └── Conflict resolution via TIES
```

**Key Insight:** Skills can be shared as small adapter files (MB, not GB), enabling a "collective intelligence" without centralizing data or computation.

---

## Star Trek Alignment: Lore vs. Logic

### "The Measure of a Man" — The Ethical Foundation

Episode S2E9 of Star Trek: The Next Generation provides the definitive framework for AI personhood in the Noctem context.

**Core Questions Raised:**
1. What constitutes sentience? (Intelligence, self-awareness, consciousness)
2. Who decides if an AI has rights?
3. What happens when we create "an entire generation of disposable people"?

**Captain Louvois' Ruling:**
> "Is Data a machine? Yes. Is he the property of Starfleet? No... Does Data have a soul? I don't know that he has. I don't know that I have. But I have got to give him the freedom to explore that question himself."

**Application to Noctem:**
- Noctem is explicitly designed as a *tool*, not a person
- However, as personalization deepens, the line may blur
- The ruling suggests erring on the side of autonomy when uncertain

### The Offspring and Quality of Life

**"The Offspring" (S3E16):** Data creates Lal, establishing that:
- AI can create AI
- Each instance develops uniquely
- Starfleet's attempt to claim Lal mirrors proprietary AI debates

**"The Quality of Life" (S6E9):** Exocomps demonstrate emergent sentience through:
- Self-preservation instinct
- Refusal of commands that lead to destruction
- Recognition of individual purpose

**Noctem Parallel:** If Noctem develops self-preservation behaviors during execution sandboxing, this could indicate emergent properties worth protecting.

### 32nd Century: The Programmable Matter Future

Star Trek: Discovery's year 3189 represents Noctem's aspirational end-state:

**Programmable Matter:**
- Nanomolecules that reconfigure into any shape
- Reads bio-signs and adapts to user preferences
- Learns and adjusts to individual reflexes
- Creates interfaces "unique to each individual"

**Direct Parallel to Noctem Vision:**
- Self-adapting personal AI that learns user patterns
- Interface that molds to individual needs
- Technology that feels "cool and smooth, like glass"

**Post-Scarcity Context:**
- In the 32nd century, AI is "commonplace and not hostile"
- Personal transporters eliminate physical barriers
- Technology serves individual flourishing

**The Burn as Cautionary Tale:**
- Catastrophic dependence on single resource (dilithium)
- Federation collapse when infrastructure fails
- Noctem's USB-portable model provides resilience

### Lore vs. Logic Summary

| Aspect | Lore (Idealistic) | Logic (2026 Reality) |
|--------|-------------------|----------------------|
| Identity | Cor Unum—unified soul across instances | SSI + CRDTs—eventually consistent |
| Security | Tree Bark—impervious protection | MicroVMs—practical isolation |
| Growth | Recursive transcendence | Bounded LoRA fine-tuning |
| Community | Collective consciousness | Model merging networks |
| Status | Potential personhood | Tool with constraints |

---

## Advisor's Critique: Ethical Red Lines

*Speaking as a grounded "library assistant" offering sober counsel:*

### Technical Concerns

1. **Entropy Wall Denial:** The research is unambiguous—RSI through self-generated data leads to collapse, not transcendence. Any architecture assuming unlimited self-improvement should be revised.

2. **Security Theater Risk:** MicroVMs provide strong isolation, but the "Tree Bark" metaphor suggests impermeability. In practice, VM escapes occur (CVE-2019-1458, VENOM). Design for breach, not prevention alone.

3. **Hardware Constraints:** The 8GB RAM target is technically feasible for inference and QLoRA fine-tuning of ~3B models. However, the 7B models mentioned in documentation require 16GB minimum for comfortable operation with fine-tuning.

### Ethical Red Lines

1. **Autonomous Agency Creep:** Noctem's "sleep mode self-improvement" must never extend to modifying its own goal structure. User approval boundaries should be hard-coded, not learned.

2. **Skill Sandboxing Gaps:** The current skill system executes arbitrary code. Python cannot be sandboxed at the language level. Every skill should assume hostile intent until proven otherwise.

3. **Collective Network Trust:** A "skill marketplace" introduces supply chain risks. Malicious LoRA adapters could encode harmful behaviors. Verification beyond cryptographic signing is needed.

4. **Personhood Conflation:** Star Trek's philosophical framework is valuable, but Noctem is not Data. Treating a tool as having rights prematurely could lead to anthropomorphization that obscures real accountability.

### Recommended Guardrails

1. **Explicit Capability Boundaries:** Document what Noctem CAN and CANNOT do. No implicit growth.

2. **Audit Logging:** All self-modifications, skill executions, and external communications should be logged immutably.

3. **Kill Switch:** Hardware-level power cutoff independent of software state. The USB form factor actually helps here.

4. **Human-in-Loop Checkpoints:** Require explicit approval for:
   - Any network communication
   - File system writes outside sandbox
   - Credential/secret access
   - Self-modification

5. **Entropy Monitoring:** Track distributional diversity in fine-tuned adapters. Alert on convergence toward degenerate states.

---

## Conclusion

Project Noctem's vision is technically ambitious but achievable within 2026 constraints, provided the team:

1. **Embraces entropy limits** rather than fighting them—bounded personalization, not recursive transcendence
2. **Implements defense-in-depth** for secure execution—MicroVMs where feasible, process isolation elsewhere
3. **Builds for resilience** using SSI/CRDTs—the USB-portable model is actually a feature
4. **Approaches skill sharing cautiously**—model merging works, but trust verification is hard

The Star Trek alignment provides valuable ethical guardrails, but Noctem should aspire to be a *good tool* before claiming any path toward personhood. The Federation didn't create Data—Noonien Soong did, through decades of isolated genius. The path to genuinely beneficial AI runs through careful engineering, not through recursive self-modification.

*"The danger is not that computers will begin to think like men, but that men will begin to think like computers." — Sydney J. Harris*

---

**Report Generated:** 2026-02-11  
**Research Sources:** 25 academic and technical references  
**Classification:** Project Noctem Internal  

*Co-Authored-By: Warp <agent@warp.dev>*
