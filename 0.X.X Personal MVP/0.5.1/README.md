# Noctem v0.5

A self-hosted executive assistant system for task management, habit tracking, and daily organization.

## Features

- **Natural Language Task Input** - Add tasks via Telegram with dates, priorities, tags
- **Morning Briefings** - Scheduled daily summaries with calendar, priorities, habits
- **Priority System** - Importance (!1/!2/!3) + urgency (from due dates) = priority score
- **Habit Tracking** - Daily/weekly habits with streaks and completion stats
- **Calendar Integration** - ICS import from any calendar (Google, Apple, Outlook)
- **Web Dashboard** - Dark mode, mobile-friendly, auto-refreshing
- **QR Code Display** - Scan to open dashboard on phone

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
| **Web Dashboard** | Read-only view at `http://localhost:5000` |
| **CLI** | Configuration and direct commands |

## Project Structure

```
noctem/
├── main.py           # Entry point
├── cli.py            # Interactive CLI
├── db.py             # SQLite database
├── models.py         # Data models
├── config.py         # Configuration
├── parser/           # Natural language parsing
├── services/         # Business logic (tasks, habits, etc.)
├── telegram/         # Bot handlers
├── scheduler/        # APScheduler jobs
├── web/              # Flask dashboard
└── data/
    ├── noctem.db     # SQLite database
    └── logs/         # Log files
```

## Documentation

- [SETUP.md](SETUP.md) - Detailed setup guide
- [COMMANDS.md](COMMANDS.md) - All commands reference
- [docs/PHASE_CUBIC.md](docs/PHASE_CUBIC.md) - Custom Ubuntu ISO phase
- [docs/ROADMAP_v1.md](docs/ROADMAP_v1.md) - v1.0 AI assistant roadmap

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
