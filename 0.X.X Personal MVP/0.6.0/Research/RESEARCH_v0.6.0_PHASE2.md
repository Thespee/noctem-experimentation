# Noctem v0.6.0 Research Report - Phase 2
## Ambient AI Assistant: Psychology, Local LLMs & Human-in-the-Loop

**Date**: 2026-02-13  
**Status**: Phase 2 Complete  
**Focus**: Making AI assistance feel helpful, not nagging; running locally on limited hardware

---

## Executive Summary

Phase 2 research addresses the gaps from Phase 1:
1. **Psychology of habit formation** — How to make AI assistance effective without overwhelming users
2. **Lightweight local LLMs** — Specific model recommendations for CPU-only inference
3. **Ambient computing principles** — How to design "invisible" background assistance
4. **Clarification/HITL patterns** — When and how the AI should ask humans for input

**Key Insight**: The most effective AI assistants are *ambient* (work in background without demanding attention) and *collaborative* (know when to ask for help vs. act autonomously).

---

## Research Area 1: Psychology of Habit Formation

### Implementation Intentions (Gollwitzer, 1997-present)

**Core Concept**: "If-then" plans that specify *when*, *where*, and *how* to act.

> "Implementation intentions delegate the control of goal-directed responses to anticipated situational cues, which (when actually encountered) elicit these responses automatically."

**Key Findings**:
- Difficult goals completed **3x more often** when paired with implementation intentions
- Effect sizes are **medium-to-large** across health, exercise, and work domains
- The strategy works by "passing control of behavior to the environment" — from conscious effort to automatic triggers

**Why This Matters for Noctem**:
- When generating "what should I do next" suggestions, frame them as implementation intentions:
  - ❌ Bad: "Work on taxes"
  - ✅ Good: "When you finish dinner, open TurboTax and complete the income section"
- The AI should help create **situation-response links**, not just remind about tasks

**Application to v0.6.0**:
```
Task: "File taxes"
AI-Generated Implementation Intention:
  "When: Saturday morning after coffee"
  "Where: Home office"
  "How: Open TurboTax → Upload W-2 → Complete income section"
  "First action: Locate W-2 PDF in email"
```

### When Implementation Intentions Don't Work

- **Repeated behaviors with established habits** — prompts have smaller effect when routines already exist
- **Low motivation** — implementation intentions depend on goal commitment
- **Fleeting opportunities** — work best when action window is limited (creates urgency)

**Design Implication**: Noctem should detect if a task is already habitual (recurrence, completion history) and skip redundant suggestions.

---

## Research Area 2: Notification Fatigue & Ambient UX

### The Problem

- **64%** of users delete apps that send 5+ notifications per week
- **40%** productivity loss from task switching to handle notifications
- Takes **30 minutes** to return to deep focus after interruption

### Solutions from Industry

**1. Just-in-Time Notifications (Uber Model)**
- Early Uber: too many generic promos → uninstalls
- Fixed: "Your driver is 2 min away" — actionable, timely, relevant
- **Noctem Application**: Only notify when action is possible *right now*

**2. Batched Digests (Apple iOS 15+)**
- Non-urgent alerts bundled into twice-daily summaries
- Urgent messages bypass the filter
- **Noctem Application**: Morning and evening Telegram updates (already planned ✓)

**3. User Control**
- 61% continue using apps that respect notification preferences
- Let users set frequency, channels, and types of alerts
- **Noctem Application**: `/settings` command to configure notification level

### Ambient Computing Principles

**Mark Weiser (1991)**: "The most profound technologies are those that disappear."

**Characteristics of Ambient AI**:
| Property | Description | Noctem Implementation |
|----------|-------------|----------------------|
| Context-aware | Knows who you are, what you're doing | Use task metadata + time of day |
| Proactive | Acts without explicit prompts | Background loop evaluates tasks |
| Non-intrusive | Works silently, minimal interruption | Telegram updates only at configured times |
| Adaptive | Learns patterns over time | Track task completion patterns |
| Transparent | User understands what it's doing | Show reasoning in suggestions |

**Key Design Principle**: 
> "Technology should create calm — inform but not demand focus or attention."

**Noctem Ambient Loop**:
```
Every 30 seconds:
  - Check task list for changes
  - Check if any AI work is pending
  - If something changed AND it's notification time → notify
  - If something changed AND not notification time → queue for digest
  - Otherwise → do nothing, stay invisible
```

