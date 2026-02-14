# Noctem v0.6.0 Implementation Plan
## Background AI Task Runner for Life Management

**Date**: 2026-02-13  
**Status**: Phase A In Progress

---

## Development Decisions

- **Build location**: Copy `0.5.0 minimum minimum working/noctem/` → `0.6.0/noctem/` and extend
- **Phased approach**: Complete Phase A → user testing → feedback → continue
- **Fast-path scoring**: Use scikit-learn (already installed) instead of LLM for Phase A

---

## Environment Status (2026-02-13)

| Component | Status | Action |
|-----------|--------|--------|
| Python | 3.9.13 ✓ | Ready |
| scikit-learn | 1.0.2 ✓ | Use for fast scoring |
| Ollama | ❌ Not installed | Install before Phase B |
| Flask | 1.1.2 | Upgrade to 3.0 |
| python-telegram-bot | ❌ | Install |
| APScheduler | ❌ | Install |
| requests | 2.28.1 ✓ | Ready |

**Setup command** (run before Phase A):
```bash
pip install python-telegram-bot>=20.0 APScheduler>=3.10 flask>=3.0 python-dateutil>=2.8 icalendar>=5.0 qrcode[pil]>=7.0 httpx
```

---

## Problem Statement

Noctem 0.5.0 provides a functional task/habit management system with Telegram integration and web dashboard. v0.6.0 adds an AI layer that works *behind the scenes* to help break down tasks, suggest next steps, and handle the cognitive load — while keeping the user fully in control.

**Design Metaphor** (from user discussion):
> *The AI layer is a background sous-chef — you're still the head chef deciding what gets cooked, but they're prepping ingredients, suggesting recipes, and asking "did you mean shallots or onions?" when your handwriting is unclear.*

---

## Current State (0.5.0)

Existing structure in `0.5.0 minimum minimum working/noctem/`:

| File/Folder | Purpose |
|-------------|---------|
| `main.py` | Entry point with modes: bot, web, cli, all |
| `db.py` | SQLite schema: tasks, habits, projects, goals, time_blocks, action_log |
| `models.py` | Dataclasses: Task, Habit, Project, Goal, TimeBlock, ActionLog |
| `telegram/` | Bot handlers and formatter |
| `web/` | Flask dashboard with templates |
| `scheduler/` | APScheduler jobs for notifications |
| `services/` | Task, habit, project, goal, briefing services |

---

## Proposed Changes

### 1. New Database Tables

Add to `db.py` SCHEMA:

```sql
-- AI help scores for tasks
ALTER TABLE tasks ADD COLUMN ai_help_score REAL;  -- 0-1, NULL = not scored
ALTER TABLE tasks ADD COLUMN ai_processed_at TIMESTAMP;

-- Implementation intentions (full breakdowns)
CREATE TABLE IF NOT EXISTS implementation_intentions (
    id INTEGER PRIMARY KEY,
    task_id INTEGER REFERENCES tasks(id),
    version INTEGER DEFAULT 1,
    when_trigger TEXT,
    where_location TEXT,
    how_approach TEXT,
    first_action TEXT,
    generated_by TEXT,  -- 'llm' or 'user_edited'
    confidence REAL,
    status TEXT DEFAULT 'draft',  -- draft | approved | in_progress | completed
    user_feedback TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);

-- Next steps extracted from intentions
CREATE TABLE IF NOT EXISTS next_steps (
    id INTEGER PRIMARY KEY,
    task_id INTEGER REFERENCES tasks(id),
    intention_id INTEGER REFERENCES implementation_intentions(id),
    step_text TEXT,
    step_order INTEGER,
    status TEXT DEFAULT 'pending',  -- pending | current | completed | skipped
    completed_at TIMESTAMP
);

-- Clarification requests
CREATE TABLE IF NOT EXISTS clarification_requests (
    id INTEGER PRIMARY KEY,
    task_id INTEGER,
    question TEXT,
    options TEXT,  -- JSON array
    status TEXT DEFAULT 'pending',  -- pending | answered | skipped
    response TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    responded_at TIMESTAMP
);

-- Pending slow work queue (for graceful degradation)
CREATE TABLE IF NOT EXISTS pending_slow_work (
    id INTEGER PRIMARY KEY,
    task_type TEXT,
    task_id INTEGER,
    task_data TEXT,  -- JSON
    queued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP,
    status TEXT DEFAULT 'pending'  -- pending | processing | completed | failed
);

-- Notification response tracking (for adaptive timing)
CREATE TABLE IF NOT EXISTS notification_responses (
    id INTEGER PRIMARY KEY,
    notification_id INTEGER,
    sent_at TIMESTAMP,
    responded_at TIMESTAMP,
    response_delay_minutes REAL,
    day_of_week INTEGER,
    notification_type TEXT,
    was_actioned INTEGER
);
```

