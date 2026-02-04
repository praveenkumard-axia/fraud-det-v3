#!/usr/bin/env bash
# Build CPU pod images for fraud-pipeline (fixes ImagePullBackOff when using local cluster).
# Run from repo root: ./k8s/build-images.sh

set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "Building fraud-pipeline images (tag: latest)..."

# data-gather: build from repo root so queue_interface + config_contract are in the image
docker build -t fraud-pipeline/data-gather:latest -f pods/data-gather/Dockerfile.repo .

# preprocessing-cpu: CPU polars image from repo root so queue_interface + config_contract are in the image
docker build -t fraud-pipeline/preprocessing-cpu:latest -f pods/data-prep/Dockerfile.cpu .

# inference-cpu: CPU-only image (python-slim + XGBoost), no Triton/GPU. Build from repo root.
docker build -t fraud-pipeline/inference-cpu:latest -f pods/inference/Dockerfile.cpu .

# inference-gpu: GPU/Triton image. Context must be pods/inference/ so COPY config/ finds pods/inference/config/
# docker build -t fraud-pipeline/inference-gpu:latest -f pods/inference/Dockerfile pods/inference/

echo "Verifying images contain queue_interface.py..."
docker run --rm fraud-pipeline/data-gather:latest ls -la /app/queue_interface.py /app/config_contract.py /app/gather.py 2>/dev/null || true
docker run --rm fraud-pipeline/preprocessing-cpu:latest ls -la /app/queue_interface.py /app/config_contract.py /app/prepare.py 2>/dev/null || true

echo ""
echo "Done. To use in cluster:"
echo "  1. Kind:     kind load docker-image fraud-pipeline/data-gather:latest fraud-pipeline/preprocessing-cpu:latest fraud-pipeline/inference-cpu:latest"
echo "  2. Minikube: eval \$(minikube docker-env) then re-run this script"
echo "  3. Force new pods: kubectl rollout restart deployment -n fraud-pipeline data-gather preprocessing-cpu inference-cpu"
echo "  4. Wait:     kubectl get pods -n fraud-pipeline -w"
