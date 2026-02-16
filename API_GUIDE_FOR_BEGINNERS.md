# 🚀 API Guide for Absolute Beginners

**Total APIs: 27 endpoints**

Think of APIs like **buttons on a remote control** for your fraud detection system. Each button does something specific!

---

## 📊 Table of Contents

1. [Main Dashboard APIs](#main-dashboard-apis) (2 APIs)
2. [Pipeline Control APIs](#pipeline-control-apis) (4 APIs)
3. [Scaling APIs](#scaling-apis) (7 APIs)
4. [System Configuration APIs](#system-configuration-apis) (6 APIs)
5. [Monitoring APIs](#monitoring-apis) (4 APIs)
6. [Business Metrics APIs](#business-metrics-apis) (2 APIs)
7. [Advanced APIs](#advanced-apis) (2 APIs)

---

## 🎯 Main Dashboard APIs

### 1. GET `/`
**What it does:** Says "Hello, I'm alive!"

**Think of it like:** Knocking on a door to see if anyone's home.

**Input:** Nothing (just visit the URL)

**Output:**
```json
{
  "status": "Dashboard Backend v4 Online",
  "version": "1.0.0"
}
```

**Data Travel:**
```
Your Browser → Backend Server → Returns a welcome message
```

**When to use:** To check if the backend server is running.

---

### 2. GET `/api/dashboard`
**What it does:** Gets ALL the current stats for the dashboard (the BIG ONE! 📈)

**Think of it like:** Opening a newspaper to see all today's news at once.

**Input:** Nothing

**Output:** (This is HUGE - all your dashboard data!)
```json
{
  "pipeline_progress": {
    "generated": 5000000,          ← How many transactions were created
    "data_prep_cpu": 2000000,      ← How many processed on CPU
    "data_prep_gpu": 3000000,      ← How many processed on GPU
    "inference_cpu": 1500000,      ← How many scored on CPU
    "inference_gpu": 3500000,      ← How many scored on GPU
    "backlog": 150000              ← How many waiting in queue
  },
  "utilization": {
    "gpu": 85,                     ← GPU is 85% busy
    "cpu": 72,                     ← CPU is 72% busy
    "flashblade": 45               ← Storage is 45% busy
  },
  "throughput": {
    "gpu": 35000,                  ← GPU processing 35K/second
    "cpu": 15000                   ← CPU processing 15K/second
  },
  "business": {
    "fraud_prevented": 125000,     ← Dollars saved from fraud!
    "txns_scored": 5000000,        ← Total transactions checked
    "fraud_blocked": 25000,        ← Fraudulent transactions caught
    "throughput": 50000            ← Processing 50K transactions/sec
  },
  "fraud_dist": {
    "low": 3250000,                ← Low-risk transactions
    "medium": 1250000,             ← Medium-risk transactions
    "high": 500000                 ← High-risk transactions
  },
  "status": {
    "live": true,                  ← Pipeline is running
    "elapsed": "05:23.4",          ← Running for 5 min 23 seconds
    "stage": "Inference",          ← Currently doing predictions
    "status": "Running"            ← Status: Running/Stopped/Error
  },
  "queue_backlogs": {
    "raw_transactions": 150000,    ← 150K transactions waiting to process
    "features_ready": 50000,       ← 50K features ready for AI
    "inference_results": 10000     ← 10K results waiting
  }
}
```

**Data Travel:**
```
Your Dashboard (every 1 second)
    ↓
Calls: GET /api/dashboard
    ↓
Backend Server:
    1. Reads telemetry from Pods (via Kubernetes logs)
    2. Reads queue backlogs (counts files on FlashBlade)
    3. Reads fraud metrics (from .metrics.json file)
    4. Calculates throughput, percentages, etc.
    5. Packages everything into JSON
    ↓
Returns to Dashboard
    ↓
Dashboard updates charts and numbers
```

**When to use:** Your dashboard calls this automatically every second to stay updated!

---

## ⚡ Pipeline Control APIs

These are like the START/STOP buttons on your TV remote!

### 3. POST `/api/control/start`
**What it does:** Starts the entire fraud detection pipeline! 🚀

**Think of it like:** Pressing the START button on a washing machine.

**Input:** Nothing (just click the button)

**Output:**
```json
{
  "success": true,
  "message": "Pipeline started (K8s pods scaled up)",
  "replicas": {
    "data-gather": 1,          ← Started 1 data generator
    "preprocessing-cpu": 1,    ← Started 1 data processor
    "inference-cpu": 2         ← Started 2 inference engines
  }
}
```

**Data Travel:**
```
You click "Start" on Dashboard
    ↓
Calls: POST /api/control/start
    ↓
Backend Server:
    1. Runs: kubectl scale deployment/data-gather --replicas=1
    2. Runs: kubectl scale deployment/preprocessing-cpu --replicas=1
    3. Runs: kubectl scale deployment/inference-cpu --replicas=2
    ↓
Kubernetes:
    1. Starts creating pods (takes 2-5 seconds)
    2. Pods begin running
    3. Pods start logging telemetry
    ↓
Returns success message
    ↓
Dashboard shows "Pipeline Running"
```

**What actually happens:**
1. **Data Gather Pod** wakes up → starts making fake credit card transactions
2. **Preprocessing Pod** wakes up → starts cleaning the data
3. **Inference Pod** wakes up → starts checking for fraud
4. They all start talking to each other through the queue!

---

### 4. POST `/api/control/stop`
**What it does:** Stops the entire pipeline! 🛑

**Think of it like:** Pressing STOP on a video player.

**Input:** Nothing

**Output:**
```json
{
  "success": true,
  "message": "Pipeline stopped"
}
```

**Data Travel:**
```
You click "Stop" on Dashboard
    ↓
Calls: POST /api/control/stop
    ↓
Backend Server:
    1. Runs: kubectl scale deployment/data-gather --replicas=0
    2. Runs: kubectl scale deployment/preprocessing-cpu --replicas=0
    3. Runs: kubectl scale deployment/inference-cpu --replicas=0
    ↓
Kubernetes:
    1. Tells all pods to shut down
    2. Pods save their state and exit
    ↓
Returns success
    ↓
Dashboard shows "Pipeline Stopped"
```

**What actually happens:**
- All workers stop generating data
- All processors finish current work and stop
- System goes quiet (but data is saved!)

---

### 5. POST `/api/control/reset`
**What it does:** Resets all the counters to zero (like resetting a stopwatch)

**Think of it like:** Resetting your car's trip odometer to 0.

**Input:** Nothing

**Output:**
```json
{
  "success": true,
  "message": "Pipeline reset"
}
```

**Data Travel:**
```
You click "Reset"
    ↓
Calls: POST /api/control/reset
    ↓
Backend Server:
    1. Sets all counters to 0
       - generated = 0
       - processed = 0
       - fraud_blocked = 0
       - etc.
    2. Resets timer to 00:00.0
    ↓
Returns success
    ↓
Dashboard shows all zeros
```

**When to use:** When you want to start fresh statistics without deleting actual data files.

---

### 6. POST `/api/control/reset-data`
**What it does:** **NUCLEAR OPTION** - Deletes ALL data and starts completely fresh! 💣

**Think of it like:** Factory reset on your phone.

**Input:** Nothing

**Output:**
```json
{
  "success": true,
  "message": "Data cleared and pipeline restarted",
  "cleanup_log": "Data cleared successfully"
}
```

**Data Travel:**
```
You click "Reset Data" (with confirmation!)
    ↓
Calls: POST /api/control/reset-data
    ↓
Backend Server:
    1. Scales all pods to 0 (stops everything)
    2. Waits 3 seconds for pods to stop
    3. Creates a cleanup pod in Kubernetes
    4. Cleanup pod runs: rm -rf /mnt/flashblade/queue/*
    5. Deletes ALL transaction data, features, results
    6. Resets all counters to 0
    7. Scales pods back up (restarts)
    ↓
Kubernetes:
    1. Deletes all files from FlashBlade
    2. Removes cleanup pod
    ↓
Returns success
    ↓
Pipeline starts fresh (like brand new install)
```

**⚠️ WARNING:** This deletes EVERYTHING! Use carefully!

---

## 📏 Scaling APIs

These control HOW MANY workers you have (like hiring more employees).

### 7. POST `/api/control/scale/generation`
**What it does:** Changes how many DATA GENERATORS are running

**Think of it like:** Hiring more people to make fake transactions.

**Input:**
```json
{
  "replicas": 3    ← I want 3 data generators!
}
```

**Output:**
```json
{
  "success": true,
  "deployment": "data-gather",
  "replicas": 3,
  "message": "Scaled to 3 replicas"
}
```

**Data Travel:**
```
You set slider to 3 on dashboard
    ↓
Calls: POST /api/control/scale/generation
Body: {"replicas": 3}
    ↓
Backend Server:
    1. Checks: Is 3 between min (1) and max (8)? ✓
    2. Runs: kubectl scale deployment/data-gather --replicas=3
    ↓
Kubernetes:
    1. Creates 2 more data-gather pods (you already had 1)
    2. Now you have 3 workers generating data
    ↓
Returns success
    ↓
Dashboard updates pod count to 3
```

**What this means:**
- Before: 1 worker making 25K transactions/sec
- After: 3 workers making 75K transactions/sec! 3x faster! 🚀

---

### 8. POST `/api/control/scale/preprocessing`
**What it does:** Scales CPU preprocessing workers

**Input:**
```json
{
  "replicas": 2
}
```

**Output:** Same format as above

**What it means:** More workers cleaning and preparing data faster.

---

### 9. POST `/api/control/scale/preprocessing-gpu`
**What it does:** Scales GPU preprocessing workers (MUCH faster!)

**Input:**
```json
{
  "replicas": 1    ← Usually just 1 because GPUs are powerful!
}
```

**Output:** Same format

**What it means:** Uses graphics card to process data 5x faster than CPU!

---

### 10. POST `/api/control/scale/training`
**What it does:** Scales AI model training workers

**Input:**
```json
{
  "replicas": 1    ← Usually just 1 at a time
}
```

**Output:** Same format

**What it means:** 
- 0 replicas = No training (just use existing model)
- 1 replica = Train new models as data comes in
- 2 replicas = Train 2 models in parallel (advanced!)

---

### 11. POST `/api/control/scale/inference`
**What it does:** Scales CPU fraud checkers (the ones that score transactions)

**Input:**
```json
{
  "replicas": 4    ← I want 4 fraud checkers!
}
```

**Output:** Same format

**What it means:**
- More checkers = Can check more transactions per second
- Good when you have a backlog of transactions to score

---

### 12. POST `/api/control/scale/inference-gpu`
**What it does:** Scales GPU fraud checkers (10x faster than CPU!)

**Input:**
```json
{
  "replicas": 1
}
```

**Output:** Same format

**What it means:** Uses GPU to check fraud 10x faster! But needs GPU hardware.

---

### 13. GET `/api/control/scale`
**What it does:** Shows current pod counts (how many workers of each type)

**Input:** Nothing

**Output:**
```json
{
  "is_running": true,
  "preprocessing_pods": 1,         ← 1 CPU preprocessor
  "training_pods": 1,              ← 1 trainer
  "inference_pods": 2,             ← 2 CPU fraud checkers
  "generation_pods": 1,            ← 1 data generator
  "preprocessing_gpu_pods": 0,     ← 0 GPU preprocessors
  "inference_gpu_pods": 1,         ← 1 GPU fraud checker
  "generation_rate": 50000         ← Generating 50K/sec
}
```

**Data Travel:**
```
Dashboard loads
    ↓
Calls: GET /api/control/scale
    ↓
Backend Server returns current pod counts
    ↓
Dashboard shows sliders at correct positions
```

---

## ⚙️ System Configuration APIs

### 14. POST `/api/control/priority`
**What it does:** Sets system priority (training vs inference)

**Think of it like:** Choosing between "charge your phone" or "use your phone" (can't do both at full speed with limited battery).

**Input:**
```json
{
  "priority": "inference"    ← Options: "training" | "inference" | "balanced"
}
```

**Output:**
```json
{
  "success": true,
  "priority": "inference",
  "message": "Priority set to inference"
}
```

**What each priority means:**

- **"training"**: Focus on training new AI models
  - Training gets GPU first
  - Inference might be slower
  - Use when improving the model is priority

- **"inference"**: Focus on checking transactions
  - Fraud checking gets GPU first
  - Training might pause
  - Use when you have tons of transactions to check NOW

- **"balanced"**: Split resources 50/50
  - Both training and inference share resources
  - Good for normal operations

**Data Travel:**
```
You select "Inference Priority"
    ↓
Calls: POST /api/control/priority
Body: {"priority": "inference"}
    ↓
Backend Server:
    1. Saves priority setting
    2. Training pods notice this
    3. Training pods pause or slow down
    4. Inference pods get more resources
    ↓
Returns success
```

---

### 15. GET `/api/control/priority`
**What it does:** Shows current priority setting

**Input:** Nothing

**Output:**
```json
{
  "priority": "balanced"
}
```

---

### 16. POST `/api/control/throttle`
**What it does:** Controls data generation speed (like a gas pedal 🚗)

**Think of it like:** Setting the speed limit for how fast data is created.

**Input:**
```json
{
  "rate": 10000    ← Generate 10,000 transactions per second
}
```

**Output:**
```json
{
  "success": true,
  "rate": 10000,
  "message": "Generation rate set to 10000 rows/sec"
}
```

**What this does:**
```
You set slider to 10,000
    ↓
Calls: POST /api/control/throttle
Body: {"rate": 10000}
    ↓
Backend Server:
    1. Tells data-gather pods: "Slow down to 10K/sec"
    2. Pods adjust their generation speed
    ↓
Data generation slows down
    ↓
Less backlog builds up
```

**When to use:**
- **Low rate (1K-10K):** Testing, saving resources
- **Medium rate (10K-50K):** Normal operations
- **High rate (50K-100K):** Stress testing, GPU mode

---

### 17. GET `/api/control/throttle`
**What it does:** Shows current generation rate

**Input:** Nothing

**Output:**
```json
{
  "rate": 50000
}
```

---

### 18. PATCH `/api/resources/{pod_key}`
**What it does:** Changes CPU/Memory limits for a specific pod type

**Think of it like:** Giving a worker more tools (CPU) or a bigger desk (RAM).

**Input:**
```json
{
  "cpu_limit": "4000m",      ← Give it 4 CPU cores
  "memory_limit": "8Gi"      ← Give it 8 GB RAM
}
```

**URL:** `/api/resources/preprocessing-cpu`

**Output:**
```json
{
  "success": true,
  "pod": "preprocessing-cpu",
  "message": "Resources updated"
}
```

**Data Travel:**
```
You adjust resource sliders
    ↓
Calls: PATCH /api/resources/preprocessing-cpu
Body: {"cpu_limit": "4000m", "memory_limit": "8Gi"}
    ↓
Backend Server:
    1. Runs: kubectl set resources deployment/preprocessing-cpu
       --limits=cpu=4000m,memory=8Gi
    2. Kubernetes restarts pods with new limits
    ↓
Pods restart with more resources
    ↓
Pods run faster with more CPU/RAM!
```

---

### 19. GET `/api/resources/bounds`
**What it does:** Shows min/max limits for resources

**Input:** Nothing

**Output:**
```json
{
  "cpu": {
    "min": "100m",     ← Minimum 0.1 cores
    "max": "8000m"     ← Maximum 8 cores
  },
  "memory": {
    "min": "256Mi",    ← Minimum 256 MB
    "max": "32Gi"      ← Maximum 32 GB
  }
}
```

**When to use:** Dashboard uses this to set slider limits.

---

## 📊 Monitoring APIs

### 20. GET `/api/backlog/status`
**What it does:** Shows how many transactions are waiting in each queue

**Think of it like:** Checking how many people are waiting in line at a store.

**Input:** Nothing

**Output:**
```json
{
  "raw_transactions": 150000,      ← 150K raw transactions waiting
  "features_ready": 50000,         ← 50K features waiting
  "inference_results": 10000,      ← 10K results waiting
  "training_queue": 5000           ← 5K waiting for training
}
```

**Data Travel:**
```
Dashboard polls every 5 seconds
    ↓
Calls: GET /api/backlog/status
    ↓
Backend Server:
    1. Goes to: /mnt/flashblade/queue/raw-transactions/pending/
    2. Counts files: ls | wc -l (150,000 files)
    3. Repeats for each queue
    ↓
Returns counts
    ↓
Dashboard shows: "⚠️ Backlog: 150K transactions"
```

**What the numbers mean:**
- **0-10K:** ✅ Healthy, no backlog
- **10K-100K:** ⚠️ Some backlog building up
- **100K+:** 🔴 Large backlog! Need more workers!

---

### 21. GET `/api/backlog/pressure`
**What it does:** Shows backlog as a percentage (0-100%)

**Think of it like:** A progress bar showing how full each queue is.

**Input:** Nothing

**Output:**
```json
{
  "raw_transactions": 75,      ← 75% full (getting close to limit!)
  "features_ready": 25,        ← 25% full (okay)
  "inference_results": 5,      ← 5% full (very good)
  "overall": 35                ← Overall system is 35% backed up
}
```

**Data Travel:**
```
Calls: GET /api/backlog/pressure
    ↓
Backend Server:
    1. Gets backlog counts: 150,000
    2. Divides by threshold: 150,000 / 200,000 = 75%
    3. Calculates for each queue
    ↓
Returns percentages
    ↓
Dashboard shows color-coded status:
    - Green (0-30%): ✅ Healthy
    - Yellow (30-70%): ⚠️ Warning
    - Red (70-100%): 🔴 Critical
```

---

### 22. GET `/api/business/metrics`
**What it does:** Shows business-focused metrics (money saved, fraud blocked, etc.)

**Think of it like:** Your executive dashboard - the metrics your boss cares about! 💰

**Input:** Nothing

**Output:**
```json
{
  "summary": {
    "total_transactions": 5000000,          ← 5 million transactions checked
    "fraud_transactions": 25000,            ← 25K were fraud!
    "fraud_rate_percent": 0.5,              ← 0.5% fraud rate
    "total_amount_protected_usd": 1250000,  ← Saved $1.25 MILLION! 💰
    "avg_transaction_amount": 50.00,        ← Average transaction: $50
    "fraud_amount_blocked_usd": 1250000     ← Blocked $1.25M in fraud
  },
  "performance": {
    "avg_processing_time_ms": 45,           ← Takes 45ms to check each transaction
    "throughput_per_second": 50000,         ← Processing 50K/second
    "uptime_seconds": 3600,                 ← Been running for 1 hour
    "model_version": "v023",                ← Using model version 23
    "model_accuracy": 0.94                  ← Model is 94% accurate
  },
  "cost_analysis": {
    "cost_per_transaction_usd": 0.0001,     ← Costs $0.0001 per check
    "total_cost_usd": 500,                  ← Total cost: $500
    "fraud_savings_usd": 1250000,           ← Savings: $1.25M
    "roi_multiplier": 2500                  ← ROI: 2500x! (Saved 2500x more than it cost!)
  },
  "risk_distribution": {
    "low_risk_count": 3250000,              ← 3.25M low-risk transactions
    "medium_risk_count": 1250000,           ← 1.25M medium-risk
    "high_risk_count": 500000,              ← 500K high-risk
    "low_risk_percent": 65,                 ← 65% are low risk
    "medium_risk_percent": 25,              ← 25% medium
    "high_risk_percent": 10                 ← 10% high risk
  },
  "alerts": {
    "critical_alerts": 3,                   ← 3 critical issues
    "warnings": 12,                         ← 12 warnings
    "info": 45                              ← 45 info messages
  }
}
```

**Data Travel:**
```
Your boss opens dashboard
    ↓
Calls: GET /api/business/metrics
    ↓
Backend Server:
    1. Reads from: /mnt/flashblade/.metrics.json
       {
         "total_fraud_blocked": 25000,
         "fraud_dist_low": 3250000,
         ...
       }
    2. Calculates business metrics:
       - Fraud rate: 25000 / 5000000 = 0.5%
       - Money saved: 25000 × $50 = $1.25M
       - ROI: 1,250,000 / 500 = 2500x
    3. Packages into business-friendly format
    ↓
Returns metrics
    ↓
Dashboard shows:
    "💰 Saved $1.25M from fraud!"
    "🎯 94% accuracy"
    "⚡ 50K transactions/sec"
```

**When to use:** Show this to executives and managers!

---

### 23. GET `/api/machine/metrics`
**What it does:** Shows technical/machine metrics (CPU, GPU, storage, etc.)

**Think of it like:** Looking under the hood of your car - technical details for engineers! 🔧

**Input:** Nothing

**Output:**
```json
{
  "compute": {
    "cpu_utilization_percent": 72,          ← CPUs are 72% busy
    "cpu_cores_used": 5.8,                  ← Using 5.8 cores
    "cpu_cores_total": 8,                   ← Have 8 cores total
    "gpu_utilization_percent": 85,          ← GPUs are 85% busy
    "gpu_memory_used_gb": 6.4,              ← Using 6.4 GB GPU memory
    "gpu_memory_total_gb": 8,               ← Have 8 GB total
    "ram_used_gb": 24.5,                    ← Using 24.5 GB RAM
    "ram_total_gb": 32,                     ← Have 32 GB RAM
    "ram_percent": 76                       ← RAM is 76% full
  },
  "storage": {
    "flashblade_read_mbps": 12000,          ← Reading at 12 GB/sec
    "flashblade_write_mbps": 18000,         ← Writing at 18 GB/sec
    "flashblade_iops": 250000,              ← 250K operations/sec
    "flashblade_latency_ms": 0.5,           ← 0.5ms latency (super fast!)
    "flashblade_utilization_percent": 45,   ← FlashBlade is 45% busy
    "total_storage_used_gb": 120,           ← Using 120 GB
    "total_storage_available_gb": 50000     ← Have 50 TB available
  },
  "network": {
    "bandwidth_in_mbps": 8500,              ← 8.5 Gbps incoming
    "bandwidth_out_mbps": 9200,             ← 9.2 Gbps outgoing
    "total_data_transferred_gb": 450        ← Transferred 450 GB so far
  },
  "kubernetes": {
    "total_pods": 7,                        ← 7 pods running
    "running_pods": 6,                      ← 6 are running
    "pending_pods": 1,                      ← 1 is starting up
    "failed_pods": 0,                       ← 0 failed (good!)
    "nodes": 3,                             ← 3 Kubernetes nodes
    "nodes_ready": 3                        ← All 3 are ready
  },
  "performance": {
    "avg_inference_latency_ms": 12,         ← Takes 12ms to score
    "p95_inference_latency_ms": 25,         ← 95% are under 25ms
    "p99_inference_latency_ms": 45,         ← 99% are under 45ms
    "avg_preprocessing_latency_ms": 35,     ← Takes 35ms to prepare data
    "model_load_time_ms": 450               ← Takes 450ms to load model
  }
}
```

**Data Travel:**
```
Engineer opens monitoring dashboard
    ↓
Calls: GET /api/machine/metrics
    ↓
Backend Server:
    1. Queries Kubernetes:
       kubectl top pods -n fraud-det-v3
       → Gets CPU/RAM usage
    
    2. Queries FlashBlade (if PURE_SERVER=true):
       → Gets throughput, IOPS, latency
    
    3. Reads pod telemetry logs:
       → Gets inference latency
    
    4. Combines all data
    ↓
Returns technical metrics
    ↓
Dashboard shows detailed graphs and charts
```

**When to use:** For DevOps, SREs, and engineers troubleshooting performance!

---

## 🌐 Advanced APIs

### 24. GET `/dashboard-v4-preview.html`
**What it does:** Serves the actual HTML dashboard file

**Input:** Nothing

**Output:** The entire dashboard HTML page

**Data Travel:**
```
You visit: http://localhost:8000/dashboard-v4-preview.html
    ↓
Backend Server:
    1. Reads: dashboard-v4-preview.html file
    2. Sends the HTML to your browser
    ↓
Your browser:
    1. Renders the HTML
    2. Starts calling other APIs to get data
```

---

### 25. WebSocket `/data/dashboard`
**What it does:** **Real-time streaming** connection for live dashboard updates! 🔴 LIVE

**Think of it like:** Instead of you asking "any updates?" every second, the server PUSHES updates to you the moment they happen!

**How it's different from regular APIs:**
- **Regular API (GET):** You ask, server answers. Repeat every second.
- **WebSocket:** You connect ONCE, server sends updates continuously.

**Connection Flow:**
```
Dashboard loads
    ↓
Opens WebSocket: ws://localhost:8000/data/dashboard
    ↓
Backend Server:
    1. Accepts connection
    2. Every 1 second, automatically sends:
       {
         "pipeline_progress": {...},
         "utilization": {...},
         "throughput": {...},
         ...
       }
    ↓
Dashboard receives updates
    ↓
Charts update smoothly in real-time!
```

**Advantages:**
- ✅ Faster (no need to make new request each time)
- ✅ Lower bandwidth (connection stays open)
- ✅ Smoother updates (no polling delay)

**When to use:** The dashboard uses this automatically for smooth, live updates!

---

## 🎓 Summary Table

| # | API | Type | What It Does | Who Uses It |
|---|-----|------|--------------|-------------|
| 1 | `/` | GET | Health check | Monitoring systems |
| 2 | `/api/dashboard` | GET | Get all dashboard data | Dashboard (every 1 sec) |
| 3 | `/api/control/start` | POST | Start pipeline | User clicks "Start" |
| 4 | `/api/control/stop` | POST | Stop pipeline | User clicks "Stop" |
| 5 | `/api/control/reset` | POST | Reset counters | User clicks "Reset" |
| 6 | `/api/control/reset-data` | POST | Delete all data | Admin (careful!) |
| 7 | `/api/control/scale/generation` | POST | Scale data generators | User adjusts slider |
| 8 | `/api/control/scale/preprocessing` | POST | Scale preprocessors | User adjusts slider |
| 9 | `/api/control/scale/preprocessing-gpu` | POST | Scale GPU preprocessors | User adjusts slider |
| 10 | `/api/control/scale/training` | POST | Scale trainers | User adjusts slider |
| 11 | `/api/control/scale/inference` | POST | Scale fraud checkers | User adjusts slider |
| 12 | `/api/control/scale/inference-gpu` | POST | Scale GPU checkers | User adjusts slider |
| 13 | `/api/control/scale` | GET | Get current pod counts | Dashboard on load |
| 14 | `/api/control/priority` | POST | Set training vs inference | User selects priority |
| 15 | `/api/control/priority` | GET | Get current priority | Dashboard |
| 16 | `/api/control/throttle` | POST | Set generation speed | User adjusts speed |
| 17 | `/api/control/throttle` | GET | Get current speed | Dashboard |
| 18 | `/api/resources/{pod}` | PATCH | Change pod CPU/RAM | Advanced users |
| 19 | `/api/resources/bounds` | GET | Get resource limits | Dashboard |
| 20 | `/api/backlog/status` | GET | Get queue sizes | Dashboard (monitoring) |
| 21 | `/api/backlog/pressure` | GET | Get queue pressure % | Dashboard (alerts) |
| 22 | `/api/business/metrics` | GET | Business metrics | Managers/Executives |
| 23 | `/api/machine/metrics` | GET | Technical metrics | Engineers/DevOps |
| 24 | `/dashboard-v4-preview.html` | GET | Serve dashboard HTML | Your browser |
| 25 | `/data/dashboard` | WebSocket | Live data streaming | Dashboard (advanced) |

---

## 🔄 Complete Data Flow Example

Let's trace what happens when you **start the pipeline and watch the dashboard**:

```
1. You open browser → http://localhost:8000/dashboard-v4-preview.html
   ↓
2. Browser: GET /dashboard-v4-preview.html
   Backend: Sends HTML file
   ↓
3. Dashboard loads JavaScript
   ↓
4. Dashboard: GET /api/control/scale
   Backend: {"is_running": false, "generation_pods": 0, ...}
   Dashboard: Shows "Pipeline Stopped"
   ↓
5. You click "START" button
   ↓
6. Dashboard: POST /api/control/start
   Backend:
   - Runs: kubectl scale deployment/data-gather --replicas=1
   - Runs: kubectl scale deployment/preprocessing-cpu --replicas=1
   - Runs: kubectl scale deployment/inference-cpu --replicas=2
   - Returns: {"success": true, "message": "Pipeline started"}
   ↓
7. Kubernetes: Starting pods... (takes 2-5 seconds)
   ↓
8. Pods start running:
   - data-gather: Starts making fake credit card transactions
   - preprocessing-cpu: Starts processing them
   - inference-cpu: Starts checking for fraud
   ↓
9. Pods log telemetry to stdout:
   [TELEMETRY] stage=Ingest | rows=50000 | throughput=25000 | ...
   ↓
10. Backend: Tails pod logs via kubectl
    Parses [TELEMETRY] lines
    Updates state.telemetry{}
    ↓
11. Dashboard: GET /api/dashboard (every 1 second)
    Backend: Returns current stats
    Dashboard: Updates charts!
    ↓
12. You see numbers going up! 📈
    - Generated: 50,000 → 100,000 → 150,000...
    - Fraud Blocked: 250 → 500 → 750...
    - Throughput: 25,000/sec
    ↓
13. You adjust slider: "I want 3 data generators!"
    ↓
14. Dashboard: POST /api/control/scale/generation
    Body: {"replicas": 3}
    Backend: kubectl scale deployment/data-gather --replicas=3
    ↓
15. Kubernetes: Creates 2 more pods
    Now you have 3x data generators!
    ↓
16. Dashboard: GET /api/dashboard
    Backend: {"throughput": 75000}  ← 3x faster now!
    Dashboard: Shows 75K/sec! 🚀
    ↓
17. Pipeline runs continuously...
    Data keeps flowing through the system!
```

---

## 💡 Pro Tips

### For Beginners:
1. **Start simple:** Just use `/api/control/start` and `/api/dashboard`
2. **Watch the dashboard:** It calls all the APIs for you automatically!
3. **Don't worry about the advanced APIs** until you need them

### For Power Users:
1. Use WebSocket for smoother updates
2. Use `/api/business/metrics` for reporting
3. Use `/api/machine/metrics` for debugging
4. Use scaling APIs to optimize performance

### Common Workflows:

**Starting a new demo:**
```bash
1. POST /api/control/reset-data   # Clear old data
2. POST /api/control/start         # Start pipeline
3. GET /api/dashboard              # Watch it run!
```

**Scaling for performance:**
```bash
1. GET /api/backlog/pressure       # Check if backlog
2. POST /api/control/scale/inference {"replicas": 4}  # Add workers
3. GET /api/dashboard              # Verify throughput increased
```

**Getting metrics for report:**
```bash
1. GET /api/business/metrics       # Business numbers
2. GET /api/machine/metrics        # Technical details
3. Export to Excel for presentation!
```

---

## ❓ FAQ

**Q: Which API is called most often?**  
A: `/api/dashboard` - the dashboard calls it every 1 second!

**Q: Which API is most dangerous?**  
A: `/api/control/reset-data` - it deletes EVERYTHING!

**Q: Can I call these APIs from code?**  
A: Yes! Use curl, Python requests, JavaScript fetch, etc.

**Q: Do I need authentication?**  
A: Not in the current version (it's for internal use). Production would add auth!

**Q: What if an API call fails?**  
A: You'll get: `{"success": false, "error": "reason"}`

**Q: Can I call multiple APIs at once?**  
A: Yes! They're independent. Fire away!

---

**That's all 25+ APIs explained! 🎉**

Now you know how every button on your fraud detection remote control works! 🎮
