#!/bin/bash
# build-images.sh: Automate building all fraud pipeline images

set -e

echo "=========================================================="
echo "      Fraud Detection Pipeline - Image Builder"
echo "=========================================================="

# 1. Backend
echo "Building Backend..."
docker build -t fraud-pipeline/backend:latest -f Dockerfile.backend .

# 2. Data Gather
echo "Building Data Gather (Generation)..."
docker build -t fraud-pipeline/data-gather:latest -f pods/data-gather/Dockerfile .

# 3. Preprocessing (CPU)
echo "Building Preprocessing (CPU)..."
docker build -t fraud-pipeline/preprocessing-cpu:latest -f pods/data-prep/Dockerfile .

# 4. Preprocessing (GPU)
echo "Building Preprocessing (GPU)..."
# Assuming Dockerfile.gpu exists or using build-args
if [ -f "pods/data-prep/Dockerfile.gpu" ]; then
    docker build -t fraud-pipeline/preprocessing-gpu:latest -f pods/data-prep/Dockerfile.gpu .
else
    echo "Warning: pods/data-prep/Dockerfile.gpu not found, skipping."
fi

# 5. Model Build (GPU/CPU)
echo "Building Model Build..."
docker build -t fraud-pipeline/model-build:latest -f pods/model-build/Dockerfile .

# 6. Inference (CPU)
echo "Building Inference (CPU)..."
docker build -t fraud-pipeline/inference-cpu:latest -f pods/inference/Dockerfile.cpu .

# 7. Inference (GPU)
echo "Building Inference (GPU)..."
docker build -t fraud-pipeline/inference-gpu:latest -f pods/inference/Dockerfile .

echo "=========================================================="
echo "                     Build Complete!"
echo "=========================================================="
