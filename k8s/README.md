# Kubernetes manifests – fraud-pipeline

Namespace: **fraud-pipeline**

## Deployments (CPU + GPU)

| File                                | Deployment name   | Replicas (default) | Resources |
| ----------------------------------- | ----------------- | ------------------ | --------- |
| `namespace.yaml`                    | —                 | —                  | —         |
| `shared-storage-pvc.yaml`           | PVC: fraud-pipeline-flashblade | — | 50Gi RWX  |
| `data-gather-deployment.yaml`       | data-gather       | 1                  | CPU       |
| `preprocessing-cpu-deployment.yaml` | preprocessing-cpu | 1                  | CPU       |
| `preprocessing-gpu-deployment.yaml` | preprocessing-gpu | 0                  | GPU       |
| `model-build-deployment.yaml`       | model-build       | 1                  | GPU       |
| `inference-cpu-deployment.yaml`     | inference-cpu     | 2                  | CPU       |
| `inference-gpu-deployment.yaml`     | inference-gpu     | 0                  | GPU       |

---

## 🚀 Quick Start Guide

### 1. Build and Deploy (First Time Setup)

```bash
# Step 1: Build Docker images
chmod +x k8s/build-images.sh
./k8s/build-images.sh

# Step 2: Load images into cluster (if using Kind)
kind load docker-image fraud-pipeline/data-gather:latest fraud-pipeline/preprocessing-cpu:latest fraud-pipeline/inference-cpu:latest

# Step 3: Create namespace, shared volume (PVC), and deploy pods
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/shared-storage-pvc.yaml   # All pods mount this at /mnt/flashblade (no Redis)
kubectl apply -f k8s/data-gather-deployment.yaml
kubectl apply -f k8s/preprocessing-cpu-deployment.yaml
kubectl apply -f k8s/inference-cpu-deployment.yaml

# Or apply all at once:
kubectl apply -f k8s/

# Step 4: Wait for pods to be ready
kubectl get pods -n fraud-pipeline -w
```

### 2. Start the Pipeline

```bash
# Start all deployments (if they were stopped)
kubectl scale deployment -n fraud-pipeline data-gather --replicas=1
kubectl scale deployment -n fraud-pipeline preprocessing-cpu --replicas=1
kubectl scale deployment -n fraud-pipeline inference-cpu --replicas=2

# Check status
kubectl get pods -n fraud-pipeline
```

### 3. Stop the Pipeline

```bash
# Stop all pods (scale to 0)
kubectl scale deployment -n fraud-pipeline data-gather --replicas=0
kubectl scale deployment -n fraud-pipeline preprocessing-cpu --replicas=0
kubectl scale deployment -n fraud-pipeline inference-cpu --replicas=0

# Verify all pods are terminated
kubectl get pods -n fraud-pipeline
```

### 4. Restart the Pipeline

```bash
# Restart deployments (useful after updating images)
kubectl rollout restart deployment -n fraud-pipeline data-gather preprocessing-cpu inference-cpu

# Monitor restart progress
kubectl get pods -n fraud-pipeline -w
```

### 5. Delete Everything

```bash
# Delete all deployments
kubectl delete deployment -n fraud-pipeline data-gather preprocessing-cpu inference-cpu

# Or delete the entire namespace (removes everything)
kubectl delete namespace fraud-pipeline
```

---

## 📊 Monitoring & Troubleshooting

### Pods stuck in Pending (PVC not bound)

If **all pods** show `Pending` and `kubectl get pvc -n fraud-pipeline` shows the PVC in **Pending**:

- The PVC was likely created with `ReadWriteMany` on a cluster whose StorageClass only supports `ReadWriteOnce`. The repo PVC is now `ReadWriteOnce`. Fix:

```bash
# Delete the stuck PVC and re-apply (PVC is now ReadWriteOnce)
kubectl delete pvc -n fraud-pipeline fraud-pipeline-flashblade
kubectl apply -f k8s/shared-storage-pvc.yaml

# Restart deployments so pods re-create and bind the new PVC
kubectl rollout restart deployment -n fraud-pipeline data-gather preprocessing-cpu inference-cpu
# If you use model-build / GPU deployments, restart those too
kubectl rollout restart deployment -n fraud-pipeline model-build preprocessing-gpu inference-gpu 2>/dev/null || true

kubectl get pods -n fraud-pipeline -w
```

After the PVC binds, pods should change to `ContainerCreating` then `Running`.

### CrashLoopBackOff / `ModuleNotFoundError: queue_interface`

If **data-gather** or **preprocessing-cpu** show `CrashLoopBackOff` and logs show `ModuleNotFoundError: No module named 'queue_interface'`, the images in the cluster were likely built without the repo-root context (so `queue_interface.py` and `config_contract.py` are not in the image). Fix:

```bash
# From repo root: rebuild with no cache, then restart
NO_CACHE=--no-cache ./k8s/build-images.sh

# If using Kind, reload images
kind load docker-image fraud-pipeline/data-gather:latest fraud-pipeline/preprocessing-cpu:latest fraud-pipeline/inference-cpu:latest

# Force new pods to use the new image
kubectl rollout restart deployment -n fraud-pipeline data-gather preprocessing-cpu inference-cpu
kubectl get pods -n fraud-pipeline -w
```

