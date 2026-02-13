# 📚 Project Noctem Research Sources Index
## 25 Academic and Technical References

Generated: 2026-02-11

---

## Download Instructions

Most sources are available as PDFs from arXiv or as web articles. Use the URLs below to access each source.

### PDF Downloads (arXiv)
```powershell
# Example download commands for arXiv papers
curl -o "distributed_identity_study.pdf" "https://arxiv.org/pdf/2503.15964"
curl -o "did_vc_survey.pdf" "https://arxiv.org/pdf/2402.02455"
curl -o "crdt_approaches.pdf" "https://arxiv.org/pdf/2310.18220"
curl -o "crdt_original.pdf" "https://pages.lip6.fr/Marc.Shapiro/papers/RR-7687.pdf"
curl -o "lora_qlora_consumer_gpu.pdf" "https://arxiv.org/pdf/2509.12229"
curl -o "llm_self_improvement_limits.pdf" "https://arxiv.org/pdf/2601.05280"
curl -o "model_merging_survey.pdf" "https://arxiv.org/pdf/2408.07666"
curl -o "merge_to_learn.pdf" "https://arxiv.org/pdf/2410.12937"
curl -o "cross_arch_merging.pdf" "https://arxiv.org/pdf/2602.05495"
curl -o "single_multi_evolution.pdf" "https://arxiv.org/pdf/2602.05182"
```

---

## Source Catalog

### Pillar 1: Distributed Identity & Memory Synchronization

#### Source 1: Decentralized Identity Applications Study
- **Title:** "Are We There Yet? A Study of Decentralized Identity Applications"
- **URL:** https://arxiv.org/html/2503.15964v1
- **arXiv ID:** 2503.15964
- **Date:** March 2025
- **Type:** Comprehensive Survey
- **Key Content:** Analysis of real-world DI/SSI deployments including QuarkID (Argentina), Gataca (EU universities), IDunion (Germany)

#### Source 2: SSI on Blockchain
- **Title:** "Self-sovereign identity on the blockchain: contextual analysis and quantification of SSI principles implementation"
- **URL:** https://www.frontiersin.org/journals/blockchain/articles/10.3389/fbloc.2024.1443362/full
- **DOI:** 10.3389/fbloc.2024.1443362
- **Date:** August 2024
- **Type:** Research Paper
- **Key Content:** SSI as fundamental human right, W3C standards alignment, KILT Protocol analysis

#### Source 3: SSI Systematic Review
- **Title:** "Self-Sovereign Identity: A Systematic Review, Mapping and Taxonomy"
- **URL:** https://pmc.ncbi.nlm.nih.gov/articles/PMC9371034/
- **PMC ID:** 9371034
- **Date:** 2022
- **Type:** Systematic Review
- **Key Content:** DID standard metamodel, backup/recovery mechanisms, four SSI components

#### Source 4: DID and VC Survey
- **Title:** "A Survey on Decentralized Identifiers and Verifiable Credentials"
- **URL:** https://arxiv.org/html/2402.02455v1
- **arXiv ID:** 2402.02455
- **Date:** February 2024
- **Type:** Survey
- **Key Content:** DIDs beyond individuals (IoT, cloud, edge), implementation analysis, regulations

#### Source 5: DID/SSI Design Aspects
- **Title:** "Design Aspects of Decentralized Identifiers and Self-Sovereign Identity Systems"
- **URL:** https://www.researchgate.net/publication/380204767
- **DOI:** 10.1109/ACCESS.2024.3394537
- **Date:** 2024
- **Type:** IEEE Access Paper
- **Key Content:** SSI Trust Triangle architecture, identity infrastructure proposals

#### Source 6: Blockchain-Based SSI Framework
- **Title:** "Decentralized Identity Management Using Self-Sovereign Identity Approach Through Blockchain"
- **URL:** https://link.springer.com/chapter/10.1007/978-981-97-7710-5_5
- **DOI:** 10.1007/978-981-97-7710-5_5
- **Date:** ICICCT 2024
- **Type:** Conference Paper
- **Key Content:** Evolution from centralized to user-centric identity paradigms

