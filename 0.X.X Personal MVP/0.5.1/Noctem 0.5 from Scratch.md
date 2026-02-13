# Noctem 0.5 - Executive Assistant System

## Overview
A self-hosted executive assistant that helps prioritize work, manages tasks/projects/goals, and delivers daily briefings. No AI in v0.5 - purely organizational infrastructure.

**Interfaces:**
- **Input**: Telegram bot (conversational commands)
- **Output**: Telegram messages (morning briefing, confirmations) + read-only web dashboard
- **Data**: Google Calendar (one-way sync IN only)

---

## Core Data Model

### Hierarchy: Goals → Projects → Tasks

```
Goal (long-term outcome)
├── Project (bounded effort toward goal)
│   ├── Task (atomic action)
│   ├── Task
│   └── Task
└── Project
    └── Task

Habit (separate entity, recurring tracked behavior)
```

### Entities

**Goal**
- id, name, type (bigger_goal | daily_goal), description, created_at, archived

**Project**
- id, name, goal_id (FK), status (backburner | in_progress | done | canceled)
- summary, start_date, end_date, completion_pct, created_at

**Task**
- id, name, project_id (FK, nullable for standalone tasks)
- status (not_started | in_progress | done | canceled)
- due_date, due_time (nullable), priority (1-4, 1=highest)
- tags (JSON array), recurrence_rule (nullable), created_at

**Habit**
- id, name, goal_id (FK, nullable)
- frequency (daily | weekly | custom), target_count (e.g., 3x per week)
- time_preference (morning | afternoon | evening | anytime)
- duration_minutes, active, created_at

**HabitLog**
- id, habit_id (FK), completed_at, notes

**TimeBlock**
- id, title, start_time, end_time, source (manual | gcal), gcal_event_id (nullable)
- block_type (meeting | focus | personal | other)

**SystemConfig**
- key, value (JSON) - stores user preferences like morning_message_time, timezone

---

## Features

### 1. Natural Language Task Input (Todoist-style, no AI)

Parse messages like:
- `buy groceries tomorrow`
- `call mom friday 3pm`
- `pay rent every 1st`
- `finish report by feb 20 !1` (priority 1)
- `email john next week #work`

**Parser rules (regex-based):**
```
Relative dates: today, tomorrow, next [day], in [N] days
Absolute dates: feb 15, 2026-02-15, 15/02
Times: 3pm, 15:00, at noon
Recurrence: every [day], every [N] days, every 1st, daily, weekly
Priority: !1, !2, !3, !4 or p1, p2, p3, p4
Tags: #word
Project: /project_name or +project_name
```

Fallback: If no date parsed, task has no due date (inbox style).

### 2. Morning Briefing Message

Sent via Telegram at user-configured time. Contains:

```
☀️ Good morning! Here's your Thursday, Feb 13:

📅 CALENDAR (3 events)
• 09:00-10:00 Team standup
• 14:00-15:30 Client call
• 18:00 Dinner with Sarah

⚡ TOP PRIORITIES
1. [!1] Finish project proposal (due today)
2. [!2] Review PR for backend (due today)  
3. [!1] Submit tax documents (due tomorrow)

🔄 HABITS TODAY
• Morning exercise (2/3 this week)
• Read 30 min (done yesterday ✓)

Reply: "done 1" to complete, "skip 2" to defer
```

### 3. Quick Actions via Telegram

**Task management:**
- `done 1` or `done [task_name_fragment]` - mark complete
- `skip 1` - defer to tomorrow
- `!1 [task]` - set priority
- `delete [task]` - remove task

**Viewing:**
- `today` - show today's tasks and calendar
- `week` - show this week
- `projects` - list active projects
- `habits` - show habit status

**Adding:**
- Any text without command prefix → parsed as new task
- `/project [name]` - create project
- `/habit [name] [frequency]` - create habit

### 4. Google Calendar Sync (One-way IN)

- Poll GCal API every 15 minutes (configurable)
- Import events as TimeBlocks with source=gcal
- Do NOT write back to GCal
- Store gcal_event_id to detect updates/deletions
- Respect user's timezone from config

