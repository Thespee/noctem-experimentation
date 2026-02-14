# Noctem v0.6.0 Research Report - Phase 3
## Fast/Slow Architecture, Adaptive Timing & Graceful Degradation

**Date**: 2026-02-13  
**Status**: Phase 3 Complete  
**Focus**: Deep dive into dual-mode processing, adaptive notification timing, fallback patterns

---

## User Clarifications Applied

From your feedback:
1. **Notification timing**: 8am/8pm defaults, adaptable based on actual response patterns
2. **Clarification channels**: Telegram + web page; Telegram for urgent
3. **Fallback**: Smart code when LLM down, mark for redo when back
4. **Fast/Slow pattern**: Should penetrate the whole system design
5. **Task breakdowns**: Full when/where/how stored for review + concrete next step

---

## Research Area 1: Fast/Slow Dual-Mode Architecture

### Kahneman's System 1 & System 2 Applied to AI Agents

**Google DeepMind's "Talker-Reasoner" Architecture** (Oct 2024):

> "We divide the agent into two agents: a fast and intuitive Talker agent and a slower and deliberative Reasoner agent."

| Component | System 1 (Fast) | System 2 (Slow) |
|-----------|-----------------|-----------------|
| **Role** | Quick responses, simple tasks | Complex reasoning, planning |
| **Trigger** | Every interaction | Only when needed |
| **Model** | Small (1.5B) | Large (7B+) |
| **Latency** | <1 second | 5-30 seconds |
| **Cost** | Low compute | High compute |

**Key Design Insight**:
> "The Talker should automatically determine whether it requires System 2 reasoning, and therefore the Reasoner, or whether it can safely proceed with its System 1 thinking."

### Noctem Fast/Slow Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    NOCTEM v0.6.0                            │
├─────────────────────────────────────────────────────────────┤
│  FAST PATH (System 1)           SLOW PATH (System 2)        │
│  ─────────────────────          ──────────────────────      │
│  • Task registration            • "What's next step?"       │
│  • "Could AI help?" score       • Full implementation       │
│  • Simple clarifications          intention breakdown       │
│  • Status queries               • External prompt gen       │
│  • Error detection              • Complex reasoning         │
│  • Notification dispatch        • Plan refinement           │
│                                                             │
│  Model: qwen2.5:1.5b            Model: qwen2.5:7b           │
│  OR scikit-learn                Fallback: queue for later   │
│  Latency: <500ms                Latency: 5-30s              │
│  Always available               May be deferred             │
└─────────────────────────────────────────────────────────────┘
```

### When to Use Each Path

| Situation | Path | Rationale |
|-----------|------|-----------|
| New task added | Fast | Just register, score later |
| User asks "what should I do?" | Slow | Needs reasoning |
| Task needs clarification (simple) | Fast | Template questions |
| Generate implementation intention | Slow | Needs full breakdown |
| LLM is down | Fast only | Graceful degradation |
| Check if work pending | Fast | Simple DB query |
| Generate prompt for external AI | Slow | Needs quality output |

### Fast/Slow Decision Logic

```python
class PathRouter:
    def route(self, request_type, context):
        # Always fast
        if request_type in ['register_task', 'status_query', 'error_detect']:
            return 'fast'
        
        # Always slow
        if request_type in ['implementation_intention', 'external_prompt']:
            return 'slow'
        
        # Conditional
        if request_type == 'clarification':
            if context.is_simple_question:
                return 'fast'
            return 'slow'
        
        if request_type == 'next_step':
            if context.has_cached_plan:
                return 'fast'  # Just retrieve
            return 'slow'  # Generate new
        
        return 'fast'  # Default to fast
