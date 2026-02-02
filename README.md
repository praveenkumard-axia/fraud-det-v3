# 🦅 Spearhead Fraud Detection - Continuous Pipeline

Real-time, non-blocking fraud detection pipeline designed for High-Throughput streaming environments (FlashBlade + Redis).

## 🏗️ Architecture Overview

The system operates as a series of decoupled microservices (Pods) communicating through persistent queues.

```text
Synthetic Generator  → [ Redis: raw-transactions ] → Data Prep
                                                        ↓
[ Redis: inference-results ] ← Inference Client ← [ Redis: features-ready ]
                                                        ↓
                                           [ FlashBlade: Models / Logs ]
                                                        ↑
                                                 Model Training
```

---

## 🛠️ DevOps Handbook

### 1. Infrastructure Requirements
- **Redis (Required)**: Used as the central message bus for all inter-pod communication. 
    - Default: `redis://localhost:6379/0`
- **FlashBlade / S3 (Recommended)**: Persistent storage for millions of Parguet files and model versions.
    - Mount point expected: `/mnt/flashblade` (Configurable in `config_contract.py`)
- **Python Runtime**: Python 3.8+ with virtual environment recommended.
- **Optional**: Nvidia Triton Inference Server for GPU-accelerated inference.

### 2. High-Level Deployment
The system can be deployed in two modes:

#### **Mode A: Single-Host (Orchestrated)**
Use the unified orchestrator to manage the lifecycle of all 4 pods as background processes.
```bash
# Setup dependencies
/home/anuj/Axia/myenv/bin/pip install redis faker numpy polars pyarrow xgboost

# Launch the entire pipeline (Asynchronous & Non-blocking)
/home/anuj/Axia/myenv/bin/python run_pipeline.py
```

#### **Mode B: Distributed (Kubernetes)**
Deploy the contents of the `pods/` directory as independent containers:
1.  `pods/data-gather`: Scaling limit = 1 replica.
2.  `pods/data-prep`: Autoscale 1-10 replicas based on `raw-transactions` queue depth.
3.  `pods/model-build`: CronJob or singleton Deployment.
4.  `pods/inference`: Autoscale 2-20 replicas based on `features-ready` queue depth.

### 3. Critical Environment Variables
| Variable | Default | Description |
|----------|---------|-------------|
| `QUEUE_TYPE` | `redis` | `redis` (Required for cross-pod) or `inmemory` (Dev only) |
| `REDIS_URL` | `redis://localhost:6379/0` | Connection string for Redis |
| `CONTINUOUS_MODE` | `true` | Set to `true` for streaming, `false` for batch extraction |
| `GENERATION_RATE` | `50000` | Target rows/second for the generator |
| `FLASHBLADE_ENABLED` | `false` | Set `true` if FB is mounted at `/mnt/flashblade` |

### 4. Backlog Monitoring & Scaling Triggers
DevOps should monitor the following Redis list lengths to trigger autoscaling:

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
- `queue_interface.py`: Handles Redis connection pooling and serialization.
- `run_pipeline.py`: Asynchronous process manager and terminal logger.
- `pods/`: Source code for the 4 pipeline stages.
- `run_data_output/`: Default storage directory (DevOps: change this to FB mount).

---

## ✅ Deployment Checklist
- [ ] Redis server is up and reachable.
- [ ] Python dependencies installed in local environment.
- [ ] FlashBlade mount point verified (or local fallback directories cleaned).
- [ ] `PYTHONUNBUFFERED=1` is set in pod environment for real-time log ingestion.
- [ ] Triton Inference Server (optional) address configured in `inference/client.py`.

**Developer:** Anuj  
**Architecture:** Spearhead Non-Blocking Streaming  
**Target Throughput:** 100k+ Transactions/Sec  