---

### 2. New Files to Create

#### `noctem/ai/__init__.py`
Empty init.

#### `noctem/ai/router.py`
Fast/slow path decision logic:

```python
class PathRouter:
    FAST_TASKS = ['register_task', 'status_query', 'score_task', 'simple_clarification']
    SLOW_TASKS = ['implementation_intention', 'external_prompt', 'complex_clarification']
    
    def route(self, request_type: str, context: dict) -> str:
        if request_type in self.FAST_TASKS:
            return 'fast'
        if request_type in self.SLOW_TASKS:
            return 'slow'
        return 'fast'  # Default safe
```

#### `noctem/ai/scorer.py`
Task AI-helpfulness scoring (fast path):
- **Option A**: scikit-learn Naive Bayes (instant, no LLM)
- **Option B**: qwen2.5:1.5b for simple classification

Features: word_count, has_due_date, contains_question, contains_research/write/schedule keywords, has_tags

#### `noctem/ai/intention_generator.py`
Slow path — generates implementation intentions:
- Uses qwen2.5:7b via Ollama
- Input: task name, project context, user history
- Output: when_trigger, where_location, how_approach, first_action

#### `noctem/ai/degradation.py`
Graceful degradation manager:

```python
class GracefulDegradation:
    def check_health(self) -> str:  # 'full' | 'degraded' | 'minimal' | 'offline'
    def execute_with_fallback(self, task_type, task_data) -> dict
    def queue_for_later(self, task_type, task_data)
    def process_pending_when_healthy(self)
```

#### `noctem/ai/timing.py`
Adaptive notification timing:
- Track response delays per hour
- After ~7 responses, shift notification times toward responsive hours
- Defaults: 8am and 8pm

#### `noctem/ai/clarification.py`
Clarification skill:
- Detect when task is vague (< 5 words, question words, low confidence)
- Generate specific questions with options
- Send via Telegram for urgent, queue for web page otherwise

#### `noctem/ai/loop.py`
Main AI background loop (daemon thread):

```python
class AILoop:
    def run(self):
        while True:
            level = self.degradation.check_health()
            if level == 'full' and self.has_pending_slow_work():
                self.process_pending()
            for task in self.get_unprocessed_tasks():
                self.process_task(task, level)
            if self.is_notification_time():
                self.send_digest()
            time.sleep(30)
```

---

### 3. Modified Files

#### `noctem/main.py`
- Add AI loop startup in "all" mode
- New CLI mode "ai" to run AI loop standalone

```python
def run_ai_loop():
    from .ai.loop import AILoop
    loop = AILoop()
    loop.run()
```

#### `noctem/models.py`
- Add `ai_help_score` and `ai_processed_at` to Task dataclass
- Add new dataclasses: ImplementationIntention, NextStep, ClarificationRequest

#### `noctem/services/task_service.py`
- Add methods: `get_unscored_tasks()`, `update_ai_score()`, `get_ai_ready_tasks()`

#### `noctem/telegram/handlers.py`
- Handle clarification responses
- New command `/nextaction` — shows current next step for a task
- New command `/aisettings` — configure AI aggressiveness