```

---

## Research Area 2: Adaptive Notification Timing

### Research Findings

**Attelia System** (ScienceDirect):
- <cite index="51-8">Notifications delivered at breakpoint timing resulted in 28% lower frustration</cite>
- <cite index="51-9">Response time of the users to the notifications was quicker by 13% than notifications in random timings</cite>

**Nurture System** (Using Reinforcement Learning):
- <cite index="52-1,52-2,52-3">Nurture converged to a high response rate on week 3, and reaches out to the user more often. The agent then realizes the user starts to show disagreement with the notification schedule, and adjusts the strategy to carefully choose when to approach the user.</cite>

**Yahoo! JAPAN Large-Scale Study** (680,000 users):
- <cite index="56-13,56-14">Delaying the notification delivery until an interruptible moment is detected is beneficial to users and results in significant reduction of user response time (49.7%) compared to delivering the notifications immediately.</cite>

### Simple Adaptive Timing for Noctem

Rather than complex RL, use a **response-window learning** approach:

```python
class AdaptiveNotificationTiming:
    def __init__(self):
        self.default_morning = "08:00"
        self.default_evening = "20:00"
        self.response_history = []  # (sent_time, response_time, response_delay)
    
    def learn_from_response(self, sent_at, responded_at):
        """Track when user actually responds"""
        delay_minutes = (responded_at - sent_at).total_seconds() / 60
        self.response_history.append({
            'sent_hour': sent_at.hour,
            'responded_hour': responded_at.hour,
            'delay_minutes': delay_minutes,
            'day_of_week': sent_at.weekday()
        })
    
    def get_optimal_times(self):
        """Analyze response patterns to find best times"""
        if len(self.response_history) < 7:
            return (self.default_morning, self.default_evening)
        
        # Find hours with fastest response
        by_hour = defaultdict(list)
        for r in self.response_history:
            by_hour[r['responded_hour']].append(r['delay_minutes'])
        
        # Average delay per hour
        avg_delay = {h: sum(delays)/len(delays) for h, delays in by_hour.items()}
        
        # Find best morning (6-12) and evening (17-23) hours
        morning_hours = {h: d for h, d in avg_delay.items() if 6 <= h <= 12}
        evening_hours = {h: d for h, d in avg_delay.items() if 17 <= h <= 23}
        
        best_morning = min(morning_hours, key=morning_hours.get, default=8)
        best_evening = min(evening_hours, key=evening_hours.get, default=20)
        
        return (f"{best_morning:02d}:00", f"{best_evening:02d}:00")
```

### Database Schema for Timing Learning

```sql
CREATE TABLE notification_responses (
    id INTEGER PRIMARY KEY,
    notification_id INTEGER,
    sent_at DATETIME,
    responded_at DATETIME,
    response_delay_minutes REAL,
    day_of_week INTEGER,
    notification_type TEXT,  -- 'morning_digest', 'evening_digest', 'urgent'
    was_actioned BOOLEAN  -- did user take action or just dismiss?
);

CREATE TABLE user_preferences (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at DATETIME
);

-- Store learned optimal times
INSERT INTO user_preferences (key, value) VALUES 
    ('morning_notification_time', '08:00'),
    ('evening_notification_time', '20:00'),
    ('notification_learning_enabled', 'true');
```

---

## Research Area 3: Graceful Degradation

### Core Principle

<cite index="71-1,71-2,71-3">When a component's dependencies are unhealthy, the component itself can still function, although in a degraded manner. Failure modes of components should be seen as normal operation. Workflows should be designed in such a way that such failures do not lead to complete failure.</cite>

<cite index="76-10,76-11">Graceful degradation is a design philosophy that ensures a system continues functioning – albeit with reduced performance or features – when one or more of its components fail. Rather than completely breaking down, the system "degrades gracefully" by maintaining core functionality.</cite>

### Noctem Degradation Levels

| Level | Condition | Capabilities | User Experience |
|-------|-----------|--------------|-----------------|
| **Full** | LLM + DB healthy | All features | Complete assistance |
| **Degraded** | LLM down, DB up | Fast path only | Basic scoring, no suggestions |
| **Minimal** | LLM down, DB slow | Queue only | Tasks registered, processed later |
| **Offline** | Everything down | Nothing | Telegram error message |

### Implementation Pattern

```python
class GracefulDegradation:
    def __init__(self):
        self.llm_available = True
        self.db_available = True
        self.pending_slow_work = []  # Queue for when LLM returns
    
    def check_health(self):
        """Periodic health check"""
        self.llm_available = self._ping_ollama()
        self.db_available = self._ping_sqlite()
        return self.get_level()
    
    def get_level(self):
        if self.llm_available and self.db_available:
            return 'full'
        elif not self.llm_available and self.db_available:
            return 'degraded'
        elif not self.llm_available and not self.db_available:
            return 'minimal'
        return 'offline'
    
    def execute_with_fallback(self, task_type, task_data):
        """Execute task with appropriate fallback"""
        level = self.get_level()
        
        if task_type == 'score_task':
            if level == 'full':
                return self._llm_score(task_data)
            else:
                # Fallback to rule-based scoring
                return self._smart_code_score(task_data)
        
        if task_type == 'generate_next_step':
            if level == 'full':
                return self._llm_generate(task_data)
            else:
                # Queue for later, return placeholder
                self._queue_for_later('generate_next_step', task_data)
                return {'status': 'queued', 'message': 'Will generate when AI is back'}
        
        # ... other task types
    
    def _smart_code_score(self, task):
        """Rule-based scoring when LLM unavailable"""
        score = 0.5  # Default middle score
        
        # Heuristics
        if '?' in task.name:
            score += 0.1  # Questions benefit from AI
        if any(w in task.name.lower() for w in ['research', 'find', 'look up']):
            score += 0.2
        if any(w in task.name.lower() for w in ['write', 'draft', 'email']):
            score += 0.15
        if task.has_due_date:
            score += 0.05
        if len(task.name.split()) < 3:
            score -= 0.1  # Very short = probably simple
        
        return min(1.0, max(0.0, score))
    
    def _queue_for_later(self, task_type, task_data):
        """Mark work to be done when LLM returns"""
        self.pending_slow_work.append({
            'type': task_type,
            'data': task_data,
            'queued_at': datetime.now()
        })
        # Also persist to DB
        self._save_pending_to_db(task_type, task_data)
    
    def process_pending_when_healthy(self):
        """Called when LLM comes back online"""
        if self.llm_available and self.pending_slow_work:
            for item in self.pending_slow_work:
                self.execute_with_fallback(item['type'], item['data'])
            self.pending_slow_work = []
