# Noctem v0.6.0 Research Report - Phase 1
## Background AI Task Runner for Life Management

**Date**: 2026-02-13  
**Status**: In Progress - Phase 1 Complete  
**Focus**: Lightweight local AI for autonomous task assistance

---

## Executive Summary

This research investigates practical approaches for building v0.6.0 of Noctem: a background AI task runner that helps users complete real-life tasks autonomously, running locally on limited hardware. The system should:
1. Score tasks for AI helpfulness (0→1, mathematically simple)
2. Generate "what should I do next" suggestions
3. Handle system/task-level recovery gracefully
4. Run continuously in the background with minimal user intervention

**Key Constraints:**
- No GPT-like systems (must run on limited hardware)
- Everything local for privacy
- Ambient computing philosophy (works autonomously, secure by default)
- Telegram-only interaction (morning/evening updates ideal)

---

## Research Area 1: Lightweight ML Classifiers (No Neural Networks)

### Findings: Scikit-learn for Task Scoring

**Best Candidates for "Could AI Help" Classifier:**

1. **Logistic Regression**
   - Extremely lightweight and fast
   - Works well with small datasets (100-500 examples)
   - Interpretable coefficients (can see what features matter)
   - <1ms inference time

2. **Decision Tree Classifier**
   - No training overhead after building tree
   - Easy to understand decision logic
   - Good for categorical features (tags, project types)
   - Can export as human-readable rules

3. **Naive Bayes (Multinomial)**
   - Very fast training and prediction
   - Works well with text features (task descriptions)
   - Probabilistic output naturally fits 0→1 score
   - Minimal memory footprint

4. **K-Nearest Neighbors (KNN)**
   - No training phase (lazy learning)
   - Good for small datasets
   - Can adapt as new tasks are added
   - Simple to implement

5. **Support Vector Machine (Linear SVM)**
   - Fast inference after training
   - Works well in high-dimensional spaces
   - Good generalization with small datasets
   - <5ms prediction time

**Recommendation for v0.6.0:**
Start with **Logistic Regression** or **Naive Bayes** for the "could AI help" scorer:
- Train on features: task length, has due date, contains question words, has tags, project association, recurrence
- Output: probability score 0→1
- Retrain nightly as new tasks are labeled

**Feature Engineering for Task Scoring:**
```python
features = {
    'word_count': len(task.name.split()),
    'has_due_date': 1 if task.due_date else 0,
    'has_time': 1 if task.due_time else 0,
    'has_project': 1 if task.project_id else 0,
    'has_tags': len(task.tags),
    'urgency': task.urgency,
    'importance': task.importance,
    'contains_question': 1 if '?' in task.name else 0,
    'contains_research': 1 if any(w in task.name.lower() for w in ['research', 'find', 'look up']) else 0,
    'contains_write': 1 if any(w in task.name.lower() for w in ['write', 'draft', 'email']) else 0,
    'contains_schedule': 1 if any(w in task.name.lower() for w in ['schedule', 'book', 'arrange']) else 0,
}
```

---

## Research Area 2: What People Automate (2026 Trends)

### Key Findings from Productivity Research

**Top Non-AI Time Savers (Fast to Run):**

1. **Micro-Automations (2 minutes × 5 times/day = 40 hours/year)**
   - Auto-filing emails/documents
   - Auto-sorting tasks by priority
   - Auto-generating daily summaries
   - Triggering reminders based on context

2. **Data Entry & Form Filling**
   - Repetitive button clicks (RPA-style)
   - Calendar event creation
   - Contact information updates
   - Expense tracking

3. **Communication Routing**
   - Email categorization (newsletters vs. action-required)
   - Meeting request consolidation
   - Appointment confirmations (auto-response)
   - Follow-up reminders

4. **Document Generation**
   - Weekly reports from structured data
   - Meeting agendas from calendar
   - Task lists from email threads
   - Progress summaries

5. **Scheduling Optimizations**
   - Find mutual availability
   - Reschedule when conflicts arise
   - Block focus time automatically
   - Suggest meeting times based on productivity patterns

6. **Research Aggregation**
   - Collect links/resources on a topic
   - Summarize articles
   - Extract key data points
   - Create structured notes

**Key Stat**: <cite index="14-1">By 2026, up to 70% of everyday work tasks may be automated</cite>, but the focus is on **augmenting** humans, not replacing them.

**Relevant for Noctem v0.6.0:**
- Breaking tasks into subtasks (research → specific searches)
- Generating search queries for external execution
- Creating checklists for complex tasks
- Suggesting resources/tools for task completion
- Draft text generation (emails, messages, notes) for user review

---

## Research Area 3: Background Task Runner Architectures

### Python Patterns for Persistent Services

**Best Practices from Research:**

1. **Daemon Thread Pattern**
   - Main loop runs in daemon thread
   - Sleeps between checks (reduce CPU usage)
   - Uses `threading.Event()` for clean shutdown
   - Monitors state via shared queue or global flags

