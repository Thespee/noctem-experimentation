# Noctem v0.6.1

A self-hosted executive assistant system for task management, voice journaling, and AI-assisted daily organization.

## Features

- **Natural Language Task Input** - Add tasks via Telegram/CLI/Web with dates, priorities, tags
- **Voice Journals** - Upload audio, automatic transcription, edit transcripts
- **Butler Protocol** - Respectful AI outreach (max 5 contacts/week) with status updates
- **Priority System** - Importance (!1/!2/!3) × urgency (from due dates) = priority score
- **Calendar Integration** - ICS import from any calendar (Google, Apple, Outlook)
- **Web Dashboard** - Dark mode, mobile-friendly, 3-column layout with thinking feed
- **Execution Logging** - Full pipeline tracing for debugging and self-improvement
- **Model Registry** - Dynamic local model discovery (Ollama) with benchmarking
- **Maintenance Scanner** - System health checks and actionable recommendations

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

## v0.6.1 New Commands

```bash
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
├── cli.py            # Interactive CLI + /summon
├── db.py             # SQLite database (11 tables)
├── models.py         # Data models (15 dataclasses)
├── config.py         # Configuration
├── parser/           # Natural language parsing
├── services/         # Business logic (tasks, suggestions, prompts)
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
    └── voice_journals/  # Audio files
```

## Documentation

- [docs/USER_GUIDE.md](docs/USER_GUIDE.md) - User guide with all features
- [docs/improvements.md](docs/improvements.md) - Design notes, roadmap, learnings
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
