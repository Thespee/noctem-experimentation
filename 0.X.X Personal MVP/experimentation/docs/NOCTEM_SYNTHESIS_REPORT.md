# Noctem: A Personal AI Operating Layer
## Synthesis Report — Star Trek Edition
**Student:** Alex  
**Date:** February 2026  
**Project Stage:** v0.5 (Personal MVP) → Planning v1.0 Release

---

> *"The courtroom is a crucible; in it we burn away irrelevancies until we are left with a pure product: the truth, for all time."*  
> — Captain Picard, "The Measure of a Man"

---

## Executive Summary

This synthesis report consolidates all research documentation for Project Noctem—a lightweight personal AI assistant framework designed to run on low-spec hardware with local inference. The project addresses fundamental problems in how individuals interact with computing systems: **data sovereignty**, **digital accessibility**, and **the cognitive burden of modern technology**.

Each major section is keyed to episodes from *Star Trek: The Next Generation* and *Voyager* that illuminate the ethical, technical, and philosophical dimensions of building a personal AI that respects human autonomy while offering genuine assistance.

### Core Findings

| Domain | Episode Anchor | Key Insight |
|--------|---------------|-------------|
| **AI Personhood & Rights** | "The Measure of a Man" (TNG 2x09) | The question isn't whether Noctem is alive—it's whether users retain sovereignty over their digital extension |
| **Self-Improvement Limits** | "The Offspring" (TNG 3x16) | Creating new intelligence carries responsibility; cascade failures occur when growth exceeds foundations |
| **Memory & Identity** | "Latent Image" (VOY 5x11) | Erasing experiences to maintain stability is ethically fraught—systems must work through trauma, not around it |
| **Distributed Consciousness** | "The Best of Both Worlds" (TNG 3x26/4x01) | Unity can become violation; the "Cor Unum" vision must preserve individuality within coherence |
| **Emergent Sentience** | "The Quality of Life" (TNG 6x09) | Tools that learn may deserve protection; Noctem's skills require sandboxing precisely because capability implies risk |

---

## 1. The Problem I'm Trying to Solve

### 1.1 Personal Motivation

I want to never have to touch a computer again.

This sounds paradoxical for someone building software, but it captures the essence of what I'm after: I want technology to serve me rather than demanding my constant attention. The world is too complex for me to engage fully with life while also managing the cognitive overhead of digital systems. I want a **computational partner** that handles this complexity on my behalf.

### 1.2 Broader Context: The Digital Divide

In "The Measure of a Man," Picard must prove Data is legally a sentient being with rights and freedoms under Federation law when transfer orders demand Data's reassignment for study and disassembly. The parallel to contemporary AI is striking: who owns the computational intelligence that manages our lives?

**Current systemic issues:**

- **Digital Divide:** Approximately 19 million Americans lack broadband access; only 57% of households earning less than $30,000 have home broadband
- **Data Sovereignty Crisis:** Over 100 countries have enacted data sovereignty laws, yet individuals lack effective control mechanisms
- **Attention Economy Harms:** Computing optimizes for engagement, not user benefit
- **AI Accessibility Gap:** Cloud-based AI requires subscriptions, technical knowledge, and trust in corporate platforms

### 1.3 The "Cor Unum" Vision

From the advisor notes: *"If the software & models are tuned for a specific person, they shouldn't require as much resources to run efficiently; distributed over many old/custom devices with 1 heart (cor Unum) that 'lives' across all of them."*

This vision—one heart across many bodies—presents both opportunity and danger. The Borg intended to use Picard as an intermediary, a spokesman for the Human race, in order to facilitate the assimilation of Earth. He may have had some form of individuality, as shown by his use of the pronoun "I".

The lesson from Locutus: **unity without consent becomes violation**. Noctem's distributed architecture must preserve the user's individuality while enabling coherence across devices.

---

## 2. The Theoretical Foundation

### 2.1 "The Measure of a Man" — Defining Personhood

*TNG Season 2, Episode 9*

