# Noctem USB Setup Guide

This guide walks you through creating a bootable USB drive with Noctem. No technical experience required.

## What You'll Need

- **1TB USB Flash Drive** (or larger)
- **A computer** with internet access
- **~2 hours** of time
- **Your phone** with Signal installed

---

## Part 1: Create the Bootable USB

### Step 1: Download Ubuntu Server

1. Go to: **https://ubuntu.com/download/server**
2. Click **"Download Ubuntu Server"** (get the LTS version)
3. Save the `.iso` file to your Downloads folder

### Step 2: Download Rufus (Windows) or balenaEtcher (Mac/Linux)

**Windows:**
1. Go to: **https://rufus.ie**
2. Download Rufus (portable version is fine)

**Mac/Linux:**
1. Go to: **https://www.balena.io/etcher**
2. Download and install balenaEtcher

### Step 3: Create the Bootable USB

**⚠️ WARNING: This will ERASE everything on the USB drive!**

**Using Rufus (Windows):**
1. Plug in your USB drive
2. Open Rufus
3. Select your USB drive under "Device"
4. Click "SELECT" and choose the Ubuntu .iso file
5. Under "Partition scheme" select **GPT**
6. Click **START**
7. Wait for it to complete (~10-15 minutes)

**Using balenaEtcher (Mac/Linux):**
1. Plug in your USB drive
2. Open balenaEtcher
3. Click "Flash from file" and select the Ubuntu .iso
4. Select your USB drive
5. Click "Flash!"
6. Wait for it to complete

---

## Part 2: Install Ubuntu Server

### Step 1: Boot from USB

1. Plug the USB into the computer that will run Noctem
2. Turn on/restart the computer
3. Press the boot menu key during startup:
   - **Dell**: F12
   - **HP**: F9 or Esc
   - **Lenovo**: F12
   - **Asus**: F8 or Esc
   - **Mac**: Hold Option key
4. Select the USB drive from the boot menu

### Step 2: Install Ubuntu

Follow the on-screen prompts:

1. **Language**: English
2. **Keyboard**: Your keyboard layout
3. **Installation type**: Ubuntu Server
4. **Network**: Connect to WiFi or Ethernet
5. **Storage**: 
   - Select your USB drive (NOT your computer's hard drive!)
   - Choose "Use entire disk"
   - **Important**: Make sure you're installing TO the USB, not erasing your computer!
6. **Profile setup**:
   - Your name: `noctem` (or your name)
   - Server name: `noctem`
   - Username: `noctem`
   - Password: Choose a strong password
7. **SSH**: ✅ Enable OpenSSH server
8. **Featured snaps**: Skip this (press Tab, then Enter)

Wait for installation to complete (~15-30 minutes), then reboot.

### Step 3: First Boot & Updates

After reboot, log in with your username and password:

```bash
# Update the system
sudo apt update && sudo apt upgrade -y

# Install git
sudo apt install -y git
```

---

## Part 3: Install Noctem

### Step 1: Download Noctem

```bash
# Clone the repository
cd ~
git clone https://github.com/Thespee/noctem.git
cd noctem
```

### Step 2: Configure Passwordless Sudo

This allows Noctem to install software automatically:

```bash
# Open the sudoers file
sudo visudo
```

Add this line at the bottom (replace `noctem` with your username if different):
```
noctem ALL=(ALL) NOPASSWD: ALL
```

Press `Ctrl+X`, then `Y`, then `Enter` to save.

### Step 3: Run the Birth Process

```bash
python3 birth/run.py
```

This will automatically:
- ✅ Check your system
- ✅ Install all required software
- ✅ Download AI models (~5GB)
- ✅ Configure auto-start

**This takes 30-60 minutes** depending on your internet speed.

---

## Part 4: Set Up Signal Messaging

### Step 1: Install signal-cli

The birth process installs signal-cli, but you need to register it with your phone number.

### Step 2: Register Your Number

```bash
# Replace +1234567890 with your actual phone number
signal-cli -u +1234567890 register
```

You'll receive an SMS with a verification code.

```bash
# Enter the code you received
signal-cli -u +1234567890 verify CODE
```

### Step 3: Configure Noctem

```bash
# Edit the config file
nano ~/noctem/data/config.json
```

Add your phone number:
```json
{
  "signal_phone": "+1234567890",
  ...
}
```

Press `Ctrl+X`, `Y`, `Enter` to save.

### Step 4: Start the Signal Daemon

```bash
# Start signal-cli in daemon mode
nohup signal-cli -u +1234567890 daemon --tcp 127.0.0.1:7583 > /tmp/signal-daemon.log 2>&1 &
```

---

## Part 5: Start Noctem

### Option A: Manual Start

```bash
cd ~/noctem
python3 main.py
```

### Option B: Auto-Start on Boot

This was configured during birth. Just reboot:

```bash
sudo reboot
```

Noctem will start automatically!

---

## Part 6: Create Shared Data Partition (Optional)

This creates a partition accessible from Windows/Android when the USB is plugged in.

### Step 1: Create the Partition

```bash
# Find your USB device (usually /dev/sda or /dev/sdb)
lsblk

# Create a new partition (replace /dev/sdX with your device)
sudo fdisk /dev/sdX
# Press: n (new), p (primary), Enter (default), Enter (default), Enter (default)
# Press: t (type), Enter (select partition), 7 (exFAT/NTFS)
# Press: w (write)

# Format as exFAT
sudo mkfs.exfat /dev/sdX3 -n SHARED
```

### Step 2: Auto-Mount on Boot

```bash
# Get the UUID
sudo blkid /dev/sdX3

# Edit fstab
sudo nano /etc/fstab
```

Add this line (replace UUID with yours):
```
UUID=YOUR-UUID-HERE /mnt/shared exfat defaults,uid=1000,gid=1000 0 0
```

```bash
# Create mount point and mount
sudo mkdir -p /mnt/shared
sudo mount -a
```

---

## Troubleshooting

### "Birth process failed"
- Check the log: `cat ~/noctem/logs/birth.log`
- Retry: `python3 birth/run.py --fresh`

### "Ollama not responding"
```bash
sudo systemctl restart ollama
sudo systemctl status ollama
```

### "Signal messages not working"
```bash
# Check if daemon is running
pgrep -f "signal-cli.*daemon"

# Restart daemon
pkill -f signal-cli
signal-cli -u YOUR_PHONE daemon --tcp 127.0.0.1:7583 &
```

### "Can't boot from USB"
- Disable Secure Boot in BIOS
- Enable Legacy/CSM boot mode
- Try a different USB port

---

## Getting Help

If you get stuck during birth, Noctem will send you a Signal message with instructions.

Reply with:
- `/umb connect user@server` - Get remote help (requires relay server)
- `/umb retry` - Retry the failed step
- `/umb skip` - Skip the current step
- `/umb abort` - Cancel and start over

---

## What's Next?

Once Noctem is running, text it via Signal:
- "Hello!" - Test the connection
- "/help" - See available commands
- "/status" - Check system status

Welcome to Noctem! 🌙
