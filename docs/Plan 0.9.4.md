# Noctem Plan v0.9.4 — Agentic Rebuild & Full Feature Roadmap
*Last updated: 2026-03-05*

## Guiding Principles
> "I never want to touch a computer again."

1. **Zero-touch operation** — every feature moves toward automation.
2. **Human-in-the-loop for risky actions** — never send/commit/write externally without approval.
3. **Local-first, privacy-first** — cloud only with explicit consent.
4. **Data sovereignty** — all data stays local unless explicitly enabled.
5. **Put down / pick up** — work must be pausable, persisted, and resumable.
6. **Respect attention** — batch questions, avoid spam.

---

## Current State (through v0.9.3)

### What exists today
- **Agentic runtime**: deterministic workflow engine with interrupt/resume, approvals, and preview/commit safety gates.
- **Model-first chat orchestration**: thread continuity across web/CLI/Telegram with fallback to deterministic execution.
- **MCP tool surface**: broad read/write task/project/goal tools with preview/commit and idempotency keys.
- **Calendar (ICS-first)**: saved URL import, refresh, clear, and event storage in `time_blocks`.
- **Wiki/RAG foundation**: source ingestion, chunking, embeddings, retrieval/query stack with trust-level fields in DB.
- **Passive scheduler**: APScheduler currently runs voice processing only (interval job), with voice journals processed when pending.
- **Web + Telegram + CLI interfaces**: core user entry points are already wired.

### Gaps to close in v0.9.4
- Durable mutation history is still incomplete (some audit/undo state remains process-memory backed).
- Interrupt semantics are strong for yes/no approvals but not yet first-class for appended follow-up instructions.
- RAG context assembly is functional but not yet structured around persistent memory packs (recent chats + recent mutations + calendar-aware context).
- No first-class **entity context documents** yet (task/project/goal/doc/calendar synthesized context views).
- Passive work execution is still static; no inactivity-budgeted decision layer for what to run next.
- Several roadmap domains (finance, universal inbox, media tracking, Obsidian-like interface, docs versioning) need first-class data models and APIs.

### Existing dependency baseline (relevant for implementation)
- `flask`, `jinja2` (web)
- `python-telegram-bot` (Telegram)
- `icalendar`, `requests` (calendar import + integrations)
- `chromadb`, `PyMuPDF` (wiki embeddings + source ingestion)
- `python-dateutil` (date parsing)
- `faster-whisper` (voice)
- `rapidfuzz`, `pyyaml` (classification/skills utility)

---

## v0.9.4 Goals
- Implement the full feature set below in this version scope (no phase split in this document).
- Add brief, codebase-grounded implementation details for each feature.
- Preserve current reliability guardrails (preview/commit, verification, idempotency) while expanding capability.
- Upgrade history and memory so every important mutation and conversation state is durable and queryable.

---

## Research Summary — How Others Solve These Problems

### 1) Agent interruption + appended instructions
- Production agent systems treat interruption as a first-class control surface, not just a cancel action.
- Best practice: pause at risk boundaries, accept structured follow-up instructions, resume deterministically in the same thread/run.

### 2) Long-context memory for assistants
- Strong systems separate:
  - **short-term thread memory** (working conversation state),
  - **long-term memory** (summaries/preferences/events),
  - **episodic action history** (what actually changed).
- Practical pattern: assemble a bounded memory pack (recent turns + summaries + recent verified mutations + temporal context).

### 3) Durable mutation history (Git-like behavior)
- Proven approach is append-only event/commit records with parent pointers and immutable history.
- Rollback is modeled as a new inverse commit, not destructive rewrite.
- This aligns well with preview/commit + idempotency systems.

### 4) RAG with citations and trust
- Retrieval quality improves with citation-aware synthesis and trust metadata on sources/chunks.
- Calendar/tasks as context should be merged as structured grounding signals, not noisy raw transcript stuffing.

### 5) Universal inbox and cross-channel capture
- Reliable inbox systems normalize heterogeneous events (IMAP, Telegram, ICS, etc.) into one envelope schema and process via deterministic routing.

### 6) Operational stability and deployability
- Graceful process reload and compatibility-safe migrations are standard for zero-downtime-ish self-hosted stacks.

### 7) Entity-centric context docs
- Systems improve grounding by maintaining entity-centric context artifacts that combine provenance, changes, and related graph links.
- Practical pattern: materialize these docs asynchronously from immutable history, then use them as high-signal retrieval units for RAG.

