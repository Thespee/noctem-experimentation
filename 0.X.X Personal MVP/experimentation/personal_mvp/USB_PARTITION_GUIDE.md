# USB Shared Partition Setup Guide

This guide walks you through creating a 128GB shared partition on your 1TB USB drive that's already running Ubuntu Server.

## Prerequisites

- 1TB USB with Ubuntu Server already installed and working
- Booted into the USB system
- ~30 minutes of time

**⚠️ IMPORTANT**: This guide shrinks your Linux partition. While the commands are safe, having a backup is always wise.

---

## Step 1: Identify Your USB Drive

```bash
lsblk
```

You should see something like:
```
NAME   SIZE TYPE MOUNTPOINTS
sda    931G disk 
├─sda1 512M part /boot/efi
└─sda2 930G part /
```

**Confirm**: Your USB is likely `/dev/sda`. The root partition is `/dev/sda2`.

---

## Step 2: Check Current Disk Usage

```bash
df -h /
```

You need at least 128GB free. If you have less than 200GB free, consider cleaning up first.

---

## Step 3: Shrink the Linux Partition

### 3a. Boot into Recovery/Live USB (Recommended)

For safety, it's best to resize from a live USB rather than the running system:

1. Create a Ubuntu Live USB (separate from your Noctem USB)
2. Boot from the Live USB
3. Open a terminal

### 3b. Resize Using GParted (Graphical - Easier)

If you have a graphical environment:

```bash
sudo apt install gparted
sudo gparted
```

1. Select your USB drive (e.g., `/dev/sda`)
2. Right-click on the main Linux partition (`/dev/sda2`)
3. Select "Resize/Move"
4. Shrink it to ~872GB (leaving 128GB free)
5. Apply changes

### 3c. Resize Using Command Line (Text-Based)

If command line only:

```bash
# 1. Unmount the partition if mounted (run from live USB)
sudo umount /dev/sda2

# 2. Check filesystem
sudo e2fsck -f /dev/sda2

# 3. Resize filesystem to 870GB (leaving room for 128GB partition)
sudo resize2fs /dev/sda2 870G

# 4. Resize the partition using parted
sudo parted /dev/sda
(parted) resizepart 2 880GB
(parted) quit
```

---

## Step 4: Create the Shared Partition

```bash
# Install exfat tools
sudo apt install exfatprogs

# Create the new partition using remaining space
sudo parted /dev/sda mkpart primary 880GB 100%

# Check partition was created
sudo parted /dev/sda print
```

You should now see:
```
Number  Start   End     Size    Type     File system
1       1049kB  538MB   537MB   primary  fat32
2       538MB   880GB   880GB   primary  ext4
3       880GB   1000GB  120GB   primary
```

---

## Step 5: Format as exFAT

```bash
# Format with label "SHARED"
sudo mkfs.exfat /dev/sda3 -L SHARED

# Verify
sudo blkid /dev/sda3
```

Note the UUID from the output (looks like `XXXX-XXXX`).

---

## Step 6: Set Up Auto-Mount

```bash
# Create mount point
sudo mkdir -p /mnt/shared

# Get the UUID
UUID=$(sudo blkid -s UUID -o value /dev/sda3)

# Add to fstab
echo "UUID=$UUID /mnt/shared exfat defaults,uid=1000,gid=1000,umask=022 0 0" | sudo tee -a /etc/fstab

# Mount now
sudo mount -a

# Create symlink for easy access
ln -sf /mnt/shared ~/shared

# Verify
ls -la ~/shared
```

---

## Step 7: Create Directory Structure

```bash
mkdir -p /mnt/shared/{mvps,project-specs,project-specs/scrapers,data-exports,reports,calendar,transfers}

# Verify structure
tree /mnt/shared
```

Expected output:
```
/mnt/shared
├── calendar/        # Place ICS files here
├── data-exports/    # Scraped data exports
├── mvps/            # Generated MVP projects
├── project-specs/   # MVP project specifications
│   └── scrapers/    # Data scraper specifications
├── reports/         # Daily/weekly reports
└── transfers/       # General file transfers
```

---

## Step 8: Test from Another Machine

1. Shut down the USB system
2. Plug the USB into a Windows/Mac computer
3. It should appear as a drive called "SHARED"
4. You should see the folders you created
5. Try creating a test file

---

## Troubleshooting

### Partition shows as "Unknown" on Windows

Windows needs exFAT drivers (built-in since Windows 10). If issues:
```bash
# On Linux, reformat with NTFS instead
sudo apt install ntfs-3g
sudo mkfs.ntfs -f /dev/sda3 -L SHARED
```

### Can't shrink partition (not enough space)

```bash
# Check what's using space
sudo du -sh /* 2>/dev/null | sort -h
```

Clean up with:
```bash
sudo apt clean
sudo journalctl --vacuum-size=100M
```

### Mount failed after reboot

```bash
# Check fstab syntax
cat /etc/fstab

# Try manual mount
sudo mount -t exfat /dev/sda3 /mnt/shared
```

### Partition not visible when booted

```bash
# List partitions
sudo fdisk -l /dev/sda

# Check if exfat module is loaded
lsmod | grep exfat

# Load if missing
sudo modprobe exfat
```

---

## Quick Reference

| Item | Value |
|------|-------|
| Partition | `/dev/sda3` |
| Filesystem | exFAT |
| Label | SHARED |
| Size | ~128GB |
| Mount Point | `/mnt/shared` |
| Symlink | `~/shared` |

---

## What's Next?

Once the shared partition is ready:

1. Export your Google Calendar to ICS and place it at `~/shared/calendar/calendar.ics`
2. Create project specs in `~/shared/project-specs/`
3. The system will auto-detect these files for reports and MVP generation

---

*Part of Noctem Personal MVP v0.5*
