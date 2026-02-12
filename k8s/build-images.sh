#!/usr/bin/env bash
# Build all fraud-det-v3 images (pipeline pods + backend).
# Run from repo root: ./k8s/build-images.sh

set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "=========================================================="
echo "      Fraud Detection Pipeline - Image Builder"
echo "=========================================================="

NO_CACHE="${NO_CACHE:-}"
[ -n "$NO_CACHE" ] && echo "Building with --no-cache"

# Tag and Push to Docker Hub
USER="apandit07650"

# 1. Backend
echo "Building Backend..."
docker build $NO_CACHE -t $USER/fraud-det-v3-dockerfile.backend:latest -f Dockerfile.backend .
docker push $USER/fraud-det-v3-dockerfile.backend:latest

# 2. Data Gather
echo "Building Data Gather (Generation)..."
docker build $NO_CACHE -t $USER/fraud-det-v3-data-gather:latest -f pods/data-gather/Dockerfile .
docker push $USER/fraud-det-v3-data-gather:latest

# 3. Preprocessing (Unified)
echo "Building Preprocessing..."
docker build $NO_CACHE -t $USER/fraud-det-v3-data-prep:latest -f pods/data-prep/Dockerfile .
docker push $USER/fraud-det-v3-data-prep:latest

# 4. Model Build
echo "Building Model Build..."
docker build $NO_CACHE -t $USER/fraud-det-v3-model-build:latest -f pods/model-build/Dockerfile .
docker push $USER/fraud-det-v3-model-build:latest

# 5. Inference
echo "Building Inference..."
docker build $NO_CACHE -t $USER/fraud-det-v3-inference:latest -f pods/inference/Dockerfile .
docker push $USER/fraud-det-v3-inference:latest

echo "=========================================================="
echo " Verifying key files in images..."
docker run --rm $USER/fraud-det-v3-data-gather:latest ls -la /app/queue_interface.py /app/config_contract.py /app/gather.py >/dev/null 2>&1 || { echo "ERROR: data-gather image verification failed"; exit 1; }

echo "Done. All images built and pushed successfully."
