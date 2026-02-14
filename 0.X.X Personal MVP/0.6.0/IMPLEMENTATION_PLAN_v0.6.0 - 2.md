# Noctem v0.6.0 Implementation Plan (Draft 2)
## The Graceful Butler: Fast Capture, Slow Reflection

**Date**: 2026-02-14  
**Status**: Draft 2 - Ready for Phase 0  
**Deadline**: End of February (personal MVP), March (friends version)

---

## Vision

> Noctem 0.6.0 is a butler who gracefully catches every thought you toss their way, filing it with quiet dignity before you've finished speaking. Once a week, they present a brief note: *"Here's what deserves your attention, and here's what I can handle while you're away."*

---

## Core Principles

1. **Fast mode is the product.** If catching thoughts isn't valuable alone, slow mode won't save it.
2. **Graceful and dignified.** Max 5 unprompted contacts per week. Never pushy, never nagging.
3. **Record everything.** Data captured now enables v0.7's self-improvement.
4. **Start from zero.** Target user has no habits, no routine. Build together.
5. **Local-first, private, secure.** All data stays on user's machine.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      NOCTEM v0.6.0                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    FAST MODE                             │   │
│  │  "The Postal Clerk"                                      │   │
│  │                                                          │   │
│  │  • Instant response to all user input                    │   │
│  │  • Rule-based parsing (no LLM)                           │   │
│  │  • State changes happen immediately                      │   │
│  │  • Templates for acknowledgments                         │   │
│  │  • Records ALL interactions for future analysis          │   │
│  │                                                          │   │
│  │  Triggers: Any user message                              │   │
│  │  Latency: <500ms                                         │   │
│  │  Availability: Always                                    │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    SLOW MODE                             │   │
│  │  "The Archivist"                                         │   │
│  │                                                          │   │
│  │  • Runs when user is NOT actively chatting               │   │
│  │  • Uses local LLM (Ollama) for 2 specific tasks:         │   │
│  │    1. Per Task: "What could a computer help with?"       │   │
│  │    2. Per Project: "What should person do next?"         │   │
│  │  • Generates weekly digest content                       │   │
│  │  • Records suggestions for v0.7 improvement              │   │
│  │                                                          │   │
│  │  Triggers: Background loop, idle detection               │   │
│  │  Latency: 5-30 seconds per item                          │   │
│  │  Availability: When LLM available (graceful degradation) │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                 BUTLER PROTOCOL                          │   │
│  │  "Graceful Contact Management"                           │   │
│  │                                                          │   │
│  │  • Max 5 unprompted contacts per calendar week           │   │
│  │  • User sets schedule during setup                       │   │
│  │  • 3 update messages + 2 clarification requests          │   │
│  │  • Responds FAST when user initiates contact             │   │
│  │  • Never interrupts, only scheduled touchpoints          │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## What v0.6.0 Does NOT Include

To maintain focus, these are explicitly **out of scope**:

- Voice input/output
- Multi-channel (WhatsApp, Discord, etc.) — Telegram only
- Skill accumulation / self-improvement (v0.7)
- Slow mode reviewing fast mode's actions (v0.7)
- Implementation intentions with when/where/how (v0.7)
- Calendar integration improvements
- Advanced clarification flows

---

## Phase 0: Codebase Review & Test Setup ✅ COMPLETE

**Status**: Audit complete. Ready for implementation.

### 0.1 Codebase Audit Results

**Directory Structure:**
```
noctem/
├── main.py              # Entry point (bot/web/cli/all/init modes)
├── db.py                # SQLite schema + get_db() context manager
├── models.py            # Dataclasses: Task, Project, Goal, Habit, etc.
├── config.py            # Key-value config in DB with caching
├── session.py           # Session state for interactive modes
├── cli.py               # CLI interface
├── handlers/
│   ├── interactive.py   # Prioritize/Update modes, correction handler
├── parser/
│   ├── command.py       # CommandType enum + parse_command()
│   ├── task_parser.py   # parse_task() - NLP for task creation
│   ├── natural_date.py  # Date/time parsing
├── services/
│   ├── task_service.py
│   ├── project_service.py
│   ├── habit_service.py
│   ├── goal_service.py
│   ├── briefing.py      # generate_morning_briefing(), generate_today_view()
│   ├── message_logger.py # MessageLog class - ALREADY EXISTS!
├── telegram/
│   ├── bot.py           # create_bot(), registers handlers
│   ├── handlers.py      # cmd_* handlers + handle_message()
│   ├── formatter.py
├── scheduler/
│   ├── jobs.py          # APScheduler setup, morning briefing job
├── web/
│   ├── app.py           # Flask dashboard
└── tests/
    └── test_parser.py, test_services.py
```

