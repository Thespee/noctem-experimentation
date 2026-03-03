# Noctem v0.9.3 User Guide

This guide reflects the active v0.9.3 runtime in `current version_v0.9.3/`.

## Start Playing with v0.9.3

### 1) Launch

```powershell
cd "current version_v0.9.3"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m noctem.main init
python -m noctem.main web
```

Open `http://localhost:5000`.

### 2) First interactions

Try these in web chat (or CLI):

- `buy milk tomorrow`
- `call dentist friday 3pm`
- `what is due today?`

### 3) Interrupt + resume behavior

For a destructive action:

- Send: `delete buy milk`
- You should receive an approval interrupt (`yes`/`no`)
- Respond `yes` to proceed or `no` to cancel

### 4) API smoke test

```powershell
$w = Invoke-RestMethod -Method POST -Uri "http://localhost:5000/api/agent/submit" -ContentType "application/json" -Body '{"input":"buy milk tomorrow"}'
Invoke-RestMethod -Method GET -Uri ("http://localhost:5000/api/agent/status/" + $w.workflow_id)
```

## What v0.9.3 Includes

- NLP-first task capture and editing
- Agent workflow execution with interrupt/resume
- Safe approval flow for destructive task operations (delete)
- Voice journal upload + transcription processing
- Calendar import and planning views
- Personal wiki ingestion and search

## What Was Removed in v0.9.3

These legacy runtime surfaces are no longer active:

- Butler runtime and scheduled outreach stack
- Skills runtime and prompt-management runtime
- Slow-mode processing runtime
- Maintenance runtime tied to removed modules

Reference-only code is archived under:

- `historical-versions/0.9.3-stripped-reference/`

## Daily Task Commands (Natural Language)

Examples:

- `buy milk tomorrow`
- `done buy milk`
- `skip call dentist`
- `delete old draft`

When deletion is requested, the workflow asks for explicit confirmation (`yes`/`no`) before applying it.

## Agent Workflow API

- `POST /api/agent/submit`
  - Body: `{ "input": "buy milk tomorrow" }`
- `GET /api/agent/status/<workflow_id>`
- `POST /api/agent/resume/<workflow_id>`
  - Body: `{ "response": "yes" }`
- `GET /api/agent/interrupts`

`/api/chat` uses the same workflow runtime.

## Optional Ollama Intent Routing

You can enable local-model intent classification:

```bash
export NOCTEM_AGENT_INTENT_MODEL="qwen2.5:7b-instruct-q4_K_M"
export NOCTEM_OLLAMA_BASE_URL="http://localhost:11434"
```

If unset/unavailable, the router uses built-in heuristics automatically.

## Voice Journals

- Upload via `/voice` or voice APIs.
- Files are queued and transcribed locally.
- You can reprocess pending/failed journals using voice endpoints.

## Notes for Migration from v0.9.2

- Continue live testing in `current version_v0.9.2/` unchanged.
- Move to v0.9.3 when ready; agent tables are created automatically on init.
- Legacy runtime tables are dropped in active v0.9.3 initialization.

## Quick Troubleshooting

- `No module named ...`:
  - activate your venv and rerun `pip install -r requirements.txt`
- API call fails to connect:
  - make sure web is running on `http://localhost:5000`
- Ollama unavailable:
  - routing still works via heuristics unless you explicitly set `NOCTEM_AGENT_INTENT_MODEL`
