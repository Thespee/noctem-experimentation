# Noctem v0.9.4.1

## Problem Statement
v0.9.4 workflows are single-intent, single-operation. Interrupts (clarifications, approvals) block inline in chat, forcing the user to respond in the same conversational turn or risk the resume being misrouted. There is no multi-step plan tracking, no queue-aware background gating, and context docs exist but aren't wired into retrieval. This update closes those gaps.

## Current State (v0.9.4.0)
- **Interrupt flow**: `workflow.py:_interrupt()` creates an interrupt + review_queue row, sets workflow status to `interrupted`. Chat orchestrator's `_maybe_resume_interrupted_workflow()` scans conversation history to find the latest interrupted workflow and only handles `approve`-type interrupts — clarification follow-ups spawn new workflows.
- **Review tab**: `/reviews` redirects to `/tools`. Review items exist in `review_queue` table with reason codes `ambiguity`, `policy_gate`, `verification_failure`, `merge_conflict`, `manual_review`. The tools page shows queue state but review items are not a first-class user surface.
- **Background scheduling**: `IdleCoordinator` in `scheduler/jobs.py` uses a 15-minute `IDLE_TRIGGER` timer based on `_last_user_activity_at`. No awareness of queue state.
- **Context docs**: `object_context_docs` table exists, `retrieval.py` has `search_context_docs()` and `get_context_for_query()` which already orders context docs first, then wiki chunks. However, `memory_pack.py:_context_docs_section()` reads context docs via raw SQL, not through the retrieval/scoring path.
- **Delivery**: `async_delivery.py:publish_queue_result()` publishes to web (conversation record) and Telegram. Currently publishes workflow results, not review notifications.

## Proposed Changes

### Phase 1: Unified Control Tab
**Goal**: All interrupts route to the Control tab instead of blocking chat inline. Chat becomes a notification channel. The existing `/tools` page is renamed to `/control` and expanded to house three sections: **Reviews**, **Tasks**, and **Background**.

**Control tab sections**:
- **Reviews** — pending approvals, clarifications, and plan reviews with resolve/respond UI.
- **Tasks** — current active task list (read from `tasks` table, filtered to non-done status).
- **Background** — scheduler controls, queue state, and delivery telemetry (existing tools content).

**Review categories** stored in `review_queue.reason_code`:
- `approval` — bulk edits, destructive operations (maps from current `policy_gate`)
- `clarification` — ambiguous targets, missing fields (maps from current `ambiguity`)
- `plan_review` — multi-step plan approval (new)
- Keep existing: `verification_failure`, `merge_conflict`, `manual_review`

**Files to change**:
- `review_queue.py`: Add `approval`, `clarification`, `plan_review` to `_REASON_CODES`. Add `category` field to `_review_from_row()` output derived from reason_code.
- `workflow.py:_interrupt()`: Already creates review items — update `_review_reason_code()` to map `approve` → `approval` and clarify-type → `clarification`.
- `workflow.py:_review_reason_code()` (line 64): Return `approval` instead of `policy_gate` for approve-type, `clarification` instead of `ambiguity` for clarify-type.
- `chat_orchestrator.py`: Remove `_maybe_resume_interrupted_workflow()` logic from `process_chat_message()`. When a workflow interrupts, the chat response becomes a notification: "This request needs your review — check the Control tab." with the review_id.
- `execution_queue_runtime.py:_process_review_resume_item()`: Already handles review resumes via queue — this becomes the sole resume path.

**Code to deprecate**:
- `chat_orchestrator.py:_maybe_resume_interrupted_workflow()` — no longer needed; resumes go through Control tab → `enqueue_review_resume()` → queue.
- `chat_orchestrator.py:_latest_interrupted_workflow()` — same reason.
- `chat_orchestrator.py:_looks_like_approval_reply()` — same reason.

**Web route changes** (`web/app.py`):
- Rename `GET /tools` → `GET /control` (keep `/tools` as redirect for bookmarks).
- `GET /reviews` → redirect to `/control` (already redirects to `/tools`, just retarget).
- Expand `control.html` template (renamed from `tools.html`) with three tab-sections: Reviews, Tasks, Background.
- `GET /api/reviews` → JSON list of pending review items grouped by category.
- `GET /api/tasks/active` → JSON list of active tasks for the Tasks section.
- `POST /api/reviews/<review_id>/resolve` → resolve a review item (approve/reject/respond), enqueue review_resume.

