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

## Architecture Direction (v0.9.3)

- **Intake layer**: fast capture (text/voice) with lightweight NLP for task extraction.
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

## Testing

- Not specified yet. Add when a standard test command is defined.

## Build & Deployment

- Target zero-downtime deploys for the web service (graceful reloads).
