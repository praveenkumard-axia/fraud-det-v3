# 🦅 Spearhead Fraud Detection - Continuous Pipeline

Real-time, non-blocking fraud detection pipeline designed for High-Throughput streaming environments (FlashBlade or SSD only; no Redis).

## 🏗️ Architecture Overview

The system operates as a series of decoupled microservices (Pods) communicating through a **shared volume** at `/mnt/flashblade`. All queue data and artifacts are file-based; each stage reads and writes in separate subdirectories.

```text
Synthetic Generator  → [ /mnt/flashblade/queue/raw-transactions ] → Data Prep
                                                                         ↓
[ /mnt/flashblade/queue/inference-results ] ← Inference ← [ queue/features-ready ]
                                                 ↓                       ↓
                                        [ Real-time Business BI ] ← [ Model Training ]
                                                 ↑                       ↑
                                     [ /mnt/flashblade: metrics, models, logs, raw-data ]
```

---

## 🚀 Business Intelligence & Real-time Metrics

The system now includes a fully integrated **Business Intelligence API** that provides real-time transaction insights derived directly from the live pipeline.

### **1. Real-time Data Flow**
- **Inference Pod**: Analyzes every transaction, calculates risk scores (0.0-1.0), and publishes real-time aggregations (Category risk, State risk, Dollar volume) to the shared `queue_service`.
- **Queue Service**: Persists global metrics to the shared volume (`.metrics.json`), enabling atomic updates and cross-process communication between pipeline pods and the backend.
- **Backend API**: Consumes live metrics and exposes a single-endpoint Business Intelligence interface.

### **2. Business API Features**
- ✅ **100% Data-Driven**: No hardcoded placeholders; all metrics (even dollar amounts) are summed from the live stream.
- ✅ **17 Key Performance Indicators (KPIs)**: Includes Fraud Exposure, Annual Savings, Precision/Recall, and Fraud Velocity.
- ✅ **Risk Concentration**: Real-time calculation of the Top 1% of transactions contributing to fraud.
- ✅ **Category & Geographic Analysis**: Top risk categories and hot-spot states updated every second.

---

## 🛠️ DevOps Handbook

### 1. Infrastructure Requirements
- **Shared storage (Required)**: FlashBlade or SSD mounted at `/mnt/flashblade` for all pods. All inter-pod communication and **Global Metrics** are file-based on this volume.
- **Python Runtime**: Python 3.8+ with virtual environment recommended.
- **Dependencies**: `numpy`, `polars`, `pyarrow`, `xgboost`, `fastapi`, `uvicorn`, `websockets`.

### 2. Launching the System
```bash
# Terminal 1: Start the Backend & Business API
/home/anuj/Axia/myenv/bin/python backend_server.py

# Terminal 2: Start the entire Pipeline (Generator → Prep → Train → Inference)
/home/anuj/Axia/myenv/bin/python run_pipeline.py
```

### 3. Testing the Business API
Wait for the pipeline to start processing (check `pipeline.log`), then run:
```bash
# Get all business KPIs
curl -s http://localhost:8000/api/business/metrics | jq .

# Check specific live metrics
curl -s http://localhost:8000/api/business/metrics | jq '.risk_signals_by_category'
curl -s http://localhost:8000/api/business/metrics | jq '.recent_risk_signals'
```

---

## 📡 API Reference

The `backend_server.py` exposes REST APIs for your monitoring stack:

- **Business Intelligence**: `GET /api/business/metrics` (Real-time financial & ML KPIs)
- **Health Check**: `GET /api/dashboard` (Infrastructure telemetry)
- **Queue Depth**: `GET /api/backlog/status` (Use for HPA/Autoscaling triggers)
- **Pressure Alerts**: `GET /api/backlog/pressure`
- **Real-time Stream**: `ws://localhost:8000/ws/metrics`

*See `API_PAYLOADS.md` for full JSON schemas and payload examples.*

---

## 📁 Project Structure
- `config_contract.py`: Single source of truth for paths and thresholds.
- `queue_interface.py`: Shared FlashBlade queue with **Metrics Persistence**.
- `run_pipeline.py`: Orchestrator for local dev/testing.
- `pods/`: Source code for the 4 pipeline stages.
- `dashboard-v4-preview.html`: Real-time interactive UI with integrated Business Tab.

---

## ✅ Deployment Checklist
- [ ] Shared volume at `/mnt/flashblade` (with write permissions for metrics/queues).
- [ ] Model weights present in `run_models_output/` (or run Training pod).
- [ ] Backend server running to expose the `/api/business/metrics` endpoint.
- [ ] Threshold `0.52` configured for optimal Business/ML balance.

**Developer:** Anuj  
**Architecture:** Spearhead Non-Blocking Streaming  
**Target Throughput:** 100k+ Transactions/Sec  

