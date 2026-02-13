# 🌙 Noctem - Comprehensive Project Report

**Generated:** 2026-02-11

## Executive Summary

**Noctem** is a lightweight, portable, agentic AI assistant framework designed to run on low-spec hardware. It's built around the concept of a **personal AI operating layer** that lives on encrypted portable storage (USB flash drive), uses local LLM inference via Ollama, and communicates primarily through Signal messaging.

The project is currently in **MVP development phase** on a Windows workstation, with plans to deploy to a bootable Linux USB for autonomous operation.

---

## Project Vision & Philosophy

### Core Principles
1. **Data Sovereignty** - User controls all data; encrypted and portable
2. **Operational Independence** - Works offline; connectivity is optional
3. **Minimal Footprint** - Targets 8GB RAM, runs on consumer hardware
4. **Self-Improvement** - Learns from interactions (bounded personalization)
5. **Transparent Operation** - Full audit logging of all actions

### Lifecycle Model
1. **MVP** (Current) - Core skills and infrastructure development on Windows
2. **Birth** - Deploy to encrypted USB flash drive, autonomous first-time setup
3. **Parent** - Multiple AI agents supervise and improve Noctem remotely

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                        Noctem                           │
├──────────────┬──────────────┬───────────────────────────┤
│  main.py     │  daemon.py   │  signal_receiver.py       │
│  (entry)     │  (LLM loop)  │  (Signal listener)        │
├──────────────┴──────────────┴───────────────────────────┤
│  skill_runner.py                                        │
│  (loads & executes skills)                              │
├─────────────────────────────────────────────────────────┤
│  skills/                                                │
│  ├── shell.py, file_ops.py, signal_send.py             │
│  ├── web_fetch.py, web_search.py                       │
│  ├── email_send.py, email_fetch.py                     │
│  ├── task_manager.py, troubleshoot.py                  │
│  └── daily_report.py                                    │
├─────────────────────────────────────────────────────────┤
│  state.py (SQLite persistence)                          │
└─────────────────────────────────────────────────────────┘
```

### Core Components

| File | Purpose | Lines |
|------|---------|-------|
| `main.py` | Entry point, CLI, service orchestration | ~330 |
| `daemon.py` | Background task processor, LLM orchestration | ~275 |
| `signal_receiver.py` | Signal messaging listener via JSON-RPC | ~580 |
| `skill_runner.py` | Skill loading and chained execution | ~155 |
| `state.py` | SQLite persistence layer | ~1050 |

---

## Database Schema

The SQLite database (`data/noctem.db`) manages:

| Table | Purpose |
|-------|---------|
| `state` | Key-value store for system state |
| `tasks` | Task queue (priority, status, plan, result) |
| `memory` | Conversation history |
| `skill_log` | Execution audit trail |
| `improvements` | Parent-suggested code changes |
| `reports` | Training data (problem→solution pairs) |
| `incidents` | Error/issue logging |
| `daily_reports` | Daily summary tracking |
| `goals` / `projects` / `user_tasks` | Personal task management hierarchy |
| `message_log` | NLP training data |

---

## Skill System

### Available Skills (13 total)

| Skill | Description |
|-------|-------------|
| `shell` | Execute shell commands with safety blacklist |
| `file_ops` | Read/write files with path protection |
| `signal_send` | Send Signal messages via daemon |
| `task_status` | Query task queue |
| `task_manager` | Personal task CRUD operations |
| `web_fetch` | URL retrieval, HTML→text |
| `web_search` | DuckDuckGo integration |
| `email_send` | SMTP email sending |
| `email_fetch` | IMAP inbox scanning |
| `daily_report` | Generate/send daily status |
| `troubleshoot` | System diagnostics |

### Skill Architecture

Skills extend a base `Skill` class and register via decorator:

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

Skills receive a `SkillContext` with task info, previous outputs, memory, and config.

---

## Message Flow

1. **Message arrives** (CLI or Signal)
2. **Routing decision** via `is_quick_chat()` based on length and action words
3. **Quick chat** → Fast 1.5B model (`qwen2.5:1.5b-instruct-q4_K_M`) responds immediately
4. **Task** → Queued in SQLite, processed by daemon with 7B model
5. **Planning** → `plan_task()` asks LLM to return JSON with skills to execute
6. **Execution** → `skill_runner.run_skill_chain()` executes the plan
7. **Response** → Sent back via Signal or CLI

---

## Configuration

`data/config.json`:
```json
{
  "signal_phone": "+15551234567",
  "model": "qwen2.5:7b-instruct-q4_K_M",
  "router_model": "qwen2.5:1.5b-instruct-q4_K_M",
  "quick_chat_max_length": 50,
  "boot_notification": true,
  "dangerous_commands": ["rm -rf /", "mkfs", "dd if=", ...]
}
```

---

## Directory Structure

| Directory | Contents |
|-----------|----------|
| `skills/` | 13 skill modules (shell, email, web, tasks, etc.) |
| `utils/` | Helper modules (vault, cache, calendar, rate limiting) |
| `scripts/` | Deployment scripts, systemd services, cron setup |
| `tests/` | Test files for email, parent, and web skills |
| `docs/` | Vision docs, synthesis reports, setup guides, research PDFs |
| `data/` | SQLite database, config files |
| `research/` | Academic papers and research notes (CRDTs, VMs, etc.) |
| `parent/` | Parent agent supervision system (compiled .pyc only) |

---

## Signal Commands

| Command | Function |
|---------|----------|
| `/ping` | Connectivity test (returns "pong") |
| `/status` | System status |
| `/queue` | Show task queue |
| `/cancel <id>` | Cancel pending task |
| `/priority <id> <1-10>` | Change task priority |
| `/tasks` | List personal tasks |
| `/add <title>` | Add personal task |
| `/done <id>` | Complete personal task |
| `/morning` | Morning briefing |
| `/report` | Generate daily report |
| `/email status/test/check/report` | Email operations |
| `/parent <subcommand>` | Parent agent commands |

---

## Dependencies

**Required (stdlib only):**
- Python 3.8+
- SQLite (built-in)

**External Services:**
- **Ollama** (localhost:11434) - Local LLM inference
- **signal-cli** (localhost:7583) - Signal messaging daemon

**Optional:**
- BeautifulSoup (`bs4`) for web_fetch
- `requests` for web_search

---

## Security Model

### Safety Features
- **Command blacklist** for dangerous shell operations (rm -rf, mkfs, dd, fork bombs)
- **Path protection** for file operations
- **Sender verification** for Signal messages
- **Audit logging** of all skill executions
- **Encrypted vault** for credentials (`utils/vault.py`)
- **Human-in-loop checkpoints** for dangerous operations

### Threat Mitigation (from Research)
- Container encryption (VeraCrypt)
- Hardware key support planned
- Sandboxed skill execution planned (Firecracker MicroVMs)
- Supply chain protection (no open skill marketplace)

---

## Research Foundation

The project is backed by significant academic research documented in `RESEARCH_REPORT.md`:

| Pillar | Technology | Status |
|--------|------------|--------|
| **Distributed Identity** | SSI + CRDTs | Planned |
| **Secure Execution** | Firecracker MicroVMs | Planned |
| **Self-Improvement** | QLoRA fine-tuning on 8GB VRAM | Researched |
| **Competency Sharing** | LoRA composition/model merging | Researched |

**Key Research Finding:** True recursive self-improvement via self-generated data leads to model collapse. Bounded personalization through LoRA fine-tuning is the viable path.

---

## Competitive Analysis (vs OpenClaw)

Noctem explicitly avoids OpenClaw's failures:

| Issue | OpenClaw | Noctem Approach |
|-------|----------|-----------------|
| Security | "Dumpster fire" (341 malicious skills) | Curated/local skills only |
| Credentials | Plaintext exposure | Encrypted vault |
| Cost | Unpredictable API bills | Local Ollama inference |
| Runtime | Node.js (heavy) | Python (lighter) |
| Portability | Mac-centric | Any Linux box + USB |

---

## Open Questions / Clarifications Needed

1. **Parent System**: Only compiled `.pyc` files exist in `parent/`. Are the source files intentionally excluded, or is this an oversight?

2. **Deployment Target**: The docs mention "1TB flash drive bootable Linux" — is there a specific distro/image planned?

3. **Email Configuration**: The vault system exists but `email_config.template.json` suggests manual setup. Is there a planned setup wizard?

4. **Warp Integration**: `config.json` has `warp_api_key` — is Warp agent delegation a planned skill?

5. **Test Coverage**: Only 3 test files exist. Is there a testing strategy for the core components?

6. **Scripts Status**: `scripts/` contains setup scripts — have these been tested on the target deployment environment?

---

## Summary

Noctem is an ambitious, well-researched personal AI assistant framework with:
- ✅ Clean architecture (skills, state, daemon separation)
- ✅ Comprehensive persistence (SQLite with 11 tables)
- ✅ Strong security philosophy (but not yet fully implemented)
- ✅ Multiple communication channels (Signal, email, CLI)
- ✅ Academic research backing for future features
- ⚠️ Missing: Parent module sources, comprehensive tests, deployment validation

The project is clearly in active MVP development, with a solid foundation for the planned "Birth" and "Parent" phases.

---

*Report generated with assistance from Warp Agent*
