# Warp Configuration
This file captures current project context and implementation-grounded guidance for agents working in this repository.

## Project Snapshot
- **Noctem** is a local-first, all-in-one personal dashboard for tasks, projects, goals, schedule, voice journals, and agentic execution.
- **Cor Unum** is a side project within Noctem for live music ingestion/curation (Vancouver-focused), with separate internal and portal surfaces.

Active runtime code lives in `current version_v0.9.4/noctem/`.

## Core Product Direction
1. Local-first data handling by default.
2. Queue-first, review-gated execution for agent actions.
3. Deterministic internal tool operations (MCP-backed for core task/object work).
4. Auditable changes and explicit mutation history.
5. Unified operator surface for review/task/background controls.

## Runtime Architecture (Current)
- **Web/API control plane**: `web/app.py`
  - Unified control page: `/control`
  - Legacy `/tools` and `/reviews` routes redirect to `/control`
  - Additional key surfaces: `/feedback`, `/graph`, `/calendar`, `/voice`, `/api/chat*`, `/api/tools*`, `/api/reviews*`
- **Queue runtime**: `services/execution_queue.py`, `agent/execution_queue_runtime.py`
- **Workflow + review gating**: `agent/workflow.py`, `agent/review_queue.py`, `agent/plan_tracker.py`
- **MCP contracts/tools**: `mcp/server.py`, `mcp/contracts.py`, `mcp/resolver.py`, `mcp/tools.py`
- **Persistence**: `db.py` (SQLite with broad schema ownership and additive migrations)
- **Memory/retrieval**: `agent/memory_pack.py`, `agent/compaction.py`, `wiki/retrieval.py`, `services/object_context_docs.py`
- **Scheduler**: inactivity-gated passive queue producer in `scheduler/jobs.py`
- **Voice**: transcription/journal pipeline in `voice/processing.py` (no voice-to-task automation path)

## Cor Unum (Current, including v2 lifecycle updates)
Cor Unum uses `cu_*` tables in the shared Noctem SQLite DB and remains manually operator-driven for ingestion runs.

### Surface split
- **Internal dashboard mode** (default app): private-only scope for `/cor-unum*` and `/api/cor-unum*` when `cor_unum_private_only=True`.
- **Portal mode** (`web/portal_app.py`): allowlisted pages/APIs for public/member-facing use.

### Access model and lifecycle
- Session roles: `admin`, `member`, `public`
- Standalone artist creation: `/cor-unum/add-artist`, `POST /api/cor-unum/artists/create`
- Artist → member expansion: `POST /api/cor-unum/artists/<id>/expand-member`
- Username-based member claim: `POST /api/cor-unum/session/assume` (sets `cu_members.claimed_at` on first claim)
- Member event creation requires linked artist and enforces performer linkage server-side

### Moderation and history
- Public suggestion queue: `POST /api/cor-unum/suggestions`
- Suggestion resolution: `POST /api/cor-unum/suggestions/<id>/resolve`
- History endpoints: `/api/cor-unum/history/<entity_type>/<entity_id>`
- Entity detail responses include history and suggestions for reviewability

### Ingestion status
- Source registry includes event, fingerprint, and internal janitor scanners.
- Current event scanner set includes Ticketmaster, RA, AdmitOne, Eventbrite, Denizens, Digital Motion, Orange Tickets, TicketLeader, and TicketWeb.
- Fingerprint scanners include SoundCloud, Spotify, and Instagram.
- Dedupe remains source-scoped; cross-source reconciliation remains review/manual merge based.

## Data, Safety, and Mutation Expectations
- Keep data local unless external integration is explicitly required.
- For ambiguous mutation targets, do not silently guess; require clarification.
- Do not claim mutation success before write/readback confirmation in workflows that support verification.
- Preserve auditable operation history for significant state changes.

## Documentation Precedence
Use this order for current-state truth:
1. Active code in `current version_v0.9.4/noctem/`
2. `docs/Noctem_0.9.4_specifications.pdf`
3. `docs/Cor_Unum_V1_Specification.pdf` (baseline context for Cor Unum v1)
4. `docs/OUTDATED/*` as historical reference only

If older comments/docstrings mention prior versions, prefer actual current code behavior.

## Practical Working Conventions
- Refer to the unified review/background/task surface as the **Control** tab/page (not the old “Tools tab” naming).
- When changing Cor Unum behavior, account for both internal and portal modes.
- Keep README/WARP/docs synchronized with structural or runtime behavior changes to avoid stale guidance.
- Treat generated/source media folders as local-only artifacts: `export/`, `video dev/export/`, and `video dev/videos/` should remain gitignored.
- Do not commit render outputs or raw media from those folders (`.mp4`, `.mov`, frame dumps, manifests, etc.); commit pipeline code/config/docs only.
- If media files are accidentally tracked, untrack them with `git rm -r --cached -- <path>`, commit the `.gitignore` update, then recommit code-only changes.
- If large media blobs land in unpushed branch history, rewrite/squash from a clean base and push only the cleaned code-only commit set.

