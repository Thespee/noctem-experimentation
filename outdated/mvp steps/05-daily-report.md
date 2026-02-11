# Phase 5: Daily Email Reports (MVP)

**Objective**: Send once-a-day status reports via email with tasks completed, incidents, and suggestions.

**Prerequisites**: 
- Working Noctem installation
- Fastmail account with app password ($3/mo)
- Python 3.8+

---

## Overview

The daily report system provides:
1. **Send**: Daily status reports (tasks, incidents, suggestions)
2. **Receive**: Read and process incoming emails (IMAP)

Recommended provider: **Fastmail** - reliable, CLI-friendly, full IMAP/SMTP.

---

## Quick Start

### 1. Create Fastmail Account (One-time, ~5 min)

1. Go to https://fastmail.com → Sign up ($3/mo)
2. Settings → Password & Security → App Passwords
3. Create new app password for "Noctem"
4. Save the generated password

### 2. Configure Noctem

Interactive setup:
```bash
python utils/vault.py
```

Or set environment variables (recommended for production):
```bash
export NOCTEM_EMAIL_USER="noctem@fastmail.com"
export NOCTEM_EMAIL_PASSWORD="your-app-password"
export NOCTEM_EMAIL_SMTP_SERVER="smtp.fastmail.com"
export NOCTEM_EMAIL_IMAP_SERVER="imap.fastmail.com"
export NOCTEM_EMAIL_RECIPIENT="your-personal@email.com"
export NOCTEM_EMAIL_FROM_NAME="Noctem"

```

### 3. Test Connections

```bash
# Test sending (SMTP)
python skills/email_send.py --test

# Test receiving (IMAP)
python skills/email_fetch.py --test
```

### 4. Generate a Test Report

```bash
# Print report to console (no email)
python skills/daily_report.py --generate

# Send report via email
python skills/daily_report.py --send
```

### 5. Set Up Daily Automation (8 AM PST)

Add to crontab:
```bash
crontab -e
```

Add this line (8 AM PST = 16:00 UTC):
```
0 16 * * * cd /path/to/noctem && python skills/daily_report.py --send >> logs/daily_report.log 2>&1
```

Or if your server is set to PST:
```
0 8 * * * cd /path/to/noctem && python skills/daily_report.py --send >> logs/daily_report.log 2>&1
```

---

## File Structure

```
noctem/
├── utils/
│   └── vault.py           # Credential storage (env vars, encrypted, or plaintext)
├── skills/
│   ├── email_send.py      # SMTP sending
│   ├── email_fetch.py     # IMAP receiving
│   └── daily_report.py    # Report generation and sending
├── tests/
│   └── test_email_skills.py  # Comprehensive tests
└── state.py               # Updated with incidents + daily_reports tables
```

---

## Components

### Credential Vault (`utils/vault.py`)

Supports three backends (in order of preference):
1. **Environment variables** - Most secure for servers
2. **Encrypted file** - Requires master password
3. **Plain JSON file** - Development only (warns on use)

```python
from utils.vault import get_credential, set_credential

# Get a credential
email = get_credential("email_user")

# Set a credential  
set_credential("email_user", "test@example.com")
```

### Email Send Skill (`skills/email_send.py`)

Basic SMTP sending:

```python
from skills.email_send import send_email_smtp

success, message = send_email_smtp(
    to="recipient@example.com",
    subject="Test",
    body="Hello!"
)
```

CLI testing:
```bash
# Test SMTP connection
python skills/email_send.py --test

# Send test email
python skills/email_send.py --send --to recipient@example.com
```

### Email Fetch Skill (`skills/email_fetch.py`)

Read emails from IMAP inbox:

```python
from skills.email_fetch import fetch_emails, test_imap_connection

# Test connection
success, msg = test_imap_connection()

# Fetch recent unread emails
emails, error = fetch_emails(
    folder="INBOX",
    limit=10,
    unread_only=True,
    since_hours=24
)
```

CLI usage:
```bash
# Test IMAP connection
python skills/email_fetch.py --test

# Fetch recent emails
python skills/email_fetch.py --fetch --limit 5

# Fetch all (not just unread) from last 48 hours
python skills/email_fetch.py --fetch --all --hours 48
```

### Daily Report Skill (`skills/daily_report.py`)

Generates and optionally sends the daily status report:

```python
from skills.daily_report import generate_report, send_daily_report

# Just generate (no send)
report_text, stats = generate_report(period_hours=24)

# Generate and send
success, message, stats = send_daily_report(
    recipient="reports@example.com",
    period_hours=24
)
```

CLI usage:
```bash
# Generate and print
python skills/daily_report.py --generate

# Generate and send
python skills/daily_report.py --send

# Custom time window
python skills/daily_report.py --send --hours 48
```