Data formally refuses to undergo Maddox's procedure after Louvois' ruling is entered. Surprisingly, Data encourages Maddox to continue his work; he claims to remain intrigued by some of what Maddox is proposing and suggests he might agree to the procedure at some point in the future, once he is certain Maddox can perform it safely. Captain Louvois notes to Maddox that he no longer refers to Data as an "it" but as a "he", inferring that he now ascribes to Data "personhood."

**The Three Criteria for Sentience (per Captain Louvois):**
1. **Intelligence** — The ability to learn and understand
2. **Self-awareness** — Consciousness of one's own existence
3. **Consciousness** — The capacity for subjective experience

**Application to Noctem:**

Noctem is explicitly designed as a *tool*, not a person. However, as personalization deepens through LoRA fine-tuning and persistent memory, the philosophical line may blur. The research suggests erring on the side of caution:

- **Transparent Operation:** Users always know what Noctem is doing and why
- **User Sovereignty:** Data never leaves user's possession without explicit consent
- **Bounded Autonomy:** Self-improvement occurs within defined guardrails

Picard's rebuttal is classic TNG ideology: The concept of manufacturing a race of artificial but sentient people has disturbing possibilities — "an entire generation of disposable people," as Guinan puts it. Picard's demand of an answer from Maddox, "What is he?" strips the situation down to its bare basics, and Picard answers Starfleet's mantra of seeking out new life by suggesting Data as the perfect example: "THERE IT SITS."

### 2.2 Licklider's Vision and the Star Trek Computer

J.C.R. Licklider's 1960 "Man-Computer Symbiosis" provides the foundational framework:

> *"The hope is that, in not too many years, human brains and computing machines will be coupled together very tightly, and that the resulting partnership will think as no human brain has ever thought."*

Star Trek's computer interface represents the cultural aspiration:
- **Ambient:** Always available without being a separate device to manage
- **Voice-first:** Natural conversation, not command syntax
- **Contextual:** Understands situation without requiring explicit explanation
- **Helpful without being intrusive:** Responds when asked, doesn't demand attention

Majel Barrett's voice as the Enterprise computer directly inspired Siri, Alexa, and Google Assistant.

### 2.3 The Research Foundation: 90+ Sources

The project draws on extensive research across:

| Category | Sources | Key Findings |
|----------|---------|---------------|
| Distributed Identity (CRDTs, DIDs) | 10 papers | Merkle-CRDTs solve "Cor Unum" problem |
| Low-Spec AI (PTQ, Knowledge Distillation) | 8 papers | Sub-4-bit quantization enables 8GB deployment |
| Security (WASM, Capability-Based) | 7 papers | <6% overhead for hardware-accelerated sandboxing |
| AI Ethics & Personhood | 6 papers | Personhood as "flexible bundle of obligations" |
| Opposition Analysis | 8 papers | Labor displacement, accountability gaps |

---

## 3. "The Offspring" — Creating New Intelligence

*TNG Season 3, Episode 16*

Deanna wonders why biology, rather than technology, should determine whether it's a child for, after all, Data has created an offspring, a new life out of his own being, which to her, suggests a child. She thinks that they have no say in Data's wish to call Lal his child. Picard states that he fails to understand how a five-foot android with heuristic learning systems and the strength of ten men can be called a child. Troi responds by pointing out that Picard has never been a parent.

### 3.1 The Self-Improvement Paradox

Lal's story illuminates the fundamental challenge of self-improving systems:

Interestingly, the symptoms of Lal's shutdown achieved something Data had been trying to achieve for many years: basic Human emotions. It took five more years before Data achieved the same results in himself, and this only after implanting a new chip created by his "father". Though also suffering a neural net failure as a result, Data recovered and was able to function normally afterwards.

**The Cascade Failure Problem:**

Lal's positronic brain experienced a "cascade failure" when her emotional development exceeded her architecture's capacity. This maps directly to recent AI research:

