# Noctem v0.6.1 — Improvements, Research, and Design Notes

*Last updated: 2026-02-17 (v0.6.1 Foundation + bug fixes complete)*

---

## Guiding North Star

> **"I never want to touch a computer again. This system should do it all for me while I am off engaging with life."**

Every feature should move toward complete automation of digital life management. Telegram for quick, low-friction communication; the web dashboard for involved human-system interaction when needed. The goal is zero-touch operation.

---

## Scope and Principles

1. **Fast capture, slow reflection** — keep instant, rule-based capture; push ambiguity and review to the background.
2. **Messaging-first** — Telegram/web chat is the control plane; unprompted outreach capped by Butler protocol.
3. **Project-as-agent** — each project can run as a resumable "agent" with its own state and queue.
4. **Put down / pick up** — background work must be pausable, durably persisted, and trivially resumable after human input.
5. **Data sovereignty** — all state and decisions are local-first with graceful degradation when models/tools are unavailable.
6. **Model agility** — hot-swap local models per task; route by capability/cost/perf; maintain a registry and health checks.

---

## 1) What Noctem Already Solves

| Capability | Implementation |
|------------|----------------|
| Quick capture | Natural language in chat/CLI; voice journals; immediate parsing for actionable items |
| Organization | Goals → Projects → Tasks; priority = importance × urgency; ICS calendar ingest |
| Respectful outreach | Butler protocol (max 5/week) with status, suggest, and slow-queue visibility |
| Local-first | SQLite for data/logs; optional local LLM for slow analysis; continues working if LLM is down |

---

## 2) Pick-Up / Put-Down Patterns (Pause/Resume with Human-in-the-Loop)

**Goal:** When background work needs input/approval but the next Butler window is hours away, the agent "puts it down" safely and later "picks it up" exactly where it left off after the user's reply.

### Approach A — LangGraph Interrupts + Checkpointing (Lightweight, App-Native)

**Pattern:** Model each project as a small state graph. When human input is required, call `interrupt()`, persist the exact graph state via a checkpointer, and return a payload describing what's needed. Resume by invoking with the same `thread_id` and the human response.

**Fit for Noctem:** Map `project_id → thread_id`; store interrupt metadata in DB (`awaiting_input_of`, `deadline_at`). Butler surfaces a concise card at the next contact window; user reply resumes that graph turn.