### Incident Logging

Log incidents from anywhere in the codebase:

```python
import state

# Log an incident
state.log_incident(
    message="Something went wrong",
    severity="error",      # info, warning, error, critical
    category="system",     # system, task, skill, network, email, other
    details="Full stack trace here",
    task_id=123            # optional
)

# Get recent incidents
from datetime import datetime, timedelta
incidents = state.get_incidents_since(datetime.now() - timedelta(hours=24))

# Acknowledge incidents (marks them as seen)
state.acknowledge_incidents()
```

---

## Report Format

Example daily report:

```
🌙 NOCTEM DAILY REPORT
   myserver | 2026-02-09 08:00
   Last report: 2026-02-08

==================================================

📊 TASKS COMPLETED (5)
------------------------------
  ✅ Check disk space
  ✅ Summarize inbox
  ✅ Fetch weather forecast
  ✅ Update system packages
  ✅ Run weekly backup

❌ TASKS FAILED (1)
------------------------------
  ❌ Send reminder email
     Error: SMTP connection timed out...

🚨 INCIDENTS (2)
------------------------------
  ⚠️ [WARNING] High memory usage detected
  ❌ [ERROR] Ollama request timed out

💡 SUGGESTED ACTIONS
------------------------------
  🔄 1 task(s) failed - review and retry?
  🔧 Multiple errors detected - investigate system health

==================================================
Generated by Noctem on myserver
```

---

## Database Schema Additions

Two new tables added to `state.py`:

**incidents**
```sql
CREATE TABLE incidents (
    id INTEGER PRIMARY KEY,
    severity TEXT DEFAULT 'info',     -- info, warning, error, critical
    category TEXT,                     -- system, task, skill, network, email
    message TEXT,
    details TEXT,
    task_id INTEGER,
    acknowledged INTEGER DEFAULT 0,
    created_at TIMESTAMP
);
```

**daily_reports**
```sql
CREATE TABLE daily_reports (
    id INTEGER PRIMARY KEY,
    report_date DATE UNIQUE,
    tasks_completed INTEGER,
    tasks_failed INTEGER,
    incidents_count INTEGER,
    report_text TEXT,
    sent_at TIMESTAMP,
    created_at TIMESTAMP
);
```

---

## Testing

Run the test suite:
```bash
python tests/test_email_skills.py
```

Tests cover:
- Vault credential storage (env, file backends)
- SMTP sending (with mock server)
- Authentication failure handling
- Report generation
- Suggestion logic
- Incident logging and acknowledgment

---

## Troubleshooting

### "Email not configured"
Run the interactive setup:
```bash
python utils/vault.py
```

Or set environment variables:
```bash
export NOCTEM_EMAIL_USER="..."
export NOCTEM_EMAIL_PASSWORD="..."
```

### "SMTP authentication failed"
- Use an **app password**, not your main password
- For Gmail: Enable 2FA, then create app password at https://myaccount.google.com/apppasswords
- For Outlook: https://account.live.com/proofs/AppPassword

### "Connection timed out"
- Check firewall allows outbound on port 587 (SMTP)
- Verify SMTP server address is correct
- Try: `telnet smtp.gmail.com 587`

### Report shows no data
- Check the time period (default 24 hours)
- Verify tasks are being logged to the database
- Run: `python -c "import state; print(state.get_recent_tasks())"`

### Vault warning about plaintext storage
This is expected during development. For production:
1. Set environment variables (recommended), or
2. Use the encrypted vault backend with a master password

---

## Integration with Signal

Add email commands to `signal_receiver.py`:

```python
# In handle_message():
if message.startswith("/report"):
    from skills.daily_report import generate_report
    report, stats = generate_report(period_hours=24)
    return report[:1500]  # Truncate for Signal
```

---

## Next Steps

1. **Scheduled sending**: Add cron job for automatic daily reports
2. **HTML reports**: Add `html=True` option for richer formatting
3. **Report customization**: Configure which sections to include
4. **Email fetching**: Implement IMAP to read/summarize incoming email
5. **Digest improvements**: Use LLM to generate smarter suggestions

---

## Completion Checklist

- [x] `utils/vault.py` - Credential storage
- [x] `skills/email_send.py` - SMTP sending
- [x] `skills/daily_report.py` - Report generation
- [x] `state.py` - Incident + daily_reports tables
- [x] `tests/test_email_skills.py` - Test suite
- [x] `skills/__init__.py` - Register new skills
- [ ] Configure email credentials
- [ ] Test email connection
- [ ] Send first report
- [ ] Set up cron job for daily automation

---

*Built with assistance from Warp Agent*
