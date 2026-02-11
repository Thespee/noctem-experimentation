#!/bin/bash
# Install Noctem Parent CLI on your workstation
#
# Usage:
#   ./install.sh              Install to ~/.local/bin
#   ./install.sh /usr/local   Install to /usr/local/bin (requires sudo)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NOCTEM_DIR="$(dirname "$SCRIPT_DIR")"

# Default installation directory
INSTALL_DIR="${1:-$HOME/.local/bin}"
CONFIG_DIR="$HOME/.config/noctem-parent"

echo "╔══════════════════════════════════════════╗"
echo "║     Noctem Parent CLI Installation       ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# Check dependencies
echo "Checking dependencies..."

if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 not found. Please install Python 3.8+"
    exit 1
fi
echo "  ✓ Python 3 found"

if ! command -v signal-cli &> /dev/null; then
    echo "  ⚠ signal-cli not found (optional, needed for Signal integration)"
    echo "    Install from: https://github.com/AsamK/signal-cli"
else
    echo "  ✓ signal-cli found"
fi

# Create directories
echo ""
echo "Creating directories..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$CONFIG_DIR"
echo "  ✓ $INSTALL_DIR"
echo "  ✓ $CONFIG_DIR"

# Create wrapper script
echo ""
echo "Installing parent CLI..."

cat > "$INSTALL_DIR/parent" << EOF
#!/usr/bin/env python3
import sys
sys.path.insert(0, "$NOCTEM_DIR")
from parent.cli import main
main()
EOF

chmod +x "$INSTALL_DIR/parent"
echo "  ✓ Installed: $INSTALL_DIR/parent"

# Create babysitter wrapper
cat > "$INSTALL_DIR/noctem-babysit" << EOF
#!/usr/bin/env python3
import sys
sys.path.insert(0, "$NOCTEM_DIR")
from parent.scheduler import main
main()
EOF

chmod +x "$INSTALL_DIR/noctem-babysit"
echo "  ✓ Installed: $INSTALL_DIR/noctem-babysit"

# Check if install dir is in PATH
echo ""
if [[ ":$PATH:" != *":$INSTALL_DIR:"* ]]; then
    echo "⚠ $INSTALL_DIR is not in your PATH"
    echo ""
    echo "Add this to your ~/.bashrc or ~/.zshrc:"
    echo ""
    echo "  export PATH=\"$INSTALL_DIR:\$PATH\""
    echo ""
else
    echo "✓ $INSTALL_DIR is in PATH"
fi

# Installation complete
echo ""
echo "╔══════════════════════════════════════════╗"
echo "║         Installation Complete!           ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "Next steps:"
echo ""
echo "  1. Configure Signal numbers:"
echo "     parent config"
echo ""
echo "  2. Test connection:"
echo "     parent status"
echo ""
echo "  3. Generate a report:"
echo "     parent report"
echo ""
echo "  4. Start continuous monitoring:"
echo "     parent watch"
echo ""
echo "  5. (Optional) Set up systemd timer for automated babysitting"
echo "     See: $NOCTEM_DIR/parent/systemd/"
echo ""