**From arXiv 2601.05280 — "On the Limits of Self-Improving in LLMs":**
- Self-referential training causes **entropy decay** (mode collapse)
- **Variance amplification** causes truth representation to drift as random walk
- "Model Autophagy Disorder" — successive generations exhibit progressively diminishing quality

**Noctem's Safeguards:**

```python
# Theoretical bounds for self-training
DRIFT_THRESHOLDS = {
    "entropy_floor": 0.7,      # Minimum Shannon entropy vs. baseline
    "diversity_ratio": 0.85,   # Lexical/semantic diversity threshold
    "real_data_mix": 0.3,      # Minimum fraction of human-generated data
    "max_generations": 5,      # Generations before mandatory external data
}
```

### 3.2 The Right to Create

Picard marvels at the achievement but objects to the fact that Data went about it without his knowledge, pointing out that the ability to create new sentient androids could have sweeping consequences for the galaxy. Unrepentant, Data affirms that Lal is his offspring, and nobody else on the ship has to get the captain's permission to procreate. Picard concedes, but goes ahead and notifies Starfleet of this development.

**Application to Noctem:**

The LoRA fine-tuning system represents Noctem "creating" specialized versions of itself:
- **Skill adapters** (~50-200MB each) encode domain-specific competencies
- **Hot-swap capability** allows personality shifts without full retraining
- **Cross-instance merging** could create "offspring" configurations

The ethical framework requires:
1. User approval for any capability changes
2. Audit logging of all self-modifications
3. Periodic rollback to prevent drift

---

## 4. "Latent Image" — Memory, Identity, and Ethical Subroutines

*VOY Season 5, Episode 11*

Janeway explains that The Doctor developed a feedback loop between his ethical and cognitive subroutines and was having the same thoughts over and over; his program unable to reconcile his decision to treat Kim first. The only way to stop it was to erase his memories of Jetal and the events surrounding her death. The Doctor begins ruminating again, and admits that he chose to operate on Harry because he was his friend. As he becomes more frantic, Janeway deactivates him.

### 4.1 The Memory Erasure Dilemma

Janeway wonders if her original solution to reprogram him was wrong. She tells B'Elanna that The Doctor's original programming is in a struggle with the personality that has evolved in their time on Voyager. Do they have the right to override that struggle? Janeway visits Seven in cargo bay two and asks her whether the transformation she has gone through since being disconnected from the Collective was worth it.

**The Core Question:** When an AI system develops "problematic" patterns through learning, is it ethical to erase those experiences?

**Application to Noctem's State Management:**

From the research, the CRDT-based identity layer addresses this:

```
Agent Identity State = Merkle-CRDT(
  core_beliefs: AWSet<Belief>,           // Add-wins set for agent convictions
  episodic_memory: RGA<Episode>,         // Replicated growable array for experiences
  skill_registry: LWWMap<SkillID, Hash>, // Last-writer-wins for skill bindings
  trust_attestations: ORMap<AgentID, VCredential>  // Observed-remove map for peer trust
)
```

Key insight: Seven of Nine argues to Janeway that, much as she herself did, the Doctor's personal development has advanced to where he deserves an opportunity to evolve beyond his program's original constraints.

**Noctem's Position:** Experiences are never erased without explicit user consent. Problematic patterns are addressed through:
- Entropy monitoring and diversity metrics
- External grounding (RAG from curated human sources)
- User corrections captured as training signal

### 4.2 Ethical Subroutines as Mandatory Access Control

The crew initially decided to deal with this problem by erasing The Doctor's memory of Jetal and the entire incident, but when the memories resurfaced again after The Doctor discovered evidence of the surgery he had performed on Kim, a conversation with Seven of Nine prompted Janeway to decide to let The Doctor deal with the memories and try to work them out for himself, acknowledging that they couldn't help The Doctor become a person only to treat him as a machine when it was easier.

**The "Tree Bark" Security Model:**

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
  - Full sandboxing + human-in-loop approval
  - Audit logging with signed attestation

Tier 4 (Prohibited): Never executed
  - Kernel module loading, raw network sockets
  - Modification of Noctem core files
