# Noctem Plan v0.9.4 — Agentic Rebuild & Full Feature Roadmap
*Last updated: 2026-03-11*

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
- Several roadmap domains (finance, media tracking, Obsidian-like interface, docs versioning) need first-class data models and APIs.
- Universal Inbox + external connectors are intentionally deferred to the Future Features section in this document.

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
## Implementation Plan (Dependency Order: Internal → External)
### 1) Universal Object Core + Durable History
Introduce `objects`, `object_versions`, `object_events`, and `object_refs` (heads) tables as the canonical registry for every entity type, with typed tables preserved for domain-specific fields. Store immutable commit/event records with parent pointers, and generate inverse commits for undo. Replace in-memory MCP preview/audit/undo stores with DB-backed records and correlation IDs. Add a shared `manual_review` state and a review queue table for merge errors and risky inbound data. Treat the object registry + commit graph as the system source of truth; external systems are imports/mirrors with explicit provenance.
**Codebase implementation steps**
- Add new schema tables and indexes in `current version_v0.9.3/noctem/db.py` (SCHEMA block + `_migrate_db()` additive migrations only).
- Keep existing typed tables (`tasks`, `projects`, `goals`, `time_blocks`, `sources`, `knowledge_chunks`) and introduce object-layer foreign keys (`object_id`) incrementally.
- Replace in-memory mutation stores in `current version_v0.9.3/noctem/mcp/tools.py` (`_PREVIEW_STORE`, `_COMMIT_RESULT_STORE`, `_AUDIT_EVENTS`, `_UNDO_PREVIEW_STORE`) with DB-backed preview/commit/event records.
- Preserve existing tool contracts in `current version_v0.9.3/noctem/mcp/tools.py` and `current version_v0.9.3/noctem/mcp/contracts.py` so web/telegram callers in `current version_v0.9.3/noctem/web/app.py` and `current version_v0.9.3/noctem/telegram/handlers.py` do not break while storage backend changes.
- Persist correlation IDs from MCP envelopes (`current version_v0.9.3/noctem/mcp/server.py`) into object event rows for end-to-end audit traceability.
### 2) Context Docs + Memory Pack Assembly
Add `object_context_docs` (JSON-first plus rendered markdown) and an async synthesizer that builds per-object context docs from commits, related objects, and provenance. Implement a memory pack builder that assembles bounded context for chat/RAG (recent conversations, recent commits, relevant context docs) with explicit budgets: 4k recent chats, 5k recent commits, 7k top context docs, 6k wiki; reserve 10k for tools/output (32k total).
**Codebase implementation steps**
- Source recent conversation slices from `conversations` via `current version_v0.9.3/noctem/services/conversation_service.py` and avoid raw transcript stuffing.
- Build context-doc generation worker as async background job (not in hot request path) and store JSON + rendered markdown in `object_context_docs`.
- Integrate pack assembly in chat flow entrypoints around `current version_v0.9.3/noctem/agent/chat_orchestrator.py` so deterministic routes and model routes share one bounded memory strategy.
- Use commit history from new object event tables instead of the current in-memory audit trail in `current version_v0.9.3/noctem/mcp/tools.py`.
- Add deterministic truncation and per-bucket token accounting before model calls (respecting 4k/5k/7k/6k split and 10k reserve).
### 3) Inactivity‑Budgeted Slow Runner
Replace the fixed interval scheduler with a coordinator that triggers after idle thresholds, computes a runtime budget (idle minus safety margin), and selects eligible jobs (context-doc refresh, ICS refresh, voice transcription if pending). Track runtime medians per job type to drive eligibility.
**Codebase implementation steps**
- Refactor `current version_v0.9.3/noctem/scheduler/jobs.py` from fixed 1-minute voice interval to an eligibility/dispatch coordinator with idle trigger at 15 minutes.
- Keep `voice` processing path unchanged at execution level (`current version_v0.9.3/noctem/voice/processing.py`), but gate execution by pending count and budget eligibility.
- Register ICS refresh jobs using existing functions in `current version_v0.9.3/noctem/services/ics_import.py` (`refresh_all_urls`, `refresh_url`) rather than adding new calendar ingestion code paths.
- Add runtime telemetry table(s) for per-job medians and failure rates to support expected-value ranking.
- Apply default 5-minute safety margin except first entry into idle-run mode after threshold.
### 4) Retrieval + RAG Integration
Make context docs first-class retrieval units ahead of raw logs and wiki chunks; extend retrieval to blend task/calendar context and trust signals into citations.
**Codebase implementation steps**
- Extend `current version_v0.9.3/noctem/wiki/retrieval.py` to query `object_context_docs` first, then fall back to `knowledge_chunks` vector search.
- Preserve and enhance trust weighting already present in wiki retrieval; add provenance metadata from object commit history into citation payloads.
- Update `current version_v0.9.3/noctem/wiki/query.py` prompt assembly to include context-doc citations and explicit source tiers.
- Integrate task/calendar grounding by retrieving relevant task/time_block summaries before final prompt assembly (without overfilling token budget).
- Add evaluation hooks for citation accuracy and source-tier usage before enabling broader autonomous behaviors.
### 5) Review + Error Surfaces
Add a web “Review” tab that consolidates merge errors, manual-review objects, and audit trails, plus endpoints for approve/reject/resume actions.
**Codebase implementation steps**
- Introduce review queue read/write services against new DB tables and connect them to existing interrupt and mutation flows.
- Reuse interrupt context patterns from `current version_v0.9.3/noctem/agent/interrupts.py` and `current version_v0.9.3/noctem/agent/workflow.py` so unresolved conflicts can become review items with structured reason codes.
- Add web API endpoints in `current version_v0.9.3/noctem/web/app.py` for listing review items, approving/rejecting actions, and resuming blocked workflows.
- Ensure destructive/multi-target actions continue using preview/commit semantics and record why an item entered manual review (`ambiguity`, `policy_gate`, `verification_failure`).
- Keep assistant success messaging conditioned on post-commit verification, consistent with existing MCP verification checks in task APIs.
### 6) Obsidian Interface + Internal Versioning
Implement a Noctem-native web graph view with optional markdown export; keep version control internal to the object commit graph (no system Git bridge in v0.9.4).
**Codebase implementation steps**
- Build graph API endpoints in `current version_v0.9.3/noctem/web/app.py` backed by object relations (`object_refs`/edge tables) and typed facets from tasks/projects/goals/docs/events.
- Represent node provenance/version state from internal commit graph only; do not invoke system Git in runtime paths.
- Add markdown export pipeline from object context docs and/or typed entities into filesystem snapshots as optional output artifact.
- Keep import/export one-way by default (export convenience), with explicit future decision before any bidirectional vault sync.
- Add lightweight UI integration in existing dashboard stack (web templates/static assets) while preserving current task/calendar views.
### 7) Documentation Updates
Update `docs/Plan 0.9.4.md` and `WARP.md` with finalized decisions (Obsidian web graph + export, internal-only versioning, memory pack budgets).
**Codebase implementation steps**
- Keep plan docs aligned with the checked-out implementation branch (`feature/v0.9.3-agentic-agent`) before each major build phase.
- Ensure deferred scope is explicit (Universal Inbox moved to Future Features) so active implementation checklists remain executable.
- Include file-level implementation references in docs when decisions depend on existing behavior (e.g., scheduler, workflow resume, MCP preview/commit).
- Add release-gate checklist: schema migration review, safety/approval verification, and retrieval/citation behavior verification.
- Preserve changelog-style date stamps for all doc updates to prevent ambiguity across concurrent planning sessions.

