# Project Noctem: State of the Project Research Briefing

**Document Type:** Academic Literature Review Synthesis  
**Generated:** 2026-02-11  
**Sources:** 25 Academic Papers (ArXiv, IEEE, ACM, PoPETs)  
**Purpose:** NotebookLM Grounding for Technical Decision-Making

---

## Executive Summary

This briefing synthesizes findings from 25 academic sources across five technical pillars critical to Project Noctem's vision of a portable, self-improving personal AI agent. The research reveals both **mature solutions** ready for adoption and **critical gaps** requiring novel approaches.

### Key Findings at a Glance

| Pillar | Maturity | Primary Risk | Recommended Path |
|--------|----------|--------------|------------------|
| Self-Sovereign Identity | High | Blockchain dependency | W3C DID + Local wallet |
| Secure Sandboxing | Very High | Performance overhead | WebAssembly + WASI |
| Bounded Self-Improvement | Medium | Memory constraints | QLoRA + Gradient checkpointing |
| Knowledge Transfer | High | Capability gap | Skill distillation via data augmentation |
| Computational Sovereignty | Low (Emerging) | Regulatory uncertainty | Local-first architecture |

---

## Pillar 1: Self-Sovereign Identity (SSI)

### Technical Landscape

Self-Sovereign Identity represents a paradigm shift from centralized identity providers to user-controlled digital credentials. The W3C standards for Decentralized Identifiers (DIDs) and Verifiable Credentials (VCs) form the foundational layer.

**Core Architecture Components:**

1. **Identity Owners** - Hold and control credentials in digital wallets
2. **Issuers** - Authorized entities that attest to identity attributes  
3. **Verifiers** - Request and validate credential presentations
4. **Verifiable Data Registry (VDR)** - Decentralized storage for DID documents

> *Citation: SSI_04_arxiv_2404.06729_sok_trusting_ssi.pdf, Section 1.3*

### Trust Model Analysis

The research identifies three distinct trust models in SSI implementations:

**Model A: Fully Decentralized**
- No single point of failure
- Highest privacy guarantees
- Challenge: Key recovery mechanisms are complex

**Model B: Federated Trust**
- Multiple issuers cooperate
- Balance between usability and decentralization
- Risk: Issuer collusion

**Model C: Anchored Trust**
- Blockchain or distributed ledger as root of trust
- Cryptographic verifiability
- Challenge: Scalability and transaction costs

> *Citation: SSI_02_arxiv_2108.08338_systematic_review_taxonomy.pdf, Section 4*

### Critical Challenges for Noctem

1. **Constrained Device Support**: Resource-limited devices may be unable to handle VC processing overhead. Research shows authorization servers can delegate credential processing, but this requires "potentially unfounded trust in the authorization server."
   > *Citation: SSI_04_arxiv_2404.06729_sok_trusting_ssi.pdf, Section 5.2*

2. **Key Management**: Loss of private keys results in permanent credential loss. Hardware security modules (HSM) or hardware keys (YubiKey/FIDO2) provide mitigation but add complexity.
   > *Citation: SSI_05_arxiv_2409.03624_ssi_gdpr_compliance.pdf, Section 3.4*

3. **Cross-Chain Interoperability**: "Blockchains are mostly siloed, affecting the interoperability and universality of SSI."
   > *Citation: SSI_03_arxiv_2503.15964_decentralized_identity_apps.pdf, Abstract*

### Noctem Implementation Recommendation

**Adopt W3C DID:key method** with local SQLite-backed wallet:
- No blockchain dependency (eliminates transaction costs)
- Credentials stored in encrypted VeraCrypt volume
- Signal phone number as identity anchor (existing integration)
- Hardware key support for unlock (YubiKey/FIDO2)

---

## Pillar 2: Secure Sandboxing Without Containers

### WebAssembly as the Solution

WebAssembly (WASM) has emerged as "a lightweight, efficient virtualization solution applicable to many domains." Unlike containers, WASM provides:

- **Memory Safety**: Linear memory model with bounds checking
- **Control Flow Integrity (CFI)**: Function table with type-checked signatures
- **Portability**: "Polyglot compilation target" supporting C/C++, Rust, Go, Python
- **Near-Native Performance**: 5-15% overhead vs native code

