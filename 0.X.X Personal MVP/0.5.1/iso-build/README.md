# Noctem 0.5.1 - Ubuntu Server ISO Build

Create a replicable Ubuntu Server ISO with Noctem pre-installed.

## What This Creates

- Ubuntu Server-based ISO (~2GB)
- Noctem 0.5 pre-installed with all dependencies
- Auto-login to QR code display on boot
- First-run wizard for Telegram token setup
- SSH enabled for remote access

## Prerequisites

- Ubuntu desktop system (for running Cubic)
- 8GB+ free disk space
- Ubuntu Server 22.04 LTS ISO (download from ubuntu.com)

## Directory Structure

```
iso-build/
├── README.md           # This file
├── noctem-source/      # Clean Noctem code (no venv/data)
├── overlay/            # Files to install in ISO
│   ├── etc/
│   │   ├── systemd/system/
│   │   │   ├── noctem.service
│   │   │   └── getty@tty1.service.d/autologin.conf
│   │   └── NetworkManager/system-connections/
│   │       └── auto-ethernet.nmconnection
│   ├── usr/local/bin/
│   │   ├── noctem-wifi
│   │   ├── noctem-logs
│   │   └── noctem-cli
│   └── home/noctem/
│       ├── .bash_profile
│       └── first-run.sh
└── scripts/
    └── chroot-setup.sh  # Run inside Cubic chroot
```

## Step 1: Install Cubic

```bash
sudo apt-add-repository universe
sudo apt-add-repository ppa:cubic-wizard/release
sudo apt update
sudo apt install cubic
```

## Step 2: Download Ubuntu Server ISO

Download Ubuntu Server 22.04 LTS from:
https://ubuntu.com/download/server

Save it somewhere accessible (e.g., ~/Downloads/).

## Step 3: Prepare Noctem Source

Copy the clean Noctem source code (without venv, __pycache__, or data):

```bash
# From this directory
rsync -av --exclude='venv' --exclude='__pycache__' --exclude='*.pyc' \
    --exclude='data/*.db' --exclude='data/logs/*' \
    /path/to/0.5.0/noctem/ ./noctem-source/
```

Also copy the supporting files:
```bash
cp /path/to/0.5.0/requirements.txt ./noctem-source/
```

## Step 4: Launch Cubic

```bash
cubic
```

1. **Project Directory**: Create/select a folder (e.g., `~/cubic-noctem-project`)
2. **Original ISO**: Select the Ubuntu Server 22.04 ISO you downloaded
3. **Custom ISO**: Set filename to `noctem-0.5.1-ubuntu-server.iso`
4. Click **Next** to enter the chroot environment

## Step 5: Run Setup in Chroot

Once in the Cubic chroot terminal:

```bash
# Copy build files into chroot (from another terminal)
# Cubic mounts the chroot at: ~/cubic-noctem-project/custom-root/

# In your regular terminal (not chroot):
sudo cp -r /path/to/iso-build/* ~/cubic-noctem-project/custom-root/tmp/

# Back in Cubic chroot terminal:
cd /tmp
chmod +x scripts/chroot-setup.sh
./scripts/chroot-setup.sh
```

The script will:
- Install Python and dependencies
- Create the `noctem` user
- Set up the virtual environment
- Install Noctem and all overlay files
- Enable auto-start services

## Step 6: Finalize ISO

1. Type `exit` to leave the chroot
2. Click **Next** in Cubic
3. (Optional) Customize kernel/boot options
4. Click **Generate** to create the ISO

## Step 7: Create Bootable USB

```bash
# Find your USB device
lsblk

# Write ISO to USB (replace sdX with your device!)
sudo dd if=noctem-0.5.1-ubuntu-server.iso of=/dev/sdX bs=4M status=progress
sync
```

**WARNING**: Double-check the device name! `dd` will overwrite everything.

## First Boot

1. Boot from USB
2. First-run wizard prompts for:
   - Telegram bot token (get from @BotFather)
   - Timezone
   - Morning briefing time
3. System reboots
4. QR code displays automatically
5. Scan to access web dashboard

## Default Credentials

- **User**: `noctem`
- **Password**: `noctem`
- **SSH**: Enabled (change password after first login!)

## Importing Existing Data

To restore data from an existing Noctem installation:

```bash
# SSH into the running system
ssh noctem@<ip-address>

# Stop the service
sudo systemctl stop noctem

# Copy your database
scp user@source:/path/to/noctem.db /home/noctem/noctem/noctem/data/

# Restart
sudo systemctl start noctem
```

## Troubleshooting

### No network after boot
- Connect Ethernet, or
- Press Ctrl+C to get shell, run `noctem-wifi`

### Service won't start
```bash
sudo systemctl status noctem
noctem-logs
```

### Need to reconfigure
```bash
rm ~/.noctem_configured
# Reboot or re-run first-run.sh
```

## Testing Checklist

- [ ] ISO boots successfully
- [ ] Auto-login to noctem user works
- [ ] First-run wizard appears
- [ ] Network connects (Ethernet/WiFi)
- [ ] QR code displays with correct IP
- [ ] Web dashboard accessible from phone
- [ ] Telegram bot responds after token setup
- [ ] SSH access works
- [ ] Survives reboot
