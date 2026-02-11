#!/bin/bash
# Moltbot Quick Setup - Signal Chat Edition
# Run this after fresh Ubuntu Server install
# Usage: bash quick-setup.sh

set -o pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() { echo -e "${GREEN}[+]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# Check if running as root (shouldn't be)
if [[ $EUID -eq 0 ]]; then
    error "Don't run as root. Run as your normal user."
fi

echo "============================================"
echo "  Moltbot Quick Setup - Signal Chat Edition"
echo "============================================"
echo ""

# Get user's phone number for Signal
read -p "Enter your phone number for Signal (e.g., +15551234567): " SIGNAL_PHONE
if [[ ! "$SIGNAL_PHONE" =~ ^\+[0-9]{10,15}$ ]]; then
    error "Invalid phone number format. Use international format: +1XXXXXXXXXX"
fi

echo ""
log "Phone number: $SIGNAL_PHONE"
echo ""

# ============================================
# PART 1: System Update and Packages
# ============================================
log "Updating system..."
sudo apt update && sudo apt upgrade -y

log "Installing required packages..."
sudo apt install -y \
    curl wget git vim \
    python3 python3-pip python3-venv \
    ufw htop \
    ca-certificates gnupg \
    jq bc \
    openjdk-21-jre-headless

# ============================================
# PART 2: Install Ollama
# ============================================
log "Installing Ollama..."
curl -fsSL https://ollama.com/install.sh | sh

log "Configuring Ollama for minimal resources..."
sudo mkdir -p /etc/systemd/system/ollama.service.d/
sudo tee /etc/systemd/system/ollama.service.d/override.conf > /dev/null << 'EOF'
[Service]
Environment="OLLAMA_HOST=127.0.0.1:11434"
Environment="OLLAMA_NUM_PARALLEL=1"
Environment="OLLAMA_MAX_LOADED_MODELS=1"
Environment="OLLAMA_FLASH_ATTENTION=1"
EOF

sudo systemctl daemon-reload
sudo systemctl restart ollama
sudo systemctl enable ollama

# Wait for Ollama to start
log "Waiting for Ollama to start..."
sleep 5
until curl -s http://localhost:11434/api/tags > /dev/null 2>&1; do
    sleep 2
done

log "Pulling minimal model (this may take a few minutes)..."
ollama pull qwen2.5:1.5b-instruct-q4_K_M

log "Creating router model..."
cat > /tmp/router.Modelfile << 'EOF'
FROM qwen2.5:1.5b-instruct-q4_K_M

SYSTEM """You are a helpful AI assistant. Be concise and direct. 
Keep responses brief - you're communicating over Signal where shorter is better.
If you don't know something, say so. Don't make things up."""

PARAMETER num_ctx 2048
PARAMETER temperature 0.7
PARAMETER num_thread 2
EOF

ollama create router -f /tmp/router.Modelfile
rm /tmp/router.Modelfile

# ============================================
# PART 3: Directory Structure
# ============================================
log "Creating directory structure..."
mkdir -p ~/moltbot-system/{config,data,logs,security}

# ============================================
# PART 4: Install Signal CLI
# ============================================
log "Installing signal-cli..."
SIGNAL_CLI_VERSION="0.13.4"
cd /tmp
wget -q "https://github.com/AsamK/signal-cli/releases/download/v${SIGNAL_CLI_VERSION}/signal-cli-${SIGNAL_CLI_VERSION}-Linux.tar.gz"
sudo tar xf "signal-cli-${SIGNAL_CLI_VERSION}-Linux.tar.gz" -C /opt
sudo ln -sf "/opt/signal-cli-${SIGNAL_CLI_VERSION}/bin/signal-cli" /usr/local/bin/signal-cli
rm "signal-cli-${SIGNAL_CLI_VERSION}-Linux.tar.gz"
cd ~

# ============================================
# PART 5: Create Signal Chat Handler
# ============================================
log "Creating Signal chat handler..."

cat > ~/moltbot-system/signal-chat.sh << EOF
#!/bin/bash
# Moltbot Signal Chat Handler
# Receives Signal messages, sends to AI, returns response

SIGNAL_ACCOUNT="$SIGNAL_PHONE"
ALLOWED_NUMBER="$SIGNAL_PHONE"  # Only respond to yourself
LOG_FILE="\$HOME/moltbot-system/logs/signal-chat.log"

log() {
    echo "[\$(date -Iseconds)] \$1" >> "\$LOG_FILE"
}

log "Signal chat handler started"

# Listen for incoming messages
signal-cli -a "\$SIGNAL_ACCOUNT" receive --json 2>/dev/null | while read -r line; do
    # Skip empty lines
    [[ -z "\$line" ]] && continue
    
    # Parse message
    sender=\$(echo "\$line" | jq -r '.envelope.source // empty' 2>/dev/null)
    message=\$(echo "\$line" | jq -r '.envelope.dataMessage.message // empty' 2>/dev/null)
    
    # Skip if no sender or message
    [[ -z "\$sender" || -z "\$message" ]] && continue
    
    log "FROM: \$sender MSG: \$message"
    
    # Only respond to allowed number
    if [[ "\$sender" != "\$ALLOWED_NUMBER" ]]; then
        log "BLOCKED: unauthorized sender \$sender"
        continue
    fi
    
    # Special commands
    case "\$message" in
        "/status")
            response="Online. Model: router (qwen2.5 1.5B)"
            ;;
        "/help")
            response="Commands: /status /help /logs
