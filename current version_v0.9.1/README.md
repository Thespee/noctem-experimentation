# Noctem v0.9.2

A self-hosted executive assistant system for task management, voice journaling, personal knowledge base, and AI-assisted daily organization.

## Features

- **Natural Language Task Input** - Add tasks via Telegram/CLI/Web with dates, priorities, tags
- **Voice Journals** - Upload audio, automatic transcription, edit transcripts
- **Butler Protocol** - Respectful AI outreach (max 5 contacts/week) with status updates
- **Priority System** - Importance (!1/!2/!3) × urgency (from due dates) = priority score
- **Calendar Integration** - ICS import with all-day event detection (Google, Apple, Outlook)
- **Web Dashboard** - Google Calendar dark mode, responsive sidebar, 2-week dashboard (v0.9.2)
- **Upcoming Tasks** - Rolling 5-day view with inline check-off and task creation (v0.9.2)
- **Projects Board** - Kanban-style columns with inline task creation (v0.9.2)
- **Remote Access** - Secure access via Tailscale VPN with `/access` command
- **Execution Logging** - Full pipeline tracing for debugging and self-improvement
- **Self-Improvement Engine** - Learns from patterns, generates insights, creates learned rules
- **Model Registry** - Dynamic local model discovery (Ollama) with benchmarking
- **Maintenance Scanner** - System health checks and actionable recommendations
- **Skills Infrastructure** - Extensible skill system with triggers, approval workflow, and execution logging
- **Personal Wiki** - Ingest PDFs, markdown, and text files; semantic search with citations (v0.9.0)

## Quick Start

```bash
# 1. Clone/copy project to your machine
# 2. Create virtual environment
python3 -m venv ~/noctem_venv
source ~/noctem_venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Initialize database
python -m noctem.main init

# 5. Set Telegram bot token (get from @BotFather)
python -m noctem.cli
> set telegram_bot_token YOUR_TOKEN_HERE

# 6. Run!
bash start.sh        # QR code mode (default)
bash start.sh all    # Web + CLI with logs
bash start.sh cli    # CLI only
```

## Interfaces

| Interface | Description |
|-----------|-------------|
| **Telegram Bot** | Primary input - add tasks, quick actions, get briefings |
| **Web Dashboard** | Interactive view at `http://localhost:5000` (Voice, Calendar, Prompts, Settings) |
| **CLI** | Configuration, direct commands, `/summon` for corrections |

## Remote Access (Tailscale)

Access Noctem securely from anywhere using Tailscale VPN:

```powershell
# Install Tailscale
winget install Tailscale.Tailscale

# Authenticate (opens browser)
& "C:\Program Files\Tailscale\tailscale.exe" up

# Get your Tailscale IP
& "C:\Program Files\Tailscale\tailscale.exe" ip -4
```

Then access `http://<tailscale-ip>:5000` from any device on your Tailscale network.

**Telegram command:** `/access` sends you the remote URL directly.

## v0.9.0 New Features: Personal Wiki

```bash
# Wiki: Your personal knowledge base with semantic search
# - Drop PDFs, Markdown, TXT files into data/sources/
# - Automatic text extraction and chunking
# - Vector embeddings via Ollama (nomic-embed-text)
# - Answers grounded in YOUR sources with citations

# CLI wiki commands
noctem wiki ingest              # Process all files in data/sources/
noctem wiki ingest file.pdf     # Process a specific file
noctem wiki search "query"      # Semantic search across all sources
noctem wiki sources             # List all indexed sources
noctem wiki status              # Show indexing status

# Query your knowledge base
noctem wiki ask "What did I note about time management?"
# Returns answer with citations: [1] productivity.md, Section: Daily Routine
```

## v0.8.0 Features: Skills Infrastructure