## Improvement Patterns to Adopt (Non-offline)
- **Tiered memory packs**: short-term chats, episodic commits, and semantic context docs with retrieval-first assembly.
- **Personal data store boundary**: Noctem DB remains canonical; external sources are imported with explicit provenance.
- **Lifelogging-style capture**: every artifact becomes a first-class object with uniform metadata and provenance.
- **Event-sourced commit ledger**: content-addressed snapshots for integrity, replay, and deterministic context regeneration.

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
```
I was wondering about building an "object" class in the database; every peice of data (calendar events, config files, tasks, pdfs in the wiki, voice memos, voice transcriptions, everything) is inherited from this class. This class would handle the gitlike version history & async ability, as well as hold a document that is the ai summary / context doc for this thing in the database; if we make everything the same sort of object indexing the "full" database should be easier (maybe all the context docs are stored in a databse along with the git info, an entry being made here for every object that enters the system). 
```
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
```
1. using this "object" class idea from above I want to have everything now and forever have this prperty. 
2.yes it should always do invrese commits
3  for now can it fail closed and have a page for errors on the website where we can review them
4 track them all; internal updates as well as historical ones; we should add an ics refresh to the options for what to do while idle; 
5  with all this context adding and everything how long do you think it can be with the 32k token context window
6 yes the local wiki should be non ai-influenced sources of truth
7 I like that universal inbox recommendation; I was also thinking since there may not be "official" apis for these chat services can we poll them as if I was a real user (using regular internet scraping); we'd scrape new messages and send replies once a day; scheduled again as an idle task; we'd have a "blackbook" that contains contact info for people, including links to multiple different messaging services
8 yes, can this be in the merge error tab mentioned in a previous answer tab too on the website; call it a review tab and have "manual review" be a standard state for the "object class"
9 what's the difference here?
10 can you go further into the  details here?
11 yes go with the recommended
12 should remain none
13 json first with rendered views (in that obsidian ui style still)
14 should batch based on whats been updated recently (held in memory)
15 yes keep it at 15 minutes for now
16 reserve a safety margin (5min by default) except when entering the mode after the 15 min delay
17 no it should also be by the expected value; basicaly I want this agent to have full control of the system and have full knowledge of the system
```
## Decisions Locked (2026-03-10)

