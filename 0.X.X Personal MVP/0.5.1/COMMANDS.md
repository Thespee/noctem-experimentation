# Noctem 0.5 Command Reference

## Quick Start
```bash
bash start.sh          # QR code display mode (default)
bash start.sh qr       # Same as above
bash start.sh all      # Web + CLI with logs visible
bash start.sh web      # Web dashboard only
bash start.sh cli      # CLI only
bash start.sh bot      # Telegram bot only
```

## Creating Tasks
Just type naturally:
```
buy groceries tomorrow
call mom friday 3pm
finish report by feb 20 !1
email john next week #work /projectname
```

### Task Modifiers
- `!1` - Important (high priority)
- `!2` - Medium importance (default)
- `!3` - Low importance
- `#tag` - Add tags
- `/project` or `+project` - Assign to project

### Date/Time Formats
- `today`, `tomorrow`, `monday`, `next week`
- `feb 20`, `2/20`, `in 3 days`
- `3pm`, `15:00`, `at noon`
- `every day`, `every monday`, `every month`

## Quick Actions

| Command | Description |
|---------|-------------|
| `done 1` | Complete task #1 from priority list |
| `done buy milk` | Complete task by name |
| `skip 2` | Defer task #2 to tomorrow |
| `delete <name>` | Delete task by name |
| `remove <name>` | Same as delete |
| `habit done <name>` | Log habit completion |

## Slash Commands

### Views
| Command | Description |
|---------|-------------|
| `today` or `/today` | Morning briefing |
| `week` or `/week` | Week ahead view |
| `projects` | List all projects |
| `habits` | Show habit stats |
| `goals` | List all goals |
| `web` | Get dashboard link (for phone) |

### Creating Entities
| Command | Description |
|---------|-------------|
| `/project <name>` | Create a new project |
| `/habit <name>` | Create a new habit |
| `/goal <name>` | Create a new goal |

### Interactive Modes
| Command | Description |
|---------|-------------|
| `/prioritize <n>` | Reorder top n tasks by priority |
| `/update <n>` | Fill in missing info for n items |

## Correction (`*`)
Quickly update the last created item:
```
buy groceries
* tomorrow !1         # Add due date and importance
* /shopping           # Assign to project
* #urgent             # Add tag
```

## Interactive Modes

### `/prioritize n`
Enter prioritize mode to reorder your top tasks:
```
/prioritize 5
⚡ Top Priority Tasks (reply with number to bump to top):
1. Task A (due today) [80%]
2. Task B (due tomorrow) [60%]
3. Task C [40%]

> 2                   # Bumps Task B to top priority
> done                # Exit mode
```

### `/update n`
Fill in missing information for tasks and projects:
```
/update 5
📝 Items needing info:
1. 📋 Task A — needs: due_date, importance
2. 📋 Task B — needs: project
3. 📁 Project X — needs: tasks

> 1. tomorrow !1      # Update task 1
> 3. write docs       # Add task to project
> done                # Exit mode
```

Update format for tasks: `<n>. <date> <importance> <project>`
Update format for projects: `<n>. <goal name>` or `<n>. <new task>`

## Priority System

### Importance (!1, !2, !3)
Manually set importance when creating tasks:
- `!1` = 1.0 (Important)
- `!2` = 0.5 (Medium) - default
- `!3` = 0.0 (Low)

### Urgency (Automatic)
Calculated from due date:
- Overdue/Today: 1.0
- Tomorrow: 0.9
- Within 3 days: 0.7
- Within 7 days: 0.5
- Within 14 days: 0.3
- Within 30 days: 0.1
- No due date / 30+ days: 0.0

### Priority Score (Automatic)
```
priority_score = (importance × 0.6) + (urgency × 0.4)
```

The web dashboard shows a 2D graph of all tasks plotted by urgency (x-axis) and importance (y-axis).

## Configuration
```
config                        # Show all config
set telegram_bot_token TOKEN  # Set Telegram bot token
set web_port 8080             # Change web port
```

## Web Dashboard
Access at http://localhost:5000 (auto-refreshes every 10s)

**Features:**
- Priority Map: 2D scatter plot of tasks by urgency/importance
- Week Ahead with calendar events
- Today view with overdue alerts
- Habits tracking with streaks
- Goals & Projects hierarchy
- Someday/Maybe for unassigned tasks

**Mobile Access:**
- Text `web` to bot for a clickable link
- Or scan QR code displayed on startup
- Dashboard is mobile-responsive

## Calendar Integration

Import calendars via ICS at http://localhost:5000/calendar

**Supported sources:**
- Google Calendar (secret ICS URL from settings)
- Apple Calendar (public calendar URL)
- Outlook (ICS publish link)
- Any .ics file upload

**Features:**
- Save calendar URLs for one-click refresh
- Events appear in Week Ahead view
- Events show in morning briefing
- Auto-converts timezones to local time

## Telegram Bot
1. Create bot with @BotFather
2. Set token: `set telegram_bot_token YOUR_TOKEN`
3. Start: `./start.sh bot`
4. Send `/start` to your bot to register

All CLI commands work in Telegram.
