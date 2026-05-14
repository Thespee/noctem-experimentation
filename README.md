# Noctem
Noctem is a local-first, all-in-one personal dashboard for managing tasks, projects, goals, calendar data, voice journals, and agentic workflows in one place.

Cor Unum is an integrated side project inside Noctem focused on live music ingestion/curation (Vancouver-centric), with both internal and portal-facing surfaces.

## Current state (source of truth)
- Active runtime code: `current version_v0.9.4/`
- Core package: `current version_v0.9.4/noctem/`
- Historical snapshots: `historical-versions/`
- Current docs/spec assets: `docs/`
- Archived docs: `docs/OUTDATED/`

When docs and legacy comments disagree with behavior, code in `current version_v0.9.4/noctem/` is authoritative.

## Repository layout
- `current version_v0.9.4/noctem/` — active runtime modules (`agent`, `web`, `mcp`, `db`, `scheduler`, `ingestion`, `voice`, `wiki`, `services`, etc.)
- `current version_v0.9.4/noctem/tests/` — package-level tests
- `tests/` — broader root-level tests and shared fixtures
- `docs/` — current specifications and project notes
- `personal-data/` — local runtime/private data (gitignored)

## Runtime data location
Noctem stores runtime data in SQLite and related local folders.

- Default data dir: `current version_v0.9.4/noctem/data/`
- Recommended: keep runtime data outside tracked code with `NOCTEM_DATA_DIR`

Example (Linux/macOS):
```bash
export NOCTEM_DATA_DIR="$PWD/personal-data/noctem-data"
```

## Quick start
```bash
cd "current version_v0.9.4"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# optional but recommended: keep runtime data outside tracked code
export NOCTEM_DATA_DIR="$PWD/../personal-data/noctem-data"

python -m noctem init
python -m noctem web
```

## Run modes
From `current version_v0.9.4/`:

- `python -m noctem web` — internal dashboard (`/`, `/control`, `/calendar`, `/feedback`, `/graph`, `/cor-unum*`)
- `python -m noctem portal` — Cor Unum portal app (public/member-facing scope)
- `python -m noctem cli` — terminal interface
- `python -m noctem bot` — Telegram bot
- `python -m noctem all` — combined web + bot runtime

Default ports come from config (`web_port` = 5000, `portal_port` = 5001).

## Core runtime architecture (v0.9.4)
- Queue-first, review-gated execution flow for agent work
- Unified control surface at `/control` (legacy `/tools` and `/reviews` routes redirect)
- MCP tool layer for deterministic task/project/goal operations
- Durable object/version/event tracking in SQLite
- Retrieval + context compaction for memory packing
- Inactivity-gated background scheduler for passive jobs
- Voice subsystem focused on transcription/journal persistence

## Cor Unum status (includes v2 updates)
Cor Unum remains a side project inside the main app and uses `cu_*` tables in the shared SQLite DB.

Implemented current behavior includes:
- Internal vs portal split:
  - Internal dashboard via main app (`create_app(...)`, private-only Cor Unum scope by default)
  - Portal app via `web/portal_app.py` with explicit page/API allowlist
- Role model and lifecycle:
  - Admin, member, public session modes
  - Standalone artist creation (`/cor-unum/add-artist`, `POST /api/cor-unum/artists/create`)
  - Artist → member expansion (`POST /api/cor-unum/artists/<id>/expand-member`)
  - Username-based member session claim (`POST /api/cor-unum/session/assume`) with `claimed_at`
- Member mutation rules:
  - Member event creation requires linked artist and enforces performer linkage server-side
- Moderation/audit:
  - Public suggestion queue (`/api/cor-unum/suggestions*`) with accept/reject
  - Entity history endpoints (`/api/cor-unum/history/<entity>/<id>`)
- Ingestion:
  - Source registry includes event, fingerprint, and internal janitor scanners
  - Runs are operator-triggered via Cor Unum APIs/UI (no autonomous scheduler orchestration for Cor Unum ingestion)

## Key docs
- `docs/Noctem_0.9.4_specifications.pdf` — current runtime capability baseline
- `docs/Cor_Unum_V1_Specification.pdf` — Cor Unum v1 baseline/context
- `docs/TECHNICAL_SUMMARY_current_version_v0.9.4.txt` — code-grounded technical snapshot
- `WARP.md` — project working context/rules for agent sessions

## Notes on legacy labels
Some comments/docstrings still contain older version labels (for example 0.5/0.6-era text). Prefer current behavior in code over historical labels.