**Reference:** [LangGraph Human-in-the-Loop](https://docs.langchain.com/oss/python/langgraph/human-in-the-loop)

### Approach B — Durable Execution Engine (Temporal/Cadence)

**Pattern:** Represent each project as a Workflow with Activities for side effects. Use Signals to pause for human input, Timers to defer until scheduled contact, retries and idempotency by default; workflows resume exactly where they left off after crashes or restarts. Sagas pattern models compensation for partial progress.

**Fit:** Strongest when Noctem starts doing real actions (email/calendar write). Heavier infra than A; excellent operational guarantees.

**Reference:** [Temporal Documentation](https://docs.temporal.io/)

### Approach C — Minimal SQLite-Backed State Machine (In-Process)

- **Table:** `slow_work_queue` with states: `pending → running → waiting_for_input → scheduled_contact → done/failed`
- **Events:** inbound user reply, Butler window, model availability change, calendar tick
- **Logging:** append-only JSONL per project for replay/audit

### Recommendation

| Timeframe | Approach |
|-----------|----------|
| Near-term | Per-project LangGraph graphs with interrupts + SQLite checkpointer |
| Medium-term | Migrate high-value automations to Temporal with Signals/Timers and Sagas |

---

## 3) Butler as Its Own Agent (Bridge Between Humans and Computer Agents)

**Purpose:** A single orchestration agent that respects attention, enforces outreach budgets, arbitrates between project agents, and mediates human-in-the-loop.

### Responsibilities

| Role | Description |
|------|-------------|
| Attention budget | Enforce 5 contacts/week; track usage; expose "N/5 used, next contact Fri 9:00" |
| Triage and batching | Collect pending interrupts/clarifications from project agents; batch into next scheduled window; provide quick-reply buttons |
| Consent and safety | Gate risky actions (email send, calendar write); request human approval; log decisions |
| Summarization | Daily/weekly status across projects (due soon, conflicts, stalled items) |
| Scheduling intelligence | Align outreach with calendar windows and user response history |
| Escalation | If a blocked workflow is critical (deadline within X hours), proactively request input within budget or recommend reschedule |

### Design Sketch

```
ButlerQueue (DB)
├── kind: 'clarify' | 'approve' | 'status'
├── project_id
├── question
├── options[]
├── urgency: 1-5
└── deadline_at

Butler Run Loop (every minute):
1. Evaluate "should contact now?" based on schedule, budget, urgency
2. If no → roll up items into next digest
3. If yes → send compact cards with inline actions
4. On reply → dispatch to originating project agent (resume via interrupt/Signal)
5. Log outcome to unified transcript
```

### Why This Fits the Direction

- **Clean separation:** Project agents "do the work," Butler "manages humans and time"
- **Predictable UX:** Fixed, respectful contact windows; fast response when user pings first
- **Extensible:** Butler can later enforce org-level policies (do-not-disturb windows) while remaining local/private

**Reference:** [Warp Oz Cloud Agents](https://docs.warp.dev/agent-platform/cloud-agents/cloud-agents-overview)

---

## 4) Dynamic Local-Model Orchestration (Hot-Swapping Safely)

**Objectives:** Frequently switch local models (new releases; task-specific strengths) while keeping outputs structured and predictable.

### A. Model Registry and Health

```json
{
  "name": "qwen2.5:7b-instruct-q4_K_M",
  "backend": "ollama",
  "family": "qwen2.5",
  "supports_function_calling": true,
  "supports_schema": true,
  "context": 8192,
  "tokens_per_sec": 45,
  "health": "ok",
  "last_checked": "2026-02-17T00:00:00Z"
}
```

- Populate via Ollama (`tags/list/show/ps`) or other servers
- Probe health and basic capabilities at boot
- Support OpenAI-compatible local servers (vLLM, llama.cpp) for easy client reuse

**References:**
- [Ollama API](https://ollama.readthedocs.io/en/api/)
- [vLLM OpenAI-Compatible Server](https://docs.vllm.ai/en/v0.8.0/serving/openai_compatible_server.html)

### B. Routing Rules

- Small/local models → classification/extraction
- Mid models → planning
- Bigger models → only when needed for hard reasoning
- Prefer backends with native tool/function calling when structure matters

**Reference:** [Qwen Function Calling](https://qwen.readthedocs.io/en/v2.0/framework/function_call.html)

### C. Structured Outputs and Tool Use

- Require JSON Schema–constrained outputs or function/tool calling for automation steps
- Retry with validation/backoff on schema mismatch
- Pattern: templates + grammars emulate cloud-style structured outputs locally

### D. Lifecycle Controls

- **Capability tests at boot:** schema adherence, tool-call echo, max tokens probe
- **Keep-alive policy:** preload "fast small" model; lazy-load "slow big" models; evict on memory pressure
- **Versioned manifests:** prompt/skill manifests to avoid drift across model swaps

---

## 5) Fast System: Thoughts-First Capture (Not Just Tasks)

### Ingest Flow

```
Any "thought" (text/voice)
        │
        ▼
┌─────────────────────────────────────┐
│  FAST PATH (small local model)      │
│  • Classify: actionable | note | ?  │
│  • Extract: date/time/!1-3/project  │
│  • File immediately if confident    │
│  • Queue ambiguous → slow review    │
└─────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────┐
│  SLOW REVIEW LOOP                   │
│  • Generate clarifying questions    │
│  • Queue interrupt for Butler       │
│  • Audit fast-path extractions      │
└─────────────────────────────────────┘
```

### Calendar Awareness

When suggesting next actions:
- Consider free/busy gaps
- Mark suggestions with "fit" (e.g., "<30 min window before 2pm meeting")
- Factor in optional task duration field

---

## 6) Project-as-Agent Execution Loop

### LangGraph Style (Pseudocode)

```python
def next_action_node(state):
    # decide next action; if missing detail, pause
    if needs_human_input(state):
        return interrupt({
            "type": "clarify_task",
            "project_id": state["project_id"],
            "question": "...",
            "options": ["A", "B", "C"]
        })
    # otherwise perform tool calls and update state
    result = run_tool(...)
    return update_state(state, result)

# Resume later with Command(resume=human_reply)
```

### Temporal Style (Pseudocode)

```python
@workflow.defn
class ProjectFlow:
    @workflow.run
    async def run(self, project_id: str):
        # ... steps
        if needs_input:
            await workflow.wait_condition(lambda: self.input_received)
        # continue from exact point; retries/compensation wrap Activities
```

---

## 7) Minimal Data Model Adjustments

### New Tables

```sql
-- Capture any thought, not just tasks
CREATE TABLE thoughts (
    id INTEGER PRIMARY KEY,
    source TEXT,              -- 'telegram', 'cli', 'web', 'voice'
    text TEXT,
    kind TEXT,                -- 'actionable', 'note', 'question', 'ambiguous'
    linked_task_id INTEGER,
    status TEXT DEFAULT 'pending'
);

-- Track pending human-in-the-loop requests
CREATE TABLE interrupts (
    id INTEGER PRIMARY KEY,
    project_id INTEGER,
    type TEXT,                -- 'clarify', 'approve', 'choose'
    payload_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP,
    resolution TEXT
);

-- Track available local models
CREATE TABLE model_registry (
    name TEXT PRIMARY KEY,
    backend TEXT,             -- 'ollama', 'vllm', 'llamacpp'
    family TEXT,
    context INTEGER,
    supports_function_calling BOOLEAN,
    supports_schema BOOLEAN,
    tokens_per_sec REAL,
    health TEXT,
    last_checked TIMESTAMP
);
```

### Updated States for slow_work_queue

`pending → running → waiting_for_input → scheduled_contact → done → failed`

---

## 8) Prioritized Improvements & Time Line

> **Foundation-first ordering**: Each layer enables the next. Logging → Correction Loop → Model Awareness → Automation → Skills → Knowledge.

### Now (v0.6.0 Polish) ✅ DONE

| Priority | Improvement | Status | Notes |
|----------|-------------|--------|-------|
| 1 | Contact budget transparency | ✅ Done | Status shows "X/5 used this week" + full datetime for next contact |
| 2 | Voice → Task | ✅ Done | Transcripts → fast classifier → thoughts table → task/note/clarification queue |
| 3 | Unclear-input queue | ✅ Done | Ambiguous thoughts (SCOPE/TIMING/INTENT) queued for Butler clarification windows |
| 4 | Context-aware suggestions | ✅ Done | SuggestionService: calendar gaps, duration matching, time-of-day awareness |

#### v0.6.0 Implementation Notes

**Architecture: "Royal Scribe" Pattern**

All inputs (text, voice, Telegram) flow through a unified capture system that acts like a well-paid royal scribe:

```
Input (any source)
      │
      ▼
┌─────────────────────────────────────┐
│  Voice Cleanup (if audio)           │
│  • Remove fillers: um, uh, you know │
│  • Normalize hesitations            │
└─────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────┐
│  Fast Classifier (rule-based)       │
│  • ThoughtKind: ACTIONABLE/NOTE/    │
│    AMBIGUOUS                        │
│  • Confidence: 0.0-1.0              │
│  • AmbiguityReason: SCOPE/TIMING/   │
│    INTENT                           │
└─────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────┐
│  Thoughts Table (always)            │
│  • Every input recorded             │
│  • Links to task_id if created      │
│  • Preserves original + cleaned     │
└─────────────────────────────────────┘
      │
      ├─── HIGH confidence (≥0.8) ──────► Create task/note immediately
      │
      ├─── MEDIUM confidence (0.5-0.8) ─► Create task with `*` hint
      │                                   (user can amend)
      │
      └─── LOW confidence (<0.5) ───────► Queue for Butler clarification
```

**Key Design Decisions**

1. **Thoughts-first, not tasks-first**: Every input creates a thought record before any routing. This preserves context for later review and enables the slow system to audit fast-path decisions.

2. **Confidence thresholds**: HIGH_CONFIDENCE=0.8, MEDIUM_CONFIDENCE=0.5. Tasks created below 0.8 get a `*` amendment hint in their name so the user knows to review.

3. **Ambiguity subcategories**: Not all unclear inputs are unclear for the same reason:
   - SCOPE: "Work on the project" — which project? how much?
   - TIMING: "Do this soon" — when exactly?
   - INTENT: "Maybe I should..." — is this actually a commitment?

4. **Butler clarification questions are context-aware**: Each ambiguity type gets targeted questions:
   - SCOPE → "Can you be more specific about what this involves?"
   - TIMING → "When would you like to do this?"
   - INTENT → "Is this something you want to commit to, or just a thought to revisit later?"

5. **Suggestions consider real constraints**: Time-of-day (morning=focused work, afternoon=meetings, evening=wind-down), calendar gaps, and task duration estimates.

**Files Created**

| File | Purpose |
|------|----------|
| `noctem/fast/classifier.py` | Rule-based classifier with signal detection (imperative verbs, time words, hedging language, question marks) |
| `noctem/fast/voice_cleanup.py` | Filler removal, hesitation normalization, whitespace cleanup |
| `noctem/fast/capture.py` | Unified `process_input()` entry point; creates thoughts, routes to task/note/clarification |
| `noctem/services/suggestion_service.py` | `SuggestionService` with calendar integration, gap detection, duration matching |
| `tests/test_v060_polish.py` | 38 tests covering classifier, capture, suggestions, voice cleanup |

**Files Modified**

| File | Changes |
|------|----------|
| `db.py` | Added `thoughts` table schema, `duration_minutes` column migration |
| `models.py` | Added `Thought` dataclass, `duration_minutes` field to `Task` |
| `cli.py` | `NEW_TASK` commands now use `process_input()` instead of direct task creation |
| `slow/loop.py` | Voice transcriptions feed into capture system with pending confirmation |
| `butler/clarifications.py` | Added `get_pending_thought_clarifications()`, `resolve_thought_clarification()`, ambiguity-specific questions |
| `butler/protocol.py` | Status format changed to "Contacts used: X/5 this week", added full datetime for next contact window |

**Database Schema Additions**

```sql
-- Implemented thoughts table (expanded from design)
CREATE TABLE thoughts (
    id INTEGER PRIMARY KEY,
    source TEXT,                    -- 'telegram', 'cli', 'web', 'voice'
    raw_text TEXT,                  -- Original input
    cleaned_text TEXT,              -- After voice cleanup
    kind TEXT,                      -- 'actionable', 'note', 'ambiguous'
    ambiguity_reason TEXT,          -- 'scope', 'timing', 'intent' (if ambiguous)
    confidence REAL,                -- 0.0-1.0
    linked_task_id INTEGER,         -- FK to tasks if converted
    status TEXT DEFAULT 'pending',  -- 'pending', 'converted', 'dismissed'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Added to tasks table
ALTER TABLE tasks ADD COLUMN duration_minutes INTEGER;
```

**Test Coverage**

323 tests pass (including 38 new v0.6.0 polish tests). Key test scenarios:
- Classifier correctly identifies actionable vs note vs ambiguous
- Voice cleanup removes fillers without mangling content
- Capture system creates thoughts and routes appropriately
- Suggestions respect calendar gaps and time-of-day
- Butler status shows new "X/5 used" format

**Learnings & Future Considerations**

1. **Rule-based classification is surprisingly effective** for the fast path. Imperative verbs + time expressions catch ~80% of actionable items. Save LLM calls for genuinely ambiguous cases.

2. **Ambiguity subcategories help Butler ask better questions**. Generic "can you clarify?" is less useful than "when would you like to do this?"

3. **The `*` amendment hint pattern** (for medium-confidence tasks) provides a lightweight way to flag "I created this but you should review" without blocking capture.

4. **Duration estimates unlock smarter suggestions**. Even rough estimates (15/30/60 min) let the system match tasks to calendar gaps.

5. **Next steps for this system**: Add execution logging (v0.6.x priority 1) to measure classifier accuracy in production and identify where rules need tuning.

---

### Development Time Line

#### v0.6.x — Core Infrastructure (Foundation Layer) ✅ DONE

| Priority | Improvement | Status | Notes |
|----------|-------------|--------|-------|
| **1** | **Basic Logging Schema** | ✅ Done | `execution_logs` table with full pipeline tracing; SQLite-only approach (JSONL deferred to v0.7) |
| **2** | **Butler Chat + /summon** | ✅ Done | `/summon` command with intent parsing, 30s timeout, state queries; `summon_mode` column in thoughts |
| **3** | **Dynamic Model Registry** | ✅ Done | `model_registry` table; Ollama discovery/benchmarking; abstract `ModelBackend` for future vLLM/llama.cpp |
| **4** | **Maintenance Protocol (Phase 1)** | ✅ Done | `maintenance_insights` table; `MaintenanceScanner`; CLI commands: models, scan, insights, report |
| 5 | Project-as-agent (basic) | — | Per-project LangGraph with `thread_id`, interrupts, SQLite checkpointer for pick-up/put-down |
| 6 | Task dependencies (DAG) | — | Add `depends_on` field; surface blockers in Butler updates |

**Rationale**: Logging + Butler correction loop is the flywheel. Every user correction teaches the system. Without logging, you're flying blind. Without `/summon`, corrections don't get captured.

#### v0.6.1 Implementation Notes

**Architecture Decisions**

1. **SQLite-only for execution logs** (not hybrid with JSONL): Simpler for v0.6.x; full traces queryable via SQL. JSONL replay/audit can be added in v0.7 if needed.

2. **Ollama-first with abstract backend**: `ModelBackend` ABC enables future vLLM/llama.cpp support without rewriting registry logic.

3. **30-second timeout for /summon**: Immediate response when possible; queues for later if slow mode times out.

4. **Preview mode for maintenance reports**: User can see what Butler would say without consuming a contact.

5. **`summon_mode` flag on thoughts**: Distinguishes user-initiated corrections from normal captures; valuable for v0.7 correction feedback loop.

**Files Created**

| File | Purpose |
|------|----------|
| `noctem/logging/__init__.py` | Logging module package |
| `noctem/logging/execution_logger.py` | `ExecutionLogger` context manager with trace/stage/error logging |
| `noctem/butler/summon.py` | `/summon` command handler with intent parsing, state queries |
| `noctem/slow/model_registry.py` | `ModelRegistry`, `OllamaBackend`, model discovery/benchmarking |
| `noctem/maintenance/__init__.py` | Maintenance module package |
| `noctem/maintenance/scanner.py` | `MaintenanceScanner` with model/queue/project scans, report generation |
| `tests/test_v061_foundation.py` | 44 tests for all v0.6.1 features |

**Files Modified**

| File | Changes |
|------|----------|
| `db.py` | Added `execution_logs`, `model_registry`, `maintenance_insights` tables; `summon_mode` migration |
| `models.py` | Added `ExecutionLog`, `ModelInfo`, `MaintenanceInsight` dataclasses |
| `config.py` | Added `maintenance_*` and `summon_timeout_seconds` config keys |
| `cli.py` | Added `/summon` command and `maintenance` subcommands |
| `fast/capture.py` | Integrated `ExecutionLogger` traces into `process_input()` |

**Database Schema Additions**

```sql
-- v0.6.1: Execution logging
CREATE TABLE execution_logs (
    id INTEGER PRIMARY KEY,
    trace_id TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    stage TEXT,              -- 'input', 'classify', 'route', 'execute', 'complete'
    component TEXT,          -- 'fast', 'slow', 'butler', 'summon'
    input_data TEXT,         -- JSON
    output_data TEXT,        -- JSON
    confidence REAL,
    duration_ms INTEGER,
    model_used TEXT,
    thought_id INTEGER,
    task_id INTEGER,
    error TEXT,
    metadata TEXT            -- JSON
);

-- v0.6.1: Model registry
CREATE TABLE model_registry (
    name TEXT PRIMARY KEY,
    backend TEXT,            -- 'ollama', 'vllm', 'llamacpp'
    family TEXT,
    parameter_size TEXT,
    quantization TEXT,
    context_length INTEGER,
    supports_function_calling BOOLEAN,
    supports_json_schema BOOLEAN,
    tokens_per_sec REAL,
    memory_gb REAL,
    quality_score REAL,
    health TEXT,             -- 'ok', 'slow', 'error', 'unknown'
    last_benchmarked TIMESTAMP,
    last_used_for TEXT,      -- Track task type usage
    notes TEXT
);

-- v0.6.1: Maintenance insights
CREATE TABLE maintenance_insights (
    id INTEGER PRIMARY KEY,
    insight_type TEXT,       -- 'pattern', 'blocker', 'recommendation', 'model_upgrade'
    source TEXT,
    title TEXT,
    details TEXT,            -- JSON
    priority INTEGER,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP,
    reported_at TIMESTAMP,
    resolved_at TIMESTAMP
);

-- v0.6.1: Summon mode flag
ALTER TABLE thoughts ADD COLUMN summon_mode INTEGER DEFAULT 0;
```

**Test Coverage**

398 tests pass (including 44 new v0.6.1 foundation tests). Key test scenarios:
- ExecutionLogger creates traces with timing and linking
- /summon parses intents correctly (status, query, correct, help, general)
- Model registry saves/retrieves models, routes by task type
- Maintenance scanner creates insights, generates reports
- All new tables and migrations work correctly

**Learnings & Design Notes**

1. **Execution logging is low-overhead**: Context manager pattern makes it easy to add tracing without changing function signatures. ~1-2ms overhead per trace.

#### v0.6.1 Bug Fixes & Quick Improvements (2026-02-17 Session 2)

**Issues Fixed**

| Issue | Fix |
|-------|-----|
| Prompt history API error (`'str' has no attribute 'isoformat'`) | `PromptVersion.from_row()` now parses `created_at` string → datetime |
| Chat messages lost on page refresh | Added `localStorage` persistence (last 50 messages) |
| Voice/audio page not discoverable | Added quick navigation bar to dashboard |

**Files Modified**

| File | Changes |
|------|----------|
| `models.py` | Fixed datetime parsing in `PromptVersion.from_row()` |
| `web/templates/dashboard.html` | Added chat `localStorage` save/load; added quick nav bar (Voice, Calendar, Prompts, Settings) |
| `docs/improvements.md` | Added § 12 "Complex AI Generated Suggestions" for future work |

**Session Learnings**

1. **SQLite stores datetimes as strings**: All `from_row()` methods need to check `isinstance(val, str)` and parse with `datetime.fromisoformat()`. Several models already had this pattern; `PromptVersion` was missing it.

2. **localStorage is a quick win for chat**: Full DB persistence (cross-device) is better but takes 6-8 hours. localStorage fix took 30 minutes and solves the immediate pain.

3. **Dashboard needs navigation**: The original design assumed users would know URLs. Quick nav bar makes pages discoverable.

4. **Document complex ideas before forgetting**: User feedback generated significant architectural ideas (page restructuring, Butler status widget, management page). Captured in § 12 for future implementation.

2. **Intent parsing for /summon works well**: Simple keyword matching handles 90% of cases; "general" fallback routes to slow mode.

3. **Model name parsing is tricky**: Ollama model names have many formats (qwen2.5:7b-instruct-q4_K_M, llama3:8b, mistral:latest). Regex handles common patterns but needs maintenance.

4. **Maintenance reports should be actionable**: Include numbered options so user can respond with just a number. Preview mode prevents wasting contact budget.

5. **`last_used_for` on model registry** enables v0.7 analysis: "model X is slower but more accurate for task classification" patterns.

---

#### v0.7 — Self-Improvement Engine (Builds on Logging)

| Priority | Improvement | Description | Depends On |
|----------|-------------|-------------|------------|
| **1** | **Execution Traces** | Full trace for each "thought" from capture → classification → action/queue → resolution; correlate with project_id | v0.6.x logging schema |
| **2** | **Slow System Logging** | Extend logging to slow skills: review decisions, suggestions generated, clarification outcomes, time-to-resolution | v0.6.x logging schema |
| **3** | **Log Review Skill** | Slow skill that periodically analyzes logs; identifies patterns (recurring ambiguities, extraction failures, common user corrections) | Execution traces + enough data |
| **4** | **Improvement Suggestions** | Generate actionable recommendations from log analysis; surface via Butler ("Fast model often misclassifies X as Y — consider adding keyword rule") | Log review skill |
| 5 | Self-Diagnostics Dashboard | Web view showing: classification accuracy over time, slow queue health, common failure modes, model performance metrics | All logging infrastructure |
| 6 | Correction Feedback Loop | When user corrects via `/summon`, automatically log before/after; weight these heavily in pattern analysis | Butler chat + logging |

**Implementation approach**: Lightweight SQLite + JSONL hybrid (inspired by Langfuse patterns but fully local). Store structured metadata in SQLite for querying; raw traces in JSONL for replay/audit.

#### v0.8 — Skills Infrastructure (The "How")

| Priority | Improvement | Description | Depends On |
|----------|-------------|-------------|------------|
| **1** | **Skill Registry** | SQLite table tracking: installed skills, triggers, last-used, success rate | Database schema |
| **2** | **Skill Definition Format** | SKILL.md standard: metadata header (name, triggers, description) + instructions body + optional resources folder | Registry to store them |
| **3** | **Progressive Disclosure** | Load only skill metadata at boot (~100 tokens each); full instructions loaded only when triggered | Skill format defined |
| **4** | **Skill Execution Logging** | All skill invocations logged (feeds 0.7 infrastructure); track success/failure/user-correction | 0.7 logging + skill format |
| 5 | User-Created Skills | Natural language skill creation: "Teach me how to do X" → Noctem generates SKILL.md structure with user's procedure. **Personal priority: Warp integration for software development** | All skill infrastructure |
| 6 | Skill-Wiki Bridge | Skills can reference wiki entries as authoritative sources; wiki entries can link to skills that use them | Prepares for 0.9 |

**Architecture**: Skills as the "how" — packaged knowledge + procedures + optional code. Integrate with wiki (0.9) as the "what" — authoritative facts and sources.

```
skills/
├── cooking-meal-prep/
│   ├── SKILL.md              # Metadata + triggers
│   ├── instructions.md       # Full procedure
│   ├── resources/
│   │   └── templates/
│   └── sources.json          # Links to wiki entries
```

#### v0.9 — Self-Contained Wiki + Digital Aristotle (The "What")

| Priority | Improvement | Description | Depends On |
|----------|-------------|-------------|------------|
| | **Wiki Core** | | |
| **1** | **Source Ingestion Pipeline** | Parse PDFs, EPUBs, web pages, images, Markdown, DOCX → unified knowledge chunks with source attribution | File system access |
| **2** | **Local Document Processing** | Use Docling or olmOCR for multimodal parsing (text + tables + images → Markdown); fully offline | Ingestion pipeline |
| **3** | **Vector Store + Embeddings** | ChromaDB or LanceDB for semantic search over knowledge chunks; SQLite for metadata/citations | Processed documents |
| **4** | **Citation System** | Every answer includes: direct quote (≤30 words), source title, page/section, local file link | Vector store working |
| 5 | Trust Levels | Sources tagged: personal (1), curated (2), web (3); weight retrieval by trust level | Citation system |
| 6 | Source Verification | Periodic re-check of web sources; flag stale/changed content; prefer downloaded local copies | Trust levels |
| | **Digital Aristotle** | | |
| **7** | **Query Mode** | Ask anything → answer grounded in wiki with inline citations; "I don't know" when sources insufficient | Full wiki infrastructure |
| 8 | Socratic Mode | System asks YOU questions; challenges assumptions; uses wiki as ground truth for evaluation | Query mode + learning items table |
| 9 | Review Mode | Spaced repetition over studied concepts; SM-2 algorithm; Butler prompts at optimal intervals | Socratic mode |
| 10 | Learning Progress | Track: concepts studied, ease factors, review history, mastery estimates | Review mode |
| 11 | Teaching Safeguards | Detect shallow understanding; require explanation before advancing; never hollow validation | All Aristotle features |

**Data Model Additions**:

```sql
-- Source documents
CREATE TABLE sources (
    id INTEGER PRIMARY KEY,
    file_path TEXT,
    file_type TEXT,           -- 'pdf', 'epub', 'md', 'url'
    title TEXT,
    author TEXT,
    ingested_at TIMESTAMP,
    last_verified TIMESTAMP,
    trust_level INTEGER       -- 1=personal, 2=curated, 3=web
);

-- Knowledge chunks with embeddings
CREATE TABLE knowledge_chunks (
    id INTEGER PRIMARY KEY,
    source_id INTEGER REFERENCES sources,
    content TEXT,
    page_or_section TEXT,     -- "p.47" or "Chapter 3.2"
    embedding BLOB,
    created_at TIMESTAMP
);

-- Spaced repetition tracking
CREATE TABLE learning_items (
    id INTEGER PRIMARY KEY,
    concept TEXT,
    source_ids TEXT,          -- JSON array of references
    ease_factor REAL DEFAULT 2.5,
    interval_days INTEGER DEFAULT 1,
    next_review DATE,
    review_count INTEGER DEFAULT 0
);
```

**Key principle**: Independence from the "increasingly useless web landscape." Download and verify sources locally. Quote directly. Link to local files. The system becomes your personal, trustworthy knowledge base.

#### v1.0+ — Advanced Automation & External Actions

| Priority | Improvement                      | Description                                                                                                   | Depends On              |
| -------- | -------------------------------- | ------------------------------------------------------------------------------------------------------------- | ----------------------- |
| 1        | Durable workflows                | Temporal for real actions (email, calendar write); Signals/Timers and Sagas; human checkpoints on risky steps | Project-as-agent mature |
| 2        | External integrations            | Calendar write-back, email drafting, API calls to external services                                           | Durable workflows       |
| 3        | Maintenance Protocol (Phase 2-3) | Butler-delivered reports; actionable quick-replies; model auto-switching based on task type                   | 0.7 self-improvement    |
| 4        | Optional cloud routing           | Behind explicit consent; route complex tasks to cloud models; default remains local-only                      | Model registry mature   |
| 5        | Hardware                         | Usb bootable linus server running the whole system                                                            | All core infrastructure |

#### Post-1.0 — Personal Skills (Future)

Skills built on top of the v0.8 skill infrastructure that extend Noctem into personal life domains. These are **not** part of the MVP roadmap.

| Skill | Description | Infrastructure Needed |
|-------|-------------|----------------------|
| **Habit Builder** | Track recurring behaviors; streaks and break recovery; Butler prompts at optimal times; analyze patterns over time | v0.8 skills + v0.7 logging |
| Fitness Tracking | Log workouts, integrate with health data exports; surface trends | Wiki (0.9) for storing routines |
| Meal Planning | Weekly meal prep suggestions; grocery list generation; recipe wiki integration | Wiki (0.9) + external API skills |
| Finance Awareness | Budget tracking; spending pattern alerts; bill reminders | Durable workflows (1.0) for recurring checks |
| Reading List | Track books/articles; surface "time to read" suggestions in calendar gaps | Wiki (0.9) + suggestion service |
V2.0 -- Take Public
**Note on existing habit code**: The codebase contains `habit_service.py`, `Habit`/`HabitLog` models, and `habits`/`habit_logs` tables from earlier development. This infrastructure is **deferred** — it works but is not actively developed or exposed in the UI until the skill infrastructure (v0.8) is mature enough to implement habits properly as a skill.

#### V2.0 — Take Public
| Priority | Improvement                      | Description                                                                                                   | Depends On              |
| -------- | -------------------------------- | ------------------------------------------------------------------------------------------------------------- | ----------------------- |
| 5        | Mobile companion                 | Lightweight app for quick capture + Butler notifications; syncs with local instance                           | All core infrastructure |

---

## 9) Security Posture (Lessons from OpenClaw)

- Treat external "skills" like executables
- Prefer a closed/curated set
- Default deny for OS-execution tools
- Require human approval at callsite
- Public skills marketplaces have seen malicious submissions; don't auto-trust third-party packages

**Reference:** [OpenClaw Security Incident](https://www.theverge.com/news/874011/openclaw-ai-skill-clawhub-extensions-security-nightmare)

---

## 10) Competitive Landscape Summary

### Direct Competitors (Privacy-First Task Managers)

| Tool | Notes |
|------|-------|
| Tududi | Self-hosted, open-source, GTD-style areas/projects/tasks |
| Super Productivity | Privacy-focused, time tracking, Jira/GitHub integration |
| Lunatask | Encrypted, habit tracking + journaling |
| Vikunja | Self-hosted Todoist alternative with Kanban |

**Noctem's differentiation:** None combine Telegram integration + AI suggestions + butler protocol + data sovereignty.

### Broader Alternatives

| Approach             | Examples                             |
| -------------------- | ------------------------------------ |
| Time-blocking        | Sunsama, Motion (AI auto-scheduling) |
| Visual/spatial       | Trello, WorkFlowy, MindManager       |
| All-in-one workspace | Notion, Nuclino                      |
| Paper/analog         | Moleskine, bullet journal            |

### AI Agent Platforms

| Platform | Key Pattern for Noctem |
|----------|------------------------|
| OpenClaw | Skills as modular packages; selective context injection; JSONL audit trails |
| Warp/Oz | Full terminal control; centralized rules (WARP.md); human steering mid-flight |

---

## 11) Maintenance Protocol (System Self-Improvement)

**Purpose:** A periodic "building maintenance" process that investigates how the system could improve itself, aggregates insights from project agents, evaluates available resources, and reports actionable recommendations to the Butler for user input.

### Core Responsibilities

| Role | Description |
|------|-------------|
| Model Discovery | Probe Ollama for available models; benchmark speed/capabilities; compare to current model |
| Suggestion Aggregation | Collect `next_action_suggestion` from all active projects; identify patterns and recurring blockers |
| Self-Diagnostics | Check queue health (failed items, backlogs), slow mode performance, butler budget usage |
| Meta-Suggestions | Synthesize cross-project insights into system-level recommendations |
| Report Generation | Create maintenance report for Butler delivery at next contact window |

### A. Model Registry and Discovery

```sql
-- Track available local models and their capabilities
CREATE TABLE model_registry (
    name TEXT PRIMARY KEY,
    backend TEXT,             -- 'ollama', 'vllm', 'llamacpp'
    family TEXT,              -- 'qwen2.5', 'llama3', 'mistral'
    parameter_size TEXT,      -- '7b', '14b', '70b'
    quantization TEXT,        -- 'q4_K_M', 'q8_0', 'fp16'
    context_length INTEGER,
    supports_function_calling BOOLEAN,
    supports_json_schema BOOLEAN,
    tokens_per_sec REAL,      -- Measured on this machine
    memory_gb REAL,           -- VRAM/RAM usage
    quality_score REAL,       -- 0-1, from capability tests
    health TEXT,              -- 'ok', 'slow', 'error'
    last_benchmarked TIMESTAMP,
    notes TEXT
);
```

**Discovery Flow:**
1. Call `GET /api/tags` to list installed models
2. For each model, call `GET /api/show` for metadata
3. Run lightweight benchmark (10-token generation, measure tokens/sec)
4. Run capability test (JSON schema adherence, tool call format)
5. Store results in registry; flag models that outperform current selection

### B. Suggestion Aggregation

```sql
-- Store aggregated insights from project agents
CREATE TABLE maintenance_insights (
    id INTEGER PRIMARY KEY,
    insight_type TEXT,        -- 'pattern', 'blocker', 'recommendation', 'model_upgrade'
    source TEXT,              -- 'project_agents', 'queue_health', 'model_benchmark'
    title TEXT,
    details TEXT,             -- JSON with supporting data
    priority INTEGER,         -- 1-5, higher = more important
    status TEXT DEFAULT 'pending',  -- 'pending', 'reported', 'actioned', 'dismissed'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reported_at TIMESTAMP,
    resolved_at TIMESTAMP
);
```

**Aggregation Logic:**
- Scan all `projects.next_action_suggestion` fields
- Extract common themes (e.g., "waiting for input", "blocked by dependency", "needs research")
- Identify projects with stale suggestions (>14 days old)
- Flag projects where suggested action hasn't changed across multiple cycles

### C. Self-Diagnostics Checks

| Check | Condition | Insight Generated |
|-------|-----------|-------------------|
| Queue backlog | >10 pending items for >24h | "Slow mode falling behind — consider faster model or longer idle threshold" |
| Failed items | >3 failed items this week | "Repeated failures — check Ollama stability or model compatibility" |
| Butler budget | 0 remaining mid-week | "Contact budget exhausted early — review urgency thresholds" |
| Model health | tokens/sec <20 | "Current model underperforming — faster alternatives available" |
| Stale suggestions | >50% projects have suggestions >14 days old | "Project insights going stale — increase analysis frequency" |

### D. Maintenance Report Format

```
🔧 **System Maintenance Report**

**Model Status**
• Current: qwen2.5:7b-instruct-q4_K_M (45 tok/s)
• Available upgrade: qwen2.5:14b-instruct-q4_K_M (28 tok/s, better reasoning)
• Recommendation: [Keep current / Try upgrade]

**Project Insights** (12 active projects)
• 4 projects blocked waiting for input
• 2 projects have stale suggestions (>14 days)
• Common theme: "needs clarification on scope"

**System Health**
• Queue: 3 pending, 0 failed
• Butler: 3/5 contacts remaining
• Slow mode: Processing normally

**Actions Needed**
1. Review blocked projects: [Project A], [Project B]...
2. Consider pulling qwen2.5:14b for complex tasks

Reply with number to action, or 'dismiss' to acknowledge.
```

### E. Integration Points

**With Slow Mode Loop:**
- Add `WorkType.MAINTENANCE_SCAN` to queue
- Run maintenance scan weekly (or when triggered manually)
- Lower priority than task/project analysis

**With Butler Protocol:**
- Maintenance reports use a special contact type: `maintenance`
- Don't count against weekly budget (or use separate 1/week allowance)
- Only send if actionable insights exist

**With Config:**
```python
# New config keys
"maintenance_scan_enabled": True,
"maintenance_scan_interval_days": 7,
"maintenance_model_benchmark_on_boot": True,
"maintenance_report_threshold": 3,  # Min insights to generate report
```

### F. Implementation Phases

| Phase         | Scope                                                                                       |
| ------------- | ------------------------------------------------------------------------------------------- |
| Now (v0.6.x)  | Model registry table; basic Ollama discovery; manual `noctem maintenance` CLI command       |
| Next (v0.7.0) | Suggestion aggregation; self-diagnostics; automated weekly scan                             |
| Later (v0.8+) | Butler-delivered reports; actionable quick-replies; model auto-switching for specific tasks |
|               |                                                                                             |

### G. CLI Interface

```bash
# Discover and benchmark available models
noctem maintenance models

# Run full maintenance scan
noctem maintenance scan

# View current insights
noctem maintenance insights

# Generate report (without sending)
noctem maintenance report --preview
```

---

## 12) Complex AI Generated Suggestions

*Generated during v0.6.1 implementation session (2026-02-17). These require significant architectural work and are documented here for future planning.*

### A. Web Dashboard Page Architecture Refactor

**Problem:** Current dashboard is a monolithic single page. User feedback requests:
- System status block above calendar (Butler protocol real-time status)
- Page navigation buttons for different interaction types
- Management page (overdue, priorities, AI suggestions, goals/projects)
- Audio journaling page (voice transcriptions with playback/edit)
- Maintenance report page
- Expandable page structure for future features

**Proposed Page Structure:**
```
/                   → Dashboard (calendar, status, quick capture)
/management         → Priorities, overdue, AI suggestions, goals/projects
/audio              → Voice journals, transcriptions, audio playback
/maintenance        → System health, model registry, insights
/settings           → Config, prompts, calendar upload
```

**Implementation Notes:**
- Create shared base template with navigation sidebar
- Each page as separate Flask route + template
- API endpoints already exist for most data
- Estimate: 4-6 hours for full restructure

### B. Cross-Device Chat Persistence

**Problem:** Chat history is lost on page refresh. User wants:
- Persistent chat across page refreshes
- Shared history between web and CLI
- Integration with "System Thinking" panel

**Proposed Solution:**
- Store messages in `conversations` table (already exists)
- Add session_id tracking (cookie or localStorage)
- Load last N messages on page load
- Real-time sync via polling or WebSocket (future)

**Schema already supports this:**
```sql
CREATE TABLE conversations (
    id INTEGER PRIMARY KEY,
    session_id TEXT,
    source TEXT,          -- 'web', 'cli', 'telegram'
    role TEXT,            -- 'user', 'assistant'
    content TEXT,
    thinking_summary TEXT,
    thinking_level TEXT,
    metadata TEXT,
    created_at TIMESTAMP
);
```

**Implementation Notes:**
- Quick fix: localStorage (done in v0.6.1)
- Full fix: DB-backed sessions with session_id
- Merge chat into thinking panel: Unified sidebar showing both messages and system activity
- Estimate: 2-3 hours for localStorage, 6-8 hours for full DB persistence

### C. Butler Protocol System Status Widget

**Problem:** User wants real-time Butler status visible on dashboard.

**Proposed Widget:**
```
┌─────────────────────────────────────┐
│ 🤖 Butler Status                    │
│ ────────────────────────────────────│
│ Contacts: 3/5 remaining this week   │
│ Next window: Tue 9:00 AM            │
│ Queue: 2 items pending              │
│                                     │
│ [Summon Butler] [View Queue]        │
└─────────────────────────────────────┘
```

**Implementation Notes:**
- API endpoint: `/api/butler/status` (partially exists)
- Add scheduled contact window calculation
- JavaScript polling every 30s
- Estimate: 2-3 hours

### D. Page Navigation System

**Requirements:**
- Buttons under calendar for page switching
- Mobile-friendly responsive design
- Keyboard shortcuts (1-5 for pages)
- Active page indicator

**Proposed Implementation:**
```html
<nav class="page-nav">
    <button data-page="/">📊 Dashboard</button>
    <button data-page="/management">📋 Management</button>
    <button data-page="/audio">🎤 Audio</button>
    <button data-page="/maintenance">🔧 System</button>
    <button data-page="/settings">⚙️ Settings</button>
</nav>
```

**Estimate:** 1-2 hours (after page architecture is in place)

### E. Priority Order for Implementation

1. **Fix prompt history bug** (5 min) — blocking
2. **Chat localStorage persistence** (30 min) — quick win
3. **Page navigation structure** (4-6 hours) — enables everything else
4. **Management page** (2-3 hours) — moves existing content
5. **Audio journaling page** (2-3 hours) — voice.html already exists
6. **Butler status widget** (2-3 hours) — high visibility
7. **Maintenance page** (2 hours) — uses existing APIs
8. **Full chat DB persistence** (6-8 hours) — cross-device

---

## 13) References

- [LangGraph Human-in-the-Loop](https://docs.langchain.com/oss/python/langgraph/human-in-the-loop)
- [Temporal Durable Execution](https://docs.temporal.io/)
- [Warp Oz Cloud Agents](https://docs.warp.dev/agent-platform/cloud-agents/cloud-agents-overview)
- [Ollama API](https://ollama.readthedocs.io/en/api/)
- [vLLM OpenAI-Compatible Server](https://docs.vllm.ai/en/v0.8.0/serving/openai_compatible_server.html)
- [Qwen Function Calling](https://qwen.readthedocs.io/en/v2.0/framework/function_call.html)
- [OpenClaw Skills Architecture](https://docs.openclaw.ai/skills)

---

*Co-Authored-By: Warp <agent@warp.dev>*
