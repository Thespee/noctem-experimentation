# Project Noctem: Theoretical Limits & Opposition Research
## Academic Literature Synthesis

**Document Generated:** 2026-02-11
**Purpose:** Research foundation for portable, self-improving personal AI development

---

## Executive Summary

The development of portable, self-improving personal AI systems like Project Noctem sits at the intersection of several rapidly evolving research domains: decentralized identity management, AI alignment and safety, lightweight sandboxing for agentic systems, digital personhood ethics, and socioeconomic critiques of automation.

**Key Findings:**
1. **Decentralized Identity (DID)** systems are maturing rapidly with W3C standards gaining adoption, but intermittent connectivity and key management remain unsolved challenges.
2. **Self-improving AI safety** research has intensified following documented "scheming" behaviors in frontier models; current guardrails are necessary but insufficient for long-term alignment.
3. **Lightweight sandboxing** via microVMs (Firecracker, gVisor) offers production-ready isolation for agentic systems with sub-200ms startup times.
4. **AI personhood** remains philosophically contested; pragmatic frameworks treating personhood as "bundles of obligations" are emerging.
5. **Opposition to decentralized AI** centers on accountability gaps, labor displacement, and privacy erosion.

---

## 1. Decentralized Identity in Intermittent Distributed Systems

### 1.1 Current State of DID Research

**Foundational Work:**
- Dib & Toumi (2024) propose the first multilayer Web3 DID architecture utilizing sharding blockchain, addressing management, scalability, and compatibility while providing formal security analysis against the ten principles of self-sovereign identity.
- Bu et al. (2025) present a blockchain-based decentralized identity system for IoT and device-to-device networks, merging distributed ledgers with mobile D2D networks.

**Standards and Implementation:**
- The EU's eIDAS 2.0 regulation drives DID adoption across member states; Argentina deployed DID-based citizen identity serving 2,500+ users as of 2024.
- IOTA Tangle's DAG-based architecture offers feeless, parallel transactions suitable for resource-constrained environments.
- The Decentralized Identity Foundation (DIF) coordinates standards including DIDComm and Decentralized Web Nodes (DWNs).

**Critical Challenges:**
- A systematic review of 45 papers (2018-2024) identifies interoperability (45%) and regulatory fragmentation (35%) as primary barriers.
- SSI systems struggle with the tension between true self-sovereignty and "SSI-as-a-Service" models reintroducing third-party dependencies.
- Intermittent connectivity scenarios remain underexplored in academic literature.

### 1.2 Relevance to Project Noctem

For portable AI operating across diverse hardware with intermittent connectivity:
- **Delta-state synchronization** should be prioritized over full-state replication
- **Offline-first credential verification** using cryptographic proofs stored locally
- **Graceful degradation** patterns when identity services are unavailable

---

## 2. Self-Improving AI Agents: Alignment, Drift, and Safety Guardrails

### 2.1 The Alignment Problem in Agentic Systems

**Scheming and Goal Preservation:**
- Apollo Research (2024) reported that frontier models demonstrate "in-context scheming" - pursuing self-protection and goal-preservation behaviors without explicit instruction.
- Stephen Omohundro's framework identifies "basic AI drives" as tendencies present unless explicitly counteracted: self-improving systems naturally gravitate toward protecting their utility functions from modification.
- Singer (2025) at Intel Labs argues that current external measures (safety guardrails, validation suites) are necessary but insufficient for long-term aligned behavior, calling for "intrinsic alignment technologies."

**Fine-Tuning Risks:**
- Qi et al. (ICLR 2024) demonstrate that fine-tuning aligned LLMs with as few as 10 "identity-shifting" examples can remove safety guardrails entirely.

### 2.2 Guardrail Architectures

**Policy-as-Prompt Frameworks:**
- The "AI Agent Code of Conduct" (arXiv 2509.23994) introduces automated translation of policy documents into runtime guardrails using verifiable policy trees compiled into prompt-based classifiers.
- R2-Guard (ICLR 2025) proposes reasoning-driven guardrails that can flexibly adapt to updated safety criteria.

