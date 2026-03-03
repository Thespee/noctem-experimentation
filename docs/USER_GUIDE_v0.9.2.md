# Noctem v0.9.1 User Guide
## The Graceful Butler: Fast Capture, Slow Reflection, Self-Improvement, Skills, Personal Wiki

---

## What's New in v0.9.1

### Wiki CLI & Quick Wins
The wiki is now fully usable from the command line. New web pages bring a Google Calendar-like view and Todoist-style task management. Commands are faster with `.` shorthand prefixes.

**Key Features:**
- **Wiki CLI** - `wiki ingest`, `wiki search`, `wiki ask`, `wiki sources`, `wiki status`, `wiki verify`
- **Feedback sessions** - Scheduled clarification sessions to resolve ambiguous tasks
- **Command shortcuts** - `.t` for task, `.p` for project, `.d` for done, `.w` for wiki, etc.
- **Calendar view** - `/calendar/view` — Google Calendar-like weekly grid
- **Task views** - `/tasks/upcoming` (overdue + upcoming) and `/tasks/projects` (project board)
- **Skill-Wiki bridge** - Skills can now request wiki context during execution

**Quick Start:**
1. Drop files into `noctem/data/sources/`
2. Run `wiki ingest` to process them
3. Query with `wiki ask "your question"`
4. Use `.t buy groceries tomorrow` to quickly add tasks
5. Visit `/calendar/view` for a weekly calendar or `/tasks/projects` for the project board

---

## v0.9.0: Personal Wiki (Knowledge Base)
Noctem includes a personal knowledge base that lets you ingest documents and query them with semantic search. Every answer is grounded in YOUR sources with proper citations.

**Key Features:**
- **Multi-format ingestion** - PDF, Markdown, and TXT files
- **Semantic search** - Find related content by meaning, not just keywords
- **Citation system** - Every answer includes source, page/section, and direct quotes
- **Trust levels** - Tag sources as personal (1), curated (2), or web (3)
- **Local-first** - All processing via Ollama; embeddings stored in ChromaDB locally

---

## v0.8.0: Skills Infrastructure
Skills are Noctem's extensible system for packaged knowledge and procedures. Think of them as "recipes" the system can execute when triggered.

**Key Features:**
- **SKILL.yaml format** - Structured metadata with separate instructions file
- **Pattern-based triggers** - RapidFuzz fuzzy matching with confidence thresholds
- **Approval workflow** - Sensitive skills can require user approval
- **Execution logging** - All skill runs are logged for analysis
- **Bundled + User skills** - Core skills ship with Noctem; create your own

---

## Fresh Install (New Computer)

### Prerequisites

