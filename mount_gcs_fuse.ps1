# GCS FUSE Mount Setup - Direct Cloud Read/Write
# After WSL reboot, run this to mount GCS bucket at E:\00_gcs

param(
    [string]$MountPoint = "E:\00_gcs\fremont-1",
    [string]$BucketName = "fremont-1",
    [string]$CredentialsPath = "E:\00_dev_1\01_secrets\gcp-credentials.json"
)

Write-Host "="*80
Write-Host "GCS FUSE Mount Setup - Direct Cloud Access"
Write-Host "="*80

# Check credentials
if (-not (Test-Path $CredentialsPath)) {
    Write-Host "[FAIL] Credentials not found: $CredentialsPath" -ForegroundColor Red
    exit 1
}

Write-Host "[OK] Found credentials" -ForegroundColor Green

# Check if WSL is ready
Write-Host "`n[CHECK] Verifying WSL status..." -ForegroundColor Cyan
$wslStatus = wsl --status 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "[FAIL] WSL requires system reboot" -ForegroundColor Red
    Write-Host "[ACTION] Please reboot your computer, then run this script again" -ForegroundColor Yellow
    exit 1
}

Write-Host "[OK] WSL is available" -ForegroundColor Green

# Check if gcsfuse is installed in WSL
Write-Host "`n[CHECK] Checking gcsfuse installation..." -ForegroundColor Cyan
$gcsfuseCheck = wsl -d Ubuntu-22.04 -e bash -c "which gcsfuse" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "[INFO] gcsfuse not installed, installing now..." -ForegroundColor Yellow
    
    # Install gcsfuse
    wsl -d Ubuntu-22.04 -e bash -c @"
sudo apt-get update && \
export GCSFUSE_REPO=gcsfuse-`lsb_release -c -s` && \
echo "deb https://packages.cloud.google.com/apt `$GCSFUSE_REPO main" | sudo tee /etc/apt/sources.list.d/gcsfuse.list && \
curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo apt-key add - && \
sudo apt-get update && \
sudo apt-get install -y fuse gcsfuse
"@
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] gcsfuse installed successfully" -ForegroundColor Green
    } else {
        Write-Host "[FAIL] gcsfuse installation failed" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "[OK] gcsfuse is installed" -ForegroundColor Green
}

# Copy credentials to WSL
Write-Host "`n[SETUP] Copying credentials to WSL..." -ForegroundColor Cyan
wsl -d Ubuntu-22.04 -e bash -c "mkdir -p ~/.config/gcloud"
wsl -d Ubuntu-22.04 -e bash -c "cp /mnt/e/00_dev_1/01_secrets/gcp-credentials.json ~/.config/gcloud/application_default_credentials.json"
Write-Host "[OK] Credentials copied" -ForegroundColor Green

# Create mount point in WSL
$wslMountPath = "~/gcs-mount/$BucketName"
Write-Host "`n[SETUP] Creating WSL mount point: $wslMountPath" -ForegroundColor Cyan
wsl -d Ubuntu-22.04 -e bash -c "mkdir -p $wslMountPath"

# Create mount script in WSL
Write-Host "[SETUP] Creating mount script..." -ForegroundColor Cyan
wsl -d Ubuntu-22.04 -e bash -c @"
cat > ~/mount-gcs.sh << 'MOUNT_SCRIPT'
#!/bin/bash
BUCKET="$BucketName"
MOUNT_DIR="$wslMountPath"

# Create mount point
mkdir -p `$MOUNT_DIR

# Check if already mounted
if mountpoint -q `$MOUNT_DIR; then
    echo "[INFO] Bucket already mounted"
    exit 0
fi

# Mount with gcsfuse (direct cloud read/write)
gcsfuse \
    --implicit-dirs \
    --file-mode 644 \
    --dir-mode 755 \
    --key-file ~/.config/gcloud/application_default_credentials.json \
    `$BUCKET `$MOUNT_DIR

