# Noctem CHANGELOG

Last updated: 2026-03-03

## v0.9.3 (Agentic Runtime Transition)

### Completed

- Added v0.9.3 agent workflow APIs:
  - `POST /api/agent/submit`
  - `GET /api/agent/status/<workflow_id>`
  - `POST /api/agent/resume/<workflow_id>`
  - `GET /api/agent/interrupts`
- Routed `/api/chat` through agent workflow execution.
- Added workflow audit + interrupt records in DB:
  - `agent_workflows`, `agent_interrupts`, `agent_actions`
- Preserved voice transcription path in v0.9.3 runtime.
- Stripped legacy runtime modules from active backend and archived reference copies.
- Added safe delete approval flow (explicit yes/no before deletion).
- Added optional local Ollama intent-classification path with automatic heuristic fallback.
- Added migration cleanup that removes legacy runtime tables from active v0.9.3 databases.

### Validation Status

- `tests/test_v093_agentic_agent.py`: 8 passed
- Core targeted suites (`v093_agentic_agent`, `v093_quick_fixes`, `v092_ui_overhaul`): 47 passed
- Full `tests/` run in `current version_v0.9.3`: 308 passed
- `python -m compileall -q noctem`: passed

## v0.9.3 Phase 1 (Quick Fixes)

- NLP reprocessing for inline task edits (explicit-field updates only)
- `tmrw` alias support
- Upcoming `Unassigned` section
- Recurring ICS expansion improvements
- UI consistency and legacy route redirect fixes