### 5. Habit Tracking

Separate from tasks. Tracks:
- Completion rate (X/Y this week)
- Streaks (consecutive days/weeks)
- Best time of day (from completion patterns)

Morning message includes habits due today. User can:
- `habit done [name]` - log completion
- `habits` - see all habits with stats

### 6. Read-Only Web Dashboard

Simple, Wikipedia-style minimal design. Single HTML page served by Python.

**Sections:**
- Today's calendar + tasks
- Goals (expandable to show projects → tasks)
- Habits with weekly completion grid
- Upcoming (next 7 days)

No authentication needed (local network only, or send fresh URL via Telegram each time).

Tech: Flask/FastAPI, Jinja2 templates, minimal CSS, no JS framework.

---

## Architecture

```
noctem/
├── main.py              # Entry point, starts all services
├── config.py            # Load/save config from DB
├── db.py                # SQLite connection, schema init
├── models.py            # Dataclasses for Goal, Project, Task, Habit, etc.
│
├── telegram/
│   ├── bot.py           # python-telegram-bot setup
│   ├── handlers.py      # Message handlers, command routing
│   └── formatter.py     # Format messages (morning briefing, etc.)
│
├── parser/
│   ├── natural_date.py  # Regex-based date/time extraction
│   ├── task_parser.py   # Parse full task string → Task object
│   └── command.py       # Detect and route commands
│
├── services/
│   ├── task_service.py  # CRUD for tasks
│   ├── project_service.py
│   ├── goal_service.py
│   ├── habit_service.py # Habit CRUD + logging + stats
│   ├── calendar_sync.py # GCal polling
│   └── briefing.py      # Generate morning briefing content
│
├── scheduler/
│   └── jobs.py          # APScheduler jobs: morning message, gcal sync
│
├── web/
│   ├── app.py           # Flask/FastAPI app
│   ├── templates/
│   │   └── dashboard.html
│   └── static/
│       └── style.css
│
├── data/
│   └── noctem.db        # SQLite database
│
└── tests/
    ├── test_parser.py
    ├── test_services.py
    └── test_briefing.py
```

### Key Patterns

1. **Service layer**: All business logic in `services/`. Handlers just parse input and call services.

2. **Processor-ready**: Each message type routes through handlers that can be swapped for AI-powered versions in v1.0.

3. **Extensive logging**: Every action logged to DB (task created, completed, habit logged, etc.) for future analysis.

4. **Single-user**: No auth complexity. Config assumes one user.

5. **Robust queue** (for v1.0 prep): Background jobs use a simple queue pattern with error handling and retry.

---

## Database Schema

