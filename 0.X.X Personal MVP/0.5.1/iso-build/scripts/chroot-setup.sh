#!/bin/bash
# Noctem ISO - Chroot Setup Script
# Run this inside Cubic's chroot environment
#
# Usage: Copy this script and the overlay/ + noctem-source/ directories
#        into the chroot, then run this script.

set -e

echo "╔══════════════════════════════════════╗"
echo "║  Noctem ISO Build - Chroot Setup     ║"
echo "╚══════════════════════════════════════╝"
echo ""

# Expect to be run from directory containing overlay/ and noctem-source/
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$(dirname "$SCRIPT_DIR")"

if [ ! -d "$BUILD_DIR/overlay" ] || [ ! -d "$BUILD_DIR/noctem-source" ]; then
    echo "ERROR: Run from iso-build directory with overlay/ and noctem-source/"
    exit 1
fi

echo "[1/7] Updating system packages..."
apt update
apt upgrade -y

echo ""
echo "[2/7] Installing system dependencies..."
apt install -y \
    python3 python3-venv python3-pip \
    network-manager \
    openssh-server \
    curl wget \
    fonts-dejavu-core

# For server ISO, remove any desktop packages if present
apt remove -y \
    ubuntu-desktop* \
    gnome-* \
    --autoremove 2>/dev/null || true

apt clean

echo ""
echo "[3/7] Creating noctem user..."
if ! id "noctem" &>/dev/null; then
    useradd -m -s /bin/bash noctem
    echo "noctem:noctem" | chpasswd
    # Add to sudo group for first-run reboot
    usermod -aG sudo noctem
fi

echo ""
echo "[4/7] Setting up Python virtual environment..."
su - noctem << 'VENV_EOF'
python3 -m venv ~/noctem_venv
source ~/noctem_venv/bin/activate
pip install --upgrade pip
pip install \
    "python-telegram-bot>=20.0" \
    "APScheduler>=3.10" \
    "flask>=3.0" \
    "jinja2>=3.0" \
    "icalendar>=5.0" \
    "requests>=2.28" \
    "qrcode[pil]>=7.0" \
    "python-dateutil>=2.8"
VENV_EOF

echo ""
echo "[5/7] Installing Noctem application..."
cp -r "$BUILD_DIR/noctem-source" /home/noctem/noctem
chown -R noctem:noctem /home/noctem/noctem

echo ""
echo "[6/7] Installing overlay files..."

# Systemd service
cp "$BUILD_DIR/overlay/etc/systemd/system/noctem.service" /etc/systemd/system/
systemctl enable noctem

# Auto-login
mkdir -p /etc/systemd/system/getty@tty1.service.d
cp "$BUILD_DIR/overlay/etc/systemd/system/getty@tty1.service.d/autologin.conf" \
   /etc/systemd/system/getty@tty1.service.d/

# NetworkManager
mkdir -p /etc/NetworkManager/system-connections
cp "$BUILD_DIR/overlay/etc/NetworkManager/system-connections/auto-ethernet.nmconnection" \
   /etc/NetworkManager/system-connections/
chmod 600 /etc/NetworkManager/system-connections/*.nmconnection
systemctl enable NetworkManager

# Helper scripts
cp "$BUILD_DIR/overlay/usr/local/bin/noctem-wifi" /usr/local/bin/
cp "$BUILD_DIR/overlay/usr/local/bin/noctem-logs" /usr/local/bin/
cp "$BUILD_DIR/overlay/usr/local/bin/noctem-cli" /usr/local/bin/
chmod +x /usr/local/bin/noctem-*

# User home files
cp "$BUILD_DIR/overlay/home/noctem/.bash_profile" /home/noctem/
cp "$BUILD_DIR/overlay/home/noctem/first-run.sh" /home/noctem/
chmod +x /home/noctem/first-run.sh
chown noctem:noctem /home/noctem/.bash_profile /home/noctem/first-run.sh

echo ""
echo "[7/7] Enabling SSH for remote access..."
systemctl enable ssh

echo ""
echo "╔══════════════════════════════════════╗"
echo "║  ✓ Chroot setup complete!            ║"
echo "╚══════════════════════════════════════╝"
echo ""
echo "Next steps in Cubic:"
echo "1. Exit the chroot (type 'exit')"
echo "2. Click 'Next' to customize boot/kernel options"
echo "3. Generate the ISO"
echo ""
echo "Default credentials:"
echo "  User: noctem"
echo "  Pass: noctem"
echo ""
