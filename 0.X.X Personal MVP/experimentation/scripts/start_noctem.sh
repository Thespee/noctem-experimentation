#!/bin/bash
# Start Noctem and Signal daemon
# Usage: ./start_noctem.sh [--foreground]

NOCTEM_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CONFIG_FILE="$NOCTEM_DIR/data/config.json"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}=== Starting Noctem ===${NC}"

# Check config exists
if [ ! -f "$CONFIG_FILE" ]; then
    echo -e "${YELLOW}Creating config from example...${NC}"
    cp "$NOCTEM_DIR/data/config.example.json" "$CONFIG_FILE"
    echo -e "${RED}Please edit $CONFIG_FILE with your Signal phone number${NC}"
    exit 1
fi

# Get phone number from config
PHONE=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('signal_phone', ''))" 2>/dev/null)

if [ -z "$PHONE" ] || [ "$PHONE" = "+1YOURNUMBER" ]; then
    echo -e "${RED}Signal phone not configured!${NC}"
    echo "Edit $CONFIG_FILE and set signal_phone"
    exit 1
fi

echo "Phone: $PHONE"

# Check if signal-cli is running
if ! pgrep -f "signal-cli.*daemon" > /dev/null; then
    echo -e "${YELLOW}Starting Signal daemon...${NC}"
    
    # Check if signal-cli exists
    if ! command -v signal-cli &> /dev/null; then
        echo -e "${RED}signal-cli not found!${NC}"
        echo "Run: ./scripts/setup_signal.sh"
        exit 1
    fi
    
    # Start signal daemon in background
    nohup signal-cli -a "$PHONE" daemon --tcp 127.0.0.1:7583 > /tmp/signal-daemon.log 2>&1 &
    SIGNAL_PID=$!
    echo "Signal daemon PID: $SIGNAL_PID"
    sleep 2
    
    # Verify it started
    if ! kill -0 $SIGNAL_PID 2>/dev/null; then
        echo -e "${RED}Signal daemon failed to start!${NC}"
        echo "Check /tmp/signal-daemon.log"
        exit 1
    fi
else
    echo -e "${GREEN}Signal daemon already running${NC}"
fi

# Start Noctem
echo -e "${YELLOW}Starting Noctem...${NC}"

if [ "$1" = "--foreground" ]; then
    # Run in foreground
    cd "$NOCTEM_DIR"
    python3 main.py
else
    # Run in background
    cd "$NOCTEM_DIR"
    nohup python3 main.py --headless > /tmp/noctem.log 2>&1 &
    NOCTEM_PID=$!
    echo "Noctem PID: $NOCTEM_PID"
    
    sleep 2
    if kill -0 $NOCTEM_PID 2>/dev/null; then
        echo -e "${GREEN}Noctem started successfully!${NC}"
        echo ""
        echo "Logs: /tmp/noctem.log"
        echo "Signal logs: /tmp/signal-daemon.log"
        echo ""
        echo "Test with Signal: send /ping to $PHONE"
    else
        echo -e "${RED}Noctem failed to start!${NC}"
        echo "Check /tmp/noctem.log"
        exit 1
    fi
fi