```

### Database Schema for Pending Work

```sql
CREATE TABLE pending_slow_work (
    id INTEGER PRIMARY KEY,
    task_type TEXT,  -- 'generate_next_step', 'implementation_intention', etc.
    task_id INTEGER,
    task_data JSON,
    queued_at DATETIME,
    processed_at DATETIME,  -- NULL until processed
    status TEXT  -- 'pending', 'processing', 'completed', 'failed'
);

-- Index for quick lookup of pending items
CREATE INDEX idx_pending_status ON pending_slow_work(status, queued_at);
```

---

## Research Area 4: Task Breakdown Storage

### Implementation Intention Schema

Store full breakdowns that can be reviewed and refined:

```sql
CREATE TABLE implementation_intentions (
    id INTEGER PRIMARY KEY,
    task_id INTEGER,
    version INTEGER DEFAULT 1,  -- Track revisions
    
    -- The "when/where/how" breakdown
    when_trigger TEXT,      -- "Saturday morning after coffee"
    where_location TEXT,    -- "Home office"
    how_approach TEXT,      -- "Open TurboTax → Upload W-2 → ..."
    first_action TEXT,      -- "Locate W-2 PDF in email"
    
    -- Metadata
    generated_by TEXT,      -- 'llm' or 'user_edited'
    confidence REAL,        -- AI confidence in this breakdown
    created_at DATETIME,
    updated_at DATETIME,
    
    -- Status
    status TEXT,  -- 'draft', 'approved', 'in_progress', 'completed'
    user_feedback TEXT,  -- User notes on quality
    
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);

-- Store the concrete "next step" separately for quick access
CREATE TABLE next_steps (
    id INTEGER PRIMARY KEY,
    task_id INTEGER,
    intention_id INTEGER,  -- Links to full breakdown
    
    step_text TEXT,        -- "Locate W-2 PDF in email"
    step_order INTEGER,    -- Which step in sequence
    
    status TEXT,  -- 'pending', 'current', 'completed', 'skipped'
    completed_at DATETIME,
    
    FOREIGN KEY (task_id) REFERENCES tasks(id),
    FOREIGN KEY (intention_id) REFERENCES implementation_intentions(id)
);
```

### Full Breakdown Example

For task: "File taxes"

```json
{
  "task_id": 42,
  "version": 1,
  "when_trigger": "Saturday morning after coffee",
  "where_location": "Home office, at desk",
  "how_approach": "1. Gather documents\n2. Open TurboTax\n3. Complete income section\n4. Complete deductions\n5. Review and file",
  "first_action": "Locate W-2 PDF in email from employer",
  "generated_by": "llm",
  "confidence": 0.85,
  "status": "draft"
}
```

Next steps extracted:
```json
[
  {"step_order": 1, "step_text": "Locate W-2 PDF in email from employer", "status": "current"},
  {"step_order": 2, "step_text": "Download and save W-2 to tax folder", "status": "pending"},
  {"step_order": 3, "step_text": "Open TurboTax and start new return", "status": "pending"},
  {"step_order": 4, "step_text": "Enter W-2 information", "status": "pending"},
  {"step_order": 5, "step_text": "Complete deductions section", "status": "pending"}
]
```

### Web Page for Reviewing Breakdowns

The clarification web page should show:

1. **Pending Clarifications** - Questions waiting for user input
2. **Draft Breakdowns** - Implementation intentions to review/approve
3. **In-Progress Tasks** - Current next steps for active tasks

```
┌──────────────────────────────────────────────────────────┐
│  NOCTEM - Task Review                                    │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  📝 PENDING CLARIFICATIONS (2)                          │
│  ├─ "Plan vacation" - Where are you thinking of going?  │
│  └─ "Schedule meeting" - With whom?                     │
│                                                          │
│  📋 DRAFT BREAKDOWNS TO REVIEW (1)                      │
│  └─ "File taxes"                                        │
│      When: Saturday morning after coffee                │
│      Where: Home office                                 │
│      First step: Locate W-2 PDF in email               │
│      [Approve] [Edit] [Regenerate]                      │
│                                                          │
│  ▶️ CURRENT NEXT STEPS (3)                              │
│  ├─ "Buy groceries" → Make shopping list               │
│  ├─ "File taxes" → Locate W-2 PDF                      │
│  └─ "Call mom" → Check calendar for free time          │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

