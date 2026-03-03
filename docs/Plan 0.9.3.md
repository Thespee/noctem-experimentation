# Noctem Plan v0.9.3 — Agentic Rebuild & Feature Roadmap

*Last updated: 2026-03-03*

## Guiding Principles

> "I never want to touch a computer again."

1. **Zero-touch operation** — every feature moves toward automation.
2. **Human-in-the-loop for risky actions** — never send/commit/write externally without approval.
3. **Local-first, privacy-first** — cloud only with explicit consent.
4. **Put down / pick up** — work must be pausable, persisted, and resumable.
5. **Respect attention** — batch questions, avoid spam.

---

## Current State (through v0.9.1)

- Fast capture pipeline (text/voice → thoughts → tasks/notes/clarifications)
- Butler protocol with clarification sessions
- Execution logging + self‑improvement engine
- Skills infrastructure (SKILL.yaml, triggers, approvals, logging)
- Wiki ingestion + embeddings + citations
- Web UI: calendar view, upcoming tasks, projects board

---

## v0.9.3 Goals

1. **Rebuild agentic infrastructure** (replace Butler protocol with a cleaner runtime).
2. **Precise task interaction** (bulk add/edit, NLP reprocess, stronger task editing UX).
3. **RAG wiki rebuild** (trust levels + citations remain, improve pipeline and evaluation).
4. **Foundation for external integrations** (universal inbox, workflow automation).

---

## Quick Fixes (carry‑forward)

- Remove the date entry field in projects when creating tasks; always reprocess NLP on submit.
- Add `tmrw` as an alias for `tomorrow` in task filters.
- Click task card → open text editor → reprocess NLP → overwrite tags/dates.
- Tasks with **no due date** should appear at the **right end** of upcoming tasks (newest → oldest).
- Calendar import misses repeating tasks (e.g., bi‑weekly therapy) — fix recurrence ingest.

---

## Research Summary — How Others Solve These Problems

### Human‑in‑the‑Loop Orchestration
- **LangGraph** supports interruptible workflows and checkpointed state so long‑running tasks can pause and resume after human input. citeturn2search0turn2search1

### Multi‑Agent Patterns
- **AutoGen** supports multi‑agent conversational workflows with configurable agent roles. citeturn1search5turn1search10
- **CrewAI** provides agent/flow constructs plus memory and guardrails for controlled execution. citeturn3search5turn3search7

### Tool & Integration Layer
- **MCP (Model Context Protocol)** defines a host‑client‑server architecture for tool access over JSON‑RPC with stdio/HTTP transports. citeturn1search0turn1search2turn1search3turn1search9
- **n8n** is a self‑hosted workflow automation platform with a large integration catalog and AI workflow templates. citeturn1search4turn1search7

### Deployment Reliability
- **Gunicorn** supports graceful reloads (HUP) to replace workers without dropping requests. citeturn3search0

### Personal Finance References
- **GnuCash** is an open‑source personal finance manager based on double‑entry accounting. citeturn3search6
- **Firefly III** is a self‑hosted personal finance manager with imports and reporting. citeturn3search10

### Food / Recipe Data
- **Open Food Facts** provides an open food database and API with ODbL licensing. citeturn4search3turn4search4

---

## Proposed Architecture (v0.9.3)

```
Input → Intake → Router/Planner → Workflow Runtime → Tools → State → Interfaces
```

- **Intake**: fast capture, NLP parsing, always creates a thought record.
- **Router/Planner**: classifies intent, queues work items, assigns to workflows.
- **Workflow Runtime**: executes tasks, pauses for approvals, resumes later.
- **Tools**: MCP servers for tool access; n8n for cross‑app automation.
- **State**: local DB + RAG wiki for knowledge; auditable logs.
- **Interfaces**: Telegram, web dashboard, CLI.

---

## Recommendations (Proposal — Needs Confirmation)

1. **Orchestration**: Use LangGraph for core workflows + human‑in‑the‑loop interrupts. citeturn2search0turn2search1
2. **Tool access**: Standardize internal tools as MCP servers; use n8n for external app fan‑in and workflows. citeturn1search0turn1search4
3. **Agent model**: Start single‑agent runtime; introduce multi‑agent roles only if needed (AutoGen/CrewAI patterns). citeturn1search5turn3search5
4. **Finance**: Implement a double‑entry ledger inspired by GnuCash/Firefly conventions. citeturn3search6turn3search10
5. **Food data**: Start with a curated pantry + optional Open Food Facts enrichment. citeturn4search3turn4search4

