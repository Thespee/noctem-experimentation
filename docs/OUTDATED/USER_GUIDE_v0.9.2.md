# Noctem v0.9.4 User Guide
## Agentic Task System + Review Queue + Object Graph + Context-Aware Retrieval

This guide reflects the **current v0.9.4 runtime** in `current version_v0.9.4/`.

## What changed in v0.9.4
- Active architecture is now agentic-first with durable workflow state.
- Fast-path command capture remains for core task mutations (`.t`, `.d`, `skip`, `delete`).
- Voice processing is **transcription-only** (no auto task creation from voice text).
- Calendar ingestion is **ICS-only** (saved URLs and file upload/import).
- Added review surfaces and APIs for blocked/risky workflow actions.
- Added Noctem-native object graph/versioning pages and markdown snapshot export.
- Added one-time migration tooling for v0.9.3 → v0.9.4 object-core import.

## Prerequisites
- Python 3.10+
- `pip`
- Optional: Telegram bot token/chat ID
- Optional: local Whisper model download on first transcription run

## Quick setup
From repo root:

```powershell path=null start=null
cd "current version_v0.9.4"
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Optional (recommended): keep runtime data out of git:

```powershell path=null start=null
$env:NOCTEM_DATA_DIR = "$PWD\..\personal-data\noctem-data"
```

Initialize database/config:

```powershell path=null start=null
python -m noctem.main init
```

## Run modes
Start interfaces/services:

```powershell path=null start=null
python -m noctem.main cli
python -m noctem.main web
python -m noctem.main bot
python -m noctem.main all
```

Notes:
- `web` starts Flask dashboard.
- `bot` requires `telegram_bot_token` configured.
- `all` runs web + scheduler + bot (if token exists).

## CLI usage (v0.9.4)
Interactive CLI:

```powershell path=null start=null
python -m noctem.main cli
```

Core commands:
- `.t <task>` or `/t <task>`: fast-path task create via MCP
- `.d <id|name>` or `done <id|name>`: fast-path complete
- `skip <id|name>`: fast-path defer/skip
- `delete <id|name>`: fast-path delete (preview+commit flow)
- `.p <project name>`: create project
- `.g <goal name>`: create goal
- `projects`: list projects
- `goals`: list goals
- `status`: task/voice summary
- `config`: show settings
- `set <key> <value>`: update setting
- `help`, `quit`

Natural language that is not a fast-path command routes through the agent runtime.

## Web app routes
Main views:
- `/` dashboard
- `/graph` object graph + version surface
- `/calendar/view` weekly calendar view
- `/tasks/upcoming` upcoming + overdue tasks
- `/tasks/projects` project board
- `/voice` voice journals/transcription
- `/reviews` review queue and blocked workflows
- `/settings` runtime settings and calendar import controls
- `/calendar` ICS upload/import management page

## Chat + workflow APIs (for integrations/UI calls)
- `POST /api/chat`
- `GET /api/chat/history`
- `POST /api/agent/submit`
- `GET /api/agent/status/<workflow_id>`
- `POST /api/agent/resume/<workflow_id>`
- `GET /api/agent/interrupts`

Review queue APIs:
- `GET /api/agent/reviews`
- `GET /api/agent/reviews/blocked`
- `POST /api/agent/reviews/<review_id>/approve`
- `POST /api/agent/reviews/<review_id>/reject`
- `POST /api/agent/reviews/<review_id>/resume`

## Graph/versioning APIs
- `GET /api/graph`
- `GET /api/graph/object/<object_id>`
- `GET /api/graph/versions`
- `POST /api/graph/export/markdown`

Graph export writes markdown snapshot files and returns a manifest including output path/file count.

## Calendar (ICS-first)
Supported workflows:
- Upload `.ics` file via `/calendar`
- Save ICS URL, refresh single/all URLs
- Clear imported ICS events

No Google OAuth calendar sync pipeline is used in the active v0.9.4 runtime.

## Voice journals
Voice pipeline behavior:
1. Upload/store audio
2. Transcribe and store text
3. Stop (no downstream task mutation from transcription)

Voice endpoints include upload/list/download/transcription edit/retry/process.

## Migration: v0.9.3 to v0.9.4
Run one-time migration utility from `current version_v0.9.4`:

```powershell path=null start=null
python -m noctem.migration.v093_to_v094 `
  --source-db "..\historical-versions\0.9.3\noctem\data\noctem.db" `
  --target-db ".\noctem\data\noctem.db"
```

Outputs:
- DB backup before migration
- export artifacts (`seed_snapshot.json`, table row dumps)
- `migration_report.json` with verification checks

Default export location:
- `current version_v0.9.4/noctem/data/migration_exports/`

## Testing
Run active suite:

```powershell path=null start=null
python -m pytest tests
```

Current project gate for active v0.9.4 suite:
- `265 passed` (legacy surfaces removed from default collection where applicable)

## Known removed/deprecated surfaces (intentional)
- Legacy Butler runtime surfaces
- Legacy skills UI/runtime APIs in active backend
- Legacy prompt management APIs/UI in active backend
- Rule-based `fast/` module pipeline
- Voice-to-task automation path

## Troubleshooting
If Telegram bot fails:
- Ensure `telegram_bot_token` and `telegram_chat_id` are set:

```powershell path=null start=null
python -m noctem.main cli
set telegram_bot_token "YOUR_TOKEN"
set telegram_chat_id "YOUR_CHAT_ID"
```

If data is writing to the wrong place:
- Check `NOCTEM_DATA_DIR`
- Re-run `python -m noctem.main init`

If workflows appear blocked:
- Open `/reviews`
- Resolve via approve/reject/resume actions

If graph appears empty:
- Confirm you have migrated/created entities
- Use `/api/graph?limit=300` to inspect raw graph payload