---

## Research Area 3: Lightweight Local LLMs

### Hardware Constraints

Your setup (from experimentation README): Ollama with qwen2.5:7b and qwen2.5:1.5b

**CPU-Only Recommendations (2025/2026 Benchmarks)**:

| Model | Params | RAM Needed | Speed (CPU) | Best For |
|-------|--------|------------|-------------|----------|
| **qwen2.5:1.5b** | 1.5B | 4GB | 30-50 tok/s | Fast routing, simple tasks |
| **phi-3-mini** | 3.8B | 6GB | 20-40 tok/s | GPT-3 quality, tiny footprint |
| **qwen2.5:3b** | 3B | 6GB | 25-35 tok/s | Better quality than 1.5b |
| **llama3.2:3b** | 3B | 6GB | 25-35 tok/s | Good instruction following |
| **qwen2.5:7b** | 7B | 8GB | 15-25 tok/s | Best quality for local |
| **SmolLM2** | 1.7B | 4GB | 40-60 tok/s | Beats qwen2.5-1.5b in accuracy |

**Recommendations for Noctem v0.6.0**:

1. **Router (fast, runs often)**: `qwen2.5:1.5b-instruct-q4_K_M`
   - Decides: Is this task AI-helpable? What type of task?
   - Speed priority over quality

2. **Task Analyzer (quality, runs less)**: `qwen2.5:7b-instruct-q4_K_M` or `phi-3-mini`
   - Generates: "What should I do next?" suggestions
   - Quality priority

3. **Recovery/Error Handler**: Same as router (fast response needed)

**Quantization Tip**: 
> "A 4-bit quantized 7B model often performs better than an 8-bit 3B model"

Use `q4_K_M` quantization for best speed/quality tradeoff.

### Model Selection for Specific Tasks

| Task | Model | Why |
|------|-------|-----|
| "Could AI help?" scoring | qwen2.5:1.5b OR scikit-learn | Speed matters, simple classification |
| "What's the next step?" | qwen2.5:7b | Needs reasoning about task context |
| Generate external prompts | qwen2.5:7b | Needs to write clear instructions |
| Ask clarifying questions | qwen2.5:1.5b | Simple templated questions |
| Summarize task status | qwen2.5:1.5b | Straightforward aggregation |

---

## Research Area 4: Human-in-the-Loop / Clarification Skill

### When AI Should Ask Humans

**Core Design Question**: 
> "Would I be OK if the agent did this without asking me?"

**Patterns from Research**:

1. **Confidence Threshold**
   - If model confidence < 0.8 → escalate to human
   - Log how often humans override → tune threshold over time

2. **Human as a Tool**
   - Agent treats "ask_human" as just another callable skill
   - When stuck or uncertain → route question to human, wait for response

3. **Granularity is a Virtue**
   - Don't just have a "big red button" (approve/reject all)
   - Break tasks into steps, ask about specific ambiguous parts

### Claude's Clarification Pattern (Highlighted as Best Practice)

Claude AI frequently asks clarifying questions like:
- "Just to make sure I understand..."
- "Before I proceed, could you clarify..."
- "There are a few ways to interpret this..."

This **reinforces user control** — the AI acts as "thoughtful collaborator" not "assertive executor."

### Noctem Clarification Skill Design

**When to Ask**:
| Situation | Ask? | Example |
|-----------|------|---------|
| Task is vague | Yes | "Research topic X" → "What specific aspect of X?" |
| Multiple interpretations | Yes | "Schedule meeting" → "With whom? What times work?" |
| High-impact action | Yes | "Delete files" → "Confirm: delete these 5 files?" |
| Routine, clear task | No | "Remind me at 5pm" → just do it |
| Low-confidence score | Yes | "I'm not sure how to help with this. Could you clarify?" |

**Skill Implementation**:
```python
class ClarificationSkill:
    def should_ask(self, task, confidence):
        if confidence < 0.7:
            return True
        if task.has_ambiguous_terms():
            return True
        if task.is_high_impact():
            return True
        return False
    
    def generate_question(self, task, ambiguity_type):
        templates = {
            "vague_goal": "What specific outcome do you want for '{task}'?",
            "missing_context": "To help with '{task}', I need to know: {missing_info}",
            "multiple_approaches": "I see {n} ways to approach '{task}'. Which sounds right?",
            "confirm_action": "Before I {action}, can you confirm this is correct?",
        }
        return templates[ambiguity_type].format(...)
```