```sql
-- Goals
CREATE TABLE goals (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT CHECK(type IN ('bigger_goal', 'daily_goal')),
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    archived INTEGER DEFAULT 0
);

-- Projects
CREATE TABLE projects (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    goal_id INTEGER REFERENCES goals(id),
    status TEXT DEFAULT 'in_progress' 
        CHECK(status IN ('backburner', 'in_progress', 'done', 'canceled')),
    summary TEXT,
    start_date DATE,
    end_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tasks
CREATE TABLE tasks (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    project_id INTEGER REFERENCES projects(id),
    status TEXT DEFAULT 'not_started'
        CHECK(status IN ('not_started', 'in_progress', 'done', 'canceled')),
    due_date DATE,
    due_time TIME,
    priority INTEGER CHECK(priority BETWEEN 1 AND 4),
    tags TEXT, -- JSON array
    recurrence_rule TEXT, -- e.g., "every monday", "every 1st"
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

-- Habits
CREATE TABLE habits (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    goal_id INTEGER REFERENCES goals(id),
    frequency TEXT DEFAULT 'daily' 
        CHECK(frequency IN ('daily', 'weekly', 'custom')),
    target_count INTEGER DEFAULT 1, -- times per frequency period
    custom_days TEXT, -- JSON array for custom, e.g., ["mon","wed","fri"]
    time_preference TEXT DEFAULT 'anytime'
        CHECK(time_preference IN ('morning', 'afternoon', 'evening', 'anytime')),
    duration_minutes INTEGER,
    active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Habit completions
CREATE TABLE habit_logs (
    id INTEGER PRIMARY KEY,
    habit_id INTEGER REFERENCES habits(id) NOT NULL,
    completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notes TEXT
);

-- Calendar time blocks
CREATE TABLE time_blocks (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NOT NULL,
    source TEXT DEFAULT 'manual' CHECK(source IN ('manual', 'gcal')),
    gcal_event_id TEXT,
    block_type TEXT DEFAULT 'other'
        CHECK(block_type IN ('meeting', 'focus', 'personal', 'other')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- System config (key-value)
CREATE TABLE config (
    key TEXT PRIMARY KEY,
    value TEXT -- JSON
);

-- Action log (for extensive local records)
CREATE TABLE action_log (
    id INTEGER PRIMARY KEY,
    action_type TEXT NOT NULL, -- task_created, task_completed, habit_logged, etc.
    entity_type TEXT, -- task, habit, project, etc.
    entity_id INTEGER,
    details TEXT, -- JSON with action-specific data
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## Natural Language Parser Specification

### Date Patterns

```python
PATTERNS = {
    # Relative
    'today': lambda: date.today(),
    'tomorrow': lambda: date.today() + timedelta(days=1),
    'yesterday': lambda: date.today() - timedelta(days=1),
    r'in (\d+) days?': lambda m: date.today() + timedelta(days=int(m.group(1))),
    r'next (monday|tuesday|...)': lambda m: next_weekday(m.group(1)),
    r'this (monday|tuesday|...)': lambda m: this_weekday(m.group(1)),
    
    # Absolute
    r'(\d{4})-(\d{2})-(\d{2})': lambda m: date(int(m[1]), int(m[2]), int(m[3])),
    r'(\d{1,2})/(\d{1,2})': lambda m: date(current_year(), int(m[2]), int(m[1])),  # DD/MM
    r'(jan|feb|mar|...) (\d{1,2})': lambda m: date(current_year(), month_num(m[1]), int(m[2])),
    r'(\d{1,2}) (jan|feb|mar|...)': lambda m: date(current_year(), month_num(m[2]), int(m[1])),
}
```

### Time Patterns

```python
TIME_PATTERNS = {
    r'(\d{1,2}):(\d{2})': lambda m: time(int(m[1]), int(m[2])),
    r'(\d{1,2})(am|pm)': lambda m: time(int(m[1]) + (12 if m[2]=='pm' and int(m[1])!=12 else 0), 0),
    r'at noon': lambda: time(12, 0),
    r'at midnight': lambda: time(0, 0),
}
```

### Recurrence Patterns

```python
RECURRENCE_PATTERNS = {
    'daily': 'FREQ=DAILY',
    'weekly': 'FREQ=WEEKLY', 
    r'every (monday|tuesday|...)': 'FREQ=WEEKLY;BYDAY=MO',  # map day
    r'every (\d+) days?': 'FREQ=DAILY;INTERVAL=N',
    r'every (\d+)(st|nd|rd|th)': 'FREQ=MONTHLY;BYMONTHDAY=N',  # every 1st
    r'every month': 'FREQ=MONTHLY',
}
```

### Priority & Tags

```python
PRIORITY_PATTERN = r'[!p]([1-4])'  # !1, p1, etc.
TAG_PATTERN = r'#(\w+)'  # #work, #personal
PROJECT_PATTERN = r'[/+](\w+)'  # /myproject, +myproject
```

### Parser Flow

1. Extract and remove priority, tags, project markers
2. Extract and remove time
3. Extract and remove recurrence
4. Extract and remove date
5. Remaining text = task name (trimmed)

---

## Telegram Bot Commands

### Implicit (any text → new task)
User sends: `buy milk tomorrow`
Bot responds: `✓ Added: "buy milk" due Thu Feb 13`

### Explicit Commands

| Command | Action |
|---------|--------|
| `/start` | Welcome message, setup instructions |
| `/today` | Today's briefing |
| `/week` | This week's view |
| `/projects` | List active projects |
| `/project <name>` | Create new project |
| `/habits` | Habit status |
| `/habit <name> <freq>` | Create habit (e.g., `/habit exercise daily`) |
| `/goals` | List goals |
| `/help` | Command reference |
| `/settings` | Show/edit config (morning time, timezone) |

### Quick Replies
- `done 1` or `done buy milk` → mark task complete
- `skip 1` → defer to tomorrow
- `delete buy milk` → remove task
- `habit done exercise` → log habit completion

---

## Implementation Order

### Phase 1: Core Infrastructure
1. Database schema + migrations (`db.py`)
2. Models + basic services (CRUD for all entities)
3. Config management
4. Action logging

### Phase 2: Natural Language Parser
1. Date parser with tests
2. Time parser
3. Recurrence parser
4. Full task parser integration
5. Extensive test coverage for edge cases

### Phase 3: Telegram Bot
1. Bot setup, basic `/start` and `/help`
2. Message handler → task parser → create task
3. Quick action handlers (done, skip, delete)
4. View commands (today, week, projects, habits)
5. Habit logging commands

### Phase 4: Scheduling
1. APScheduler setup
2. Morning briefing job
3. Google Calendar sync job

### Phase 5: Google Calendar Integration
1. GCal API auth (OAuth, store refresh token)
2. Event polling + upsert to time_blocks
3. Handle event updates/deletions

### Phase 6: Web Dashboard
1. Flask app with single route
2. Dashboard template (Goals → Projects → Tasks tree)
3. Today view, habits grid
4. Minimal CSS (Wikipedia-inspired)

### Phase 7: Polish
1. Error handling throughout
2. Timezone handling
3. Edge cases in parser
4. Import existing data from Notion CSVs (one-time script)

---

## Dependencies

```
python-telegram-bot>=20.0   # Telegram bot
APScheduler>=3.10           # Job scheduling
google-api-python-client    # GCal API
google-auth-oauthlib        # GCal OAuth
flask>=3.0                  # Web dashboard (or fastapi+uvicorn)
jinja2                      # Templates
python-dateutil             # Date parsing helpers
```

All stored in `requirements.txt`. No other external dependencies.

---

## Configuration Defaults

```json
{
    "telegram_bot_token": "YOUR_TOKEN",
    "telegram_chat_id": "YOUR_CHAT_ID",
    "timezone": "America/Vancouver",
    "morning_message_time": "07:00",
    "gcal_sync_interval_minutes": 15,
    "gcal_calendar_ids": ["primary"],
    "web_port": 5000,
    "web_host": "0.0.0.0"
}
```

---

## Future (v1.0 Considerations)

- **AI task prioritization**: Replace manual priority with LLM-suggested ordering
- **AI task breakdown**: "Find a job" → generates subtasks automatically
- **AI calendar optimization**: Suggest best times for tasks based on patterns
- **Email integration**: AI reads emails, creates tasks
- **Custom ISO (Cubic)**: Package as installable Ubuntu derivative for easy deployment

---

## Testing Strategy

1. **Parser tests**: Comprehensive date/time/recurrence parsing
2. **Service tests**: CRUD operations, business logic
3. **Integration tests**: Telegram message → task created → appears in DB
4. **Manual testing**: Daily use as primary task manager

Run: `python -m pytest tests/`

---

## Deployment

For v0.5, simple systemd service:

```ini
[Unit]
Description=Noctem Executive Assistant
After=network.target

[Service]
Type=simple
User=alex
WorkingDirectory=/path/to/noctem
ExecStart=/usr/bin/python3 main.py
Restart=always

[Install]
WantedBy=multi-user.target
```

GCal OAuth requires initial browser-based auth, then stores refresh token.

---

## Success Criteria

v0.5 is complete when:
- [ ] Can add tasks via Telegram with natural language dates
- [ ] Morning briefing arrives at configured time with calendar + priorities
- [ ] Habits tracked with weekly completion stats
- [ ] Google Calendar events appear in briefing
- [ ] Web dashboard shows full Goals → Projects → Tasks hierarchy
- [ ] All actions logged for audit trail
- [ ] System runs reliably as background service