- **Obsidian mode**: Noctem-native web graph with optional markdown export.
- **Version control**: internal commit graph only (no system Git bridge in v0.9.4).
- **Memory pack budget (32k total)**: 4k recent chats, 5k recent commits, 7k top context docs, 6k wiki; reserve 10k for tools/output.
- **Source-of-truth boundary**: object registry + commit graph are canonical; external systems are imports/mirrors with explicit provenance.
- **Universal Inbox + external connectors**: deferred to Future Features (not active v0.9.4 execution scope).
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
  - object registry + append-only commit/event history for all entities (typed tables preserved for domain fields).
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
| Zero-Downtime Deployment | High | Graceful reload deploy process | Deploy script, health checks, migration checks | Gunicorn signal handling + compatibility-safe migrations | Replace production runtime assumption from Flask dev run to Gunicorn-managed app process; keep app factory pattern; enforce migration compatibility gates pre-reload. | Keep rollback script for failed health checks. |
| Embedding Classification | High | Semantic intent detection with fallback safety | Labeled utterances + live traces | Embedding model + similarity thresholds + deterministic fallback | Integrate sentence-embedding classifier alongside current router/rule-based intent path; keep hard fallback to existing deterministic classifier when confidence low. | Preserve explainability and audit logs for route decisions. |
| Digital Aristotle | Medium | Socratic Q&A + review scheduling | Wiki chunks + user-selected domains | Question-generation + spaced repetition scheduler | Use existing wiki retrieval for evidence-backed prompts; add review queue with SM-2/FSRS-like scheduling metadata and opt-in user sessions. | Must remain opt-in, not ambient nagging. |
| Meal Planning | Medium | Weekly plan + grocery list generation | Pantry, dietary prefs, local goals/calendar | Pantry DB + recipe/food metadata source + planner | New pantry + meal plan tables; use task/calendar slots for execution windows; Open Food Facts integration via `requests` when API connectors are added. | Keep “Later” depth features optional, but base planning included in v0.9.4 scope. |
| Obsidian-like Interface for Personal Wiki | High | Graph/navigation-first wiki exploration in web UI | Notes, links, tags, source metadata | Graph view UI + backlink index + search | Build graph API from existing wiki chunks/links and add web graph component; Noctem already stores docs/chunks and can expose node-edge endpoints. | Noctem-native web graph with optional markdown export. |
| Git-like Versioning for Local Docs | High | Version history + diff + restore for docs | Markdown/doc edits | Internal commit graph + diff/restore APIs | Extend durable history model to docs entity type; expose commit log/diff/restore actions in UI; no system Git bridge in v0.9.4. | Obsidian-like interface should expose version controls via internal commits. |
| Warp-style Interrupt + Appended Instructions | High | Interrupt and continue with refined instructions in same workflow | User decisions + follow-up instructions | Structured interrupt payload + resume routing | Existing interrupt flow in `agent/workflow.py` and `chat_orchestrator.py` can be extended from yes/no to `{decision,instructions,scope_edits}` contract. | Align behavior with “refine request” style interactions. |
| LangGraph Runtime + Memory Pack | High | Durable conversational state + resumable HITL + bounded context assembly | Thread messages, summaries, recent mutation commits | LangGraph checkpointer/store + memory assembler | Introduce LangGraph runtime wrapper while preserving current API envelope; add memory pack builder using conversations + commit history + temporal context with explicit budgets (4k chats, 5k commits, 7k context docs, 6k wiki; reserve 10k for tools/output). | Budgets supersede earlier “last N chats” defaults. |
| Git-like Mutation History for Tasks + Calendar Events | High | Immutable audit trail + queryable history + inverse-commit undo | All committed mutations | Append-only commit tables + parent pointers + refs + change records | Replace in-memory audit stores in MCP tools with DB-backed history service; include `time_blocks` mutations in same commit graph model. | Undo should be inverse commit, never destructive rewrite. |
| Entity Context Docs (Task/Project/Goal/Doc/Calendar) | High | Per-entity context artifacts for accurate retrieval and explainability | Entity snapshots + commit history + relations | Async context-doc synthesizer + context-doc store + retrieval hooks | Build from existing conversations + workflow outputs + commit history into canonical per-entity docs; run via slow runner to avoid hot-path latency. Use docs as top-tier RAG context objects before raw logs. | Primary accuracy/memory lever; should include original creation context, change history, and related entities. |
| Adaptive Slow Runner (Inactivity-Budgeted) | High | Single “what can I run now?” passive executor based on idle time and pending work | Session inactivity timestamp + job runtime estimates + queue states | APScheduler coordinator + job runtime telemetry + dispatch policy | Replace fixed periodic passive pattern with coordinator that triggers after inactivity (initial 15m), computes budget, and selects jobs where expected runtime fits budget. Voice processing only runs when `voice_journals` pending count > 0. | Start simple with deterministic policy and measured runtime medians per job type. |
| Calendar Event Intelligence & Planning Awareness | High | Calendar-aware planning, prioritization, and conflict detection | Imported ICS + manual events + task deadlines | Time-block normalization + conflict resolver + planner hooks | Existing `ics_import` + `time_blocks` provide foundation; add conflict detector and planning heuristics in workflow/query layers and memory pack. | Keep ICS-first direction and avoid reintroducing removed Google OAuth sync path unless explicitly requested. |

