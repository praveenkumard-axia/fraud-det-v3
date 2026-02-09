#!/usr/bin/env python3
"""
Dashboard metrics collector: 1s polling.
Aggregates K8s utilization, queue/telemetry, Prometheus, and Pure1 metrics
into a structured JSON written to a file. WebSocket server reads this file and emits to clients.

Prometheus: set PROMETHEUS_URL for storage throughput, utilization, latency.
Pure1: set PURE1_API_TOKEN + PURE1_ARRAY_ID for FlashBlade current_bw/max_bw.
Local: when neither is available, uses psutil for local SSD/HDD (LOCAL_DISK_MAX_MBPS).
"""

import json
import subprocess
import time
import os
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from config_contract import StoragePaths
from k8s_scale import get_deployment_resources

MAX_SERIES_LEN = 60

try:
    from prometheus_metrics import fetch_prometheus_metrics
except ImportError:
    def fetch_prometheus_metrics() -> Dict[str, Any]:
        return {}

try:
    from pure1_metrics import fetch_flashblade_util
except ImportError:
    def fetch_flashblade_util() -> Dict[str, Any]:
        return {}

try:
    from local_disk_metrics import fetch_local_disk_metrics
except ImportError:
    def fetch_local_disk_metrics() -> Dict[str, Any]:
        return {}

# Default path for the metrics JSON (read by WebSocket every 1.2s)
METRICS_JSON_PATH = Path(__file__).parent / "run_data_output" / "dashboard_metrics.json"

# State for delta-based throughput calculation (file sizes)
_last_fb_stats = {
    "cpu": {"ts": 0.0, "bytes": 0},
    "gpu": {"ts": 0.0, "bytes": 0}
}

def _get_dir_size(path: Path) -> int:
    """Calculate total size of files in a directory (non-recursive for speed)."""
    try:
        if not path.exists():
            return 0
        return sum(f.stat().st_size for f in path.iterdir() if f.is_file())
    except Exception:
        return 0

def _kubectl_top_pods(namespace: str) -> List[Dict[str, Any]]:
    """Fetch real-time CPU/Mem usage from kubectl top pods."""
    cmd = ["kubectl", "top", "pods", "-n", namespace, "--no-headers"]
    pods = []
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return []
        
        for line in result.stdout.strip().split("\n"):
            parts = line.split()
            if len(parts) >= 3:
                # App name from pod name (assumes deployment-name-randomsuffix)
                pod_name = parts[0]
                deploy_name = "-".join(pod_name.split("-")[:-2]) if pod_name.count("-") >= 2 else pod_name
                
                cpu_raw = parts[1]
                mem_raw = parts[2]
                
                # Convert "100m" -> 100
                cpu = int(cpu_raw[:-1]) if cpu_raw.endswith("m") else int(cpu_raw)
                # Convert "100Mi" -> 100
                mem = int(mem_raw[:-2]) if mem_raw.endswith("Mi") else int(mem_raw)
                
                pods.append({
                    "pod": pod_name,
                    "app": deploy_name,
                    "cpu_millicores": cpu,
                    "mem_mib": mem
                })
    except Exception:
        pass
    return pods

