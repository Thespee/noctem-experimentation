#!/bin/bash
# Noctem Cron Setup Script
# Sets up daily report at 8 AM PST (16:00 UTC)

set -e

NOCTEM_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${PYTHON:-python3}"
CRON_TIME="${CRON_TIME:-0 16 * * *}"  # 8 AM PST = 16:00 UTC

echo "🌙 Noctem Cron Setup"
echo "===================="
echo ""
echo "Noctem directory: $NOCTEM_DIR"
echo "Python: $PYTHON"
echo "Cron time: $CRON_TIME (8 AM PST)"
echo ""

# Check if crontab is available
if ! command -v crontab &> /dev/null; then
    echo "❌ crontab not found. Please install cron."
    exit 1
fi

# Create the cron job line
CRON_LINE="$CRON_TIME cd $NOCTEM_DIR && $PYTHON skills/daily_report.py --send >> logs/daily_report.log 2>&1"

# Check if already installed
if crontab -l 2>/dev/null | grep -q "daily_report.py"; then
    echo "⚠️  Daily report cron job already exists."
    echo "   Current crontab entries:"
    crontab -l | grep daily_report
    echo ""
    read -p "Replace with new schedule? [y/N] " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Keeping existing schedule."
        exit 0
    fi
    # Remove old entry
    crontab -l 2>/dev/null | grep -v "daily_report.py" | crontab -
fi

# Add new cron job
(crontab -l 2>/dev/null; echo "$CRON_LINE") | crontab -

echo "✓ Cron job installed:"
echo "  $CRON_LINE"
echo ""

# Verify
echo "Current crontab:"
crontab -l | grep -E "(noctem|daily_report)" || echo "  (no noctem entries found)"
echo ""

# Create logs directory if needed
mkdir -p "$NOCTEM_DIR/logs"

echo "✓ Setup complete!"
echo ""
echo "Daily report will be sent at 8 AM PST (16:00 UTC)."
echo "Logs: $NOCTEM_DIR/logs/daily_report.log"
echo ""
echo "To test immediately:"
echo "  cd $NOCTEM_DIR && $PYTHON skills/daily_report.py --send"
echo ""
echo "To remove the cron job:"
echo "  crontab -e  # then delete the noctem line"