#### `noctem/web/templates/`
- New template `clarifications.html` — review pending clarifications
- New template `breakdowns.html` — review/approve implementation intentions
- Modify `dashboard.html` — show AI status indicator

---

### 4. Configuration Additions

Add to `config` table defaults:

```python
'ai_enabled': True,
'fast_model': 'qwen2.5:1.5b-instruct-q4_K_M',
'slow_model': 'qwen2.5:7b-instruct-q4_K_M',
'morning_notification_time': '08:00',
'evening_notification_time': '20:00',
'ai_confidence_threshold': 0.7,
'ollama_host': 'http://localhost:11434',
```

---

## Implementation Phases

### Phase A: Foundation (DB + Core AI) ← CURRENT
1. Copy 0.5.0 to 0.6.0 directory
2. Install missing dependencies
3. Add new tables to db.py (ai_help_score columns + new tables)
4. Create `noctem/ai/` directory structure
5. Implement `scorer.py` with scikit-learn + rule-based fallback (no LLM needed)
6. Implement `degradation.py` health checks
7. Basic `loop.py` that scores tasks only
8. Add tests for scoring and degradation

**Test**: 
- Tasks get ai_help_score populated automatically
- System works without Ollama (graceful degradation validated)
- All existing 0.5.0 functionality still works

---

### Phase B: Implementation Intentions
1. Implement `intention_generator.py` with Ollama integration
2. Create `next_steps` extraction logic
3. Add Telegram `/nextaction` command
4. Create web `breakdowns.html` template

**Test**: High-scored tasks get implementation intentions generated, viewable on web

---

### Phase C: Clarification System
1. Implement `clarification.py` skill
2. Add Telegram clarification handlers
3. Create web `clarifications.html` template
4. Wire up response tracking

**Test**: Vague tasks trigger clarification requests, responses update task context

---

### Phase D: Adaptive Timing
1. Implement `timing.py` learning algorithm
2. Add notification_responses tracking
3. Modify scheduler to use learned times

**Test**: After ~7 responses, notification times shift toward user's responsive hours

---

### Phase E: Polish & Integration
1. Add AI status to dashboard
2. Implement `/aisettings` command
3. End-to-end testing
4. Documentation

---

## Future Ideas (Not for MVP)

### Metaphor-Based Understanding Confirmation

*Note from user discussion*: When confirming AI understands a complex task, have it respond with a 2-3 sentence metaphor explaining the task back to the user. This creates a "soft handshake" that feels natural rather than a dry "I will do X, Y, Z" confirmation.

**Example:**
> User: "Plan vacation"  
> AI: "Got it — I'll be your travel agent drafting an itinerary. I'll start by sketching out destinations and timelines, then come back with a shortlist for you to pick from. Sound right?"

This could be triggered for tasks with confidence < 0.8 or complexity > threshold. Store metaphor templates per task category.

---

## Dependencies

- Ollama installed and running locally
- Models pulled: `qwen2.5:1.5b-instruct-q4_K_M`, `qwen2.5:7b-instruct-q4_K_M`
- Optional: scikit-learn for ML-based scoring

---

## File Structure After Implementation

```
noctem/
├── ai/
│   ├── __init__.py
│   ├── clarification.py
│   ├── degradation.py
│   ├── intention_generator.py
│   ├── loop.py
│   ├── router.py
│   ├── scorer.py
│   └── timing.py
├── handlers/
├── parser/
├── scheduler/
├── services/
├── telegram/
├── web/
│   ├── templates/
│   │   ├── breakdowns.html
│   │   ├── clarifications.html
│   │   └── ...
├── cli.py
├── config.py
├── db.py
├── main.py
├── models.py
└── ...
```

---

## Success Criteria

1. **Ambient**: AI works in background; user only sees results in digests
2. **Graceful**: System functions (degraded) when Ollama is down
3. **Helpful**: Implementation intentions actually help users start tasks
4. **Respectful**: Clarifications feel collaborative, not nagging
5. **Adaptive**: Notification timing improves with use

---

*Ready for implementation approval.*

*Co-Authored-By: Warp <agent@warp.dev>*