#### Source 7: CRDT Foundational Paper
- **Title:** "Conflict-free Replicated Data Types"
- **URL:** https://pages.lip6.fr/Marc.Shapiro/papers/RR-7687.pdf
- **Authors:** Shapiro, Preguiça, Baquero, Zawirski
- **Date:** 2011
- **Type:** Foundational Research
- **Key Content:** Original CRDT formalization, state-based vs operation-based approaches

#### Source 8: CRDT Approaches Survey
- **Title:** "Approaches to Conflict-free Replicated Data Types"
- **URL:** https://arxiv.org/pdf/2310.18220
- **arXiv ID:** 2310.18220
- **Date:** October 2023
- **Type:** Survey
- **Key Content:** Pure op-based CRDTs, causal stability, delta CRDTs

---

### Pillar 2: Secure Execution & Sandboxing

#### Source 9: Firecracker Documentation
- **Title:** AWS Firecracker - Secure and fast microVMs for serverless computing
- **URL:** https://github.com/firecracker-microvm/firecracker
- **Type:** Technical Documentation
- **Key Content:** <125ms boot, <5MB overhead, KVM-based isolation, Jailer security model

#### Source 10: Firecracker Announcement
- **Title:** "Announcing the Firecracker Open Source Technology"
- **URL:** https://aws.amazon.com/blogs/opensource/firecracker-open-source-secure-fast-microvm-serverless/
- **Date:** 2018 (updated 2020)
- **Type:** Technical Announcement
- **Key Content:** AWS Lambda/Fargate foundation, Rust implementation, minimal device model

#### Source 11: Isolation Technology Comparison
- **Title:** "Firecracker, gVisor, Containers, and WebAssembly - Comparing Isolation Technologies for AI Agents"
- **URL:** https://www.softwareseni.com/firecracker-gvisor-containers-and-webassembly-comparing-isolation-technologies-for-ai-agents/
- **Date:** 2026
- **Type:** Comparison Guide
- **Key Content:** Security hierarchy, threat models, cold start tradeoffs

#### Source 12: Awesome Sandbox Collection
- **Title:** "Awesome Code Sandboxing for AI"
- **URL:** https://github.com/restyler/awesome-sandbox
- **Type:** Resource Collection
- **Key Content:** MicroVM security models, gVisor vs Firecracker, WASM limitations

#### Source 13: Firecracker vs QEMU
- **Title:** "Firecracker vs QEMU"
- **URL:** https://e2b.dev/blog/firecracker-vs-qemu
- **Type:** Technical Comparison
- **Key Content:** VMM architecture differences, KVM integration, use cases

#### Source 14: Secure Runtime for Codegen
- **Title:** "Secure runtime for codegen tools: microVMs, sandboxing, and execution at scale"
- **URL:** https://northflank.com/blog/secure-runtime-for-codegen-tools-microvms-sandboxing-and-execution-at-scale
- **Date:** 2026
- **Type:** Technical Guide
- **Key Content:** Kata Containers integration, 2M+ monthly microVMs at Northflank

---

### Pillar 3: Recursive Self-Improvement & Fine-Tuning

#### Source 15: LoRA/QLoRA Consumer GPU Benchmark
- **Title:** "Profiling LoRA/QLoRA Fine-Tuning Efficiency on Consumer GPUs: An RTX 4060 Case Study"
- **URL:** https://arxiv.org/html/2509.12229
- **arXiv ID:** 2509.12229
- **Date:** September 2025
- **Type:** Benchmark Study
- **Key Content:** 8GB VRAM feasibility, PagedAdamW optimization, fp16 vs bf16

#### Source 16: LLM Self-Improvement Limits
- **Title:** "On the Limits of Self-Improving in LLMs and Why AGI, ASI and the Singularity Are Not Near Without Symbolic Model Synthesis"
- **URL:** https://arxiv.org/html/2601.05280
- **arXiv ID:** 2601.05280
- **Date:** January 2026
- **Type:** Theoretical Research
- **Key Content:** Entropy decay proofs, model collapse mathematics, Kantian analysis framework

#### Source 17: LoRA vs QLoRA Guide
- **Title:** "LoRA vs. QLoRA: Efficient fine-tuning techniques for LLMs"
- **URL:** https://modal.com/blog/lora-qlora
- **Type:** Technical Guide
- **Key Content:** Memory reduction (4x with QLoRA), practical implementation

