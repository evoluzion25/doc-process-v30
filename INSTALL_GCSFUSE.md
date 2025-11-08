# Cloud Storage FUSE Installation Guide for Windows

**Purpose**: Mount GCS buckets as local filesystem on Windows using WSL2  
**Location**: `E:\00_dev_1\y_apps\x3_doc-processing\INSTALL_GCSFUSE.md`  
**Date**: 2025-11-05

---

## Overview

Cloud Storage FUSE lets you mount Google Cloud Storage buckets as local file systems. This enables you to:
- Access GCS files using standard file paths (e.g., `G:\fremont-1\docs\file.pdf`)
- Read/write files without explicit API calls
- Use existing tools that expect local filesystems

**Important**: Cloud Storage FUSE is NOT POSIX-compliant and has [limitations](https://cloud.google.com/storage/docs/cloud-storage-fuse/overview#limitations). Use it within its capabilities.

---

## Prerequisites

### 1. Windows Subsystem for Linux 2 (WSL2)

Cloud Storage FUSE runs on Linux, so you need WSL2 on Windows.

**Check if WSL2 is installed**:
```powershell
wsl --status
```

**Install WSL2** (if not installed):
```powershell
# Run as Administrator
wsl --install -d Ubuntu-22.04

# Restart computer after installation
```

**Set default WSL version to 2**:
```powershell
wsl --set-default-version 2
```

**Verify installation**:
```powershell
wsl -l -v
# Should show Ubuntu-22.04 with VERSION 2
```

### 2. Google Cloud Credentials

Ensure you have service account credentials:
- **File**: `E:\00_dev_1\01_secrets\gcp-credentials.json`
- **Service Account**: `legal-doc-processor@devops-227806.iam.gserviceaccount.com`
- **Required Permissions**: Storage Object Viewer (minimum) or Storage Admin (recommended)

---

## Installation Steps

### Step 1: Enter WSL Environment

```powershell
wsl -d Ubuntu-22.04
```

### Step 2: Install Dependencies

```bash
# Update package lists
sudo apt-get update

# Install FUSE library
sudo apt-get install -y fuse

# Verify FUSE is installed
fusermount -V
```

### Step 3: Configure Package Manager for Cloud Storage FUSE

**For Ubuntu 22.04+**:
```bash
export GCSFUSE_REPO=gcsfuse-`lsb_release -c -s`

echo "deb https://packages.cloud.google.com/apt $GCSFUSE_REPO main" | sudo tee /etc/apt/sources.list.d/gcsfuse.list

curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo apt-key add -
```

### Step 4: Install Cloud Storage FUSE

```bash
sudo apt-get update
sudo apt-get install -y gcsfuse

# Verify installation
gcsfuse --version
```

Expected output: `gcsfuse version X.X.X`

### Step 5: Set Up Google Cloud Credentials in WSL

**Option A: Copy credentials to WSL home directory** (Recommended):
```bash
# Create credentials directory
mkdir -p ~/.config/gcloud

# Copy credentials from Windows to WSL
cp /mnt/e/00_dev_1/01_secrets/gcp-credentials.json ~/.config/gcloud/application_default_credentials.json

# Set environment variable
echo 'export GOOGLE_APPLICATION_CREDENTIALS=~/.config/gcloud/application_default_credentials.json' >> ~/.bashrc
source ~/.bashrc
```

**Option B: Use Windows path directly** (Simpler but less portable):
```bash
# Set environment variable to Windows path
echo 'export GOOGLE_APPLICATION_CREDENTIALS=/mnt/e/00_dev_1/01_secrets/gcp-credentials.json' >> ~/.bashrc
source ~/.bashrc
```

### Step 6: Test Authentication

```bash
# Test gcloud authentication (install gcloud SDK first if needed)
# OR test gcsfuse directly in next step
```

---

## Mounting GCS Buckets

### Manual Mount (Test First)

```bash
# Create mount point
mkdir -p ~/gcs-mount/fremont-1

# Mount bucket
gcsfuse --implicit-dirs fremont-1 ~/gcs-mount/fremont-1

# Verify mount
ls ~/gcs-mount/fremont-1

# Test write
echo "test" > ~/gcs-mount/fremont-1/test.txt

# Unmount
fusermount -u ~/gcs-mount/fremont-1
```

### Access from Windows

Once mounted in WSL, you can access from Windows via WSL network path:

**Windows Explorer**: `\\wsl$\Ubuntu-22.04\home\<username>\gcs-mount\fremont-1`

**PowerShell**:
```powershell
# Map network drive (run as Administrator)
$wslPath = "\\wsl$\Ubuntu-22.04\home\$env:USERNAME\gcs-mount\fremont-1"
New-PSDrive -Name "G" -PSProvider FileSystem -Root $wslPath -Persist

# Or use directly
cd "\\wsl$\Ubuntu-22.04\home\$env:USERNAME\gcs-mount\fremont-1"
```

### Automatic Mount on WSL Startup

Create a startup script:

```bash
# Create mount script
cat > ~/mount-gcs.sh << 'EOF'
#!/bin/bash

# Create mount point if it doesn't exist
mkdir -p ~/gcs-mount/fremont-1

# Check if already mounted
if mountpoint -q ~/gcs-mount/fremont-1; then
    echo "GCS bucket already mounted"
else
    # Mount bucket
    gcsfuse --implicit-dirs \
            --key-file ~/.config/gcloud/application_default_credentials.json \
            fremont-1 ~/gcs-mount/fremont-1
    
    if [ $? -eq 0 ]; then
        echo "Successfully mounted fremont-1 bucket"
    else
        echo "Failed to mount bucket"
        exit 1
    fi
fi
EOF

# Make executable
chmod +x ~/mount-gcs.sh

# Add to bashrc for automatic mounting
echo '~/mount-gcs.sh' >> ~/.bashrc
```

**Test the script**:
```bash
~/mount-gcs.sh
ls ~/gcs-mount/fremont-1
```

---

## Important gcsfuse Options

### `--implicit-dirs`
**Critical for flat namespace buckets**: Infers directories from object paths (e.g., `docs/file.pdf` creates virtual `docs/` directory)

Without this flag, you can only see explicitly created folders.

### `--dir-mode` and `--file-mode`
Set permissions for mounted files/directories:
```bash
gcsfuse --dir-mode 755 --file-mode 644 fremont-1 ~/gcs-mount/fremont-1
```

### `--uid` and `--gid`
Set ownership:
```bash
gcsfuse --uid $(id -u) --gid $(id -g) fremont-1 ~/gcs-mount/fremont-1
```

### `--debug_fuse` and `--debug_gcs`
Enable debug logging:
```bash
gcsfuse --debug_fuse --debug_gcs fremont-1 ~/gcs-mount/fremont-1
```

### Full Example with All Options

```bash
gcsfuse \
    --implicit-dirs \
    --dir-mode 755 \
    --file-mode 644 \
    --uid $(id -u) \
    --gid $(id -g) \
    --key-file ~/.config/gcloud/application_default_credentials.json \
    fremont-1 ~/gcs-mount/fremont-1
```

---

## Performance Considerations

### Caching (Recommended for Better Performance)

```bash
# Enable file caching (default: disabled)
gcsfuse \
    --implicit-dirs \
    --file-cache-max-size-mb 1000 \
    --stat-cache-ttl 60s \
    --type-cache-ttl 60s \
    fremont-1 ~/gcs-mount/fremont-1
```

**Cache options**:
- `--file-cache-max-size-mb`: Local file cache size (default: unlimited)
- `--stat-cache-ttl`: Time to cache file metadata (default: 1m)
- `--type-cache-ttl`: Time to cache object type info (default: 1m)

### Limitations to Be Aware Of

1. **Not POSIX-compliant**: Some file operations may behave differently
2. **Eventual consistency**: Changes may not be immediately visible
3. **No file locking**: Concurrent writes can corrupt files
4. **Latency**: Network operations are slower than local disk
5. **Costs**: All operations incur Cloud Storage API charges

---

## Troubleshooting

### Issue: "fusermount: fuse device not found"

**Solution**: Load FUSE kernel module
```bash
sudo modprobe fuse
```

### Issue: "Permission denied" when mounting

**Solution**: Add user to fuse group
```bash
sudo usermod -a -G fuse $USER
# Log out and back in
```

### Issue: "Transport endpoint is not connected"

**Solution**: Unmount and remount
```bash
fusermount -u ~/gcs-mount/fremont-1
~/mount-gcs.sh
```

### Issue: Empty directory after mount

**Possible causes**:
1. Wrong bucket name
2. No permissions to access bucket
3. Missing `--implicit-dirs` flag for flat namespace bucket

**Debug**:
```bash
# Test with debug logging
gcsfuse --debug_fuse --debug_gcs fremont-1 ~/gcs-mount/fremont-1

# Check logs
journalctl -xe | grep gcsfuse
```

### Issue: Slow performance

**Solutions**:
1. Enable caching (see Performance Considerations)
2. Use hierarchical namespace bucket instead of flat namespace
3. Reduce `--stat-cache-ttl` and `--type-cache-ttl` if stale data is acceptable

---

## Unmounting

### Graceful Unmount

```bash
fusermount -u ~/gcs-mount/fremont-1
```

### Force Unmount (if stuck)

```bash
sudo umount -f ~/gcs-mount/fremont-1
# Or
sudo fusermount -uz ~/gcs-mount/fremont-1
```

---

## Integration with Python Scripts

Once mounted, access GCS files as local files:

```python
# Instead of using GCS API:
# from google.cloud import storage
# client = storage.Client()
# bucket = client.bucket('fremont-1')
# blob = bucket.blob('docs/file.pdf')
# blob.download_to_filename('local.pdf')

# Use direct file operations:
import shutil

gcs_mount = "/home/username/gcs-mount/fremont-1"

# Read file
with open(f"{gcs_mount}/docs/file.pdf", 'rb') as f:
    data = f.read()

# Write file
with open(f"{gcs_mount}/docs/new-file.txt", 'w') as f:
    f.write("Hello GCS")

# Copy file
shutil.copy("local.pdf", f"{gcs_mount}/docs/uploaded.pdf")

# List directory
import os
files = os.listdir(f"{gcs_mount}/docs")
```

---

## Windows PowerShell Helper Script

Save this as `E:\00_dev_1\y_apps\x3_doc-processing\mount_gcs.ps1`:

```powershell
# Mount GCS bucket via WSL gcsfuse and map as Windows drive

param(
    [string]$DriveLetter = "G",
    [string]$BucketName = "fremont-1"
)

Write-Host "Mounting GCS bucket: $BucketName" -ForegroundColor Cyan

# Start WSL and mount bucket
wsl -d Ubuntu-22.04 -e bash -c "~/mount-gcs.sh"

if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] Bucket mounted in WSL" -ForegroundColor Green
    
    # Map Windows drive
    $wslPath = "\\wsl$\Ubuntu-22.04\home\$env:USERNAME\gcs-mount\$BucketName"
    
    Write-Host "Mapping Windows drive ${DriveLetter}: -> $wslPath" -ForegroundColor Cyan
    
    # Remove existing mapping if present
    if (Test-Path "${DriveLetter}:") {
        net use "${DriveLetter}:" /delete /y 2>$null
    }
    
    # Create new mapping
    net use "${DriveLetter}:" "$wslPath" /persistent:yes
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] Mapped drive ${DriveLetter}: successfully" -ForegroundColor Green
        Write-Host "[INFO] Access your bucket at: ${DriveLetter}:\" -ForegroundColor Green
    } else {
        Write-Host "[WARN] Could not map drive, but bucket is accessible at: $wslPath" -ForegroundColor Yellow
    }
} else {
    Write-Host "[FAIL] Failed to mount bucket in WSL" -ForegroundColor Red
    exit 1
}
```

**Usage**:
```powershell
# Mount fremont-1 bucket as G: drive
.\mount_gcs.ps1

# Mount different bucket as different drive
.\mount_gcs.ps1 -DriveLetter "H" -BucketName "other-bucket"
```

---

## Quick Reference

### Common Commands

```bash
# Mount bucket
gcsfuse --implicit-dirs fremont-1 ~/gcs-mount/fremont-1

# Unmount bucket
fusermount -u ~/gcs-mount/fremont-1

# Check if mounted
mountpoint ~/gcs-mount/fremont-1

# List mounted filesystems
mount | grep gcsfuse

# View gcsfuse version
gcsfuse --version
```

### File Paths

| Location | Path |
|----------|------|
| WSL mount point | `~/gcs-mount/fremont-1` |
| Windows via WSL | `\\wsl$\Ubuntu-22.04\home\<user>\gcs-mount\fremont-1` |
| Windows mapped drive | `G:\` (after mapping) |
| GCS bucket | `gs://fremont-1/` |

---

## References

- [Cloud Storage FUSE Overview](https://cloud.google.com/storage/docs/cloud-storage-fuse/overview)
- [Installation Guide](https://cloud.google.com/storage/docs/cloud-storage-fuse/install)
- [Mount Bucket Guide](https://cloud.google.com/storage/docs/cloud-storage-fuse/mount-bucket)
- [CLI Options](https://cloud.google.com/storage/docs/cloud-storage-fuse/cli-options)
- [GitHub Repository](https://github.com/GoogleCloudPlatform/gcsfuse)
- [Troubleshooting](https://github.com/GoogleCloudPlatform/gcsfuse/blob/master/docs/troubleshooting.md)

---

## Next Steps

1. Complete WSL2 installation if not already installed
2. Install gcsfuse in WSL following steps above
3. Test manual mount with your `fremont-1` bucket
4. Set up automatic mounting on WSL startup
5. Map Windows drive for easy access from Windows applications
6. Update doc-process-v31 scripts to use mounted filesystem paths
