#!/bin/bash
# Noctem - First Run Setup Wizard

CONFIG_FLAG="/home/noctem/.noctem_configured"

# Skip if already configured
if [ -f "$CONFIG_FLAG" ]; then
    exit 0
fi

clear
echo "╔══════════════════════════════════════╗"
echo "║    NOCTEM - First Time Setup         ║"
echo "╚══════════════════════════════════════╝"
echo ""
echo "Welcome! Let's configure your Noctem instance."
echo ""

# Telegram Bot Token
echo "━━━━ Telegram Bot Setup ━━━━"
echo ""
echo "To use Noctem, you need a Telegram bot token."
echo ""
echo "1. Open Telegram and message @BotFather"
echo "2. Send /newbot"
echo "3. Follow the prompts to create your bot"
echo "4. Copy the API token you receive"
echo ""
read -p "Telegram Bot Token (or press Enter to skip): " TOKEN

if [ -n "$TOKEN" ]; then
    source ~/noctem_venv/bin/activate
    cd ~/noctem
    python3 -c "
from noctem.config import Config
Config.set('telegram_bot_token', '$TOKEN')
print('✓ Token saved!')
"
else
    echo "⚠ Skipped - You can set this later with noctem-cli"
fi

echo ""

# Timezone
echo "━━━━ Timezone Setup ━━━━"
echo ""
read -p "Your timezone [UTC]: " TZ
TZ=${TZ:-UTC}

source ~/noctem_venv/bin/activate
cd ~/noctem
python3 -c "
from noctem.config import Config
Config.set('timezone', '$TZ')
print('✓ Timezone set to: $TZ')
"

echo ""

# Morning briefing time
echo "━━━━ Morning Briefing ━━━━"
echo ""
read -p "Morning briefing time [07:00]: " MORNING
MORNING=${MORNING:-07:00}

source ~/noctem_venv/bin/activate
cd ~/noctem
python3 -c "
from noctem.config import Config
Config.set('morning_message_time', '$MORNING')
print('✓ Morning briefing set to: $MORNING')
"

# Initialize database
echo ""
echo "Initializing database..."
source ~/noctem_venv/bin/activate
cd ~/noctem
python3 -m noctem.main init

# Mark as configured
touch "$CONFIG_FLAG"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✓ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Message your bot in Telegram"
echo "2. Send /start to register your chat"
echo "3. Try adding a task: 'buy groceries tomorrow !1'"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
read -p "Press Enter to reboot and start Noctem..."
sudo reboot
