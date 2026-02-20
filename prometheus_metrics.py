"""
Prometheus metrics fetcher for dashboard.
Polls Prometheus at 1s interval; provides throughput, utilization, latency.
Configure via env: PROMETHEUS_URL, PROMETHEUS_*_QUERY for custom metric names.
"""

import os
from typing import Any, Dict, Optional

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


def _prometheus_query(url: str, query: str, timeout: float = 2.0) -> Optional[float]:
    """Run a single PromQL instant query; return first scalar/value or None."""
    if not REQUESTS_AVAILABLE or not url:
        return None
    try:
        r = requests.get(
            f"{url.rstrip('/')}/api/v1/query",
            params={"query": query},
            timeout=timeout,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        if data.get("status") != "success":
            return None
        result = data.get("data", {}).get("result", [])
        if not result:
            return None
        val = result[0].get("value")
        if val is None:
            return None
        # Prometheus returns [timestamp, "value"]
        if isinstance(val, (list, tuple)) and len(val) >= 2:
            try:
                return float(val[1])
            except (ValueError, TypeError):
                return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None
    except Exception:
        return None



def fetch_prometheus_metrics() -> Dict[str, Any]:
    """
    Fetch storage throughput, utilization, latency from Prometheus.
    Returns dict suitable for merging into metrics payload.
    Env vars:
      PROMETHEUS_URL - e.g. http://prometheus:9090
      PROMETHEUS_READ_THROUGHPUT_QUERY - e.g. rate(node_disk_read_bytes_total[5m])*1024 (MB/s)
      PROMETHEUS_WRITE_THROUGHPUT_QUERY
      PROMETHEUS_UTIL_QUERY - storage utilization 0-100
      PROMETHEUS_LATENCY_QUERY - latency ms
      PROMETHEUS_FB_READ_QUERY, PROMETHEUS_FB_WRITE_QUERY - FlashBlade-specific
    """
    url = os.getenv("PROMETHEUS_URL", "http://10.23.181.153:9090").strip()
    if not url:
        return {}

    # 1. FLASHBLADE NATIVE QUERIES (Preferred over node_exporter NFS)
    # Bandwidth (Conversion: Bytes -> MB/s)
    fb_read_q = 'sum(purefb_file_systems_performance_bandwidth_bytes{dimension="read_bytes_per_sec"}) / 1024 / 1024'
    fb_write_q = 'sum(purefb_file_systems_performance_bandwidth_bytes{dimension="write_bytes_per_sec"}) / 1024 / 1024'
    fb_iops_q = 'sum(purefb_file_systems_performance_throughput_iops)'
    fb_latency_q = 'avg(purefb_file_systems_performance_latency_usec) / 1000'
    fb_throughput_q = 'sum(purefb_array_performance_throughput_iops)' #to check the throughputof the data

    # 2. CPU UTILIZATION & BREAKDOWN
    cpu_total_q = '100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[1m])) * 100)'
    cpu_user_q = 'avg(rate(node_cpu_seconds_total{mode="user"}[1m])) * 100'
    cpu_iowait_q = 'avg(rate(node_cpu_seconds_total{mode="iowait"}[1m])) * 100'
    cpu_cores_q = 'count(count(node_cpu_seconds_total) by (cpu))'
    
    # 3. GPU UTILIZATION (DCGM Preferred)
    gpu_util_q = 'avg(DCGM_FI_DEV_GPU_UTIL)'
    
    # 4. MEMORY UTILIZATION
    node_mem_q = "((node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes) / node_memory_MemTotal_bytes) * 100"

    # Execution
    fb_read = _prometheus_query(url, fb_read_q) or 0
    fb_write = _prometheus_query(url, fb_write_q) or 0
    fb_iops = _prometheus_query(url, fb_iops_q) or 0
    fb_latency = _prometheus_query(url, fb_latency_q) or 0
    fb_throughput = _prometheus_query(url, fb_throughput_q) or 0
    
    cpu_total = _prometheus_query(url, cpu_total_q) or 0
    cpu_user = _prometheus_query(url, cpu_user_q) or 0
    cpu_iowait = _prometheus_query(url, cpu_iowait_q) or 0
    cpu_cores = _prometheus_query(url, cpu_cores_q) or 0
    
    gpu_util = _prometheus_query(url, gpu_util_q) or 0
    node_mem = _prometheus_query(url, node_mem_q) or 0

    # Pod-level Totals
    total_pod_cpu = _prometheus_query(url, "sum(rate(container_cpu_usage_seconds_total{namespace='fraud-det-v3'}[1m])) * 1000")
    total_pod_mem = _prometheus_query(url, "sum(container_memory_working_set_bytes{namespace='fraud-det-v3'}) / 1048576")

    out = {
        "storage_read_mbps": round(fb_read, 2),
        "storage_write_mbps": round(fb_write, 2),
        "latency_ms": round(fb_latency, 2),
        "fb_read_mbps": round(fb_read, 2),
        "fb_write_mbps": round(fb_write, 2),
        "fb_iops": int(fb_iops),
        "fb_latency_ms": round(fb_latency, 2),
        "fb_throughput": round(fb_throughput, 2),
        
        "node_cpu_percent": round(cpu_total, 2),
        "cpu_user_percent": round(cpu_user, 2),
        "cpu_iowait_percent": round(cpu_iowait, 2),
        "cpu_cores": int(cpu_cores),
        
        "node_ram_percent": round(node_mem, 2),
        "gpu_util_pct": round(gpu_util, 2),
        
        "total_pod_cpu_millicores": round(total_pod_cpu, 1) if total_pod_cpu is not None else 0,
        "total_pod_mem_mib": round(total_pod_mem, 1) if total_pod_mem is not None else 0,
    }
    
    return out