#### Source 18: Illusion of Self-Improvement
- **Title:** "The Illusion of Self-Improvement: Why AI Can't Think Its Way to Genius"
- **URL:** https://medium.com/@vishalmisra/the-illusion-of-self-improvement-why-ai-cant-think-its-way-to-genius
- **Date:** June 2025
- **Type:** Analysis
- **Key Content:** Entropic drift lemma, CoT limitations, external grounding requirements

#### Source 19: RSI Theoretical Overview
- **Title:** "Recursive Self-Improvement" (Alignment Forum)
- **URL:** https://www.alignmentforum.org/w/recursive-self-improvement
- **Type:** Wiki/Overview
- **Key Content:** Yudkowsky's hard/soft takeoff arguments, seed AI concepts

#### Source 20: RSI Topic Synthesis
- **Title:** "Recursive Self-Improvement" (Emergent Mind)
- **URL:** https://www.emergentmind.com/topics/recursive-self-improvement
- **Type:** Research Synthesis
- **Key Content:** Information-theoretic bounds, LADDER framework, self-rewarding approaches

---

### Pillar 4: Competency Sharing & Model Merging

#### Source 21: Model Merging Survey
- **Title:** "Model Merging in LLMs, MLLMs, and Beyond: Methods, Theories, Applications and Opportunities"
- **URL:** https://arxiv.org/html/2408.07666v1
- **arXiv ID:** 2408.07666
- **Date:** August 2024
- **Type:** Comprehensive Survey
- **Key Content:** Skill-specific expert merging, cross-modal applications, detoxification

#### Source 22: Merge to Learn
- **Title:** "Merge to Learn: Efficiently Adding Skills to Language Models with Model Merging"
- **URL:** https://arxiv.org/abs/2410.12937
- **arXiv ID:** 2410.12937
- **Authors:** Morrison et al. (Allen Institute for AI)
- **Date:** October 2024
- **Type:** Research Paper
- **Key Content:** Parallel-train-then-merge framework, safety feature integration

#### Source 23: Cross-Architecture Merging
- **Title:** "Transport and Merge: Cross-Architecture Merging for Large Language Models"
- **URL:** https://arxiv.org/html/2602.05495
- **arXiv ID:** 2602.05495
- **Date:** February 2026
- **Type:** Research Paper
- **Key Content:** High-resource to low-resource transfer, cross-lingual knowledge transfer

#### Source 24: Single-Multi Evolution Loop
- **Title:** "The Single-Multi Evolution Loop for Self-Improving Model Collaboration Systems"
- **URL:** https://arxiv.org/html/2602.05182
- **arXiv ID:** 2602.05182
- **Date:** February 2026
- **Type:** Research Paper
- **Key Content:** Multi-LLM collaboration distillation, 8-15% improvement gains

#### Source 25: Awesome Model Merging
- **Title:** "Model Merging in LLMs, MLLMs, and Beyond" (GitHub Collection)
- **URL:** https://github.com/EnnengYang/Awesome-Model-Merging-Methods-Theories-Applications
- **Type:** Resource Collection
- **Key Content:** LoraHub, TIES, DARE, continual learning applications

---

## Star Trek References

### Primary Episode Sources

1. **"The Measure of a Man"** (TNG S2E9, 1989)
   - Memory Alpha: https://memory-alpha.fandom.com/wiki/The_Measure_Of_A_Man_(episode)
   - IMDb: https://www.imdb.com/title/tt0708807/
   - Key Theme: AI personhood, rights of sentient beings

2. **"The Offspring"** (TNG S3E16, 1990)
   - Theme: AI creating AI, individual development

3. **"The Quality of Life"** (TNG S6E9, 1992)
   - Theme: Emergent sentience, self-preservation

4. **Star Trek: Discovery Season 3-4** (2020-2022)
   - Memory Alpha: https://memory-alpha.fandom.com/wiki/Programmable_matter
   - Key Technology: Programmable matter, 32nd-century Federation

---

## Notes

- All arXiv papers are freely accessible
- Web articles may be subject to paywalls or registration
- Star Trek content is copyrighted by Paramount/CBS
- Academic citations follow standard formats for each source type

*Generated for Project Noctem research purposes*
