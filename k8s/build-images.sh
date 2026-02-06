#!/usr/bin/env bash
# Build all fraud-pipeline images (pipeline pods + backend).
# Run from repo root: ./k8s/build-images.sh

set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "Building fraud-pipeline images (tag: latest)..."
NO_CACHE="${NO_CACHE:-}"
[ -n "$NO_CACHE" ] && echo "Building with --no-cache"

# Pipeline pods
docker build $NO_CACHE -t fraud-pipeline/data-gather:latest -f pods/data-gather/Dockerfile.repo .
docker build $NO_CACHE -t fraud-pipeline/preprocessing-cpu:latest -f pods/data-prep/Dockerfile.cpu .
docker build $NO_CACHE -t fraud-pipeline/preprocessing-gpu:latest -f pods/data-prep/Dockerfile.gpu .
docker build $NO_CACHE -t fraud-pipeline/inference-cpu:latest -f pods/inference/Dockerfile.cpu .
docker build $NO_CACHE -t fraud-pipeline/inference-gpu:latest -f pods/inference/Dockerfile .
docker build $NO_CACHE -t fraud-pipeline/model-build:latest -f pods/model-build/Dockerfile .

# Backend (dashboard API)
docker build $NO_CACHE -t fraud-pipeline/backend:latest -f Dockerfile.backend .

echo "Verifying images..."
docker run --rm fraud-pipeline/data-gather:latest ls -la /app/queue_interface.py /app/config_contract.py /app/gather.py 2>/dev/null || { echo "ERROR: data-gather image missing queue_interface.py"; exit 1; }
docker run --rm fraud-pipeline/preprocessing-cpu:latest ls -la /app/queue_interface.py 2>/dev/null || true
docker run --rm fraud-pipeline/backend:latest ls -la /app/backend_server.py /app/k8s_scale.py 2>/dev/null || true

echo ""
echo "Done. Next steps:"
echo "  1. Kind:     kind load docker-image fraud-pipeline/data-gather:latest fraud-pipeline/preprocessing-cpu:latest fraud-pipeline/preprocessing-gpu:latest fraud-pipeline/inference-cpu:latest fraud-pipeline/inference-gpu:latest fraud-pipeline/model-build:latest fraud-pipeline/backend:latest"
echo "  2. Minikube: eval \$(minikube docker-env) && ./k8s/build-images.sh"
echo "  3. Deploy:   kubectl apply -f k8s/fraud-pipeline-all.yaml"
echo "  4. Restart:  kubectl rollout restart deployment -n fraud-pipeline --all"
echo "  5. Watch:    kubectl get pods -n fraud-pipeline -w"
echo ""
echo "  Backend (dashboard) runs in-cluster. Port-forward to access:"
echo "    kubectl port-forward -n fraud-pipeline svc/backend 8000:8000"
