# Noctem Setup Summary

*Last updated: 2026-02-08 (evening)*

## What Is Noctem?

A lightweight, portable, self-improving personal AI assistant that runs on any Linux machine. Communicates via Signal, executes tasks autonomously, and learns from interactions.

**Core Principles**: Data sovereignty, operational independence, minimal footprint, self-improvement, transparent operation.

---

## Current State

### Architecture Implemented

```
noctem/
├── main.py              # Entry point, orchestration
├── daemon.py            # LLM-powered task planner (Ollama)
├── signal_receiver.py   # Signal message handling
├── skill_runner.py      # Skill execution engine
├── state.py             # SQLite state management
├── skills/              # Skill modules
│   ├── shell.py         # System commands
│   ├── signal_send.py   # Messaging
│   ├── file_ops.py      # File read/write
│   ├── task_status.py   # Queue management
│   ├── web_fetch.py     # URL fetching ✓ NEW
│   ├── web_search.py    # DuckDuckGo search ✓ NEW
│   └── troubleshoot.py  # Diagnostics ✓ NEW
├── utils/               # Shared utilities ✓ NEW
│   ├── cache.py         # File-based TTL cache
│   ├── robots.py        # Robots.txt compliance
│   └── rate_limit.py    # Per-domain throttling
├── tests/               # Test suite
│   ├── test_web_skills.py
│   └── local/           # Comprehensive local tests ✓ NEW
│       ├── run_all.py       # Master test runner
│       ├── test_utils.py    # Cache, robots, rate_limit
│       ├── test_state.py    # SQLite state management
│       ├── test_shell_skill.py  # Shell + safety tests
│       ├── test_file_ops_skill.py
│       ├── test_skill_runner.py
│       └── ...              # 9 test modules total
├── docs/
│   └── VISION.md        # Full idealized architecture
└── mvp steps/           # Implementation guides
    ├── 01-web-skills.md  ✓ COMPLETE
    ├── 02-birth.md       ◯ NEXT
    ├── 03-parent.md      ◯ PENDING
    └── 04-email.md       ◯ PENDING
```

### Skills Status (8 total)

| Skill | Status | Description |
|-------|--------|-------------|
| `shell` | ✅ Working | Execute system commands |
| `signal_send` | ✅ Working | Send Signal messages |
| `file_read` | ✅ Working | Read files safely |
| `file_write` | ✅ Working | Write files with path protection |
| `task_status` | ✅ Working | Check task queue |
| `web_fetch` | ✅ Working | Fetch URLs, extract text, robots.txt compliant |
| `web_search` | ✅ Working | DuckDuckGo search with rate limiting |
| `troubleshoot` | ✅ Working | Modular diagnostics system |

### Infrastructure Status

| Component | Status | Notes |
|-----------|--------|-------|
| Ollama | ✅ Required | Local LLM inference |
| signal-cli | ✅ Required | Signal messaging |
| SQLite DB | ✅ Working | State persistence |
| Cache system | ✅ Working | File-based with TTL |
| Rate limiter | ✅ Working | Per-domain throttling |
| Robots.txt | ✅ Working | Web crawling compliance |
| Local Test Suite | ✅ Working | 136 tests across 9 modules |

---

## Feature Comparison: Current vs Idealized

### Layer 1: Portable Foundation

| Feature | Idealized | Current | Gap |
|---------|-----------|---------|-----|
| VeraCrypt encrypted container | ✓ | ◯ | Manual setup still needed |
| USB portability | ✓ | ◯ | Works but no auto-mount |
| Hardware key (YubiKey) | ✓ | ◯ | Not implemented |
| Credential vault | ✓ | ◯ | Phase 4 (email) |
| Cross-platform | ✓ | △ | Linux only currently |

**Progress: ~20%** - Foundation exists but encryption/portability features not automated.

### Layer 2: Communication Hub

| Feature | Idealized | Current | Gap |
|---------|-----------|---------|-----|
| Signal messaging | ✓ | ✅ | Working |
| Email (IMAP/SMTP) | ✓ | ◯ | Phase 4 |
| Matrix integration | ✓ | ◯ | Future roadmap |
| Local web UI | ✓ | ◯ | Future roadmap |

**Progress: ~25%** - Signal works. Email in Phase 4. Matrix/Web UI are stretch goals.

### Layer 3: Intelligence Core

| Feature | Idealized | Current | Gap |
|---------|-----------|---------|-----|
| Router model (fast) | ✓ | ◯ | Single model only |
| Worker model (complex) | ✓ | ✅ | Ollama working |
| LoRA adapters | ✓ | ◯ | Not implemented |
| RAG pipeline | ✓ | ◯ | Not implemented |
| Self-improvement | ✓ | ◯ | Phase 3 (parent) |
| Sleep mode training | ✓ | ◯ | Future roadmap |

