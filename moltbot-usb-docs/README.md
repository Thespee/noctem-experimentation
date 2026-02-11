# Portable Local AI Assistant (Moltbot USB)

A complete guide to creating a portable, encrypted, local AI assistant that runs from a USB drive.

## Philosophy
**Accessibility first.** AI assistance should be available to everyone, regardless of hardware. Start minimal, upgrade when you can.

## Overview

This documentation suite provides everything you need to set up:
- **Portable Linux** on an encrypted USB drive
- **Local LLM** (Ollama) with auto-scaling models (1.5B → 14B based on hardware)
- **Router architecture** - tiny fast model dispatches to tools/models/cloud
- **Moltbot/Clawdbot** agentic framework
- **Background task automation** with state management
- **Signal integration** for remote commands
- **Secure, privacy-focused** design (no cloud dependencies unless you ask)

## Hardware Requirements Summary

| Component | Minimum | Recommended | Optimal |
|-----------|---------|-------------|----------|
| USB Drive | 128GB | 256GB SSD | 1TB SSD (USB 3.0+) |
| RAM | 8GB | 16GB | 32GB |
| CPU | 2 cores | 4 cores | 8+ cores with AVX2 |
| GPU | None | None | Any NVIDIA (optional) |

### What You Get By Tier
| RAM | Model | Speed | Capability |
|-----|-------|-------|------------|
| 8GB | 1.5B router | 2-8 t/s | Routing + simple tasks |
| 16GB | 7B agentic | 3-5 t/s | Full local reasoning |
| 32GB | 14B+ | 2-4 t/s | Complex reasoning |
| +GPU | Largest fit | 15-100+ t/s | Speed boost |

## Documentation Structure

```
moltbot-usb-docs/
├── README.md                          # This file
├── 00-MINIMAL-SETUP-GUIDE.md         # ⭐ START HERE - accessible setup (8GB+)
├── 01-MASTER-SETUP-GUIDE.md          # Full setup for 16GB+ systems
├── 02-SECURITY-HARDENING.md          # Firewall, encryption, auditing
└── skills/
    ├── SKILL-optimizer.md            # ⭐ Hardware detection & model selection
    ├── SKILL-router.md               # ⭐ Main brain - dispatches requests
    ├── SKILL-web-scraper.md          # Web scraping & database
    ├── SKILL-google-calendar.md      # Calendar integration (read-only)
    ├── SKILL-gmail-reader.md         # Email reading & summarization
    ├── SKILL-background-scheduler.md # Task scheduling with state
    └── SKILL-hybrid-cloud.md         # Cloud AI with privacy sanitization
```

## Quick Start

### For Most Users (8GB+ RAM): Use Minimal Guide
1. Read `00-MINIMAL-SETUP-GUIDE.md`
2. Download Ubuntu Server ISO
3. Create installation USB with Rufus
4. Install Ubuntu to your USB with LUKS encryption
5. Install Ollama + pull tiny router model
6. Run **Optimizer skill** to detect hardware and upgrade if possible

**Time: ~1-2 hours**

### For Power Users (16GB+ RAM): Use Full Guide
1. Read `01-MASTER-SETUP-GUIDE.md`
2. Follow complete setup with 7B model default
3. Add security hardening from `02-SECURITY-HARDENING.md`
4. Set up skills as needed

**Time: ~3-4 hours**

### After Setup
1. Run `optimizer.py detect` to verify hardware tier
2. Run `optimizer.py apply` to upgrade model if hardware allows
3. Add skills as needed (calendar, email, scraper, etc.)

## Security Model

### What's Protected
- **Full disk encryption** (LUKS2 with AES-256) for Linux system
- **Firewall** blocks all non-essential traffic
- **No cloud AI** - all processing local
- **Read-only APIs** for Google services

### Shared Partition (128GB exFAT)
- **NOT encrypted** - accessible without password
- Use for file transfers only, not sensitive data
- Accessible from Windows, macOS, Android via USB
- Linux can read/write when booted

### What Can Access Internet
- Web scraping (HTTP/HTTPS outbound)
- Google APIs (Calendar, Gmail - read only)
- Signal messaging (for remote commands)
- System updates

### What CANNOT Happen
- Personal data sent to external servers
- Email sending (blocked at firewall)
- SSH outbound (blocked)
- Analytics/telemetry (blocked)

## Example Use Cases

### "What's on my calendar today?"
```
You → Moltbot → calendar_reader.py → Google Calendar API
                                    ↓
You ← Moltbot ← "You have 3 meetings..."
```

### "Summarize my unread emails"
```
You → Moltbot → gmail_reader.py → Gmail API (read-only)
                    ↓
              Local Ollama (summarize)
                    ↓
You ← Moltbot ← "5 unread: 2 from work, 1 urgent..."
```

### Remote: "status" via Signal
```
Phone → Signal → signal-cli → signal-handler.sh
                                    ↓
Phone ← Signal ← "System online. 3 tasks running..."
```

## Performance Expectations

| Task | Time |
|------|------|
| Model response (simple) | 5-15 seconds |
| Model response (complex) | 30-60 seconds |
| Email fetch | 2-5 seconds |
| Calendar check | 1-2 seconds |
| Web scrape | 2-10 seconds |

*Note: CPU inference is slower than GPU but fully functional*

## File System Layout (After Setup)

```
/mnt/shared/                 # 128GB exFAT partition (accessible from Windows/Mac/Android)
├── exports/                 # Exported data
├── reports/                 # Generated reports
├── transfers/               # Files to transfer
└── data/                    # Data exports

/home/moltbot/
├── shared -> /mnt/shared    # Symlink to shared partition
├── workspace/               # Moltbot working directory
│   └── SOUL.md             # Agent personality/rules
├── moltbot-system/
│   ├── config/
│   │   └── tasks.json      # Scheduled tasks
│   ├── data/
│   │   ├── scraped.db      # Scraper database
│   │   └── scheduler.db    # Scheduler state
│   ├── logs/               # All logs
│   ├── skills/             # Python skill modules
│   ├── tasks/              # Bash task scripts
│   ├── state/              # Task state files
│   └── security/           # Security scripts
├── .clawdbot/
│   └── clawdbot.json       # Moltbot config
├── .config/moltbot/
│   ├── env                 # Environment variables
│   ├── google_credentials.json
│   └── google_token.json
└── start-moltbot.sh        # Startup script
```

## Maintenance

### Daily (Automatic)
- Background tasks run per schedule
- Logs rotate automatically
- Security monitoring runs every 30 minutes

### Weekly (Manual)
- Check security logs
- Review task error counts
- Verify Signal connectivity

### Monthly (Manual)
- System updates: `sudo apt update && sudo apt upgrade`
- Backup LUKS header to external drive
- Review and update allowed domains

## Troubleshooting Quick Reference

| Issue | Solution |
|-------|----------|
| Boot fails | Check BIOS boot order, disable Secure Boot |
| Ollama slow | Expected on CPU (~2-5 t/s) |
| Google auth fails | Delete token file, re-authenticate |
| Signal not responding | Check daemon: `systemctl status signal-cli` |
| Task stuck | Check logs, restart scheduler |

## Contributing

These documents are designed to be modified for your specific needs. Feel free to:
- Add new skills
- Modify security rules
- Customize the SOUL.md for your preferences
- Add integrations with other services

## License

This documentation is provided as-is for personal use.

---

*Built for privacy, portability, and productivity.*
