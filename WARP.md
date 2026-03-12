# Warp Configuration

This file contains project-specific rules and preferences for Oz agents working in this repository.

## Project Overview

Noctem is a private, local-first agentic assistant for managing tasks, projects, personal knowledge, and automation without sending data to the cloud by default.

## North Star

“I never want to touch a computer again. This system should do it all for me while I am off engaging with life.”

## Guiding Principles

1. **Zero-touch operation** — every feature moves toward automation.
2. **Human-in-the-loop for risky actions** — never send/commit/write externally without approval.
3. **Local-first, privacy-first** — cloud only with explicit consent.
4. **Put down / pick up** — work must be pausable, persisted, and resumable.
5. **Respect attention** — batch questions, avoid spam.
6. **Grounded knowledge** — answers cite sources and prefer trusted local data.

## Architecture Direction (v0.9.4)

- **Intake layer**: command parsing (dot/slash prefix commands) + voice transcription. The `fast/` rule-based capture pipeline is removed.
- **Router/Planner**: classifies intent and creates queued work items.
- **Workflow/Agent runtime**: executes plans, pauses for approvals, resumes later.
- **Tool/Integration layer**: single Noctem MCP server is the required internal task tool surface; n8n is optional for external app workflows only.
- **Knowledge system**: RAG-based wiki with trust levels and citations.
- **Interfaces**: Telegram, web dashboard, CLI.

## Task Mutation Reliability Rules (Persistent)

- Core internal task DB operations should be implemented through Noctem MCP tool contracts.
- n8n is not required for internal operation and must not be in the critical path for core task CRUD/bulk mutations.
- Never perform silent best-guess mutations when targeting is ambiguous; require clarification.
- Use preview/commit semantics for risky operations, especially destructive or large-scope updates.
- Do not report mutation success until post-commit readback verifies affected task IDs/counts.
- Keep auditable preview/commit events with correlation IDs across execution paths.

## Chat Workflow Reliability Lessons (Mar 2026)

- A chat approval prompt can be issued from an interrupted workflow, but if follow-up replies are routed through normal `submit_input` only, they can create a new workflow instead of resuming the pending one.
- This caused a real failure mode: bulk preview showed “approve yes/no,” user replied `yes`, but the original bulk workflow remained interrupted and commit never ran.
- Model-only assistant replies (`requires_action=false`) can sound like confirmed mutations even when no workflow/mutation executed; success text must not be treated as proof of commit.
- Completion intent heuristics must cover natural phrasing variants; `completed ...` should route the same as `complete ...`/`done ...`.
- Keep resume behavior thread-grounded: detect the latest interrupted workflow in the active thread and resume it for approval-style yes/no responses.
- Restrict auto-resume scope to approval interrupts plus explicit approval lexicon to avoid hijacking unrelated conversational turns.
- Maintain regression tests for these exact failure paths:
  - chat approval follow-up resumes the same bulk workflow and commits
  - `completed ...` utterances execute completion workflow instead of add-task fallback

## Data & Safety

- Store data locally unless the user explicitly enables external services.
- Require explicit approval for actions that send, commit, or modify external systems.
- Keep auditable logs for automated actions and decisions.

## Documentation Precedence

- `docs/Plan 0.9.4.md` is the source of truth. If documentation conflicts, follow the plan.

## Development Workflow

- Update documentation before major architectural changes.
- Keep the improvements summary concise and current.
- Always start implementation work on a new development branch (never directly on `master`).
- Make a git commit between distinct implementation tasks so each step is reviewable and reversible.
- After significant changes, commit and push to the active branch unless explicitly told not to.
- Never merge into `main`/`master` unless the user explicitly requests it.

## Session Learnings (Mar 2026)

- Calendar import via saved `.ics` URLs and Google OAuth sync were separate pipelines; one can work while the other logs as unconfigured.
- Runtime direction is now **ICS-only calendar ingestion** (manual/saved-feed refresh), with the Google OAuth calendar sync pipeline removed.
- Runtime direction is now **voice-processing-only scheduler jobs**; scheduled morning briefing and scheduled calendar sync are removed.
- Avoid reintroducing `gcal_*` scheduled sync settings or morning briefing scheduler settings unless explicitly requested by the user.
- Voice processing should **never** create tasks or take actions from transcribed text. Voice is purely for recording thoughts. Do not reintroduce voice-to-task pipelines.
- Do not reintroduce `today`/`week` as template-based CLI commands. The user prefers asking the agent naturally for schedule information.
- The `fast/` module (rule-based classifier + capture pipeline) is permanently removed. Do not recreate rule-based thought classification; the agentic runtime handles intent.

## Session Learnings (Mar 2026, v0.9.4 Planning Additions)

- Chat interruption behavior should support **appended follow-up instructions**, not only yes/no approvals.
  - Prefer structured resume payloads like `decision`, `instructions`, and optional scope edits.
  - Keep resume bound to the same interrupted workflow/thread; do not spawn parallel workflows for approval follow-ups.
- Prioritize adopting a **LangGraph-style HITL runtime pattern**:
  - durable interrupt/resume semantics
  - explicit state transitions
  - bounded memory pack assembly
- Treat mutation history as **durable, append-only, Git-like commits** in the database:
  - immutable commits with parent links and refs
  - rollback via inverse commits, not destructive rewrite
  - include task and calendar-event mutations in this history model
- Replace in-memory mutation audit stores with persistent DB-backed history for reliability across restarts.
- Add **entity context docs** (task/project/goal/doc/calendar) generated asynchronously:
  - include original creation context, verified change history, related entities, and provenance
  - use them as high-signal retrieval units to improve assistant accuracy and RAG grounding
  - run generation in slow/background paths, not hot chat path
