#!/bin/bash
# Stop Noctem and Signal daemon

echo "Stopping Noctem..."
pkill -f "python3.*main.py" 2>/dev/null && echo "Noctem stopped" || echo "Noctem not running"

echo "Stopping Signal daemon..."
pkill -f "signal-cli.*daemon" 2>/dev/null && echo "Signal daemon stopped" || echo "Signal daemon not running"

echo "Done"
