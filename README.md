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
| ImagePullBackOff | Build locally; use `make load-kind` (Kind) or `make load-minikube` (Minikube) |
| CrashLoopBackOff | `make build-no-cache` then `make restart` |
| PVC Pending | Check StorageClass; multi-node needs ReadWriteMany |
| Metrics API missing | Install metrics-server (Kind/Minikube) |
