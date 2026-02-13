# Noctem Setup Summary

*Last updated: 2026-02-08 (night) — Phase 2 Complete*

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
├── birth/               # Phase 2: Autonomous setup ✓ NEW
│   ├── run.py           # Entry point
│   ├── state.py         # BirthStage enum, persistence
│   ├── notify.py        # Signal notifications
│   ├── umbilical.py     # /umb commands, reverse SSH
│   ├── stages/          # 10 modular stages
│   │   ├── s01_detect.py    # OS/hardware detection
│   │   ├── s02_network.py   # Connectivity tests
│   │   ├── s03_system_deps.py  # apt packages
│   │   ├── s04_python_deps.py  # pip packages
│   │   ├── s05_ollama.py    # Install + pull models
│   │   ├── s06_signal_cli.py   # Download/install
│   │   ├── s07_noctem_init.py  # Config + DB init
│   │   ├── s08_test_skills.py  # Skill validation
│   │   ├── s09_autostart.py    # systemd setup
│   │   └── s10_cleanup.py      # Finalization
│   └── templates/       # systemd service files
├── tests/               # Test suite
│   ├── test_web_skills.py
│   └── local/           # Comprehensive local tests
│       ├── run_all.py       # Master test runner
│       ├── test_birth.py    # Birth process tests ✓ NEW
│       └── ...              # 10 test modules total
├── docs/
│   ├── VISION.md        # Full idealized architecture
│   └── USB_SETUP.md     # Beginner USB creation guide ✓ NEW
└── mvp steps/           # Implementation guides
    ├── 01-web-skills.md  ✓ COMPLETE
    ├── 02-birth.md       ✓ COMPLETE
    ├── 03-parent.md      ◯ IN PROGRESS (parallel)
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

|| Feature | Idealized | Current | Gap |
||---------|-----------|---------|-----|
|| Auto-start on boot | ✓ | ✅ | systemd services created |
|| Birth process | ✓ | ✅ | 10-stage state machine |
|| Umbilical recovery | ✓ | ✅ | /umb commands + reverse SSH |
|| Parent monitoring | ✓ | ◯ | Phase 3 |
|| Babysitting reports | ✓ | ◯ | Phase 3 |
|| Warp integration | ✓ | ◯ | Phase 3 |

**Progress: ~55%** - Birth complete. Parent features pending in Phase 3.

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
██████████████░░░░░░ 70% toward idealized vision

Phase 1 (Web Skills):     ████████████████████ 100% ✓
Phase 2 (Birth):          ████████████████████ 100% ✓
Phase 3 (Parent):         ████████████████████ 100% ✓
Phase 4 (Email):          ████████████████████ 100% ✓
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

1. ~~**Autonomous setup** (birth process)~~ ✓ Complete
2. ~~**Error recovery** (umbilical)~~ ✓ Complete
3. **Remote monitoring** (parent) - can't check status from elsewhere
4. **Self-improvement** - no learning from interactions yet
5. **Email integration** - can't read/send emails
6. **Encrypted storage** - credentials in plaintext config
7. ~~**Auto-start**~~ ✓ systemd services ready

---

## MVP Roadmap

### Week 1 ✅ COMPLETE
- [x] web_fetch skill
- [x] web_search skill
- [x] Cache infrastructure
- [x] Rate limiting
- [x] Robots.txt compliance
- [x] Troubleshoot skill

### Week 2 ✅ COMPLETE
- [x] Birth state machine (10 stages with checkpoint/resume)
- [x] Signal progress notifications
- [x] Dependency checking (system + Python)
- [x] `/umb` umbilical commands (reverse SSH tunnel)
- [x] systemd auto-start (noctem.service + noctem-birth.service)
- [x] USB setup documentation for beginners

### Week 3 (In Progress - Parallel Agent)
- [ ] Parent protocol
- [ ] Remote status checks
- [ ] History retrieval
- [ ] Warp CLI integration
- [ ] Babysitting reports

