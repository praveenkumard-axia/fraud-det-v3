# Kubernetes manifests – fraud-pipeline

Namespace: **fraud-pipeline**

**Current setup: CPU-only.** GPU deployments are in `k8s/disabled/` and are not applied by default.

## Active (CPU) deployments

| File | Deployment name | Replicas (default) | Resources |
|------|-----------------|--------------------|-----------|
| `namespace.yaml` | — | — | — |
| `data-gather-deployment.yaml` | data-gather | 1 | CPU |
| `preprocessing-cpu-deployment.yaml` | preprocessing-cpu | 1 | CPU |
| `inference-cpu-deployment.yaml` | inference-cpu | 2 | CPU |

---

## 🚀 Quick Start Guide

### 1. Build and Deploy (First Time Setup)

```bash
# Step 1: Build Docker images
chmod +x k8s/build-images.sh
./k8s/build-images.sh

# Step 2: Load images into cluster (if using Kind)
kind load docker-image fraud-pipeline/data-gather:v2 fraud-pipeline/preprocessing-cpu:v2 fraud-pipeline/inference-cpu:v2

# Step 3: Create namespace and deploy pods
kubectl apply -f k8s/namespace.yaml
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
kubectl logs -n fraud-pipeline deployment/inference-cpu --tail=50

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
kubectl apply -f k8s/data-gather-deployment.yaml
kubectl apply -f k8s/preprocessing-cpu-deployment.yaml
kubectl apply -f k8s/inference-cpu-deployment.yaml
```

Or apply the whole directory (only the files above are in `k8s/` now):

```bash
kubectl apply -f k8s/
```

If you previously applied GPU deployments and want to remove them (e.g. to clear Pending/ImagePullBackOff):

```bash
kubectl delete deployment -n fraud-pipeline model-build preprocessing-gpu inference-gpu --ignore-not-found
```

## Storage / FlashBlade

**You do not need FlashBlade.** The app uses `config_contract.StoragePaths.get_path()`:

- If `/mnt/flashblade` **exists** (e.g. FlashBlade or NFS mounted), it uses that.
- If **not**, it uses in-container fallback paths under the app dir (e.g. `/app/run_data_output`, `/app/run_features_output`), which are created automatically and are writable.

So without FlashBlade, everything works; data is written inside the container. For production you can mount a PVC or NFS at `/mnt/flashblade` if you want shared storage.

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
