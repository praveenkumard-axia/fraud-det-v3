#!/usr/bin/env bash
# Build all fraud-pipeline images (pipeline pods + backend).
# Run from repo root: ./k8s/build-images.sh

set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "=========================================================="
echo "      Fraud Detection Pipeline - Image Builder"
echo "=========================================================="

NO_CACHE="${NO_CACHE:-}"
[ -n "$NO_CACHE" ] && echo "Building with --no-cache"

# 1. Backend
echo "Building Backend..."
if [ -f "Dockerfile.backend" ]; then
    docker build $NO_CACHE -t fraud-pipeline/backend:latest -f Dockerfile.backend .
else
    echo "Error: Dockerfile.backend not found!"; exit 1
fi

# 2. Data Gather
echo "Building Data Gather (Generation)..."
if [ -f "pods/data-gather/Dockerfile.repo" ]; then
    docker build $NO_CACHE -t fraud-pipeline/data-gather:latest -f pods/data-gather/Dockerfile.repo .
elif [ -f "pods/data-gather/Dockerfile" ]; then
    docker build $NO_CACHE -t fraud-pipeline/data-gather:latest -f pods/data-gather/Dockerfile .
else
    echo "Error: Data Gather Dockerfile not found!"; exit 1
fi

# 3. Preprocessing (CPU)
echo "Building Preprocessing (CPU)..."
if [ -f "pods/data-prep/Dockerfile.cpu" ]; then
    docker build $NO_CACHE -t fraud-pipeline/preprocessing-cpu:latest -f pods/data-prep/Dockerfile.cpu .
else
    echo "Warning: pods/data-prep/Dockerfile.cpu not found, falling back to pods/data-prep/Dockerfile"
    docker build $NO_CACHE -t fraud-pipeline/preprocessing-cpu:latest -f pods/data-prep/Dockerfile .
fi

# 4. Preprocessing (GPU)
echo "Building Preprocessing (GPU)..."
if [ -f "pods/data-prep/Dockerfile.gpu" ]; then
    docker build $NO_CACHE -t fraud-pipeline/preprocessing-gpu:latest -f pods/data-prep/Dockerfile.gpu .
else
    echo "Warning: pods/data-prep/Dockerfile.gpu not found, skipping."
fi

# 5. Model Build (GPU/CPU)
echo "Building Model Build..."
if [ -f "pods/model-build/Dockerfile" ]; then
    docker build $NO_CACHE -t fraud-pipeline/model-build:latest -f pods/model-build/Dockerfile .
else
    echo "Error: pods/model-build/Dockerfile not found!"; exit 1
fi

# 6. Inference (CPU)
echo "Building Inference (CPU)..."
if [ -f "pods/inference/Dockerfile.cpu" ]; then
    docker build $NO_CACHE -t fraud-pipeline/inference-cpu:latest -f pods/inference/Dockerfile.cpu .
else
    echo "Error: pods/inference/Dockerfile.cpu not found!"; exit 1
fi

# 7. Inference (GPU)
echo "Building Inference (GPU - Triton Server)..."
if [ -f "pods/inference/Dockerfile" ]; then
    docker build $NO_CACHE -t fraud-pipeline/inference-gpu:latest -f pods/inference/Dockerfile .
else
    echo "Warning: pods/inference/Dockerfile not found, skipping."
fi

echo "=========================================================="
echo " Verifying key files in images..."
docker run --rm fraud-pipeline/data-gather:latest ls -la /app/queue_interface.py /app/config_contract.py /app/gather.py >/dev/null 2>&1 || { echo "ERROR: data-gather image verification failed"; exit 1; }
docker run --rm fraud-pipeline/preprocessing-cpu:latest ls -la /app/queue_interface.py >/dev/null 2>&1 || true
docker run --rm fraud-pipeline/backend:latest ls -la /app/backend_server.py /app/k8s_scale.py >/dev/null 2>&1 || true

echo "Done. All images built successfully."
