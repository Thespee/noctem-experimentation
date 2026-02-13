# Noctem v0.5 - Setup Guide

Complete guide to setting up Noctem from scratch on a fresh Ubuntu system.

## Prerequisites

- Ubuntu 22.04+ (or similar Linux distribution)
- Python 3.11+
- Internet connection (for Telegram bot)

## Step 1: System Dependencies

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip git
```

## Step 2: Create Virtual Environment

```bash
# Create venv in home directory (recommended)
python3 -m venv ~/noctem_venv

# Activate it
source ~/noctem_venv/bin/activate
```

## Step 3: Get the Code

Either clone from your repository or copy the `NOCTEM_0.5` folder to your machine.

```bash
# Example: copy from USB
cp -r /media/user/USB/NOCTEM_0.5 ~/noctem
cd ~/noctem
```

## Step 4: Install Python Dependencies

```bash
# Make sure venv is activated
source ~/noctem_venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

**Required packages:**
- `python-telegram-bot>=20.0` - Telegram bot framework
- `APScheduler>=3.10` - Job scheduling
- `flask>=3.0` - Web dashboard
- `icalendar` - ICS calendar parsing
- `requests` - HTTP requests for calendar URLs
- `qrcode[pil]` - QR code generation

## Step 5: Initialize Database

```bash
python -m noctem.main init
```

This creates:
- `noctem/data/noctem.db` - SQLite database
- `noctem/data/logs/` - Log directory
- Default configuration values

## Step 6: Create Telegram Bot

1. Open Telegram and message [@BotFather](https://t.me/BotFather)
2. Send `/newbot`
3. Choose a name (e.g., "My Noctem")
4. Choose a username (e.g., "my_noctem_bot")
5. Copy the **API token** BotFather gives you

## Step 7: Configure Noctem

```bash
# Start CLI
python -m noctem.cli

# Set your bot token
> set telegram_bot_token YOUR_TOKEN_HERE

# Set your timezone (optional, defaults to America/Vancouver)
> set timezone America/Vancouver

# Set morning briefing time (optional, defaults to 07:00)
> set morning_message_time 07:00

# Exit CLI
> exit
```

## Step 8: First Run

```bash
# Start with QR code display (recommended)
bash start.sh

# Or start with verbose output
bash start.sh all
```

**First time setup:**
1. Open Telegram and message your bot
2. Send `/start` - this registers your chat ID
3. Try adding a task: `buy groceries tomorrow !1`

## Step 9: Import Your Calendar

1. Open the web dashboard: `http://localhost:5000/calendar`
2. Add your calendar URL (from Google Calendar, Apple, etc.)
3. Click "Add Calendar" - it will be saved for easy refresh

**Getting calendar URLs:**
- **Google Calendar**: Settings → [calendar] → Integrate → Secret address in iCal format
- **Apple Calendar**: Share calendar → Public Calendar → Copy URL
- **Outlook**: Calendar settings → Shared calendars → Publish → ICS link

## Step 10: Run as Service (Optional)

Create a systemd service for auto-start:

```bash
sudo nano /etc/systemd/system/noctem.service
```

```ini
[Unit]
Description=Noctem Executive Assistant
After=network.target

[Service]
Type=simple
User=YOUR_USERNAME
WorkingDirectory=/home/YOUR_USERNAME/noctem
ExecStart=/home/YOUR_USERNAME/noctem_venv/bin/python -m noctem.main all --quiet
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable noctem
sudo systemctl start noctem

# Check status
sudo systemctl status noctem

# View logs
journalctl -u noctem -f
```

## Configuration Reference

| Key | Default | Description |
|-----|---------|-------------|
| `telegram_bot_token` | (required) | From BotFather |
| `telegram_chat_id` | (auto-set) | Set when you /start the bot |
| `timezone` | America/Vancouver | Your timezone |
| `morning_message_time` | 07:00 | When to send daily briefing |
| `web_host` | 0.0.0.0 | Web server bind address |
| `web_port` | 5000 | Web server port |

## Troubleshooting

### Bot not responding
- Check token is correct: `python -m noctem.cli` then `config`
- Check internet connection
- Look at logs: `tail -f noctem/data/logs/noctem.log`

### Web dashboard not accessible from phone
- Make sure `web_host` is `0.0.0.0` (not `127.0.0.1`)
- Check firewall: `sudo ufw allow 5000`
- Use your computer's local IP, not `localhost`

### Calendar events not showing
- Refresh calendars at `/calendar`
- Check timezone settings
- Events must be within 2 weeks past to 30 days future

### Morning briefing not sending
- Check `morning_message_time` is set correctly
- Verify `telegram_chat_id` is set (send `/start` to bot)
- Check scheduler is running in logs

## Updating

```bash
# Stop service if running
sudo systemctl stop noctem

# Update code (copy new files or git pull)

# Reinstall dependencies if needed
source ~/noctem_venv/bin/activate
pip install -r requirements.txt

# Restart
sudo systemctl start noctem
```

## Backup

The entire system state is in one file:
```bash
cp noctem/data/noctem.db noctem_backup_$(date +%Y%m%d).db
```
