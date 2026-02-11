#!/bin/bash
# Signal CLI Setup for Headless Server
# This script helps set up signal-cli without a GUI

set -e

SIGNAL_CLI_VERSION="0.13.4"
INSTALL_DIR="/opt/signal-cli"
DATA_DIR="$HOME/.local/share/signal-cli"

echo "=== Noctem Signal Setup ==="
echo ""

# Check for Java
if ! command -v java &> /dev/null; then
    echo "Installing Java..."
    sudo apt update
    sudo apt install -y default-jre-headless
fi

# Check for qrencode (for terminal QR codes)
if ! command -v qrencode &> /dev/null; then
    echo "Installing qrencode for terminal QR display..."
    sudo apt install -y qrencode
fi

# Download signal-cli if not present
if [ ! -f "$INSTALL_DIR/bin/signal-cli" ]; then
    echo "Downloading signal-cli v${SIGNAL_CLI_VERSION}..."
    
    sudo mkdir -p "$INSTALL_DIR"
    cd /tmp
    
    wget -q "https://github.com/AsamK/signal-cli/releases/download/v${SIGNAL_CLI_VERSION}/signal-cli-${SIGNAL_CLI_VERSION}.tar.gz"
    sudo tar xf "signal-cli-${SIGNAL_CLI_VERSION}.tar.gz" -C "$INSTALL_DIR" --strip-components=1
    rm "signal-cli-${SIGNAL_CLI_VERSION}.tar.gz"
    
    # Add to PATH
    sudo ln -sf "$INSTALL_DIR/bin/signal-cli" /usr/local/bin/signal-cli
    
    echo "signal-cli installed!"
fi

echo ""
echo "signal-cli version: $(signal-cli --version)"
echo ""

# Setup options
echo "Choose setup method:"
echo "  1) Link as secondary device (scan QR from your phone)"
echo "  2) Register new number (requires CAPTCHA)"
echo "  3) Test existing setup"
echo ""
read -p "Enter choice [1/2/3]: " choice

case $choice in
    1)
        echo ""
        echo "=== Linking as Secondary Device ==="
        echo ""
        echo "On your phone:"
        echo "  Signal > Settings > Linked Devices > Link New Device"
        echo ""
        echo "Then scan this QR code (will appear below):"
        echo ""
        
        # Generate link URI and display as terminal QR
        LINK_OUTPUT=$(signal-cli link -n "noctem-server" 2>&1)
        
        # Extract the URI
        LINK_URI=$(echo "$LINK_OUTPUT" | grep -o 'sgnl://linkdevice.*' | head -1)
        
        if [ -n "$LINK_URI" ]; then
            # Display QR in terminal
            echo "$LINK_URI" | qrencode -t ANSIUTF8
            echo ""
            echo "URI: $LINK_URI"
            echo ""
            echo "Waiting for link confirmation..."
            
            # The link command should complete after scanning
            wait
        else
            echo "Error generating link. Output was:"
            echo "$LINK_OUTPUT"
        fi
        ;;
        
    2)
        echo ""
        echo "=== Registering New Number ==="
        echo ""
        read -p "Enter phone number (with country code, e.g., +1555123456): " PHONE
        
        echo ""
        echo "You need a CAPTCHA token. Get one from:"
        echo "  https://signalcaptchas.org/registration/generate.html"
        echo ""
        echo "Complete the CAPTCHA, then copy the signalcaptcha:// link"
        echo ""
        read -p "Paste CAPTCHA token: " CAPTCHA
        
        echo ""
        echo "Registering..."
        signal-cli -a "$PHONE" register --captcha "$CAPTCHA"
        
        echo ""
        read -p "Enter verification code from SMS: " CODE
        
        signal-cli -a "$PHONE" verify "$CODE"
        
        echo ""
        echo "Registration complete! Your number: $PHONE"
        ;;
        
    3)
        echo ""
        echo "=== Testing Existing Setup ==="
        echo ""
        
        # Find registered accounts
        if [ -d "$DATA_DIR/data" ]; then
            echo "Found accounts:"
            ls -1 "$DATA_DIR/data/" 2>/dev/null | grep -v "+" || echo "  (none)"
        fi
        
        read -p "Enter your phone number to test: " PHONE
        
        echo ""
        echo "Sending test message to yourself..."
        signal-cli -a "$PHONE" send -m "Noctem test message $(date)" "$PHONE"
        
        echo ""
        echo "If you received the message, setup is working!"
        ;;
        
    *)
        echo "Invalid choice"
        exit 1
        ;;
esac

echo ""
echo "=== Next Steps ==="
echo ""
echo "1. Save your phone number in config:"
echo "   Edit ~/data/noctem/data/config.json"
echo "   Set: \"signal_phone\": \"+1YOURNUMBER\""
echo ""
echo "2. Start the signal-cli daemon:"
echo "   signal-cli -a +1YOURNUMBER daemon --tcp 127.0.0.1:7583"
echo ""
echo "3. Start Noctem:"
echo "   cd ~/data/noctem && python3 main.py"
echo ""
echo "For systemd service, see: scripts/noctem.service"