---

## Implementation Research Sources (Mar 2026, expanded)
1) **Universal Object Core + Durable History**
- **Version Control Is for Your Data Too** (https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.SNAPL.2019.8)
  - Supports: DVCS concepts (immutable commits, branching, merge, provenance) are broadly applicable to data systems, not only source code.
  - Limitations/Drawbacks: conceptual paper, not a full production relational implementation guide.
  - Noctem implementation specifics: supports `objects` + `object_events` + `object_refs` as canonical lineage with auditable heads.
- **GlassDB: An Efficient Verifiable Ledger Database System Through Transparency** (https://arxiv.org/abs/2207.00944)
  - Supports: append-only, verifiable history model for tamper-evident audit trails.
  - Limitations/Drawbacks: cryptographic verification adds complexity and can impose throughput/latency trade-offs.
  - Noctem implementation specifics: use hash-linked commits in `object_versions` and surface verification signals in Review.
2) **Context Docs + Memory Pack Assembly**
- **MemGPT: Towards LLMs as Operating Systems** (https://arxiv.org/abs/2310.08560)
  - Supports: multi-tier memory with explicit promotion/eviction control.
  - Limitations/Drawbacks: weak policies can persist noise and degrade retrieval quality.
  - Noctem implementation specifics: deterministic 4k/5k/7k/6k pack buckets with explicit truncation/accounting and 10k reserve.
- **Generative Agents: Interactive Simulacra of Human Behavior** (https://arxiv.org/abs/2304.03442)
  - Supports: memory-stream + reflection loops improve longitudinal coherence and planning quality.
  - Limitations/Drawbacks: computationally expensive; unfiltered reflections can drift quality.
  - Noctem implementation specifics: async synthesis only, provenance-weighted reflection inclusion.
3) **Inactivity‑Budgeted Slow Runner**
- **Idletime Scheduling Dissertation** (https://eggert.org/dissertation/)
  - Supports: secondary work can be scheduled in idle windows with budget controls.
  - Limitations/Drawbacks: idle prediction errors can still impact responsiveness.
  - Noctem implementation specifics: 15-minute idle trigger, runtime-fit dispatch, default 5-minute safety margin.
- **Restrained Utilization of Idleness for Transparent Background Work** (https://www1.ece.neu.edu/~ningfang/papers/nmi-sigmetrics09.pdf)
  - Supports: conservative idle use reduces user-visible interference.
  - Limitations/Drawbacks: conservative policy can underutilize available idle capacity.
  - Noctem implementation specifics: rank jobs by expected value/runtime, not runtime alone.
4) **Retrieval + RAG Integration**
- **Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks** (https://arxiv.org/abs/2005.11401)
  - Supports: retrieval grounding improves factuality versus pure parametric generation.
  - Limitations/Drawbacks: retrieval quality errors propagate into answers.
  - Noctem implementation specifics: query context docs first, then wiki chunks, with citations/provenance attached.
- **Retrieval-Augmented Generation for Large Language Models: A Survey** (https://arxiv.org/abs/2312.10997)
  - Supports: consolidated design/failure-mode map for indexing, retrieval, and evaluation choices.
  - Limitations/Drawbacks: broad survey guidance still requires local parameter testing.
  - Noctem implementation specifics: add citation/trust-weight evaluation harness before autonomy expansion.
5) **Review + Error Surfaces (HITL)**
- **A Survey of Human-in-the-loop for Machine Learning** (https://arxiv.org/abs/2108.00941)
  - Supports: targeted human intervention improves reliability at decision boundaries.
  - Limitations/Drawbacks: broad intervention can increase latency and operator burden.
  - Noctem implementation specifics: limit manual review to risky/ambiguous/high-blast-radius operations and support batch handling in Review UI.
- **Constructing Explainable Classifiers from the Start—Enabling Human-in-the Loop ML** (https://www.mdpi.com/2078-2489/13/10/464)
  - Supports: explanation-first systems improve correction quality and trust.
  - Limitations/Drawbacks: explainability constraints may reduce peak model performance in some tasks.
  - Noctem implementation specifics: persist structured reason codes for every review/interrupt decision.
6) **Obsidian Interface + Internal Versioning**
- **An Ecosystem for Personal Knowledge Graphs: A Survey and Research Roadmap** (https://arxiv.org/abs/2304.09572)
  - Supports: PKG patterns for entity/relationship lifecycle and retrieval grounding.
  - Limitations/Drawbacks: ontology drift/interoperability issues increase long-term maintenance cost.
  - Noctem implementation specifics: maintain minimal stable ontology (task/project/goal/doc/event/contact) mapped to internal objects.
- **Personal Knowledge Graph Population from User Utterances** (https://www.microsoft.com/en-us/research/publication/personal-knowledge-graph-population-from-user-utterances-in-conversational-understanding/)
  - Supports: practical extraction of personal entities/relations from conversational utterances.
  - Limitations/Drawbacks: ambiguity can create false links when confidence thresholds are weak.
  - Noctem implementation specifics: confidence gating + disambiguation prompts; route low-confidence graph edges to `manual_review`.
7) **Documentation Updates**
- **Documenting research software in engineering science** (https://www.nature.com/articles/s41598-022-10376-9)
  - Supports: documentation quality directly impacts reproducibility and maintainability.
  - Limitations/Drawbacks: guidance is domain-general and not a ready-made governance workflow.
  - Noctem implementation specifics: docs-and-rules sync as a release gate before build phases.
- **Assessing the alignment between developer information needs and documentation** (https://arxiv.org/abs/2202.04431)
  - Supports: docs are most useful when mapped to real implementation decisions and developer tasks.
  - Limitations/Drawbacks: requires iterative maintenance and continuous calibration.
  - Noctem implementation specifics: keep sections mapped to concrete tasks (schema, runtime, UI, safety, retrieval) with source-backed rationale.

---

## Existing Core References (kept)
1. LangGraph — Human-in-the-loop: https://langchain-ai.github.io/langgraph/concepts/human_in_the_loop/
2. LangGraph — Interrupts: https://langchain-ai.github.io/langgraph/concepts/interrupts/
3. MCP Overview: https://modelcontextprotocol.io/docs/introduction
4. MCP Architecture: https://modelcontextprotocol.io/docs/concepts/architecture
5. MCP Transports: https://modelcontextprotocol.io/docs/concepts/transports
6. n8n Integrations: https://docs.n8n.io/integrations/

---

## Future Features (Deferred)
### 1) Universal Inbox + External Connectors
- Scope: deferred from active v0.9.4 execution. Keep web dashboard and Telegram chat modes unchanged in this version.
- Planned capability: normalized inbox envelope schema with dedupe keys and provenance, a “blackbook” contact graph, and connector adapters for polling/scraping sources; outbound actions remain approval-gated with full mutation history.
- Implementation intent for later: define stable envelope fields (`source`, `external_id`, `fingerprint`, `timestamp`, `provenance`, `review_state`), normalize all inbound events into one internal format, and route low-confidence/ambiguous events to `manual_review`.
### 2) Additional Deferred Features (TBD)
- Placeholder section for deferred roadmap ideas that are not in active v0.9.4 scope.