- Evolve passive background work to an **inactivity-budgeted adaptive scheduler**:
  - initial idle trigger target: 15 minutes
  - choose jobs based on expected runtime relative to idle budget
  - run voice processing only when there are pending/new voice memos
- Keep human approval and verification guarantees intact while extending autonomy:
  - preview/commit on risky operations
  - post-commit verification before success messaging

## Session Learnings (Mar 2026, Pre-Dev Cleanup & Routing Decisions)

- **Voice processing is transcription-only.** Voice memos are transcribed and stored in `voice_journals`; no downstream actions (task creation, classification, etc.) are taken from transcribed text. Voice is for recording thoughts, not interacting with the agent.
- **Command parser (`parser/command.py`) is permanent infrastructure.** Dot/slash commands (`.t`, `.d`, `skip`, `delete`, `.p`, `.g`) are the fast path for simple DB modifications without invoking the LLM. `parser/task_parser.py` handles extraction of task names, due dates, etc.
- **Fast path routing**: `.t`, `.d`, `skip`, `delete` bypass the agentic runtime entirely and go directly to MCP. `.p`/`.g` go to direct service calls. Everything else goes through `process_chat_message()` (agentic runtime).
- **Removed command types**: `PRIORITIZE`, `UPDATE`, `CORRECT`, `SESSION`, `SUMMON`, `TODAY`, `WEEK`, `WIKI` are all removed from the parser. `today`/`week` views are replaced by asking the agent naturally. Wiki search is handled by the agent autonomously.
- **`fast/` module is fully removed** (`capture.py`, `classifier.py`, `voice_cleanup.py`). The rule-based thought classifier and voice-to-task pipeline are dead code after voice becomes transcription-only and CLI commands route through the agentic runtime.
- **Dead DB tables removed**: `action_log`, `message_log`, `thoughts` — these tables are not migrated to v0.9.4.
- **Pre-agentic interactive modules removed**: `session.py`, `handlers/interactive.py` — fully superseded by the agentic workflow runtime.
- **Disconnected services removed**: `services/suggestion_service.py`, `services/briefing.py` — no remaining callers.
- **Scheduler gutted**: The fixed 1-minute APScheduler interval in `scheduler/jobs.py` is replaced wholesale by the inactivity-budgeted coordinator.
- **Directory convention**: Previous version dirs renamed from `current version_v0.9.X` to `v0.9.X`; active development always in `current version_v0.9.4`.
- **Data migration scope**: Only `conversations`, `voice_journals`, and `time_blocks` are migrated from v0.9.3. Goals/projects/tasks/wiki are exported via `seed/loader.py`.
- **In-memory MCP stores** (`_PREVIEW_STORE`, `_COMMIT_RESULT_STORE`, `_AUDIT_EVENTS`, `_UNDO_PREVIEW_STORE`) are replaced by DB-backed records in Phase 1 (not removed in Phase 0).

## Session Learnings (Mar 2026, v0.9.4 Decisions)

- Obsidian mode: **Noctem-native web graph** with optional markdown export.
- Version control: **internal commit graph only** (no system Git bridge in v0.9.4).
- Memory pack budget (32k total): 4k recent chats, 5k recent commits, 7k top context docs, 6k wiki; reserve 10k for tools/output.
- Multi-device offline editing is **future scope** (not in v0.9.4) and will require an explicit sync/conflict strategy.
- Future multi-device outline: per-device append-only event logs, periodic event exchange, conflict detection with manual review, and merge commits as new heads.
- CRDTs are a **future optional** merge strategy for text-heavy objects (notes/docs) if true concurrent offline edits are required.

## Codebase Grounding for v0.9.4 Execution (Mar 2026)

- Core schema and migrations live in `current version_v0.9.3/noctem/db.py`; additive migrations are required for object/commit history rollout.
- MCP preview/commit logic is currently in `current version_v0.9.3/noctem/mcp/tools.py` with in-memory preview/audit/undo stores that must be replaced by DB-backed records.
- Interrupt/resume behavior is centered in `current version_v0.9.3/noctem/agent/workflow.py`, `current version_v0.9.3/noctem/agent/interrupts.py`, and `current version_v0.9.3/noctem/agent/chat_orchestrator.py`.
- Passive scheduling is currently voice-only in `current version_v0.9.3/noctem/scheduler/jobs.py`; ICS refresh hooks already exist in `current version_v0.9.3/noctem/services/ics_import.py`.
- Wiki retrieval/query grounding lives in `current version_v0.9.3/noctem/wiki/retrieval.py` and `current version_v0.9.3/noctem/wiki/query.py`.
- Web and Telegram task actions already route through MCP paths in `current version_v0.9.3/noctem/web/app.py` and `current version_v0.9.3/noctem/telegram/handlers.py`.

## Active vs Deferred Scope (v0.9.4)

- **Active v0.9.4 execution scope**: object core + durable history, context docs + bounded memory packs, inactivity-budgeted scheduler, retrieval integration, review/error surfaces, and Noctem-native graph interface with internal commit history.
- **Deferred (future features)**: Universal Inbox + external connectors and other TBD deferred concepts.
- Keep chat interaction modes unchanged for this version: web dashboard and Telegram UI.
- External side effects remain approval-gated; never report mutation success before post-commit verification/readback.

## Testing

- Not specified yet. Add when a standard test command is defined.

## Build & Deployment

- Target zero-downtime deploys for the web service (graceful reloads).

