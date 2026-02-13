# Security Hardening Guide

## Overview
This guide implements security measures to ensure:
- **No personal data leaves the system** except through controlled channels
- **Read-only internet access** for fetching data only
- **Full disk encryption** protects data at rest
- **Signal integration** for secure remote communication
- **Audit logging** for all external network activity

---

## Part 1: Firewall Configuration (UFW)

### Step 1.1: Basic Firewall Setup
```bash
# Enable UFW
sudo ufw default deny incoming
sudo ufw default deny outgoing
sudo ufw enable
```

### Step 1.2: Allow Essential Outgoing Traffic
```bash
# DNS resolution (required for hostname lookups)
sudo ufw allow out 53/udp
sudo ufw allow out 53/tcp

# HTTP/HTTPS for web scraping and API access
sudo ufw allow out 80/tcp
sudo ufw allow out 443/tcp

# Signal messaging (Signal servers)
sudo ufw allow out 443/tcp

# NTP for time synchronization
sudo ufw allow out 123/udp
```

### Step 1.3: Block Known Data Exfiltration Ports
```bash
# Block common exfiltration methods
sudo ufw deny out 25/tcp    # SMTP (prevent email sending)
sudo ufw deny out 587/tcp   # SMTP submission
sudo ufw deny out 465/tcp   # SMTPS
sudo ufw deny out 22/tcp    # SSH outbound (prevent reverse shells)
```

### Step 1.4: Allow Local Services
```bash
# Localhost communication (Ollama, etc.)
sudo ufw allow from 127.0.0.1
sudo ufw allow to 127.0.0.1
```

### Step 1.5: Verify Firewall Rules
```bash
sudo ufw status verbose
```

---

## Part 2: Network Traffic Logging

### Step 2.1: Install and Configure iptables Logging
```bash
# Create logging rules for outbound connections
sudo iptables -A OUTPUT -m state --state NEW -j LOG --log-prefix "OUTBOUND: " --log-level 4
sudo iptables -A OUTPUT -p tcp --dport 443 -j LOG --log-prefix "HTTPS_OUT: " --log-level 4
sudo iptables -A OUTPUT -p tcp --dport 80 -j LOG --log-prefix "HTTP_OUT: " --log-level 4
```

### Step 2.2: Configure rsyslog for Network Logs
```bash
sudo tee /etc/rsyslog.d/50-network.conf << 'EOF'
# Log all network traffic to separate file
:msg, contains, "OUTBOUND:" /var/log/network-outbound.log
:msg, contains, "HTTPS_OUT:" /var/log/network-outbound.log
:msg, contains, "HTTP_OUT:" /var/log/network-outbound.log
& stop
EOF

sudo systemctl restart rsyslog
```

### Step 2.3: Log Rotation
```bash
sudo tee /etc/logrotate.d/network-outbound << 'EOF'
/var/log/network-outbound.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 640 root adm
}
EOF
```

---

## Part 3: Outbound Request Proxy (mitmproxy)

For additional control, you can route all HTTP/HTTPS traffic through a local proxy.

### Step 3.1: Install mitmproxy
```bash
pip3 install mitmproxy
```