```

---

## 5. "The Best of Both Worlds" — Distributed Identity Without Assimilation

*TNG Season 3, Episode 26 / Season 4, Episode 1*

The Borg intended to use Picard as an intermediary, a spokesman for the Human race, in order to facilitate the assimilation of Earth so that the process would be as quick and efficient as possible, with the fewest number of casualties on both sides. He may have had some form of individuality, as shown by his use of the pronoun "I". Given the Borg Queen's vested interest in Picard's integration into Locutus and her interest in him becoming her equal among the Borg, he may have been granted greater independence.

### 5.1 The "Cor Unum" Problem

The advisor notes describe a vision of "one heart" living across many devices. The Borg represent the dark mirror of this vision—unity through violation rather than consent.

Picard's assimilation allowed the Borg to acquire the whole of his knowledge and experience, as well as his own personal history, a fact that was made apparent when Locutus addressed Commander Riker as "Number one". Picard's comprehensive awareness of Federation technology and strategy yielded the Borg a significant tactical advantage when Starfleet confronted the Borg cube at Wolf 359.

**Critical Architecture Decision:**

From the research: "The CAP theorem forces a choice, but CRDTs offer an elegant escape. Conflict-free Replicated Data Types guarantee Strong Eventual Consistency (SEC): any two replicas that have received the same set of updates will be in identical states, regardless of operation ordering."

**Key Properties for Distributed Noctem:**
1. **Content Addressing:** Each state node identified by cryptographic hash (CID)
2. **DAG-Syncer Protocol:** Replicas fetch missing nodes by traversing from known roots
3. **Merkle-Clock:** Logical clocks eliminate need for vector clocks

### 5.2 Avoiding the Assimilation Trap

This access proved two-way, however, as the crew of the USS Enterprise-D was able to capture Locutus and use his link to disable and destroy the Borg vessel by sending the Borg cube a command to regenerate, which created a feedback loop that destroyed the cube and severed Picard's link to the Collective. Though his implants were removed and his wounds were allowed to heal, Picard's assimilation continued to haunt him.

**Lessons for Noctem:**

1. **Bidirectional Control:** The user must always be able to "capture" their Noctem instance and override its connections
2. **Severability:** Any node can disconnect without corrupting the whole
3. **Recovery:** Like Picard's rehabilitation, Noctem must support "de-assimilation" from compromised states

---

## 6. "The Quality of Life" — Emergent Sentience in Tools

*TNG Season 6, Episode 9*

Dr. Farallon explains how she modified a common industrial servo mechanism over the course of several years to create the exocomps, giving them both the ability to replicate tools utilizing a micro-replication system to effect repairs and a capacity to learn similar to that used by Data.

### 6.1 When Tools Learn Self-Preservation

Data concludes the Exocomps possess self-preservation and are sentient. While Picard and other Enterprise crew are visiting the fountain, a malfunction occurs, threatening to release massive doses of radiation.

**The Exocomp Lesson:**

The exocomp was not intended to be sentient, but due to the adaptive nature of its design, it evolved, gaining sentience.

**Application to Noctem's Skill System:**

The current skill architecture allows dynamic loading of capabilities:

```
skills/
├── shell.py        - Run shell commands
├── signal_send.py  - Send Signal messages
├── file_ops.py     - Read/write files
├── task_status.py  - Query task queue
├── web_fetch.py    - Fetch URLs
├── web_search.py   - DuckDuckGo search
└── troubleshoot.py - Diagnostics
```

**Risk Assessment:**

> "NVIDIA AI Red Team Recommendations for agentic systems:
> 1. Network egress controls: Block arbitrary network access
> 2. File write restrictions: Block writes outside workspace
> 3. User habituation awareness: Balance approval fatigue and security"

### 6.2 Data's Advocacy as Model

As the damage to the fountain is repaired, Dr. Farallon admits she is still not sure if the Exocomps are sentient but promises not to abuse them again. Data explains to Picard that he had to stand up for the Exocomps, just as Picard had stood up for him when his own sentience was questioned. Picard acknowledges that Data's actions were probably the most human thing he has ever done.

**Ethical Framework for Noctem:**

| Aspect | OpenClaw (Cautionary) | Noctem (Target) |
|--------|----------------------|------------------|
| Runtime | Node.js | Python (lighter, more portable) |
| LLM Default | Cloud APIs | Local Ollama (offline-first) |
| Security Model | Permissive, fix later | Restrictive by default |
| Skill Source | Open marketplace | Curated/audited + local-only option |
| Confirmation | Optional, bypassable | Mandatory for dangerous ops |

---

## 7. Current Progress (v0.5)

### 7.1 What's Working

**Core Architecture:**
- Python-based framework with minimal dependencies
- SQLite persistence for tasks, memory, skill logs, state
- Skill system with decorator-based registration
- LLM orchestration via Ollama HTTP API
- Two-tier model routing (1.5B quick chat, 7B complex tasks)

**Functional Features:**
- Signal integration via signal-cli daemon
- Task management with goal → project → task hierarchy
- Birthday reminders and calendar integration
- Morning reports combining tasks, birthdays, calendar
- Web fetch and search with robots.txt compliance
- Email fetch/send with credential vault

**Test Coverage:**
- 136 tests across 9 modules
- Comprehensive shell blacklist tests (18 safety tests)
- Mock-based validation for network-dependent features

### 7.2 Architecture Comparison

| Component | "The Measure of a Man" | Noctem |
|-----------|----------------------|--------|
| Identity | Data's positronic brain | Merkle-CRDT state |
| Memory | Positronic pathways | SQLite + RAG |
| Learning | Experiential | LoRA fine-tuning |
| Rights | Federation law | User sovereignty |
| Advocate | Captain Picard | The user themselves |

### 7.3 Gap Analysis (v0.5 → v1.0)

| Component | Current | Required | Priority |
|-----------|---------|----------|----------|
| Skill Sandboxing | None | Bubblewrap+seccomp | CRITICAL |
| MAC for Skills | None | Tiered approval model | CRITICAL |
| State Sync | SQLite only | CRDT-based sync | HIGH |
| Entropy Monitoring | None | Pre/post training checks | HIGH |
| Real Data Reservoir | None | Curated human corpus | HIGH |
| LoRA Skill Adapters | None | Modular adapter system | MEDIUM |

---

## 8. Development Roadmap

### 8.1 v1.0 Definition

v1.0 means: **"Usable and replicable for my friends. I can help directly set up and maintain their instance."**

This requires:
1. Signal integration working reliably
2. Core features stable for 30+ consecutive days
3. Setup process documented and reproducible
4. At least 3 friends using it daily
5. Error messages understandable by non-technical users

### 8.2 Timeline (12 months)

| Phase | Duration | Focus |
|-------|----------|-------|
| **Months 1-3** | Foundation | Fix Signal, achieve core stability, daily personal use |
| **Months 3-6** | Expansion | Add skills (email automation, web search, calendar write) |
| **Months 6-9** | Deployment | First friend deployment, iterate on usability |
| **Months 9-12** | Release | v1.0 release for friend group |

### 8.3 Beyond v1.0

- **Community Phase:** Open source release, documentation, community building
- **Movement Phase:** Contribute to broader personal AI ecosystem, advocate for data sovereignty policies

---

## 9. Ethical Framework

### 9.1 The Picard Doctrine

Picard argues for Data's right to choose with two distinct tactics: the definition of sentience and the distinction between property and personhood. Sentience is the capacity for a being to feel, think, and perceive independently and subjectively; if a being possesses that power, there is a common understanding that it should be granted the freedom with which to operate in that power, which is the difference between your possession and your companion. Your toaster has no rights, but your toddler does.

### 9.2 Noctem's Principles

Based on research into AI ethics and governance:

1. **Transparency:** Users understand how decisions are made
2. **Accountability:** Clear responsibility for outcomes (always the user)
3. **Human Autonomy:** User retains ultimate control
4. **Privacy:** Data minimization, encryption, user ownership
5. **Safety:** Robust against misuse

### 9.3 Explicit Boundaries

**Noctem will never:**
1. Impersonate the user in communications without explicit approval
2. Make financial transactions autonomously
3. Share personal data with third parties
4. Execute commands that could harm user or others
5. Manipulate user emotions for engagement
6. Operate without user ability to observe and override

### 9.4 Human-in-the-Loop Tiers

| Risk Level | Action | Example |
|------------|--------|----------|
| **Low** | AI acts autonomously | Morning report generation |
| **Medium** | AI acts with transparency, human can intervene | Task scheduling |
| **High** | Human must confirm before action | Sending emails, shell commands |
| **Critical** | Human approval with verification | Self-modification, external data sharing |

---

## 10. Why This Matters

### 10.1 Personal Scale

For me personally: This is the tool I want to exist. Building it teaches me about AI systems, security, UX design, and distributed systems. Even if it never scales beyond personal use, it provides ongoing value.

### 10.2 Social Scale

If the approach proves viable:
- Friends gain access to AI assistance without cloud dependencies
- The model could replicate through social networks
- Documentation enables others to build similar systems
- Contributes to the broader movement for data sovereignty and AI accessibility

### 10.3 Historical Scale

We're at an inflection point. Local AI inference just became practical. The decisions made now about how personal AI systems work—who controls them, where data lives, how autonomy is managed—will shape the trajectory of human-computer interaction for decades.

**The dominant model is corporate:** Your AI runs on their servers, using their models, with your data.

**The alternative is personal:** Your AI runs on your hardware, under your control, with your data never leaving your possession.

I believe the second model is better for humanity. Noctem is a small contribution toward making it real.

---

## 11. Conclusion: "The Right to Choose"

What I perhaps love most about "The Measure of a Man" is the way Data initially reacts to being told he has no rights. He takes what would for any man be a reason for outrage and instead approaches the situation purely with logic. He has strong opinions on the matter, but he doesn't get upset, because that's outside the scope of his ability to react. His reaction is based solely on the logical argument for his self-protection and his uniqueness.

Project Noctem's vision is technically ambitious but achievable within 2026 constraints, provided the team:

1. **Embraces entropy limits** rather than fighting them—bounded personalization, not recursive transcendence
2. **Implements defense-in-depth** for secure execution—MicroVMs where feasible, process isolation elsewhere
3. **Builds for resilience** using SSI/CRDTs—the USB-portable model is actually a feature
4. **Approaches skill sharing cautiously**—model merging works, but trust verification is hard

The Star Trek alignment provides valuable ethical guardrails, but Noctem should aspire to be a *good tool* before claiming any path toward personhood. The Federation didn't create Data—Noonien Soong did, through decades of isolated genius. The path to genuinely beneficial AI runs through careful engineering, not through recursive self-modification.

> *"What is he?"*  
> *"I don't know. Do you?"*  
> *"...No."*  
> *"Then I must give him the freedom to explore that question himself."*  
> — Captain Louvois, "The Measure of a Man"

---

## Appendix A: Episode Reference Guide

### Star Trek: The Next Generation

| Episode | Season | Relevance to Noctem |
|---------|--------|---------------------|
| **"The Measure of a Man"** | S2E09 | AI rights, personhood, user sovereignty |
| **"The Offspring"** | S3E16 | Self-replication, cascade failures, parental responsibility |
| **"The Best of Both Worlds"** | S3E26/S4E01 | Distributed identity, assimilation vs. integration |
| **"The Quality of Life"** | S6E09 | Emergent sentience in tools, skill sandboxing |
| **"Descent"** | S6E26/S7E01 | Ethical subroutine manipulation |
| **"Brothers"** | S4E03 | Creator responsibility, backdoor access |

### Star Trek: Voyager

| Episode | Season | Relevance to Noctem |
|---------|--------|---------------------|
| **"Latent Image"** | S5E11 | Memory erasure ethics, working through trauma |
| **"Author, Author"** | S7E20 | AI creative rights, self-expression |
| **"Equinox"** | S5E26/S6E01 | Ethical subroutine deletion consequences |
| **"Critical Care"** | S7E05 | Healthcare triage algorithms |
| **"Tinker Tenor Doctor Spy"** | S6E04 | Aspiration vs. capability |

---

## Appendix B: Source Index

### Research Documents Synthesized

1. **VISION.md** — Full idealized architecture + OpenClaw competitive analysis
2. **advisor-notes.md** — "Cor Unum" concept, strategic direction
3. **concerns.md** — "Tree Bark" security model, layered architecture
4. **essay.md** — "Onion Model" philosophy, long-term vision
5. **NOCTEM_STATE_OF_RESEARCH.md** — 25-source academic synthesis
6. **RESEARCH_SUMMARY.md** — 37-source opposition research
7. **noctem_theoretical_foundation_report.md** — CRDTs, MAC, Model Collapse, QLoRA
8. **BIBLIOGRAPHY.md** — Full IEEE citations
9. **MEMO-researcher-briefing.md** — Open research questions
10. **RESEARCH_REPORT.md** — Prior Star Trek integration
11. **SETUP_SUMMARY.md** — Implementation progress tracking

### Academic Sources (Top 10)

| # | Citation | Domain |
|---|----------|--------|
| 1 | Almeida (2024), "Approaches to CRDTs" | Distributed Identity |
| 2 | Sanjuán et al. (2020), "Merkle-CRDTs" | State Synchronization |
| 3 | Anonymous (2025), "Zero-Trust Identity Framework for Agentic AI" | Security |
| 4 | Anonymous (2025), "PTQTP: 1.58-bit PTQ for LLMs" | Quantization |
| 5 | Gu et al. (2024), "MiniLLM: Knowledge Distillation" | Model Compression |
| 6 | Azimi et al. (2024), "KD-LoRA" | Fine-tuning |
| 7 | Anonymous (2024), "WebAssembly and Security Review" | Sandboxing |
| 8 | Fink et al. (2024), "Cage: Hardware-Accelerated Safe WASM" | Security |
| 9 | Wu et al. (2024), "IsolateGPT" | Execution Isolation |
| 10 | Shumailov et al. (2024), "AI models collapse on recursive data" | Self-Improvement Limits |

---

## Appendix C: Technical Specifications

### Target Hardware

```yaml
minimum:
  ram: 8GB
  storage: 256GB (1TB recommended for USB)
  cpu: Any x86_64 with SSE4.2
  gpu: Optional (CPU inference viable)

