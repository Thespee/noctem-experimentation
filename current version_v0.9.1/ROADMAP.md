# Roadmap
This is the high-level roadmap for Noctem. For the detailed working plan, see `docs/0.9.X Plan.md`.

## 0.9.x (current) — Wiki + reliability + UX
Primary goal: make the existing system *reliable* and *pleasant* day-to-day.
- Finish/ship the Wiki CLI surface area (ingest/search/ask/status/verify)
- Web dashboard: split the monolith into a small set of pages and add navigation
- Cross-device state where it matters (chat persistence, session continuity)
- Tighten diagnostics: health, queue status, model registry visibility

## 0.9.1+ — “Digital Aristotle” learning loop
Primary goal: use your wiki as a grounded study system.
- Better grounded Q&A (confidence + “I don’t know” when sources are thin)
- Socratic mode (questioning + evaluation against sources)
- Spaced repetition (SM-2) built from wiki chunks

## 1.0 — Durable automation + external actions
Primary goal: safe, resumable, human-in-the-loop automations.
- Durable workflows (Temporal or equivalent)
- Integrations (calendar write-back, email drafting/sending) with explicit approval checkpoints
- Maintenance protocol v2 (weekly improvement reports)

## 2.0 — Public-facing release
Primary goal: usability + packaging.
- Installer / Docker / security hardening
- Documentation cleanup and examples
- Optional mobile companion for capture + notifications
