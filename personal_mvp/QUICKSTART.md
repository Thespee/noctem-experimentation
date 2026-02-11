# Noctem Personal MVP - Quick Start Guide

Get Noctem running on your Ubuntu Server USB in 10-15 minutes.

## Prerequisites

- Ubuntu Server running on the USB
- SSH access from another machine
- A phone with Signal installed

---

## Step 1: Pull Latest Code (1 min)

```bash
cd ~/data/noctem
git pull
```

---

## Step 2: Set Up Signal (10 min)

```bash
chmod +x scripts/setup_signal.sh
./scripts/setup_signal.sh
```

Choose option 1 (Link as secondary device) and:
1. Open Signal on your phone
2. Go to Settings → Linked Devices → Link New Device
3. Scan the QR code shown in the terminal

---

## Step 3: Configure (2 min)

```bash
# Create config from example
cp data/config.example.json data/config.json

# Edit with your phone number
nano data/config.json
```

Change `+1YOURNUMBER` to your actual Signal phone number (with country code).

---

## Step 4: Start Noctem (1 min)

```bash
chmod +x scripts/start_noctem.sh scripts/stop_noctem.sh
./scripts/start_noctem.sh
```

---

## Step 5: Test! (1 min)

Send a Signal message to your phone number:
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
# Copy service files
sudo cp scripts/signal-daemon.service /etc/systemd/system/
sudo cp scripts/noctem.service /etc/systemd/system/

# Edit signal-daemon.service to set your phone number
sudo nano /etc/systemd/system/signal-daemon.service
# Replace SIGNAL_PHONE_PLACEHOLDER with +1YOURNUMBER

# Enable services
sudo systemctl daemon-reload
sudo systemctl enable signal-daemon noctem
sudo systemctl start signal-daemon noctem
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

| What | Where |
|------|-------|
| Config | `~/data/noctem/data/config.json` |
| Database | `~/data/noctem/data/noctem.db` |
| Logs | `/tmp/noctem.log`, `/tmp/signal-daemon.log` |
| Birthdays | `/mnt/shared/birthdays.csv` |
| Calendar | `/mnt/shared/calendar/calendar.ics` |

---

## Stopping Noctem

```bash
./scripts/stop_noctem.sh
```

Or if using systemd:
```bash
sudo systemctl stop noctem signal-daemon
```

---

## Troubleshooting

### Signal not responding
```bash
# Check if signal-cli daemon is running
pgrep -f "signal-cli.*daemon"

# Check logs
tail -50 /tmp/signal-daemon.log
```

### Noctem not responding
```bash
# Check if running
pgrep -f "python3.*main.py"

# Check logs
tail -50 /tmp/noctem.log
```

### Test locally without Signal
```bash
cd ~/data/noctem
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
