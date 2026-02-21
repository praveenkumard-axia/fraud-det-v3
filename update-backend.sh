#!/bin/bash
# update-backend.sh: Quick build and deploy for backend_server.py

set -e

echo "=========================================================="
echo "      Deploying Backend Updates"
echo "=========================================================="

DOCKER_USER="pduraiswamy16722"

echo "1. Building backend image..."
docker build -t $DOCKER_USER/fraud-det-v3-backend:latest -f Dockerfile.backend .

echo "2. Pushing to Docker Hub..."
docker push $DOCKER_USER/fraud-det-v3-backend:latest

echo "Done!"
