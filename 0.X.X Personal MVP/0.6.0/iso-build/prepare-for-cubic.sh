#!/bin/bash
# =============================================================================
# Prepare Noctem files for Cubic
# =============================================================================
# Run this on your HOST machine (not in chroot) to prepare the files.
# Then use Cubic's file manager to copy /tmp/noctem-build into the chroot.
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NOCTEM_DIR="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="/tmp/noctem-build"

echo "==========================================="
echo "  Preparing Noctem for Cubic"
echo "==========================================="
echo ""
echo "Source: $NOCTEM_DIR"
echo "Build:  $BUILD_DIR"
echo ""

# Clean and create build directory
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

# Copy noctem code (excluding pycache, venv, data)
echo "Copying noctem code..."
mkdir -p "$BUILD_DIR/noctem"
rsync -av --exclude='__pycache__' \
          --exclude='*.pyc' \
          --exclude='venv' \
          --exclude='data/*.db' \
          --exclude='data/logs/*.log' \
          "$NOCTEM_DIR/noctem/" "$BUILD_DIR/noctem/"

# Copy setup script
echo "Copying setup script..."
cp "$SCRIPT_DIR/setup-chroot.sh" "$BUILD_DIR/"

# Create empty data directories
mkdir -p "$BUILD_DIR/noctem/data/logs"
touch "$BUILD_DIR/noctem/data/logs/.gitkeep"

echo ""
echo "==========================================="
echo "  Files prepared at: $BUILD_DIR"
echo "==========================================="
echo ""
echo "Contents:"
ls -la "$BUILD_DIR"
echo ""
echo "Next steps:"
echo "  1. In Cubic, use the file manager (or terminal) to copy"
echo "     $BUILD_DIR to /tmp/noctem-build in the chroot"
echo ""
echo "  2. In the Cubic chroot terminal, run:"
echo "     bash /tmp/noctem-build/setup-chroot.sh"
echo ""
