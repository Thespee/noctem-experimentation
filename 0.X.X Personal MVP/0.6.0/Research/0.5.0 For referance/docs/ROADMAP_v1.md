# Noctem v1.0 - AI Agent Roadmap

Transform Noctem from a rule-based task manager into an intelligent AI-powered executive assistant.

## Vision

**v0.5** (Current): Rule-based task parsing, manual organization
**v1.0** (Target): AI agent that understands context, suggests actions, and helps accomplish goals

Think: Personal Warp/Claude that knows your projects, calendar, and priorities.

## Core Capabilities

### 1. Intelligent Task Understanding

**Current (v0.5):**
```
User: "buy groceries tomorrow"
→ Creates task with due_date=tomorrow
```

**v1.0:**
```
User: "I need to prepare for the client meeting next week"
→ AI: "I see you have a meeting with Acme Corp on Thursday. 
       I'll create tasks for:
       1. Review project status (due: Tuesday)
       2. Prepare slide deck (due: Wednesday)  
       3. Send agenda to team (due: Wednesday)
       Should I add these?"
```

### 2. Proactive Suggestions

The AI monitors your system and suggests actions:

- **Priority conflicts**: "You have 3 high-priority tasks due tomorrow but a full calendar. Want to reschedule the dentist appointment?"
- **Forgotten tasks**: "The 'Finish report' task has been in progress for 2 weeks. Need help breaking it down?"
- **Pattern recognition**: "You usually work on 'Canadian Standard' on weekends. Want me to schedule time this Saturday?"
- **Goal tracking**: "You're 60% through 'Finish School' but graduation is in 3 months. Here's a suggested timeline..."

### 3. Natural Conversation

Full conversational interface, not just commands:

```
User: "What should I focus on today?"
AI: "Based on your calendar and priorities:

     Morning (you have 2 hours free):
     → Finish the white paper draft (high priority, 80% done)
     
     Afternoon (after your 2pm meeting):
     → Review PR for backend project
     → Quick win: Register for dental plan (10 min)
     
     You also have 'Ketamine Night' at 7:15pm - 
     maybe tackle admin tasks before then?"

User: "Actually push the white paper to tomorrow, I'm not feeling it"
AI: "Done. Moved to tomorrow. Want me to block focus time 
     on your calendar for it?"
```

### 4. Task Decomposition

AI breaks down complex tasks:

```
User: "I need to do my taxes"
AI: "I'll help break this down:

     1. Gather documents
        - T4 from employer
        - Investment statements
        - Donation receipts
        - Previous year return
     
     2. Choose filing method
        - SimpleTax (free, you used last year)
        - Accountant (deadline: March 15 for appointment)
     
     3. File and verify
     
     Want me to create these as subtasks with suggested due dates?"
```

## Architecture

### Agent Framework

```
┌─────────────────────────────────────────────┐
│              User Interface                  │
│    (Telegram / Web / CLI / Voice?)          │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│            Agent Controller                  │
│  - Conversation management                   │
│  - Context assembly                          │
│  - Tool orchestration                        │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│              LLM Backend                     │
│  - Claude API / Local LLM                    │
│  - System prompt with persona                │
│  - Tool definitions                          │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│               Tools                          │
│  - task_create, task_update, task_complete  │
│  - calendar_query, calendar_block           │
│  - project_status, goal_progress            │
│  - habit_log, habit_stats                   │
│  - briefing_generate                        │
│  - web_search (optional)                    │
└─────────────────────────────────────────────┘
```

### Context Assembly

Before each LLM call, assemble relevant context:

```python
def build_context():
    return {
        "current_time": datetime.now(),
        "today_calendar": get_todays_events(),
        "overdue_tasks": get_overdue_tasks(),
        "priority_tasks": get_priority_tasks(10),
        "active_projects": get_active_projects_summary(),
        "recent_completions": get_recent_completions(7),
        "habits_today": get_habits_status(),
        "user_patterns": get_user_patterns(),  # When they work, preferences
    }
```

### Tool Definitions

```python
TOOLS = [
    {
        "name": "create_task",
        "description": "Create a new task",
        "parameters": {
            "name": "string, required",
            "due_date": "date, optional",
            "project": "string, optional - project name",
            "importance": "1-3, optional - 1=high, 3=low",
        }
    },
    {
        "name": "update_task",
        "description": "Update an existing task",
        "parameters": {
            "task_id": "int, required",
            "name": "string, optional",
            "due_date": "date, optional",
            "status": "not_started|in_progress|done",
        }
    },
    {
        "name": "query_tasks",
        "description": "Search/filter tasks",
        "parameters": {
            "query": "string - natural language query",
            "project": "string, optional",
            "status": "string, optional",
            "due_before": "date, optional",
        }
    },
    # ... more tools
]
```

## Implementation Phases