if [ `$? -eq 0 ]; then
    echo "[OK] Successfully mounted gs://`$BUCKET/ at `$MOUNT_DIR"
    echo "[INFO] All read/write operations go directly to cloud"
else
    echo "[FAIL] Failed to mount bucket"
    exit 1
fi
MOUNT_SCRIPT
chmod +x ~/mount-gcs.sh
"@

Write-Host "[OK] Mount script created" -ForegroundColor Green

# Mount the bucket
Write-Host "`n[MOUNT] Mounting GCS bucket: $BucketName" -ForegroundColor Cyan
wsl -d Ubuntu-22.04 -e bash -c "~/mount-gcs.sh"

if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] Bucket mounted successfully" -ForegroundColor Green
    
    # Create Windows mount point directory
    New-Item -ItemType Directory -Path $MountPoint -Force | Out-Null
    
    # Map to Windows drive
    $wslUsername = wsl -d Ubuntu-22.04 -e bash -c "whoami"
    $wslNetworkPath = "\\wsl$\Ubuntu-22.04\home\$wslUsername\gcs-mount\$BucketName"
    
    Write-Host "`n[WINDOWS] Creating symbolic link..." -ForegroundColor Cyan
    Write-Host "[INFO] WSL Path: $wslNetworkPath" -ForegroundColor Cyan
    Write-Host "[INFO] Windows Path: $MountPoint" -ForegroundColor Cyan
    
    # Remove existing link if present
    if (Test-Path $MountPoint) {
        Remove-Item -Path $MountPoint -Force -Recurse 2>$null
    }
    
    # Create symbolic link (requires admin privileges)
    try {
        New-Item -ItemType SymbolicLink -Path $MountPoint -Target $wslNetworkPath -Force | Out-Null
        Write-Host "[OK] Symbolic link created" -ForegroundColor Green
    } catch {
        Write-Host "[WARN] Could not create symbolic link (requires admin)" -ForegroundColor Yellow
        Write-Host "[INFO] You can still access via: $wslNetworkPath" -ForegroundColor Cyan
    }
    
    # Set environment variable
    [Environment]::SetEnvironmentVariable("GCS_MOUNT_PATH", $MountPoint, "User")
    Write-Host "[OK] Environment variable set: GCS_MOUNT_PATH=$MountPoint" -ForegroundColor Green
    
    Write-Host "`n[SUCCESS] GCS bucket mounted!" -ForegroundColor Green
    Write-Host "`n[USAGE]" -ForegroundColor Yellow
    Write-Host "  Windows Path:  $MountPoint" -ForegroundColor White
    Write-Host "  WSL Path:      $wslMountPath" -ForegroundColor White
    Write-Host "  Network Path:  $wslNetworkPath" -ForegroundColor White
    Write-Host "  GCS Bucket:    gs://$BucketName/" -ForegroundColor White
    
    Write-Host "`n[IMPORTANT] All operations write directly to cloud!" -ForegroundColor Green
    Write-Host "  - Reading a file: Downloads from GCS on-demand" -ForegroundColor Cyan
    Write-Host "  - Writing a file: Uploads to GCS immediately" -ForegroundColor Cyan
    Write-Host "  - No local storage consumed (except cache)" -ForegroundColor Cyan
    
    Write-Host "`n[COMMANDS]" -ForegroundColor Yellow
    Write-Host "  Unmount: wsl -d Ubuntu-22.04 -e fusermount -u $wslMountPath" -ForegroundColor White
    Write-Host "  Remount: wsl -d Ubuntu-22.04 -e ~/mount-gcs.sh" -ForegroundColor White
    
} else {
    Write-Host "[FAIL] Failed to mount bucket" -ForegroundColor Red
    Write-Host "[DEBUG] Check WSL logs: wsl -d Ubuntu-22.04 -e dmesg | tail" -ForegroundColor Yellow
    exit 1
}