```bash
# Skills: Extensible system for packaged knowledge + procedures
# - SKILL.yaml metadata + instructions.md format
# - RapidFuzz pattern matching for triggers
# - Approval workflow for sensitive skills
# - Full execution logging

# CLI skill commands
noctem skill list               # List all installed skills
noctem skill info <name>        # Show skill details
noctem skill run <name> [input] # Execute a skill
noctem skill enable <name>      # Enable a skill
noctem skill disable <name>     # Disable a skill
noctem skill create <name>      # Scaffold a new skill
noctem skill validate <path>    # Validate SKILL.yaml

# Telegram skill commands
/skill list                     # List enabled skills
/skill info <name>              # Show skill details  
/skill run <name> [input]       # Execute a skill
```

## v0.7.0 Features: Self-Improvement

```bash
# Self-improvement: pattern detection and learning
# - Detects recurring issues (ambiguities, extraction failures, corrections)
# - Generates insights from patterns (max 3 per review)
# - Creates learned rules to improve future classifications
# - Runs automatically (weekly OR 50+ thoughts OR 10+ patterns)

# Summon Butler for corrections/queries
noctem summon "actually that task is for next week"
noctem summon "what's my status?"

# Maintenance commands
noctem maintenance models    # List available LLMs
noctem maintenance scan      # Run health check
noctem maintenance insights  # View recommendations
noctem maintenance preview   # Preview Butler report
```

## Project Structure

```
noctem/
├── main.py           # Entry point
├── cli.py            # Interactive CLI + /summon + skill + wiki commands
├── db.py             # SQLite database (15 tables)
├── models.py         # Data models (21 dataclasses)
├── config.py         # Configuration
├── parser/           # Natural language parsing
├── services/         # Business logic (tasks, suggestions, prompts)
├── skills/           # Skills infrastructure
│   ├── loader.py     # YAML parsing, validation
│   ├── registry.py   # Discovery, CRUD, stats
│   ├── trigger.py    # Pattern matching (RapidFuzz)
│   ├── executor.py   # Execution flow, approval workflow
│   └── service.py    # High-level API
├── wiki/             # Personal knowledge base (v0.9.0)
│   ├── ingestion.py  # File parsing (PDF, MD, TXT)
│   ├── chunking.py   # Text splitting with overlap
│   ├── embeddings.py # Ollama + ChromaDB integration
│   ├── retrieval.py  # Semantic search, citations
│   └── query.py      # Query mode with LLM
├── fast/             # Fast path: classifier, capture, voice cleanup
├── slow/             # Slow path: LLM analysis, model registry
├── butler/           # Butler protocol, summon handler, clarifications
├── logging/          # Execution logging with trace IDs
├── maintenance/      # System scanner, insights, reports
├── telegram/         # Bot handlers
├── scheduler/        # APScheduler jobs
├── web/              # Flask dashboard + templates
└── data/
    ├── noctem.db     # SQLite database
    ├── chroma/       # Vector database (ChromaDB)
    ├── sources/      # Documents for wiki ingestion
    ├── skills/       # User-created skills
    └── voice_journals/  # Audio files
```

## Documentation

- [docs/USER_GUIDE_v0.9.2.md](current%20version_v0.9.1/docs/USER_GUIDE_v0.9.2.md) - v0.9.2 UI overhaul guide
- [docs/USER_GUIDE_v0.9.0.md](docs/USER_GUIDE_v0.9.0.md) - User guide with all features
- [docs/improvements.md](docs/improvements.md) - Design notes, roadmap, learnings
- [docs/Ideals_v0.9.0.md](docs/Ideals_v0.9.0.md) - Aspirational vision and philosophy
- [docs/discussion_v0.7.0.md](docs/discussion_v0.7.0.md) - Critical analysis and technical review
- [SETUP.md](SETUP.md) - Detailed setup guide
- [COMMANDS.md](COMMANDS.md) - All commands reference

## Data Model

```
Goal (long-term outcome)
├── Project (bounded effort)
│   └── Task (atomic action)
└── Project
    └── Task

Habit (recurring tracked behavior)
TimeBlock (calendar events)
```

## License

Personal project - not licensed for distribution.
