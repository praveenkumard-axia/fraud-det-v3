# Fraud Detection v3: Real-Time Pipeline on FlashBlade

![Python](https://img.shields.io/badge/Python-3.9+-blue?logo=python)
![Kubernetes](https://img.shields.io/badge/Kubernetes-v1.30+-blue?logo=kubernetes)
![Prometheus](https://img.shields.io/badge/Prometheus-Monitoring-orange?logo=prometheus)
![NVIDIA](https://img.shields.io/badge/NVIDIA-GPU_Accelerated-76B900?logo=nvidia)
![Pure Storage](https://img.shields.io/badge/Pure_Storage-FlashBlade-orange)

A high-performance, real-time fraud detection pipeline designed for Kubernetes, utilizing **NVIDIA GPUs** for accelerated inference/training and **Pure Storage FlashBlade** for high-throughput dual-volume storage.

---

## 🏗️ Infrastructure Architecture

The project implements a scale-out architecture where data flows through a sequence of specialized pods, coordinated via a file-based queuing system on FlashBlade.

```mermaid
graph TD
    subgraph "Kubernetes Cluster (fraud-det-v3)"
        DG[Data Gather Pod]
        PC[Preprocessing CPU]
        PG[Preprocessing GPU]
        IC[Inference CPU]
        IG[Inference GPU]
        OS[One-Shot Pipeline Job]
        BE[Backend Server]
    end

    subgraph "FlashBlade Storage"
        CV[("/mnt/cpu-fb (CPU Volume)") ]
        GV[("/mnt/gpu-fb (GPU Volume)") ]
    end

    DG -->|Writes Raw| CV
    DG -->|Writes Raw| GV
    
    CV -->|Read/Write| PC
    GV -->|Read/Write| PG
    
    PC -->|Features| CV
    PG -->|Features| GV
    
    CV -->|Predict| IC
    GV -->|Predict| IG
    
    OS -->|Orchestrates| DG
    OS -->|Orchestrates| PG
    
    BE -->|Monitors| DG & PC & PG & IC & IG
    BE -->|Polls| CV & GV
```

---

## 📦 Pod Catalog

### 1. Data Generation (`data-gather`)
- **Role**: Synthetic transaction generator.
- **Config**: [dual-flashblade.yaml](file:///Users/praveenkumar/Downloads/fraud-det-v3/k8s_configs/dual-flashblade.yaml#L102-169)
- **Volumes**: Mounts both CPU and GPU volumes for multi-archiving.
- **Continuous Mode**: Supported via `CONTINUOUS_MODE=true`.

### 2. Preprocessing (`preprocessing-cpu/gpu`)
- **CPU Path**: Standard feature engineering using Polars.
- **GPU Path**: High-performance RAPIDS-based preprocessing (cuDF).
- **Isolation**: Each pod is pinned to its respective volume (`/mnt/cpu-fb` vs `/mnt/gpu-fb`).

### 3. Model Hosting (`inference-cpu/gpu`)
- **CPU Inference**: Scalable XGBoost CPU prediction.
- **GPU Inference**: Triton Inference Server (integrated) for sub-millisecond scoring.
- **Service**: Exposed via `inference-gpu` service on ports `8000` (HTTP) and `8001` (gRPC).

### 4. Batch Execution (`one-shot-pipeline`)
- **Kind**: K8s Job.
- **Config**: [model.yaml](file:///Users/praveenkumar/Downloads/fraud-det-v3/k8s_configs/model.yaml)
- **Operation**: Sequences Data Ingest -> Prep -> Training in a single non-continuous run.

---

## 📊 Monitoring & Metrics

The system uses `prometheus_metrics.py` to bridge FlashBlade and K8s telemetry to the dashboard.

### Prometheus Queries
| Metric | Query |
| :--- | :--- |
| **FB Read BW** | `sum(purefb_file_systems_performance_bandwidth_bytes{dimension="read_bytes_per_sec"}) / 1024 / 1024` |
| **FB Write BW** | `sum(purefb_file_systems_performance_bandwidth_bytes{dimension="write_bytes_per_sec"}) / 1024 / 1024` |
| **FB IOPS** | `sum(purefb_file_systems_performance_throughput_iops)` |
| **FB Latency** | `avg(purefb_file_systems_performance_latency_usec) / 1000` |
| **GPU Util** | `avg(DCGM_FI_DEV_GPU_UTIL)` |
| **Pod CPU** | `sum(rate(container_cpu_usage_seconds_total{namespace='fraud-det-v3'}[1m])) * 1000` |

---

## ⚙️ Setup & Execution

### 1. Environment Configuration (`.env`)
Create a `.env` file in the root directory:

```env
# Infrastructure
PROMETHEUS_URL=http://10.23.181.153:9090
CONFIG_MODE=dual  # cpu, gpu, or dual

# Storage Paths (Overrides)
CPU_VOLUME_PATH=/mnt/cpu-fb
GPU_VOLUME_PATH=/mnt/gpu-fb

# System Settings
GENERATION_RATE=100000
SYSTEM_PRIORITY=balanced
PURE_SERVER=true  # Enables FlashBlade-specific metrics
```

### 2. Running the Backend
The backend server provides the API and serves the dashboard UI.

```bash
# Install dependencies
pip install -r requirements.txt

# Start the server
python backend_server.py
```
Access the dashboard at `http://localhost:8000/dashboard-v4-preview.html`.

### 3. Building & Tagging Images
The project uses a unified build script to manage multiple components and architectures.

#### Build Commands
```bash
# Build all images using the script
chmod +x build-images.sh
./build-images.sh

# Or use the Makefile (if configured)
make build
```

#### Tagging Strategy
Images are tagged based on their optimized architecture and role:
-   **:latest**: Used for universal or GPU-optimized components (e.g., `inference:latest` for Triton GPU).
-   **:cpu**: Specific images for CPU-bound execution (e.g., `data-prep:cpu`, `inference:cpu`).
-   **:gpu**: Specific images for GPU-accelerated execution (e.g., `data-prep:gpu`, `model-build:gpu`).

#### Image List
| Component | Image Name | Arch |
| :--- | :--- | :--- |
| **Backend** | `fraud-det-v3-dockerfile.backend:latest` | CPU |
| **Data Gather** | `fraud-det-v3-data-gather:latest` | CPU |
| **Data Prep** | `fraud-det-v3-data-prep:cpu` / `:gpu` | Multi |
| **Model Build** | `fraud-det-v3-model-build:gpu` | GPU |
| **Inference** | `fraud-det-v3-inference:cpu` / `:latest` (GPU) | Multi |

### 4. Kubernetes Deployment
```bash
# Apply RBAC and Service Accounts
kubectl apply -f k8s_configs/prometheus-rbac.yaml -> one time to make your k8s communicate with prometheus

# Deploy Dual-Volume Storage and Pods
kubectl apply -f k8s_configs/dual-flashblade.yaml -> (this will me automatically run by the `backend_Server.py`)

# Run a one-shot training job
kubectl apply -f k8s_configs/model.yaml -> one time to train your model
```

---

## 🛠️ Security & Access
- **RBAC**: The backend requires `fraud-backend-role` to scale pods and `fraud-backend-nodes` to view node status.
- **Monitoring**: Prometheus scraper requires `prometheus-scraper-role` in the `monitoring` namespace.
