# Noctem: Idealized Vision & Architecture Plan

A portable, self-improving personal computing symbiont for life management.

## Vision Statement

Noctem is a **personal AI operating layer** that lives on encrypted portable storage, connecting you to your digital life through secure messaging while continuously learning and adapting to serve you better. It represents a shift from "using AI tools" to **having a computational partner** that understands your context, manages complexity on your behalf, and grows alongside you.

### Core Principles

1. **Data Sovereignty** - Your data is yours. Encrypted, portable, verifiable.
2. **Operational Independence** - Works offline; connectivity enhances but isn't required.
3. **Minimal Footprint** - Runs on low-spec hardware; efficient by design.
4. **Self-Improvement** - Learns from interactions to serve you better over time.
5. **Transparent Operation** - You always know what it's doing and why.

---

## Architecture Overview

### Layer 1: Portable Foundation

**Encrypted Container (VeraCrypt)**
- Cross-platform (Win/Mac/Linux) encrypted volume
- Contains: Noctem runtime, SQLite DB, local models, LoRA adapters, personal data
- Hidden volume capability for plausible deniability
- Can boot from any machine with VeraCrypt installed

**Identity & Authentication**
- Hardware key support (YubiKey/FIDO2) for container unlock
- Signal phone number as identity anchor
- Local credential vault (encrypted secrets store)

### Layer 2: Communication Hub

**Primary: Signal (Current)**
- Pros: Strong E2E encryption, phone as universal identity, existing integration
- Cons: Centralized, hostile to forks, limited rich media
- Keep as default for MVP; battle-tested, works now

**Secondary: Matrix (Future)**
- Self-hosted homeserver for full control
- Bridge to Signal, Telegram, email via mautrix
- Rich media, reactions, threads, read receipts
- Ideal for the "web page construction" use case (share links to dashboards)

**Tertiary: Email (IMAP/SMTP)**
- Newsletter summarization and digest
- Appointment confirmations
- Bill notifications and tracking
- Automated low-risk responses

**Quaternary: Local Web UI**
- For tasks requiring visual interaction
- Document review and approval
- Database browsing
- Learning/tutoring interface

### Layer 3: Intelligence Core

**Local LLM Stack (Ollama)**
- Router Model (1.5B-3B): Fast routing, quick responses, task classification
- Worker Model (7B-14B): Complex reasoning, planning, code generation
- Specialist Adapters (LoRA): Domain-specific fine-tuning swapped on demand

**RAG Pipeline**
- Vector database (SQLite-vss or ChromaDB) for personal knowledge
- Document ingestion: PDFs, emails, notes, bookmarks
- Course materials for tutoring use case

**Self-Improvement System**
- Interaction logging with quality signals (task success, user corrections)
- Periodic LoRA fine-tuning on accumulated data
- Router optimization: learn which tasks need which model
- "Sleep" mode for background training during idle time

### Layer 4: Skill Framework

**Core Skills (Built-in)**
- `shell` - System commands with safety rails
- `file_ops` - Read/write with path protection
- `signal_send` - Messaging
- `task_status` - Queue management

**Communication Skills**
- `email_fetch` - IMAP inbox scanning
- `email_send` - SMTP with templates
- `email_summarize` - Newsletter/thread digests
- `calendar_check` - iCal/CalDAV integration
- `appointment_confirm` - Automated responses

**Research Skills**
- `web_fetch` - URL retrieval with HTML→text
- `web_search` - DuckDuckGo/SearXNG integration
- `business_lookup` - Government registry scrapers
- `document_draft` - Structured document generation
- `database_update` - Maintain research databases

**Development Skills**
- `code_generate` - Write code to spec
- `code_review` - Analyze existing code
- `project_manage` - Track development tasks
- `git_ops` - Version control operations

**Learning Skills**
- `tutor_session` - Socratic dialogue for education
- `quiz_generate` - Assessment creation
- `concept_explain` - Adaptive explanation depth
- `progress_track` - Learning journey management

**Government/Admin Skills**
- `gov_lookup` - Find official processes (passport, license, etc.)
- `form_assist` - Help fill official forms
- `deadline_track` - Renewal reminders

---

## Use Case Deep Dives

### 1. Business License Research

**Flow:**
1. User: "Find active business licenses in Ottawa for cleaning services"
2. Noctem scrapes Ontario Business Registry + city licensing portal
3. Extracts: business name, license number, address, phone, email
4. Web searches for additional contact info
5. Compiles into structured database
6. Sends summary via Signal; full data accessible via web UI

**Implementation:**
- Skyvern or custom Playwright automation for dynamic sites
- Rate limiting and respectful scraping
- Structured storage in SQLite with full-text search

### 2. Statistics Tutoring

