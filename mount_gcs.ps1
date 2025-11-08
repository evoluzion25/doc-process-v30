# Mount GCS bucket via WSL gcsfuse and map as Windows drive

param(
    [string]$DriveLetter = "G",
    [string]$BucketName = "fremont-1"
)

Write-Host "="*80
Write-Host "GCS FUSE Mount - Windows Helper"
Write-Host "="*80

Write-Host "`nMounting GCS bucket: $BucketName" -ForegroundColor Cyan
Write-Host "Target drive: ${DriveLetter}:" -ForegroundColor Cyan

# Check if WSL is available
$wslCheck = wsl -l -v 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "[FAIL] WSL not installed or not configured" -ForegroundColor Red
    Write-Host "[INFO] Please install WSL2 and run installation steps from INSTALL_GCSFUSE.md" -ForegroundColor Yellow
    exit 1
}

Write-Host "[OK] WSL is available" -ForegroundColor Green

# Start WSL and mount bucket
Write-Host "`n[WSL] Executing mount script in WSL..." -ForegroundColor Cyan
wsl -d Ubuntu-22.04 -e bash -c "~/mount-gcs.sh"

if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] Bucket mounted in WSL" -ForegroundColor Green
    
    # Construct WSL path
    $wslUsername = wsl -d Ubuntu-22.04 -e whoami
    $wslPath = "\\wsl$\Ubuntu-22.04\home\$wslUsername\gcs-mount\$BucketName"
    
    Write-Host "`n[WINDOWS] Mapping Windows drive ${DriveLetter}: -> $wslPath" -ForegroundColor Cyan
    
    # Remove existing mapping if present
    if (Test-Path "${DriveLetter}:") {
        Write-Host "[INFO] Removing existing drive mapping..." -ForegroundColor Yellow
        net use "${DriveLetter}:" /delete /y 2>$null | Out-Null
    }
    
    # Create new mapping
    net use "${DriveLetter}:" "$wslPath" /persistent:yes 2>$null
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] Mapped drive ${DriveLetter}: successfully" -ForegroundColor Green
        Write-Host "`n[SUCCESS] GCS bucket mounted and accessible!" -ForegroundColor Green
        Write-Host "`n[USAGE]" -ForegroundColor Yellow
        Write-Host "  Windows Drive:  ${DriveLetter}:\" -ForegroundColor White
        Write-Host "  WSL Path:       ~/gcs-mount/$BucketName" -ForegroundColor White
        Write-Host "  Windows UNC:    $wslPath" -ForegroundColor White
        Write-Host "`n[COMMANDS]" -ForegroundColor Yellow
        Write-Host "  Unmount: wsl -d Ubuntu-22.04 -e fusermount -u ~/gcs-mount/$BucketName" -ForegroundColor White
        Write-Host "  Unmap drive: net use ${DriveLetter}: /delete" -ForegroundColor White
    } else {
        Write-Host "[WARN] Could not map drive automatically" -ForegroundColor Yellow
        Write-Host "[INFO] Bucket is still accessible at: $wslPath" -ForegroundColor Cyan
        Write-Host "[TIP] You can manually map the drive in File Explorer:" -ForegroundColor Yellow
        Write-Host "      1. Open File Explorer" -ForegroundColor White
        Write-Host "      2. Right-click 'This PC' -> 'Map network drive'" -ForegroundColor White
        Write-Host "      3. Choose drive letter: ${DriveLetter}:" -ForegroundColor White
        Write-Host "      4. Enter path: $wslPath" -ForegroundColor White
    }
} else {
    Write-Host "[FAIL] Failed to mount bucket in WSL" -ForegroundColor Red
    Write-Host "`n[TROUBLESHOOTING]" -ForegroundColor Yellow
    Write-Host "  1. Verify WSL Ubuntu-22.04 is installed: wsl -l -v" -ForegroundColor White
    Write-Host "  2. Verify gcsfuse is installed in WSL: wsl -d Ubuntu-22.04 -e gcsfuse --version" -ForegroundColor White
    Write-Host "  3. Check mount script exists: wsl -d Ubuntu-22.04 -e cat ~/mount-gcs.sh" -ForegroundColor White
    Write-Host "  4. Check credentials: wsl -d Ubuntu-22.04 -e ls ~/.config/gcloud/" -ForegroundColor White
    Write-Host "  5. See full installation guide: INSTALL_GCSFUSE.md" -ForegroundColor White
    exit 1
}

Write-Host "`n[INFO] Mount complete!" -ForegroundColor Green