### Enable Metrics API (for `kubectl top` and dashboard CPU/memory)

If you see **`error: Metrics API not available`** when running `kubectl top pods`, install the metrics-server so the dashboard can show real pod CPU/memory:

- **Docker Desktop**: Metrics server is often available as an add-on; check Kubernetes settings or install manually.
- **Kind**: `kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml` (you may need to add `--kubelet-insecure-tls` to the metrics-server deployment for Kind).
- **Minikube**: `minikube addons enable metrics-server`.
- **Other clusters**: Deploy [metrics-server](https://github.com/kubernetes-sigs/metrics-server) per your provider’s docs.

After it’s running, `kubectl top pods -n fraud-pipeline` should work and the dashboard WebSocket payload will include non-zero `util_millicores` when pods are under load.

### Check Pod Status

```bash
# View all pods
kubectl get pods -n fraud-pipeline

# Watch pods in real-time
kubectl get pods -n fraud-pipeline -w

# Get detailed pod information
kubectl describe pod -n fraud-pipeline <pod-name>
```

### View Logs

```bash
# View logs from a specific deployment
kubectl logs -n fraud-pipeline deployment/data-gather --tail=50
kubectl logs -n fraud-pipeline deployment/preprocessing-cpu --tail=50
kubectl logs -n fraud-pipeline deployment/preprocessing-gpu --tail=50
kubectl logs -n fraud-pipeline deployment/inference-cpu --tail=50
kubectl logs -n fraud-pipeline deployment/inference-gpu --tail=50
kubectl logs -n fraud-pipeline deployment/model-build --tail=50


# Follow logs in real-time
kubectl logs -n fraud-pipeline deployment/data-gather -f

# View logs from all pods with a specific label
kubectl logs -n fraud-pipeline -l app=data-gather --tail=20
```

### Scale Deployments

```bash
# Scale up preprocessing for heavy load
kubectl scale deployment -n fraud-pipeline preprocessing-cpu --replicas=3

# Scale up inference
kubectl scale deployment -n fraud-pipeline inference-cpu --replicas=5

# Scale down
kubectl scale deployment -n fraud-pipeline preprocessing-cpu --replicas=1
kubectl scale deployment -n fraud-pipeline inference-cpu --replicas=2
```

---

## 🔧 Apply (CPU-only)

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/shared-storage-pvc.yaml
kubectl apply -f k8s/data-gather-deployment.yaml
kubectl apply -f k8s/preprocessing-cpu-deployment.yaml
kubectl apply -f k8s/inference-cpu-deployment.yaml
```

Or apply the whole directory:

```bash
kubectl apply -f k8s/
```

**Note:** The PVC uses `ReadWriteOnce` so it works with the default StorageClass (e.g. local-path) on Kind/Minikube/Docker Desktop. All pods run on the same node and share the volume. For multi-node with shared storage, use a StorageClass that supports `ReadWriteMany` and change the PVC accordingly.

If you previously applied GPU deployments and want to remove them (e.g. to clear Pending/ImagePullBackOff):

```bash
kubectl delete deployment -n fraud-pipeline model-build preprocessing-gpu inference-gpu --ignore-not-found
```

## Storage: shared volume at /mnt/flashblade (no Redis)

All pods share one volume mounted at `/mnt/flashblade` via the PVC `fraud-pipeline-flashblade`. Communication between pods is **file-based only** (no Redis):

- **data-gather** writes to `queue/raw-transactions/pending`
- **preprocessing** reads raw, writes to `queue/features-ready/pending`
- **inference** reads features, writes to `queue/inference-results/...`
- **model-build** uses `queue/training-queue/...` and `models/`

Each stage reads and writes in different subdirectories under `/mnt/flashblade`. Use FlashBlade, NFS, or any RWX-capable storage for the PVC.

## Fix ImagePullBackOff (local cluster)

Deployments use `imagePullPolicy: Never`, so the cluster will **not** pull from a registry; images must exist on the node.

**1. Build images** (from repo root):

```bash
chmod +x k8s/build-images.sh
./k8s/build-images.sh
```

**2. Load into cluster**

- **Kind:**  
  `kind load docker-image fraud-pipeline/data-gather:latest fraud-pipeline/preprocessing-cpu:latest fraud-pipeline/inference-cpu:latest`

- **Minikube:** run `eval $(minikube docker-env)`, then run `./k8s/build-images.sh` again so images are built in minikube’s Docker.

- **Docker Desktop Kubernetes:** uses the host Docker daemon; after building with `./k8s/build-images.sh`, no load step is needed.

**3. Restart deployments** so they pick up the images:

```bash
kubectl rollout restart deployment -n fraud-pipeline data-gather preprocessing-cpu inference-cpu
```

**Using a real registry:** push the images to your registry, set `image` in the YAML to your image URL, and set `imagePullPolicy: IfNotPresent` (or remove it).

## GPU deployments (disabled)

`k8s/disabled/` contains preprocessing-gpu, model-build, and inference-gpu. They are **not** applied with the commands above. To use them later, move the YAML files from `k8s/disabled/` into `k8s/` and ensure GPU nodes have the NVIDIA device plugin (`nvidia.com/gpu`).
