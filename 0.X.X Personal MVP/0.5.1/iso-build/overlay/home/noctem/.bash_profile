#!/bin/bash
# Noctem 0.5 - Login Display Script

# Run first-run setup if not configured
/home/noctem/first-run.sh

# Wait for network to come up
echo "Waiting for network..."
for i in {1..10}; do
    IP=$(hostname -I | awk '{print $1}')
    if [ -n "$IP" ]; then
        break
    fi
    sleep 1
done

# Clear screen and show header
clear
echo "╔══════════════════════════════════════╗"
echo "║         NOCTEM v0.5                  ║"
echo "║      Executive Assistant             ║"
echo "╚══════════════════════════════════════╝"
echo ""

# Get IP address
IP=$(hostname -I | awk '{print $1}')
if [ -z "$IP" ]; then
    echo "⚠  No network connection detected"
    echo ""
    echo "Run 'noctem-wifi' to configure WiFi"
    echo "Or connect Ethernet cable"
else
    echo "Dashboard: http://$IP:5000"
    echo ""
    
    # Generate and display QR code
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
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Telegram bot: $(systemctl is-active noctem)"
echo ""
echo "Commands:"
echo "  noctem-wifi  - Configure WiFi"
echo "  noctem-logs  - View service logs"
echo "  noctem-cli   - Open Noctem CLI"
echo "  systemctl restart noctem - Restart service"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Press Enter to refresh, or type a command..."

# Keep terminal interactive
while true; do
    read -r CMD
    if [ -z "$CMD" ]; then
        exec bash --login
    else
        eval "$CMD"
        echo ""
        echo "Press Enter to refresh..."
    fi
done
