# Metrics Integration Guide: High-Performance Hardware Analytics

This document outlines the current state of metrics collection in the Fraud Detection Platform and provides a detailed plan for integrating advanced FlashArray IOPS and CPU telemetry based on live Grafana data.

## 1. Current State (Node & Pod Level)

Our existing implementation (`prometheus_metrics.py`) focuses on **Node Exporter** and **cAdvisor** data:

| Metric Group | Data Source | Metrics Collected |
| :--- | :--- | :--- |
| **Storage (NFS)** | Node Exporter | Throughput (MB/s) for NFS mounts on `.44`. |
| **Compute (Node)** | Node Exporter | Aggregated CPU and RAM utilization for the node. |
| **GPU (NVIDIA)** | NVIDIA Smi Exporter | GPU utilization percentage (via `nvidia_smi_utilization_gpu_ratio`). |
| **Pods (Workload)** | cAdvisor | K8s namespace-level CPU (millicores) and RAM (MiB) totals. |

> [!NOTE]
> We currently use NFS metrics as a proxy for FlashBlade throughput since both CPU and GPU pods mount FlashBlade volumes via NFS.

---

## 2. Gap Analysis (What's Missing)

Based on the provided Grafana screenshots, we need to add deep-visibility metrics for **Pure Storage FlashArray** and specialized **CPU breakdown** to match the official monitoring standards.

### FlashArray Advanced IOPS
The dashboard now includes block-level IOPS visibility. Verified queries from Prometheus UI:
*   **Array Level**: `sum(purefa_array_performance_throughput_iops)`
    *   *Result*: Successfully returning scalar value (e.g., `0` when idle).
*   **Host Level**: `sum by (dimension) (purefa_host_performance_throughput_iops)`
    *   *Result*: Returning dimensions: `mirrored_writes_per_sec`, `reads_per_sec`, `writes_per_sec`.

### CPU Detailed Breakdown
Verified granular CPU telemetry to identify processing vs I/O bottlenecks:
*   **User Mode**: `avg(rate(node_cpu_seconds_total{mode="user"}[1m])) * 100`
    *   *Result*: Returning precise percentage (e.g., `0.579%`).
*   **I/O Wait**: `avg(rate(node_cpu_seconds_total{mode="iowait"}[1m])) * 100`
    *   *Note*: Essential for detecting storage saturation.

---

## 3. Detailed Implementation Plan

### Step 1: Update `prometheus_metrics.py` (The Collector)
We will add new PromQL query constants and updated logic to fetch these specific metrics.

```python
# New Queries to be added
PROMETHEUS_FA_ARRAY_IOPS_QUERY = 'sum(purefa_array_performance_throughput_iops)'
PROMETHEUS_FA_HOST_IOPS_QUERY = 'sum by (dimension) (purefa_host_performance_throughput_iops)'
PROMETHEUS_CPU_USER_QUERY = 'avg(rate(node_cpu_seconds_total{mode="user"}[1m])) * 100'
PROMETHEUS_CPU_IOWAIT_QUERY = 'avg(rate(node_cpu_seconds_total{mode="iowait"}[1m])) * 100'
```

### Step 2: Update `backend_server.py` (The Aggregator)
The backend needs to map these new fields into the JSON payload sent to the dashboard via WebSockets.
*   Add `fa_array_iops` and `fa_host_iops` to the `hw` object.
*   Include `cpu_user_pct` and `cpu_iowait_pct` in the `infra` object.

### Step 3: Dashboard UI Enhancement (`dashboard-v4-preview.html`)
*   **Hardware Tab**: Add two new cards specifically for "FlashArray Block Storage" showing IOPS trends.
*   **Technology Tab**: Update the "Machine Metrics" table to include User/Wait CPU breakdown.

---

## 4. Verification Flow

1.  **PromQL Validation**: Run the queries directly in the Prometheus UI (`http://10.23.181.153:9090`) to ensure the `purefa_*` metrics are flowing.
2.  **API Inspection**: Use `curl http://localhost:8000/api/dashboard` to verify the JSON response contains the new hardware fields.
3.  **UI Verification**: Switch to the **Hardware Analytics** tab on the dashboard and verify the charts reflect real-time IOPS data.