### Phase 2: Background Task Gating
**Goal**: Replace the 15-min idle timer with queue-state-aware gating + 2-minute cooldown.

**Gate conditions** (ALL must be true before background work runs):
1. No `queued` items in `execution_queue`
2. No `processing` items in `execution_queue`
3. ≥ 2 minutes since last user message (cooldown)

`review_blocked` items do NOT block background work — if the only remaining items are parked waiting for user review, the system is idle and should use that time for background tasks.

**Files to change**:
- `scheduler/jobs.py:IdleCoordinator._current_budget_seconds()`: Replace the `_idle_trigger` check with the 3-condition gate. Query `execution_queue` for pending/processing counts and `_last_user_activity_at` for the 2-minute cooldown. Budget = time since last activity minus 2-minute cooldown minus safety margin.
- `scheduler/jobs.py`: Remove `IDLE_TRIGGER = timedelta(minutes=15)` constant; replace with `COOLDOWN_SECONDS = 120`.
- `scheduler/jobs.py:IdleCoordinator.status()`: Update status dict to report new gate conditions instead of idle trigger.

### Phase 3: Plan Object Type
**Goal**: Complex requests decompose into tracked sub-steps. Plans are versioned objects that appear on the review tab.

**New object type**: `plan` in the `objects` table.

**Schema addition** (new table):
```sql
CREATE TABLE IF NOT EXISTS plan_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_object_id TEXT NOT NULL REFERENCES objects(object_id),
    step_index INTEGER NOT NULL,
    title TEXT NOT NULL,
    status TEXT DEFAULT 'pending'
        CHECK(status IN ('pending', 'approved', 'executing', 'completed', 'failed', 'skipped')),
    workflow_id INTEGER,
    review_id TEXT,
    payload_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    UNIQUE(plan_object_id, step_index)
);
```

**Files to change**:
- `db.py`: Add `plan_steps` table and index to schema.
- New file `agent/plan_tracker.py`:
    - `create_plan_object(title, steps: list[dict]) -> dict` — creates object + object_version + plan_steps rows + review_queue item with `plan_review` reason.
    - `approve_plan_step(plan_object_id, step_index) -> dict` — marks step approved, enqueues the step's payload as a queue item.
    - `get_plan_status(plan_object_id) -> dict` — returns plan with all steps and their statuses.
    - `fail_plan_step(plan_object_id, step_index, error) -> dict`
    - `complete_plan_step(plan_object_id, step_index) -> dict`
- `workflow.py:submit_input()`: After intent classification, the model decides whether a request needs a plan. The model already returns structured JSON with `requires_action` and `fast_path_input` — extend the schema to include `needs_plan: boolean` and `plan_steps: list[{title, action}]|null`. When the model sees a request that requires multiple MCP tool calls (e.g. "move all overdue tasks to today and then delete the Home project"), it sets `needs_plan=true` and decomposes into steps. If `needs_plan=true`, call `create_plan_object()` instead of executing inline.
- `execution_queue_runtime.py`: Add handler for a new queue item type `plan_step_execution` that executes a single plan step and calls `complete_plan_step()` or `fail_plan_step()`.
- `execution_queue.py`: Add `QUEUE_ITEM_PLAN_STEP = "plan_step_execution"` constant and `enqueue_plan_step()` helper.

**Step ordering**: `enqueue_plan_step()` sets `priority_rank` based on `step_index` (e.g. `50 + step_index`) so the execution queue processes steps sequentially. Only enqueue the next step after the current one completes — `complete_plan_step()` checks for the next pending step and enqueues it.

**Plan failure policy**: When a step fails, the plan halts and a `clarification` review item is created with the error details. The user can then retry the failed step, skip it, or abort the remaining plan from the Control tab.

**Plan lifecycle**:
1. User sends complex request → model returns `needs_plan=true` with step decomposition → plan created with N steps → `plan_review` item on Control tab.
2. User reviews plan on Control tab → approves (all or per-step).
3. First approved step is enqueued as `plan_step_execution`. Each subsequent step is enqueued only after the prior step completes.
4. If a step fails, plan halts and a `clarification` review item is created. User decides: retry, skip, or abort.
5. If a step hits ambiguity, it creates its own `clarification` review item.
6. Plan object version is bumped after each step completion.