**Data Flow:**
```
Telegram Message
    ↓
handle_message() [telegram/handlers.py:253]
    ↓
parse_command() → CommandType
    ↓ (if NEW_TASK)
parse_task() → ParsedTask
    ↓
task_service.create_task()
    ↓
SQLite (tasks table)
```

### 0.2 Gap Analysis Results

**✅ Already Exists (Reuse Directly):**
| Component | Location | Notes |
|-----------|----------|-------|
| message_log table | db.py:105 | Records raw_message, parsed_command, action_taken, result |
| MessageLog class | services/message_logger.py | Context manager for logging |
| Scheduler | scheduler/jobs.py | APScheduler with CronTrigger |
| Parser | parser/task_parser.py | Handles NLP task creation |
| Config system | config.py | Key-value with caching |
| Test infrastructure | tests/ | pytest with temp DB isolation |

**🔧 Needs Modification:**
| Component | Change Needed |
|-----------|---------------|
| db.py SCHEMA | Add butler_contacts, slow_work_queue tables; add columns to tasks/projects |
| config.py DEFAULTS | Add butler_contacts_per_week, update_days, slow_model |
| telegram/handlers.py | Wrap ALL handlers with MessageLog recording |
| scheduler/jobs.py | Add butler contact jobs |
| main.py | Add slow mode loop startup |

**🆕 Build From Scratch:**
| Component | Purpose |
|-----------|----------|
| butler/protocol.py | Contact budget management |
| butler/updates.py | Generate update messages |
| slow/loop.py | Background processing thread |
| slow/task_analyzer.py | "What could computer help with?" |
| slow/project_analyzer.py | "What should person do next?" |
| slow/degradation.py | Ollama health checks |

### 0.3 What YOU Must Do Before Development

**Step 1: Copy v0.5.0 to v0.6.0**
```powershell
# From: 0.X.X Personal MVP
Copy-Item -Path ".\0.5.0 minimum minimum working\*" -Destination ".\0.6.0\" -Recurse -Force
```

**Step 2: Create/Activate Python Environment**
```powershell
# Create venv in 0.6.0 directory
cd "0.6.0"
python -m venv venv
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r noctem/requirements.txt
pip install httpx pytest pytest-asyncio
```

**Step 3: Verify Tests Pass**
```powershell
# From 0.6.0 directory with venv active
python -m pytest tests/ -v
```