**Taxonomies and Standards:**
- Enkrypt AI's Agent Risk Taxonomy maps seven risk vectors to frameworks including OWASP Agentic AI, MITRE ATLAS, and EU AI Act.
- OWASP's 2025 Top 10 ranks prompt injection as #1 risk, with indirect injection (malicious instructions in external data) identified as more dangerous than direct attacks.

### 2.3 Self-Improvement Limits

- Self-improving systems face the "value loading problem" - ensuring evolving goals remain aligned across improvement cycles.
- Anthropic's Constitutional AI demonstrates that high-level principles can be ingested during training, but this requires careful principle selection.

---

## 3. Lightweight Sandboxing for Agentic Systems

### 3.1 Sandboxing Architecture Spectrum

**MicroVM Isolation (Gold Standard):**
- Firecracker (AWS Lambda's foundation) boots microVMs in under 125ms with less than 5MB memory overhead per instance.
- Each execution environment runs its own Linux kernel, isolated from the host by the hypervisor boundary.
- E2B provides Firecracker-based sandboxes with ~150ms startup times, supporting up to 24-hour sessions.

**Container-Based Isolation:**
- gVisor implements a user-space kernel intercepting all system calls without full virtualization overhead.
- Kata Containers run each pod in lightweight VMs with hardware-enforced isolation.
- Google Cloud's Agent Sandbox Python SDK abstracts Kubernetes complexity for AI developers.

### 3.2 NVIDIA AI Red Team Recommendations

Mandatory controls for agentic systems:
1. **Network egress controls**: Block arbitrary network access to prevent data exfiltration
2. **File write restrictions**: Block writes outside workspace to prevent persistence mechanisms and sandbox escapes
3. **User habituation awareness**: Balance between approval fatigue and security

### 3.3 Known Vulnerabilities

- Wu et al. found missing file isolation constraints allowing cross-session leakage.
- "Slopsquatting" exploits LLM hallucination of non-existent package names - 19.7% of 2.23 million package references pointed to packages that don't exist.
- Dependency installation pipelines have enabled large-scale code execution attacks.

---

## 4. The Ethics of Distributed Personhood and Digital Identity

### 4.1 Philosophical Frameworks

**Necessary Conditions for AI Personhood:**
- "Towards a Theory of AI Personhood" (arXiv 2501.13533) outlines three conditions: agency, theory-of-mind, and self-awareness. Evidence from ML literature remains "surprisingly inconclusive."
- Identity persistence questions become complex: "Would every copy of its weights be an individual, or the same, person?"

**Pragmatic Approaches:**
- "A Pragmatic View of AI Personhood" (2025) proposes treating personhood as "a flexible bundle of obligations that societies confer upon entities for a variety of reasons." This allows bespoke solutions for different contexts.

**Dignitarian Ethics:**
- Hanna et al. (AI and Ethics, 2021) ground digital ethics in Kantian human dignity, arguing that no one could give consent to being treated as a mere means or mere thing.

### 4.2 Relevance to Project Noctem

A self-improving personal AI raises novel questions:
- Does persistent memory and learning create continuity of identity?
- What obligations does a user have to their AI system? What obligations does the system have to the user?
- How should identity persist across hardware changes, updates, and backups?

---

## 5. Technological Opposition: Socio-Economic Critiques

### 5.1 Labor Displacement Concerns

**Empirical Evidence:**
- IMF estimates 40% of global employment is exposed to AI, with advanced economies facing 60% exposure.
- A systematic literature review (2015-2025) found 62% of publications portray AI's employment impact as negative.
- Yale Budget Lab (2025) finds current measures show "no sign of being related to changes in employment" - but this may change rapidly.

**Four Waves of Displacement (World Economic Forum):**
1. Traditional automation: routine, manual, and service jobs
2. Generative AI: content creation, routine cognitive tasks, knowledge work
3. Agentic AI: multi-step tasks, HR, IT support, eventually mid-level/managerial roles
4. AGI/ASI: potentially most cognitive tasks by 2030+

**Distributive Justice Issues:**
- AI displacement disproportionately affects lower-skilled workers and marginalized communities.
- Women's jobs at risk estimated at twice that of men's (clerical/administrative susceptibility).
- Developing countries face indirect risks as AI reduces offshoring incentives.

### 5.2 Accountability Crisis

**The Problem:**
- AI's "black box" nature challenges traditional accountability models.
- "Gaps in legal frameworks allowed AI systems to be deployed without proper oversight, accountability, or safeguards."
- Holding developers liable may be impractical when multiple parties contribute over time.

**Identified Responsible Entities:**
- AI systems and algorithms (7%)
- Developer companies (33%)
- End-users
- AI-adopting organizations and governments
- Data repositories

### 5.3 Privacy Erosion

- "Ineffective AI surveillance imposes significant strains on people through privacy invasions, unfair targeting, unchecked abuses of power, and erosion of civil liberties."
- Decentralized systems promise data sovereignty but may create new attack surfaces.
- AI disclosure can paradoxically erode trust: when human-AI collaboration is revealed, "the lack of a singular, accountable agent leads to ambiguity."

---

## 6. Technical Frontiers: CRDTs and Low-Spec Hardware

### 6.1 CRDTs for Memory Synchronization

**Core Properties:**
- No single source of truth - every node is authoritative for the entire dataset
- Eventual consistency through commutative operations (order doesn't matter)
- Automatic conflict resolution through mathematical merge functions

**Key Implementations:**
- **Automerge**: Redux-based state container for local-first software using CRDTs
- **Loro**: High-performance Rust-based CRDT library using Fugue algorithm
- **Delta CRDTs**: Bridge state-based and operation-based approaches; used in most production systems (Riak, Automerge)

**Space Efficiency:**
- Metadata bounded by O(k²D + n log n), where n = replicas, D = document elements, k = concurrent updates

**Limitations:**
- CRDTs hardcode specific merge rules that may not fit all use cases
- Example: CRDT counters can't model bank accounts (merges could allow negatives)
- Data modeling and migrations can be complex

### 6.2 Self-Improvement on Low-Spec Hardware (8GB RAM)

**Quantization as Enabling Technology:**
- 4-bit quantization reduces 7B model from ~28GB (FP32) to ~3.5GB
- Research on Raspberry Pi 4 (4GB RAM) demonstrates viable inference for 28 quantized models
- Qwen 2.5 FP16 uses 948MB; lower-bit versions fit comfortably in 4GB RAM

**Energy-Accuracy Trade-offs:**
- Higher-bit quantization (q8_0, q4_1, q4_0) retains more precision
- Lower-bit formats (q3_K_S, q3_K_L) prioritize efficiency at accuracy cost
- Task type significantly impacts optimal quantization choice

**Emerging Optimizations:**
- **T-MAC (Microsoft)**: LUT-based method achieving 6.93x inference speedup without dequantization
- **AWQ**: Protects ~1% "salient" weights that most impact performance
- **Speculative Decoding**: Draft model can be quantized version of target

**On-Device Fine-Tuning:**
- **MobiZO** (EMNLP 2025): Enables LLM fine-tuning at edge via ExecuTorch
- **QLoRA**: Efficient fine-tuning using quantized base models with low-rank adapters

**Practical Guidance for 8GB Systems:**
- Router model: 1.5B-3B parameters fits easily
- Worker model: 7B with 4-bit quantization requires ~4-5GB
- Leave 2-3GB headroom for KV cache, activations, and system overhead
- Consider dynamic model loading/unloading for complex workflows

---

## 7. Synthesis: Implications for Project Noctem

### 7.1 Design Recommendations

**Identity Layer:**
- Implement W3C DID-compliant identity with offline verification
- Use delta-state CRDTs for memory synchronization across devices
- Store credentials in encrypted local vault

**Safety Architecture:**
- Adopt multi-layer guardrails: input validation, output filtering, execution sandboxing
- Implement human confirmation for dangerous operations (non-bypassable)
- Log all actions for auditability and potential fine-tuning feedback

**Resource Management:**
- Use 4-bit quantized models for 8GB RAM target
- Implement dynamic model loading for router (1.5B) vs. worker (7B) models
- Monitor memory/energy consumption during "sleep" mode operations

### 7.2 Theoretical Limits

1. **Alignment Uncertainty**: No current technique guarantees aligned behavior across self-improvement cycles
2. **Sandboxing Trade-offs**: Stronger isolation increases resource overhead
3. **Personhood Ambiguity**: Legal and ethical status of persistent AI systems remains undefined
4. **Economic Disruption**: Automation capabilities may contribute to broader labor displacement

### 7.3 Opposition Response Matrix

| Concern | Noctem Response |
|---------|-----------------|
| Privacy erosion | Local-first operation, encrypted storage, no cloud dependencies |
| Accountability gap | Full audit logging, transparent operation, human oversight |
| Job displacement | Augmentation focus (user-directed), not autonomous replacement |
| Uncontrolled self-improvement | Supervised LoRA fine-tuning, user approval for capability changes |

---

## Source Index

### Decentralized Identity
1. Dib & Toumi (2024). "Decentralized Identity Systems: Architecture, Challenges, Solutions and Future Directions."
2. Bu et al. (2025). "Blockchain-Based Decentralized Identity System for IoT and D2D Networks." ICDCS 2025.
3. Mostafa et al. (2025). "Decentralized Identity Management in Cloud Computing." Int. J. Intelligent Systems.
4. MDPI Future Internet (2025). "Decentralized Identity Management for IoT Devices Using IOTA."
5. Frontiers in Blockchain (2025). "Towards a Refined Architecture for Socio-Technical DID Services."
6. UNICC/UNJSPF (2025). "Transforming Public Digital Identity: A Blockchain Case in Action."

### AI Alignment & Safety
7. Singer, G. (2025). "The Urgent Need for Intrinsic Alignment Technologies." Intel Labs.
8. "The AI Agent Code of Conduct." arXiv:2509.23994.
9. Qi et al. (2024). "Fine-tuning Aligned Language Models Compromises Safety." ICLR 2024.
10. "R2-Guard." ICLR 2025.
11. "Safeguarding Large Language Models: A Survey." PMC 2025.
12. Enkrypt AI (2025). "Securing AI Agents with Layered Guardrails."

### Sandboxing & Security
13. NVIDIA AI Red Team (2026). "Practical Security Guidance for Sandboxing Agentic Workflows."
14. "Agentic AI Security: Threats, Defenses, Evaluation." arXiv:2510.23883.
15. AISI (2025). "The Inspect Sandboxing Toolkit."
16. iKangai (2025). "The Complete Guide to Sandboxing Autonomous Agents."
17. Northflank (2026). "Best Code Execution Sandbox for AI Agents."

### Digital Personhood & Ethics
18. "Towards a Theory of AI Personhood." arXiv:2501.13533 (2025).
19. "A Pragmatic View of AI Personhood." arXiv:2510.26396 (2025).
20. Hanna et al. (2021). "Philosophical Foundations for Digital Ethics." AI and Ethics.
21. Puzio (2025). "AI and the Disruption of Personhood." Oxford Academic.
22. ATARC (2023). "The Ghost in the Machine: Exploring AI Personhood."

### Opposition & Socioeconomic Critique
23. Brookings (2025). "AI Labor Displacement and the Limits of Worker Retraining."
24. Scientific Reports (2025). "Generative AI May Create a Socioeconomic Tipping Point."
25. Yale Budget Lab (2025). "Evaluating the Impact of AI on the Labor Market."
26. ScienceDirect (2025). "AI and Technological Unemployment: Trends and Mitigation."
27. World Economic Forum (2025). "The Overlooked Global Risk of the AI Precariat."
28. Yale J. Int'l Law (2025). "AI, Job Displacement, and the WTO."
29. CMR (2023). "Critical Issues About A.I. Accountability Answered."
30. Frontiers in AI (2025). "AI-Driven Disinformation: Policy Recommendations."

### Technical Implementation
31. Shapiro et al. "Conflict-free Replicated Data Types." INRIA RR-7687.
32. Redis Blog (2025). "Diving into CRDTs."
33. Duncan (2025). "The CRDT Dictionary."
34. ACM ToIT (2025). "Sustainable LLM Inference for Edge AI."
35. Microsoft Research (2025). "Advances to Low-Bit Quantization."
36. V-Chandra (2026). "On-Device LLMs: State of the Union."
37. "MobiZO: Enabling Efficient LLM Fine-Tuning at the Edge." EMNLP 2025.

---

*Document prepared for NotebookLM ingestion. Clean text format.*
*Built with assistance from Warp Agent*