---

## Decision Points (Confirm Before Implementation)

1. **Primary orchestration**: LangGraph vs CrewAI vs AutoGen as the core runtime.
2. **Integration strategy**: MCP‑first, n8n‑first, or hybrid (recommended: hybrid).
3. **Universal inbox MVP scope**: email + calendar only, or add messaging platforms immediately?
4. **Finance depth**: full double‑entry ledger vs simplified tracking with upgrade path.
5. **Food data**: Open Food Facts vs custom curated recipe set.

---

## Feature Implementation Plans (Brief)

| Feature | MVP Outcome | Inputs | Infrastructure | Notes |
| --- | --- | --- | --- | --- |
| Task Precision & Bulk Ops | Bulk add/edit + NLP reprocess | tasks DB, NLP parser | unified edit pipeline | aligns with quick fixes |
| RAG Wiki Rebuild | grounded Q&A + citations | local sources | ingestion → embeddings → retrieval | preserve trust levels |
| Meal Planning | weekly plan + grocery list | pantry + prefs | pantry DB + recipe source | user approval required |
| Finance Tracking | statement import + ledger + reports | CSVs/OFX | double‑entry schema | inspired by GnuCash/Firefly |
| Reading/Listen/Watch | unified list + reminders | manual capture | list DB + status fields | calendar prompts |
| Universal Inbox | one queue for inbound items | IMAP/ICS/Telegram | n8n + MCP connectors | start with forwarding |
| Zero‑Downtime Deployment | graceful reloads | deploy script | Gunicorn HUP + health check | backward‑compatible migrations |
| Embedding Classification | semantic intent detection | labeled examples | embeddings + thresholds | keep rule fallback |
| Digital Aristotle | Socratic Q&A + review | wiki chunks | Q‑gen + SM‑2 scheduler | opt‑in sessions |

---

## Agent Implementation Plan (Brief)

1. **Define agent state model** (thoughts, intents, queued work, approvals).
2. **Router/Planner v1**: single‑agent workflow queue with explicit states.
3. **Human‑in‑the‑loop**: use interrupts/checkpoints to pause/resume tasks. citeturn2search0turn2search1
4. **Tool registry**: expose internal tools via MCP servers. citeturn1search0turn1search2turn1search3
5. **External workflows**: use n8n for fan‑in/out integrations. citeturn1search4turn1search7
6. **Multi‑agent expansion (optional)**: add role‑specific agents only if single‑agent saturates. citeturn1search5turn3search5
7. **Observability**: keep audit logs and traceability across all steps.

---

## References

1. LangGraph — Human‑in‑the‑loop: https://langchain-ai.github.io/langgraph/concepts/human_in_the_loop/
2. LangGraph — Interrupts: https://langchain-ai.github.io/langgraph/concepts/interrupts/
3. MCP Overview: https://modelcontextprotocol.io/docs/introduction
4. MCP Architecture: https://modelcontextprotocol.io/docs/concepts/architecture
5. MCP Transports: https://modelcontextprotocol.io/docs/concepts/transports
6. n8n AI Workflow Starter Kit: https://docs.n8n.io/advanced-ai/intro-tutorial/
7. n8n Integrations: https://docs.n8n.io/integrations/
8. AutoGen (Microsoft): https://microsoft.github.io/autogen/
9. AutoGen Reference: https://microsoft.github.io/autogen/stable/
10. CrewAI Docs: https://docs.crewai.com/
11. CrewAI Memory: https://docs.crewai.com/concepts/memory
12. Gunicorn Reloading: https://docs.gunicorn.org/en/stable/signals.html
13. GnuCash Features: https://www.gnucash.org/features.phtml
14. Firefly III Introduction: https://docs.firefly-iii.org/firefly-iii/about-firefly-iii/introduction/
15. Open Food Facts API: https://openfoodfacts.github.io/api-documentation/
16. Open Food Facts Data & Licensing: https://world.openfoodfacts.org/data

