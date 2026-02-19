# Running Backend Locally with Hybrid K8s Pipeline

This guide explains how to run the `backend_server.py` on your local Windows machine while the data-generation and preprocessing pods continue to run in your Kubernetes cluster. This is useful if the cluster nodes are under `DiskPressure` or if you need to debug the dashboard quickly.

## 📋 Prerequisites

1. **Python 3.9+** installed on your Windows machine.
2. **Kubectl** configured and connected to your cluster.
3. **Required Python Packages**:
   ```powershell
   pip install uvicorn fastapi pydantic kubernetes prometheus_client psutil requests
   ```

## 🚀 Execution Steps

### 1. Set Environment Variables
The backend needs to know where Prometheus is and how to talk to your cluster.

**In PowerShell:**
```powershell
$env:PROMETHEUS_URL = "http://10.23.181.153:9090"
$env:LOCAL_MODE = "true"  # Simulates K8s scaling commands if needed
```

### 2. Handle Storage Paths (Important)
The backend expects metrics in `/mnt/cpu-fb/.metrics.json`. Since you are running locally, it won't see the FlashBlade mount.

- The backend will automatically create a local `queue/` directory for simulation. 
- **Note**: You will see "Tech" metrics (Business/Latency) only if the `data-gather` pod is writing to a location your local machine can see, OR if you are using the **Prometheus** infra metrics which we've already configured to point to the master IP.

### 3. Start the Backend
```powershell
uvicorn backend_server.py:app --host 0.0.0.0 --port 8000 --reload
```

### 4. Access the Dashboard
1. Ensure the `backend` deployment in K8s is scaled to 0 (optional but recommended to avoid conflicts):
   ```powershell
   kubectl scale deployment backend -n fraud-det-v3 --replicas=0
   ```
2. Open `dashboard-v4-preview.html` in your browser.
3. It will connect to your local `http://localhost:8000` by default.

## 🔍 Hybrid Architecture

- **Backend (Local)**: Handles API requests, serves the dashboard, and fetches infra metrics from `10.23.181.153:9090`.
- **Prometheus (Master)**: Continues to scrape node `.44` and other cluster metrics.
- **Pods (K8s)**: `data-gather`, `preprocessing`, and `inference` continue running in the cluster.

If you don't see "Business" metrics, ensure the pods are running:
```powershell
kubectl get pods -n fraud-det-v3
```
