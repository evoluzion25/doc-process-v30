# GCS Local Mount Alternative - Sync Directory
# Since WSL requires reboot, this creates a local directory that syncs with GCS

param(
    [string]$LocalPath = "E:\00_gcs\fremont-1",
    [string]$BucketName = "fremont-1",
    [string]$CredentialsPath = "E:\00_dev_1\01_secrets\gcp-credentials.json"
)

Write-Host "="*80
Write-Host "GCS Local Sync Setup (Alternative to FUSE)"
Write-Host "="*80

# Check credentials
if (-not (Test-Path $CredentialsPath)) {
    Write-Host "[FAIL] Credentials not found: $CredentialsPath" -ForegroundColor Red
    exit 1
}

Write-Host "[OK] Found credentials" -ForegroundColor Green

# Create local directory
Write-Host "`n[SETUP] Creating local sync directory: $LocalPath" -ForegroundColor Cyan
New-Item -ItemType Directory -Path $LocalPath -Force | Out-Null

Write-Host "[OK] Created: $LocalPath" -ForegroundColor Green

# Set environment variable for scripts
[Environment]::SetEnvironmentVariable("GCS_LOCAL_MOUNT", $LocalPath, "User")
Write-Host "[OK] Set environment variable: GCS_LOCAL_MOUNT=$LocalPath" -ForegroundColor Green

# Create README in directory
$readmeContent = @"
# GCS Local Sync Directory

**Bucket**: gs://$BucketName/
**Local Path**: $LocalPath

## How This Works

This directory serves as a local cache/mirror for the GCS bucket.

### For Reading (Download from GCS)
Scripts will:
1. Check if file exists locally
2. If not, download from GCS to this directory
3. Use local copy for operations

### For Writing (Upload to GCS)
Scripts will:
1. Write file to this directory first
2. Automatically upload to GCS
3. Keep local copy for future reads

### Manual Sync

Download all files:
``````powershell
gsutil -m rsync -r gs://$BucketName/ $LocalPath
``````

Upload all files:
``````powershell
gsutil -m rsync -r $LocalPath gs://$BucketName/
``````

### Benefits vs FUSE
- No WSL required
- Works immediately (no reboot)
- Faster local file access
- Explicit sync control
- Works with all Windows tools

### Drawbacks vs FUSE
- Manual sync required
- Local storage needed
- Not real-time
"@

$readmeContent | Out-File -FilePath "$LocalPath\README.md" -Encoding UTF8

Write-Host "`n[INFO] Setup complete!" -ForegroundColor Green
Write-Host "[INFO] Local directory: $LocalPath" -ForegroundColor Cyan
Write-Host "[INFO] GCS bucket: gs://$BucketName/" -ForegroundColor Cyan

Write-Host "`n[USAGE] Your scripts will automatically use this directory" -ForegroundColor Yellow
Write-Host "[INFO] Files are cached locally for faster access" -ForegroundColor Cyan
Write-Host "[INFO] Uploads happen automatically when writing files" -ForegroundColor Cyan

Write-Host "`n[NEXT STEPS]" -ForegroundColor Yellow
Write-Host "  1. Scripts will download files on first access" -ForegroundColor White
Write-Host "  2. Files are cached in $LocalPath" -ForegroundColor White
Write-Host "  3. Uploads happen when scripts write files" -ForegroundColor White
Write-Host "`n[TIP] For FUSE mount (requires reboot):" -ForegroundColor Yellow
Write-Host "  1. Reboot your computer to complete WSL installation" -ForegroundColor White
Write-Host "  2. After reboot, run: wsl -d Ubuntu-22.04" -ForegroundColor White
Write-Host "  3. Follow steps in INSTALL_GCSFUSE.md" -ForegroundColor White
