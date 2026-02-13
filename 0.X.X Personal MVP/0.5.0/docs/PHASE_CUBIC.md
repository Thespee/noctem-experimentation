# Noctem - Custom Ubuntu ISO Phase

Create a distributable Ubuntu-based ISO with Noctem pre-installed for easy deployment on any machine.

## Overview

**Goal:** Boot any computer from USB → Noctem running immediately with QR code displayed.

**Tool:** [Cubic](https://github.com/PJ-Singh-001/Cubic) - Custom Ubuntu ISO Creator

## Why Custom ISO?

1. **Zero Setup** - Boot and run, no installation needed
2. **Portable** - Run Noctem on any computer
3. **Kiosk Mode** - Dedicated executive assistant terminal
4. **Backup** - Known-good system state, easy to recreate
5. **Privacy** - No data in cloud, runs locally

## Prerequisites

- Ubuntu desktop (for running Cubic)
- 8GB+ USB drive for the ISO
- Ubuntu 22.04 LTS base ISO

## Phase 1: Base System Customization

### Install Cubic

```bash
sudo apt-add-repository universe
sudo apt-add-repository ppa:cubic-wizard/release
sudo apt update
sudo apt install cubic
```

### Create Custom ISO

1. Launch Cubic
2. Select project directory
3. Choose Ubuntu 22.04 LTS minimal/server as base
4. Enter chroot environment

### In Chroot - System Setup

```bash
# Update system
apt update && apt upgrade -y

# Install minimal dependencies
apt install -y \
    python3 python3-venv python3-pip \
    network-manager \
    openssh-server \
    git curl wget \
    fonts-dejavu-core

# Remove unnecessary packages (slim down)
apt remove -y \
    libreoffice* \
    thunderbird* \
    firefox* \
    gnome-games* \
    --autoremove

apt clean
```

## Phase 2: Noctem Installation

### In Chroot - Install Noctem

```bash
# Create noctem user
useradd -m -s /bin/bash noctem
echo "noctem:noctem" | chpasswd

# Create venv and install dependencies
su - noctem << 'EOF'
python3 -m venv ~/noctem_venv
source ~/noctem_venv/bin/activate
pip install \
    python-telegram-bot>=20.0 \
    APScheduler>=3.10 \
    flask>=3.0 \
    icalendar \
    requests \
    qrcode[pil]
EOF

# Copy Noctem code
mkdir -p /home/noctem/noctem
# (Copy noctem/ directory here during build)

chown -R noctem:noctem /home/noctem
```

### Auto-Start Configuration

Create systemd service:

```bash
cat > /etc/systemd/system/noctem.service << 'EOF'
[Unit]
Description=Noctem Executive Assistant
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=noctem
WorkingDirectory=/home/noctem/noctem
ExecStart=/home/noctem/noctem_venv/bin/python -m noctem.main all --quiet
Restart=always
RestartSec=5
StandardOutput=null
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl enable noctem
```

### Console Auto-Login

For kiosk mode - auto-login to show QR code:

```bash
# Auto-login on tty1
mkdir -p /etc/systemd/system/getty@tty1.service.d
cat > /etc/systemd/system/getty@tty1.service.d/autologin.conf << 'EOF'
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin noctem --noclear %I $TERM
EOF
```

### Login Script

```bash
cat > /home/noctem/.bash_profile << 'EOF'
# Wait for network
echo "Waiting for network..."
sleep 5

# Clear and show status
clear
echo "=================================="
echo "  NOCTEM v0.5"
echo "  Executive Assistant"
echo "=================================="
echo ""

# Get IP and show QR
IP=$(hostname -I | awk '{print $1}')
echo "Dashboard: http://$IP:5000"
echo ""

# Generate QR code
source ~/noctem_venv/bin/activate
python3 -c "
import qrcode
qr = qrcode.QRCode(box_size=1, border=2)
qr.add_data('http://$IP:5000/')
qr.make()
qr.print_ascii(invert=True)
"

echo ""
echo "Scan QR code to open dashboard"
echo "Telegram bot active (if configured)"
echo ""
echo "Press Ctrl+C to access shell"
echo "=================================="

# Keep terminal open
read -r -d '' _ </dev/tty
EOF

chown noctem:noctem /home/noctem/.bash_profile
```

## Phase 3: Network Configuration

### NetworkManager Setup

```bash
# Enable NetworkManager
systemctl enable NetworkManager

# Create default connection (DHCP)
cat > /etc/NetworkManager/system-connections/auto-ethernet.nmconnection << 'EOF'
[connection]
id=auto-ethernet
type=ethernet
autoconnect=true

[ipv4]
method=auto

[ipv6]
method=auto
EOF

chmod 600 /etc/NetworkManager/system-connections/*.nmconnection
```

### WiFi Configuration Script

Create a helper script for WiFi setup:

```bash
cat > /usr/local/bin/noctem-wifi << 'EOF'
#!/bin/bash
echo "Available WiFi networks:"
nmcli device wifi list
echo ""
read -p "Network name (SSID): " SSID
read -s -p "Password: " PASS
echo ""
nmcli device wifi connect "$SSID" password "$PASS"
EOF

chmod +x /usr/local/bin/noctem-wifi
```

## Phase 4: First-Run Configuration

### Setup Wizard

Create first-run setup for Telegram token:

```bash
cat > /home/noctem/first-run.sh << 'EOF'
#!/bin/bash
CONFIG_FLAG="/home/noctem/.noctem_configured"

if [ -f "$CONFIG_FLAG" ]; then
    exit 0
fi

clear
echo "========================================"
echo "  NOCTEM - First Time Setup"
echo "========================================"
echo ""

# Telegram token
echo "Get a Telegram bot token from @BotFather"
echo ""
read -p "Telegram Bot Token: " TOKEN

if [ -n "$TOKEN" ]; then
    source ~/noctem_venv/bin/activate
    cd ~/noctem
    python3 -c "
from noctem.config import Config
Config.set('telegram_bot_token', '$TOKEN')
print('Token saved!')
"
fi

# Timezone
echo ""
read -p "Timezone [America/Vancouver]: " TZ
TZ=${TZ:-America/Vancouver}
source ~/noctem_venv/bin/activate
cd ~/noctem
python3 -c "
from noctem.config import Config
Config.set('timezone', '$TZ')
"

# Mark as configured
touch "$CONFIG_FLAG"

echo ""
echo "Setup complete! Rebooting..."
sleep 3
sudo reboot
EOF

chmod +x /home/noctem/first-run.sh
chown noctem:noctem /home/noctem/first-run.sh

# Run first-run before main profile
echo '/home/noctem/first-run.sh' >> /home/noctem/.bashrc
```

## Phase 5: Finalize ISO

### In Cubic

1. Exit chroot
2. Remove unnecessary files (apt cache, logs)
3. Generate ISO
4. Test in VM first!

### Estimated ISO Size

- Base Ubuntu minimal: ~1.5GB
- Python + venv: ~500MB
- Noctem code: ~5MB
- **Total: ~2GB**

## Usage

### Create Bootable USB

```bash
# Find USB device
lsblk

# Write ISO (replace sdX)
sudo dd if=noctem-ubuntu.iso of=/dev/sdX bs=4M status=progress
sync
```

### Boot Sequence

1. Boot from USB
2. First run: Enter Telegram token, timezone
3. Reboot
4. QR code appears automatically
5. Scan with phone to access dashboard

## Advanced Options

### Persistent Storage

For saving data across reboots, create a persistence partition:

```bash
# During USB creation, add a persistence partition
# Label it "casper-rw"
```

### Read-Only Mode

For kiosk deployments, mount root as read-only:

```bash
# Add to kernel parameters
overlayroot=tmpfs
```

### Remote Management

Enable SSH for remote configuration:

```bash
# In chroot
systemctl enable ssh
# Set up authorized_keys for noctem user
```

## Testing Checklist

- [ ] Boots to login screen
- [ ] Auto-login works
- [ ] Network connects (Ethernet)
- [ ] WiFi setup works
- [ ] QR code displays correctly
- [ ] Web dashboard accessible
- [ ] Telegram bot responds
- [ ] Morning briefing sends
- [ ] Survives reboot
- [ ] First-run wizard works on fresh boot

## Future Enhancements

- **Touch screen support** - For tablet/kiosk mode
- **Local display dashboard** - Show dashboard on connected monitor
- **Hardware buttons** - Physical buttons for quick actions
- **E-ink display** - Low-power always-on dashboard
- **Raspberry Pi image** - Dedicated hardware appliance