### Week 4 ✅ COMPLETE
- [x] Credential vault (`utils/vault.py` - env vars, encrypted file, JSON backends)
- [x] IMAP email fetching (`skills/email_fetch.py`)
- [x] SMTP sending (`skills/email_send.py`)
- [x] Daily digest (`skills/daily_report.py`)
- [x] Signal commands (`/email`, `/report`)
- [x] Birth integration (stage s06_email)

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

## Addendum: Parent Feature Session (2026-02-08 Night)

### Session Summary

Implemented complete **Phase 3 (Parent)** from `mvp steps/03-parent.md`:

**New Files Created:**
- `parent/__init__.py` - Module exports
- `parent/protocol.py` - `ParentCommand` enum, `ParentRequest`/`ParentResponse` dataclasses
- `parent/child_handler.py` - Handles `/parent` commands on child side
- `parent/cli.py` - Parent CLI (`parent status`, `parent report`, `parent improve`)
- `parent/improve.py` - Improvement queue management, pattern analysis
- `parent/scheduler.py` - Babysitting scheduler, self-improvement loop
- `parent/install.sh` - Installation script for parent machine
- `parent/systemd/` - Timer and service files for automated babysitting
- `tests/test_parent.py` - 33 comprehensive tests

**Modified Files:**
- `state.py` - Added `improvements` and `reports` tables + helper functions
- `signal_receiver.py` - Routes `/parent` commands to child_handler
- `main.py` - Initializes child_handler on startup

### New Signal Commands

| Command | Response |
|---------|----------|
| `/parent status` | Uptime, active tasks, queue size |
| `/parent health` | Ollama, Signal, disk/memory/CPU status |
| `/parent history` | Recent task history with success rate |
| `/parent logs` | Last N lines of noctem.log |
| `/parent report` | Full babysitting report |
| `/parent approve {"id": N}` | Approve an improvement |
| `/parent reject {"id": N}` | Reject an improvement |

### Database Additions

**`improvements` table**: Tracks code improvement suggestions
- Status flow: pending → approved → applied (or rejected)
- Stores patches for automated application

**`reports` table**: Training data storage
- Every babysitting report captures problem→solution pairs
- Fields: metrics_json, problems_json, solutions_json
- Designed for future LoRA fine-tuning

### Updated Progress

```
Phase 1 (Web Skills):     ████████████████████ 100% ✓
Phase 2 (Birth):          ░░░░░░░░░░░░░░░░░░░░   0%
Phase 3 (Parent):         ████████████████████ 100% ✓
Phase 4 (Email):          ░░░░░░░░░░░░░░░░░░░░   0%

Overall: ~40% toward idealized vision (up from 25%)
```

---

## Addendum: Alignment Speculations (Parent Feature)

### 1. Training Data Pipeline is Ready

**Current**: `reports` table captures problems (failed tasks, skill errors) and stores them as JSON.

**Gap**: Solutions are often empty - we capture *what failed* but not *how it was fixed*.

**Path Forward**: When an improvement is applied, backfill solutions_json in related reports. This creates explicit problem→solution pairs for fine-tuning.

### 2. "Sleep Mode" Foundation Exists

**Current**: `BabysittingScheduler` runs analysis when idle, but doesn't do actual LoRA training.

**From VISION.md**: "Sleep mode for background training during idle time."

**Speculation**: With 100+ reports accumulated:
1. Export training pairs to JSONL
2. Fine-tune small LoRA adapter on local patterns
3. Hot-swap adapter into Ollama

The data pipeline is now in place. Actual training is the next step.

### 3. Parent Built Before Child

**Observation**: We built the supervisor (parent) before the worker (birth process).

**Why This is Good**: When birth is implemented (Phase 2), it can immediately report to parent. The supervision infrastructure is ready.

**Speculation**: Birth could send `/parent report` as part of umbilical handshake - proving the channel works.

### 4. Success Patterns Not Captured

**Current**: Reports focus on errors. Successful patterns aren't logged.

**Ideal**: "This worked well" is training data too.