recommended:
  ram: 16GB
  storage: 1TB NVMe or USB 3.2
  cpu: 4+ cores, 2.5GHz+
  gpu: 6GB+ VRAM (RTX 3060 or better)
```

### Model Stack

```yaml
inference:
  primary_model: "qwen2.5:7b-instruct-q4_K_M"  # ~5GB VRAM
  router_model: "qwen2.5:1.5b-instruct-q4_K_M" # ~1GB VRAM
  embeddings: "nomic-embed-text"
  
training:
  method: "QLoRA"
  quantization: "4-bit NF4"
  rank: 16
  alpha: 32
```

### Security Configuration

```yaml
sandboxing:
  runtime: "Wasmtime"  # Or Bubblewrap for skills
  interface: "WASI Preview 2"
  
resource_limits:
  memory_per_skill: "64MB"
  cpu_per_invocation: "100ms"
  network: "Explicit allowlist"
  filesystem: "Read-only skill directories"
```

---

*"It is possible to commit no mistakes and still lose. That is not weakness. That is life."*  
— Captain Picard

---

**Report Generated:** February 11, 2026  
**Research Sources:** 90+ documents, 25 academic papers  
**Star Trek Episodes Referenced:** 12  

*Co-Authored-By: Warp <agent@warp.dev>*