### 8) Adaptive background scheduling
- Mature schedulers use runtime controls (misfire handling, coalescing, concurrency limits) and eligibility constraints.
- A useful agent pattern is budget-aware dispatch: choose short, high-value passive jobs when the user/session is idle and skip jobs with no new work.

---

## Confirmed Decisions (2026-03-05)

1. Keep every existing roadmap feature and plan implementation coverage in this version.
2. Add a **Priority** column and a **codebase/dependency implementation overview** column in the roadmap table.
3. Replace all placeholders in this document with executable planning content.
4. Include calendar events in “full-history” / mutation-history architecture planning.
5. Include external research references at the bottom with at least one source per feature.
6. Add entity context-doc generation planning across tasks/projects/goals/docs/calendar events.
7. Add an inactivity-budgeted slow-runner planning model (voice runs only when new memos exist).

---

## Clarifying Questions To Finalize Before Build Start (Research-Informed)
These are the key implementation decisions that should be answered before coding begins.

1. **History scope**: Should immutable commit history include only tasks/calendar/docs at first, or also projects/goals/finance rows from day one?
2. **Undo policy**: Should undo always generate inverse commits (recommended) and be limited to operations with verified pre-state snapshots?
3. **Conflict policy**: If a task changed after the original commit, should undo perform best-effort field-level merge or fail closed and ask user?
4. **Calendar source of truth**: For imported ICS events, should history track only local state mutations, or also preserve upstream event fingerprint/version for replay?
5. **Memory retention limits**: Confirm defaults for chat and mutation memory windows (currently proposed: last 5 chats, last 2 mutation sessions).
6. **RAG grounding precedence**: Should local wiki facts always outrank inferred assistant memory unless user asks for speculative synthesis?
7. **Universal inbox dedupe key**: Which canonical key strategy should be used across channels (`source + external_id + timestamp hash` recommended)?
8. **Finance ingestion risk controls**: Require manual review for every imported transaction batch before ledger commit?
9. **Obsidian integration mode**: Built-in web graph in Noctem first, or filesystem-first interoperability with external Obsidian vault UI assumptions?
10. **Git controls in UI**: Should docs version control use internal commit APIs only initially, or optionally invoke system Git for vault/doc paths?
11. **Deployment target**: Is Gunicorn standardization mandatory for production profile in v0.9.4 (recommended) vs Flask dev server fallback only?
12. **Security boundary**: Which features can ever write externally without prompt-time approval (default should remain “none”)?
13. **Context-doc format**: Should entity context docs be markdown-first (human-readable) plus JSON index, or JSON-first with rendered markdown views?
14. **Context-doc freshness**: Generate on every commit, or batch via slow-runner with staleness SLA (e.g., <5 minutes)?
15. **Idle threshold policy**: Confirm initial inactivity trigger (15 min suggested) and whether threshold adapts by time-of-day/workload.
16. **Budget model**: Should passive job eligibility be `expected_runtime <= idle_duration`, or reserve a fixed safety margin?
17. **Voice priority rule**: If new voice memos exist, should voice always preempt other passive jobs or be ranked by expected value/runtime?

---

## Proposed Architecture (v0.9.4)
`Input → Intake → Router/Planner → Workflow Runtime → Tools → State → Interfaces`

- **Intake**: fast capture, NLP parsing, thought/event records.
- **Router/Planner**: intent + scope resolution; structured tasking.
- **Workflow Runtime**: deterministic execution; interrupt + appended-instruction resume.
- **Tools**: MCP contracts first; n8n connectors for external systems where needed.
- **State**:
  - core DB tables (tasks/projects/goals/time_blocks/conversations),
  - wiki chunks + vector store,
  - append-only commit/event history for mutations (tasks + calendar + docs).
- **Context Docs Layer**: asynchronously synthesized entity docs for tasks/projects/goals/docs/calendar events (history + related entities + provenance).
- **Adaptive Passive Runner**: inactivity-triggered scheduler that selects eligible low-runtime background jobs based on expected duration and queue signals.
- **Interfaces**: Telegram, web dashboard, CLI.

---

## Full Feature Roadmap Table (Updated)