**Step 4: Create Test Telegram Bot** (if not already done)
1. Message @BotFather on Telegram
2. Create new bot, get token
3. Store token somewhere safe (we'll configure during Phase 1)

**Step 5: Install Ollama** (optional for now - graceful degradation)
```powershell
# Download from https://ollama.ai
# Then pull the model:
ollama pull qwen2.5:7b-instruct-q4_K_M
```

### 0.4 Development Best Practices

**1. Test-Driven Development**
- Write tests BEFORE implementing features
- Run tests after each significant change
- Keep test DB isolated (already set up in tests/)

**2. Incremental Commits**
- Commit after each working feature
- Use descriptive commit messages
- Tag milestones (e.g., `v0.6.0-phase1`)

**3. Development Flow**
```
1. Make change
2. Run: python -m pytest tests/ -v
3. Test manually: python -m noctem cli
4. If Telegram needed: python -m noctem bot
5. Commit if tests pass
```

**4. Debugging**
- Logs go to: noctem/data/logs/noctem.log
- SQLite browser can inspect: noctem/data/noctem.db
- Use `--quiet` flag to reduce console noise

### Phase 0 Checklist (For You)

- [ ] Copy 0.5.0 → 0.6.0
- [ ] Create Python venv in 0.6.0
- [ ] Install dependencies
- [ ] Run `python -m pytest tests/ -v` — should pass
- [ ] Run `python -m noctem init` — should create DB
- [ ] (Optional) Set up Telegram bot token
- [ ] (Optional) Install Ollama

**Once complete, tell me and I'll proceed with Phase 1.**

---

## Phase 1: Fast Mode Foundation

**Goal**: Every user message is captured, parsed, and stored instantly.

### 1.1 Database Schema Updates

**File**: `noctem/db.py` — Add to SCHEMA string (after line 123):

```sql
-- Butler contact tracking (for 5 contacts/week limit)
CREATE TABLE IF NOT EXISTS butler_contacts (
    id INTEGER PRIMARY KEY,
    contact_type TEXT,           -- 'update', 'clarification'
    message_content TEXT,
    week_number INTEGER,         -- ISO week number
    year INTEGER,
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Slow work queue (for background LLM processing)
CREATE TABLE IF NOT EXISTS slow_work_queue (
    id INTEGER PRIMARY KEY,
    work_type TEXT,              -- 'task_computer_help', 'project_next_action'
    target_id INTEGER,           -- task_id or project_id
    depends_on_id INTEGER,       -- Another queue item that must complete first
    status TEXT DEFAULT 'pending', -- pending, processing, completed, failed
    result TEXT,                 -- The generated suggestion
    queued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_butler_contacts_week ON butler_contacts(year, week_number);
CREATE INDEX IF NOT EXISTS idx_slow_work_status ON slow_work_queue(status, queued_at);
```

**File**: `noctem/db.py` — Add columns to tasks table (ALTER after init):
```sql
-- Run these as migrations after table exists:
ALTER TABLE tasks ADD COLUMN computer_help_suggestion TEXT;
ALTER TABLE tasks ADD COLUMN suggestion_generated_at TIMESTAMP;

ALTER TABLE projects ADD COLUMN next_action_suggestion TEXT;
ALTER TABLE projects ADD COLUMN suggestion_generated_at TIMESTAMP;
```

**Note**: The existing `message_log` table (db.py:105-114) already captures what we need for interaction recording. We'll use it directly instead of creating a new table.

### 1.2 Ensure ALL Interactions Are Logged

**File**: `noctem/telegram/handlers.py` — Wrap `handle_message()` with MessageLog:

```python
# At top of file, add import:
from ..services.message_logger import MessageLog

# Modify handle_message() starting at line 253:
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle non-command messages (tasks and quick actions)."""
    text = update.message.text
    
    # Record EVERY interaction
    with MessageLog(text, source="telegram") as log:
        session = get_session()
        
        # ... existing logic ...
        
        # Before returning, set result:
        log.set_result(True, {"response": response_text})
```

**Key insight**: v0.5.0 has `MessageLog` class but it's not consistently used. We need to wrap ALL handlers.

### 1.3 Add Config Defaults for Butler

**File**: `noctem/config.py` — Add to DEFAULTS dict (line 10):

```python
DEFAULTS = {
    # ... existing ...
    
    # Butler protocol (v0.6.0)
    "butler_contacts_per_week": 5,
    "butler_update_days": ["monday", "wednesday", "friday"],
    "butler_update_time": "09:00",
    "butler_clarification_days": ["tuesday", "thursday"],
    "butler_clarification_time": "09:00",
    
    # Slow mode (v0.6.0)
    "slow_mode_enabled": True,
    "slow_model": "qwen2.5:7b-instruct-q4_K_M",
    "ollama_host": "http://localhost:11434",
    "slow_idle_minutes": 5,  # Wait this long after last message
}
```

### 1.4 Handle Unclear Input Gracefully

**File**: `noctem/telegram/handlers.py` — Modify `handle_new_task()` (line 308):

Currently, if parsing fails, it says "Couldn't parse task name." Instead:

```python
async def handle_new_task(update: Update, text: str, session=None):
    """Parse and create a new task from natural language."""
    parsed = parse_task(text)
    
    if not parsed.name or len(parsed.name.strip()) < 2:
        # Still record it, but as unclear
        task = task_service.create_task(
            name=text,  # Store original text as task name
            tags=["unclear"],  # Mark for review
        )
        if session:
            session.set_last_entity("task", task.id)
        
        await update.message.reply_text(
            f"✉️ Filed: \"{text}\"\n_I'll review this later._",
            parse_mode="Markdown"
        )
        return
    
    # ... rest of existing logic ...
```

**Key principle**: Nothing is lost. Even unclear input becomes a task tagged for review.

### Phase 1 Tests

**File**: `tests/test_v060_fast_mode.py` (new file):

```python
def test_unclear_input_still_recorded():
    """Unclear input should create task tagged 'unclear'."""
    # Simulate very short/unclear input
    task = task_service.create_task(name="?", tags=["unclear"])
    assert task.id is not None
    assert "unclear" in task.tags

def test_message_log_records_all():
    """Every message should be in message_log."""
    with MessageLog("test input", source="test") as log:
        log.set_parsed("TEST", {})
        log.set_action("test_action")
        log.set_result(True, {})
    
    logs = get_recent_logs(1)
    assert len(logs) == 1
    assert logs[0]["raw_message"] == "test input"
```

---

## Phase 2: Butler Protocol

**Goal**: Respectful, scheduled contact. Never pushy.

### 2.1 Contact Budget System

```python
class ButlerProtocol:
    """
    Manages the 5 contacts per week budget.
    """
    
    def get_remaining_contacts(self, week: int, year: int) -> int:
        """How many contacts left this week?"""
        
    def can_contact(self, contact_type: str) -> bool:
        """Check if we have budget for this contact type."""
        
    def record_contact(self, contact_type: str, message: str):
        """Log that we contacted the user."""
        
    def get_scheduled_times(self) -> List[datetime]:
        """When are our next scheduled contacts?"""
```

### 2.2 Update Message Generation

Updates summarize system state (fast, no LLM):

```python
def generate_update_message() -> str:
    """
    Template-based summary:
    - Tasks due today/this week
    - Overdue items
    - Projects with no recent activity
    - Habits status
    
    No LLM. Just data aggregation + templates.
    """
```

### 2.3 Clarification Queue

When slow mode identifies unclear items:

```python
class ClarificationQueue:
    """
    Holds questions to ask user during clarification contacts.
    Limited to 2 per week by butler protocol.
    """
    
    def add_question(self, task_id: int, question: str, options: List[str]):
        """Queue a clarification question."""
        
    def get_next_questions(self, limit: int = 3) -> List[Question]:
        """Get highest priority questions for next contact."""
```

### 2.4 Scheduler Integration

Modify existing scheduler (APScheduler) for butler contacts:

```python
def schedule_butler_contacts():
    """
    Based on user preferences, schedule:
    - 3 update messages (e.g., Mon/Wed/Fri 9am)
    - 2 clarification windows (e.g., Tue/Thu 9am, only if queue non-empty)
    """
```

### Phase 2 Tests
- [ ] Contact budget enforced (max 5/week)
- [ ] Update messages generated correctly
- [ ] Clarification queue works
- [ ] Scheduler triggers at correct times
- [ ] User can modify preferences

---

## Phase 3: Slow Mode Foundation

**Goal**: Background LLM processing for 2 specific tasks.

### 3.1 Slow Mode Loop

```python
class SlowModeLoop:
    """
    Runs in background thread/process.
    Only active when:
    - User hasn't sent message in 5+ minutes
    - LLM is available
    - There's work to do
    """
    
    def run(self):
        while True:
            if self.user_is_idle() and self.llm_available():
                self.process_pending_tasks()
                self.process_pending_projects()
            time.sleep(60)  # Check every minute
```

### 3.2 Task Analysis: "What Could a Computer Help With?"

For each task without computer_help_suggestion:

```python
def analyze_task_for_computer_help(task: Task) -> str:
    """
    Uses local LLM to answer:
    "Given this task, what could a computer/automation help with?"
    
    Examples:
    - "Buy groceries" → "Could generate shopping list, find deals, set reminder"
    - "File taxes" → "Could gather documents, pre-fill forms, schedule appointment"
    - "Call mom" → "Could suggest times based on calendar, set reminder"
    
    Returns suggestion string. Stored in task record.
    """
    
    prompt = f"""Task: {task.name}
Context: {task.project_name or 'No project'}, Due: {task.due_date or 'No date'}

What could a computer or automation help with for this task?
Be specific and practical. One paragraph max."""
    
    return llm_generate(prompt)
```

### 3.3 Project Analysis: "What Should Person Do Next?"

For each project:

```python
def analyze_project_for_next_action(project: Project) -> str:
    """
    Uses local LLM to answer:
    "Given this project and its tasks, what should the person do next?"
    
    Considers:
    - Task priorities
    - Dependencies (if Task B needs Task A done first)
    - What's blocking progress
    
    Returns suggested next action. Stored in project record.
    """
    
    tasks = get_tasks_for_project(project.id)
    task_summary = "\n".join([f"- {t.name} (status: {t.status})" for t in tasks])
    
    prompt = f"""Project: {project.name}
Tasks:
{task_summary}

What should the person do next to make progress on this project?
Be specific. One concrete action."""
    
    return llm_generate(prompt)
```

### 3.4 Slow Work Queue with Dependencies

```sql
CREATE TABLE IF NOT EXISTS slow_work_queue (
    id INTEGER PRIMARY KEY,
    work_type TEXT,              -- 'task_computer_help', 'project_next_action'
    target_id INTEGER,           -- task_id or project_id
    depends_on_id INTEGER,       -- Another slow_work_queue item that must complete first
    status TEXT DEFAULT 'pending', -- pending, processing, completed, failed
    result TEXT,                 -- The generated suggestion
    queued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT
);
```

**Dependency logic**:
- All tasks in a project get `task_computer_help` analysis first
- Then the project gets `project_next_action` analysis (depends on all task analyses)

### 3.5 Graceful Degradation

```python
class GracefulDegradation:
    """
    When LLM unavailable:
    - Slow mode pauses
    - Work stays in queue
    - Fast mode continues normally
    - When LLM returns, process queue
    """
    
    def check_llm_health(self) -> bool:
        """Ping Ollama, return True if responsive."""
        
    def get_system_status(self) -> str:
        """'full' | 'degraded' | 'offline'"""
```

### Phase 3 Tests
- [ ] Slow loop only runs when user idle
- [ ] Task analysis generates reasonable suggestions
- [ ] Project analysis generates reasonable next actions
- [ ] Dependencies respected in queue processing
- [ ] Graceful degradation works (LLM down → queue persists)
- [ ] Results stored correctly

---

## Phase 4: Integration & Polish

**Goal**: Everything works together. Ready for daily use.

### 4.1 Telegram Integration Updates

- [ ] All fast mode responses use templates
- [ ] Butler protocol enforced for outgoing messages
- [ ] Slow mode suggestions accessible via commands (e.g., `/suggest`)
- [ ] Setup flow for new users (set contact preferences)

### 4.2 Web Dashboard Updates

- [ ] Show slow mode suggestions on tasks/projects
- [ ] Show butler contact history
- [ ] Show interaction log (for debugging/review)
- [ ] System status indicator (full/degraded/offline)

### 4.3 CLI Updates

- [ ] Command to view/clear slow work queue
- [ ] Command to force slow mode run
- [ ] Command to view interaction log
- [ ] Command to modify butler preferences

### 4.4 Startup & Health

- [ ] Clean startup sequence: DB → Fast mode → Scheduler → Slow mode
- [ ] Health check endpoint/command
- [ ] Graceful shutdown (finish current slow work)

### Phase 4 Tests
- [ ] End-to-end: Add task via Telegram → appears on web
- [ ] End-to-end: Slow mode generates suggestion → visible on web
- [ ] Butler contacts sent at scheduled times
- [ ] System recovers from LLM restart
- [ ] All v0.5.0 functionality still works

---

## Phase 5: Personal Testing

**Goal**: Use it daily. Find what breaks.

### 5.1 Dogfooding Protocol

- [ ] Use as primary task capture for 1 week
- [ ] Note friction points
- [ ] Note what's missing
- [ ] Note what's annoying

### 5.2 Iteration

- [ ] Fix critical bugs
- [ ] Adjust templates based on usage
- [ ] Tune slow mode prompts
- [ ] Adjust butler contact frequency if needed

---

## Success Criteria for v0.6.0

1. **Fast mode works**: Every message captured <500ms, nothing lost
2. **Butler respected**: Never more than 5 unprompted contacts/week
3. **Slow mode runs**: Suggestions generated for tasks and projects
4. **Graceful degradation**: System works (degraded) without Ollama
5. **Recording complete**: All interactions logged for v0.7 analysis
6. **Daily usable**: Developer uses it as primary task system for 1+ week

---

## Data Model Summary

```
User Input (Telegram)
    │
    ▼
┌─────────────┐
│ Fast Parser │ ──────► interaction_log (ALL inputs)
└─────────────┘
    │
    ▼
┌─────────────┐
│  Services   │ ──────► tasks, projects, habits, etc.
└─────────────┘
    │
    ▼
┌─────────────┐
│  Response   │ ──────► Templates (instant)
└─────────────┘

Background (when idle):
┌─────────────┐
│ Slow Loop   │ ──────► slow_work_queue
└─────────────┘
    │
    ▼
┌─────────────┐
│  Local LLM  │ ──────► task.computer_help_suggestion
└─────────────┘         project.next_action_suggestion

Scheduled:
┌─────────────┐
│  Scheduler  │ ──────► butler_contacts
└─────────────┘
    │
    ▼
┌─────────────┐
│  Telegram   │ ──────► User (max 5/week)
└─────────────┘
```

---

## Dependencies

### Required (v0.5.0 already has most)
- Python 3.9+
- SQLite
- python-telegram-bot
- APScheduler
- Flask

### New for v0.6.0
- Ollama (for slow mode) — with graceful degradation if unavailable
- httpx or requests (for Ollama API calls)

### Development
- pytest
- pytest-asyncio (if using async Telegram)

---

## File Structure After Implementation

```
noctem/
├── __init__.py
├── main.py                    # Entry point, mode selection
├── db.py                      # Schema + migrations
├── models.py                  # Dataclasses
├── config.py                  # Configuration
│
├── fast/                      # NEW: Fast mode components
│   ├── __init__.py
│   ├── parser.py              # Rule-based parsing
│   ├── responder.py           # Template responses
│   └── recorder.py            # Interaction logging
│
├── slow/                      # NEW: Slow mode components
│   ├── __init__.py
│   ├── loop.py                # Background processing loop
│   ├── task_analyzer.py       # "What could computer help with?"
│   ├── project_analyzer.py    # "What should person do next?"
│   ├── queue.py               # Work queue with dependencies
│   └── degradation.py         # Health checks, fallbacks
│
├── butler/                    # NEW: Butler protocol
│   ├── __init__.py
│   ├── protocol.py            # Contact budget management
│   ├── updates.py             # Update message generation
│   └── clarifications.py      # Clarification queue
│
├── services/                  # Existing business logic
│   ├── task_service.py
│   ├── project_service.py
│   ├── habit_service.py
│   └── ...
│
├── telegram/                  # Existing + modifications
│   ├── handlers.py
│   └── formatter.py
│
├── web/                       # Existing + modifications
│   ├── app.py
│   └── templates/
│
├── scheduler/                 # Existing + butler integration
│   └── jobs.py
│
└── tests/                     # NEW: Test suite
    ├── __init__.py
    ├── conftest.py            # Fixtures, test DB
    ├── test_fast_parser.py
    ├── test_butler_protocol.py
    ├── test_slow_mode.py
    └── test_integration.py
```

---

## Timeline Estimate

| Phase | Estimated Time | Cumulative |
|-------|---------------|------------|
| Phase 0: Review & Setup | 1-2 sessions | Day 1-2 |
| Phase 1: Fast Mode | 2-3 days | Day 5 |
| Phase 2: Butler Protocol | 1-2 days | Day 7 |
| Phase 3: Slow Mode | 2-3 days | Day 10 |
| Phase 4: Integration | 2-3 days | Day 13 |
| Phase 5: Testing | Ongoing | Day 14+ |

**Target**: Usable personal MVP by end of February.

---

## Phase 0 Answers (Completed)

1. **Parser**: `noctem/parser/task_parser.py` — `parse_task()` handles NLP, `parse_command()` handles commands
2. **Database**: 8 tables exist (goals, projects, tasks, habits, habit_logs, time_blocks, config, action_log, message_log). Need to ADD: butler_contacts, slow_work_queue. Need to ALTER: tasks, projects (add suggestion columns)
3. **Telegram handlers**: `telegram/handlers.py:handle_message()` is main entry, routes to specific handlers
4. **Scheduler**: `scheduler/jobs.py` — APScheduler with morning briefing + calendar sync jobs
5. **Tests**: `tests/test_noctem.py` — pytest with temp DB isolation, ~200 lines of tests
6. **Config**: `config.py` — Key-value in DB with DEFAULTS fallback and caching

---

## Quick Reference: Key Files to Modify

| Phase | File | Change |
|-------|------|--------|
| 1 | db.py | Add tables, ALTER columns |
| 1 | config.py | Add butler/slow defaults |
| 1 | telegram/handlers.py | Wrap with MessageLog, handle unclear |
| 2 | butler/protocol.py | NEW: Contact budget logic |
| 2 | scheduler/jobs.py | Add butler contact jobs |
| 3 | slow/loop.py | NEW: Background thread |
| 3 | slow/task_analyzer.py | NEW: Ollama integration |
| 4 | main.py | Start slow loop in 'all' mode |

---

*Draft 2 - 2026-02-14*  
*Phase 0 Complete — Ready for YOUR setup steps, then Phase 1*

*Co-Authored-By: Warp <agent@warp.dev>*
