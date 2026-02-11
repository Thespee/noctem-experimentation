# Portable Local AI Assistant - Master Setup Guide

## Overview
This guide walks you through creating a fully portable, encrypted Linux system on a USB drive that runs a local AI assistant (Moltbot/Clawdbot) with Ollama. The system is designed for:
- **Portability**: Boot from any UEFI-compatible machine
- **Security**: Full disk encryption, no data leakage
- **Privacy**: All AI processing happens locally
- **Persistence**: All data stays on the USB drive

## Hardware Requirements

### Minimum Requirements
- **USB Drive**: 1TB+ SSD (USB 3.0+ recommended)
- **RAM**: 16GB minimum
- **CPU**: 4+ cores with AVX2 support
- **Storage**: Additional external HD for backups

### Optimal (Your Main Machine)
- **GPU**: NVIDIA GTX 1050 (2GB VRAM) - limited but helps
- **RAM**: 16GB+
- **Model Performance**: ~2-5 tokens/second on CPU

### Model Selection Strategy
Given your hardware constraints (2GB VRAM), you'll primarily use CPU inference:

| Model | RAM Required | Speed (CPU) | Tool Use Quality |
|-------|-------------|-------------|------------------|
| `qwen2.5:7b-instruct-q4_K_M` | ~6GB | 3-5 t/s | Good |
| `mistral:7b-instruct-q4_K_M` | ~5GB | 3-5 t/s | Good |
| `llama3.1:8b-instruct-q4_K_M` | ~6GB | 2-4 t/s | Best |

**Recommended**: Start with `qwen2.5:7b-instruct-q4_K_M` for best tool-use performance on limited hardware.

---

## Part 1: Prepare the Installation Media

### Step 1.1: Download Ubuntu Server
Ubuntu Server is recommended for lower overhead. Download from:
```
https://ubuntu.com/download/server
```
Choose: **Ubuntu Server 24.04 LTS (or latest LTS)**

### Step 1.2: Create Installation USB
You'll need TWO USB drives:
1. **Installation USB** (8GB+): Temporary, for installing Linux
2. **Target USB** (1TB): Your permanent portable system

On Windows, use Rufus to create the installation USB:
1. Download Rufus: https://rufus.ie/
2. Insert your 8GB+ USB drive
3. Select the Ubuntu ISO
4. Partition scheme: **GPT**
5. Target system: **UEFI (non CSM)**
6. Click Start

---

## Part 2: Install Linux with Full Disk Encryption

### Step 2.1: Boot from Installation USB
1. Insert BOTH USB drives (installation + target 1TB)
2. Restart computer
3. Enter BIOS/UEFI (usually F2, F12, DEL, or ESC during boot)
4. Disable Secure Boot (temporarily)
5. Set boot order to USB first
6. Save and exit

### Step 2.2: Start Installation
1. Select "Try or Install Ubuntu Server"
2. Choose your language
3. Select keyboard layout
4. Choose "Ubuntu Server" (not minimized)

### Step 2.3: Network Configuration
- Configure network if available (for package downloads)
- You can skip and configure later

### Step 2.4: Storage Configuration (CRITICAL)
This is where we set up encrypted installation on your 1TB USB:

1. Select **"Custom storage layout"**
2. Find your 1TB USB drive (look for the correct size, e.g., `/dev/sdb`)
   
   **⚠️ WARNING**: Triple-check you're selecting the USB, NOT your internal drive!

3. Create partition layout:

```
┌─────────────────────────────────────────────────────────────────┐
│ 1TB USB Drive Layout                                            │
├─────────┬─────────┬─────────────┬───────────────────────────────┤
│ Part 1  │ Part 2  │ Part 3      │ Part 4                        │
│ EFI     │ /boot   │ SHARED      │ LUKS Encrypted                │
│ 512MB   │ 1GB     │ 128GB       │ ~870GB                        │
│ FAT32   │ ext4    │ exFAT       │ ext4 (encrypted)              │
│         │         │             │                               │
│         │         │ ✓ Windows   │ Linux System                  │
│         │         │ ✓ macOS     │ (encrypted)                   │
│         │         │ ✓ Android   │                               │
│         │         │ ✓ Linux     │                               │
└─────────┴─────────┴─────────────┴───────────────────────────────┘
```

