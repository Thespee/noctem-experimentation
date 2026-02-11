#!/bin/bash
# Noctem Quickstart Script
# Checks prerequisites, configures if needed, and starts the system

set -o pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

NOCTEM_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$NOCTEM_DIR/data/config.json"

log() { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
error() { echo -e "${RED}[✗]${NC} $1"; }
info() { echo -e "${BLUE}[i]${NC} $1"; }

echo ""
echo "  🌙 Noctem Quickstart"
echo "  ===================="
echo ""

# =============================================================================
# Check Prerequisites
# =============================================================================

CHECKS_PASSED=true

# Check Python 3
echo "Checking prerequisites..."
echo ""

if command -v python3 &> /dev/null; then
    PY_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
    log "Python 3: $PY_VERSION"
else
    error "Python 3: NOT FOUND"
    echo "    Install with: sudo apt install python3"
    CHECKS_PASSED=false
fi

# Check Ollama
if command -v ollama &> /dev/null; then
    log "Ollama: installed"
    
    # Check if Ollama is running
    if curl -s http://localhost:11434/api/tags &> /dev/null; then
        log "Ollama service: running"
    else
        warn "Ollama service: not running"
        echo "    Starting Ollama..."
        ollama serve &> /dev/null &
        sleep 3
        if curl -s http://localhost:11434/api/tags &> /dev/null; then
            log "Ollama service: started"
        else
            error "Ollama service: failed to start"
            echo "    Try: systemctl start ollama"
            CHECKS_PASSED=false
        fi
    fi
    
    # Check for a model
    MODELS=$(ollama list 2>/dev/null | tail -n +2 | wc -l)
    if [ "$MODELS" -gt 0 ]; then
        DEFAULT_MODEL=$(ollama list 2>/dev/null | tail -n +2 | head -1 | awk '{print $1}')
        log "Ollama models: $MODELS available (default: $DEFAULT_MODEL)"
    else
        warn "Ollama models: none found"
        echo "    Pulling a small model for quick start..."
        ollama pull qwen2.5:1.5b-instruct-q4_K_M
        if [ $? -eq 0 ]; then
            log "Pulled qwen2.5:1.5b model"
        else
            error "Failed to pull model"
            CHECKS_PASSED=false
        fi
    fi
else
    error "Ollama: NOT FOUND"
    echo "    Install with: curl -fsSL https://ollama.com/install.sh | sh"
    CHECKS_PASSED=false
fi

# Check signal-cli (optional)
if command -v signal-cli &> /dev/null; then
    log "signal-cli: installed"
    SIGNAL_AVAILABLE=true
else
    warn "signal-cli: not found (Signal integration disabled)"
    echo "    Optional - install for Signal messaging support"
    SIGNAL_AVAILABLE=false
fi

# Check Python dependencies
echo ""
info "Checking Python packages..."
MISSING_PKGS=""

# requests and bs4 are optional but useful
python3 -c "import requests" 2>/dev/null || MISSING_PKGS="$MISSING_PKGS requests"
python3 -c "import bs4" 2>/dev/null || MISSING_PKGS="$MISSING_PKGS beautifulsoup4"

if [ -n "$MISSING_PKGS" ]; then
    warn "Optional packages not installed:$MISSING_PKGS"
    echo "    Install with: pip3 install$MISSING_PKGS"
else
    log "Optional packages: all available"
fi

echo ""

# =============================================================================
# Configuration
# =============================================================================

if [ ! -f "$CONFIG_FILE" ]; then
    error "Config file not found at $CONFIG_FILE"
    echo "    Creating default config..."
    mkdir -p "$NOCTEM_DIR/data"
    cat > "$CONFIG_FILE" << 'EOF'
{
  "signal_phone": null,
  "model": "qwen2.5:7b-instruct-q4_K_M",
  "router_model": "qwen2.5:1.5b-instruct-q4_K_M",
  "warp_api_key": null,
  "quick_chat_max_length": 50,
  "boot_notification": true,
  "dashboard_refresh_ms": 1000,
  "max_concurrent_tasks": 1,
  "skill_timeout_seconds": 60,
  "warp_timeout_seconds": 300,
  "dangerous_commands": ["rm -rf /", "rm -rf /*", "mkfs", "dd if=", "> /dev/"]
}
EOF
    log "Created default config"
fi

# Check if Signal phone is configured
SIGNAL_PHONE=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('signal_phone') or '')" 2>/dev/null)

if [ -z "$SIGNAL_PHONE" ] && [ "$SIGNAL_AVAILABLE" = true ]; then
    echo ""
    warn "No Signal phone number configured"
    read -p "Enter your Signal phone number (e.g., +15551234567) or press Enter to skip: " INPUT_PHONE
    
    if [ -n "$INPUT_PHONE" ]; then
        # Update config with phone number
        python3 << EOF
import json
with open('$CONFIG_FILE', 'r') as f:
    config = json.load(f)
config['signal_phone'] = '$INPUT_PHONE'
with open('$CONFIG_FILE', 'w') as f:
    json.dump(config, f, indent=2)
EOF
        log "Saved Signal phone: $INPUT_PHONE"
    else
        info "Skipping Signal configuration"
    fi
fi

# =============================================================================
# Final Check
# =============================================================================

echo ""
if [ "$CHECKS_PASSED" = false ]; then
    error "Some prerequisites are missing. Please install them and try again."
    exit 1
fi

log "All prerequisites satisfied!"
echo ""

# =============================================================================
# Start signal-cli daemon if configured
# =============================================================================

SIGNAL_PHONE=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('signal_phone') or '')" 2>/dev/null)

if [ -n "$SIGNAL_PHONE" ] && [ "$SIGNAL_AVAILABLE" = true ]; then
    # Check if daemon already running
    if pgrep -f "signal-cli.*daemon" > /dev/null; then
        log "signal-cli daemon: already running"
    else
        info "Starting signal-cli daemon..."
        nohup signal-cli -a "$SIGNAL_PHONE" daemon --tcp 127.0.0.1:7583 > /tmp/signal-daemon.log 2>&1 &
        sleep 2
        if pgrep -f "signal-cli.*daemon" > /dev/null; then
            log "signal-cli daemon: started on port 7583"
        else
            warn "signal-cli daemon: failed to start"
            echo "    Check /tmp/signal-daemon.log for errors"
        fi
    fi
fi

# =============================================================================
# Start Noctem
# =============================================================================

echo ""
echo "  Starting Noctem..."
echo "  =================="
echo ""

cd "$NOCTEM_DIR"

# Check if we should run in interactive mode
if [ -t 0 ]; then
    # Interactive terminal
    exec python3 main.py
else
    # Non-interactive (e.g., systemd)
    exec python3 main.py --headless
fi
