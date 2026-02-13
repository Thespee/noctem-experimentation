# Noctem Project: State of the Research Briefing
## Deep-Dive Research Synthesis for Low-Resource Agentic AI Safety
**Date:** February 11, 2026  
**Target Configuration:** 8GB RAM / 1TB USB Portable Linux System

---

## Executive Summary

This briefing synthesizes research across four critical pillars for the Noctem Project's theoretical foundations: (1) Distributed Identity & State, (2) Hardware-Level Sandboxing, (3) Alignment Drift Prevention, and (4) Privacy-Preserving Inference. The research reveals both promising pathways and significant theoretical limits for running secure, self-improving AI systems on low-spec portable hardware.

**Critical Finding:** The intersection of cryptographic agility (post-quantum), activation-level steering, and lightweight sandboxing presents a viable architecture for Noctem's "unified heart" vision, but requires careful engineering to avoid the "YOLO Mode Fallacy" and resource exhaustion on constrained hardware.

---

## Pillar 1: Distributed Identity & State
### W3C Decentralized Identifiers (DIDs) and CRDTs for the "Unified Heart"

### 1.1 W3C Decentralized Identifiers (DIDs)

The W3C DID Core 1.0 specification became an official W3C Recommendation on July 19, 2022 [1]. DIDs are a new type of globally unique identifier that enables verifiable, decentralized digital identity [2]. Unlike federated identifiers, DIDs are designed to be decoupled from centralized registries, identity providers, and certificate authorities [3].

**Key Properties for Noctem:**
- **Self-Sovereignty:** The controller of a DID can prove control over it without requiring permission from any other party [4].
- **Persistence:** DIDs can be assigned once and never need to change, ideal for a portable AI identity across machines [5].
- **Cryptographic Verifiability:** Each DID document can express cryptographic material and verification methods [6].

**Theoretical Limit for 8GB/1TB Configuration:**
DID resolution is lightweight—the Universal Resolver can function with minimal resources. The primary constraint is network connectivity for resolution operations. Noctem should implement local DID caching with periodic sync, targeting <50MB for identity state storage.

### 1.2 Conflict-free Replicated Data Types (CRDTs)

CRDTs were formally defined in 2011 by Marc Shapiro, Nuno Preguiça, Carlos Baquero, and Marek Zawirski [7]. They are data structures that simplify distributed data storage by ensuring that no matter what data modifications are made on different replicas, the data can always be merged into a consistent state automatically [8].

**CRDT Types Relevant to Noctem:**
- **State-based CRDTs (CvRDTs):** Send full local state on updates; require only gossip protocol for communication [9].
- **Operation-based CRDTs (CmRDTs):** Transmit update actions directly; require exactly-once delivery [10].
- **Pure operation-based CRDTs:** Reduce metadata size while maintaining equivalence [11].

**Resource Considerations:**
CRDTs face a fundamental challenge for low-resource devices: Some CRDTs can grow large over time, especially those that keep a history of all operations [12]. For Noctem's memory state, PN-Counters and LWW-Registers are recommended as they offer bounded growth. OR-Sets should be used cautiously with periodic garbage collection.

**Theoretical Limit:** On 8GB RAM, CRDT state for task queues, conversation history, and configuration should be capped at ~500MB with aggressive compaction. The Redis CRDT implementation demonstrates that CRDTs provide "strong eventual consistency" that is "much more efficient than the more common types of replication based on quorum quotas" [13].

### 1.3 Noctem-Specific Recommendations

For maintaining a "unified heart" across intermittently connected nodes:
1. Implement `did:key` method for offline-first identity (no ledger dependency)
2. Use LWW-Registers for configuration state, G-Counters for metrics
3. Design hybrid state sync: CRDT for low-priority data, explicit conflict resolution for high-priority decisions
4. Target <100ms state merge operations to not block inference

---

## Pillar 2: Hardware-Level Sandboxing
### Alternatives to Docker for Container-less, High-Security Skill Execution

### 2.1 Firecracker MicroVMs

Firecracker is an open-source VMM developed by AWS, purpose-built for creating secure, multi-tenant container and function-based services [14]. It combines the security and isolation properties of hardware virtualization with the speed and flexibility of containers [15].

