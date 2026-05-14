System Role: Senior Full-Stack Engineer (Noctem-Compatible, Manual Tooling Scope)  
Project Goal: Build a singleton Feedback Capture surface and pipeline that stores one canonical feedback document, supports fast insertion, and exports raw text for downstream model parsing/fix workflows.  
Current Scope: Manual capture and export only. No AI-side integration in this phase.

Project context is rooted in the parent directory: read WARP.md first for architecture rules, workflow constraints, branch/commit expectations, and current priorities, then use docs/ for planning/history details (especially latest plan files and scheduler/database notes).  
Treat current version_v0.9.4/ as the active implementation codebase, and keep work on the active feature branch (never main/master directly) with small, reviewable commits between distinct tasks.  
Do not initialize a new repo; follow existing branch conventions, and only merge to main/master when explicitly requested.

Phase 0: Scope & Guardrails
•  Do not initialize a new repository.
•  Implement as additive changes only.
•  Do not integrate with agentic workflow/interrupt/review runtime yet.
•  Keep the feature fully manual and deterministic.
•  The system must maintain exactly one feedback document in persistent storage.

Phase 1: Data Model (Singleton in Object Core)
Implement one singleton feedback doc represented in object-core-compatible form.

Requirements:
1) Singleton object
•  Object type: feedback_doc (or equivalent).
•  Exactly one active record must exist system-wide.
•  If missing, create lazily on first access.

2) Content model
•  Store full raw text as a single large document body.
•  Delimiter between feedback items is literal &&& on its own line usage by operator convention.
•  Do not auto-rewrite user text beyond safe normalization (preserve operator content).

3) Ordering rule for new fast-command inserts
•  New .f ... submissions must be inserted at the top of the document.
•  Existing content remains below.
•  Preserve delimiter boundaries when prepending (insert with clear &&& separation).

Phase 2: Fast Command .f
Add a fast command:
•  Syntax: .f [feedback text is entire remainder of message]
•  Behavior:
◦  Take everything after .f  as raw feedback content.
◦  Prepend this content to the singleton feedback doc.
◦  Insert separator &&& between entries if needed.