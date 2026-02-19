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
Host must have directory `/mnt/data/fraud-det-v3` created.
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
| `make status` | Show pods in fraud-det-v3 namespace |
| `make restart` | Rollout restart all deployments |
| `make clean` | Delete fraud-det-v3 namespace |

---

## Windows Instructions (PowerShell)

If you are on Windows and don't have `make` or `bash`, use the provided PowerShell scripts:

| PowerShell Command | Equivalent Makefile Target |
|--------------------|----------------------------|
| `.\Makefile.ps1 build` | `make build` |
| `.\Makefile.ps1 build-no-cache` | `make build-no-cache` |
| `.\Makefile.ps1 deploy` | `make deploy` |
| `.\Makefile.ps1 start` | `make start` |
| `.\Makefile.ps1 stop` | `make stop` |
| `.\Makefile.ps1 port-forward` | `make port-forward` |
| `.\Makefile.ps1 logs` | `make logs` |
| `.\Makefile.ps1 status` | `make status` |
| `.\Makefile.ps1 restart` | `make restart` |
| `.\Makefile.ps1 clean` | `make clean` |

**Note:** Ensure your PowerShell execution policy allows running local scripts:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

---

## K8s resources

| Resource | Purpose |
|----------|---------|
| Namespace | fraud-det-v3 |
| PVC | fraud-det-v3-flashblade (or local-pvc) |
| Deployments | data-gather, preprocessing-cpu/gpu, model-build, inference-cpu/gpu, backend |
| Services | backend, inference-gpu |

---

---

## 🛠 Project Status & Setup (Latest Updates)

### Current Status
- ✅ **Eviction Fix**: Backend memory request set to **1Gi** with **ephemeral-storage** limits.
- ✅ **OOM Fix**: `data-gather` workers reduced to **4** with **16Gi** RAM limit.
- ✅ **Prometheus Connectivity**: Configured to use external master at `http://10.23.181.153:9090`.
- ✅ **Dashboard Stability**: Fixed JS typos and added DOM null checks.

### Final Prometheus Configuration (cAdvisor)
To enable pod-level CPU/Mem metrics on the dashboard, update your master Prometheus config:

1. **Find config**: `ps aux | grep prometheus` (usually `/etc/prometheus/prometheus.yml`).
2. **Apply job**: Add the following under `scrape_configs`:
```yaml
  - job_name: 'kubernetes-node-44-cadvisor'
    scheme: https
    tls_config:
      insecure_skip_verify: true
    bearer_token: "YOUR_TOKEN_HERE" # Generate with: kubectl create token prometheus-scraper -n monitoring
    metrics_path: /metrics/cadvisor
    static_configs:
      - targets: ['10.23.181.44:10250']
```
3. **Restart**: `sudo systemctl restart prometheus`.

---

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
kubectl describe pod -n fraud-det-v3 <pod-name>
kubectl describe nodes
```

**Fix:** Edit `k8s_configs/cpu-local-ssd.yaml` and reduce `resources.requests` (e.g., set memory to `512Mi` or `1Gi`).

### 3. Persistent Volume Stuck in "Released"

If `kubectl get pv` shows `Released` but not `Available` (binding issue), force delete both the PVC and PV to reset.

```bash
kubectl delete pvc fraud-det-v3-flashblade -n fraud-det-v3 --force
kubectl delete pv fraud-det-v3-local-pv --force
# Re-deploy
make deploy-cpu
```

### 4. Application Crash (CrashLoopBackOff)

Rebuild images cleanly and restart deployments.

```bash
make build-no-cache
make restart
```

### 6. Permission Denied on Shared Volumes

If logs show `[Errno 13] Permission denied` (e.g. for `.metrics.json`), it means files were created by a different user UID in a previous run.

**Fix:** Use the `k8s_configs/cleanup-job.yaml` to fix permissions and clear stale data.
```powershell
kubectl apply -f k8s_configs/cleanup-job.yaml
# Wait for completion, then delete
kubectl delete -f k8s_configs/cleanup-job.yaml
```

### 7. Node Disk Pressure (Taints)

If pods are stuck in `ContainerCreating` and nodes show `DiskPressure`, the node cannot pull new images.

**Fix:**
1. Clear the FlashBlade volumes using the cleanup job above.
2. (If authorized) Clean up Docker/containerd images on the node directly:
```bash
docker system prune -a --volumes --force
```
3. The `dual-flashblade.yaml` manifest includes **Tolerations** to allow scheduled pods to bypass this blocker while the node recovers.