**Progress: ~15%** - Basic Ollama inference works. No router, RAG, or self-improvement yet.

### Layer 4: Skill Framework

| Skill Category | Idealized | Current | Gap |
|----------------|-----------|---------|-----|
| Core (shell, files, signal) | 4 skills | ✅ 5 skills | Done |
| Research (web_fetch, web_search) | 5 skills | ✅ 2 skills | Scraping, business lookup remaining |
| Communication (email) | 4 skills | ◯ 0 skills | Phase 4 |
| Development (code, git) | 4 skills | ◯ 0 skills | Future |
| Learning (tutor, quiz) | 4 skills | ◯ 0 skills | Future |
| Government (forms, deadlines) | 3 skills | ◯ 0 skills | Future |

**Progress: ~30%** - Core skills working. Web research skills added. Email next.

### Operational Features

| Feature | Idealized | Current | Gap |
|---------|-----------|---------|-----|
| Auto-start on boot | ✓ | ◯ | Phase 2 (birth) |
| Birth process | ✓ | ◯ | Phase 2 |
| Umbilical recovery | ✓ | ◯ | Phase 2 |
| Parent monitoring | ✓ | ◯ | Phase 3 |
| Babysitting reports | ✓ | ◯ | Phase 3 |
| Warp integration | ✓ | ◯ | Phase 3 |

**Progress: ~5%** - All operational features pending in Phases 2-3.

### Security Model

| Feature | Idealized | Current | Gap |
|---------|-----------|---------|-----|
| Command allowlisting | ✓ | △ | Basic blocklist exists |
| Path restrictions | ✓ | ✅ | Working in file_ops |
| Audit logging | ✓ | △ | Basic logging exists |
| Encrypted storage | ✓ | ◯ | Not automated |
| Credential vault | ✓ | ◯ | Phase 4 |
| Human confirmation | ✓ | △ | For some ops only |

**Progress: ~35%** - Basic safety rails exist. Encryption and vault pending.

---

## Overall Progress

```
██████░░░░░░░░░░░░░░ 25% toward idealized vision

Phase 1 (Web Skills):     ████████████████████ 100% ✓
Phase 2 (Birth):          ░░░░░░░░░░░░░░░░░░░░   0%
Phase 3 (Parent):         ░░░░░░░░░░░░░░░░░░░░   0%
Phase 4 (Email):          ░░░░░░░░░░░░░░░░░░░░   0%
```

### What Works Today

1. **Send a Signal message → Noctem responds** via Ollama-powered planning
2. **Execute shell commands** with basic safety checks
3. **Read/write files** with path protection
4. **Fetch any URL** with robots.txt compliance and caching
5. **Search the web** via DuckDuckGo with rate limiting
6. **Run diagnostics** via troubleshoot skill (`troubleshoot all -v`)
7. **Track tasks** in SQLite database

### What's Missing

1. **Autonomous setup** (birth process) - must manually install deps
2. **Error recovery** (umbilical) - no remote help when stuck
3. **Remote monitoring** (parent) - can't check status from elsewhere
4. **Self-improvement** - no learning from interactions yet
5. **Email integration** - can't read/send emails
6. **Encrypted storage** - credentials in plaintext config
7. **Auto-start** - must manually start after reboot

---

## MVP Roadmap

### Week 1 ✅ COMPLETE
- [x] web_fetch skill
- [x] web_search skill
- [x] Cache infrastructure
- [x] Rate limiting
- [x] Robots.txt compliance
- [x] Troubleshoot skill

### Week 2 (Next)
- [ ] Birth state machine
- [ ] Signal progress notifications
- [ ] Dependency checking
- [ ] `/umb` umbilical commands
- [ ] systemd auto-start

### Week 3
- [ ] Parent protocol
- [ ] Remote status checks
- [ ] History retrieval
- [ ] Warp CLI integration
- [ ] Babysitting reports

### Week 4
- [ ] Credential vault
- [ ] IMAP email fetching
- [ ] Email summarization
- [ ] SMTP sending with approval
- [ ] Daily digest

---

## Quick Start

```bash
# 1. Install dependencies
pip install requests beautifulsoup4 duckduckgo-search

# 2. Ensure Ollama is running with a model
ollama run llama3.2

# 3. Configure signal-cli (see signal-cli docs)

# 4. Start Noctem
python3 main.py

# 5. Test diagnostics
python3 skills/troubleshoot.py all -v
```

---

## Test Results (2026-02-08)

### Local Test Suite (136 tests)

