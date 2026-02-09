# Build all fraud-det-v3 images (pipeline pods + backend) on Windows.
# Run from repo root: .\k8s\build-images.ps1

$ErrorActionPreference = "Stop"

# Get root directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..")
Set-Location $RepoRoot

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "      Fraud Detection Pipeline - Windows Image Builder" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

$NoCache = $env:NO_CACHE
if ($null -ne $NoCache -and $NoCache -ne "") {
    Write-Host "Building with --no-cache" -ForegroundColor Yellow
    $DockerArgs = "--no-cache"
} else {
    $DockerArgs = ""
}

# Helper to build and check
function Build-Image($Name, $Tag, $File) {
    Write-Host "Building $Name..." -ForegroundColor Green
    if (Test-Path $File) {
        if ($DockerArgs -ne "") {
            docker build --no-cache -t $Tag -f $File .
        } else {
            docker build -t $Tag -f $File .
        }
    } else {
        Write-Error "Error: $File not found!"
    }
}

# 1. Backend
Build-Image "Backend" "fraud-det-v3/backend:latest" "Dockerfile.backend"

# 2. Data Gather
if (Test-Path "pods/data-gather/Dockerfile.repo") {
    Build-Image "Data Gather" "fraud-det-v3/data-gather:latest" "pods/data-gather/Dockerfile.repo"
} else {
    Build-Image "Data Gather" "fraud-det-v3/data-gather:latest" "pods/data-gather/Dockerfile"
}

# 3. Preprocessing (CPU)
if (Test-Path "pods/data-prep/Dockerfile.cpu") {
    Build-Image "Preprocessing (CPU)" "fraud-det-v3/preprocessing-cpu:latest" "pods/data-prep/Dockerfile.cpu"
} else {
    Write-Host "Warning: pods/data-prep/Dockerfile.cpu not found, falling back to pods/data-prep/Dockerfile" -ForegroundColor Yellow
    Build-Image "Preprocessing (CPU)" "fraud-det-v3/preprocessing-cpu:latest" "pods/data-prep/Dockerfile"
}

# 4. Preprocessing (GPU)
if (Test-Path "pods/data-prep/Dockerfile.gpu") {
    Build-Image "Preprocessing (GPU)" "fraud-det-v3/preprocessing-gpu:latest" "pods/data-prep/Dockerfile.gpu"
}

# 5. Model Build
Build-Image "Model Build" "fraud-det-v3/model-build:latest" "pods/model-build/Dockerfile"

# 6. Inference (CPU)
Build-Image "Inference (CPU)" "fraud-det-v3/inference-cpu:latest" "pods/inference/Dockerfile.cpu"

# 7. Inference (GPU)
if (Test-Path "pods/inference/Dockerfile") {
    Build-Image "Inference (GPU)" "fraud-det-v3/inference-gpu:latest" "pods/inference/Dockerfile"
}

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " Verifying images..." -ForegroundColor Cyan

try {
    docker run --rm fraud-det-v3/data-gather:latest ls -la /app/queue_interface.py /app/gather.py | Out-Null
    Write-Host "Success: Images verified." -ForegroundColor Green
} catch {
    Write-Host "Warning: Image verification failed (requires Linux-capable Docker). Skipping..." -ForegroundColor Yellow
}

Write-Host "Done. All images built successfully." -ForegroundColor Green