**Required:**
- Python 3.10+ (https://python.org)
- pip (comes with Python)

**Strongly Recommended Optional (for full features):**
- Ollama (https://ollama.ai) - for AI suggestions (slow mode)
- Telegram account - for mobile notifications

### Step 1: Clone & Setup Virtual Environment

```powershell
# Clone the repository
git clone https://github.com/YOUR_USERNAME/noctem.git
cd noctem/"current version_v0.9.1"

# Create virtual environment
python -m venv venv

# Activate it (Windows PowerShell)
.\venv\Scripts\Activate.ps1

# Or on Linux/Mac:
# source venv/bin/activate
```

### Step 2: Install Dependencies

```powershell
# Install all required packages
pip install -r requirements.txt

# The requirements include:
# - flask (web dashboard)
# - python-telegram-bot (Telegram integration)
# - icalendar (calendar sync)
# - apscheduler (scheduled tasks)
# - requests (HTTP client)
# - faster-whisper (voice transcription)
# - rapidfuzz (skill trigger matching)
```

### Step 3: Download AI Models (Optional but Recommended)

```powershell
# For Whisper voice transcription (tiny model, ~39MB)
.\venv\Scripts\python.exe -c "from noctem.slow.whisper import get_whisper_service; svc = get_whisper_service(); svc.preload(); print('Whisper ready!')"

# For Ollama slow mode suggestions:
# 1. Install Ollama from https://ollama.ai
# 2. Pull the model:
ollama pull qwen2.5:7b-instruct-q4_K_M
```

### Step 4: Initialize Database

```powershell
# Initialize the SQLite database
.\venv\Scripts\python.exe -c "from noctem.db import init_db; init_db()"
```

### Step 5: Run Tests (Verify Installation)

```powershell
# Run all tests to verify everything works
.\venv\Scripts\python.exe -m pytest tests/ -v

# Should see: "~500+ passed" (includes 90 skill + 95 wiki tests)
```

### Step 6: Configure Telegram Bot (Optional)

1. Message @BotFather on Telegram
2. Send `/newbot`, follow prompts to create bot
3. Copy the token (looks like `123456789:ABCdef...`)
4. Configure in Noctem:

```powershell
.\venv\Scripts\python.exe -m noctem cli
# Then type:
set telegram_bot_token YOUR_TOKEN_HERE
```

5. Start Noctem, send `/start` to your bot to link your chat

### Step 7: Run Noctem

```powershell
# Run everything (Telegram bot + web dashboard + scheduler)
.\venv\Scripts\python.exe -m noctem all

# Or run components separately:
.\venv\Scripts\python.exe -m noctem bot    # Just Telegram bot
.\venv\Scripts\python.exe -m noctem web    # Just web dashboard (http://localhost:5000)
.\venv\Scripts\python.exe -m noctem cli    # Interactive CLI
```

---

## Skills System (v0.8.0)

### Overview

Skills extend Noctem's capabilities through packaged knowledge and procedures. Each skill consists of:
- **SKILL.yaml** - Metadata (name, version, triggers, dependencies)
- **instructions.md** - Human-readable procedure/instructions

### Skill Locations

| Location | Purpose |
|----------|---------|
| `noctem/skills/bundled/` | Ships with Noctem (read-only) |
| `noctem/data/skills/` | User-created skills |

### CLI Commands

```bash
# List all installed skills
noctem skill list

# Show skill details
noctem skill info my-skill

# Execute a skill
noctem skill run my-skill "optional input"

# Enable/disable a skill
noctem skill enable my-skill
noctem skill disable my-skill

# Create a new skill (scaffolding)
noctem skill create my-new-skill

# Validate a skill's SKILL.yaml
noctem skill validate path/to/skill
```

### Telegram Commands

```
/skill list                    - List enabled skills
/skill info <name>             - Show skill details
/skill run <name> [input]      - Execute a skill
```

### Web Dashboard

Visit `/skills` to:
- View all installed skills with stats
- Enable/disable skills with one click
- Run skills with custom input
- See execution history (success/failure counts)

### Creating a Skill

1. **Scaffold the skill:**
   ```bash
   noctem skill create my-awesome-skill
   ```

2. **Edit `noctem/data/skills/my-awesome-skill/SKILL.yaml`:**
   ```yaml
   name: my-awesome-skill
   version: "1.0.0"
   description: "Does something awesome"
   triggers:
     - pattern: "how do I do something awesome"
       confidence_threshold: 0.8
   dependencies: []
   requires_approval: false
   instructions_file: instructions.md
   ```

3. **Edit `noctem/data/skills/my-awesome-skill/instructions.md`:**
   ```markdown
   # My Awesome Skill
   
   ## Steps
   1. First, do this
   2. Then, do that
   3. Finally, finish up
   
   ## Notes
   - Remember to check X before Y
   ```

4. **Validate and test:**
   ```bash
   noctem skill validate noctem/data/skills/my-awesome-skill
   noctem skill run my-awesome-skill "test input"
   ```

### Skill Triggers

Skills can be triggered in two ways:

1. **Explicit invocation:** `/skill run <name>` always works
2. **Pattern matching:** Natural language triggers using RapidFuzz fuzzy matching

Pattern matching uses confidence thresholds (0.5-1.0):
- **0.8+** = High confidence (recommended default)
- **0.5-0.8** = Moderate confidence (more permissive)

```yaml
triggers:
  - pattern: "how do I make coffee"
    confidence_threshold: 0.8
  - pattern: "brew coffee"
    confidence_threshold: 0.7
```

### Approval Workflow

Skills that perform sensitive actions can require approval:

```yaml
requires_approval: true
```

When executed:
1. Skill creates an execution record with status `pending_approval`
2. User is notified and asked to approve
3. After approval, skill proceeds with execution

### Execution Logging

All skill runs are logged in the `skill_executions` table:
- Input text
- Output/result
- Duration (ms)
- Status (pending, running, completed, failed)
- Trigger source (explicit, pattern, api)

This data feeds into the v0.7.0 self-improvement engine for pattern analysis.

---

## Features (All Versions)

### Fast Mode (Always Active)
Fast mode catches every thought instantly (<500ms). Just type naturally:

**Adding Tasks:**
- `buy groceries tomorrow`
- `call mom friday 3pm`
- `finish report by feb 20 !1` (high priority)
- `review PR /backend #work` (with project and tag)

**Quick Actions:**
- `done 1` — Complete task #1 from today's list
- `done buy milk` — Complete by name
- `skip 2` — Defer task #2 to tomorrow
- `delete old task` — Remove a task
- `habit done exercise` — Log a habit

**Priority Markers:**
- `!1` = High priority (important)
- `!2` = Medium priority (default)
- `!3` = Low priority

**Shortcut Commands (v0.9.1):**
- `.t <text>` — Quick task creation (`.t buy groceries tomorrow`)
- `.p <name>` — Quick project creation
- `.g <name>` — Quick goal creation
- `.d <n|name>` — Quick done (`.d 1` or `.d buy milk`)
- `.s <n|name>` — Quick skip
- `.w <cmd>` — Wiki shorthand (`.w ask "question"`)

**View Commands:**
- `today` or `/today` — Today's briefing
- `week` or `/week` — Week ahead
- `projects` or `/projects` — Active projects

**Status Commands:**
- `status` or `/status` — System health (butler, slow mode, LLM)
- `suggest` or `/suggest` — View AI suggestions
- `slow` — Slow mode queue status
- `/session` — Start a feedback session (clarify ambiguous tasks)

**Web Pages (v0.9.1):**
- `/calendar/view` — Weekly calendar (Google Calendar-style)
- `/tasks/upcoming` — Upcoming tasks + overdue (Todoist-style)
- `/tasks/projects` — Project board with task columns

### Self-Improvement Engine (v0.7.0)

Noctem learns from its own behavior:

1. **Pattern Detection** - Identifies recurring issues
2. **Insight Generation** - Creates actionable recommendations
3. **Learned Rules** - Improves future classifications

```bash
# View detected patterns
noctem patterns list

# Apply an insight
noctem insights apply 1

# View learned rules
noctem rules list
```

### Remote Access (Tailscale)

Access Noctem securely from anywhere:

```powershell
# Install Tailscale
winget install Tailscale.Tailscale

# Connect
& "C:\Program Files\Tailscale\tailscale.exe" up

# Get your remote URL via Telegram
/access
```

Then visit `http://<tailscale-ip>:5000` from any device.

---

## Wiki System (v0.9.0)

### CLI Commands

```bash
# Ingest documents
noctem wiki ingest              # Process all files in data/sources/
noctem wiki ingest notes.pdf    # Process a specific file

# Search your knowledge base
noctem wiki search "time management"  # Semantic search
noctem wiki ask "What are the key principles of GTD?"  # Full answer with citations

# Manage sources
noctem wiki sources             # List all indexed sources
noctem wiki sources --trust 2   # Filter by trust level
noctem wiki status              # Show indexing status and stats
noctem wiki verify              # Check for changed source files
```

### Trust Levels

| Level | Meaning | Examples |
|-------|---------|----------|
| 1 (Personal) | Your own notes and writing | journals, personal notes |
| 2 (Curated) | Vetted sources you trust | textbooks, official docs |
| 3 (Web) | Unverified web content | downloaded articles |

Higher trust sources are prioritized in search results.

### Example Query

```
> noctem wiki ask "What did I note about time management?"

Based on your sources:

Time management works best with "time blocking — dedicating specific 
hours to specific types of work" [1].

You also noted that mornings are best for focused work, while 
afternoons suit meetings [2].

---
[1] productivity-notes.md, Section: Daily Routine
[2] deep-work.pdf, Page 47
```

---

## Architecture Overview

```
noctem/
├── wiki/             # v0.9.0 Personal knowledge base
│   ├── ingestion.py  # File parsing (PDF, MD, TXT)
│   ├── chunking.py   # Text splitting with overlap
│   ├── embeddings.py # Ollama + ChromaDB
│   ├── retrieval.py  # Semantic search, citations
│   └── query.py      # Query mode with LLM
├── skills/           # v0.8.0 Skills infrastructure
│   ├── loader.py     # YAML parsing, validation
│   ├── registry.py   # Discovery, CRUD, stats
│   ├── trigger.py    # Pattern matching (RapidFuzz)
│   ├── executor.py   # Execution flow, approval
│   └── service.py    # High-level API
├── fast/             # Fast path: classifier, capture
├── slow/             # Slow path: LLM analysis, patterns
├── butler/           # Butler protocol, summon
├── telegram/         # Bot handlers
├── web/              # Flask dashboard
└── data/
    ├── noctem.db     # SQLite database
    ├── chroma/       # ChromaDB vector store
    ├── sources/      # Documents for wiki
    └── skills/       # User-created skills
```

---

## Troubleshooting

### Skills not discovered
```bash
# Check skill directory exists
ls noctem/data/skills/

# Validate skill format
noctem skill validate noctem/data/skills/my-skill
```

### Pattern not matching
- Check confidence threshold (try lowering to 0.7)
- Use explicit invocation: `/skill run <name>`
- Verify skill is enabled: `noctem skill info <name>`

### Execution fails
- Check execution logs in web dashboard `/skills`
- Review error message in skill execution record
- Validate skill YAML and instructions exist

---

*Co-Authored-By: Warp <agent@warp.dev>*