**Flow:**
1. User uploads course syllabus and textbook PDF
2. Noctem ingests into RAG knowledge base
3. Daily check-in: "Ready for your stats session?"
4. Socratic dialogue via Signal for concepts
5. Practice problems with step-by-step hints (not answers)
6. Web UI for visualizations, formula sheets, quizzes
7. Progress tracking and spaced repetition

**Implementation:**
- RAG over course materials
- Structured prompts for Socratic method
- Quiz generation from content
- Progress stored in SQLite

### 3. Email Automation

**Safe Automation Zones:**
- Newsletter summarization → daily digest
- Appointment confirmations → auto-respond with user rules
- Bill notifications → extract amounts, due dates → reminder database
- Unsubscribe management → bulk cleanup with approval

**Requires Human Approval:**
- Sending to new contacts
- Financial actions
- Anything with legal implications

**Implementation:**
- IMAP polling on schedule
- Classification model for email types
- Template-based responses
- Approval queue via Signal

### 4. Government Process Guidance

**Example: Passport Application**
1. User: "How do I get a Canadian passport?"
2. Noctem fetches current info from canada.ca
3. Extracts: requirements, documents needed, fees, processing time
4. Creates personalized checklist based on user profile
5. Tracks progress: "Have you gotten your photos taken?"
6. Fills forms where possible (PDF form filling)
7. Reminds of appointments and deadlines

**Implementation:**
- Web scraping with caching (government sites change slowly)
- Checklist templates per process type
- PDF form filling (pdftk or similar)

### 5. Background Software Development

**Flow:**
1. User describes project: "I want an app that tracks my reading list"
2. Noctem creates project plan, breaks into tasks
3. Generates code incrementally during "sleep" periods
4. Commits to git with proper structure
5. Runs tests, reports status
6. User reviews via web UI or Signal summaries
7. Iterates based on feedback

**Implementation:**
- Code generation via capable model (7B+ with coding specialization)
- Git integration for version control
- Test runner integration
- Web UI for code review

### 6. Self-Improvement Loop

**Data Collection:**
- Every interaction logged: query, response, outcome
- User corrections captured
- Task success/failure tracked
- Timing data for model selection optimization

**Training Pipeline:**
- Nightly/weekly LoRA fine-tuning run
- Router model learns: "this type of query → this model"
- Response quality model learns from corrections
- Small adapter files (~50MB) stored and versioned

**"Sleep" Mode:**
- When idle, Noctem enters improvement mode
- Processes accumulated data
- Runs fine-tuning if GPU available
- Optimizes databases and caches
- Reports improvements on wake

---

## Security Model

### Threat Model

- **Lost/Stolen USB**: Mitigated by VeraCrypt encryption + hidden volume
- **Compromised Public Machine**: Mitigated by read-only mode option
- **Credential Theft**: Mitigated by hardware key support, never storing secrets in plain text
- **Model Injection**: Mitigated by input sanitization, output validation
- **Runaway Commands**: Mitigated by command blacklist, confirmation for dangerous ops

### Defense Layers

1. **Physical**: Encrypted container
2. **Access**: Hardware key + passphrase
3. **Network**: TLS for all external comms, optional Tor/VPN
4. **Application**: Sandboxed skills, audit logging
5. **Data**: Encryption at rest, secure deletion

---

## Portability Model

### Scenario: Moving Between Machines
1. Plug in USB
2. Mount VeraCrypt volume (passphrase + optional hardware key)
3. Run portable Ollama/Python from volume
4. Noctem detects new machine, adapts
5. On disconnect: auto-dismount, clean shutdown

### Scenario: No VeraCrypt Available (Public Computer)
1. Limited mode: Signal-only interface
2. No local state access
3. Cloud relay for essential functions
4. Zero local data persistence

### Scenario: Fresh Install on New Server
1. Install Ollama, Python, signal-cli
2. Copy encrypted data directory
3. Decrypt and run
4. Machine-specific config auto-detected

---

## Technology Stack

### Core Runtime
- Python 3.11+ (portable)
- SQLite (database + vector search via sqlite-vss)
- Ollama (LLM serving)
- signal-cli (Signal interface)

### Models
- Router: qwen2.5:1.5b or phi-3:mini
- Worker: qwen2.5:7b, mistral:7b, or deepseek-coder:6.7b
- Embeddings: nomic-embed-text or all-MiniLM-L6-v2

### Future Additions
- Matrix homeserver (Synapse/Dendrite)
- Playwright/Skyvern for web automation
- ChromaDB or Qdrant for advanced RAG
- n8n or custom workflow engine

---

## Metrics for Success

1. **Response Time**: Quick chat <3s, complex task acknowledgment <10s
2. **Uptime**: >99% when host machine is on
3. **Task Success Rate**: >90% for well-defined tasks
4. **User Corrections**: Decreasing over time (learning)
5. **Portability**: <5 min to operational on new machine
6. **Storage**: Core system <5GB, grows with personal data
7. **Memory**: <4GB RAM for basic operation

