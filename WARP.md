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
- **Tool/Integration layer**: MCP servers for tool access; selective n8n workflows for external apps.
- **Knowledge system**: RAG-based wiki with trust levels and citations.
- **Interfaces**: Telegram, web dashboard, CLI.

## Data & Safety

- Store data locally unless the user explicitly enables external services.
- Require explicit approval for actions that send, commit, or modify external systems.
- Keep auditable logs for automated actions and decisions.

## Documentation Precedence

- `docs/Plan 0.9.3.md` is the source of truth. If documentation conflicts, follow the plan.

## Development Workflow

- Update documentation before major architectural changes.
- Keep the improvements summary concise and current.

## Testing

- Not specified yet. Add when a standard test command is defined.

## Build & Deployment

- Target zero-downtime deploys for the web service (graceful reloads).