> *Citation: SANDBOX_01_arxiv_2407.12297_wasm_security_review.pdf, Section 2*

### Security Model

WASM implements a **capability-based security model**:

```
┌─────────────────────────────────────────┐
│           Host Environment               │
│  ┌─────────────────────────────────┐    │
│  │      WASM Runtime (wasmtime)     │    │
│  │  ┌───────────────────────────┐  │    │
│  │  │    Sandboxed Module       │  │    │
│  │  │  - Linear Memory (4GB)    │  │    │
│  │  │  - Function Table         │  │    │
│  │  │  - No direct syscalls     │  │    │
│  │  └───────────────────────────┘  │    │
│  │           WASI Interface         │    │
│  └─────────────────────────────────┘    │
└─────────────────────────────────────────┘
```

> *Citation: SANDBOX_04_arxiv_2312.03858_wasm_thin_kernel_interfaces.pdf, Section 3*

### Memory Safety Enhancements

Recent research introduces **Cage**, a hardware-accelerated WASM toolchain using:

1. **ARM Memory Tagging Extension (MTE)**: Spatial and temporal memory safety
2. **Pointer Authentication (PAC)**: Prevents pointer reuse across instances

Results show "minimal runtime (<5.8%) and memory (<3.7%) overheads" while "achieving a speedup of over 5.1%" for sandboxing mechanisms.

> *Citation: SANDBOX_02_arxiv_2408.11456_cage_hw_accelerated_wasm.pdf, Abstract*

### IoT and Edge Integration

For Noctem's USB-portable deployment, WASI (WebAssembly System Interface) provides:

- **Secure sensor access**: "Multi-tenant access to sensor data across heterogeneous embedded devices"
- **Application memory isolation**: Prevents cross-contamination between skills
- **Access control lists (ACL)**: Capability-based hardware interface permissions

> *Citation: SANDBOX_03_arxiv_2601.14555_wasm_iot_sandbox.pdf, Section 1*

### Threat Model Alignment

WASM addresses Noctem's security requirements:

| Threat | WASM Mitigation |
|--------|-----------------|
| Runaway Commands | Sandboxed execution, no direct syscalls |
| Memory Corruption | Bounds-checked linear memory |
| Code Injection | CFI via function table validation |
| Credential Access | WASI capability gating |

> *Citation: SANDBOX_01_arxiv_2407.12297_wasm_security_review.pdf, Section 5*

### Noctem Implementation Recommendation

**Deploy skills as WASM modules** compiled from Python/Rust:
- Runtime: wasmtime (battle-tested, WASI support)
- Skill interface: Custom WASI extension for Noctem APIs
- Path restrictions: Capability-based file access
- Network access: Explicit capability grant per skill

---

## Pillar 3: Bounded Self-Improvement on Consumer Hardware

### The 8GB RAM Constraint

Noctem targets systems with ≤8GB RAM, which creates fundamental constraints for model fine-tuning. Research shows that even with optimization, full fine-tuning of 7B parameter models requires 28-56GB VRAM.

**Solution: Parameter-Efficient Fine-Tuning (PEFT)**

### LoRA and QLoRA Analysis

Low-Rank Adaptation (LoRA) "reduces the number of trainable parameters by orders of magnitude, making fine-tuning feasible on consumer-grade hardware."

**Mechanism:**
```
Original Weight: W ∈ R^(d×k)
LoRA Adaptation: W' = W + BA where B ∈ R^(d×r), A ∈ R^(r×k), r << min(d,k)
```

QLoRA extends this with 4-bit quantization:
- Base model weights: NF4 quantization (4-bit)
- LoRA adapters: fp16 (trainable)
- Memory reduction: ~75% vs fp16

> *Citation: SELFIMPROV_01_arxiv_2509.12229_lora_qlora_consumer_gpu.pdf, Section 2*

### Consumer GPU Profiling Results

Research on RTX 4060 (8GB VRAM) with Qwen2.5-1.5B shows:

| Configuration | Throughput | VRAM Usage |
|---------------|------------|------------|
| LoRA + fp16 + AdamW | 500 tok/s | 6.2 GB |
| QLoRA + fp16 + PagedAdamW | 628 tok/s | 5.4 GB |
| QLoRA + bf16 + PagedAdamW | 512 tok/s | 5.6 GB |