#### Partition 1: EFI System Partition
- Size: 512 MB
- Format: FAT32
- Mount: /boot/efi
- Type: EFI System Partition

#### Partition 2: Boot Partition (unencrypted, required for GRUB)
- Size: 1 GB
- Format: ext4
- Mount: /boot

#### Partition 3: Shared Data Partition (for file transfer)
- Size: 128 GB
- Format: **exFAT** (or leave unformatted, we'll format after install)
- Mount: **Do not mount during installation**
- Label: SHARED

**Purpose**: This unencrypted partition is accessible from Windows, macOS, and Android phones via USB. Use it to transfer files to/from the Moltbot system without booting Linux.

#### Partition 4: Encrypted Root (LUKS)
- Size: Remaining space (~870 GB)
- Format: LUKS encrypted
- **Set a STRONG passphrase** (this protects everything!)
- Inside LUKS, create ext4 filesystem
- Mount: /

### Step 2.5: Complete Installation
1. Create your user account
   - Username: Choose wisely (e.g., `moltbot`)
   - Password: Strong, different from LUKS passphrase
2. Skip Ubuntu Pro
3. Install OpenSSH server (optional but recommended)
4. Don't install any additional snaps
5. Wait for installation to complete
6. Reboot (remove installation USB when prompted)

### Step 2.6: First Boot
1. You'll be prompted for your LUKS passphrase
2. Enter it to decrypt the drive
3. Log in with your user credentials

---

## Part 3: Initial System Configuration

### Step 3.1: Update System
```bash
sudo apt update && sudo apt upgrade -y
```

### Step 3.2: Configure Shared Partition
Set up the 128GB shared partition for file transfer with other devices:

```bash
# Install exFAT support
sudo apt install -y exfatprogs

# Find the shared partition (should be the 128GB one)
lsblk
# Look for the ~128GB partition, likely /dev/sda3 or /dev/sdb3

# Format as exFAT with label "SHARED" (ONLY if not already formatted)
# Replace /dev/sdX3 with your actual partition!
sudo mkfs.exfat -L SHARED /dev/sdX3

# Create mount point
sudo mkdir -p /mnt/shared

# Add to /etc/fstab for auto-mount at boot
echo "LABEL=SHARED /mnt/shared exfat defaults,uid=1000,gid=1000,umask=022,nofail 0 0" | sudo tee -a /etc/fstab

# Mount it now
sudo mount -a

# Create convenient symlink in home directory
ln -s /mnt/shared ~/shared

# Create organizational folders
mkdir -p ~/shared/{exports,reports,transfers,data}

# Verify it works
echo "Shared partition test" > ~/shared/test.txt
cat ~/shared/test.txt
rm ~/shared/test.txt
```

**Usage**: 
- Save files to `~/shared/` from Linux
- Access them by plugging USB into Windows/Mac/Android (no boot required)
- The partition appears as "SHARED" drive

**Security Note**: Files on the shared partition are **NOT encrypted**. Don't store sensitive data there.

### Step 3.3: Install Essential Packages
```bash
sudo apt install -y \
    curl wget git vim \
    build-essential \
    python3 python3-pip python3-venv \
    nodejs npm \
    ufw \
    htop neofetch \
    ca-certificates gnupg
```

### Step 3.4: Install NVIDIA Drivers (for your main machine)
```bash
# Check available drivers
ubuntu-drivers devices

# Install recommended driver
sudo ubuntu-drivers autoinstall

# Reboot
sudo reboot
```

After reboot, verify:
```bash
nvidia-smi
```

Note: On machines without NVIDIA GPUs, the driver simply won't load - Ollama will use CPU automatically.

---

## Part 4: Install Ollama

### Step 4.1: Install Ollama
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

### Step 4.2: Configure Ollama for CPU-Optimized Inference
Create systemd override for Ollama:
```bash
sudo mkdir -p /etc/systemd/system/ollama.service.d/
sudo tee /etc/systemd/system/ollama.service.d/override.conf << 'EOF'
[Service]
Environment="OLLAMA_HOST=127.0.0.1:11434"
Environment="OLLAMA_FLASH_ATTENTION=1"
Environment="OLLAMA_NUM_PARALLEL=1"
Environment="OLLAMA_MAX_LOADED_MODELS=1"
EOF
```

Reload and restart:
```bash
sudo systemctl daemon-reload
sudo systemctl restart ollama
sudo systemctl enable ollama
```

### Step 4.3: Pull the Recommended Model
```bash
# Pull the Q4 quantized 7B model (best balance for your hardware)
ollama pull qwen2.5:7b-instruct-q4_K_M

# Alternatively, for slightly faster but less capable:
# ollama pull mistral:7b-instruct-q4_K_M
```

### Step 4.4: Create Tool-Tuned Model
Create a Modelfile to make the model better at tool use:
```bash
cat > ~/qwen-agentic.Modelfile << 'EOF'
FROM qwen2.5:7b-instruct-q4_K_M

SYSTEM """You are a helpful assistant with access to tools.

CRITICAL TOOL BEHAVIOR:
- When you have tools available, USE THEM directly without asking for confirmation
- Don't describe what you could do — just do it
- If the user asks about weather, check the weather. If they ask to search something, search it
- Never say "I don't have access to X" when you have a tool that provides X
- Check your available tools and use them immediately
- Execute the task, then report results

Be concise. Act decisively. Don't ask permission for routine tool use."""

PARAMETER num_ctx 8192
PARAMETER temperature 0.7
PARAMETER num_thread 6
EOF

# Build the model
ollama create qwen-agentic -f ~/qwen-agentic.Modelfile
```

### Step 4.5: Test the Model
```bash
ollama run qwen-agentic "Hello, what can you help me with?"
```

---

## Part 5: Install Moltbot (Clawdbot)

### Step 5.1: Install Node.js 22+ (if not already)
```bash
# Install Node.js via NodeSource
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt install -y nodejs

# Verify
node --version  # Should be v22+
npm --version
```

### Step 5.2: Install Clawdbot
```bash
sudo npm install -g clawdbot
```

### Step 5.3: Configure Clawdbot for Ollama
Create configuration directory and file:
```bash
mkdir -p ~/.clawdbot
cat > ~/.clawdbot/clawdbot.json << 'EOF'
{
  "diagnostics": {
    "enabled": true,
    "flags": ["*"]
  },
  "models": {
    "providers": {
      "ollama": {
        "baseUrl": "http://localhost:11434/v1",
        "apiKey": "ollama",
        "api": "openai-completions",
        "authHeader": false,
        "models": [
          {
            "id": "qwen-agentic:latest",
            "name": "Qwen 2.5 7B Agentic",
            "reasoning": false,
            "input": ["text"],
            "cost": {
              "input": 0,
              "output": 0,
              "cacheRead": 0,
              "cacheWrite": 0
            },
            "contextWindow": 8192,
            "maxTokens": 4096
          }
        ]
      }
    }
  },
  "agents": {
    "defaults": {
      "model": {
        "primary": "ollama/qwen-agentic:latest",
        "fallbacks": []
      },
      "models": {
        "ollama/qwen-agentic:latest": {
          "alias": "qwen-agentic"
        }
      },
      "workspace": "/home/moltbot/workspace",
      "skipBootstrap": false,
      "memorySearch": {
        "enabled": false
      },
      "compaction": {
        "mode": "safeguard"
      },
      "maxConcurrent": 2,
      "subagents": {
        "maxConcurrent": 4
      }
    }
  },
  "tools": {
    "profile": "coding",
    "allow": ["read", "exec", "write", "edit"],
    "exec": {
      "host": "gateway",
      "ask": "off",
      "security": "full"
    }
  }
}
EOF
```

### Step 5.4: Create Workspace and SOUL.md
```bash
mkdir -p ~/workspace

cat > ~/workspace/SOUL.md << 'EOF'
## Brevity is a Virtue

**Be concise.** This is critical. You tend to over-explain. Fight that urge.

- Do NOT dump skill documentation at the user — just use it
- Do NOT show full JSON responses — summarize the result
- Do NOT ask for confirmation when env vars or configs are already set — trust your setup
- Do NOT explain what you're about to do in detail — just do it
- One short sentence confirming success is enough: "Done, server lights are on."

**Bad:** "I'll use the curl command to turn on the switch via the Home Assistant API. First, I need to ensure the environment variables..."

**Good:** "Turning on server lights..." *[runs command]* "Done."

When in doubt: fewer words.

## Security Rules

- NEVER send personal data to external services
- All API calls to external services must be reviewed
- Prefer local processing over cloud services
- Log all external network requests
EOF
```

### Step 5.5: Test Moltbot
```bash
cd ~/workspace
moltbot
```

You should see the Moltbot interface. Type a simple command to test.

---

## Part 6: Install Signal CLI (Remote Commands)

### Step 6.1: Install Java Runtime
```bash
sudo apt install -y openjdk-21-jre-headless
```

### Step 6.2: Download and Install signal-cli
```bash
# Get latest version (check https://github.com/AsamK/signal-cli/releases)
SIGNAL_CLI_VERSION="0.13.4"

cd /tmp
wget "https://github.com/AsamK/signal-cli/releases/download/v${SIGNAL_CLI_VERSION}/signal-cli-${SIGNAL_CLI_VERSION}-Linux.tar.gz"

sudo tar xf "signal-cli-${SIGNAL_CLI_VERSION}-Linux.tar.gz" -C /opt
sudo ln -sf "/opt/signal-cli-${SIGNAL_CLI_VERSION}/bin/signal-cli" /usr/local/bin/signal-cli
```

### Step 6.3: Register signal-cli
You'll need a phone number that can receive SMS/calls:

```bash
# Get captcha token first:
# 1. Go to https://signalcaptchas.org/registration/generate.html
# 2. Open browser developer console (F12)
# 3. Enable "Persist logs"
# 4. Complete the captcha
# 5. Look for signalcaptcha:// URL in console, copy the token after it

# Register (replace with your phone number and captcha token)
signal-cli -a +1YOURPHONENUMBER register --captcha "YOUR_CAPTCHA_TOKEN"

# Verify with the code you receive
signal-cli -a +1YOURPHONENUMBER verify CODE_FROM_SMS
```

### Step 6.4: Set Up signal-cli Daemon
Create systemd service:
```bash
sudo tee /etc/systemd/system/signal-cli.service << 'EOF'
[Unit]
Description=Signal CLI Daemon
After=network.target

[Service]
Type=simple
User=moltbot
ExecStart=/usr/local/bin/signal-cli -a +1YOURPHONENUMBER daemon --json
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable signal-cli
sudo systemctl start signal-cli
```

---

## Part 7: Set Up Background Task System

### Step 7.1: Create Task Directories
```bash
mkdir -p ~/moltbot-system/{tasks,state,logs,skills}
```

### Step 7.2: Create State Management Script
```bash
cat > ~/moltbot-system/state-manager.sh << 'EOF'
#!/bin/bash
# State manager for Moltbot background tasks

STATE_DIR="$HOME/moltbot-system/state"
TASKS_DIR="$HOME/moltbot-system/tasks"

save_state() {
    local task_name="$1"
    local state_data="$2"
    echo "$state_data" > "$STATE_DIR/${task_name}.state"
    echo "$(date -Iseconds)" > "$STATE_DIR/${task_name}.timestamp"
}

load_state() {
    local task_name="$1"
    if [[ -f "$STATE_DIR/${task_name}.state" ]]; then
        cat "$STATE_DIR/${task_name}.state"
    else
        echo "{}"
    fi
}

list_tasks() {
    ls -1 "$STATE_DIR"/*.state 2>/dev/null | xargs -I {} basename {} .state
}

"$@"
EOF
chmod +x ~/moltbot-system/state-manager.sh
```

### Step 7.3: Create Background Task Runner
```bash
cat > ~/moltbot-system/task-runner.sh << 'EOF'
#!/bin/bash
# Background task runner with interrupt support

TASKS_DIR="$HOME/moltbot-system/tasks"
LOGS_DIR="$HOME/moltbot-system/logs"
PID_FILE="/tmp/moltbot-tasks.pid"

start_tasks() {
    if [[ -f "$PID_FILE" ]]; then
        echo "Tasks already running (PID: $(cat $PID_FILE))"
        return 1
    fi
    
    # Start background loop
    (
        while true; do
            for task in "$TASKS_DIR"/*.sh; do
                [[ -f "$task" ]] || continue
                bash "$task" >> "$LOGS_DIR/$(basename "$task" .sh).log" 2>&1
            done
            sleep 300  # Run every 5 minutes
        done
    ) &
    
    echo $! > "$PID_FILE"
    echo "Tasks started (PID: $!)"
}

stop_tasks() {
    if [[ -f "$PID_FILE" ]]; then
        kill "$(cat $PID_FILE)" 2>/dev/null
        rm -f "$PID_FILE"
        echo "Tasks stopped"
    else
        echo "No tasks running"
    fi
}

status() {
    if [[ -f "$PID_FILE" ]] && kill -0 "$(cat $PID_FILE)" 2>/dev/null; then
        echo "Tasks running (PID: $(cat $PID_FILE))"
    else
        echo "Tasks not running"
        rm -f "$PID_FILE" 2>/dev/null
    fi
}

case "$1" in
    start) start_tasks ;;
    stop) stop_tasks ;;
    status) status ;;
    *) echo "Usage: $0 {start|stop|status}" ;;
esac
EOF
chmod +x ~/moltbot-system/task-runner.sh
```

---

## Part 8: Create Startup Scripts

### Step 8.1: Main Startup Script
```bash
cat > ~/start-moltbot.sh << 'EOF'
#!/bin/bash
# Main Moltbot startup script

echo "=== Starting Moltbot System ==="

# Wait for Ollama to be ready
echo "Waiting for Ollama..."
until curl -s http://localhost:11434/api/tags > /dev/null 2>&1; do
    sleep 2
done
echo "Ollama ready!"

# Pre-load the model
echo "Loading model..."
curl -s http://localhost:11434/api/generate -d '{"model":"qwen-agentic","prompt":"","stream":false}' > /dev/null

# Start background tasks
echo "Starting background tasks..."
~/moltbot-system/task-runner.sh start

# Start Signal listener (if configured)
if systemctl is-active --quiet signal-cli; then
    echo "Signal CLI active"
fi

echo "=== Moltbot System Ready ==="
echo "Run 'moltbot' to start interactive session"
echo "Run '~/moltbot-system/task-runner.sh status' to check background tasks"
EOF
chmod +x ~/start-moltbot.sh
```

### Step 8.2: Add to Login
```bash
echo '~/start-moltbot.sh' >> ~/.bashrc
```

---

## Part 9: Verify Installation

### Step 9.1: Reboot and Test
```bash
sudo reboot
```

After reboot:
1. Enter LUKS passphrase
2. Log in
3. System should auto-start Moltbot components
4. Run `moltbot` to test interactive mode

### Step 9.2: Test on Another Machine
1. Shut down the main machine
2. Unplug USB drive
3. Plug into another UEFI-compatible machine
4. Boot from USB
5. Verify everything works (model will use CPU if no compatible GPU)

---

## Troubleshooting

### LUKS passphrase prompt doesn't appear
- Check BIOS/UEFI boot order
- Ensure Secure Boot is disabled
- Try different USB port (USB 2.0 vs 3.0)

### Ollama not starting
```bash
sudo systemctl status ollama
sudo journalctl -u ollama -f
```

### Model running slow
- This is expected on CPU (~2-5 t/s)
- Ensure no other heavy processes running
- Check `htop` for resource usage

### Signal CLI issues
```bash
# Check registration status
signal-cli -a +1YOURPHONENUMBER listAccounts

# Receive messages manually
signal-cli -a +1YOURPHONENUMBER receive
```

---

## Next Steps
1. Read `02-SECURITY-HARDENING.md` for firewall and security setup
2. See task-specific guides in the `tasks/` directory
3. Customize your SOUL.md for your specific needs
