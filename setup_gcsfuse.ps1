# Setup gcsfuse for Windows - Mount GCS buckets as local drives
# Requirements: Docker Desktop for Windows with WSL2 backend

param(
    [Parameter(Mandatory=$false)]
    [string]$BucketName = "fremont-1",
    
    [Parameter(Mandatory=$false)]
    [string]$MountPoint = "G:",
    
    [Parameter(Mandatory=$false)]
    [string]$CredentialsPath = "E:\00_dev_1\01_secrets\gcp-credentials.json"
)

Write-Host "="*80
Write-Host "GCS FUSE Setup for Windows"
Write-Host "="*80

# Check if credentials exist
if (-not (Test-Path $CredentialsPath)) {
    Write-Host "[FAIL] Credentials not found: $CredentialsPath" -ForegroundColor Red
    exit 1
}

Write-Host "[OK] Found credentials: $CredentialsPath" -ForegroundColor Green

# Check if Docker is installed and running
$dockerRunning = docker ps 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[FAIL] Docker Desktop is not running or not installed" -ForegroundColor Red
    Write-Host "[INFO] Please install Docker Desktop for Windows with WSL2 backend" -ForegroundColor Yellow
    Write-Host "[INFO] Download from: https://www.docker.com/products/docker-desktop" -ForegroundColor Yellow
    exit 1
}

Write-Host "[OK] Docker Desktop is running" -ForegroundColor Green

# Check if WSL2 is available
$wslVersion = wsl --status 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[WARN] WSL2 may not be properly configured" -ForegroundColor Yellow
}

# Create mount directory if it doesn't exist
$mountDir = "${MountPoint}\"
if (-not (Test-Path $mountDir)) {
    Write-Host "[INFO] Creating mount point: $mountDir" -ForegroundColor Cyan
    New-Item -ItemType Directory -Path $mountDir -Force | Out-Null
}

# Convert Windows path to WSL path for credentials
$wslCredPath = $CredentialsPath -replace "\\", "/" -replace "^([A-Z]):", { "/mnt/$($_.Groups[1].Value.ToLower())" }
Write-Host "[INFO] WSL Credentials Path: $wslCredPath" -ForegroundColor Cyan

# Convert mount point to WSL path
$wslMountPath = $mountDir -replace "\\", "/" -replace "^([A-Z]):", { "/mnt/$($_.Groups[1].Value.ToLower())" }
Write-Host "[INFO] WSL Mount Path: $wslMountPath" -ForegroundColor Cyan

Write-Host "`n[INFO] Mounting GCS bucket: $BucketName" -ForegroundColor Cyan
Write-Host "[INFO] Mount point: $mountDir" -ForegroundColor Cyan

# Check if container already exists
$containerName = "gcsfuse-$BucketName"
$existingContainer = docker ps -a --filter "name=^${containerName}$" --format "{{.Names}}" 2>$null

if ($existingContainer) {
    Write-Host "[INFO] Removing existing container: $containerName" -ForegroundColor Yellow
    docker rm -f $containerName 2>$null | Out-Null
}

# Run gcsfuse in Docker container with persistent mount
# Using volume mount to share between WSL and Windows
Write-Host "`n[DOCKER] Starting gcsfuse container..." -ForegroundColor Cyan

docker run -d `
    --name $containerName `
    --privileged `
    --device /dev/fuse `
    --cap-add SYS_ADMIN `
    -v "${wslMountPath}:/mnt/gcs" `
    -v "${wslCredPath}:/credentials/key.json:ro" `
    -e GOOGLE_APPLICATION_CREDENTIALS=/credentials/key.json `
    gcr.io/cloud-builders/gcsfuse `
    sh -c "gcsfuse --foreground --implicit-dirs --key-file /credentials/key.json $BucketName /mnt/gcs"

if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] gcsfuse container started successfully" -ForegroundColor Green
    Write-Host "`n[SUCCESS] GCS bucket mounted at: $mountDir" -ForegroundColor Green
    Write-Host "[INFO] Container name: $containerName" -ForegroundColor Cyan
    Write-Host "`n[USAGE] Access your bucket at: $mountDir" -ForegroundColor Green
    Write-Host "`n[COMMANDS]" -ForegroundColor Yellow
    Write-Host "  Stop mount:  docker stop $containerName" -ForegroundColor White
    Write-Host "  Start mount: docker start $containerName" -ForegroundColor White
    Write-Host "  Remove mount: docker rm -f $containerName" -ForegroundColor White
    Write-Host "  View logs:   docker logs $containerName" -ForegroundColor White
} else {
    Write-Host "[FAIL] Failed to start gcsfuse container" -ForegroundColor Red
    Write-Host "[DEBUG] Checking Docker logs..." -ForegroundColor Yellow
    docker logs $containerName
    exit 1
}

# Wait a moment for mount to initialize
Start-Sleep -Seconds 3

# Verify mount is working
Write-Host "`n[VERIFY] Testing mount..." -ForegroundColor Cyan
$testResult = docker exec $containerName ls -la /mnt/gcs 2>&1

if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] Mount verified - bucket contents accessible" -ForegroundColor Green
} else {
    Write-Host "[WARN] Could not verify mount immediately" -ForegroundColor Yellow
    Write-Host "[INFO] Container may still be initializing" -ForegroundColor Cyan
}

Write-Host "`n[INFO] Setup complete!" -ForegroundColor Green
Write-Host "[INFO] Your GCS bucket is now available at: $mountDir" -ForegroundColor Green
Write-Host "[INFO] Changes to local files will sync to GCS automatically" -ForegroundColor Green
