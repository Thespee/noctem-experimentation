# Moltbot/OpenClaw Setup Summary

## What We Built
A portable Linux system on USB that runs a local AI assistant, accessible via Signal messaging from your phone.

---

## Hardware Setup

### Requirements
- **Two USB drives**: One for installer (8GB+), one for target system (128GB+)
- **RAM**: 12-16GB detected → 3B model tier
- **GPU**: GTX 1050 Max-Q present but drivers not installed (CPU-only mode)

### Ubuntu Server Installation
1. Download Ubuntu Server 24.04 LTS
2. Create bootable USB with Rufus (GPT, UEFI)
3. Boot from installer USB with target USB also plugged in
4. **Storage**: Use "Custom storage layout"
   - Select target USB (verify by size!)
   - Use "Use as Boot Device" to create GPT + EFI partition
   - Add 1GB ext4 `/boot` partition
   - Add remaining space as encrypted (LUKS) ext4 `/`
   - Note: exFAT shared partition must be formatted AFTER install
5. Enable OpenSSH server during install

### Gotcha: Encryption
- Ubuntu Server installer's manual mode may not show encryption option
- Alternative: Use "guided entire disk with LVM + encryption"
- Shared partition can be added later (complex) or skipped

---

## Software Installation

### Ollama
```bash
curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl enable ollama
ollama pull qwen2.5:3b-instruct-q4_K_M
```

### Model Tiers (from optimizer)
| RAM | Model | Speed |
|-----|-------|-------|
| 8GB | 1.5B | 2-8 t/s |
| 12GB | 3B | 4-10 t/s |
| 16GB | 7B | 3-5 t/s |
| 32GB | 14B | 2-4 t/s |
| GPU 4GB+ | 7B+ | 15-100+ t/s |

### Signal CLI
```bash
# Get latest version
VERSION=$(curl -Ls -o /dev/null -w %{url_effective} https://github.com/AsamK/signal-cli/releases/latest | sed -e 's/^.*\/v//')
curl -L -O "https://github.com/AsamK/signal-cli/releases/download/v${VERSION}/signal-cli-${VERSION}.tar.gz"
sudo tar xf "signal-cli-${VERSION}.tar.gz" -C /opt
sudo ln -sf "/opt/signal-cli-${VERSION}/bin/signal-cli" /usr/local/bin/
```

### Signal Registration - IMPORTANT LESSONS

**Option A: Register as primary device**
- `signal-cli -a +1NUMBER register --captcha "CAPTCHA"`
- `signal-cli -a +1NUMBER verify CODE`
- ⚠️ This DISCONNECTS your phone from Signal!

**Option B: Link as secondary device (RECOMMENDED)**
- Keeps phone AND server both receiving messages
- `signal-cli link -n "moltbot"`
- Generates QR code to scan with phone
- Phone: Settings → Linked Devices → + → Scan

**QR Code on headless server:**
```bash
sudo apt install qrencode
signal-cli link -n "moltbot" 2>&1 | tee /tmp/link.txt &
sleep 2
head -1 /tmp/link.txt | qrencode -t ANSIUTF8
```

**Captcha notes:**
- Get from: https://signalcaptchas.org/registration/generate.html
- Expires in ~5 minutes
- When it tries to open `signalcaptcha://...`, copy that URL
- Use the part after `signalcaptcha://` as the captcha value

---

## OpenClaw Setup

### Installation
```bash
curl -fsSL https://openclaw.ai/install.sh | bash
```

### Configure for Ollama
Set environment variable BEFORE onboarding:
```bash
export OLLAMA_API_KEY="ollama-local"
openclaw onboard
```

This makes OpenClaw auto-detect local Ollama models.

### Manual Config (if needed)
Edit `~/.openclaw/openclaw.json`:
```json
{
  "models": {
    "providers": {
      "ollama": {
        "baseUrl": "http://127.0.0.1:11434/v1",
        "apiKey": "ollama-local",
        "api": "openai-completions"
      }
    }
  },
  "agents": {
    "defaults": {
      "model": {
        "primary": "ollama/qwen2.5:3b-instruct-q4_K_M"
      }
    }
  }
}
```

