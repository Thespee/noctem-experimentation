# Session Summary - 2026-02-12

## What We Did This Session

### 1. Pivoted Messaging from Signal to Telegram
- **Why**: Signal requires signal-cli daemon, Java, QR code linking - complex
- **Telegram**: Just an API token, simple HTTP requests
- **Status**: Bot created via @BotFather, token obtained (store securely!)

### 2. Created USB Autoinstall Config
- **Location**: `autoinstall/user-data` and `autoinstall/meta-data`
- **Purpose**: Automated Ubuntu Server installation with correct partitions
- **Partition Layout**:
  - 512MB EFI (fat32)
  - 800GB Linux root (ext4)
  - ~128GB Shared (exFAT, readable from Windows)
- **Default credentials**: noctem / noctem

### 3. Clarified v0.5 Scope
**Goal**: Todoist clone over Telegram
- Natural language task parsing ("Buy milk tomorrow at 4pm")
- Read-only web interface
- Morning report (what's due today)
- Evening report (ask what was done)

---

## Next Steps

### Immediate (USB Setup)
1. Format small USB as FAT32, label it `CIDATA`
2. Copy `autoinstall/user-data` and `autoinstall/meta-data` to CIDATA USB
3. Boot target PC with: Ubuntu installer USB + CIDATA USB + 1TB USB
4. Let autoinstall run (~15-20 min)
5. SSH in: `ssh noctem@<IP_ADDRESS>` (password: noctem)

### After USB is Running
1. Build Telegram bot (replace signal_receiver.py)
2. Implement natural language date parsing
3. Add read-only web interface
4. Create Ansible playbook for reproducible setup

---

## Key Files

| File | Purpose |
|------|---------|
| `autoinstall/user-data` | Ubuntu autoinstall config (partitions, packages) |
| `autoinstall/meta-data` | Required by cloud-init |
| `personal_mvp/PROGRESS.md` | Updated with new scope |
| `data/config.json` | Will need Telegram token added |

---

## Research Findings

### Telegram vs Signal
Telegram is much simpler - no daemon, just HTTP API calls.

### USB Reproducibility Options
1. **Autoinstall** (done) - automated Ubuntu installation
2. **Ansible playbook** (TODO) - automated app deployment after install
3. **dd backup** - full disk image for recovery

---

*Session ended: 2026-02-12 ~21:38 UTC*
