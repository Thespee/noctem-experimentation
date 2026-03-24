# Background Task Scheduler: Configurable Frequency, Persistence & Web UI
## Problem
The idle-budgeted passive scheduler (`scheduler/jobs.py`) has three registered jobs — `voice_transcription`, `context_doc_refresh`, `ics_refresh` — but:
1. Run intervals are hardcoded and too aggressive (1m, 5m, 10m). ICS and voice should run at most once per day; context docs should poll for changes frequently but not force-regenerate on a timer.
2. The staleness query in `object_context_docs.py` has a blanket 30-minute forced-regeneration clause that rewrites every context doc whether or not anything changed.
3. Job run history is in-memory only (`JobRuntimeStats`) — lost on restart, invisible to the user.
4. There is no UI to view, configure, or manually trigger background jobs.
## Current State
* `IdleCoordinator` (jobs.py:64-204) holds a hardcoded `_jobs` list with `PassiveJob` instances.
* Each `PassiveJob` has a `min_interval` that gates re-runs, but these are not persisted or configurable.
* `JobRuntimeStats` tracks runs/failures/durations in memory.
* `list_stale_object_ids` (object_context_docs.py:277-296) uses three OR conditions; the third (`generated_at < now - 30m`) forces regeneration regardless of changes.
* The web app (`web/app.py`) has no scheduler-related routes. The sidebar (`base.html`) has no scheduler link.
* DB migrations live in `db.py:_migrate_db()` using an ALTER TABLE pattern; new tables go in the `SCHEMA` string.
## Changes
### 1. Fix context doc staleness query
File: `noctem/services/object_context_docs.py` — `list_stale_object_ids`
Remove the third OR condition (`datetime(d.generated_at) < datetime('now', ?)`) and the `stale_after_minutes` parameter. The query becomes purely change-driven:
* Condition 1: no context doc exists for the object (`d.object_id IS NULL`)
* Condition 2: object was updated after its context doc was generated (`o.updated_at > d.generated_at`)
The `stale_clause` variable and the parameter binding for it are removed. The function signature drops `stale_after_minutes` but keeps `limit`.
`has_stale_context_docs()` (line 299) and `synthesize_stale_context_docs()` (line 303) need no signature changes — they just call `list_stale_object_ids` which now has a simpler query.
### 2. Add `scheduler_runs` table
File: `noctem/db.py`
Append to the `SCHEMA` string:
```SQL
CREATE TABLE IF NOT EXISTS scheduler_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_name TEXT NOT NULL,
    started_at TEXT NOT NULL,
    duration_seconds REAL,
    ok INTEGER NOT NULL DEFAULT 1,
    summary_json TEXT,
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_scheduler_runs_job ON scheduler_runs(job_name, started_at);
```
No column migrations needed — this is a new table.
### 3. Persisted job config via `config` table
Store a single JSON blob under config key `scheduler_job_config`:
```json
{
  "voice_transcription":  {"interval_minutes": 1440, "enabled": true},
  "context_doc_refresh":  {"interval_minutes": 5,    "enabled": true},
  "ics_refresh":          {"interval_minutes": 1440, "enabled": true}
}
```
Defaults are applied on first read if the key doesn't exist.
### 4. Scheduler changes
File: `noctem/scheduler/jobs.py`
**a) Load persisted config on init.**
`IdleCoordinator.__init__` reads `scheduler_job_config` from the config table. For each job in `_jobs`, if a matching entry exists, override `min_interval` from `interval_minutes` and respect `enabled`. Add an `_enabled` dict tracking which jobs are active.
**b) Record runs to DB.**
After each job execution in `tick()`, insert a row into `scheduler_runs` with `job_name`, `started_at`, `duration_seconds`, `ok`, `summary_json` (the return value of `job.run()` serialised), and `error`.
**c) Expose config update helper.**
Add `update_job_config(job_name, interval_minutes=None, enabled=None)` that writes back to the config table and hot-reloads the affected job's `min_interval` / enabled state.
**d) Expose run history helper.**
Add `get_job_run_history(job_name=None, limit=20)` that queries `scheduler_runs`.
**e) Manual trigger.**
Add `async run_job_now(job_name)` that bypasses interval/budget checks and runs a named job immediately, recording the result.
### 5. Web API endpoints
File: `noctem/web/app.py`
* `GET /api/scheduler/status` — returns current coordinator status (idle time, per-job stats, config, last N runs from DB).
* `POST /api/scheduler/config` — accepts `{"job_name": "...", "interval_minutes": N, "enabled": bool}`, calls `update_job_config`.
* `POST /api/scheduler/run` — accepts `{"job_name": "..."}`, calls `run_job_now`.
### 6. Web page and sidebar
Files: `noctem/web/templates/scheduler.html` (new), `noctem/web/templates/base.html`
New sidebar entry under **System**: `⏱️ Background`  →  `/scheduler`
The page shows:
* **Per-job card** for each of the three jobs:
    * Name and description
    * Enabled/disabled toggle
    * Interval dropdown (5m / 30m / 1h / 6h / 12h / Daily)
    * Last run: timestamp + duration + success/fail badge
    * Last result summary (e.g. "Processed 2 journals" or "3 created, 1 updated")
    * "Run Now" button
* **Recent runs table** (last 20 across all jobs) from `scheduler_runs`, showing job name, time, duration, status, summary.
Styling follows the existing dark theme from `base.html`.
Each job card also has a note explaining that background execution happens automatically during idle time, with the "Run Now" button available for immediate manual execution.
### 7. Slim down Settings calendar section
File: `noctem/web/templates/settings.html`
The current Calendar Import section (lines 180-247) contains both feed management and sync/refresh controls. Since sync is now managed by the background scheduler:
* **Keep:** saved calendar list (names + URLs), add-new-calendar form (URL + file upload), remove buttons
* **Remove:** "Refresh All" button, per-calendar "Refresh" buttons, "Clear All Imported Events" button, upcoming events preview
* **Add:** a note with link: "Calendar syncing is handled automatically. See [Background Tasks](/scheduler) to configure frequency or run manually."
This keeps Settings focused on configuration (which feeds exist) while the scheduler page owns execution.
## File Change Summary
* `noctem/services/object_context_docs.py` — remove forced-staleness condition from SQL
* `noctem/db.py` — add `scheduler_runs` table to SCHEMA
* `noctem/scheduler/jobs.py` — load persisted config, write run history to DB, add config/trigger helpers
* `noctem/web/app.py` — three new API routes under `/api/scheduler/`, plus `/scheduler` page route
* `noctem/web/templates/scheduler.html` — new page
* `noctem/web/templates/base.html` — add sidebar link
* `noctem/web/templates/settings.html` — slim calendar section, add link to scheduler page
## Defaults
* `ics_refresh`: 1440 min (daily), enabled
* `voice_transcription`: 1440 min (daily), enabled
* `context_doc_refresh`: 5 min, enabled (cheap change-detection poll; only regenerates docs whose objects actually changed)
