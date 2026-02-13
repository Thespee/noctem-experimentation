# Noctem Personal MVP - Setup Summary

**Last Updated**: 2026-02-11
**Version**: 0.5

---

## What's Working

### Core Features ✅
- **Task Management**: Goal → Project → Task hierarchy
  - `/tasks` - List pending tasks
  - `/add <title>` - Add a task
  - `/add <title> in <project>` - Add task to project
  - `/done <id>` - Complete a task
- **Birthday Reminders**: 3-day window alerts from CSV
- **Calendar Integration**: ICS file parsing (standard library only)
- **Morning Reports**: Combined birthdays, tasks, calendar events
- **Message Logging**: All Signal messages logged for future NLP training

### Infrastructure ✅
- SQLite database with tables: goals, projects, user_tasks, message_log
- Global error handling (no crashes)
- Systemd service files ready
- Startup/shutdown scripts

---

## What's NOT Working

### Signal Integration ❌
**Status**: Blocked - receiving messages doesn't work reliably

**What we tried**:
1. Linking signal-cli as secondary device to personal phone
   - Sending FROM server works
   - Receiving on server does NOT work (messages from phone don't arrive)
2. Registering a TextNow VoIP number as primary device
   - Registration completed, verification passed
   - Single checkmarks only (not delivered) - Signal may have blocked the VoIP number

**Root cause**: Signal's linked device model doesn't reliably sync messages you send to yourself. VoIP numbers are often blocked by Signal.

---

## How Signal Integration SHOULD Work

Based on research into OpenClaw (formerly Moltbot):

> "Use a separate Signal number for the bot (recommended)"
> "Don't use your personal Signal number. The bot will take over that account"

**The correct approach**:
1. Get a **dedicated phone number** for the bot (physical SIM preferred, some VoIP works)
2. **Register** that number as the PRIMARY device via signal-cli (not linked)
3. Message that number from your personal phone
4. Server receives messages as the primary device

**Options for phone numbers**:
- Physical SIM in old phone (most reliable)
- Twilio (~$1/month, usually works)
- TextNow/Google Voice (hit or miss - Signal blocks many VoIP)

**signal-cli usage for primary device**:
```bash
# Register (will get SMS verification)
signal-cli -a +1BOTNUMBER register

# If captcha required, go to https://signalcaptchas.org/registration/generate.html
# Solve it, right-click "Open Signal", copy link
signal-cli -a +1BOTNUMBER register --captcha "signalcaptcha://..."

# Verify with SMS code
signal-cli -a +1BOTNUMBER verify 123456

# Set profile
signal-cli -a +1BOTNUMBER updateProfile --given-name "Noctem"

# Run daemon for receiving
signal-cli -a +1BOTNUMBER daemon --http localhost:7583
```

---

## USB Partition Layout

Fresh Ubuntu Server installation:
| Partition | Size | Mount | Purpose |
|-----------|------|-------|---------|
| sda1 | 1GB | /boot/efi | EFI System |
| sda2 | 2GB | /boot | Boot |
| sda3 | 107GB | / | Root (ext4) |
| sda4 | 128GB | /mnt/shared | SHARED - Windows/Android accessible (exFAT) |
| sda5 | 786GB | /mnt/data | DATA - Internal storage (ext4) |

Symlinks: `~/shared` → `/mnt/shared`, `~/data` → `/mnt/data`

---

## Directory Structure

```
~/data/noctem/
├── main.py              # Entry point, CLI, Signal commands
├── daemon.py            # Background task processor, LLM via Ollama
├── signal_receiver.py   # Signal message handling
├── skill_runner.py      # Skill execution with context
├── state.py             # SQLite persistence
├── data/
│   ├── config.json      # Runtime config (create from example)
│   ├── config.example.json
│   └── noctem.db        # SQLite database (auto-created)
├── skills/
│   ├── base.py          # Skill base class + registry
│   ├── task_manager.py  # Task CRUD operations
│   └── ...
├── utils/
│   ├── birthday.py      # Birthday CSV parser
│   ├── calendar.py      # ICS file parser
│   └── morning_report.py
├── scripts/
│   ├── start_noctem.sh
│   ├── stop_noctem.sh
│   ├── setup_signal.sh
│   ├── noctem.service
│   ├── signal-daemon.service
│   └── noctem-morning.timer
├── personal_mvp/
│   ├── QUICKSTART.md    # Getting started guide
│   └── PROGRESS.md      # Development tracker
├── docs/
│   └── SETUP-SUMMARY.md # This file
└── outdated/            # Old docs moved here (not deleted)
```

---

## Quick Start (Once Signal is Working)

```bash
# 1. Pull latest
cd ~/data/noctem
git pull

# 2. Create config
cp data/config.example.json data/config.json
nano data/config.json  # Set signal_phone to bot number

# 3. Start
./scripts/start_noctem.sh

# 4. Test
# Send "/ping" from your phone to bot's Signal number
```

---

## Configuration

`data/config.json`:
```json
{
    "signal_phone": "+1BOTNUMBER",
    "model": "qwen2.5:7b",
    "router_model": "qwen2.5:1.5b",
    "quick_chat_max_length": 80,
    "timezone": "America/Los_Angeles",
    "morning_report_hour": 8,
    "evening_report_hour": 20,
    "birthday_window_days": 3,
    "calendar_path": "/mnt/shared/calendar/calendar.ics",
    "birthdays_path": "/mnt/shared/birthdays.csv"
}
```

---

## External Data Files

Place these on the shared partition for easy access:

| File | Location | Format |
|------|----------|--------|
| Birthdays | `/mnt/shared/birthdays.csv` | `name,date` (date as YYYY-MM-DD or MM-DD) |
| Calendar | `/mnt/shared/calendar/calendar.ics` | Standard ICS format |

Example birthdays.csv:
```csv
name,date
Alice,1990-03-15
Bob,05-22
```

---

## Next Steps

1. **Get Signal working**: Acquire a physical SIM or reliable VoIP number
2. **Test end-to-end**: Phone → Server → Response
3. **Enable systemd services**: Auto-start on boot
4. **Enable morning timer**: 8am daily reports
5. **Continue to Day 2 features**: Natural language tasks, web dashboard

---

## Commands Reference

| Command | Description |
|---------|-------------|
| `/ping` | Test - responds "pong" |
| `/tasks` | List pending tasks |
| `/add <title>` | Add a task |
| `/add <title> in <project>` | Add task to project |
| `/done <id>` | Complete a task |
| `/morning` | Morning briefing |
| `/status` | System status |
| `/help` | Show all commands |

---

## Troubleshooting

### Signal not receiving messages
- If linked device: This approach doesn't work reliably. Use dedicated number as primary.
- If VoIP number: May be blocked by Signal. Try different provider or physical SIM.

### Check processes
```bash
pgrep -f "signal-cli.*daemon"
pgrep -f "python3.*main.py"
```

### Check logs
```bash
tail -50 /tmp/signal-daemon.log
tail -50 /tmp/noctem.log
```

### Test locally without Signal
```bash
python3 -c "from utils.morning_report import generate_morning_report; print(generate_morning_report())"
```

---

## Resources

- **OpenClaw Signal docs**: https://docs.openclaw.ai/channels/signal
- **signal-cli GitHub**: https://github.com/AsamK/signal-cli
- **signal-cli-rest-api**: https://github.com/bbernhard/signal-cli-rest-api (Docker wrapper)

---

*Noctem Personal MVP v0.5*