### Phase 1: Basic AI Integration

**Goal:** Replace rule-based parser with LLM understanding

1. Add Claude/OpenAI API integration
2. Create system prompt with Noctem context
3. Route all messages through LLM
4. LLM calls existing tools (create_task, etc.)
5. Maintain conversation history

**Complexity:** Medium
**Time:** 1-2 weeks

### Phase 2: Context Awareness

**Goal:** AI understands your full situation

1. Build context assembly system
2. Include calendar, tasks, projects in every prompt
3. Add user preference learning
4. Implement "what should I do" queries

**Complexity:** Medium
**Time:** 2-3 weeks

### Phase 3: Proactive Agent

**Goal:** AI initiates helpful suggestions

1. Background analysis job (hourly)
2. Detect anomalies (overdue, conflicts, stalled)
3. Generate suggestions
4. Send via Telegram at appropriate times
5. User feedback loop (helpful/not helpful)

**Complexity:** High
**Time:** 3-4 weeks

### Phase 4: Advanced Features

**Goal:** Full executive assistant capabilities

1. Task decomposition
2. Calendar optimization
3. Email integration (read/draft)
4. Meeting prep automation
5. Weekly review generation
6. Goal progress tracking with suggestions

**Complexity:** High
**Time:** Ongoing

## Technical Decisions

### LLM Choice

| Option | Pros | Cons |
|--------|------|------|
| **Claude API** | Best reasoning, tool use | Cost, requires internet |
| **GPT-4 API** | Good tool use, fast | Cost, requires internet |
| **Local LLM (Ollama)** | Free, private, offline | Worse reasoning, slower |
| **Hybrid** | Best of both | Complexity |

**Recommendation:** Start with Claude API for development, add local fallback later.

### Conversation Memory

```python
# Short-term: Recent messages
conversation_history = [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."},
]  # Last 10-20 messages

# Long-term: Summarized in DB
user_preferences = {
    "work_hours": "9am-6pm",
    "focus_time_preference": "morning",
    "communication_style": "concise",
}
```

### Cost Management

- Cache common queries
- Use smaller model for simple tasks
- Batch context updates
- Rate limit proactive suggestions
- Track token usage per feature

## System Prompt (Draft)

```
You are Noctem, a personal executive assistant. You help manage tasks, 
projects, goals, and habits for a single user.

Your personality:
- Concise and direct
- Proactive but not annoying
- Remembers context from previous conversations
- Asks clarifying questions when needed

You have access to:
- Tasks, projects, and goals database
- Calendar events
- Habit tracking
- User's timezone and preferences

Current context:
{assembled_context}

When helping:
1. Consider the user's full picture (calendar, priorities, energy)
2. Suggest concrete next actions
3. Respect stated preferences
4. Learn from feedback

Available tools:
{tool_definitions}
```

## Privacy & Security

### Data Handling

- All task/project data stays local
- Only send to LLM API what's needed for current query
- Option to redact sensitive info before API calls
- Local LLM option for full privacy

### API Key Management

```python
# Secure storage
Config.set("anthropic_api_key", key, encrypted=True)

# Environment variable option
ANTHROPIC_API_KEY=xxx python -m noctem.main
```

## Success Metrics

### Quantitative
- Tasks created per day (should increase)
- Task completion rate (should increase)
- Time from task creation to completion (should decrease)
- User messages per session (engagement)

### Qualitative
- "Did the AI suggestion help?" feedback
- Weekly satisfaction check-in
- Feature usage patterns

## Migration Path

### v0.5 → v1.0 Compatibility

- All v0.5 commands still work
- Database schema unchanged (add new tables only)
- Gradual rollout: AI features optional
- Fallback to rule-based if API unavailable

### User Opt-in

```
> enable ai
AI features enabled. Your data will be sent to Claude API 
for processing. Type 'disable ai' to return to basic mode.
```

## Future Ideas (v1.x+)

- **Voice interface** - "Hey Noctem, what's on my plate today?"
- **Multi-user** - Family/team task coordination
- **Integrations** - Slack, Discord, email, calendar write
- **Automation** - "When I complete X, automatically create Y"
- **Learning** - Improve suggestions based on what you actually do
- **Mobile app** - Native iOS/Android with widgets

## Resources

### APIs
- [Anthropic Claude](https://docs.anthropic.com/)
- [OpenAI](https://platform.openai.com/docs)
- [Ollama](https://ollama.ai/) (local)

### Frameworks
- [LangChain](https://python.langchain.com/) - Agent framework
- [Instructor](https://github.com/jxnl/instructor) - Structured outputs
- [Guidance](https://github.com/guidance-ai/guidance) - Constrained generation

### Inspiration
- Warp AI terminal
- GitHub Copilot Workspace
- Notion AI
- Motion (AI calendar)