### Remote Dashboard Access
From your laptop:
```bash
ssh -N -L 18789:127.0.0.1:18789 user@SERVER_IP
```
Then open: `http://localhost:18789/`

---

## Troubleshooting

### I/O Errors
- Sign of USB drive or filesystem issues
- Reboot immediately
- May need to reinstall corrupted packages

### Signal "user not registered"
- Registration didn't complete
- Re-register with fresh captcha

### Firewall blocking SSH
- `sudo ufw allow ssh` or `sudo ufw disable`
- The setup script's firewall config can lock you out

### OpenClaw not responding
- Check Ollama directly: `time ollama run MODEL "hello"`
- Check config is pointing to ollama, not claude
- Check gateway is running: `ps aux | grep openclaw`
- Restart: `pkill -f openclaw && openclaw gateway`

### Model slow
- First message loads model into RAM (30-60s)
- 3B on CPU ≈ 8 seconds for simple response
- This is normal for CPU inference

---

## Minimal Working Setup (DIY Version)

If OpenClaw is too heavy, here's a bare-bones Signal → AI → Signal loop:

```bash
export SIGNAL_PHONE="+1YOURNUMBER"
MODEL="qwen2.5:3b-instruct-q4_K_M"

while true; do
    signal-cli receive | while read -r line; do
        if echo "$line" | grep -q "Body:"; then
            message=$(echo "$line" | sed 's/.*Body: //')
            echo "Got: $message"
            response=$(ollama run "$MODEL" "$message" 2>/dev/null | head -c 1500)
            signal-cli send -m "$response" "$SIGNAL_PHONE"
        fi
    done
    sleep 2
done
```

---

## Key Lessons Learned

1. **Signal registration kicks phone off** - Use `link` not `register`
2. **Captchas expire fast** - Have browser ready, paste immediately
3. **Firewall can lock you out** - Be careful with UFW rules
4. **First AI response is slow** - Model loading takes time
5. **USB I/O errors are serious** - Reboot and check filesystem
6. **OpenClaw needs OLLAMA_API_KEY env var** - Set before onboarding
7. **signal-cli `--json` flag removed** - Newer versions changed syntax
8. **CPU inference is slow but works** - 8 seconds for simple response is normal

---

## Services to Enable for Auto-start

```bash
sudo systemctl enable ollama
# OpenClaw gateway may run as user service or need manual start
```

---

## Files Created

| File | Purpose |
|------|---------|
| `~/.openclaw/openclaw.json` | OpenClaw configuration |
| `~/.local/share/signal-cli/` | Signal account data |
| `~/.moltbot-model` | (Custom) Stores preferred model name |

---

## Where to Go From Here

### Immediate Next Steps
1. **Test Signal integration** — Send a message to Note to Self, verify AI responds
2. **Install GPU drivers** (optional) — For faster inference:
   ```bash
   sudo apt install nvidia-driver-535
   sudo reboot
   ```
   Then re-run optimizer to use GPU

3. **Re-run optimizer** — After GPU drivers or hardware changes:
   ```bash
   python3 ~/moltbot-system/skills/optimizer.py apply
   ```

### Add Capabilities
- **Skills** — OpenClaw supports plugins for calendar, email, web scraping, etc.
- **Tools** — Give AI ability to run shell commands, read/write files
- **Multiple messaging apps** — Telegram, WhatsApp, Discord also supported

### Security Hardening
- Review `02-SECURITY-HARDENING.md` for:
  - Firewall rules
  - Network logging
  - Outbound request filtering
  - Signal whitelist (only respond to your number)

### Documentation to Read
- `01-MASTER-SETUP-GUIDE.md` — Full setup with more features
- `02-SECURITY-HARDENING.md` — Lock down the system
- `skills/` folder — Individual skill documentation
- https://docs.openclaw.ai — OpenClaw official docs

### If Building Your Own Version
Start with the minimal DIY loop (above), then add:
1. Tool execution (`/run` commands)
2. Persistent conversation memory
3. Skill routing (calendar, email, etc.)
4. Cloud fallback for complex tasks

---

Good luck with your own version! 🚀
