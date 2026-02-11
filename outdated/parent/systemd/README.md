# Systemd Setup for Noctem Babysitting

These systemd unit files automate the babysitting reports and self-improvement analysis.

## Installation

1. **Edit the service file** to set correct paths:
   ```bash
   # Edit noctem-babysit.service
   # Replace /path/to/noctem with your actual Noctem directory
   ```

2. **Copy files to systemd user directory**:
   ```bash
   mkdir -p ~/.config/systemd/user/
   cp noctem-babysit.timer ~/.config/systemd/user/
   cp noctem-babysit.service ~/.config/systemd/user/
   ```

3. **Reload systemd**:
   ```bash
   systemctl --user daemon-reload
   ```

4. **Enable and start the timer**:
   ```bash
   systemctl --user enable noctem-babysit.timer
   systemctl --user start noctem-babysit.timer
   ```

5. **Verify it's running**:
   ```bash
   systemctl --user status noctem-babysit.timer
   systemctl --user list-timers
   ```

## Manual Run

To run babysitting manually:
```bash
systemctl --user start noctem-babysit.service
```

Or directly:
```bash
python3 /path/to/noctem/parent/scheduler.py --report --analyze
```

## Logs

View logs:
```bash
journalctl --user -u noctem-babysit.service -f
```

## Uninstall

```bash
systemctl --user stop noctem-babysit.timer
systemctl --user disable noctem-babysit.timer
rm ~/.config/systemd/user/noctem-babysit.*
systemctl --user daemon-reload
```

## Alternative: Cron

If you prefer cron over systemd:

```bash
# Edit crontab
crontab -e

# Add this line (runs every 6 hours)
0 */6 * * * /usr/bin/python3 /path/to/noctem/parent/scheduler.py --report --analyze >> /tmp/noctem-babysit.log 2>&1
```