Key finding: "Paged optimizers improve throughput by up to 25%"

> *Citation: SELFIMPROV_01_arxiv_2509.12229_lora_qlora_consumer_gpu.pdf, Section 4*

### Edge Device Specific Optimizations

For Noctem's Jetson-class targets, **LoRA-Edge** introduces tensor-train decomposition:

- "Reduces the number of trainable parameters by up to two orders of magnitude"
- "Achieves accuracy within 4.7% of full fine-tuning while updating at most 1.49% of parameters"
- "1.4-3.8x faster convergence" on Jetson Orin Nano

> *Citation: SELFIMPROV_03_arxiv_2511.03765_lora_edge_tensor_train.pdf, Abstract*

### Self-Improvement Safety Constraints

Critical for "bounded" improvement:

1. **Data Quality Filtering**: Only high-signal interactions (task success, explicit corrections)
2. **Catastrophic Forgetting Prevention**: Elastic Weight Consolidation (EWC)
3. **Capability Boundaries**: Define skill domains, prevent cross-domain drift
4. **Rollback Mechanism**: Version LoRA adapters (50MB each), enable quick revert

### Noctem Implementation Recommendation

**Nightly LoRA fine-tuning pipeline:**

```python
# Sleep mode self-improvement
1. Filter daily interactions (success rate > 0.8)
2. Generate synthetic expansions via router model
3. QLoRA fine-tune worker model (rank=32, alpha=64)
4. Validate on held-out set (prevent regression)
5. Version and store adapter (~50MB)
6. A/B test new adapter for 24 hours before promotion
```

Target: <4GB RAM for fine-tuning 1.5B-3B models via gradient checkpointing + QLoRA

> *Citation: SELFIMPROV_04_arxiv_2504.15610_lora_resource_constrained.pdf, Section 3*

---

## Pillar 4: Transferring Narrow Competencies Between Models

### Knowledge Distillation Taxonomy

Knowledge Distillation (KD) in the LLM era operates across three dimensions:

1. **Algorithm** - Technical methods for knowledge extraction and injection
2. **Skill** - Specific capabilities (reasoning, alignment, agents)
3. **Verticalization** - Domain adaptation (legal, medical, finance)

> *Citation: TRANSFER_01_arxiv_2402.13116_kd_llm_survey.pdf, Section 2*

### Skill Distillation Methods

**Data Augmentation (DA)** has emerged as the dominant paradigm:

"A small seed of knowledge is used to prompt the LLM to generate more data with respect to a specific skill or domain."

Process:
1. Define skill taxonomy (e.g., email summarization)
2. Craft elicitation prompts targeting specific capabilities
3. Generate synthetic training data from larger model
4. Fine-tune smaller model on synthetic data

> *Citation: TRANSFER_01_arxiv_2402.13116_kd_llm_survey.pdf, Section 3.1*

### Online Knowledge Distillation

For continuous improvement, **Online KD (OKD)** shows promise:

- "Teacher network integrates small online modules to concurrently train with the student model"
- "Abolishes the necessity for on-policy sampling"
- "Reduces training time by up to fourfold"

This aligns with Noctem's "Parent" supervision model where external agents guide improvement.

> *Citation: TRANSFER_04_arxiv_2409.12512_online_kd_autoregressive.pdf, Abstract*

### Skill Transfer Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Parent Agent (7B+)                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │
│  │ Email Skill │  │ Research    │  │ Coding      │     │
│  │ Specialist  │  │ Specialist  │  │ Specialist  │     │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘     │
└─────────┼────────────────┼────────────────┼─────────────┘
          │ Synthetic      │ Synthetic      │ Synthetic
          │ Training Data  │ Training Data  │ Training Data
          ▼                ▼                ▼