2. **State Persistence**
   - SQLite for current work state
   - Track: what's running, what's queued, what's waiting for approval
   - Checkpoint progress regularly
   - Enable quick restart after crash

3. **Telegram Bot as Separate Thread**
   - Independent polling loop
   - Non-blocking (async or separate thread)
   - Communicates with main loop via queue
   - Can respond immediately while background work continues

**Architecture Pattern:**
```python
# Main loop (daemon thread)
while True:
    - Check task list
    - Check current work status
    - Decide what to do next
    - Update database
    - Sleep (5-30 seconds)

# Telegram bot (separate thread/process)
while True:
    - Poll for messages
    - Handle commands
    - Update state in database
    - Respond immediately
```

**Key Insight**: <cite index="21-2,21-17,21-18">Use a while-loop that does not end, with each iteration checking for desired state via a shared queue or database</cite>

**For Quick Restarts:**
- Store "current work" in SQLite with status column
- On startup, check for RUNNING tasks and resume or mark as FAILED
- Log all state changes for recovery
- Use file locks to prevent multiple instances

---

## Research Area 4: System Recovery Patterns

### Resilience Strategies

**System-Level Recovery:**
1. **Graceful Degradation**
   - If AI model fails, fall back to simpler scoring
   - If database locked, retry with exponential backoff
   - If Telegram fails, queue messages for later

2. **Health Checks**
   - Periodically verify components are working
   - Log errors to SQLite action_log table
   - Send Telegram notification on critical failures

3. **Automatic Restart**
   - Use systemd (Linux) or Task Scheduler (Windows)
   - On crash, wait 10 seconds and restart
   - Track restart count to detect crash loops

**Task-Level Recovery:**
1. **Retry Logic**
   - If "what should I do next" generation fails, retry once
   - If external prompt generation fails, mark task for manual review
   - Track failure count per task

2. **Rollback**
   - If task enters bad state, revert to "unassessed"
   - Clear AI suggestions if they're stale (>24 hours)

3. **User Notification**
   - Send Telegram message when AI gives up on a task
   - Include failure reason and last known state
   - Allow user to retry or skip via command

**Key Principle**: <cite index="22-4,22-5,22-18,22-19">Durable execution with state persistence allows resuming after failures, handling retries and progress tracking automatically</cite>

---

## Research Area 5: Task Automation Insights (2026)

### What Actually Gets Automated

**Common Patterns:**

1. **Small Repetitive Actions** (<cite index="20-1,20-39,20-40">2-minute tasks repeated 5 times daily = 40 hours annually</cite>)
   - File sorting
   - Email routing
   - Task categorization
   - Reminder triggers

2. **Context Switching Reduction**
   - Tool consolidation (fewer apps)
   - Dashboards as single starting point
   - Async communication (reduce meeting interruptions)

3. **Focus Protection**
   - Blocking focus time automatically
   - Batching similar tasks
   - Reducing notification noise

**Relevant for v0.6.0:**
- Auto-categorize tasks (work, personal, errands)
- Batch similar tasks for efficient completion
- Suggest optimal times for task execution
- Generate "focus session" agendas

---

## Next Research Phase (To Complete)

**Still needed:**

1. **Psychology of Habit Formation**
   - Implementation intentions (Gollwitzer)
   - Cognitive load management
   - Gamification that works
   - How to make AI assistance feel helpful, not nagging

2. **Lightweight Local LLMs**
   - Models that run on limited hardware (no GPU)
   - CPU-only options (Llama.cpp, GGUF format)
   - Model size vs. capability tradeoffs
   - Ollama vs. alternatives for Windows

3. **State Management Best Practices**
   - Event-driven vs. polling
   - SQLite performance for concurrent reads/writes
   - Locking strategies
   - State machine patterns

4. **Recovery & Error Handling**
   - Exponential backoff strategies
   - Circuit breaker pattern
   - Health check implementations
   - User notification UX

---

## Preliminary Recommendations

### For "Could AI Help" Scorer:
- Use **Naive Bayes** on task features
- Train on 200-500 labeled examples
- Retrain weekly as new data accumulates
- Store model in pickle file (~10KB)

### For Background Loop:
- Daemon thread with 10-second sleep intervals
- SQLite table for current work state
- Telegram bot in separate thread
- Queue for inter-thread communication

### For Task Suggestion Generator:
- Keep prompts minimal (no GPT, just templates)
- Generate based on task type heuristics
- Store suggestions in database
- Expire after 24 hours if not acted upon

### For Recovery:
- Store all state in SQLite
- Log errors to action_log table
- Send Telegram alerts on critical failures
- Restart automatically on crash

---

**Status**: Phase 1 complete. Continuing research on psychology, LLMs, and detailed implementation patterns.

**Next Steps**: 
- Complete remaining research areas
- Propose detailed architecture
- Create implementation plan
- Get user feedback and iterate

*Research conducted: 2026-02-13*