---

## Synthesis: Complete Fast/Slow System Design

### Main Loop with Fast/Slow Integration

```python
class NoctemMainLoop:
    def __init__(self):
        self.degradation = GracefulDegradation()
        self.router = PathRouter()
        self.timing = AdaptiveNotificationTiming()
        self.fast_model = "qwen2.5:1.5b-instruct-q4_K_M"
        self.slow_model = "qwen2.5:7b-instruct-q4_K_M"
    
    def run(self):
        while True:
            # Health check
            level = self.degradation.check_health()
            
            # If LLM just came back, process pending
            if level == 'full' and self.degradation.pending_slow_work:
                self._process_pending_slow_work()
            
            # Check for new work
            tasks = self._get_unprocessed_tasks()
            for task in tasks:
                self._process_task(task, level)
            
            # Check if notification time
            if self._is_notification_time():
                self._send_digest()
            
            time.sleep(30)  # Main loop interval
    
    def _process_task(self, task, level):
        # Fast path: Score the task
        score = self.degradation.execute_with_fallback('score_task', task)
        task.ai_help_score = score
        
        if score > 0.5 and level == 'full':
            # Slow path: Generate implementation intention
            intention = self.degradation.execute_with_fallback(
                'generate_intention', task
            )
            self._save_intention(task, intention)
        elif score > 0.5 and level != 'full':
            # Queue for later
            self.degradation._queue_for_later('generate_intention', task)
```

### Telegram vs Web Page Decision

| Notification Type | Channel | Reason |
|-------------------|---------|--------|
| Morning/evening digest | Telegram | Scheduled, ambient |
| Urgent clarification | Telegram | Needs immediate response |
| Task breakdown review | Web page | Needs thoughtful review |
| Error alert | Telegram | Quick awareness |
| Bulk pending clarifications | Web page | Too many for Telegram |

---

## Next Steps

1. ✅ Phase 1: Lightweight ML, background architecture, recovery patterns
2. ✅ Phase 2: Psychology, local LLMs, ambient UX, clarification skill
3. ✅ Phase 3: Fast/slow architecture, adaptive timing, graceful degradation
4. ⏳ **Implementation Plan**: Specific file changes, database migrations, API design

**Ready for implementation planning when you are.**

---

## References

### Fast/Slow Architecture
- Google DeepMind. "Agents Thinking Fast and Slow: A Talker-Reasoner Architecture" (arXiv, Oct 2024)
- Kahneman, D. (2011). Thinking, Fast and Slow. Penguin Books.
- Cambridge Core. "Design thinking, fast and slow" (Design Science, 2019)

### Adaptive Notification Timing
- Okoshi et al. "Towards attention-aware adaptive notification on smart phones" (ScienceDirect, 2015)
- NSF. "Nurture: Notifying Users at the Right Time Using Reinforcement Learning"
- Yahoo! JAPAN. "Real-world large-scale study on adaptive notification scheduling" (2018)

### Graceful Degradation
- AWS Well-Architected. "Implement graceful degradation" (Reliability Pillar)
- GeeksforGeeks. "Graceful Degradation in Distributed Systems"
- LogRocket. "A guide to graceful degradation in web development"

---

*Research conducted: 2026-02-13*  
*Co-Authored-By: Warp <agent@warp.dev>*
