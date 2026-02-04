# 🦅 Spearhead Fraud Detection - Continuous Pipeline

Real-time, non-blocking fraud detection pipeline designed for High-Throughput streaming environments (FlashBlade or SSD only; no Redis).

## 🏗️ Architecture Overview

The system operates as a series of decoupled microservices (Pods) communicating through a **shared volume** at `/mnt/flashblade`. All queue data and artifacts are file-based; each stage reads and writes in separate subdirectories.

```text
Synthetic Generator  → [ /mnt/flashblade/queue/raw-transactions ] → Data Prep
                                                                         ↓
[ /mnt/flashblade/queue/inference-results ] ← Inference ← [ queue/features-ready ]
                                                                         ↓
                                    [ /mnt/flashblade: models, logs, raw-data, features ]
                                                                         ↑
                                                                  Model Training
```

---

## 🛠️ DevOps Handbook

### 1. Infrastructure Requirements
- **Shared storage (Required)**: FlashBlade or SSD mounted at `/mnt/flashblade` for all pods. All inter-pod communication is file-based on this volume (no Redis).
    - In Kubernetes: use the provided PVC `fraud-pipeline-flashblade` so every pod mounts the same volume.
- **Python Runtime**: Python 3.8+ with virtual environment recommended.
- **Optional**: Nvidia Triton Inference Server for GPU-accelerated inference.

### 2. High-Level Deployment
The system can be deployed in two modes:

#### **Mode A: Single-Host (Orchestrated)**
Use the unified orchestrator to manage the lifecycle of all 4 pods as background processes.
```bash
# Setup dependencies (no Redis; queue is file-based on FlashBlade/SSD)
pip install faker numpy polars pyarrow xgboost

# Launch the entire pipeline (Asynchronous & Non-blocking)
/home/anuj/Axia/myenv/bin/python run_pipeline.py
```

#### **Mode B: Distributed (Kubernetes)**
Deploy the contents of the `pods/` directory as independent containers:
1.  `pods/data-gather`: Scaling limit = 1 replica.
2.  `pods/data-prep`: Autoscale 1-10 replicas based on `raw-transactions` queue depth.
3.  `pods/model-build`: CronJob or singleton Deployment.
4.  `pods/inference`: Autoscale 2-20 replicas based on `features-ready` queue depth.

**Quick Start:**
```bash
# Build and deploy
./k8s/build-images.sh
kubectl apply -f k8s/

# Start the pipeline
kubectl scale deployment -n fraud-pipeline data-gather --replicas=1
kubectl scale deployment -n fraud-pipeline preprocessing-cpu --replicas=1
kubectl scale deployment -n fraud-pipeline inference-cpu --replicas=2

# Stop the pipeline
kubectl scale deployment -n fraud-pipeline data-gather preprocessing-cpu inference-cpu --replicas=0

# Monitor
kubectl get pods -n fraud-pipeline
kubectl logs -n fraud-pipeline deployment/data-gather --tail=20
```

*See `k8s/README.md` for complete deployment instructions and troubleshooting.*

### 3. Critical Environment Variables
| Variable | Default | Description |
|----------|---------|-------------|
| `QUEUE_TYPE` | `flashblade` | File-based queue only (no Redis). |
| `FLASHBLADE_PATH` | `/mnt/flashblade` | Shared volume path for queue and storage. |
| `CONTINUOUS_MODE` | `true` | Set to `true` for streaming, `false` for batch extraction |
| `GENERATION_RATE` | `50000` | Target rows/second for the generator |

### 4. Backlog Monitoring & Scaling Triggers
DevOps should monitor queue depths (file counts under `/mnt/flashblade/queue/...`) to trigger autoscaling:

- **`raw-transactions`**: 
    - Warning: > 1.5M records. 
    - Action: Scale up **Data Prep** pods.
- **`features-ready`**: 
    - Warning: > 250k records.
    - Action: Scale up **Inference** pods.

---

## 📡 API Reference for Monitoring
The `backend_server.py` exposes REST APIs for your monitoring stack:

- **Health Check**: `GET /api/dashboard`
- **Queue Depth**: `GET /api/backlog/status` (Use this for HPA/Autoscaling triggers)
- **Pressure Alerts**: `GET /api/backlog/pressure`
- **Real-time Stream**: `ws://localhost:8000/ws/metrics`

*See `API_PAYLOADS.md` for full JSON schemas and payload examples.*

---

## 📁 Project Structure
- `config_contract.py`: The single source of truth for DevOps/Dev interfaces.
- `queue_interface.py`: File-based queue on FlashBlade/SSD (no Redis).
- `run_pipeline.py`: Asynchronous process manager and terminal logger.
- `pods/`: Source code for the 4 pipeline stages.
- `run_data_output/`: Default storage directory (DevOps: change this to FB mount).

---

## ✅ Deployment Checklist
- [ ] Shared volume at `/mnt/flashblade` (in K8s: PVC `fraud-pipeline-flashblade` applied).
- [ ] Python dependencies installed in local environment.
- [ ] No Redis required; all communication is file-based on the shared volume.
- [ ] `PYTHONUNBUFFERED=1` is set in pod environment for real-time log ingestion.
- [ ] Triton Inference Server (optional) address configured in `inference/client.py`.

**Developer:** Anuj  
**Architecture:** Spearhead Non-Blocking Streaming  
**Target Throughput:** 100k+ Transactions/Sec  
