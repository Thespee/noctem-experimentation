# AGENTS.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## What is Noctem

A lightweight agentic AI assistant framework for low-spec hardware. Uses Ollama for local LLM inference and Signal for messaging.

## Commands

```bash
# Start interactive mode
python3 main.py

# Start headless/daemon mode (for systemd)
python3 main.py --headless

# Quick chat (no queue)
python3 main.py -c "message"

# Queue a task
python3 main.py -t "task description"

# Run tests
python3 tests/test_web_skills.py
```

### Signal Integration (on deployment server)

```bash
# Start signal-cli daemon first
signal-cli -a YOUR_PHONE daemon --tcp 127.0.0.1:7583

# Then start Noctem
python3 main.py
```

## Architecture

```
main.py          → Entry point, CLI interface, service orchestration
    ↓
daemon.py        → Background task processor, LLM orchestration via Ollama HTTP API
    ↓
skill_runner.py  → Executes skills with context, supports skill chaining
    ↓
skills/          → Plugin system (each skill extends skills/base.py:Skill)
    ↓
state.py         → SQLite persistence (tasks, memory, skill logs)

signal_receiver.py → Parallel: listens for Signal messages via JSON-RPC
```

### Message Flow

1. Message arrives (CLI or Signal)
2. `SignalReceiver.is_quick_chat()` routes based on length and action words
3. **Quick chat**: Fast 1.5b model responds immediately
4. **Task**: Queued in SQLite, processed by daemon with 7b model
5. Daemon calls `plan_task()` → LLM returns JSON with skills to execute
6. `skill_runner.run_skill_chain()` executes the plan
7. Response sent back via Signal or CLI

### Skill System

Skills are registered via decorator in `skills/base.py`:

```python
@register_skill
class MySkill(Skill):
    name = "my_skill"
    description = "What it does"
    parameters = {"param": "description"}
    
    def run(self, params, context) -> SkillResult:
        # Implementation
        return SkillResult(success=True, output="result")
```

New skills must be imported in `skills/__init__.py` to be registered.

### State/Persistence

All state is in `data/noctem.db` (SQLite). Key tables:
- `tasks` - Task queue with priority, status, plan, result
- `memory` - Conversation history
- `skill_log` - Execution audit trail
- `state` - Key-value store for system state

### Configuration

`data/config.json` contains:
- `signal_phone` - Phone number for Signal
- `model` - Main LLM model (default: qwen2.5:7b)
- `router_model` - Fast model for quick chat (default: qwen2.5:1.5b)
- `quick_chat_max_length` - Threshold for routing

## Key Patterns

- **Singleton services**: `get_daemon()`, `get_receiver()` return global instances
- **LLM calls**: Always via `daemon.call_llm()` using Ollama HTTP API (not subprocess)
- **Skill context**: Skills receive `SkillContext` with task info, previous outputs, memory, config
- **Skill chaining**: Previous skill's `output` and `data` flow to next skill

## Dependencies

Python 3.8+ with standard library only (no pip packages required). External services:
- Ollama (localhost:11434) for LLM inference
- signal-cli daemon (localhost:7583) for Signal messaging