### Step 3.2: Create Filtering Script
```bash
mkdir -p ~/moltbot-system/security

cat > ~/moltbot-system/security/filter-proxy.py << 'EOF'
"""
Moltbot Outbound Proxy Filter
Blocks requests containing personal data patterns
"""

import re
from mitmproxy import ctx, http

# Patterns that should NEVER be sent externally
BLOCKED_PATTERNS = [
    r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',  # Email addresses
    r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',  # Phone numbers
    r'\b\d{3}[-]?\d{2}[-]?\d{4}\b',  # SSN pattern
    r'\b\d{16}\b',  # Credit card numbers
    r'password["\s:=]+[^&\s]+',  # Password fields
    r'api[_-]?key["\s:=]+[^&\s]+',  # API keys (except allowed)
]

# Allowed domains for external requests
ALLOWED_DOMAINS = [
    'google.com',
    'googleapis.com',
    'signal.org',
    'whispersystems.org',  # Signal
    'github.com',
    'githubusercontent.com',
    # Add domains your tasks need
]

# Always block these domains (known tracking/analytics)
BLOCKED_DOMAINS = [
    'doubleclick.net',
    'google-analytics.com',
    'facebook.com',
    'fbcdn.net',
    'analytics.',
    'tracker.',
    'telemetry.',
]

def check_blocked_patterns(content: str) -> tuple[bool, str]:
    """Check if content contains blocked patterns"""
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            return True, pattern
    return False, ""

def is_blocked_domain(host: str) -> bool:
    """Check if domain is blocked"""
    for blocked in BLOCKED_DOMAINS:
        if blocked in host.lower():
            return True
    return False

class OutboundFilter:
    def request(self, flow: http.HTTPFlow) -> None:
        host = flow.request.host
        
        # Block known bad domains
        if is_blocked_domain(host):
            ctx.log.warn(f"BLOCKED (domain): {host}")
            flow.kill()
            return
        
        # Check request body for personal data
        if flow.request.content:
            content = flow.request.content.decode('utf-8', errors='ignore')
            blocked, pattern = check_blocked_patterns(content)
            if blocked:
                ctx.log.error(f"BLOCKED (personal data pattern): {pattern}")
                flow.kill()
                return
        
        # Check URL parameters
        url = flow.request.pretty_url
        blocked, pattern = check_blocked_patterns(url)
        if blocked:
            ctx.log.error(f"BLOCKED (URL contains personal data): {pattern}")
            flow.kill()
            return
        
        # Log all allowed requests
        ctx.log.info(f"ALLOWED: {flow.request.method} {host}{flow.request.path}")

addons = [OutboundFilter()]
EOF
```

### Step 3.3: Create Proxy Service
```bash
sudo tee /etc/systemd/system/moltbot-proxy.service << 'EOF'
[Unit]
Description=Moltbot Outbound Proxy Filter
After=network.target

[Service]
Type=simple
User=moltbot
ExecStart=/usr/local/bin/mitmdump -p 8080 -s /home/moltbot/moltbot-system/security/filter-proxy.py --set block_global=false
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Don't start yet - this is optional
# sudo systemctl enable moltbot-proxy
```

### Step 3.4: Configure System to Use Proxy (Optional)
If you want to force all traffic through the proxy:
```bash
# Add to ~/.bashrc
export HTTP_PROXY=http://127.0.0.1:8080
export HTTPS_PROXY=http://127.0.0.1:8080
export NO_PROXY=localhost,127.0.0.1
```

---

## Part 4: Application-Level Security

### Step 4.1: Secure Environment Variables
Create a secure env file that's not world-readable:
```bash
# Create secure directory
mkdir -p ~/.config/moltbot
chmod 700 ~/.config/moltbot

# Create env file
cat > ~/.config/moltbot/env << 'EOF'
# Google API credentials (read-only access)
GOOGLE_CLIENT_ID=your_client_id_here
GOOGLE_CLIENT_SECRET=your_client_secret_here

# Signal phone number
SIGNAL_PHONE=+1YOURPHONENUMBER

# Never store these here:
# - Banking credentials
# - Social media passwords
# - Full SSN or ID numbers
EOF

chmod 600 ~/.config/moltbot/env
```

### Step 4.2: Load Secure Environment
Add to your startup script:
```bash
# Add to ~/start-moltbot.sh
if [[ -f ~/.config/moltbot/env ]]; then
    set -a
    source ~/.config/moltbot/env
    set +a
fi
```

### Step 4.3: Audit All curl/wget Requests
Create wrapper scripts that log all external requests:
```bash
cat > ~/moltbot-system/security/safe-curl << 'EOF'
#!/bin/bash
# Wrapper for curl that logs all requests

LOG_FILE="$HOME/moltbot-system/logs/http-requests.log"

# Log the request
echo "[$(date -Iseconds)] curl $@" >> "$LOG_FILE"

# Check for personal data in arguments
for arg in "$@"; do
    # Check for email pattern
    if echo "$arg" | grep -qE '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}'; then
        echo "ERROR: Detected email address in curl request. Blocked." >&2
        echo "[$(date -Iseconds)] BLOCKED: email in args" >> "$LOG_FILE"
        exit 1
    fi
done

# Execute curl
/usr/bin/curl "$@"
EOF

chmod +x ~/moltbot-system/security/safe-curl

# Create alias
echo 'alias curl="$HOME/moltbot-system/security/safe-curl"' >> ~/.bashrc
```

---

## Part 5: Signal Security Configuration