| Feature | Priority | MVP Outcome | Inputs | Infrastructure | Implementation details (current codebase + deps) | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| RAG Wiki Rebuild | High | Grounded Q&A + citations + trust filtering + calendar/task awareness | Local docs/PDF/text, task/calendar context | Ingestion → chunking → embeddings → retrieval → citation synthesis | Reuse `noctem/wiki/*` pipeline and `sources` / `knowledge_chunks` schema; extend retrieval context builder to include relevant `tasks` + `time_blocks`; leverage existing `chromadb` + `PyMuPDF` deps. | Must preserve trust levels and source attribution. |
| Finance Tracking | High | Statement import + normalized ledger + reports | CSV/OFX files, manual corrections | Double-entry ledger schema + importer + reconciliation views | New `finance_*` tables and import service; existing `action_log`/agent workflows can record approvals; `requests` can support institution API pulls later. | Start local-first with CSV/OFX import + review-before-commit. |
| Reading/Listen/Watch | High | Unified media list + reminders + status progression | Manual entry + optional metadata APIs | Shared media schema with `media_type` + status + reminder hooks | Add `media_items` and reminder integration with existing scheduler/time blocks; web + Telegram capture paths already exist and can be reused. | Use one normalized model across book/podcast/video types. |
| Universal Inbox | High | Unified inbound queue for all channels | IMAP + Telegram + ICS + manual notes/messages | n8n triggers + MCP normalization endpoint + inbox table | Existing Telegram + ICS plumbing exists; add email ingress (IMAP trigger) and canonical “inbox envelope” schema; route through workflow runtime for triage. | Include messaging immediately; strict dedupe keys. |
| Zero-Downtime Deployment | High | Graceful reload deploy process | Deploy script, health checks, migration checks | Gunicorn signal handling + compatibility-safe migrations | Replace production runtime assumption from Flask dev run to Gunicorn-managed app process; keep app factory pattern; enforce migration compatibility gates pre-reload. | Keep rollback script for failed health checks. |
| Embedding Classification | High | Semantic intent detection with fallback safety | Labeled utterances + live traces | Embedding model + similarity thresholds + deterministic fallback | Integrate sentence-embedding classifier alongside current router/rule-based intent path; keep hard fallback to existing deterministic classifier when confidence low. | Preserve explainability and audit logs for route decisions. |
| Digital Aristotle | Medium | Socratic Q&A + review scheduling | Wiki chunks + user-selected domains | Question-generation + spaced repetition scheduler | Use existing wiki retrieval for evidence-backed prompts; add review queue with SM-2/FSRS-like scheduling metadata and opt-in user sessions. | Must remain opt-in, not ambient nagging. |
| Meal Planning | Medium | Weekly plan + grocery list generation | Pantry, dietary prefs, local goals/calendar | Pantry DB + recipe/food metadata source + planner | New pantry + meal plan tables; use task/calendar slots for execution windows; Open Food Facts integration via `requests` when API connectors are added. | Keep “Later” depth features optional, but base planning included in v0.9.4 scope. |
| Obsidian-like Interface for Personal Wiki | High | Graph/navigation-first wiki exploration in web UI | Notes, links, tags, source metadata | Graph view UI + backlink index + search | Build graph API from existing wiki chunks/links and add web graph component; Noctem already stores docs/chunks and can expose node-edge endpoints. | Keep markdown-native and filesystem-friendly. |
| Git-like Versioning for Local Docs | High | Version history + diff + restore for docs | Markdown/doc edits | Internal commit graph (or system Git bridge) + diff/restore APIs | Extend durable history model to docs entity type; expose commit log/diff/restore actions in UI; optionally bridge to real Git for vault folders if enabled. | Obsidian-like interface should expose version controls. |
| Warp-style Interrupt + Appended Instructions | High | Interrupt and continue with refined instructions in same workflow | User decisions + follow-up instructions | Structured interrupt payload + resume routing | Existing interrupt flow in `agent/workflow.py` and `chat_orchestrator.py` can be extended from yes/no to `{decision,instructions,scope_edits}` contract. | Align behavior with “refine request” style interactions. |
| LangGraph Runtime + Memory Pack | High | Durable conversational state + resumable HITL + bounded context assembly | Thread messages, summaries, recent mutation commits | LangGraph checkpointer/store + memory assembler | Introduce LangGraph runtime wrapper while preserving current API envelope; add memory pack builder using conversations + commit history + temporal context. | Proposed defaults: last 5 chats, last 2 mutation sessions. |
| Git-like Mutation History for Tasks + Calendar Events | High | Immutable audit trail + queryable history + inverse-commit undo | All committed mutations | Append-only commit tables + parent pointers + refs + change records | Replace in-memory audit stores in MCP tools with DB-backed history service; include `time_blocks` mutations in same commit graph model. | Undo should be inverse commit, never destructive rewrite. |
| Entity Context Docs (Task/Project/Goal/Doc/Calendar) | High | Per-entity context artifacts for accurate retrieval and explainability | Entity snapshots + commit history + relations | Async context-doc synthesizer + context-doc store + retrieval hooks | Build from existing conversations + workflow outputs + commit history into canonical per-entity docs; run via slow runner to avoid hot-path latency. Use docs as top-tier RAG context objects before raw logs. | Primary accuracy/memory lever; should include original creation context, change history, and related entities. |
| Adaptive Slow Runner (Inactivity-Budgeted) | High | Single “what can I run now?” passive executor based on idle time and pending work | Session inactivity timestamp + job runtime estimates + queue states | APScheduler coordinator + job runtime telemetry + dispatch policy | Replace fixed periodic passive pattern with coordinator that triggers after inactivity (initial 15m), computes budget, and selects jobs where expected runtime fits budget. Voice processing only runs when `voice_journals` pending count > 0. | Start simple with deterministic policy and measured runtime medians per job type. |
| Calendar Event Intelligence & Planning Awareness | High | Calendar-aware planning, prioritization, and conflict detection | Imported ICS + manual events + task deadlines | Time-block normalization + conflict resolver + planner hooks | Existing `ics_import` + `time_blocks` provide foundation; add conflict detector and planning heuristics in workflow/query layers and memory pack. | Keep ICS-first direction and avoid reintroducing removed Google OAuth sync path unless explicitly requested. |