┌─────────────────────────────────────────────────────────┐
│                   Noctem (1.5B-7B)                       │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │
│  │ Email LoRA  │  │ Research    │  │ Coding      │     │
│  │ Adapter     │  │ LoRA        │  │ LoRA        │     │
│  └─────────────┘  └─────────────┘  └─────────────┘     │
└─────────────────────────────────────────────────────────┘
```

### White-Box vs Black-Box Distillation

| Approach | Access Required | Best For |
|----------|-----------------|----------|
| Black-Box (DA) | API outputs only | Proprietary teachers (GPT-4) |
| White-Box | Model weights/activations | Open-source teachers |
| Self-Distillation | Same model | Self-improvement loops |

For Noctem's local-first philosophy, **white-box distillation from Qwen/Mistral** is optimal.

> *Citation: TRANSFER_02_arxiv_2504.14772_kd_dataset_distillation.pdf, Section 2.2*

### Noctem Implementation Recommendation

**Skill acquisition pipeline:**

1. **Skill Definition**: YAML schema defining inputs/outputs/examples
2. **Data Generation**: Parent agent generates 1000+ synthetic examples
3. **Quality Filtering**: Remove low-quality samples (perplexity filtering)
4. **LoRA Training**: Task-specific adapter (rank=16, ~25MB)
5. **Validation**: Hold-out test set (>90% task completion)
6. **Deployment**: Hot-swap adapter based on task classification

---

## Pillar 5: The "Right to Compute" and Computational Sovereignty

### Historical Context

The concept of "digital sovereignty" emerged from the tension between:

1. **State Sovereignty**: Control over data within borders
2. **Corporate Power**: Tech platforms as "quasi-sovereign entities"
3. **Individual Rights**: Privacy, data ownership, compute access

"Digital spaces defy physical borders; data flows seamlessly across countries, transcending the reach of any single jurisdiction."

> *Citation: RIGHTS_04_arxiv_2202.10069_digital_sovereignty_identity.pdf, Section 2*

### Compute as Governance Lever

Research identifies compute as a critical governance mechanism:

"Computing power, or 'compute', is crucial for the development and deployment of artificial intelligence capabilities. As a result, governments and companies have started to leverage compute as a means to govern AI."

**Key Tensions:**

| Stakeholder | Objective | Compute Relationship |
|-------------|-----------|---------------------|
| States | National security, economic competitiveness | Control via export restrictions |
| Corporations | Market dominance, data collection | Concentration in cloud infrastructure |
| Individuals | Privacy, autonomy, access | Dependency on centralized services |
| Researchers | Academic freedom, reproducibility | Access disparity vs industry |

> *Citation: RIGHTS_02_arxiv_2402.08797_computing_power_ai_governance.pdf, Section 1*

### The Emerging Right to Local Compute

The research identifies an "emerging trend shift in digital sovereignty towards individuals to take complete control of the security and privacy of their own digital assets."

This manifests in:

1. **Data Sovereignty**: "Capability of a data owner to decide the destiny of his/her data"
2. **Compute Sovereignty**: Right to process data locally without cloud dependency
3. **Identity Sovereignty**: Self-sovereign identity (SSI) as discussed in Pillar 1

> *Citation: RIGHTS_04_arxiv_2202.10069_digital_sovereignty_identity.pdf, Section 3*

### Trustless Autonomy and Self-Sovereign AI

Recent research explores AI agents that are "self-sovereign beyond mere autonomy":

"Once launched, an agent holds its own cryptographic private keys and makes autonomous decisions without human intervention."

This includes deployment on:
- Blockchain smart contracts
- Decentralized physical infrastructure (DePIN)
- Trusted Execution Environments (TEEs)

"DeAgents deployed in trustless enclaves are designed to be unstoppable without external permission."

> *Citation: RIGHTS_05_arxiv_2505.09757_trustless_autonomy_self_sovereign_ai.pdf, Section 2*

### Legal and Ethical Considerations

The research warns of regulatory uncertainty:

1. **Export Controls**: US restrictions on AI chips affect global compute access
2. **Terms of Service**: Cloud providers may terminate accounts for policy violations
3. **Legal Jurisdiction**: "Operates on a global, borderless network that is resistant to conventional law enforcement"

> *Citation: RIGHTS_03_arxiv_2412.13821_ai_proliferation_governance.pdf, Section 4*

### Noctem's Position in the Sovereignty Landscape

Noctem's architecture aligns with computational sovereignty principles:

| Principle | Noctem Implementation |
|-----------|----------------------|
| Data Sovereignty | Encrypted local storage (VeraCrypt) |
| Compute Sovereignty | Local Ollama inference (no cloud) |
| Identity Sovereignty | Signal phone + local credentials |
| Operational Independence | USB-portable, offline-capable |
| Transparency | Full audit logging, open-source |

### Noctem Implementation Recommendation

**Sovereignty-first design:**

1. **Zero Cloud Dependency**: All inference local (Ollama)
2. **Encrypted Portable Storage**: VeraCrypt container
3. **Predictable Costs**: No API fees, no usage-based pricing
4. **Air-Gap Capable**: Full functionality without network
5. **Exit Strategy**: `rm -rf noctem/` removes everything

---

## Technical Limits and Constraints Summary

### Hardware Boundaries (8GB RAM Target)

| Operation | Memory Required | Feasibility |
|-----------|-----------------|-------------|
| Inference (7B q4) | 4-6 GB | ✅ Viable |
| Inference (14B q4) | 8-10 GB | ⚠️ Marginal |
| LoRA Fine-tune (1.5B) | 3-4 GB | ✅ Viable |
| LoRA Fine-tune (7B) | 6-8 GB | ⚠️ With optimization |
| Full Fine-tune (any) | 28+ GB | ❌ Not viable |

### Performance Expectations

| Task | Expected Latency | Model |
|------|------------------|-------|
| Quick chat | <3 seconds | 1.5B q4 |
| Task planning | <10 seconds | 7B q4 |
| Skill execution | Variable | N/A |
| LoRA training (1000 samples) | 2-4 hours | 1.5B |

### Security Boundaries

| Attack Vector | Mitigation | Confidence |
|--------------|------------|------------|
| Prompt Injection | Input sanitization + output validation | Medium |
| Credential Theft | Encrypted vault + hardware keys | High |
| Malicious Skills | WASM sandboxing | High |
| Model Poisoning | Validation set + rollback | Medium |

---

## Recommended Research Agenda

### Immediate Priorities (0-3 months)

1. **WASM Skill Runtime**: Implement wasmtime-based skill execution
2. **QLoRA Pipeline**: Validate 8GB fine-tuning on target hardware
3. **DID:key Integration**: Local wallet with Signal identity anchor

### Medium-Term (3-6 months)

1. **Parent Agent Protocol**: Define skill distillation API
2. **Sleep Mode Automation**: Nightly self-improvement scheduler
3. **Hardware Key Support**: YubiKey unlock integration

### Long-Term (6-12 months)

1. **Skill Marketplace Alternatives**: Curated/audited skill distribution
2. **Federated Learning**: Multi-Noctem collaboration without data sharing
3. **TEE Integration**: Intel SGX/ARM TrustZone for sensitive operations

---

## References (Downloaded Sources)

### Pillar 1: Self-Sovereign Identity
1. `SSI_01_arxiv_2209.11647_architecture_usecases.pdf` - Reece & Mittal (2022). "Self-Sovereign Identity in a World of Authentication: Architecture and Domain Usecases." arXiv:2209.11647
2. `SSI_02_arxiv_2108.08338_systematic_review_taxonomy.pdf` - Schardong & Custódio (2022). "Self-Sovereign Identity: A Systematic Review, Mapping and Taxonomy." arXiv:2108.08338
3. `SSI_03_arxiv_2503.15964_decentralized_identity_apps.pdf` - (2025). "Are We There Yet? A Study of Decentralized Identity Applications." arXiv:2503.15964
4. `SSI_04_arxiv_2404.06729_sok_trusting_ssi.pdf` - Krul et al. (2024). "SoK: Trusting Self-Sovereign Identity." PoPETs 2024. arXiv:2404.06729
5. `SSI_05_arxiv_2409.03624_ssi_gdpr_compliance.pdf` - Shehu (2024). "On the Compliance of Self-Sovereign Identity with GDPR Principles." arXiv:2409.03624

### Pillar 2: Secure Sandboxing (WebAssembly)
6. `SANDBOX_01_arxiv_2407.12297_wasm_security_review.pdf` - (2024). "WebAssembly and Security: A Review." arXiv:2407.12297
7. `SANDBOX_02_arxiv_2408.11456_cage_hw_accelerated_wasm.pdf` - Fink et al. (2024). "Cage: Hardware-Accelerated Safe WebAssembly." CGO 2025. arXiv:2408.11456
8. `SANDBOX_03_arxiv_2601.14555_wasm_iot_sandbox.pdf` - (2026). "WebAssembly Based Portable and Secure Sensor Interface for IoT." arXiv:2601.14555
9. `SANDBOX_04_arxiv_2312.03858_wasm_thin_kernel_interfaces.pdf` - (2025). "Empowering WebAssembly with Thin Kernel Interfaces." arXiv:2312.03858
10. `SANDBOX_05_arxiv_2410.22919_cyberphysical_wasm.pdf` - (2025). "Cyber-physical WebAssembly: Secure Hardware Interfaces and Pluggable Drivers." arXiv:2410.22919

### Pillar 3: Bounded Self-Improvement
11. `SELFIMPROV_01_arxiv_2509.12229_lora_qlora_consumer_gpu.pdf` - Avinash (2025). "Profiling LoRA/QLoRA Fine-Tuning Efficiency on Consumer GPUs: An RTX 4060 Case Study." arXiv:2509.12229
12. `SELFIMPROV_02_arxiv_2507.23536_peft_edge_devices.pdf` - (2025). "From LLMs to Edge: Parameter-Efficient Fine-Tuning on Edge Devices." arXiv:2507.23536
13. `SELFIMPROV_03_arxiv_2511.03765_lora_edge_tensor_train.pdf` - Kwak et al. (2025). "LoRA-Edge: Tensor-Train-Assisted LoRA for Practical CNN Fine-Tuning on Edge Devices." arXiv:2511.03765
14. `SELFIMPROV_04_arxiv_2504.15610_lora_resource_constrained.pdf` - (2025). "A LoRA-Based Approach to Fine-Tuning LLMs for Educational Guidance in Resource-Constrained Settings." arXiv:2504.15610
15. `SELFIMPROV_05_arxiv_2410.16954_lora_cnn_iot.pdf` - (2024). "LoRA-C: Parameter-Efficient Fine-Tuning of Robust CNN for IoT Devices." arXiv:2410.16954

### Pillar 4: Knowledge Transfer
16. `TRANSFER_01_arxiv_2402.13116_kd_llm_survey.pdf` - Xu et al. (2024). "A Survey on Knowledge Distillation of Large Language Models." arXiv:2402.13116
17. `TRANSFER_02_arxiv_2504.14772_kd_dataset_distillation.pdf` - (2025). "Knowledge Distillation and Dataset Distillation of Large Language Models." arXiv:2504.14772
18. `TRANSFER_03_arxiv_2509.26497_post_training_small_lm.pdf` - (2025). "Revealing the Power of Post-Training for Small Language Models via Knowledge Distillation." arXiv:2509.26497
19. `TRANSFER_04_arxiv_2409.12512_online_kd_autoregressive.pdf` - Rao et al. (2024). "Exploring and Enhancing the Transfer of Distribution in Knowledge Distillation for Autoregressive Language Models." arXiv:2409.12512
20. `TRANSFER_05_arxiv_2406.12066_kd_llm_comprehensive.pdf` - (2024). Knowledge Distillation Survey. arXiv:2406.12066

### Pillar 5: Computational Sovereignty
21. `RIGHTS_01_arxiv_2410.17481_ai_global_governance_digital_sovereignty.pdf` - Bullock et al. (2024). "AI, Global Governance, and Digital Sovereignty." arXiv:2410.17481
22. `RIGHTS_02_arxiv_2402.08797_computing_power_ai_governance.pdf` - Sastry et al. (2024). "Computing Power and the Governance of Artificial Intelligence." arXiv:2402.08797
23. `RIGHTS_03_arxiv_2412.13821_ai_proliferation_governance.pdf` - (2024). "Towards Responsibly Governing AI Proliferation." Cambridge MPhil Dissertation. arXiv:2412.13821
24. `RIGHTS_04_arxiv_2202.10069_digital_sovereignty_identity.pdf` - Tan et al. (2022). "Analysis of Digital Sovereignty and Identity: From Digitization to Digitalization." arXiv:2202.10069
25. `RIGHTS_05_arxiv_2505.09757_trustless_autonomy_self_sovereign_ai.pdf` - (2025). "Trustless Autonomy: Understanding Motivations, Benefits and Governance Dilemmas in Self-Sovereign Decentralized AI Agents." arXiv:2505.09757

---

*This report was generated for NotebookLM ingestion. All citations reference downloaded PDF files in the `./noctem_research_v1/` directory.*

*Built with assistance from Warp Agent*
