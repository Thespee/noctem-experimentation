# Internal Memo: Noctem Project Briefing

**To:** Research Advisor (Best Practices & Theoretical Limits)  
**From:** Development Team  
**Date:** 2026-02-11  
**Re:** Project handoff—current state, open questions, and guidance needed

---

## Executive Summary

Noctem is a portable, self-improving personal AI assistant designed to run on low-spec hardware (target: USB-bootable Linux on a 1TB flash drive). The MVP is functional: we have Signal messaging integration, a task router using local Ollama models, and a skill-based plugin architecture. We're now at a critical juncture where theoretical guidance would help us avoid architectural dead-ends before v1.0.

**Key tension:** We want OpenClaw's extensibility and "shared info" benefits without its security disasters. Your input on where the theoretical limits lie would be invaluable.

---

## What Currently Works

### Implemented (v0.5-ish)
- **Signal integration** via signal-cli daemon (bidirectional messaging)
- **Dual-model routing**: 1.5B model for quick chat, 7B for complex tasks
- **Skill framework**: shell, file_ops, signal_send, task_status (see `skills/`)
- **SQLite persistence**: tasks, memory, skill execution logs
- **Research agent**: automated Warp CLI-based research loop (needs output parsing fix)

### Architecture
```
User ←→ Signal ←→ Router (1.5B) ──→ Quick response
                        │
                        └──→ Task queue ──→ Daemon (7B) ──→ Skill chain ──→ Response
```

---

## Core Theoretical Questions We Need Help With

### 1. Distributed Identity ("Cor Unum" Problem)

**Vision:** One "heart" that lives across many devices—old laptops, phones, potentially shared library terminals.

**Current approach:** Single USB as the canonical state holder.

**Questions for you:**
- What are the theoretical limits of maintaining coherent identity across async, intermittently-connected nodes?
- Is there prior art in distributed systems we should study? (CRDTs? Vector clocks for memory/context?)
- How do we handle conflicting self-modifications if the system runs on two machines simultaneously?

### 2. Security Layers ("Tree Bark" Model)

**Vision:** Onion/tree-bark layers of security—outer nodes (smart fridges, public terminals) are untrusted; inner layers have more privacy and capability.

**Our concerns:**
- OpenClaw's CVE-2026-25253 (one-click RCE) happened because security was "deprioritized in favor of usability"
- We want mandatory confirmation for dangerous ops, but where's the line?
- 341 malicious skills found on their marketplace—we're avoiding open marketplaces entirely

**Questions for you:**
- What's the minimum viable trust model for a portable personal AI?
- How do we formalize "dangerous operation" in a way that's both safe and not crippling?
- Is there a principled way to sandbox skills without Docker (target hardware can't run containers)?

### 3. Self-Improvement Bounds

**Vision:** LoRA fine-tuning during "sleep" mode, learning from corrections, router optimization.

**Current approach:** Log everything; plan nightly fine-tuning runs.

**Questions for you:**
- What are the theoretical limits of self-improvement on consumer hardware (8GB RAM, no dedicated GPU)?
- How do we prevent drift toward unsafe behaviors during unsupervised learning?
- Is there research on "small adapter" approaches that maintain alignment?

### 4. Competency Sharing ("CORE SKILLS")

**Vision:** Very limited-scope skills/components that can be shared model-to-model, potentially across users' systems.

**Questions for you:**
- Is there prior art on transferring narrow competencies between different base models?
- What's the minimum granularity for a "skill" to be safely shareable?
- How do we verify a skill does what it claims without full formal verification?

### 5. Resource Minimization

**Constraint:** Must run on old/low-spec hardware. "How small can we get the components?"

**Current stack:** Python 3.8+, SQLite, Ollama (llama.cpp backend), signal-cli.

**Questions for you:**
- What's the theoretical minimum for a useful personal AI? (Model size, RAM, storage)
- Are there compression/quantization techniques we should prioritize researching?
- Trade-offs between local inference quality and cloud fallback—when is degraded-but-private better than capable-but-exposed?

---

## Known Issues & Risks

| Area | Issue | Severity |
|------|-------|----------|
| Security | No formal threat model beyond "better than OpenClaw" | High |
| Portability | VeraCrypt dependency for encryption; not available everywhere | Medium |
| Self-improvement | No guardrails on what fine-tuning can change | High |
| Copyright | Using training data, web scraping—unclear legal ground | Medium |
| Personhood | "Right to personhood" aspiration is philosophically loaded | Low (aspirational) |

---

## Philosophical Framing (For Context)

The project originated with these aspirations (see `docs/essay.md`):
- "Right to compute" as a recognized/provided right
- "Remove AI from capitalism"—accessible to everyone via libraries, not just people of means
- The "onion model"—layers of capability with distributed sub-agents

These are background motivations, not immediate technical requirements. But they inform why we care about portability, minimal resources, and avoiding cloud dependency.

---

## What We Need From You

1. **Literature review**: Point us to relevant prior art on distributed personal AI, secure sandboxing without containers, and bounded self-improvement.

2. **Theoretical limits**: Help us understand what's actually achievable vs. aspirational given our constraints.

3. **Red lines**: Where should we absolutely not go? What design choices would make the system fundamentally unsafe or unethical?

4. **MVP scoping**: Given v0.5 → v1.0 goals, what should we defer vs. get right the first time?

---

## Repository Access

```
git clone https://github.com/Thespee/noctem.git
```

Key files to review:
- `docs/VISION.md` — Full architecture vision + OpenClaw competitive analysis
- `docs/concerns.md` — Advisor's architectural concerns
- `docs/advisor-notes.md` — Advisor's strategic notes
- `AGENTS.md` — Technical architecture for AI agents working on the code
- `skills/base.py` — Skill system implementation

---

## Next Steps

Once you've reviewed, we'd like to schedule a working session to:
1. Prioritize the theoretical questions above
2. Identify any "stop and rethink" areas before we build further
3. Establish best practices for the v1.0 milestone

Looking forward to your guidance.

—Dev Team