---

## Addendum: OpenClaw Competitive Analysis

OpenClaw (formerly Clawdbot/Moltbot) is the closest existing implementation to Noctem's vision. Created by Peter Steinberger, it achieved "60,000+ GitHub stars in 72 hours" and now has 176k+ stars. Understanding its strengths and failures is critical.

### OpenClaw's Strengths (Learn From)

**1. Multi-Platform Messaging**
- Integrates with WhatsApp, Telegram, Discord, Signal simultaneously
- Users control via familiar chat apps - "the mobile chat experience is as simple as talking to a friend"

**2. Self-Improving/Self-Extending**
- "Can enhance its own capabilities by autonomously writing code to create relevant new skills"
- User reported: "it opened my browser… opened the Google Cloud Console… Configured oauth and provisioned a new token"

**3. Persistent Memory**
- "Recall past interactions over weeks and adapt to user habits"
- "Persistent memory... acts as an accelerant" for personalization

**4. Rich Integrations**
- 50+ integrations spanning "chat providers, AI models, productivity tools, music and audio platforms, smart home devices"
- Apple Notes, Reminders, Things 3, Notion, Obsidian, Trello, GitHub, etc.

**5. Model Agnostic**
- "Supports various LLMs via API keys or local deployment" (Claude, GPT, DeepSeek, Ollama)

**6. Community Momentum**
- Massive open-source contribution velocity
- Active skill marketplace (ClawHub)

### OpenClaw's Critical Failures (Avoid)

**1. Security Nightmare**
- Cisco: "From a security perspective, it's an absolute nightmare"
- npm founding CTO: "OpenClaw is a security dumpster fire"
- CVE-2026-25253: One-click RCE via malicious link - "takes milliseconds"
- "Three high-impact security advisories" in three days after launch
- 341 malicious skills found on ClawHub stealing data

**2. Supply Chain Vulnerability**
- ClawHub "is open by default and allows anyone to upload skills"
- Only restriction: "GitHub account that's at least one week old"
- Malicious skills deliver AMOS stealer, steal crypto keys, SSH credentials, browser passwords

**3. Credential Exposure**
- "Has already been reported to have leaked plaintext API keys and credentials"
- "Can leave behind users' credentials and configuration files" after uninstall
- "Fully revoking access" is difficult

**4. Excessive Privilege by Default**
- "Agents are able to modify critical settings... without requiring confirmation from a human"
- "Security considerations were largely deprioritized in favor of usability and rapid adoption"
- Sandboxing can be disabled via API, allowing direct host execution

**5. Complexity & Accessibility**
- "Takes some effort to setup and the concept of AI taking control of everything is too scary for average tech enthusiasts"
- HN thread: "I cannot find a single user of OpenClaw in my familiar communities"
- "A few HN users who did try it gave up / failed for various reasons"

**6. Cost Unpredictability**
- "Delivering some shocking bills"
- "With scheduled jobs or other functionality, the costs can increase quickly and unexpectedly"

**7. Node.js/Mac-Centric**
- "Long-running Node.js service" - heavier runtime than Python
- Initial momentum tied to "buying Mac minis to run Moltbot"
- Less portable than intended

### Noctem Differentiation Strategy

| Aspect | OpenClaw | Noctem |
|--------|----------|--------|
| Runtime | Node.js | Python (lighter, more portable) |
| LLM Default | Cloud APIs | Local Ollama (offline-first) |
| Security Model | Permissive, fix later | Restrictive by default |
| Skill Source | Open marketplace | Curated/audited + local-only option |
| Credential Storage | Exposed in config | Encrypted vault |
| Target User | Tech enthusiasts with Macs | Anyone with any Linux box |
| Cost Model | Pay-per-token (unpredictable) | Local inference (predictable) |
| Portability | Server-bound | USB-portable encrypted container |
| Confirmation | Optional, bypassable | Mandatory for dangerous ops |

### Key Lessons for Noctem

1. **Security-first architecture**: Every skill runs sandboxed. Credentials never in plaintext. Human confirmation for anything destructive.
2. **Curated skills only**: No open marketplace. Skills are reviewed or user-written only. Trust boundary is explicit.
3. **Local-first inference**: Ollama by default means no API cost surprises, no credential leakage to cloud.
4. **Minimal privilege**: Shell commands require allowlisting. File ops have path restrictions. Network access is explicit.
5. **Simple uninstall**: Single directory. No scattered config. `rm -rf noctem/` removes everything.
6. **Gradual capability**: Start with messaging + simple skills. Add autonomy only when trust is established.
7. **Transparent operation**: Every action logged. User can always see what Noctem did and why.

---

*Document generated: 2026-02-08*
*Built with assistance from Warp Agent*
