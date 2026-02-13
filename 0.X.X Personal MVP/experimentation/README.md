# 🌙 Noctem

A lightweight agentic AI assistant framework designed for low-spec hardware. Runs on a USB-portable Linux server with Ollama for LLM inference and Signal for messaging.

## Deployment Model

**Target**: 1TB flash drive bootable Linux system — portable, encrypted, runs on any compatible hardware.

**Development**: Windows workstation (this repo). Code is developed/tested here, then deployed to the flash drive for "birth."

**Lifecycle**:
1. **MVP** — Complete core skills and infrastructure on Windows
2. **Birth** — Deploy to flash drive, autonomous first-time setup
3. **Parent** — Multiple AI agents supervise and improve Noctem remotely

## Quick Start

```bash
# On your server
cd ~/noctem

# Start signal-cli daemon first (replace YOUR_PHONE)
nohup signal-cli -a YOUR_PHONE daemon --tcp 127.0.0.1:7583 > /tmp/signal-daemon.log 2>&1 &

# Start Noctem
python3 main.py
```

Or use the quickstart script:
```bash
./quickstart.sh
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                        Noctem                           │
├──────────────┬──────────────┬───────────────────────────┤
│  main.py     │  daemon.py   │  signal_receiver.py       │
│  (entry)     │  (LLM loop)  │  (Signal listener)        │
├──────────────┴──────────────┴───────────────────────────┤
│  skill_runner.py                                        │
│  (loads & executes skills)                              │
├─────────────────────────────────────────────────────────┤
│  skills/                                                │
│  ├── shell.py        - Run shell commands               │
│  ├── signal_send.py  - Send Signal messages             │
│  ├── file_ops.py     - Read/write files                 │
│  └── task_status.py  - Query task queue                 │
├─────────────────────────────────────────────────────────┤
│  state.py (SQLite persistence)                          │
└─────────────────────────────────────────────────────────┘
```

## Signal Integration

Noctem uses **signal-cli** in daemon mode for bidirectional messaging:

1. **Daemon**: `signal-cli daemon --tcp 127.0.0.1:7583` runs as JSON-RPC server
2. **Send**: Skills call the daemon via JSON-RPC to send messages
3. **Receive**: `signal_receiver.py` maintains a TCP connection to receive incoming messages

### Message Flow
- **Quick chats** (short messages, commands): Handled immediately with fast 1.5b model
- **Tasks** (complex requests): Queued for processing with 7b model

### Commands
Text these to Noctem:
- `/ping` - Get "pong" (connectivity test)
- `/status` - System status
- `/help` - List commands
- `/last` - Show last received message

## Configuration

Edit `data/config.json`:

```json
{
  "signal_phone": "+15551234567",
  "model": "qwen2.5:7b-instruct-q4_K_M",
  "router_model": "qwen2.5:1.5b-instruct-q4_K_M",
  "quick_chat_max_length": 50,
  "boot_notification": true
}
```

## Deployment

From your workstation:
```bash
# Sync to server
rsync -avz /media/alex/5D9B-8C80/noctem/ user@SERVER_IP:~/noctem/

# On server - restart everything
pkill -f signal-cli && pkill -f "python3 main.py"
nohup signal-cli -a YOUR_PHONE daemon --tcp 127.0.0.1:7583 > /tmp/signal-daemon.log 2>&1 &
sleep 2
cd ~/noctem && python3 main.py
```

## CLI Usage

```bash
# Interactive mode
python3 main.py

# Quick chat
python3 main.py -c "Hello!"

# Queue a task
python3 main.py -t "Check disk space"

# Headless (for systemd)
python3 main.py --headless
```

## Logs

- `logs/noctem.log` - Main application log
- `/tmp/signal-daemon.log` - signal-cli daemon output

## Prerequisites

- Python 3.8+
- Ollama with models pulled
- signal-cli (for Signal integration)

## Known Issues

- **Ollama timeout**: If the 7b model is slow/unavailable, tasks will fail after 2 minutes. Ensure Ollama is running and the model is loaded.
- **SyncMessage handling**: Messages from your own phone arrive as sync messages (handled correctly as of latest version).

---

## TODO / Next Steps

### High Priority
1. **Ollama health check** - Verify Ollama is running before accepting tasks
2. **Faster task routing** - Use 1.5b model for simple questions, 7b only for complex tasks
3. **Streaming responses** - Use Ollama API for streaming instead of subprocess timeout
4. **Error recovery** - Better handling when Ollama times out or fails

### Medium Priority
5. **Web fetch skill** - Retrieve URLs for the LLM to process
6. **Warp Agent skill** - Delegate complex coding tasks to Warp
7. **Scheduled tasks** - Run tasks at specific times (cron-like)
8. **Memory/context window** - Include recent conversation in prompts

### Low Priority  
9. **Multi-user support** - Handle messages from multiple Signal contacts
10. **Dashboard TUI** - curses-based status display
11. **Systemd unit file** - For automatic startup

---

*Built with assistance from Warp Agent*