---

## Feature Sources (at least one per feature)
1. **RAG Wiki Rebuild** — LlamaIndex citation query engine: https://docs.llamaindex.ai/en/stable/examples/workflow/citation_query_engine/
2. **Finance Tracking** — GnuCash double-entry transactions: https://www.gnucash.org/docs/v5/C/gnucash-guide/chapter_txns.html
3. **Reading/Listen/Watch** — Schema.org `CreativeWork`: https://schema.org/CreativeWork
4. **Universal Inbox** — n8n Email Trigger (IMAP): https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.emailimap/
5. **Zero-Downtime Deployment** — Gunicorn signals/reload: https://gunicorn.org/signals/
6. **Embedding Classification** — Sentence Transformers STS usage: https://sbert.net/docs/sentence_transformer/usage/semantic_textual_similarity.html
7. **Digital Aristotle** — Socratic subquestion generation (research): https://arxiv.org/abs/2211.12835
8. **Meal Planning** — Open Food Facts API docs: https://openfoodfacts.github.io/documentation/docs/Product-Opener/api/
9. **Obsidian-like Interface** — Obsidian Graph view docs: https://help.obsidian.md/plugins/graph
10. **Git-like Versioning for Docs** — Pro Git internals (objects): https://yeeon.github.io/ebook/progit.pdf
11. **Warp-style Interrupt + Appended Instructions** — Warp Full Terminal Use (refine/follow-up controls): https://docs.warp.dev/agent-platform/capabilities/full-terminal-use
12. **LangGraph Runtime + Memory Pack** — LangGraph add memory: https://docs.langchain.com/oss/python/langgraph/add-memory
13. **Git-like Mutation History (Tasks + Calendar)** — Event Sourcing pattern: https://www.martinfowler.com/eaaDev/EventSourcing.html
14. **Calendar Event Intelligence** — iCalendar standard (RFC 5545): https://datatracker.ietf.org/doc/html/rfc5545
15. **Entity Context Docs** — LlamaIndex PropertyGraphIndex: https://docs.llamaindex.ai/en/stable/module_guides/indexing/lpg_index_guide/
16. **Adaptive Slow Runner** — APScheduler User Guide (misfire/coalesce/concurrency controls): https://apscheduler.readthedocs.io/en/master/userguide.html
17. **Runtime-aware scheduling heuristic basis** — Smith/WSPT reference: https://www.stern.nyu.edu/om/faculty/pinedo/scheduling/sched.pdf

---

## Existing Core References (kept and expanded)
1. LangGraph — Human-in-the-loop: https://langchain-ai.github.io/langgraph/concepts/human_in_the_loop/
2. LangGraph — Interrupts: https://langchain-ai.github.io/langgraph/concepts/interrupts/
3. MCP Overview: https://modelcontextprotocol.io/docs/introduction
4. MCP Architecture: https://modelcontextprotocol.io/docs/concepts/architecture
5. MCP Transports: https://modelcontextprotocol.io/docs/concepts/transports
6. n8n Integrations: https://docs.n8n.io/integrations/