**Quick Win**: Add `successes_json` to reports table. Log successful task completions with prompts and skill chains.

### 5. Trust Model is Phone-Based Only

**Current**: Any message from configured phone can send `/parent` commands.

**Risk**: If Signal account is compromised, attacker can approve malicious patches.

**Quick Win**: Add confirmation token - parent sends command, child responds with one-time code, parent confirms with code.

---

*Built with assistance from Warp Agent*

---

## Addendum: Phase 2 Birth Implementation (2026-02-08 Night)

### What Was Built

Complete **autonomous first-time setup system** (17 files, ~3000 lines):

| Component | Files | Purpose |
|-----------|-------|--------|
| State machine | `state.py` | BirthStage enum, JSON persistence, checkpoint/resume |
| Notifications | `notify.py` | Signal progress updates via daemon or CLI |
| Umbilical | `umbilical.py` | `/umb` commands, reverse SSH tunnel (30min timeout) |
| 10 Stages | `stages/s01-s10` | Modular setup with check/run/verify/rollback |
| Services | `templates/` | systemd oneshot (birth) + main service |
| Docs | `USB_SETUP.md` | Beginner guide: USB creation → first boot |
| Tests | `test_birth.py` | Mock-based validation |

### Birth Stage Sequence

```
DETECT → NETWORK → SYSTEM_DEPS → PYTHON_DEPS → OLLAMA →
SIGNAL_CLI → NOCTEM_INIT → TEST_SKILLS → AUTOSTART → CLEANUP → COMPLETE
```

Each stage: checks prerequisites → executes → verifies → reports via Signal.

### Key Design Decisions

1. **Checkpoint persistence**: State saved to `data/.birth_state.json` after each stage. Power loss = resume from last successful stage.

2. **Umbilical protocol**: When stuck, sends Signal help request with `/umb` command menu. Parent can SSH in via reverse tunnel.

3. **Beginner-first docs**: `USB_SETUP.md` assumes zero Linux experience. Step-by-step from Rufus to first Signal message.

4. **Service gating**: `noctem.service` has `ConditionPathExists=.birth_complete` — won't start until birth succeeds.

### Deployment Model Clarified

```
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│   Windows PC    │ ───▶ │   1TB USB Boot  │ ◀─── │  Parent Agent   │
│  (MVP Dev)      │      │  Ubuntu Server  │      │  (Remote Help)  │
│  Warp + Git     │      │  Ollama + Signal│      │  SSH + Signal   │
└─────────────────┘      └─────────────────┘      └─────────────────┘
     Phase 1                  Phase 2                  Phase 3
```

### Speculations on Moving Toward Ideals

1. **Shared partition automation**: Currently documented manually; could become optional `s11_shared_partition.py` stage using `parted` + `mkfs.exfat`.

2. **Signal registration stage**: Birth assumes Signal already registered. Could add polling stage that waits for registration and notifies when ready.

3. **Model pull progress**: Largest wait is Ollama model download. Could parse `ollama pull` output for percentage and send periodic Signal updates.

4. **Test-driven birth validation**: Stage `s08_test_skills` runs basic checks. Could integrate with `tests/local/run_all.py` for comprehensive validation.

5. **Birth ↔ Parent handoff**: Birth ends with `/umb` capability. Parent phase should extend this with `/parent` commands for ongoing remote management.

6. **LoRA data collection**: After Parent phase, skill execution logs in SQLite could feed self-improvement training (per VISION.md).

---

*Phase 2 implementation: Warp Agent (commit 5e6e794)*

---

## Addendum: Email MVP Implementation (2026-02-09)

### What Was Built

**Email System** (12 files, ~1500 lines):

