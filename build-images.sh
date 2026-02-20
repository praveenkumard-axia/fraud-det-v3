#!/bin/bash
# build-images.sh: Automate building all fraud pipeline images

set -e

echo "=========================================================="
echo "      Fraud Detection Pipeline - Image Builder"
echo "=========================================================="

# Tag and Push to Docker Hub
DOCKER_USER="pduraiswamy16722"


docker build -t $DOCKER_USER/fraud-det-v3-backend:latest -f Dockerfile.backend .
docker push $DOCKER_USER/fraud-det-v3-backend:latest

docker build -t $DOCKER_USER/fraud-det-v3-data-gather:latest -f pods/data-gather/Dockerfile .
docker push $DOCKER_USER/fraud-det-v3-data-gather:latest

docker build -t $DOCKER_USER/fraud-det-v3-data-prep:cpu -f pods/data-prep/Dockerfile.cpu .
docker push $DOCKER_USER/fraud-det-v3-data-prep:cpu

docker build -t $DOCKER_USER/fraud-det-v3-inference:cpu -f pods/inference/Dockerfile.cpu .
docker push $DOCKER_USER/fraud-det-v3-inference:cpu

docker build -t $DOCKER_USER/fraud-det-v3-data-prep:gpu -f pods/data-prep/Dockerfile.gpu .
docker push $DOCKER_USER/fraud-det-v3-data-prep:gpu

docker build -t $DOCKER_USER/fraud-det-v3-model-build:gpu -f pods/model-build/Dockerfile .
docker push $DOCKER_USER/fraud-det-v3-model-build:gpu

docker build -t $DOCKER_USER/fraud-det-v3-inference:latest -f pods/inference/Dockerfile .
docker push $DOCKER_USER/fraud-det-v3-inference:latest