def collect_metrics(
    queue_service: Any,
    telemetry: Dict[str, Any],
    namespace: str = "fraud-det-v3",
) -> Dict[str, Any]:
    """
    Build the dashboard payload from K8s, queue, and telemetry.
    Returns the structured dict to be stored and emitted over WebSocket.
    """
    ts = time.time()
    pod_top = _kubectl_top_pods(namespace)

    # CPU: from kubectl top when available; else fallback to telemetry cpu_percent
    cpu_util = sum(p.get("cpu_millicores", 0) for p in pod_top)
    if cpu_util == 0 and pod_top == []:
        cpu_pct = telemetry.get("cpu_percent", 0) or 0
        cpu_util = int(cpu_pct * 10)
    cpu_throughput = telemetry.get("throughput", 0)
    cpu_point = {"t": round(ts, 1), "util_millicores": cpu_util, "throughput": cpu_throughput}

    # GPU Utilization (placeholder until we have DCGM or similar)
    gpu_util = telemetry.get("gpu_util", 0)
    gpu_throughput = int(cpu_throughput * 0.7)  # Simulated split
    gpu_point = {"t": round(ts, 1), "util": gpu_util, "throughput": gpu_throughput}

    # Storage Paths
    cpu_fb_path = Path(os.getenv("CPU_VOLUME_PATH", "/mnt/cpu-fb"))
    gpu_fb_path = Path(os.getenv("GPU_VOLUME_PATH", "/mnt/gpu-fb"))

    # FlashBlade Throughput (Direct file growth measurement)
    global _last_fb_stats
    
    # CPU Volume metrics
    cpu_bytes = _get_dir_size(cpu_fb_path / "raw") + _get_dir_size(cpu_fb_path / "models")
    cpu_dt = ts - _last_fb_stats["cpu"]["ts"]
    cpu_tp_mbps = 0.0
    if cpu_dt > 0 and _last_fb_stats["cpu"]["ts"] > 0:
        cpu_tp_mbps = (cpu_bytes - _last_fb_stats["cpu"]["bytes"]) / (1024 * 1024) / cpu_dt
        cpu_tp_mbps = max(0.0, cpu_tp_mbps)
    _last_fb_stats["cpu"] = {"ts": ts, "bytes": cpu_bytes}

    # GPU Volume metrics
    gpu_bytes = _get_dir_size(gpu_fb_path / "raw") + _get_dir_size(gpu_fb_path / "features") + _get_dir_size(gpu_fb_path / "models")
    gpu_dt = ts - _last_fb_stats["gpu"]["ts"]
    gpu_tp_mbps = 0.0
    if gpu_dt > 0 and _last_fb_stats["gpu"]["ts"] > 0:
        gpu_tp_mbps = (gpu_bytes - _last_fb_stats["gpu"]["bytes"]) / (1024 * 1024) / gpu_dt
        gpu_tp_mbps = max(0.0, gpu_tp_mbps)
    _last_fb_stats["gpu"] = {"ts": ts, "bytes": gpu_bytes}

    # Prometheus Fallback/Merge
    prom = fetch_prometheus_metrics()
    latency_ms = prom.get("latency_ms", 12.0)

    # Pure1: Only if enabled
    pure1 = {}
    try:
        from config_contract import get_env, EnvironmentVariables
        if get_env(EnvironmentVariables.PURE_SERVER, "false").lower() in ("true", "1", "yes"):
            pure1 = fetch_flashblade_util()
    except ImportError:
        pass

    # FB Points for series (combined for backward compatibility, but we provide granular too)
    fb_cpu_point = {
        "t": round(ts, 1),
        "util": pure1.get("util_pct", 0),
        "throughput_mbps": round(cpu_tp_mbps, 2),
    }
    fb_gpu_point = {
        "t": round(ts, 1),
        "util": pure1.get("util_pct", 0),
        "throughput_mbps": round(gpu_tp_mbps, 2),
    }

    # Business from telemetry + queue
    generated = telemetry.get("generated", 0)
    data_prep_cpu = telemetry.get("data_prep_cpu", 0)
    data_prep_gpu = telemetry.get("data_prep_gpu", 0)
    processed = data_prep_cpu + data_prep_gpu
    txns_scored = telemetry.get("txns_scored", 0)
    fraud_blocked = telemetry.get("fraud_blocked", 0)
    
    # 17 KPIs
    kpis = {
        "1_fraud_exposure_identified_usd": round(fraud_blocked * 50, 2),
        "2_transactions_analyzed": txns_scored,
        "3_high_risk_flagged": fraud_blocked,
        "4_decision_latency_ms": round(latency_ms, 2),
        "17_flashblade_util_pct": pure1.get("util_pct", 0),
    }

    # Resource Allocation (Infra request/limit)
    res_alloc = get_deployment_resources()

    payload = {
        "cpu": [cpu_point],
        "gpu": [gpu_point],
        "fb_cpu": [fb_cpu_point],
        "fb_gpu": [fb_gpu_point],
        "fb": [fb_cpu_point], # Fallback for old UI
        "storage": {
            "cpu_mbps": round(cpu_tp_mbps, 2),
            "gpu_mbps": round(gpu_tp_mbps, 2),
            "latency_ms": latency_ms
        },
        "kpis": kpis,
        "infra": {
            "pods": pod_top,
            "allocation": res_alloc
        },
        "business": {
            "no_of_generated": generated,
            "no_of_processed": processed,
            "no_fraud": fraud_blocked,
            "pods": {
                "generation": {"no_of_generated": generated, "stream_speed": cpu_throughput},
                "prep": {"no_of_transformed": processed},
                "inference": {"fraud": fraud_blocked}
            }
        },
        "timestamp": ts,
    }
    return payload