| Component | File | Purpose |
|-----------|------|---------|
| Vault | `utils/vault.py` | Credential storage (env vars, encrypted, JSON) |
| SMTP | `skills/email_send.py` | Fastmail/Gmail SMTP sending |
| IMAP | `skills/email_fetch.py` | Inbox fetching and search |
| Reports | `skills/daily_report.py` | Generate/send daily status |
| Tests | `tests/test_email_skills.py` | 11 tests, all passing |
| Birth | `birth/stages/s06_email.py` | Credential loading at birth |
| Scripts | `scripts/setup_cron.sh` | Daily cron automation |
| Config | `data/email_config.template.json` | Pre-provision template |

### Database Tables Added

**From Parent (remote):**
- `improvements` - Parent-suggested code changes
- `reports` - Training data (problem→solution pairs)

**From Email (local):**
- `incidents` - Error/event logging with severity
- `daily_reports` - Report tracking with sent status

### Signal Commands Added

```
/report        - Generate daily report (display in Signal)
/email status  - Check email configuration
/email test    - Send test email
/email check   - Check inbox via IMAP
/email report  - Send daily report via email
```

### Provider Choice: Fastmail

- $3/mo, full IMAP/SMTP, CLI-friendly
- App passwords for secure automation
- SMTP: `smtp.fastmail.com:587`
- IMAP: `imap.fastmail.com:993`

### Setup Model: Option A (Pre-Provisioned)

User creates Fastmail account once (~5 min), saves credentials to `data/email_config.json`. All future births auto-configure.

---

## Alignment Speculation: MVP → VISION.md Ideals

### 1. Email Automation (VISION.md §Use Case 3)

**Current MVP:**
- ✅ IMAP polling for inbox check
- ✅ SMTP sending with credential vault
- ✅ Daily digest generation
- ◯ Newsletter summarization
- ◯ Appointment confirmation auto-response
- ◯ Bill notification extraction

**Next Steps:**
- Add `email_summarize` skill using LLM for newsletter digests
- Add classification model for email types (newsletter vs. appointment vs. bill)
- Implement approval queue via Signal for auto-responses

### 2. Credential Vault (VISION.md §Layer 1)

**Current MVP:**
- ✅ Environment variable backend (most secure)
- ✅ Encrypted JSON with master password
- ✅ Plain JSON (dev only, warns on use)
- ◯ Hardware key (YubiKey) integration

**Alignment:** Vault now exists. Hardware key support would complete Layer 1 security model.

### 3. Self-Improvement Data (VISION.md §Use Case 6)

**Current MVP:**
- ✅ `incidents` table logs errors with severity/category
- ✅ `daily_reports` tracks task success/failure
- ✅ `reports` table stores problem→solution pairs (from parent)
- ◯ LoRA fine-tuning pipeline

**Bridge Opportunity:** Daily reports + incidents provide training signal. Parent's `reports` table could feed LoRA adapter training during "sleep mode."

### 4. Security Model (VISION.md §Security)

**Improvements:**
- ✅ Credentials never in plaintext config (vault)
- ✅ Email config excluded from git (`.gitignore`)
- ✅ App passwords (not main password)
- ◯ Encrypted storage at rest (VeraCrypt layer above this)

### 5. Transparent Operation (VISION.md §Core Principles)

**Current MVP:**
- ✅ All incidents logged with timestamps
- ✅ Daily reports show exactly what Noctem did
- ✅ `/email status` shows configuration state
- ✅ Skill execution logged in `skill_log` table

---

## What's Left for Full Vision

### High Value, Low Effort
1. **Newsletter summarization** - LLM skill over fetched emails
2. **Model routing** - Router model (1.5B) for quick chat, worker (7B) for complex
3. **RAG pipeline** - ChromaDB/SQLite-vss for personal knowledge

### High Value, Medium Effort
4. **Matrix integration** - Self-hosted homeserver for rich media
5. **LoRA training pipeline** - Use accumulated logs for fine-tuning
6. **Calendar integration** - iCal/CalDAV for appointment tracking

### Deferred
7. **Hardware key** - YubiKey for vault unlock
8. **Web UI** - Local dashboard for visual tasks
9. **Skyvern automation** - Browser automation for complex scraping

---

*Email MVP implementation: Warp Agent (2026-02-09)*