**Telegram Integration**:
```
Noctem: I'm looking at "Plan vacation" but need some context:
  - Where are you thinking of going?
  - Roughly when?
  - Solo or with others?

[Reply with answers or "skip" to figure it out later]
```

### Anti-Patterns to Avoid

1. **Asking too often** — becomes annoying, defeats ambient goal
2. **Vague questions** — "Can you tell me more?" is useless
3. **Blocking on non-critical info** — progress should be possible without perfect info
4. **No way to skip** — always allow "figure it out" or "ask me later"

---

## Synthesis: Design Principles for v0.6.0

### 1. Ambient First
- Work silently in background
- Batch notifications to morning/evening
- Only interrupt for time-sensitive or high-confidence suggestions

### 2. Implementation Intentions
- Frame suggestions as "when X, do Y at Z"
- Include first concrete action
- Link to situational triggers (time, location, context)

### 3. Smart Clarification
- Ask only when genuinely uncertain (confidence < 0.7)
- Ask specific questions with options
- Always allow skipping/deferring

### 4. Lightweight Compute
- Use 1.5B model for routing/classification
- Use 7B model for quality suggestions
- Prefer scikit-learn for simple scoring (instant, no GPU)

### 5. Human Control
- Never take irreversible actions without confirmation
- Show reasoning for suggestions
- Let user adjust AI aggressiveness via settings

---

## Proposed Skill: `ask_clarification`

**Purpose**: When the AI needs human input to proceed effectively.

**Triggers**:
- Task description is under 5 words with no context
- Task contains question words ("how", "what", "should")
- AI confidence for next step < 0.7
- Multiple equally-valid approaches exist

**Output Format** (via Telegram):
```
🤔 Quick question about: [Task Name]

[Specific question]

Options:
1. [Option A]
2. [Option B]
3. Tell me more: [free text]
4. Skip for now

Reply with 1, 2, 3, or 4
```

**Database Schema Addition**:
```sql
CREATE TABLE clarification_requests (
    id INTEGER PRIMARY KEY,
    task_id INTEGER,
    question TEXT,
    options JSON,
    status TEXT,  -- 'pending', 'answered', 'skipped'
    response TEXT,
    created_at DATETIME,
    responded_at DATETIME
);
```

---

## Next Steps

1. ✅ Phase 1: Lightweight ML, background architecture, recovery patterns
2. ✅ Phase 2: Psychology, local LLMs, ambient UX, clarification skill
3. ⏳ **Phase 3**: Create implementation plan with specific file changes
4. ⏳ **Phase 4**: Build v0.6.0

**Ready for user feedback on research before creating implementation plan.**

---

## References

### Psychology
- Gollwitzer, P.M. (1999). Implementation Intentions: Strong Effects of Simple Plans. *American Psychologist*
- Gollwitzer & Brandstatter (1997). Implementation Intentions and Effective Goal Pursuit
- Trenz et al. (2024). Promoting new habits at work through implementation intentions. *J. Occupational Psychology*

### Notification/UX
- MagicBell. Help Your Users Avoid Notification Fatigue
- LogRocket. Why Users Ignore Notifications
- NinjaOne. What Is Alert Fatigue & How to Combat It

### Ambient Computing
- Weiser, M. (1991). The Computer for the 21st Century. *Scientific American*
- DigitalOcean. Ambient Agents: The Next Frontier in Context-Aware AI
- Wikipedia. Ambient Intelligence

### Local LLMs
- Skywork AI. Ollama Models List 2025: 100+ Models Compared
- Kolosal AI. Top 5 Best LLM Models to Run Locally in CPU (2025)
- Collabnix. Best Ollama Models 2025: Performance Comparison Guide

### Human-in-the-Loop
- Stanford HAI. Humans in the Loop: The Design of Interactive AI Systems
- WorkOS. Why AI Still Needs You: Exploring Human-in-the-Loop Systems
- Permit.io. Human-in-the-Loop for AI Agents: Best Practices

---

*Research conducted: 2026-02-13*  
*Co-Authored-By: Warp <agent@warp.dev>*
