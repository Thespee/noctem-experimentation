#!/bin/bash
# Noctem 0.5 - Start Script
# Starts web dashboard and optional services

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Try to find Python: venv first, then system python3
if [ -f "$HOME/noctem_venv/bin/python" ]; then
    VENV_PYTHON="$HOME/noctem_venv/bin/python"
else
    VENV_PYTHON="python3"
fi

cd "$SCRIPT_DIR"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Parse arguments
MODE="${1:-qr}"

case "$MODE" in
    web)
        echo -e "${BLUE}Noctem 0.5${NC} - Web Dashboard"
        $VENV_PYTHON -m noctem.main web
        ;;
    cli)
        echo -e "${BLUE}Noctem 0.5${NC} - CLI"
        $VENV_PYTHON -m noctem.cli
        ;;
    bot)
        echo -e "${BLUE}Noctem 0.5${NC} - Telegram Bot"
        $VENV_PYTHON -m noctem.main bot
        ;;
    all)
        echo -e "${BLUE}Noctem 0.5${NC} - All Services"
        # Start web in background
        $VENV_PYTHON -m noctem.main web &
        WEB_PID=$!
        echo "Web dashboard started (PID: $WEB_PID)"
        echo "Dashboard: http://localhost:5000"
        echo ""
        # Start CLI in foreground
        echo "Starting CLI (Ctrl+C to exit all)..."
        $VENV_PYTHON -m noctem.cli
        # When CLI exits, kill web
        kill $WEB_PID 2>/dev/null
        ;;
    qr)
        # QR code mode - quiet, shows big QR code
        $VENV_PYTHON -m noctem.main all --quiet
        ;;
    *)
        echo "Usage: $0 [qr|web|cli|bot|all]"
        echo "  qr   - QR code display + all services (default)"
        echo "  web  - Start web dashboard only"
        echo "  cli  - Start CLI only"
        echo "  bot  - Start Telegram bot only"
        echo "  all  - Start web + CLI"
        exit 1
        ;;
esac