### Phase 4: Context Docs → Retrieval Integration
**Goal**: Wire `object_context_docs` as first-class semantic retrieval units.

**Current state**: `retrieval.py:search_context_docs()` does lexical token matching. `get_context_for_query()` already orders context docs first. `memory_pack.py:_context_docs_section()` does raw SQL.

**Changes**:
- `memory_pack.py:_context_docs_section()`: Replace raw SQL with call to `retrieval.search_context_docs()` so scoring/ordering is consistent.
- `retrieval.py:search_context_docs()`: Add optional embedding-based similarity when chromadb collection exists for context docs (future — lexical is acceptable for v0.9.4.1, but wire the interface).

### Phase 5: Deterministic Context Compaction
**Goal**: When conversation messages exceed the 4k chat budget, preserve key decisions and references instead of silently truncating.

**Approach**: Deterministic extraction (no model call). When `_recent_chat_section()` truncates messages, extract structured facts from the dropped turns and store them as a compaction record.

**Extracted facts** (from dropped messages):
- Task IDs mentioned (created, completed, updated)
- Decisions made (approve/reject actions, scope choices)
- Scope anchors (project/goal references, date anchors)
- Active review items referenced

**Storage**: New `conversation_compactions` table:
```sql
CREATE TABLE IF NOT EXISTS conversation_compactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id TEXT NOT NULL,
    dropped_turn_count INTEGER NOT NULL,
    facts_json TEXT NOT NULL,
    oldest_turn_at TIMESTAMP,
    newest_turn_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Files to change**:
- `db.py`: Add `conversation_compactions` table and index.
- `memory_pack.py:_recent_chat_section()`: When truncation occurs, extract facts from dropped lines using deterministic regex/keyword extraction. Store as compaction record. Read all existing compaction records for the thread, merge their facts, and prepend a unified `compaction_summary` to the chat section (e.g. "Earlier in this thread: created tasks #42, #43; approved bulk edit of 5 overdue tasks; scope was 'Home' project").
- New helper `agent/compaction.py`:
    - `extract_facts(lines: list[str]) -> dict` — regex-based extraction of task IDs, decision verbs, scope references, date anchors from conversation lines.
    - `merge_compaction_facts(records: list[dict]) -> dict` — merges facts from multiple compaction records into a single combined fact set (union of task IDs, latest scope anchors, all decisions).
    - `format_compaction_header(facts: dict) -> str` — renders merged facts into a compact one-liner for memory pack injection.
    - `store_compaction(thread_id, dropped_lines, facts) -> dict` — persists to `conversation_compactions`.

**Design constraint**: No model calls. Pure deterministic extraction. If this proves too lossy in practice, a model-assisted path can be added later as a background task.

### Phase 6: Dual-Channel Review Notifications
**Goal**: When a review item is created, notify both Telegram and web dashboard.

**Files to change**:
- New function `async_delivery.py:publish_review_notification(review_item: dict) -> list[dict]`:
    - Formats a short notification: e.g. "Review needed: [clarification] Which task did you mean? — view at /control"
    - Publishes to both web (conversation record) and Telegram using existing `_send_telegram_message_with_retries()`.
    - Records delivery in `delivery_publications` with a new `notification` status or reuses existing statuses.
- `workflow.py:_interrupt()`: After creating review item, call `publish_review_notification()`.
- `execution_queue_runtime.py:_stale_context_requires_review()` path: Also call `publish_review_notification()` when creating stale-context review items.

### Phase 7: Cleanup Remaining v0.9.4.0 Gaps
- `chat_orchestrator.py:_maybe_resume_interrupted_workflow()`: Remove dead code after Phase 1 deploys.
- `chat_orchestrator.py:_looks_like_approval_reply()` and `_latest_interrupted_workflow()`: Remove.
- Remove `web/templates/tools.html` after `control.html` is live; update all internal links and nav references from "Tools" to "Control".
- Verify all three Control tab sections (Reviews, Tasks, Background) render correctly with resolve/respond UI for review items.

## Dependency Ordering
1. **Phase 1** (Unified Control Tab) — no dependencies, foundational for everything else.
2. **Phase 6** (Dual-Channel Notifications) — depends on Phase 1 review items existing.
3. **Phase 2** (Background Gating) — independent of Phase 1 but should land after to avoid conflicts in scheduler.
4. **Phase 4** (Context Docs Retrieval) — fully independent.
5. **Phase 5** (Deterministic Compaction) — fully independent.
6. **Phase 3** (Plan Objects) — depends on Phase 1 (plan_review reason code + review tab UI) and Phase 6 (notifications).
7. **Phase 7** (Cleanup) — depends on all above phases being complete.

## Migration Notes
- `review_queue.reason_code` is a TEXT field with no CHECK constraint in the current schema — adding new reason codes requires no migration, just updating the Python `_REASON_CODES` set. However, existing pending review items with `policy_gate`/`ambiguity` reason codes need a one-time UPDATE to `approval`/`clarification` respectively. Add this migration to Phase 7 cleanup.
- `plan_steps` table is a new additive table — no migration of existing data required.
- `conversation_compactions` table is a new additive table — no migration required.
- The `QUEUE_ITEM_PLAN_STEP` item type is just a new string constant — the `execution_queue.item_type` column has no CHECK constraint.

## What Does NOT Change
- `.t`, `.d`, `skip`, `delete` fast-path commands — these bypass the agentic runtime entirely.
- Voice processing — remains transcription-only.
- Wiki ingestion pipeline.
- Object core / versioning / graph.
- Memory pack budgets (4k/5k/7k/6k/10k).
- Telegram and web as the two chat interfaces.

## Open Issues
Known concerns deferred from v0.9.4.1 scope — revisit based on real-world usage:

1. **Chat approval-reply confusion.** After removing `_maybe_resume_interrupted_workflow()`, users who reply "yes" in chat expecting to approve a pending review will get a new workflow instead. A future improvement could detect approval-like replies when pending reviews exist and redirect the user to the Control tab. Skipped for now since this is a single-user system.
2. **Compaction write on the hot path.** Fact extraction (regex) is fast, but the DB write inside `_recent_chat_section()` adds latency to every message that triggers truncation. If this becomes noticeable, move the DB persist to an async post-response step while keeping extraction synchronous.

## Beyond v0.9.4.1 — Gaps to "Properly Useful"
v0.9.4.1 is infrastructure. It fixes architectural gaps and makes the system more robust, but it's still a reactive task manager with a chat interface. The following gaps remain between this plan and the north star ("I never want to touch a computer again"):

### No proactive behavior
The background scheduler infrastructure is ready, but there are no proactive jobs defined. Nothing looks at the schedule and flags conflicts, notices stale tasks, or suggests what to work on next. v0.9.4.1 builds the runway (queue-aware gating, background scheduler) but doesn't add the planes.

**v0.9.5 candidates**: schedule conflict detection, stale task nudges, daily planning suggestions — all runnable as background jobs through the scheduler and surfaced as review items on the Control tab.

### Limited action surface
The system can manage tasks in its own DB, but can't send emails, create external calendar events, interact with other services, or do anything outside its sqlite boundary. The MCP tool surface is task/project/goal CRUD only.

**v0.9.5 candidates**: External actions via n8n or direct integrations, gated through the review tab's approval flow. Plan objects become the vehicle for multi-step autonomous work involving external systems.

### 7b model ceiling
Plan decomposition, intent classification, and "does this need a plan?" detection all lean on the local model. A 7b model handles simple cases but will struggle with nuanced requests. The plan objects feature may under-deliver in practice until the model is upgraded or prompt engineering is refined.

**Mitigation**: Conservative defaults — only trigger plan decomposition when the model is confident, fall back to single-step execution otherwise. Monitor plan quality and adjust thresholds.

### No learning / adaptation
The system doesn't adapt to user habits. Compaction preserves short-term working state, but there's no long-term preference model ("when Alex says 'soon' he means 'this week'", "Alex always does admin tasks on Monday").

**v0.9.5 candidates**: Preference extraction from conversation history (stored as wiki entries or a dedicated preferences table), injected into memory pack context.

### Limited intake surface
Input is limited to typed commands and voice memos (transcription only). There's no "scan my email and extract action items" or "watch my calendar for changes" type of passive intake.

**v0.9.5 candidates**: Email/RSS/webhook intake connectors that feed into the execution queue, with extracted items appearing as review items for approval before becoming tasks.