def load_series_and_append(
    path: Path,
    new_payload: Dict[str, Any],
    max_len: int = MAX_SERIES_LEN,
) -> Dict[str, Any]:
    """Load existing metrics JSON, append new cpu/gpu/fb points (rolling), merge business, write back."""
    payload = new_payload.copy()
    cpu_new = payload.get("cpu", [])
    gpu_new = payload.get("gpu", [])
    fb_new = payload.get("fb", [])
    fb_cpu_new = payload.get("fb_cpu", [])
    fb_gpu_new = payload.get("fb_gpu", [])

    if path.exists():
        try:
            with open(path, "r") as f:
                existing = json.load(f)
            cpu_old = existing.get("cpu", [])[-max_len:]
            gpu_old = existing.get("gpu", [])[-max_len:]
            fb_old = existing.get("fb", [])[-max_len:]
            fb_cpu_old = existing.get("fb_cpu", [])[-max_len:]
            fb_gpu_old = existing.get("fb_gpu", [])[-max_len:]
            
            payload["cpu"] = (cpu_old + cpu_new)[-max_len:]
            payload["gpu"] = (gpu_old + gpu_new)[-max_len:]
            payload["fb"] = (fb_old + fb_new)[-max_len:]
            payload["fb_cpu"] = (fb_cpu_old + fb_cpu_new)[-max_len:]
            payload["fb_gpu"] = (fb_gpu_old + fb_gpu_new)[-max_len:]
        except Exception:
            payload["cpu"] = cpu_new[-max_len:]
            payload["gpu"] = gpu_new[-max_len:]
            payload["fb"] = fb_new[-max_len:]
            payload["fb_cpu"] = fb_cpu_new[-max_len:]
            payload["fb_gpu"] = fb_gpu_new[-max_len:]
    else:
        payload["cpu"] = cpu_new[-max_len:]
        payload["gpu"] = gpu_new[-max_len:]
        payload["fb"] = fb_new[-max_len:]
        payload["fb_cpu"] = fb_cpu_new[-max_len:]
        payload["fb_gpu"] = fb_gpu_new[-max_len:]

    return payload


def write_metrics_json(
    payload: Dict[str, Any],
    path: Optional[Path] = None,
) -> None:
    path = path or METRICS_JSON_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(payload, f, indent=0)


def run_one_poll(
    queue_service: Any,
    telemetry: Dict[str, Any],
    namespace: str = "fraud-det-v3",
    path: Optional[Path] = None,
) -> Dict[str, Any]:
    """One polling cycle: collect, merge series, write JSON. Returns raw payload."""
    path = path or METRICS_JSON_PATH
    raw = collect_metrics(queue_service, telemetry, namespace)
    merged = load_series_and_append(path, raw)
    write_metrics_json(merged, path)
    return raw
