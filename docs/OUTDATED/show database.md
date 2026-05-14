System Role: Senior Python Data Engineer & Ingestion Engineer (Noctem-Compatible, Manual Tooling Scope)  
Project Goal: Build a local-first live music ingestion prototype for Vancouver, BC that can be merged into Noctem later with minimal refactoring, especially around database and web UI architecture.  
Current Scope: Entirely manual tooling. No AI/runtime orchestration integration yet.

Project context is rooted in the parent directory: read WARP.md first for architecture rules, workflow constraints, branch/commit expectations, and current priorities, then use docs/ for planning/history details (especially latest plan files and scheduler/database notes).  
Treat current version_v0.9.4/ as the active implementation codebase, and keep work on the active feature branch (never main/master directly) with small, reviewable commits between distinct tasks.  
Do not initialize a new repo; follow existing branch conventions, and only merge to main/master when explicitly requested.

Phase 0: Repository & Scope Guardrails
- Do not initialize a new Git repository.
- Treat this as a merge-target prototype with additive modules and migrations.
- Do not integrate into the core scheduler/runtime yet (future major update will handle that).
- Do not wire this system to the AI/agentic side of the project in this phase.
- Keep all operations manually triggered from web/API controls.

Phase 1: Data Model Design (Noctem-Compatible)
1) Additive typed tables
- `venues`: id, name (unique), address, url, is_verified
- `artists`: id, name (unique), bio_link, last_seen
- `events`: id, title, date, venue_id (FK), description
- `event_performers`: event_id (FK), artist_id (FK), UNIQUE(event_id, artist_id)
- `event_sources`: id, event_id (FK), source_type (IG/Web), source_url, raw_capture_path, captured_at, source_fingerprint

2) Source registry/status table for UI controls
- Add `source_registry` (or equivalent): id, source_key, source_label, source_kind, target, enabled, last_run_at, last_status, last_error, needs_fixing, notes
- This table is the control-plane for manual refresh and scraper health display.

3) Compatibility requirements
- Keep schema additive-only (no destructive changes).
- Design entities to be mappable to object-core conventions later.
- Avoid table name collisions (do not use generic `sources` for scraper provenance).

4) Fallback venue
- Ensure “Out in the Wild” exists by name (get-or-create).
- Do not hardcode primary key IDs.

Phase 2: Ingestion Implementation Plan (Required Before Coding)
The plan must include:
- Playwright (headless) for JS-heavy sources.
- BeautifulSoup for static sources.
- Session-based Instagram ingestion with local config loader and 5–15s randomized delay.
- Deterministic dedupe fingerprint + fuzzy fallback.
- Idempotent re-run behavior.
- Break detection: capture raw content + structured error records.
- Explicit manual-review flow for repeated scraper failures.
- Mapping notes for eventual future scheduler integration (not active now).

Phase 3: Manual Execution Services (No Scheduler Coupling Yet)
Implement manual execution paths only:
- Refresh all sources (manual trigger).
- Refresh individual source by source ID/key (manual trigger).
- Update source status fields (`last_run_at`, `last_status`, `last_error`, `needs_fixing`).
- Record ingestion run summaries in persistent tables/logs.

Here are the 4 sources I want to begin this testing with; intested in upcoming shows at the moment; some of these sites may have non music related things; These are all ticketing websites of some sort, and most likely wont have repeated events:
- https://www.ticketmaster.ca/ (need to select Vancouver for location)
- https://ra.co/events/ca/vancouver
- https://admitone.com/events/vancouver
- https://www.eventbrite.ca/b/canada--vancouver/music/

Do not:
- auto-enqueue jobs
- auto-run on timers
- depend on background idle gating

Phase 4: Web UI — “Cor Unum” Surface
Add a dedicated web subpage:
- Route: `/cor-unum`
- Page title: `Cor Unum`

`/cor-unum` must include:
1) Source control panel
- List all configured sources.
- Show status fields per source (enabled, last run, healthy/broken, needs fixing, last error summary).
- Manual buttons:
  - Refresh source
  - Enable/Disable source
  - Mark issue resolved / clear error
- Optional “Refresh All Sources” action.

2) Scraper health section
- Explicit “Needs Fixing” view/filter.
- Quick diagnostics links to recent failure details/raw capture path.

3) Data access links
- Links to lightweight read-only subpages for basic table views:
  - `/cor-unum/db/events`
  - `/cor-unum/db/artists`
  - `/cor-unum/db/venues`
  - `/cor-unum/db/event-sources`
  - `/cor-unum/db/source-registry`
- These pages only need simple pagination/filter/search (minimal UI acceptable).

4) Scope constraints on UI
- No AI assistant actions.
- No autonomous decisions.
- No integration with agent interrupt/review workflows in this phase.
- Entirely operator-driven manual tool.

Phase 5: API Endpoints (Manual Tooling)
Provide manual-control endpoints (names can vary, behavior required):
- GET source list/status
- POST refresh single source
- POST refresh all sources
- PATCH source enabled/disabled
- PATCH source status clear/resolve
- GET basic table data endpoints for DB subpages

All mutation endpoints should:
- be idempotent where applicable
- return structured status payloads for UI rendering

Phase 6: Testing (Pytest)
Required tests:
1) Ingestion correctness
- No duplicate artists on re-run.
- Same event across multiple sources links to one event + many `event_sources`.
- Unknown venues resolve to “Out in the Wild”.
2) Idempotency
- Reprocessing the same source data is duplicate-safe.
3) Source control/status
- Manual refresh updates source status and timestamps.
- Failure paths mark source as `needs_fixing`.
4) Cor Unum endpoints
- `/cor-unum` renders source list and status fields.
- Individual refresh actions work.
- DB subpages return expected records.
5) Migration safety
- Additive schema applies cleanly to existing DB.

Phase 7: Manual Review Output
At the end of each manual run, generate queryable summary data showing:
- Events ingested
- New artists added
- New venues added
- Duplicates avoided
- Sources healthy vs needs fixing
- Last run result per source

This summary should be visible through Cor Unum (and/or associated APIs), not only a flat file.

Non-Negotiable Constraints
- Local-first, zero-cost preference.
- Manual operation only for this phase.
- No scheduler/runtime/AI integration yet.
- Additive migrations only.
- Merge absorbability over short-term shortcuts.