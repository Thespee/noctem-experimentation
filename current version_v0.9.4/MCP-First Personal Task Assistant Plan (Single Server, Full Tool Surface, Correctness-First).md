# Problem Statement
Noctem v0.9.3 currently executes task operations through internal workflow handlers where intent and targeting can still mis-resolve in edge cases. The next step is to move to a single MCP server tool architecture that prioritizes mutation correctness and explicit verification over response latency.
## Current State (Code-Verified)
Execution currently routes through `process_chat_message` into `submit_input` and internal handlers, not external tool calls (`noctem/agent/chat_orchestrator.py (236-409)`, `noctem/agent/workflow.py (684-737)`). Single-target selection relies on `_resolve_target_task` and eventually partial `%LIKE%` name matching (`noctem/agent/workflow.py (103-164)`, `noctem/services/task_service.py:60`). Bulk edits resolve scope and mutate all matched tasks without mandatory preview-confirm for non-destructive wide updates (`noctem/agent/workflow.py (445-560)`, `noctem/agent/workflow.py (476-560)`). Legacy skills runtime is removed and dropped at DB init (`README.md (11-24)`, `noctem/web/app.py (1432-1460)`, `noctem/cli.py (141-166)`, `noctem/db.py (526-644)`).
## External Research Basis
MCP tools should be schema-defined, listable, and callable via `tools/list` and `tools/call`, with optional `listChanged` notifications and HITL for risky operations (MCP Tools spec, rev 2025-06-18: [https://modelcontextprotocol\.io/specification/2025\-06\-18/server/tools\)\.](https://modelcontextprotocol.io/specification/2025-06-18/server/tools).) MCP foundation requires capability negotiation and JSON-RPC lifecycle discipline (MCP Overview/Lifecycle: [https://modelcontextprotocol\.io/specification/2025\-11\-25/basic\)\.](https://modelcontextprotocol.io/specification/2025-11-25/basic).) n8n supports MCP access and MCP Server Trigger tool exposure, plus HITL approval for risky tool calls ([https://docs\.n8n\.io/advanced\-ai/accessing\-n8n\-mcp\-server/,](https://docs.n8n.io/advanced-ai/accessing-n8n-mcp-server/,) [https://docs\.n8n\.io/integrations/builtin/core\-nodes/n8n\-nodes\-langchain\.mcptrigger/,](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-langchain.mcptrigger/,) [https://docs\.n8n\.io/advanced\-ai/human\-in\-the\-loop\-tools/\)\.](https://docs.n8n.io/advanced-ai/human-in-the-loop-tools/).) Agent best-practice guidance supports structured tool outputs, validation gates, and explicit approval before irreversible actions (Anthropic/OpenAI guidance).
## Target End-State
A single server `noctem-task-mcp` becomes the only required mutation interface used by the assistant for internal task database operations. The assistant can still use model reasoning, but all state changes flow through typed MCP tools with deterministic validation, dry-run previews, policy gates, explicit approvals, and post-commit verification. n8n remains optional and is limited to external automations/approvals, not core internal task state changes.
## MCP Server Design Principles
* One server process exposes all task-domain tools.
* Strict JSON schemas for both inputs and structured outputs.
* Two-phase mutation for risky operations: `preview_*` then `commit_*`.
* Idempotency keys for commit tools.
* Explicit `affected_task_ids`, `affected_count`, and before/after diffs in results.
* Policy engine gates destructive or high-blast-radius operations.
* Append-only audit events for every preview/commit.
* No success message without verified DB commit readback.
## Full Tool Surface for a Personal Task Database
### Core Task Read
`tasks.get`, `tasks.list`, `tasks.search`, `tasks.list_by_ids`, `tasks.list_today`, `tasks.list_overdue`, `tasks.list_upcoming`, `tasks.list_inbox`, `tasks.list_completed`, `tasks.list_recurring`, `tasks.list_by_project`, `tasks.list_by_goal`, `tasks.list_by_tag`, `tasks.list_by_date_range`, `tasks.list_by_status`, `tasks.list_by_priority`, `tasks.list_blocked`, `tasks.list_stale`.
### Core Task Write (Safe Single-Entity)
`tasks.create`, `tasks.update_fields`, `tasks.rename`, `tasks.set_due`, `tasks.clear_due`, `tasks.set_priority`, `tasks.set_tags`, `tasks.add_tags`, `tasks.remove_tags`, `tasks.assign_project`, `tasks.assign_goal`, `tasks.mark_in_progress`, `tasks.complete`, `tasks.reopen`, `tasks.skip_to_date`, `tasks.duplicate`, `tasks.archive`, `tasks.unarchive`, `tasks.delete`.
### Bulk Operations (Always Previewable)
`tasks.preview_bulk_update`, `tasks.commit_bulk_update`, `tasks.preview_bulk_complete`, `tasks.commit_bulk_complete`, `tasks.preview_bulk_skip`, `tasks.commit_bulk_skip`, `tasks.preview_bulk_delete`, `tasks.commit_bulk_delete`, `tasks.preview_bulk_move_project`, `tasks.commit_bulk_move_project`, `tasks.preview_bulk_retag`, `tasks.commit_bulk_retag`.
### Targeting & Disambiguation
`tasks.resolve_candidates`, `tasks.resolve_scope`, `tasks.explain_resolution`, `tasks.confirm_resolution`, `tasks.reject_resolution`, `tasks.suggest_clarifications`.
### Projects / Goals / Structure
`projects.get`, `projects.list`, `projects.create`, `projects.update`, `projects.archive`, `projects.delete`, `projects.list_tasks`, `goals.get`, `goals.list`, `goals.create`, `goals.update`, `goals.archive`, `goals.delete`, `goals.list_projects`, `sections.get`, `sections.list`, `sections.create`, `sections.update`, `sections.delete`, `tasks.move_section`.
### Metadata & Enrichment
`labels.list`, `labels.create`, `labels.rename`, `labels.delete`, `comments.list_for_task`, `comments.add`, `comments.update`, `comments.delete`, `attachments.add_link`, `attachments.remove`, `custom_fields.list`, `custom_fields.set`, `custom_fields.clear`, `dependencies.add`, `dependencies.remove`, `dependencies.list`, `subtasks.create`, `subtasks.list`, `subtasks.promote`.
### Time, Scheduling, and Review
`calendar.list_blocks`, `calendar.import_ics`, `calendar.clear_imported`, `schedule.suggest_day_plan`, `schedule.place_task`, `schedule.reschedule_conflicts`, `review.daily_summary`, `review.weekly_summary`, `review.inbox_triage`, `review.next_actions`.
### Reliability, Safety, and Ops
`db.begin_transaction`, `db.rollback_transaction`, `db.commit_transaction`, `ops.health`, `ops.ping`, `ops.version`, `ops.get_capabilities`, `ops.get_schema_versions`, `audit.list_events`, `audit.get_event`, `audit.explain_last_mutation`, `undo.preview`, `undo.commit`.
### Import/Export/Interoperability
`interop.import_seed`, `interop.export_seed`, `interop.import_tasks_csv`, `interop.export_tasks_csv`, `interop.import_tasks_json`, `interop.export_tasks_json`, `interop.sync_pull`, `interop.sync_push`, `interop.detect_conflicts`, `interop.resolve_conflicts`.
### User Preference & Policy Tools
`preferences.get`, `preferences.set`, `policy.get`, `policy.set_thresholds`, `policy.set_approval_rules`, `policy.test_decision`.
## Execution Semantics (Correctness Over Latency)
All mutation tools support deep validation before commit: selector normalization, candidate ranking with ambiguity scoring, blast-radius analysis, policy checks, and post-commit readback. If ambiguity remains, server returns a structured clarification interrupt instead of mutating.
## n8n and MCP Expansion Strategy (Design Only)
Keep Noctem as source of truth. n8n is not required for internal Noctem operation and should not be in the critical path for core task CRUD or bulk mutations. Use n8n only as an optional orchestration layer for external automations, notifications, and approval workflows. Noctem MCP preview/commit remains the final mutation authority for task DB state. If using n8n MCP endpoints, expose only approved workflow tools and map them to Noctem preview/commit primitives.
## Implementation Phases
### Phase 1: MCP Server Skeleton + Contracts
Define MCP capabilities, tool registry, schema versioning, correlation IDs, and audit envelope. Implement read-only tools first.
### Phase 2: Resolver Engine
Build deterministic+ranked candidate resolver and scope resolver as standalone components used by all write tools.
### Phase 3: Preview/Commit Mutation Layer
Add preview/commit tool pairs and enforce approval policies for destructive or large-scope operations.
### Phase 4: Assistant Integration
Replace direct `task_service` mutation paths in workflow handlers with MCP tool calls while preserving current API surface.
### Phase 5: Optional n8n Bridge
Add optional n8n workflows for approvals/notifications and external side effects with strict boundary: Noctem MCP commit decides DB state. Internal task operations must continue to work unchanged when n8n is disabled.
### Phase 6: Eval & Hardening
Create eval corpus for targeting precision, blast-radius errors, and false success claims; gate releases on eval pass criteria.
## Acceptance Criteria
* No mutation executes without an explicit target set and validated update spec.
* Bulk updates above policy thresholds require preview + approval.
* All success responses include verified affected IDs/counts from post-commit readback.
* Ambiguous targeting always produces clarification, never silent best-guess commit.
* Assistant, web, CLI, and Telegram all mutate through the same MCP tool contracts.
* Core internal task operations are fully functional with n8n disabled.
