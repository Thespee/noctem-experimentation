#!/bin/bash
# =============================================================================
# Noctem 0.5.0 - Cubic Chroot Setup Script
# =============================================================================
# Run this script INSIDE the Cubic chroot environment.
# 
# Before running:
# 1. Copy this script and the noctem/ directory to somewhere accessible
#    (e.g., /tmp/noctem-build/)
# 2. In Cubic chroot, run: bash /tmp/noctem-build/setup-chroot.sh
# =============================================================================

set -e  # Exit on error

echo "==========================================="
echo "  Noctem 0.5.0 - Chroot Setup"
echo "==========================================="
echo ""

# Where is the noctem source code?
NOCTEM_SOURCE="${NOCTEM_SOURCE:-/tmp/noctem-build/noctem}"

if [ ! -d "$NOCTEM_SOURCE" ]; then
    echo "ERROR: Noctem source not found at $NOCTEM_SOURCE"
    echo "Copy the noctem/ directory there first, or set NOCTEM_SOURCE"
    exit 1
fi

# -----------------------------------------------------------------------------
# Step 1: Update system and install packages
# -----------------------------------------------------------------------------
echo "[1/8] Installing system packages..."
apt update
apt upgrade -y

apt install -y \
    python3 python3-venv python3-pip \
    network-manager \
    openssh-server \
    git curl wget \
    fonts-dejavu-core

apt clean

# -----------------------------------------------------------------------------
# Step 2: Create noctem user
# -----------------------------------------------------------------------------
echo "[2/8] Creating noctem user..."
if id "noctem" &>/dev/null; then
    echo "  User 'noctem' already exists, skipping..."
else
    useradd -m -s /bin/bash noctem
    echo "noctem:noctem" | chpasswd
    usermod -aG sudo noctem
    echo "  User 'noctem' created with password 'noctem'"
fi

# -----------------------------------------------------------------------------
# Step 3: Create Python virtual environment
# -----------------------------------------------------------------------------
echo "[3/8] Setting up Python virtual environment..."
su - noctem << 'VENV_EOF'
python3 -m venv ~/noctem_venv
source ~/noctem_venv/bin/activate
pip install --upgrade pip
pip install \
    python-telegram-bot>=20.0 \
    APScheduler>=3.10 \
    flask>=3.0 \
    jinja2>=3.0 \
    icalendar>=5.0 \
    requests>=2.28 \
    qrcode[pil]>=7.0 \
    python-dateutil>=2.8
VENV_EOF
echo "  Virtual environment created at /home/noctem/noctem_venv"

