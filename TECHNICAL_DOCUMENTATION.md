# Fraud Detection ML Pipeline - Complete Technical Documentation

**Author:** Technical Analysis  
**Date:** February 15, 2026  
**Version:** 3.0  
**Repository:** fraud-det-v3  

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [System Architecture Overview](#system-architecture-overview)
3. [API Layer](#api-layer)
4. [Data Flow](#data-flow)
5. [Component Deep Dive](#component-deep-dive)
6. [GPU vs CPU Architecture](#gpu-vs-cpu-architecture)
7. [Kubernetes & Docker](#kubernetes--docker)
8. [Performance & Optimization](#performance--optimization)
9. [Metrics & Monitoring](#metrics--monitoring)
10. [Troubleshooting Guide](#troubleshooting-guide)

---

## Executive Summary

This is a **real-time fraud detection pipeline** built on Kubernetes that processes credit card transactions at scale (up to 50K+ transactions/second on GPU infrastructure). The system uses:

- **Queue-based architecture** with FlashBlade file-based queuing
- **Continuous processing** across 4 main pods
- **Dual deployment modes**: CPU-only or GPU-accelerated
- **Real-time inference** with XGBoost models
- **Interactive dashboard** for monitoring and control

### Key Technologies
- **Data Processing:** Polars (CPU), RAPIDS cuDF (GPU)
- **Model Training:** XGBoost with GPU/CPU support
- **Inference:** Triton Inference Server (GPU) / Native XGBoost (CPU)
- **Storage:** FlashBlade for high-throughput shared storage
- **Orchestration:** Kubernetes with dynamic scaling
- **Backend API:** FastAPI with WebSocket support

---

## System Architecture Overview

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                          DASHBOARD UI                                │
│                    (dashboard-v4-preview.html)                       │
└────────────────────────────┬────────────────────────────────────────┘
                             │ HTTP/WebSocket
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       BACKEND SERVER (FastAPI)                       │
│  - REST API endpoints                                                │
│  - Pod orchestration & scaling                                       │
│  - Telemetry aggregation                                             │
│  - Metrics calculation                                               │
└────────────────────────────┬────────────────────────────────────────┘
                             │ kubectl commands
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        KUBERNETES CLUSTER                            │
│  Namespace: fraud-det-v3                                             │
└─────────────────────────────────────────────────────────────────────┘
                             │
        ┌────────────────────┴───────────────────┬─────────────────┐
        ▼                    ▼                    ▼                 ▼
   ┌─────────┐        ┌─────────────┐      ┌──────────┐     ┌──────────┐
   │  Data   │        │    Data     │      │  Model   │     │Inference │
   │ Gather  │───────▶│    Prep     │─────▶│  Build   │────▶│  Client  │
   │  (Pod1) │        │   (Pod2)    │      │  (Pod3)  │     │  (Pod4)  │
   └─────────┘        └─────────────┘      └──────────┘     └──────────┘
        │                    │                    │                 │
        └────────────────────┴────────────────────┴─────────────────┘
                             │
                             ▼
                ┌────────────────────────┐
                │   FLASHBLADE STORAGE   │
                │  (Shared PVC/Volume)   │
                │                        │
                │  Queue-based Workflow: │
                │  • raw-transactions    │
                │  • features-ready      │
                │  • inference-results   │
                │  • training-queue      │
                └────────────────────────┘
```

### Components Overview

| Component | Purpose | Technology Stack | Scalability |
|-----------|---------|------------------|-------------|
| **Data Gather** | Generate synthetic transactions | Python, Faker, NumPy, PyArrow | 1-8 pods |
| **Data Prep** | Feature engineering | Polars (CPU) / RAPIDS (GPU) | 1-4 pods |
| **Model Build** | Train XGBoost models | XGBoost, cuML (GPU) | 0-2 pods |
| **Inference** | Predict fraud scores | Triton (GPU) / XGBoost (CPU) | 1-4 pods |
| **Backend** | API & orchestration | FastAPI, Kubernetes Python Client | 1 pod |

---

## API Layer

### Base URL
```
http://localhost:8000  (via port-forward)
http://backend.fraud-det-v3.svc.cluster.local:8000  (inside cluster)
```

### Core Endpoints

#### 1. Dashboard Data Endpoint
**GET** `/api/dashboard`

**Response Schema:**
```json
{
  "pipeline_progress": {
    "generated": 5000000,
    "data_prep_cpu": 2000000,
    "data_prep_gpu": 3000000,
    "inference_cpu": 1500000,
    "inference_gpu": 3500000,
    "backlog": 150000
  },
  "utilization": {
    "gpu": 85,
    "cpu": 72,
    "flashblade": 45
  },
  "throughput": {
    "gpu": 35000,
    "cpu": 15000
  },
  "business": {
    "fraud_prevented": 125000,
    "txns_scored": 5000000,
    "fraud_blocked": 25000,
    "throughput": 50000
  },
  "fraud_dist": {
    "low": 3250000,
    "medium": 1250000,
    "high": 500000
  },
  "flashblade": {
    "read": 12000,
    "write": 18000,
    "util": 45,
    "headroom": 55.0,
    "cpu_vol": 12000,
    "gpu_vol": 18000
  },
  "status": {
    "live": true,
    "elapsed": "05:23.4",
    "stage": "Inference",
    "status": "Running"
  },
  "queue_backlogs": {
    "raw_transactions": 150000,
    "features_ready": 50000,
    "inference_results": 10000
  },
  "pod_counts": {
    "generation": 1,
    "preprocessing": 1,
    "training": 1,
    "inference": 2,
    "preprocessing_gpu": 1,
    "inference_gpu": 1
  },
  "system_config": {
    "generation_rate": 50000,
    "priority": "balanced"
  }
}
```

**Data Source:**
- **Real-time from pods**: Telemetry logs parsed from Kubernetes pod stdout
- **Queue metrics**: Direct reads from FlashBlade queue directories
- **Calculated metrics**: Backend aggregates pod telemetry

**Update Frequency:**
- Dashboard polls every 1 second
- Backend aggregates telemetry as logs arrive
- Queue backlogs updated on each API call (file count)

#### 2. Pipeline Control Endpoints

**POST** `/api/control/start`
```json
{
  "success": true,
  "message": "Pipeline started (K8s pods scaled up)",
  "replicas": {
    "data-gather": 1,
    "preprocessing-cpu": 1,
    "inference-cpu": 2
  }
}
```

**POST** `/api/control/stop`
```json
{
  "success": true,
  "message": "Pipeline stopped"
}
```

**POST** `/api/control/reset`
```json
{
  "success": true,
  "message": "Pipeline reset"
}
```

#### 3. Scaling Endpoints

**POST** `/api/control/scale/generation`
```json
{
  "replicas": 2
}
```

**POST** `/api/control/scale/preprocessing`
**POST** `/api/control/scale/preprocessing-gpu`
**POST** `/api/control/scale/training`
**POST** `/api/control/scale/inference`
**POST** `/api/control/scale/inference-gpu`

All follow the same pattern with replica count validation against configured min/max.

### API Call Flow

#### UI → Backend Flow

```
User clicks "Start" on Dashboard
    ↓
JavaScript: fetch('http://localhost:8000/api/control/start', {method: 'POST'})
    ↓
Backend: start_pipeline() function executes
    ↓
Backend runs: kubectl scale deployment/data-gather --replicas=1 -n fraud-det-v3
Backend runs: kubectl scale deployment/preprocessing-cpu --replicas=1 -n fraud-det-v3
Backend runs: kubectl scale deployment/inference-cpu --replicas=2 -n fraud-det-v3
    ↓
Pods start → Begin telemetry logging
    ↓
Backend: _k8s_telemetry_loop() discovers running pods
Backend: _tail_pod_logs() captures stdout from each pod
    ↓
Backend: parse_telemetry_line() extracts metrics
Backend: state.update_telemetry() updates in-memory state
    ↓
Dashboard polls: fetch('http://localhost:8000/api/dashboard')
    ↓
Backend: get_dashboard_data() returns current state
    ↓
Dashboard: Updates charts and metrics display
```

### Why Second API Call Takes Time (1-2 seconds)

**Root Cause:** Cold start + Kubernetes pod scheduling

**Detailed Flow:**
1. **First call** (`/api/control/start`):
   - Executes `kubectl scale` commands (fast, ~200ms)
   - Returns success immediately
   - Pods begin scheduling (async)

2. **Second call** (`/api/dashboard`) within 1-2 seconds:
   - Pods are still in `ContainerCreating` or just `Running`
   - No telemetry logs available yet
   - Backend waits for pod discovery in `_k8s_telemetry_loop()`
   - **Delay: ~2-5 seconds** for pods to start logging

3. **Subsequent calls** (`/api/dashboard`):
   - Telemetry available
   - Fast response (~50-100ms)

**How to Reduce Latency:**

1. **Pre-warm pods** (keep at 0 replicas but ready):
   ```yaml
   - Use readinessProbe with initialDelaySeconds: 1
   - Reduce pod startup time with smaller images
   ```

2. **Cache last known state**:
   ```python
   # In backend_server.py
   if not telemetry_available:
       return cached_state  # Return last known good state
   ```

3. **Return optimistic response**:
   ```python
   # Immediately after scaling
   return {"status": "starting", "estimated_ready": "3s"}
   ```

---

## Data Flow

### Complete End-to-End Flow

```
┌──────────────────────────────────────────────────────────────────────┐
│ STAGE 1: DATA GENERATION (Pod 1: data-gather)                        │
└──────────────────────────────────────────────────────────────────────┘
   
   Triggered by: kubectl scale deployment/data-gather --replicas=1
   
   Process:
   1. Pod starts → gather.py main() executes
   2. Generate string pools using Faker (one-time, ~10 seconds)
   3. Spawn N worker subprocesses (default: 8 workers)
   4. Each worker generates chunks of 50K transactions
   5. Write to: /mnt/flashblade/queue/raw-transactions/pending/*.parquet
   
   Files Written:
   - /mnt/flashblade/queue/raw-transactions/pending/batch_000001.parquet
   - /mnt/flashblade/queue/raw-transactions/pending/batch_000002.parquet
   - ... (continuous)
   
   Storage: FlashBlade (CPU volume) or PVC
   Format: Parquet with Snappy compression
   Schema: 22 columns (cc_num, amt, lat, long, category, is_fraud, etc.)
   
   Telemetry Logged:
   [TELEMETRY] stage=Ingest | status=Running | rows=500000 | throughput=25000 | ...
   
   ↓

┌──────────────────────────────────────────────────────────────────────┐
│ STAGE 2: FEATURE ENGINEERING (Pod 2: preprocessing-cpu/gpu)          │
└──────────────────────────────────────────────────────────────────────┘
   
   Triggered by: Queue backlog > 0 (automatic via continuous mode)
   
   Process:
   1. Pod continuously monitors queue_service.consume_batch()
   2. Reads from: /mnt/flashblade/queue/raw-transactions/pending/
   3. Moves file to: /mnt/flashblade/queue/raw-transactions/processing/
   4. Loads Parquet → Polars DataFrame (or cuDF if GPU)
   5. Apply feature engineering:
      - amt_log = log(amt + 1)
      - hour_of_day = (unix_time / 3600) % 24
      - day_of_week = (unix_time / 86400) % 7
      - is_weekend = (day_of_week >= 5)
      - distance_km = haversine(lat, long, merch_lat, merch_long)
   6. Drop string columns (merchant, first, last, etc.)
   7. Write to: /mnt/flashblade/queue/features-ready/pending/*.parquet
   8. Move processed file to: /mnt/flashblade/queue/raw-transactions/completed/
   
   GPU Acceleration (if preprocessing-gpu):
   - Uses RAPIDS cuDF for DataFrame operations
   - 3-5x faster than CPU Polars for large datasets
   
   Files Written:
   - /mnt/flashblade/queue/features-ready/pending/features_000001.parquet
   
   Telemetry Logged:
   [TELEMETRY] stage=Data Prep | status=Running | rows=500000 | throughput=35000 | ...
   
   ↓

┌──────────────────────────────────────────────────────────────────────┐
│ STAGE 3: MODEL TRAINING (Pod 3: model-build)                         │
└──────────────────────────────────────────────────────────────────────┘
   
   Triggered by: Continuous retraining loop (every N minutes or M rows)
   
   Process:
   1. Pod monitors features queue backlog
   2. Checks system priority (training vs inference)
   3. If priority="training" or "balanced":
      - Consume batch from features-ready queue
      - Load latest 100 feature files (or configured amount)
      - Split 80/20 train/test
      - Train XGBoost classifier:
         ```python
         XGBClassifier(
             n_estimators=100,
             max_depth=6,
             learning_rate=0.1,
             tree_method='gpu_hist',  # if GPU available
             gpu_id=0
         )
         ```
      - Evaluate: Precision, Recall, F1, ROC-AUC
      - Save model to: /mnt/flashblade/models/fraud_model_v{version}.json
      - Generate Triton config (for GPU inference)
   
   GPU Acceleration (if model-build has GPU):
   - XGBoost tree_method='gpu_hist'
   - 10-20x faster training than CPU
   
   Files Written:
   - /mnt/flashblade/models/fraud_model_v001.json (XGBoost model)
   - /mnt/flashblade/models/fraud_model_v001/1/model.xgb (Triton format)
   - /mnt/flashblade/models/fraud_model_v001/config.pbtxt (Triton config)
   
   Metrics Generated:
   - Precision, Recall, F1-Score
   - ROC-AUC, Confusion Matrix
   - Training time, throughput
   
   Telemetry Logged:
   [TELEMETRY] stage=Model Train | status=Running | rows=500000 | ...
   
   ↓

┌──────────────────────────────────────────────────────────────────────┐
│ STAGE 4: INFERENCE (Pod 4: inference-cpu/gpu)                        │
└──────────────────────────────────────────────────────────────────────┘
   
   Triggered by: Features queue backlog > 0
   
   Process:
   1. Pod continuously consumes from features-ready queue
   2. Batch size: 10,000 transactions (configurable)
   3. Load latest model from /mnt/flashblade/models/
   4. Two inference paths:
   
      **GPU Path (inference-gpu with Triton):**
      - Send batch to Triton Inference Server (localhost:8001)
      - Triton loads XGBoost model with GPU acceleration
      - Returns fraud_probability for each transaction
      
      **CPU Path (inference-cpu):**
      - Load XGBoost model directly in Python
      - model.predict_proba(X) on CPU
      - Slower but no GPU required
   
   5. Apply threshold (default: 0.5):
      - fraud_score > 0.5 → Flag as fraud
      - fraud_score ≤ 0.5 → Legitimate
   
   6. Calculate risk distribution:
      - Low risk: score < 0.3
      - Medium risk: 0.3 ≤ score < 0.7
      - High risk: score ≥ 0.7
   
   7. Write results to: /mnt/flashblade/queue/inference-results/pending/*.parquet
   
   8. Update metrics:
      - queue_service.increment_metric("fraud_dist_low", low_count)
      - queue_service.increment_metric("fraud_dist_high", high_count)
      - queue_service.increment_metric("total_fraud_blocked", fraud_count)
   
   GPU Acceleration (if inference-gpu):
   - Triton batches requests across GPU
   - 5-10x faster than CPU inference
   
   Files Written:
   - /mnt/flashblade/queue/inference-results/pending/results_000001.parquet
   
   Metrics Updated (FlashBlade):
   - /mnt/flashblade/.metrics.json:
     {
       "fraud_dist_low": 325000,
       "fraud_dist_medium": 125000,
       "fraud_dist_high": 50000,
       "total_fraud_blocked": 50000
     }
   
   Telemetry Logged:
   [TELEMETRY] stage=Inference | status=Running | rows=500000 | fraud_blocked=2500 | ...
   
   ↓

┌──────────────────────────────────────────────────────────────────────┐
│ STAGE 5: DASHBOARD UPDATE (Backend aggregates & serves)              │
└──────────────────────────────────────────────────────────────────────┘
   
   Process:
   1. Backend tails pod logs (kubectl logs -f <pod>)
   2. Parses [TELEMETRY] lines
   3. Updates in-memory state.telemetry{}
   4. Reads queue metrics from FlashBlade
   5. Serves via /api/dashboard endpoint
   6. Dashboard polls every 1 second
   7. Charts update with new data
```

### Storage Details

| Path | Purpose | Format | Lifecycle |
|------|---------|--------|-----------|
| `/mnt/flashblade/queue/raw-transactions/pending/` | Incoming raw data | Parquet | → processing |
| `/mnt/flashblade/queue/raw-transactions/processing/` | Currently processing | Parquet | → completed |
| `/mnt/flashblade/queue/raw-transactions/completed/` | Processed raw data | Parquet | Archive |
| `/mnt/flashblade/queue/features-ready/pending/` | Engineered features | Parquet | → consumed |
| `/mnt/flashblade/queue/features-ready/completed/` | Consumed features | Parquet | Archive |
| `/mnt/flashblade/models/` | Trained models | JSON/XGBoost | Persistent |
| `/mnt/flashblade/queue/inference-results/` | Predictions | Parquet | Archive |
| `/mnt/flashblade/.metrics.json` | Global metrics | JSON | Updated continuously |

---

## Component Deep Dive

### 1. Data Gather (Pod 1)

**File:** `pods/data-gather/gather.py`

**Purpose:** Generate synthetic credit card transactions continuously

**Key Functions:**

```python
def generate_pools(output_path: Path) -> Path:
    """Generate string pools using Faker (one-time startup cost)"""
    # Creates pools of pre-generated names, addresses, merchants
    # Avoids repeated Faker calls (slow)
    # Saves to pickle file for workers to load
```

**Worker Process Model:**
- Main process spawns N subprocesses (default: 8)
- Each worker runs independently with own RNG seed
- Workers generate chunks of 50K transactions using NumPy vectorization
- Direct PyArrow Table creation (no pandas overhead)
- Writes Parquet files with Snappy compression

**Continuous Mode:**
```python
continuous_mode = os.getenv('CONTINUOUS_MODE', 'true').lower() == 'true'
target_rate = int(os.getenv('GENERATION_RATE', '50000'))  # rows/sec
```

**Backlog-Aware Throttling:**
```python
backlog = queue_service.get_backlog(QueueTopics.RAW_TRANSACTIONS)
if backlog > backlog_threshold:
    log(f"⚠️  Backlog too high ({backlog:,}), pausing generation...")
    time.sleep(5)
    continue
```

**Where Data Goes:**
1. Write to `/mnt/flashblade/queue/raw-transactions/pending/worker_XXX_YYYYY.parquet`
2. Publish batch to queue via `queue_service.publish_batch()`
3. Queue moves file from `pending/` → `processing/` when consumed

**Performance:**
- CPU Mode: 10-25K rows/sec per pod
- Scales linearly with replicas (2 pods = 20-50K rows/sec)
- Bottleneck: Disk write throughput (FlashBlade handles this well)

---

### 2. Data Prep (Pod 2)

**Files:** 
- `pods/data-prep/prepare.py` (main logic)
- `Dockerfile.cpu` (Polars-based)
- `Dockerfile.gpu` (RAPIDS cuDF-based)

**Purpose:** Feature engineering to transform raw transactions into ML-ready features

**CPU Mode (Polars):**

```python
def _process_cpu_polars(self, files: List[Path], run_name: str):
    # Use Polars lazy API for memory efficiency
    q = pl.scan_parquet(file_pattern)
    
    # Feature engineering in lazy mode (no execution yet)
    q = q.with_columns([
        pl.col("amt").log1p().alias("amt_log"),
        (pl.col("unix_time") / 3600 % 24).cast(pl.Int8).alias("hour_of_day"),
        (pl.col("unix_time") / 86400 % 7).cast(pl.Int8).alias("day_of_week"),
    ])
    
    # Sink to parquet (triggers execution, streams to disk)
    q.sink_parquet(output_file, compression='snappy')
```

**Why Polars?**
- 10-20x faster than Pandas for large datasets
- Lazy execution (query optimization)
- Minimal memory footprint
- Native Parquet support

**GPU Mode (RAPIDS cuDF):**

```python
def _process_gpu(self, files: List[Path], run_name: str):
    import dask_cudf
    ddf = dask_cudf.read_parquet([str(f) for f in files])
    
    # GPU-accelerated DataFrame operations
    # 3-5x faster than Polars CPU for large datasets
```

**Feature Engineering Pipeline:**

| Feature | Formula | Purpose |
|---------|---------|---------|
| `amt_log` | log(amt + 1) | Normalize skewed amount distribution |
| `hour_of_day` | (unix_time / 3600) % 24 | Detect time-of-day patterns |
| `day_of_week` | (unix_time / 86400) % 7 | Weekend vs weekday fraud |
| `is_weekend` | day_of_week >= 5 | Binary weekend flag |
| `is_night` | hour ∈ [22, 6] | Night transactions (higher fraud) |
| `distance_km` | haversine(lat, long, merch_lat, merch_long) | Unusual distance = fraud |

**Continuous Mode:**
```python
def run_continuous(self):
    while not STOP_FLAG:
        messages = self.queue_service.consume_batch(
            QueueTopics.RAW_TRANSACTIONS,
            batch_size=10000,
            timeout=1.0
        )
        df = pl.DataFrame(messages)
        df = self._apply_features(df)
        self.queue_service.publish_batch(QueueTopics.FEATURES_READY, df.to_dicts())
```

**Performance:**
- CPU (Polars): 30-50K rows/sec
- GPU (cuDF): 100-200K rows/sec
- Memory: 2-4 GB RAM (CPU), 4-8 GB VRAM (GPU)

---

### 3. Model Build (Pod 3)

**File:** `pods/model-build/train.py`

**Purpose:** Train XGBoost fraud detection models continuously

**Model Architecture:**
```python
XGBClassifier(
    n_estimators=100,        # 100 decision trees
    max_depth=6,             # Tree depth
    learning_rate=0.1,       # Step shrinkage
    scale_pos_weight=199,    # Handle 0.5% fraud imbalance (199:1 ratio)
    tree_method='gpu_hist',  # GPU acceleration (or 'hist' for CPU)
    gpu_id=0,
    eval_metric='auc',
    random_state=42
)
```

**Training Workflow:**

```python
def run_continuous(self):
    while not STOP_FLAG:
        # 1. Check system priority
        if not self.should_train_now():
            time.sleep(30)
            continue
        
        # 2. Load recent features
        files = self.get_recent_feature_files(max_files=100)
        df = pl.read_parquet(files)
        
        # 3. Prepare data
        X_train, X_test, y_train, y_test = self.prepare_data(df)
        
        # 4. Train model
        model = self.train(X_train, y_train, X_test, y_test)
        
        # 5. Evaluate
        metrics = self.evaluate(model, X_test, y_test)
        
        # 6. Save model (versioned)
        self.save_model(model, feature_names, version=None)
        
        # 7. Sleep before next training cycle
        time.sleep(300)  # Retrain every 5 minutes
```

**Priority System:**
```python
def should_train_now(self):
    priority = self.check_system_priority()  # Calls backend API
    if priority == "inference":
        return False  # Pause training, give GPU to inference
    elif priority == "training":
        return True   # Prioritize training
    else:  # balanced
        return True   # Train during idle periods
```

**Model Versioning:**
```python
def save_model(self, model, feature_names, version=None):
    if version is None:
        existing = list(self.output_path.glob("fraud_model_v*.json"))
        version = len(existing) + 1
    
    model_file = self.output_path / f"fraud_model_v{version:03d}.json"
    model.save_model(model_file)
    
    # Also save Triton-compatible format
    triton_dir = self.output_path / f"fraud_model_v{version:03d}" / "1"
    triton_dir.mkdir(parents=True, exist_ok=True)
    model.save_model(triton_dir / "model.xgb")
```

**GPU vs CPU Training:**

| Metric | CPU (XGBoost hist) | GPU (XGBoost gpu_hist) |
|--------|-------------------|------------------------|
| 500K rows | ~60 seconds | ~6 seconds |
| 5M rows | ~10 minutes | ~60 seconds |
| Memory | 4-8 GB RAM | 2-4 GB VRAM |

**When Training Happens:**
- Continuously in background (if priority allows)
- Triggered by: New features available OR scheduled interval
- Paused when: System priority = "inference"

---

### 4. Inference (Pod 4)

**File:** `pods/inference/client.py`

**Purpose:** Real-time fraud scoring using trained models

**Two Inference Paths:**

#### GPU Path (with Triton Inference Server):

```python
def run_triton_inference(triton_client, model_name, input_data):
    # 1. Prepare input tensor
    input_tensor = httpclient.InferInput("input", input_data.shape, "FP32")
    input_tensor.set_data_from_numpy(input_data)
    
    # 2. Request inference from Triton
    result = triton_client.infer(
        model_name=model_name,
        inputs=[input_tensor],
        outputs=[httpclient.InferRequestedOutput("output")]
    )
    
    # 3. Extract predictions
    predictions = result.as_numpy("output")
    return predictions[:, 1]  # Probability of fraud
```

**Why Triton?**
- Batches multiple requests for GPU efficiency
- Hot-reload models without restart
- Optimized for NVIDIA GPUs
- REST + gRPC API

#### CPU Path (Native XGBoost):

```python
def run_cpu_inference(xgb_model, input_array):
    # Direct XGBoost prediction on CPU
    dmatrix = xgb.DMatrix(input_array)
    predictions = xgb_model.predict(dmatrix)
    return predictions
```

**Continuous Inference Loop:**

```python
def run_continuous_inference(triton_client, cpu_model, model_name, batch_size, queue_service):
    while not STOP_FLAG:
        # 1. Consume features from queue
        messages = queue_service.consume_batch(
            QueueTopics.FEATURES_READY,
            batch_size=batch_size,
            timeout=1.0
        )
        
        # 2. Convert to NumPy array
        X = np.array([[msg[col] for col in FEATURE_COLUMNS] for msg in messages])
        
        # 3. Run inference (GPU or CPU)
        if triton_client:
            predictions = run_triton_inference(triton_client, model_name, X)
        else:
            predictions = run_cpu_inference(cpu_model, X)
        
        # 4. Calculate metrics
        fraud_count = (predictions > 0.5).sum()
        low_risk = (predictions < 0.3).sum()
        high_risk = (predictions > 0.7).sum()
        
        # 5. Update global metrics
        queue_service.increment_metric("fraud_dist_low", low_risk)
        queue_service.increment_metric("fraud_dist_high", high_risk)
        queue_service.increment_metric("total_fraud_blocked", fraud_count)
        
        # 6. Publish results
        results = [{**msg, "fraud_score": float(pred)} for msg, pred in zip(messages, predictions)]
        queue_service.publish_batch(QueueTopics.INFERENCE_RESULTS, results)
```

**Performance:**
- CPU: 5-10K predictions/sec
- GPU (Triton): 30-50K predictions/sec
- Latency: <10ms per batch (GPU), <50ms (CPU)

**Metrics Generated:**
- Fraud distribution (low/medium/high risk)
- Total fraud blocked
- Throughput (predictions/sec)
- Average fraud score

---

## GPU vs CPU Architecture

### Deployment Modes

#### Mode 1: CPU-Only (cpu-local-ssd.yaml)

```yaml
Deployments:
  - data-gather (CPU)
  - preprocessing-cpu (Polars)
  - inference-cpu (XGBoost CPU)

Storage:
  - Local PV (hostPath): /mnt/data/fraud-det-v3
  - Single volume (no GPU volume needed)

Resources:
  - Total CPU: ~4 cores
  - Total RAM: ~8 GB
  - No GPU required
```

**When to Use:**
- Development/testing
- Budget-constrained environments
- Throughput < 10K rows/sec

#### Mode 2: GPU-Accelerated (gpu-flashblade.yaml)

```yaml
Deployments:
  - data-gather (CPU)
  - preprocessing-gpu (RAPIDS cuDF)
  - model-build (XGBoost GPU)
  - inference-gpu (Triton + GPU)

Storage:
  - FlashBlade PVC (pure-file StorageClass)
  - High-throughput shared storage

Resources:
  - Total CPU: ~8 cores
  - Total RAM: ~32 GB
  - GPUs: 3 NVIDIA GPUs (1 per preprocessing/training/inference)
```

**When to Use:**
- Production with high throughput (>50K rows/sec)
- Need for fast model training
- Real-time inference at scale

### GPU Usage Details

#### Where CUDA is Used:

1. **Preprocessing (preprocessing-gpu)**
   ```python
   import cudf  # GPU DataFrame library
   df = cudf.read_parquet(...)  # Loads data to GPU memory
   df['amt_log'] = cudf.log1p(df['amt'])  # GPU-accelerated operation
   ```
   - CUDA Kernels: cuDF operations compiled to CUDA
   - Library: RAPIDS cuDF (built on CUDA primitives)
   - Benefit: 3-5x faster than CPU Polars

2. **Model Training (model-build)**
   ```python
   XGBClassifier(tree_method='gpu_hist', gpu_id=0)
   ```
   - CUDA Kernels: XGBoost's GPU histogram builder
   - Library: XGBoost with CUDA support
   - Benefit: 10-20x faster training

3. **Inference (inference-gpu with Triton)**
   ```python
   # Triton Inference Server runs XGBoost on GPU
   # Model loaded once to GPU memory
   # Batch predictions executed on GPU
   ```
   - CUDA Kernels: XGBoost prediction kernels
   - Library: Triton + XGBoost CUDA backend
   - Benefit: 5-10x faster inference

#### GPU Resource Allocation:

| Pod | GPU Request | GPU Limit | Purpose |
|-----|-------------|-----------|---------|
| preprocessing-gpu | 1 | 1 | cuDF operations |
| model-build | 1 | 1 | XGBoost training |
| inference-gpu | 1 | 1 | Triton inference |

#### How Kubernetes Selects GPU Nodes:

1. **Resource Request:**
   ```yaml
   resources:
     requests:
       nvidia.com/gpu: "1"
     limits:
       nvidia.com/gpu: "1"
   ```

2. **Scheduler Logic:**
   - Kubernetes finds nodes with label: `accelerator=nvidia-gpu`
   - Checks available GPU count via NVIDIA device plugin
   - Schedules pod only on nodes with free GPU

3. **GPU Pending Issues:**
   - **Cause:** No nodes with available GPUs
   - **Check:** `kubectl describe node <node-name> | grep nvidia.com/gpu`
   - **Fix:** Add GPU nodes or scale down other GPU pods

### File Size Differences (GPU vs CPU)

**Why GPU files are larger (17.7 GB vs CPU):**

1. **Different Storage Paths:**
   - CPU: `/mnt/cpu-fb/`
   - GPU: `/mnt/gpu-fb/`

2. **Data Volume Difference:**
   - GPU processes more data (higher throughput)
   - GPU volume accumulates faster due to 3-5x processing speed

3. **Not Inherent File Size:**
   - Parquet files themselves are the same format
   - Difference is in total accumulated data over time

---

## Kubernetes & Docker

### Namespace

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: fraud-det-v3
```

All resources deployed to `fraud-det-v3` namespace.

### Persistent Volumes

#### CPU Mode (Local SSD):

```yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: fraud-det-v3-local-pv
spec:
  storageClassName: local-storage
  capacity:
    storage: 100Gi
  accessModes:
    - ReadWriteOnce
  hostPath:
    path: "/mnt/data/fraud-det-v3"
    type: DirectoryOrCreate
```

- **Type:** Local hostPath
- **Location:** `/mnt/data/fraud-det-v3` on node
- **Access:** Single node only
- **Performance:** SSD speeds (~500 MB/s)

#### GPU Mode (FlashBlade):

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: fraud-det-v3-flashblade
  namespace: fraud-det-v3
spec:
  storageClassName: pure-file
  accessModes:
    - ReadWriteMany
  resources:
    requests:
      storage: 50Gi
```

- **Type:** FlashBlade (NFS-based)
- **Storage Class:** `pure-file` (provided by Pure Storage CSI driver)
- **Access:** Multi-node (ReadWriteMany)
- **Performance:** Up to 25 GB/s throughput

### Docker Images

| Image | Base | Size | Purpose |
|-------|------|------|---------|
| `fraud-det-v3/backend:latest` | python:3.11-slim | ~500 MB | FastAPI server |
| `fraud-det-v3/data-gather:latest` | python:3.11-slim | ~600 MB | Data generation |
| `fraud-det-v3/preprocessing-cpu:latest` | python:3.11-slim | ~800 MB | Polars preprocessing |
| `fraud-det-v3/preprocessing-gpu:latest` | nvidia/cuda:12.0-runtime | ~4 GB | RAPIDS cuDF |
| `fraud-det-v3/model-build:latest` | nvidia/cuda:12.0-runtime | ~3 GB | XGBoost GPU |
| `fraud-det-v3/inference-gpu:latest` | nvcr.io/nvidia/tritonserver | ~8 GB | Triton + XGBoost |

### Building Images

```bash
# Build all images
make build

# Build without cache
make build-no-cache

# Load into Kind cluster
make load-kind

# Load into Minikube
make load-minikube
```

### Pod Resource Requests/Limits

#### CPU Mode:

```yaml
resources:
  requests:
    cpu: "500m"      # 0.5 cores
    memory: "1Gi"
  limits:
    cpu: "2000m"     # 2 cores
    memory: "4Gi"
```

#### GPU Mode:

```yaml
resources:
  requests:
    cpu: "1000m"
    memory: "8Gi"
    nvidia.com/gpu: "1"
  limits:
    cpu: "4000m"
    memory: "32Gi"
    nvidia.com/gpu: "1"
```

### RBAC Configuration

Backend pod needs Kubernetes API access for scaling:

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: fraud-backend
  namespace: fraud-det-v3
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: fraud-backend-role
rules:
  - apiGroups: ["apps"]
    resources: ["deployments", "deployments/scale"]
    verbs: ["get", "list", "patch", "update"]
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "list", "patch"]
```

**Why Needed:**
- Backend executes `kubectl scale` commands
- Backend tails pod logs via `kubectl logs -f`
- Backend queries pod status

### GPU Pod Pending - Root Causes

**Check Pod Status:**
```bash
kubectl describe pod <pod-name> -n fraud-det-v3
```

**Common Issues:**

1. **No GPU Available:**
   ```
   Events:
     Warning  FailedScheduling  0/3 nodes are available: 
              3 Insufficient nvidia.com/gpu
   ```
   **Fix:** Add GPU node or scale down other GPU pods

2. **Node Selector Mismatch:**
   ```yaml
   nodeSelector:
     accelerator: nvidia-gpu
   ```
   **Fix:** Ensure nodes have this label

3. **Resource Limits Too High:**
   ```yaml
   limits:
     nvidia.com/gpu: "2"  # Requesting 2 GPUs
   ```
   **Fix:** Reduce to `"1"` if node only has 1 GPU

4. **Taints on GPU Nodes:**
   ```bash
   kubectl describe node gpu-node-1 | grep Taints
   ```
   **Fix:** Add tolerations in pod spec

---

## Performance & Optimization

### Why Inference Takes Longer on Repeated Calls

**Scenario:** First inference call is fast, subsequent calls within 1-2 seconds are slower.

**Root Cause Analysis:**

1. **Model Loading (First Call):**
   ```python
   # First call
   model = load_xgboost_model_cpu()  # Loads from disk (~500ms)
   predictions = model.predict(X)     # Fast (~50ms)
   
   # Model cached in memory
   ```

2. **Model Cache Invalidation:**
   - If new model trained, old model invalidated
   - Next call re-loads model from disk
   - **Delay:** ~500ms model load time

3. **Queue Backlog:**
   - Inference pod processes queue in order
   - If backlog exists, your request waits
   - **Delay:** Depends on backlog size

4. **GPU Memory:**
   - First call allocates GPU memory
   - Subsequent calls reuse allocation (faster)
   - **But:** If GPU OOM, must free memory first (slower)

**Solutions:**

#### 1. Model Caching Strategy

```python
# In inference/client.py
class ModelCache:
    def __init__(self):
        self.model = None
        self.model_version = None
        self.last_check = 0
    
    def get_model(self):
        # Check for new model every 60 seconds
        if time.time() - self.last_check > 60:
            latest_version = find_latest_model_version()
            if latest_version != self.model_version:
                self.model = load_xgboost_model_cpu()
                self.model_version = latest_version
            self.last_check = time.time()
        
        return self.model
```

#### 2. Warm-Up Inference

```python
# On pod startup
def warm_up():
    model = get_model()
    dummy_data = np.zeros((1000, len(FEATURE_COLUMNS)))
    _ = model.predict(dummy_data)  # Warm up GPU/CPU cache
```

#### 3. Batch Request Optimization

```python
# Instead of: 100 requests of 100 rows each
# Do: 1 request of 10,000 rows
batch_size = 10000  # Larger batches = better GPU utilization
```

### Latency Reduction Strategies

| Strategy | Latency Reduction | Complexity |
|----------|-------------------|------------|
| Model caching | -500ms | Low |
| Warm-up on startup | -200ms | Low |
| Increase batch size | -50ms | Medium |
| Use GPU inference | -300ms | High |
| Pre-load models in memory | -500ms | Medium |

### Blocking Operations to Avoid

1. **Disk I/O in Hot Path:**
   ```python
   # BAD: Loading model on every request
   def predict(X):
       model = load_model()  # Disk I/O!
       return model.predict(X)
   
   # GOOD: Load once, cache in memory
   model = load_model()  # Once at startup
   def predict(X):
       return model.predict(X)
   ```

2. **Synchronous Queue Operations:**
   ```python
   # BAD: Waiting for each message
   for _ in range(1000):
       msg = queue.consume(timeout=5)  # Blocks!
   
   # GOOD: Batch consume
   msgs = queue.consume_batch(batch_size=1000, timeout=1)
   ```

3. **Excessive Logging:**
   ```python
   # BAD: Log every transaction
   for txn in transactions:
       log(f"Processing {txn}")  # I/O overhead!
   
   # GOOD: Log batches
   log(f"Processing batch of {len(transactions)} transactions")
   ```

### Caching Strategy

**What is Cached:**
- ✅ Trained models (in memory)
- ✅ String pools (in data-gather)
- ✅ Queue metrics (FlashBlade .metrics.json)

**What is NOT Cached:**
- ❌ Raw transaction data (too large)
- ❌ Feature engineered data (archival only)
- ❌ Inference results (streamed to queue)

### Throughput Benchmarks

| Configuration | Throughput | Latency | Cost |
|---------------|------------|---------|------|
| 1 CPU pod each | 10K rows/sec | 100ms | $ |
| 2 CPU pods each | 20K rows/sec | 80ms | $$ |
| 1 GPU pod each | 50K rows/sec | 20ms | $$$ |
| 2 GPU pods each | 100K rows/sec | 15ms | $$$$ |

---

## Metrics & Monitoring

### Metrics Sources

#### 1. Pod Telemetry (Logged to stdout)

**Format:**
```
[TELEMETRY] stage=Inference | status=Running | rows=500000 | throughput=25000 | 
            elapsed=20.5 | cpu_cores=2.3 | ram_gb=4.5 | ram_percent=28.5 | fraud_blocked=2500
```

**Fields:**
- `stage`: Ingest, Data Prep, Model Train, Inference
- `status`: Running, Completed, Error
- `rows`: Total rows processed
- `throughput`: Rows/second
- `elapsed`: Seconds since start
- `cpu_cores`: CPU cores in use
- `ram_gb`: RAM used in GB
- `ram_percent`: Memory utilization %
- `fraud_blocked`: (Inference only) Fraud transactions detected

**How Backend Parses:**
```python
def parse_telemetry_line(line: str):
    if "[TELEMETRY]" not in line:
        return None
    
    data = {}
    parts = line.split("|")
    for part in parts:
        if "=" in part:
            key, value = part.split("=", 1)
            data[key.strip()] = value.strip()
    
    return {
        "stage": data.get("stage"),
        "rows": int(data.get("rows", 0)),
        "throughput": int(data.get("throughput", 0)),
        # ...
    }
```

#### 2. Queue Metrics (FlashBlade Files)

**Backlog Counts:**
```python
def get_backlog(topic: str) -> int:
    pending_dir = f"/mnt/flashblade/queue/{topic}/pending"
    return len(list(Path(pending_dir).glob("*.parquet")))
```

**Global Metrics (.metrics.json):**
```json
{
  "fraud_dist_low": 325000,
  "fraud_dist_medium": 125000,
  "fraud_dist_high": 50000,
  "total_fraud_blocked": 50000,
  "total_txns_scored": 500000
}
```

**Updated By:**
- Inference pod increments these atomically
- File-based locking for concurrent writes

#### 3. FlashBlade Metrics (Pure1 API)

**If PURE_SERVER=true:**
```python
# backend_server.py
if os.getenv("PURE_SERVER") == "true":
    from pure1_metrics import get_flashblade_performance
    fb_metrics = get_flashblade_performance()
    # Returns: read_bps, write_bps, iops, latency_ms
```

**Requires:**
- Pure1 API credentials
- FlashBlade Prometheus endpoint
- Network access to FlashBlade management

### Metrics Not Appearing - Troubleshooting

**Issue:** Dashboard shows 0 for fraud metrics

**Check 1: Are Inference Pods Running?**
```bash
kubectl get pods -n fraud-det-v3 -l app=inference-cpu
# Should show Running state
```

**Check 2: Are Metrics Being Written?**
```bash
kubectl exec -it deployment/inference-cpu -n fraud-det-v3 -- cat /mnt/flashblade/.metrics.json
# Should show non-zero values
```

**Check 3: Is Backend Reading Metrics?**
```bash
curl http://localhost:8000/api/dashboard | jq '.fraud_dist'
# Should show {"low": X, "medium": Y, "high": Z}
```

**Common Fixes:**

1. **Metrics File Permissions:**
   ```bash
   # Fix via cleanup job
   kubectl apply -f k8s_configs/cleanup-job.yaml
   ```

2. **Inference Not Running:**
   ```bash
   # Scale up inference
   kubectl scale deployment/inference-cpu --replicas=2 -n fraud-det-v3
   ```

3. **No Features Available:**
   ```bash
   # Check features queue
   kubectl exec -it deployment/preprocessing-cpu -n fraud-det-v3 -- \
     ls /mnt/flashblade/queue/features-ready/pending/ | wc -l
   # Should be > 0
   ```

### Metrics After Training

**Generated Metrics:**
```python
# In model-build/train.py
metrics = {
    "precision": precision_score(y_test, y_pred),
    "recall": recall_score(y_test, y_pred),
    "f1": f1_score(y_test, y_pred),
    "roc_auc": roc_auc_score(y_test, y_pred_proba),
    "confusion_matrix": confusion_matrix(y_test, y_pred).tolist(),
    "training_time": training_duration,
    "model_version": version,
    "timestamp": datetime.now().isoformat()
}

# Saved to:
/mnt/flashblade/models/fraud_model_v001_metrics.json
```

**Typical Values:**
- Precision: 0.85-0.95 (85-95% of fraud predictions are correct)
- Recall: 0.70-0.85 (70-85% of actual fraud detected)
- F1-Score: 0.75-0.90 (harmonic mean)
- ROC-AUC: 0.90-0.98 (model discrimination ability)

**Why Metrics Might Not Appear:**
- Training hasn't completed yet (check pod logs)
- JSON file write failed (permission issue)
- Model training errored (check logs for exceptions)

### Metrics After Inference

**Real-Time Metrics:**
- Updated in `.metrics.json` every batch (10K transactions)
- Accessible via backend API immediately
- Dashboard updates every 1 second

**Historical Metrics:**
- Stored in inference results Parquet files
- Can query with Polars/Pandas for analytics
- Not displayed in dashboard (real-time focus)

---

## Troubleshooting Guide

### Issue 1: Pods Stuck in Pending

**Symptom:**
```bash
kubectl get pods -n fraud-det-v3
NAME                              READY   STATUS    
preprocessing-gpu-xyz             0/1     Pending
```

**Diagnosis:**
```bash
kubectl describe pod preprocessing-gpu-xyz -n fraud-det-v3
Events:
  Warning  FailedScheduling  0/3 nodes available: 3 Insufficient nvidia.com/gpu
```

**Solution:**
- **Option A:** Scale down other GPU pods
- **Option B:** Add GPU node to cluster
- **Option C:** Switch to CPU deployment mode

### Issue 2: Permission Denied on Volumes

**Symptom:**
```
PermissionError: [Errno 13] Permission denied: '/mnt/flashblade/.metrics.json'
```

**Cause:** Files created by different user UID in previous run

**Solution:**
```bash
# Apply cleanup job
kubectl apply -f k8s_configs/cleanup-job.yaml

# Wait for completion
kubectl wait --for=condition=complete job/cleanup-job -n fraud-det-v3 --timeout=60s

# Delete cleanup job
kubectl delete -f k8s_configs/cleanup-job.yaml
```

### Issue 3: Dashboard Shows No Data

**Symptoms:**
- All metrics show 0
- Charts are empty
- Status shows "Idle"

**Diagnosis Steps:**

1. **Check if pipeline is started:**
   ```bash
   kubectl get pods -n fraud-det-v3
   # Should show Running pods
   ```

2. **Check backend logs:**
   ```bash
   kubectl logs deployment/backend -n fraud-det-v3
   # Should show "Started tailing logs for K8s pod: ..."
   ```

3. **Check pod telemetry:**
   ```bash
   kubectl logs deployment/data-gather -n fraud-det-v3 | grep TELEMETRY
   # Should show [TELEMETRY] lines
   ```

**Solutions:**

- Start pipeline: `curl -X POST http://localhost:8000/api/control/start`
- Restart backend: `kubectl rollout restart deployment/backend -n fraud-det-v3`
- Check browser console for JavaScript errors

### Issue 4: High Latency Between API Calls

**Already covered in [API Layer](#why-second-api-call-takes-time-1-2-seconds)**

### Issue 5: Inference Results Not Updating

**Symptom:** Fraud metrics frozen, not incrementing

**Check:**
```bash
# 1. Is inference running?
kubectl get pods -n fraud-det-v3 -l tier=inference

# 2. Are features available?
kubectl exec deployment/inference-cpu -n fraud-det-v3 -- \
  ls /mnt/flashblade/queue/features-ready/pending/ | wc -l

# 3. Check inference logs
kubectl logs deployment/inference-cpu -n fraud-det-v3 --tail=50
```

**Solutions:**
- No features: Check if data-prep is running
- Inference error: Check logs for exceptions
- Queue full: Increase inference replicas

### Issue 6: Out of Disk Space

**Symptom:**
```
OSError: [Errno 28] No space left on device
```

**Check:**
```bash
kubectl exec deployment/backend -n fraud-det-v3 -- df -h /mnt/flashblade
```

**Solution:**
```bash
# Clear old data via API
curl -X POST http://localhost:8000/api/control/reset-data

# Or manually clear
kubectl exec deployment/backend -n fraud-det-v3 -- \
  sh -c "rm -rf /mnt/flashblade/queue/*/completed/*"
```

---

## Architecture Summary

### Services

| Service | Type | Port | Purpose |
|---------|------|------|---------|
| backend | ClusterIP | 8000 | Dashboard API, orchestration |
| inference-gpu | ClusterIP | 8000, 8001, 8002 | Triton HTTP, gRPC, metrics |

### Pods

| Pod | Tier | Replicas | Auto-scaling | GPU |
|-----|------|----------|--------------|-----|
| data-gather | generation | 1-8 | Manual | No |
| preprocessing-cpu | preprocessing | 1-4 | Manual | No |
| preprocessing-gpu | preprocessing | 0-2 | Manual | Yes (1) |
| model-build | training | 0-2 | Manual | Yes (1) |
| inference-cpu | inference | 1-4 | Manual | No |
| inference-gpu | inference | 0-2 | Manual | Yes (1) |
| backend | api | 1 | No | No |

### Volumes

| Volume | Type | Access Mode | Size | Mount Path |
|--------|------|-------------|------|------------|
| fraud-det-v3-flashblade (GPU mode) | FlashBlade PVC | RWX | 50Gi | /mnt/flashblade |
| fraud-det-v3-local-pv (CPU mode) | Local hostPath | RWO | 100Gi | /mnt/flashblade |

### Data Flow Summary

```
User → Dashboard UI → Backend API → Kubernetes Pods → FlashBlade Queue → Processing Pipeline → Results → Dashboard
```

**Key Insight:** Everything flows through FlashBlade-based file queue, not traditional message queues (Kafka/RabbitMQ). This provides:
- ✅ High throughput (GB/s vs MB/s)
- ✅ Persistence (data survives restarts)
- ✅ Simplicity (no external dependencies)
- ❌ No ordering guarantees (file-based)
- ❌ No pub/sub (point-to-point only)

---

## Beginner-Friendly Summary

**What This System Does:**
Detects fraudulent credit card transactions in real-time at massive scale (50K+ per second).

**How It Works (Simple):**

1. **Generate Fake Transactions** (like Netflix generating test data)
2. **Clean the Data** (remove unnecessary info, calculate useful metrics)
3. **Train AI Model** (teach computer to spot fraud patterns)
4. **Score New Transactions** (AI predicts: fraud or legit?)
5. **Show Results on Dashboard** (beautiful charts and metrics)

**Why It's Fast:**
- Uses GPU (graphics cards) for AI calculations (10-20x faster than CPU)
- Uses FlashBlade storage (Ferrari of disk drives)
- Uses smart libraries (Polars, XGBoost, RAPIDS)

**Key Technologies Explained:**

| Technology | What It Is | Why We Use It |
|------------|-----------|---------------|
| Kubernetes | Container orchestrator | Runs our pods, scales automatically |
| FlashBlade | Super-fast storage | Handles 25 GB/s throughput |
| XGBoost | Machine learning algorithm | Best for fraud detection (decision trees) |
| Polars | Data processing library | 10x faster than Pandas |
| RAPIDS cuDF | GPU data processing | Makes Polars even faster with GPUs |
| Triton | AI model server | NVIDIA's optimized inference engine |
| FastAPI | Python web framework | Serves our dashboard API |

---

## Advanced Technical Summary

**Architecture Pattern:** Event-driven microservices with file-based queuing

**Key Design Decisions:**

1. **File Queue vs Message Queue:**
   - Chose FlashBlade file queue over Kafka/RabbitMQ
   - Reason: Higher throughput for batch ML workloads
   - Trade-off: Less real-time, no ordering guarantees

2. **Polars vs Pandas:**
   - Polars for CPU data processing
   - Reason: 10-20x faster, lazy execution, memory efficient
   - Trade-off: Smaller ecosystem, less familiar API

3. **XGBoost vs Neural Networks:**
   - XGBoost for fraud detection
   - Reason: Better for tabular data, faster training, interpretable
   - Trade-off: Not suitable for unstructured data (images, text)

4. **Triton vs Direct XGBoost:**
   - Triton for GPU inference
   - Reason: Batching, hot-reload, optimized for production
   - Trade-off: Added complexity, requires NVIDIA GPUs

5. **Continuous vs Batch Processing:**
   - Continuous streaming mode
   - Reason: Real-time fraud detection, always-on pipeline
   - Trade-off: More complex error handling, resource usage

**Performance Characteristics:**

- **Throughput:** 50K-100K rows/sec (GPU mode)
- **Latency:** 10-50ms per batch
- **Storage:** 25 GB/s FlashBlade throughput
- **Scalability:** Linear scaling with replicas (up to storage bottleneck)
- **Availability:** Kubernetes self-healing, no single point of failure

**Cost Considerations:**

| Resource | Monthly Cost (estimate) | % of Total |
|----------|------------------------|------------|
| 3x NVIDIA A100 GPUs | $3,000 | 60% |
| FlashBlade Storage | $1,500 | 30% |
| Kubernetes Cluster | $500 | 10% |
| **Total** | **$5,000** | **100%** |

**When to Use This Architecture:**
- ✅ High-throughput ML inference (>10K predictions/sec)
- ✅ Continuous training/retraining required
- ✅ Batch processing acceptable (not sub-millisecond latency)
- ✅ Budget for GPU infrastructure

**When NOT to Use:**
- ❌ Low throughput (<1K predictions/sec) → Use simple REST API
- ❌ Sub-millisecond latency required → Use in-memory caching
- ❌ Budget-constrained → Use CPU-only mode
- ❌ Small dataset (<1M rows) → Use single-machine solution

---

**End of Technical Documentation**

For questions or issues, check:
- README.md (quick start guide)
- Pod logs: `kubectl logs <pod-name> -n fraud-det-v3`
- Backend API: `curl http://localhost:8000/api/dashboard | jq .`
- GitHub Issues: (if applicable)