```
$ python3 tests/local/run_all.py
🌙 Noctem Local Test Suite

Module Results:
  ✅ utils: 12/12          # Cache, robots.txt, rate limiting
  ✅ base_skill: 11/11     # Skill framework and registry
  ✅ state: 23/23          # SQLite state management
  ✅ skill_runner: 16/16   # Skill execution and chaining
  ✅ shell_skill: 23/23    # Shell commands + safety (18 blacklist tests)
  ✅ file_ops_skill: 18/18 # File read/write + path protection
  ✅ task_status_skill: 7/7
  ✅ signal_send_skill: 9/9 # Mock-based validation
  ✅ web_skills: 17/17     # Network-dependent

Total: 136 passed, 0 failed
Duration: ~30s

✅ ALL TESTS PASSED
```

### Test Runner Commands

```bash
# Run all tests
python3 tests/local/run_all.py

# Verbose output
python3 tests/local/run_all.py -v

# Run single module
python3 tests/local/run_all.py --module shell_skill

# Run single test (for troubleshooting)
python3 tests/local/run_all.py --test shell_skill.dangerous_rm_rf_root

# List available tests
python3 tests/local/run_all.py --list
```

### Troubleshoot Skill

```
$ python3 skills/troubleshoot.py all
✓ dns_resolution: DNS resolution working
✓ network_connectivity: Network connectivity working
✓ https_connectivity: HTTPS connectivity working
✓ cache_directory: Cache directory exists
✓ cache_permissions: Cache directory is writable
✓ dependencies: All required packages installed
✓ skill_registration: Both web_fetch and web_search skills registered
✓ skills_loaded: 8 skills loaded
✓ skill_runner: Skill runner operational
✓ shell_skill_test: Shell skill working

Overall Status: OK
```

---

## References

- `docs/VISION.md` - Full idealized architecture
- `mvp steps/01-web-skills.md` - Phase 1 implementation guide
- `mvp steps/02-birth.md` - Phase 2 implementation guide
- `mvp steps/03-parent.md` - Phase 3 implementation guide
- `mvp steps/04-email.md` - Phase 4 implementation guide

---

## Addendum: Session Insights (2026-02-08 Evening)

### What Was Built

A comprehensive **local test suite** (`tests/local/`) covering all implemented functionality:

| Module | Tests | Key Coverage |
|--------|-------|-------------|
| `test_utils` | 12 | Cache TTL, robots.txt parsing, rate limiting |
| `test_base_skill` | 11 | SkillResult, SkillContext, registry, validation |
| `test_state` | 23 | All SQLite ops: tasks, memory, skill_log, boot |
| `test_skill_runner` | 16 | Single skill, chaining, context passing, failures |
| `test_shell_skill` | 23 | Commands + **18 safety/blacklist tests** |
| `test_file_ops_skill` | 18 | Read/write, protected paths, user expansion |
| `test_task_status_skill` | 7 | Queue status, recent tasks |
| `test_signal_send_skill` | 9 | Validation only (mock-based, no daemon needed) |
| `test_web_skills` | 17 | Fetch, search, caching (network required) |

### Design Decisions

1. **Troubleshooting-First Tests**: Each test function returns `{"status": "pass", "message": "..."}` for integration with future troubleshooting sub-skills.

2. **Programmatic Access**: `run_all.py` exports `get_test_manifest()` and `run_single_test()` for automated troubleshooting.

3. **Mock-Based Signal Tests**: Test validation logic without requiring signal-cli daemon.

4. **Safety Test Coverage**: 18 dedicated tests for shell blacklist (rm -rf, fork bombs, curl|bash, etc.).

---

## Addendum: Alignment Speculations

### Gap: Tests ↔ Troubleshooting

**Current**: Tests exist separately from the `troubleshoot.py` skill.

**Ideal**: The troubleshoot skill should *run* these tests as sub-checks. The test suite already exports the right interface (`run_single_test`, `get_test_manifest`).

**Quick Win**: Add a `troubleshoot tests` command that runs `tests/local/run_all.py` and reports failures as diagnostics.

### Gap: No Test-Driven Birth Process

**Current**: Phase 2 birth will manually check dependencies.

**Ideal**: Birth should run the test suite as validation. If `test_state.test_database_connection` passes, DB is working. If `test_shell_skill.test_shell_echo` passes, shell is working.

**Speculation**: Birth state machine could use test results as gates:
```
CHECK_DEPS → run test_utils, test_state
CONFIG_SIGNAL → run test_signal_send_skill
TEST_SKILLS → run full suite
```

### Gap: Cache Key Doesn't Include All Params

**Observed**: `web_fetch` cache key is `{url}:{selector}` but not `max_length`. This caused test flakiness.

**Quick Fix**: Either include `max_length` in cache key, or document that cached results use original fetch params.

### Gap: Model Routing Not Implemented

**Current**: Single model for everything (config `model` field).

**Ideal**: `router_model` (1.5b) for quick chat, `model` (7b) for complex tasks.

**Quick Win**: ~30 lines in `daemon.py` to check message length/complexity and select model. The config already has both fields.

---

*Built with assistance from Warp Agent*