# -----------------------------------------------------------------------------
# Step 4: Copy Noctem code
# -----------------------------------------------------------------------------
echo "[4/8] Copying Noctem code..."
mkdir -p /home/noctem/noctem
cp -r "$NOCTEM_SOURCE"/* /home/noctem/noctem/
chown -R noctem:noctem /home/noctem
echo "  Noctem code copied to /home/noctem/noctem"

# -----------------------------------------------------------------------------
# Step 5: Create systemd service
# -----------------------------------------------------------------------------
echo "[5/8] Creating systemd service..."
cat > /etc/systemd/system/noctem.service << 'SERVICE_EOF'
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
SERVICE_EOF

systemctl enable noctem
echo "  Noctem service enabled"

# Enable other services
systemctl enable NetworkManager
systemctl enable ssh
echo "  NetworkManager and SSH enabled"

# -----------------------------------------------------------------------------
# Step 6: Setup auto-login
# -----------------------------------------------------------------------------
echo "[6/8] Configuring auto-login..."
mkdir -p /etc/systemd/system/getty@tty1.service.d
cat > /etc/systemd/system/getty@tty1.service.d/autologin.conf << 'AUTOLOGIN_EOF'
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin noctem --noclear %I $TERM
AUTOLOGIN_EOF
echo "  Auto-login configured for tty1"

# -----------------------------------------------------------------------------
# Step 7: Create login display script
# -----------------------------------------------------------------------------
echo "[7/8] Creating login display script..."
cat > /home/noctem/.bash_profile << 'PROFILE_EOF'
#!/bin/bash
# Noctem 0.5.0 - Login Display

# Wait for network and services
sleep 3

clear
echo "==========================================="
echo "  NOCTEM v0.5.0"
echo "  Executive Assistant"
echo "==========================================="
echo ""

# Get IP address
IP=$(hostname -I | awk '{print $1}')
if [ -z "$IP" ]; then
    echo "Network: Not connected"
    echo ""
    echo "Run 'noctem-wifi' to connect to WiFi"
else
    echo "Dashboard: http://$IP:5000"
    echo "Settings:  http://$IP:5000/settings"
    echo ""
    
    # Generate QR code
    source ~/noctem_venv/bin/activate
    python3 -c "
import qrcode
qr = qrcode.QRCode(box_size=1, border=2)
qr.add_data('http://$IP:5000/')
qr.make()
qr.print_ascii(invert=True)
" 2>/dev/null || echo "(QR code unavailable)"
fi

echo ""
echo "Scan QR code or visit URL to open dashboard"
echo "Configure via Settings page in browser"
echo ""
echo "Commands: noctem-wifi, noctem-cli, noctem-logs"
echo "Press Ctrl+C for shell"
echo "==========================================="

# Keep terminal open
read -r -d '' _ </dev/tty
PROFILE_EOF

chown noctem:noctem /home/noctem/.bash_profile
chmod +x /home/noctem/.bash_profile
echo "  Login script created"

# -----------------------------------------------------------------------------
# Step 8: Create helper scripts
# -----------------------------------------------------------------------------
echo "[8/8] Creating helper scripts..."

# WiFi helper
cat > /usr/local/bin/noctem-wifi << 'WIFI_EOF'
#!/bin/bash
echo "==========================================="
echo "  Noctem WiFi Setup"
echo "==========================================="
echo ""
echo "Available WiFi networks:"
echo ""
nmcli device wifi list
echo ""
read -p "Network name (SSID): " SSID
read -s -p "Password: " PASS
echo ""
echo "Connecting..."
nmcli device wifi connect "$SSID" password "$PASS"

if [ $? -eq 0 ]; then
    echo "Connected successfully!"
    IP=$(hostname -I | awk '{print $1}')
    echo "IP Address: $IP"
    echo "Dashboard: http://$IP:5000"
else
    echo "Connection failed. Please try again."
fi
WIFI_EOF
chmod +x /usr/local/bin/noctem-wifi

# CLI helper
cat > /usr/local/bin/noctem-cli << 'CLI_EOF'
#!/bin/bash
source /home/noctem/noctem_venv/bin/activate
cd /home/noctem/noctem
python -m noctem.cli
CLI_EOF
chmod +x /usr/local/bin/noctem-cli

# Logs helper
cat > /usr/local/bin/noctem-logs << 'LOGS_EOF'
#!/bin/bash
echo "=== Noctem Service Logs ==="
journalctl -u noctem -f
LOGS_EOF
chmod +x /usr/local/bin/noctem-logs

echo "  Helper scripts created in /usr/local/bin/"

# -----------------------------------------------------------------------------
# Done!
# -----------------------------------------------------------------------------
echo ""
echo "==========================================="
echo "  Setup Complete!"
echo "==========================================="
echo ""
echo "Next steps in Cubic:"
echo "  1. Exit the chroot"
echo "  2. Click through the remaining tabs"
echo "  3. Generate the ISO"
echo ""
echo "After generating ISO:"
echo "  1. Boot from ISO (use another USB or VM)"
echo "  2. Install Ubuntu to your target USB drive"
echo "  3. Boot from target USB"
echo "  4. Open http://<IP>:5000/settings to configure"
echo ""
echo "Default login: noctem / noctem"
echo "==========================================="
