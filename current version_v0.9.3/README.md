# Noctem v0.9.3

Noctem v0.9.3 is a local-first personal operations system focused on task execution through an agent workflow runtime.

## Active v0.9.3 Scope

- Natural-language task capture (web/CLI/Telegram)
- Agent workflow runtime with interrupt + resume support
- Voice journal upload and local transcription processing
- Calendar ICS import and upcoming task views
- Personal wiki ingestion/search (local data + local embeddings stack)

## Removed from Active Runtime

The following legacy runtime layers are intentionally removed from active v0.9.3 execution:

- Butler protocol runtime
- Skills runtime
- Slow-mode processing pipeline
- Prompt-management runtime surfaces
- Maintenance runtime surfaces tied to the removed stack

Reference-only copies of stripped code are stored in:

- `historical-versions/0.9.3-stripped-reference/`

## Workspace Layout

- Active development: `current version_v0.9.3/`
- Frozen live-testing baseline: `current version_v0.9.2/`

## Quick Start (Play Mode)

From repository root, switch into the active v0.9.3 workspace:

```powershell
cd "current version_v0.9.3"
```

Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install dependencies, initialize DB, and run web:

```powershell
pip install -r requirements.txt
python -m noctem.main init
python -m noctem.main web
```

Open:

- `http://localhost:5000`

Optional: run CLI in another terminal (same workspace, same venv):

```powershell
python -m noctem.main cli
```

## First 5 Minutes

Use the web chat (or CLI) and try:

- `buy milk tomorrow`
- `what is due today?`
- `delete buy milk` (you should get an explicit yes/no confirmation interrupt)

API quick checks:

```powershell
$r = Invoke-RestMethod -Method POST -Uri "http://localhost:5000/api/agent/submit" -ContentType "application/json" -Body '{"input":"buy milk tomorrow"}'
$r
Invoke-RestMethod -Method GET -Uri ("http://localhost:5000/api/agent/status/" + $r.workflow_id)
```

## Agent API (v0.9.3)

- `POST /api/agent/submit`
- `GET /api/agent/status/<workflow_id>`
- `POST /api/agent/resume/<workflow_id>`
- `GET /api/agent/interrupts`

`/api/chat` routes through the same agent workflow layer.

## Optional Ollama Intent Classification

Intent routing can use a local Ollama model with heuristic fallback.

Set environment variables before starting Noctem:

```bash
export NOCTEM_AGENT_INTENT_MODEL="qwen2.5:7b-instruct-q4_K_M"
export NOCTEM_OLLAMA_BASE_URL="http://localhost:11434"
```

If `NOCTEM_AGENT_INTENT_MODEL` is not set (or Ollama is unavailable), routing automatically falls back to built-in heuristics.

## Documentation

- `docs/USER_GUIDE_v0.9.2.md` (current v0.9.3 usage guide)
- `docs/CHANGELOG.md`
