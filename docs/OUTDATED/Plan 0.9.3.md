# Noctem Plan v0.9.3 — Agentic Rebuild & Feature Roadmap

*Last updated: 2026-03-03*

## Guiding Principles

> "I never want to touch a computer again."

1. **Zero-touch operation** — every feature moves toward automation.
2. **Human-in-the-loop for risky actions** — never send/commit/write externally without approval.
3. **Local-first, privacy-first** — cloud only with explicit consent.
4. **Data sovereignty** — all data stays local unless explicitly enabled.
5. **Put down / pick up** — work must be pausable, persisted, and resumable.
6. **Respect attention** — batch questions, avoid spam.

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

## Confirmed Decisions (2026‑03‑03)

1. **Orchestration**: LangGraph for the core workflow runtime. citeturn2search0turn2search1
2. **Integration strategy**: hybrid MCP + n8n (skills standardized as MCP). MCP servers stay **local/private**; no public exposure. citeturn1search0turn1search4
3. **Agent model**: start single‑agent for task management; expand only if necessary. citeturn1search5turn3search5
4. **Universal inbox scope**: include messaging platforms immediately (design + plan only).
5. **Finance**: full double‑entry ledger approach. citeturn3search6turn3search10
6. **Meal planning**: defer for later; when implemented, use Open Food Facts. citeturn4search3turn4search4

---

## Proposed Architecture (v0.9.3)

```
Input → Intake → Router/Planner → Workflow Runtime → Tools → State → Interfaces
```

- **Intake**: fast capture, NLP parsing, always creates a thought record.
- **Router/Planner**: classifies intent, queues work items, assigns to workflows.
- **Workflow Runtime**: executes tasks, pauses for approvals, resumes later.
- **Tools**: MCP servers for tool access; n8n for cross‑app automation. citeturn1search0turn1search4
- **State**: local DB + RAG wiki for knowledge; auditable logs.
- **Interfaces**: Telegram, web dashboard, CLI.

---

## Implementation Plan (Ordered)

### Phase 1 — Quick Fixes (verbatim feedback)

- Remove the date entry field in the projects page when you create a task; should instead process the nlp interpretation whenever and where ever a task is entered from
- add ‘tmrw’ to task filter for as a different form for ‘tomorrow’
- Editing tasks: when clicking them on the website, I want it to, when you lick on a task card, open a text entry box, similar to when creating a task, let me add or remove words and then reprocess the nlp; the reprocessing should over write any tags:
    - input text: “take out trash on monday” | new text: “take out trash Sunday”
    - This example should overwrite the due date on the take out trash task to Sunday
- Can we add tasks with no due date to the right end of the upcoming tasks (ordered recently created → oldest)
- The calendar import seems to miss repeating tasks; there should be a therapy session every other tuesday that doesnt show up
- Fix Website: The move to a more standard view broke every page that isn't the dashboard:
    - colours shceme has been reverted to old version?, please fix them to follow the dashboard colours
    - the upcoming page isn't horizontal on desktop
    - the side bars don't look like the dashboard sidebar
    - quick links broken on subpages; theres something called task settings that isn't a page at all
    - the ability to check tasks is gone
    - Just in general need to make them look like they did before the last change

### Phase 2 — Agent for Task Management (Single‑Agent Runtime)

**Objective:** Replace the Butler protocol with a task‑management agent that can parse, plan, and apply task edits in a controlled, auditable workflow.

**Plan (brief):**

1. **Agent state model**: define canonical states for task requests (captured → parsed → planned → pending approval → committed).
2. **LangGraph workflow**: model the task lifecycle as a graph with interrupts for clarifications and approvals. citeturn2search0turn2search1
3. **Router/Planner v1**: single agent that routes to task intents (add/edit/bulk/complete/move/schedule).
4. **Human‑in‑the‑loop**: generate targeted clarifying questions and resume on response.
5. **Tool access**: expose internal task operations via MCP (local/private). citeturn1search0turn1search2turn1search3
6. **Auditability**: every change logs input → decision → result for review and rollback.
7. **UI alignment**: task cards open inline editor; NLP reprocess applied consistently.

### Phase 3 — Additional Features (Brief Implementation Table)

| Feature | MVP Outcome | Inputs | Infrastructure | Notes |
| --- | --- | --- | --- | --- |
| RAG Wiki Rebuild | grounded Q&A + citations | local sources | ingestion → embeddings → retrieval | preserve trust levels |
| Finance Tracking | statement import + ledger + reports | CSVs/OFX | double‑entry schema | based on GnuCash/Firefly models citeturn3search6turn3search10 |
| Reading/Listen/Watch | unified list + reminders | manual capture | list DB + status fields | calendar prompts |
| Universal Inbox | unified inbound queue | IMAP/ICS/Telegram + messaging | n8n + MCP connectors | include messaging immediately |
| Zero‑Downtime Deployment | graceful reloads | deploy script | Gunicorn HUP + health check | backward‑compatible migrations citeturn3search0 |
| Embedding Classification | semantic intent detection | labeled examples | embeddings + thresholds | keep rule fallback |
| Digital Aristotle | Socratic Q&A + review | wiki chunks | Q‑gen + SM‑2 scheduler | opt‑in sessions |
| Meal Planning (Later) | weekly plan + grocery list | pantry + prefs | pantry DB + recipe source | Open Food Facts when implemented citeturn4search3turn4search4 |

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