### Step 5.1: Restrict Signal Access
Only allow Signal to communicate with your own number:
```bash
cat > ~/moltbot-system/security/signal-whitelist.txt << 'EOF'
# Allowed Signal numbers (one per line)
+1YOURNUMBER
# Add trusted contacts here
EOF

chmod 600 ~/moltbot-system/security/signal-whitelist.txt
```

### Step 5.2: Create Secure Signal Handler
```bash
cat > ~/moltbot-system/signal-handler.sh << 'EOF'
#!/bin/bash
# Secure Signal message handler

WHITELIST_FILE="$HOME/moltbot-system/security/signal-whitelist.txt"
LOG_FILE="$HOME/moltbot-system/logs/signal.log"
SIGNAL_ACCOUNT="+1YOURPHONENUMBER"

# Check if sender is whitelisted
is_whitelisted() {
    local sender="$1"
    grep -qF "$sender" "$WHITELIST_FILE"
}

# Process incoming message
process_message() {
    local sender="$1"
    local message="$2"
    
    echo "[$(date -Iseconds)] FROM: $sender MSG: $message" >> "$LOG_FILE"
    
    if ! is_whitelisted "$sender"; then
        echo "[$(date -Iseconds)] BLOCKED: unknown sender $sender" >> "$LOG_FILE"
        return
    fi
    
    # Command parsing
    case "$message" in
        "status")
            signal-cli -a "$SIGNAL_ACCOUNT" send -m "System online. Tasks: $(~/moltbot-system/task-runner.sh status)" "$sender"
            ;;
        "tasks")
            signal-cli -a "$SIGNAL_ACCOUNT" send -m "$(ls ~/moltbot-system/tasks/)" "$sender"
            ;;
        "logs")
            signal-cli -a "$SIGNAL_ACCOUNT" send -m "$(tail -10 ~/moltbot-system/logs/tasks.log)" "$sender"
            ;;
        run:*)
            local cmd="${message#run:}"
            # Only allow pre-approved commands
            case "$cmd" in
                check-calendar|check-email|scrape-*)
                    echo "[$(date -Iseconds)] EXECUTING: $cmd" >> "$LOG_FILE"
                    result=$(bash ~/moltbot-system/tasks/"$cmd".sh 2>&1 | tail -5)
                    signal-cli -a "$SIGNAL_ACCOUNT" send -m "Result: $result" "$sender"
                    ;;
                *)
                    signal-cli -a "$SIGNAL_ACCOUNT" send -m "Unknown command: $cmd" "$sender"
                    ;;
            esac
            ;;
        *)
            signal-cli -a "$SIGNAL_ACCOUNT" send -m "Unknown command. Try: status, tasks, logs, run:<task>" "$sender"
            ;;
    esac
}

# Listen for messages
signal-cli -a "$SIGNAL_ACCOUNT" receive --json | while read -r line; do
    # Parse JSON (basic parsing)
    sender=$(echo "$line" | jq -r '.envelope.source // empty')
    message=$(echo "$line" | jq -r '.envelope.dataMessage.message // empty')
    
    if [[ -n "$sender" && -n "$message" ]]; then
        process_message "$sender" "$message"
    fi
done
EOF

chmod +x ~/moltbot-system/signal-handler.sh
```

---

## Part 6: Disk Security

### Step 6.1: Backup LUKS Header
Your LUKS header is critical - back it up:
```bash
# Mount your backup drive
sudo mount /dev/sdX1 /mnt/backup  # Replace with your backup drive

# Backup LUKS header
sudo cryptsetup luksHeaderBackup /dev/sdY3 \
    --header-backup-file /mnt/backup/luks-header-backup.img

# Also backup to external location (encrypted)
gpg -c /mnt/backup/luks-header-backup.img
# This creates luks-header-backup.img.gpg - store this safely

sudo umount /mnt/backup
```

### Step 6.2: Add Recovery Key
```bash
# Add a backup passphrase (store securely!)
sudo cryptsetup luksAddKey /dev/sdY3  # Your encrypted partition

# This allows you to have a recovery passphrase
```

### Step 6.3: Verify Encryption Status
```bash
# Check LUKS status
sudo cryptsetup status /dev/mapper/dm_crypt-0  # Your mapped device

# Should show:
# type:    LUKS2
# cipher:  aes-xts-plain64
# keysize: 512 bits
```

---

## Part 7: System Hardening

