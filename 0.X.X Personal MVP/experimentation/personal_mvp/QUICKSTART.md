# Noctem Personal MVP - Quick Start Guide

Get Noctem running on your Ubuntu Server USB in 10-15 minutes.

## Prerequisites

- Ubuntu Server running on the USB
- SSH access from another machine
- A Telegram account

---

## Fresh Install: Automated Setup (Optional)

The `autoinstall/` folder contains Ubuntu autoinstall files for unattended installation.

### Preparing the Autoinstall

1. **Get your USB serial number** (on Windows PowerShell):
   ```powershell
   Get-Disk | Select-Object Number, FriendlyName, SerialNumber, Size
   ```

2. **Edit `autoinstall/user-data`**:
   - Line 20: Remove the SSH key line (or add your public key)
   - Lines 32-33: Change `size: largest` to target your USB:
     ```yaml
     match:
       serial: "YOUR_USB_SERIAL_HERE"
     ```

3. **Copy to installer USB**:
   - Create `autoinstall/` folder at root of Ubuntu Server installer USB
   - Copy `user-data` and `meta-data` into it

4. **Boot and trigger autoinstall**:
   - Boot from installer USB
   - At GRUB menu, press `e` to edit
   - Add to the `linux` line: `autoinstall ds=nocloud;s=/cdrom/autoinstall/`
   - Press F10 to boot

**Default credentials**: username `noctem`, password `noctem`

---

## Quick Setup Commands (After Fresh Ubuntu Install)

SSH into the machine and run these commands:

```bash
# Update system and install dependencies
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip git curl

# Set timezone
sudo timedatectl set-timezone America/Los_Angeles

# Clone the repo
mkdir -p ~/data
cd ~/data
git clone https://github.com/Thespee/noctem.git
cd noctem

# Create config
cp data/config.example.json data/config.json

# Edit config with your Telegram bot token (see Telegram Setup below)
nano data/config.json
```

---

## Telegram Setup (5 min)

### 1. Create a Telegram Bot

1. Open Telegram and search for `@BotFather`
2. Send `/newbot`
3. Choose a name (e.g., "Noctem Assistant")
4. Choose a username (e.g., `noctem_assistant_bot`)
5. **Copy the API token** - looks like `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`

### 2. Get Your Chat ID

1. Start a chat with your new bot (send any message)
2. Visit: `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
3. Find `"chat":{"id":123456789}` - that number is your chat ID

### 3. Configure Noctem

Edit `data/config.json`:
```json
{
    "telegram_token": "YOUR_BOT_TOKEN_HERE",
    "telegram_chat_id": "YOUR_CHAT_ID_HERE",
    "model": "qwen2.5:7b",
    "router_model": "qwen2.5:1.5b",
    "timezone": "America/Los_Angeles"
}
```

---

## Start Noctem

```bash
cd ~/data/noctem
python3 main.py
```

Or in headless/daemon mode:
```bash
python3 main.py --headless
```

---

## Test It!

Send a message to your bot on Telegram:
```
/ping
```

You should get `pong` back.

Try other commands:
```
/tasks           # List tasks
/add Buy milk    # Add a task
/done 1          # Complete task #1
/morning         # Get morning briefing
/help            # See all commands
```

---

## Optional: Auto-Start on Boot

```bash
# Copy service file
sudo cp scripts/noctem.service /etc/systemd/system/

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable noctem
sudo systemctl start noctem
```

---

## Optional: Morning Reports at 8am

```bash
sudo cp scripts/noctem-morning.service /etc/systemd/system/
sudo cp scripts/noctem-morning.timer /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable noctem-morning.timer
sudo systemctl start noctem-morning.timer

# Verify
sudo systemctl list-timers | grep noctem
```

---

## File Locations

- Config: `~/data/noctem/data/config.json`
- Database: `~/data/noctem/data/noctem.db`
- Logs: `/tmp/noctem.log`

---

## Stopping Noctem

```bash
# If running in foreground: Ctrl+C

# If using systemd:
sudo systemctl stop noctem
```

---

## Troubleshooting

### Noctem not responding
```bash
# Check if running
pgrep -f "python3.*main.py"

# Check logs
tail -50 /tmp/noctem.log
```

### Test locally without Telegram
```bash
cd ~/data/noctem
python3 main.py -c "hello"
```

### Test morning report
```bash
python3 -c "from utils.morning_report import generate_morning_report; print(generate_morning_report())"
```

---

## Commands Reference

| Command | Description |
|---------|-------------|
| `/ping` | Test - responds "pong" |
| `/tasks` | List pending tasks |
| `/add <title>` | Add a task |
| `/add <title> in <project>` | Add task to project |
| `/done <id>` | Complete a task |
| `/morning` | Morning briefing |
| `/status` | System status |
| `/help` | Show all commands |

---

*Noctem Personal MVP v0.5*
