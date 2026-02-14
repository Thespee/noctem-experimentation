# Noctem v0.6.0 User Guide
## The Graceful Butler: Fast Capture, Slow Reflection

---

## Fresh Install (New Computer)

### Prerequisites

**Required:**
- Python 3.10+ (https://python.org)
- pip (comes with Python)

**Optional (for full features):**
- Ollama (https://ollama.ai) - for AI suggestions (slow mode)
- Telegram account - for mobile notifications

### Step 1: Clone & Setup Virtual Environment

```powershell
# Clone the repository
git clone https://github.com/YOUR_USERNAME/noctem.git
cd noctem/"0.X.X Personal MVP"/0.6.0

# Create virtual environment
python -m venv venv

# Activate it (Windows PowerShell)
.\venv\Scripts\Activate.ps1

# Or on Linux/Mac:
# source venv/bin/activate
```

### Step 2: Install Dependencies

```powershell
# Install all required packages
pip install -r requirements.txt

# The requirements include:
# - flask (web dashboard)
# - python-telegram-bot (Telegram integration)
# - icalendar (calendar sync)
# - apscheduler (scheduled tasks)
# - requests (HTTP client)
# - faster-whisper (voice transcription)
```

### Step 3: Download AI Models (Optional but Recommended)

```powershell
# For Whisper voice transcription (tiny model, ~39MB)
.\venv\Scripts\python.exe -c "from noctem.slow.whisper import get_whisper_service; svc = get_whisper_service(); svc.preload(); print('Whisper ready!')"

# For Ollama slow mode suggestions:
# 1. Install Ollama from https://ollama.ai
# 2. Pull the model:
ollama pull qwen2.5:7b-instruct-q4_K_M
```

### Step 4: Initialize Database

```powershell
# Initialize the SQLite database
.\venv\Scripts\python.exe -c "from noctem.db import init_db; init_db()"
```

### Step 5: Run Tests (Verify Installation)

```powershell
# Run all tests to verify everything works
.\venv\Scripts\python.exe -m pytest tests/ -v

# Should see: "285 passed" (or similar)
```

### Step 6: Configure Telegram Bot (Optional)

1. Message @BotFather on Telegram
2. Send `/newbot`, follow prompts to create bot
3. Copy the token (looks like `123456789:ABCdef...`)
4. Configure in Noctem:

```powershell
.\venv\Scripts\python.exe -m noctem cli
# Then type:
set telegram_bot_token YOUR_TOKEN_HERE
```

5. Start Noctem, send `/start` to your bot to link your chat

### Step 7: Run Noctem

```powershell
# Run everything (Telegram bot + web dashboard + scheduler)
.\venv\Scripts\python.exe -m noctem all

# Or run components separately:
.\venv\Scripts\python.exe -m noctem bot    # Just Telegram bot
.\venv\Scripts\python.exe -m noctem web    # Just web dashboard (http://localhost:5000)
.\venv\Scripts\python.exe -m noctem cli    # Interactive CLI
```

### Step 8: Load Your Seed Data (Optional)

Quickly set up goals, projects, and tasks by pasting seed data:

**Via CLI:**
```powershell
.\venv\Scripts\python.exe -m noctem cli
# Then type: seed
# Paste your data and type 'done' on a blank line
```

**Via Telegram:**
Just paste your seed data directly - it auto-detects the format!

**Seed Data Format:**
```
Goals:
-Goal 1
-Goal 2

Projects by goal:
-Goal 1
---- Project A
---- Project B

Tasks by Project:
- Project A
---- Task 1
---- Task 2; due date

Links to calendars:
name:
https://your-calendar-url.ics
```

---

## Features

### Fast Mode (Always Active)
Fast mode catches every thought instantly (<500ms). Just type naturally:

**Adding Tasks:**
- `buy groceries tomorrow`
- `call mom friday 3pm`
- `finish report by feb 20 !1` (high priority)
- `review PR /backend #work` (with project and tag)

**Quick Actions:**
- `done 1` — Complete task #1 from today's list
- `done buy milk` — Complete by name
- `skip 2` — Defer task #2 to tomorrow
- `delete old task` — Remove a task
- `habit done exercise` — Log a habit

**Priority Markers:**
- `!1` = High priority (important)
- `!2` = Medium priority (default)
- `!3` = Low priority

**View Commands:**
- `today` or `/today` — Today's briefing
- `week` or `/week` — Week ahead
- `projects` or `/projects` — Active projects
- `habits` or `/habits` — Habit status

**Status Commands (v0.6.0):**
- `status` or `/status` — System health (butler, slow mode, LLM)
- `suggest` or `/suggest` — View AI suggestions
- `slow` — Slow mode queue status

**Seed Data Commands (v0.6.0):**
- `seed` — Paste natural language seed data (CLI interactive)
- `load <file.json>` — Load seed data from JSON file
- `export [file.json]` — Export current data to JSON
- `/seed` — Show seed data format help (Telegram)

**Voice Journals (v0.6.0):**
- Send a voice message on Telegram → auto-saved & transcribed
- Upload audio at `/voice` on web dashboard
- Transcription happens in background (uses Whisper)

### Butler Protocol (Scheduled Contact)
The butler respects your time with **maximum 5 unprompted contacts per week**:

| Type | Default Schedule | Description |
|------|-----------------|-------------|
| Updates (3/week) | Mon/Wed/Fri 9am | Status summary |
| Clarifications (2/week) | Tue/Thu 9am | Questions about unclear items |

**You can always message the bot** — your messages don't count against the budget.

### Slow Mode (Background Processing)
When you're not actively chatting (5+ minutes idle), slow mode uses a local LLM to:

1. **Analyze tasks**: "What could a computer help with?"
2. **Analyze projects**: "What should you do next?"

Suggestions are stored and shown in updates/dashboard.

**Requirements:**
- Ollama running locally (`ollama serve`)
- Model: `qwen2.5:7b-instruct-q4_K_M`

If Ollama is unavailable, the system continues working (graceful degradation).

---

## Configuration

### Butler Settings
```python
butler_contacts_per_week = 5           # Total weekly budget
butler_update_days = ["monday", "wednesday", "friday"]
butler_update_time = "09:00"
butler_clarification_days = ["tuesday", "thursday"]
butler_clarification_time = "09:00"
```

### Slow Mode Settings
```python
slow_mode_enabled = True
slow_model = "qwen2.5:7b-instruct-q4_K_M"
ollama_host = "http://localhost:11434"
slow_idle_minutes = 5
```

### Changing Settings
Via CLI:
```
python -m noctem cli
/config butler_update_time 08:00
/config butler_update_days ["monday", "friday"]
```

Via web dashboard: http://localhost:5000/settings

---

## Data Storage

All data is stored locally:
- **Database**: `noctem/data/noctem.db` (SQLite)
- **Logs**: `noctem/data/logs/noctem.log`

Nothing leaves your machine unless you configure external integrations.

---

## Troubleshooting

### Bot not responding
1. Check token is set: `python -m noctem cli` then `/settings`
2. Ensure bot is running: `python -m noctem bot`
3. Send `/start` to link your chat

### Slow mode not working
1. Check status: use `status` command or `/status` in Telegram
2. Check Ollama is running: `ollama list`
3. Check model is installed: `ollama pull qwen2.5:7b-instruct-q4_K_M`
4. Check config: `slow_mode_enabled = True`
5. Force process queue: `slow process` in CLI

### Butler not sending updates
1. Check status: use `status` command or `/status` in Telegram
2. Check schedule matches current time
3. Check chat ID is saved (send `/start`)

### Database issues
```powershell
# Reset database (WARNING: deletes all data)
python -c "from noctem.db import reset_db; reset_db()"
python -m noctem init
```

---

## Commands Reference

### Telegram Commands
| Command | Description |
|---------|-------------|
| `/start` | Initialize bot, save chat ID |
| `/today` | Today's briefing |
| `/week` | Week view |
| `/projects` | List projects |
| `/project <name>` | Create project |
| `/habits` | Habit status |
| `/habit <name>` | Create habit |
| `/settings` | View settings |
| `/status` | System health (v0.6.0) |
| `/suggest` | View AI suggestions (v0.6.0) |
| `/seed` | Seed data format help (v0.6.0) |
| `/help` | Full help |
| Voice message | Auto-saved & transcribed (v0.6.0) |

### CLI Commands
| Command | Description |
|---------|-------------|
| `today` | Today's view |
| `status` | System health (v0.6.0) |
| `suggest` | View AI suggestions (v0.6.0) |
| `slow` | Slow mode queue status (v0.6.0) |
| `slow process` | Force process queue (v0.6.0) |
| `seed` | Paste natural language seed data (v0.6.0) |
| `load <file>` | Load seed data from JSON file (v0.6.0) |
| `export [file]` | Export data to JSON (v0.6.0) |
| `/prioritize [n]` | Prioritize top n tasks |
| `/update [n]` | Update n tasks missing info |
| `config` | Show configuration |
| `set <key> <value>` | Set configuration |
| `quit` | Exit CLI |

---

## Architecture Overview

```
┌─────────────────────────────────────────┐
│           Your Messages                 │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│          FAST MODE                      │
│  • Instant parsing (<500ms)             │
│  • Rule-based (no LLM)                  │
│  • Records everything                   │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│        BUTLER PROTOCOL                  │
│  • 5 contacts/week max                  │
│  • Scheduled updates                    │
│  • Clarification questions              │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│          SLOW MODE                      │
│  • Runs when idle                       │
│  • Local LLM analysis                   │
│  • Generates suggestions                │
└─────────────────────────────────────────┘
```

---

## Web Dashboard

Access at http://localhost:5000 when running `noctem all` or `noctem web`.

**Pages:**
- `/` — Main dashboard with tasks, projects, calendar, chat widget
- `/voice` — Voice journals (upload audio, view transcriptions)
- `/calendar` — Calendar URL management
- `/settings` — Configuration

**API Endpoints:**
- `POST /api/chat` — Send chat message (same as Telegram)
- `POST /api/seed/text` — Load natural language seed data
- `POST /api/seed/upload` — Load JSON seed data file
- `GET /api/seed/export` — Export data as JSON
- `POST /api/voice/upload` — Upload audio for transcription
- `GET /api/voice/list` — List voice journals

---

## Version History

- **v0.6.0** — The Graceful Butler
  - Fast mode: instant capture, never lose data
  - Butler protocol: respectful, scheduled contact (5/week max)
  - Slow mode: background LLM analysis when idle
  - New commands: `/status`, `/suggest`, `slow`, `slow process`
  - **Web chat widget**: Same fast mode as Telegram, right on the dashboard
  - Web dashboard: system status bar, AI suggestions section
  - **Voice journals**: Send voice messages on Telegram or upload audio on web
  - **Whisper transcription**: Local transcription with faster-whisper (tiny model)
  - **Seed data loading**: Load goals/projects/tasks from natural language or JSON
  - Startup health check
  - Unified message logging (Telegram, CLI, Web all in same data)
  - 285 passing tests

---

*Last updated: 2026-02-14*
*Co-Authored-By: Warp <agent@warp.dev>*