### Step 7.1: Disable Unnecessary Services
```bash
# List running services
systemctl list-units --type=service --state=running

# Disable services you don't need
sudo systemctl disable cups         # Printing
sudo systemctl disable avahi-daemon # mDNS (network discovery)
sudo systemctl disable bluetooth    # If not needed
```

### Step 7.2: Secure SSH (if enabled)
```bash
sudo tee -a /etc/ssh/sshd_config << 'EOF'

# Security hardening
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
MaxAuthTries 3
X11Forwarding no
AllowTcpForwarding no
EOF

# Generate SSH key for remote access (if needed)
ssh-keygen -t ed25519 -f ~/.ssh/moltbot_key

sudo systemctl restart sshd
```

### Step 7.3: Automatic Security Updates
```bash
sudo apt install unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades
```

---

## Part 8: Monitoring and Alerts

### Step 8.1: Create Security Monitor
```bash
cat > ~/moltbot-system/security/monitor.sh << 'EOF'
#!/bin/bash
# Security monitoring script

LOG_DIR="$HOME/moltbot-system/logs"
ALERT_FILE="$LOG_DIR/security-alerts.log"

# Check for suspicious outbound connections
check_connections() {
    local suspicious=$(netstat -an | grep ESTABLISHED | grep -v '127.0.0.1' | grep -v ':443' | grep -v ':80' | grep -v ':53')
    if [[ -n "$suspicious" ]]; then
        echo "[$(date -Iseconds)] ALERT: Suspicious connections detected:" >> "$ALERT_FILE"
        echo "$suspicious" >> "$ALERT_FILE"
        return 1
    fi
    return 0
}

# Check disk encryption status
check_encryption() {
    if ! cryptsetup status /dev/mapper/dm_crypt-0 &>/dev/null; then
        echo "[$(date -Iseconds)] ALERT: Disk encryption check failed!" >> "$ALERT_FILE"
        return 1
    fi
    return 0
}

# Check for failed login attempts
check_logins() {
    local failed=$(grep "Failed password" /var/log/auth.log 2>/dev/null | tail -5)
    if [[ -n "$failed" ]]; then
        echo "[$(date -Iseconds)] ALERT: Failed login attempts:" >> "$ALERT_FILE"
        echo "$failed" >> "$ALERT_FILE"
    fi
}

# Run checks
check_connections
check_encryption
check_logins

echo "[$(date -Iseconds)] Security check completed" >> "$LOG_DIR/security.log"
EOF

chmod +x ~/moltbot-system/security/monitor.sh
```

### Step 8.2: Schedule Security Checks
```bash
# Add to crontab
(crontab -l 2>/dev/null; echo "*/30 * * * * $HOME/moltbot-system/security/monitor.sh") | crontab -
```

---

## Part 9: Security Checklist

Run through this checklist periodically:

### Daily
- [ ] Check `~/moltbot-system/logs/security-alerts.log` for alerts
- [ ] Review `~/moltbot-system/logs/http-requests.log` for unexpected requests
- [ ] Verify Signal handler is responding

### Weekly
- [ ] Run `sudo ufw status` to verify firewall rules
- [ ] Check `df -h` for unexpected disk usage
- [ ] Review systemd service status

### Monthly
- [ ] Update system: `sudo apt update && sudo apt upgrade`
- [ ] Rotate logs
- [ ] Backup LUKS header to external storage
- [ ] Review and update allowed domains list

---

## Emergency Procedures

### If You Suspect a Breach
1. **Disconnect from network immediately**
   ```bash
   sudo ip link set eth0 down
   sudo ip link set wlan0 down
   ```

2. **Check running processes**
   ```bash
   ps aux | grep -v "^root\|^moltbot"
   ```

3. **Review recent network connections**
   ```bash
   cat ~/moltbot-system/logs/network-outbound.log | tail -100
   ```

4. **Change LUKS passphrase**
   ```bash
   sudo cryptsetup luksChangeKey /dev/sdY3
   ```

5. **Re-register Signal** (revokes old sessions)
   ```bash
   signal-cli -a +1YOURPHONENUMBER unregister
   # Then re-register
   ```

### If USB Drive is Lost/Stolen
- Data is encrypted - without passphrase, data is unrecoverable
- Change any API keys/tokens that were stored
- Revoke Google OAuth tokens
- Re-register Signal on new device
