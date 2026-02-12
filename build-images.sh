#!/bin/bash
# build-images.sh: Automate building all fraud pipeline images

set -e

echo "=========================================================="
echo "      Fraud Detection Pipeline - Image Builder"
echo "=========================================================="

# Tag and Push to Docker Hub
USER="pduraiswamy16722"

# 1. Backend
echo "Building and Pushing Backend..."
docker build -t $USER/fraud-det-v3-dockerfile.backend:latest -f Dockerfile.backend .
docker push $USER/fraud-det-v3-dockerfile.backend:latest

# 2. Data Gather
echo "Building and Pushing Data Gather..."
docker build -t $USER/fraud-det-v3-data-gather:latest -f pods/data-gather/Dockerfile .
docker push $USER/fraud-det-v3-data-gather:latest

# 3. Preprocessing (CPU/GPU unified in data-prep)
echo "Building and Pushing Data Prep..."
docker build -t $USER/fraud-det-v3-data-prep:latest -f pods/data-prep/Dockerfile .
docker push $USER/fraud-det-v3-data-prep:latest

# 4. Model Build
echo "Building and Pushing Model Build..."
docker build -t $USER/fraud-det-v3-model-build:latest -f pods/model-build/Dockerfile .
docker push $USER/fraud-det-v3-model-build:latest

# 5. Inference
echo "Building and Pushing Inference..."
docker build -t $USER/fraud-det-v3-inference:latest -f pods/inference/Dockerfile .
docker push $USER/fraud-det-v3-inference:latest

echo "=========================================================="
echo "               Build & Push Complete!"
echo "=========================================================="
