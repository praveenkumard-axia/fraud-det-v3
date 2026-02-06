# Fraud Detection Pipeline

Real-time fraud detection pipeline with file-based queueing on shared storage (FlashBlade or PVC). Deploy to Kubernetes and benchmark via the dashboard.

## Architecture

```
Generator (data-gather) → [raw-transactions] → Data Prep (preprocessing-cpu/gpu)
                                                      ↓
Inference (inference-cpu/gpu) ← [features-ready] ← Model (model-build)
       ↓
[inference-results] → Backend (dashboard API + metrics)
```

All pods share volume at `/mnt/flashblade`. Backend provides REST API, WebSocket metrics, and dashboard control.

## Quick Start

### 1. Build images

```bash
make build
```

### 2. Load images

**Kind:**
```bash
make load-kind
```

**Minikube** (or Docker Desktop K8s): build directly into cluster Docker:
```bash
make load-minikube
```

### 3. Deploy

**Option A: CPU Machine + Local SSD**
Host must have directory `/mnt/data/fraud-pipeline` created.
```bash
make deploy-cpu
```

**Option B: GPU Machine + FlashBlade**
Nodes must have NVIDIA GPUs and connect to FlashBlade via `pure-file` StorageClass.
```bash
make deploy-gpu
```

### 4. Port-forward backend and start pipeline

```bash
make port-forward &
make start
```

### 5. Open dashboard

Serve `dashboard-v4-preview.html` with `DASHBOARD_BACKEND_URL=http://localhost:8000`, or open directly if backend is on same host.

### 6. Benchmark

The pipeline generation rate (transactions/sec) is the primary benchmark control.

**Run Load Test:**
1. Open Dashboard -> "Control" Tab.
2. Set "Target Rate" (e.g., 5000 for CPU, 50000 + for GPU).
3. Click "Start".
4. Monitor "Throughput" on the dashboard.

**Metrics via CLI:**
```bash
# Business metrics (latency, fraud rate)
curl -s http://localhost:8000/api/business/metrics | jq .

# Machine metrics (CPU/GPU utilization, queue depth)
curl -s http://localhost:8000/api/machine/metrics | jq .
```

### 7. Stop

```bash
make stop
```

---

## Makefile targets

| Target | Description |
|--------|-------------|
| `make build` | Build all Docker images |
| `make build-no-cache` | Build with --no-cache |
| `make load-kind` | Load images into Kind cluster |
| `make load-minikube` | Build into Minikube (no separate load step) |
| `make deploy-cpu` | **NEW:** Deploy CPU + Local SSD config |
| `make deploy-gpu` | **NEW:** Deploy GPU + FlashBlade config |
| `make deploy` | Deploy default legacy all-in-one manifest |
| `make start` | Start pipeline (scale deployments up) |
| `make stop` | Stop pipeline (scale to 0) |
| `make port-forward` | Port-forward backend to localhost:8000 |
| `make logs` | Tail data-gather logs |
| `make status` | Show pods in fraud-pipeline namespace |
| `make restart` | Rollout restart all deployments |
| `make clean` | Delete fraud-pipeline namespace |

---

## K8s resources

| Resource | Purpose |
|----------|---------|
| Namespace | fraud-pipeline |
| PVC | fraud-pipeline-flashblade (or local-pvc) |
| Deployments | data-gather, preprocessing-cpu/gpu, model-build, inference-cpu/gpu, backend |
| Services | backend, inference-gpu |

---

## Metrics (Prometheus / Pure1)

Set on backend deployment:

**Local disk / General:**
```bash
kubectl set env deployment/backend -n fraud-pipeline PROMETHEUS_URL=http://prometheus.monitoring:9090
```

**FlashBlade (Pure1 + FB Prometheus):**
```bash
kubectl set env deployment/backend -n fraud-pipeline PURE_SERVER=true PROMETHEUS_URL=http://prometheus.monitoring:9090
```

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
### 1. Image Issues (ErrImageNeverPull / ImagePullBackOff)

If using Kind or Minikube with `imagePullPolicy: Never`, images must be manually loaded into the cluster node.

**Kind:**
```bash
make load-kind
```

**Minikube:**
```bash
make load-minikube
```

### 2. Pods Stuck in "Pending" / Resource Starvation

If pods remain `Pending`, the node may not have enough CPU/Memory.

**Check constraints:**
```bash
kubectl describe pod -n fraud-pipeline <pod-name>
kubectl describe nodes
```

**Fix:** Edit `k8s_configs/cpu-local-ssd.yaml` and reduce `resources.requests` (e.g., set memory to `512Mi` or `1Gi`).

### 3. Persistent Volume Stuck in "Released"

If `kubectl get pv` shows `Released` but not `Available` (binding issue), force delete both the PVC and PV to reset.

```bash
kubectl delete pvc fraud-pipeline-flashblade -n fraud-pipeline --force
kubectl delete pv fraud-pipeline-local-pv --force
# Re-deploy
make deploy-cpu
```

### 4. Application Crash (CrashLoopBackOff)

Rebuild images cleanly and restart deployments.

```bash
make build-no-cache
make restart
```

### 5. RBAC / Scaling Errors

If the backend fails to scale pods (logs show "Forbidden"), verify RBAC permissions. The `fraud-backend` ServiceAccount must have `deployments/scale` access.

**Verify Role:**
```bash
kubectl describe role fraud-backend-role -n fraud-pipeline
```

**Fix:** Ensure the Role in `k8s_configs/*.yaml` includes:
```yaml
- apiGroups: ["apps"]
  resources: ["deployments/scale"]
  verbs: ["get", "patch", "update"]
```