Or just chat normally!"
            ;;
        "/logs")
            response=\$(tail -5 "\$LOG_FILE" 2>/dev/null || echo "No logs yet")
            ;;
        *)
            # Send to Ollama
            log "Sending to Ollama..."
            response=\$(ollama run router "\$message" 2>/dev/null)
            
            # Truncate if too long for Signal
            if [[ \${#response} -gt 2000 ]]; then
                response="\${response:0:1997}..."
            fi
            
            # Handle empty response
            [[ -z "\$response" ]] && response="(no response from model)"
            ;;
    esac
    
    log "RESPONSE: \$response"
    
    # Send response
    signal-cli -a "\$SIGNAL_ACCOUNT" send -m "\$response" "\$sender" 2>/dev/null
    
done

log "Signal chat handler stopped"
EOF

chmod +x ~/moltbot-system/signal-chat.sh

# ============================================
# PART 6: Create Systemd Service
# ============================================
log "Creating systemd service..."

sudo tee /etc/systemd/system/moltbot-signal.service > /dev/null << EOF
[Unit]
Description=Moltbot Signal Chat Handler
After=network.target ollama.service

[Service]
Type=simple
User=$USER
ExecStart=$HOME/moltbot-system/signal-chat.sh
Restart=always
RestartSec=10
Environment="HOME=$HOME"

[Install]
WantedBy=multi-user.target
EOF

# ============================================
# PART 7: Create Helper Scripts
# ============================================
log "Creating helper scripts..."

# Start script
cat > ~/moltbot-start.sh << 'EOF'
#!/bin/bash
echo "Starting Moltbot Signal service..."
sudo systemctl start moltbot-signal
sudo systemctl status moltbot-signal --no-pager
echo ""
echo "To view logs: journalctl -u moltbot-signal -f"
EOF
chmod +x ~/moltbot-start.sh

# Stop script
cat > ~/moltbot-stop.sh << 'EOF'
#!/bin/bash
echo "Stopping Moltbot Signal service..."
sudo systemctl stop moltbot-signal
EOF
chmod +x ~/moltbot-stop.sh

# Status script
cat > ~/moltbot-status.sh << 'EOF'
#!/bin/bash
echo "=== Ollama Status ==="
systemctl status ollama --no-pager | head -5
echo ""
echo "=== Signal Service Status ==="
systemctl status moltbot-signal --no-pager | head -5
echo ""
echo "=== Recent Chat Log ==="
tail -10 ~/moltbot-system/logs/signal-chat.log 2>/dev/null || echo "No logs yet"
EOF
chmod +x ~/moltbot-status.sh

# ============================================
# PART 8: Basic Firewall
# ============================================
log "Configuring firewall..."
sudo ufw default deny incoming
sudo ufw default deny outgoing
sudo ufw allow out 53/udp   # DNS
sudo ufw allow out 53/tcp
sudo ufw allow out 80/tcp   # HTTP
sudo ufw allow out 443/tcp  # HTTPS (Signal uses this)
sudo ufw allow out 123/udp  # NTP
sudo ufw allow from 127.0.0.1
sudo ufw allow to 127.0.0.1
sudo ufw --force enable

# ============================================
# DONE - Signal Registration Required
# ============================================
echo ""
echo "============================================"
echo -e "${GREEN}  Setup Complete!${NC}"
echo "============================================"
echo ""
echo "NEXT STEP: Register Signal"
echo ""
echo "1. Get a captcha from:"
echo "   https://signalcaptchas.org/registration/generate.html"
echo ""
echo "2. Run this command (paste your captcha):"
echo -e "   ${YELLOW}signal-cli -a $SIGNAL_PHONE register --captcha \"YOUR_CAPTCHA\"${NC}"
echo ""
echo "3. You'll receive an SMS code. Verify with:"
echo -e "   ${YELLOW}signal-cli -a $SIGNAL_PHONE verify CODE_FROM_SMS${NC}"
echo ""
echo "4. Start the chat service:"
echo -e "   ${YELLOW}sudo systemctl enable moltbot-signal${NC}"
echo -e "   ${YELLOW}~/moltbot-start.sh${NC}"
echo ""
echo "5. Send yourself a Signal message to test!"
echo ""
echo "Helper commands:"
echo "  ~/moltbot-start.sh   - Start the service"
echo "  ~/moltbot-stop.sh    - Stop the service"  
echo "  ~/moltbot-status.sh  - Check status"
echo ""