**Key Specifications:**
- **Boot Time:** <125ms on i3.metal instances [16]
- **Memory Overhead:** <5 MiB per microVM [17]
- **Creation Rate:** Up to 150 microVMs per second on a single host [18]
- **Code Base:** Only 50,000 lines of Rust (96% reduction over QEMU's 1.4M lines) [19]

**Security Model:**
Firecracker uses a companion "jailer" process that applies seccomp-bpf filters, cgroups, and chroot isolation to the VMM process itself [20]. This provides defense-in-depth: even if the virtualization barrier is compromised, the jailer provides a second line of defense [21].

**Theoretical Limit for 8GB/1TB:**
Firecracker's 5MiB overhead per microVM is exceptional. However, each microVM requires a guest kernel image (~15-50MB) and root filesystem. On 8GB RAM, Noctem could theoretically run 10-15 concurrent skill execution microVMs while reserving 4GB for the main LLM inference. The 1TB USB storage can accommodate 100+ root filesystem snapshots for various skill environments.

**Critical Risk - The "YOLO Mode" Fallacy:**
Even isolated sandboxes risk "habituation," where users approve dangerous network egress calls out of fatigue [22]. Noctem must implement:
- Mandatory cooling-off periods for network access requests
- Anomaly detection on egress patterns
- Hard caps on daily approval counts

### 2.2 gVisor Syscall Filtering

gVisor is an open-source Linux-compatible sandbox that implements the Linux API by intercepting all sandboxed application system calls to the kernel [23]. It is used in production at Google to run untrusted workloads securely [24].

**Architecture:**
- **Sentry:** An application kernel in userspace that serves the untrusted application. It handles syscalls, routes I/O to gofers, and manages memory and CPU, all in userspace [25].
- **Gofer:** A process that handles different types of I/O for the Sentry (usually disk I/O) [26].
- **Attack Surface Reduction:** Of 350 syscalls in the Linux kernel, the Sentry implements only 237. At most, it only needs to call 68 host Linux syscalls [27].

**Performance Characteristics:**
gVisor introduces 10-30% overhead on I/O-heavy workloads [28]. For compute-heavy AI workloads where full VM isolation isn't justified, gVisor provides strong isolation without full VM overhead.

**Theoretical Limit:**
On low-spec hardware without virtualization support (KVM), gVisor's "Systrap" platform uses seccomp-bpf for system call interception without requiring hardware virtualization [29]. This makes gVisor viable for older USB-bootable hardware that may lack VT-x/AMD-V support—a significant advantage for Noctem's portability goals.

### 2.3 macOS Seatbelt (sandbox-exec)

macOS Sandbox, initially called Seatbelt, limits applications running inside the sandbox to allowed actions specified in a Sandbox profile [30]. It uses hooks in almost any operation a process might try using MACF (Mandatory Access Control Framework) [31].

**Profile Capabilities:**
- File read/write restrictions with regex patterns
- Network access control (inbound/outbound)
- Mach service access limitations
- Process execution restrictions [32]

**Syntax Example:**
```scheme
(version 1)
(deny default)
(allow file-read-data (regex "^/usr/lib"))
(allow process-exec (literal "/usr/bin/python3"))
```

**Limitation for Noctem:**
Seatbelt/sandbox-exec has been marked deprecated and has no graphical interface for configuration [33]. Custom Seatbelt policies are easy to mess up—bugs have been reported where AI agent sandboxes failed to properly block access to user home directory dotfiles and ~/Library [34]. For cross-platform Noctem deployment, Seatbelt should be considered a macOS-specific fallback, not a primary sandboxing strategy.

### 2.4 Recommended Sandboxing Architecture

For Noctem's skill execution on portable Linux:
1. **Primary:** Firecracker microVMs for untrusted skill code (when KVM available)
2. **Fallback:** gVisor/Systrap for environments without hardware virtualization
3. **macOS:** Seatbelt with carefully audited profiles for macOS deployments
4. **All platforms:** Mandatory network egress approval with anti-habituation controls

---

## Pillar 3: The "Assistant Axis" & Alignment Drift
### Preventing Persona Drift During Nightly LoRA Fine-Tuning

### 3.1 The Safety Tax Problem

Recent research reveals that safety alignment fine-tuning has been shown to significantly degrade reasoning abilities, a phenomenon known as the "Safety Tax" [35]. Reasoning fine-tuning often compromises safety, even when starting from a safety-aligned checkpoint [36].

**Mechanism of Drift:**
Safety drift during fine-tuning is characterized by:
- Reduction in the model's refusal rate on harmful prompts
- Increased generation of toxic or compliance outputs
- Disruption of safety-aligned layer-level computations [37]

This phenomenon manifests robustly across settings—full-parameter (SFT), parameter-efficient (LoRA), and continual pretraining (CPT)—and is observable even with benign fine-tuning data [38].

### 3.2 LoRA for Safety-Preserving Fine-Tuning

The key insight for Noctem: Using LoRA for SFT on refusal datasets effectively aligns the model for safety without harming its reasoning capabilities. This is because restricting the safety weight updates to a low-rank space minimizes the interference with the reasoning weights [39].

**Safe LoRA Methodology:**
Safe LoRA obtains an alignment matrix V = W_aligned - W_unaligned from a pair of unaligned and aligned LLMs [40]. For example, W_unaligned can be the Llama-2-7b-base model, while W_aligned can be the Llama-2-7b-chat model. The fine-tuning weights are then projected to preserve this safety direction.

**Results:**
With Safe LoRA implementation, the harmfulness score dramatically drops to around 1.05 (from much higher baselines), and the MT-Bench score increases to 6.4 [41].

### 3.3 Activation Steering as Alternative to Weight Modification

Activation steering (also called Representation Engineering) offers a lightweight approach to align LLMs by manipulating their internal activations at inference time—without modifying model weights [42].

**Core Method - Activation Addition (ActAdd):**
The intervention can be represented as: h' = h + α·v, where h is the hidden state at the layer, v is the steering vector, and α is a scaling factor [43].

**Advantages for Low-Spec Hardware:**
- No training required—single pair of data points enables rapid iteration [44]
- Inference-time control over high-level output properties (topic, sentiment) while preserving off-target performance [45]
- Non-destructive: operates on activations rather than permanently altering weights [46]

**Recent Advances (2025-2026):**
- **CAST (Conditional Activation Steering):** Introduces condition vectors representing activation patterns induced by the prompt, enabling context-dependent control [47]
- **ASM (Activation State Machines):** Dynamically computes interventions at each token based on learned state dynamics [48]
- **BODES:** Uses ODE-based multi-step adaptive steering, achieving 7% improvement on TruthfulQA [49]

### 3.4 Theoretical Limit for Noctem's Nightly Fine-Tuning

**Resource Constraints:**
On 8GB RAM with a 7B parameter model:
- Full-parameter fine-tuning: Infeasible (requires 28GB+ for gradients/optimizer)
- LoRA fine-tuning (rank 8): Feasible with 4-bit quantization (~6GB VRAM)
- Activation steering: Negligible overhead (<1% inference time increase)

**Recommended Approach:**
1. **Primary:** Activation steering for immediate alignment corrections (no training)
2. **Secondary:** Safe LoRA for periodic (weekly, not nightly) capability updates
3. **Safeguard:** Pre-computed "safety anchor" steering vectors that can be applied when drift is detected
4. **Monitoring:** Implement DriftCheck-style evaluation on a small probe set before deploying any fine-tuned adapters

---

## Pillar 4: Privacy-Preserving Inference
### TEEs, Lightweight Trusted Hardware, and Secure Computation

### 4.1 Trusted Execution Environments (TEEs)

TEEs use hardware-backed cryptographic technologies to create isolated, verified execution environments for code and data [50]. They function as digital vaults installed directly into the CPU and GPU, where attestation cryptographically proves the vault is authentic and untampered [51].

**Current Hardware Support:**
- **Intel SGX:** 128 MB reserved enclave memory by default [52]
- **NVIDIA Hopper/Blackwell:** GPU Confidential Computing with encrypted GPU memory [53]
- **AMD SEV:** Memory encryption for virtual machines

**Limitations for Low-Spec Hardware:**
TEEs inherently introduce computational overhead—secure enclaves must maintain continuous memory integrity checks, cryptographic isolation, and anti-replay safeguards [54]. Many TEEs lack support for GPU offloading or SIMD acceleration, resulting in longer execution times for ML inference [55].

### 4.2 Stamp: Small Trusted Hardware Assisted MPC

The Stamp framework proposes using lightweight trusted hardware (LTH) comparable to TPM or Apple's enclave processor to accelerate privacy-preserving ML inference [56]. 

**Key Insight:**
Non-linear operations (ReLU, sigmoid) account for the major part of MPC overhead. By offloading only these operations to a small trusted processor, Stamp achieves significant speedups without requiring full SGX enclaves [57].

**Performance Results:**
- For Network-B: Stamp (0.12s) vs Full SGX (0.46s)
- For ResNet18: Stamp with LTH-SoC takes 148 seconds vs Full SGX at 8.15 seconds [58]

**Trade-off Analysis:**
Stamp prioritizes communication efficiency over raw compute. It can even outperform high-performance TEE with secure GPU outsourcing (Goten) thanks to significantly reduced inter-party communication [59].

### 4.3 HT2ML: Hybrid TEE + Homomorphic Encryption

HT2ML proposes a hybrid framework where HE-friendly functions (linear operations) are performed outside the enclave using optimized HE matrix multiplications, while remaining operations are performed inside the enclave obliviously [60].

**Performance:**
- Linear Regression training: ~11× faster than HE-only baseline
- CNN inference: ~196× faster than previous approaches [61]

### 4.4 Theoretical Limits for Noctem

**On 8GB RAM Portable USB:**
- Full SGX enclave inference: Impractical (128MB enclave limit, frequent swapping)
- Stamp-style LTH approach: Viable if discrete security chip available
- Hybrid HE+software approach: Feasible for small models with significant latency

**Recommendation for Noctem:**
Given the target hardware constraints, Noctem should prioritize:
1. Local-only inference (no cloud dependency) as the primary privacy mechanism
2. VeraCrypt encryption at rest for all state and model files
3. Memory-mapped inference to minimize RAM footprint
4. Consider secure element integration (YubiKey, TPM) for key management only, not inference

---

## Critical Risk: Post-Quantum Cryptography and "Harvest Now, Decrypt Later"

### 5.1 The HNDL Threat Model

NIST explicitly warns: "Encrypted data remains at risk because of the 'harvest now, decrypt later' threat in which adversaries collect encrypted data now with the goal of decrypting it once quantum technology matures" [62].

**Timeline Urgency:**
- Q-Day estimates: 10-15 years
- NIST mandate: All federal agencies must migrate to PQC by 2035 [63]
- Algorithm standardization to full integration: 10-20 years [64]

**Implication for Noctem:**
The portable USB state holder is a prime target for HNDL attacks. An adversary could clone the encrypted drive today and decrypt Noctem's memory, conversation history, and personal data once quantum computers mature.

### 5.2 NIST Post-Quantum Standards

NIST finalized three cryptographic standards in August 2024:
- **ML-KEM (FIPS 203):** Key encapsulation mechanism based on structured lattices
- **ML-DSA (FIPS 204):** Digital signature algorithm
- **SLH-DSA (FIPS 205):** Stateless hash-based digital signature [65]

**Cryptographic Agility:**
NIST defines cryptographic agility as "the capabilities needed to replace and adapt cryptographic algorithms without interrupting the flow of a running system" [66].

### 5.3 Recommendations for Noctem

1. **Immediate:** Implement hybrid cryptography for VeraCrypt container (classical + PQC)
2. **Storage:** Use ML-KEM for any key exchange operations
3. **Signatures:** Migrate to ML-DSA for code signing of skills and adapters
4. **Architecture:** Design all cryptographic interfaces to be algorithm-agnostic, enabling hot-swap of algorithms
5. **Inventory:** Maintain explicit documentation of all cryptographic dependencies

---

## Theoretical Limits Summary: 8GB RAM / 1TB USB Configuration

| Component | Memory Budget | Storage Budget | Feasibility |
|-----------|---------------|----------------|-------------|
| LLM Inference (7B, 4-bit) | 4-5 GB | 4 GB model | ✓ Feasible |
| CRDT State | 500 MB | 2 GB | ✓ Feasible |
| DID/Credential Cache | 50 MB | 100 MB | ✓ Feasible |
| Firecracker microVM (1 skill) | 150-300 MB | 100 MB rootfs | ✓ Feasible |
| Multiple concurrent microVMs | 1-2 GB | 500 MB | ⚠️ Limited (3-5 max) |
| Safe LoRA training | 6 GB peak | 100 MB adapter | ⚠️ Marginal |
| Full fine-tuning | 28 GB+ | N/A | ✗ Infeasible |
| SGX enclave inference | 128 MB limit | N/A | ✗ Impractical |
| Activation steering | <50 MB | <10 MB vectors | ✓ Feasible |

---

## Source Bibliography

### Distributed Identity & State
[1] W3C. "Decentralized Identifiers (DIDs) v1.0 becomes a W3C Recommendation." W3C Press Release, July 2022.
[2-6] W3C DID Core 1.0 Specification. https://www.w3.org/TR/did-1.0/
[7-11] Shapiro, M., Preguiça, N., Baquero, C., Zawirski, M. "Conflict-free Replicated Data Types." INRIA Research Report RR-7687, 2011.
[12] DataDrivenDaily. "What is a CRDT?" 2024.
[13] Redis. "Diving into Conflict-Free Replicated Data Types." Redis Blog, 2025.

### Hardware-Level Sandboxing
[14-21] AWS. "Firecracker: Secure and Fast microVMs for Serverless Computing." GitHub/Documentation, 2018-2025.
[22] Northflank. "How to sandbox AI agents in 2026." Northflank Blog, 2026.
[23-29] Google. "gVisor Security Basics." gVisor Documentation, 2019-2024.
[30-34] Apple/Community. "macOS Sandbox (Seatbelt) Documentation." Various sources, 2011-2025.

### Alignment Drift Prevention
[35-39] Various. "LoRA is All You Need for Safety Alignment of Reasoning LLMs." arXiv:2507.17075, 2025.
[40-41] Hsu et al. "Safe LoRA: the Silver Lining of Reducing Safety Risks." NeurIPS 2024.
[42-49] Various. "Activation Steering and Representation Engineering." ICLR 2025, arXiv, 2023-2026.

### Privacy-Preserving Inference
[50-55] Various. "Confidential Computing and TEEs." Red Hat/Duality/Medium, 2025.
[56-59] Huang et al. "Stamp: Efficient Privacy-Preserving Machine Learning with Lightweight Trusted Hardware." PETS 2024.
[60-61] ScienceDirect. "HT2ML: Hybrid TEE + HE Framework." Computers & Security, 2023.

### Post-Quantum Cryptography
[62-64] NIST. "Transition to Post-Quantum Cryptography Standards." NIST IR 8547, 2024.
[65-66] NIST. "What Is Post-Quantum Cryptography?" NIST Cybersecurity, 2025.

---

## Appendix: Recommended Source Downloads

For NotebookLM ingestion, prioritize obtaining these PDFs:

1. **CRDT-Comprehensive-Study-2011.pdf** - Shapiro et al. original CRDT paper
2. **W3C-DID-Core-v1.0-2022.pdf** - Official W3C specification
3. **Firecracker-Design-AWS-2018.pdf** - AWS Firecracker architecture
4. **gVisor-Security-Model-2019.pdf** - Google gVisor design document
5. **Safe-LoRA-NeurIPS-2024.pdf** - Safety-preserving fine-tuning
6. **Representation-Engineering-Survey-2025.pdf** - Wehner comprehensive survey
7. **Stamp-PETS-2024.pdf** - Lightweight trusted hardware for PPML
8. **NIST-IR-8547-PQC-Transition-2024.pdf** - Post-quantum migration guide
9. **Activation-Steering-ICLR-2025.pdf** - CAST methodology
10. **AlignGuard-LoRA-2025.pdf** - Alignment drift prevention

---

*Document generated: 2026-02-11*
*Built with assistance from Warp Agent for the Noctem Project*
