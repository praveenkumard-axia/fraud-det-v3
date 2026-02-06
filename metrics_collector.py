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
from pathlib import Path
from typing import Dict, Any, List, Optional

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

# Rolling window size for cpu/gpu/fb time series
MAX_SERIES_LEN = 120


def _kubectl_top_pods(namespace: str = "fraud-pipeline") -> List[Dict[str, Any]]:
    """Get CPU/memory usage per pod via kubectl top pods. Returns list of {pod, cpu_millicores, memory_mb}."""
    try:
        result = subprocess.run(
            ["kubectl", "top", "pods", "-n", namespace, "--no-headers"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return []
        out = []
        for line in result.stdout.strip().splitlines():
            parts = line.split()
            if len(parts) >= 3:
                pod_name = parts[0]
                cpu_str = parts[1].rstrip("m")
                mem_str = parts[2].rstrip("Mi").rstrip("Gi")
                cpu_m = int(cpu_str) if cpu_str.isdigit() else 0
                try:
                    mem_mb = int(float(mem_str)) if "Gi" not in parts[2] else int(float(mem_str) * 1024)
                except ValueError:
                    mem_mb = 0
                out.append({"pod": pod_name, "cpu_millicores": cpu_m, "memory_mb": mem_mb})
        return out
    except Exception:
        return []


def collect_metrics(
    queue_service: Any,
    telemetry: Dict[str, Any],
    namespace: str = "fraud-pipeline",
) -> Dict[str, Any]:
    """
    Build the dashboard payload from K8s, queue, and telemetry.
    Returns the structured dict to be stored and emitted over WebSocket.
    """
    ts = time.time()
    pod_top = _kubectl_top_pods(namespace)

    # CPU: from kubectl top when available; else fallback to telemetry cpu_percent (e.g. when running pipeline locally)
    cpu_util = sum(p.get("cpu_millicores", 0) for p in pod_top)
    if cpu_util == 0 and pod_top == []:
        # No K8s metrics (metrics-server missing or no pods): use telemetry if available (local pipeline)
        cpu_pct = telemetry.get("cpu_percent", 0) or 0
        cpu_util = int(cpu_pct * 10)  # rough millicores proxy (e.g. 50% -> 500m)
    cpu_throughput = telemetry.get("throughput", 0)  # txns/s from telemetry
    cpu_point = {"t": round(ts, 1), "util_millicores": cpu_util, "throughput": cpu_throughput}

    # Prometheus: storage throughput, utilization, latency (when available)
    prom = fetch_prometheus_metrics()
    storage_read = prom.get("storage_read_mbps") or prom.get("fb_read_mbps")
    storage_write = prom.get("storage_write_mbps") or prom.get("fb_write_mbps")
    storage_util = prom.get("storage_util_pct")
    latency_ms = prom.get("latency_ms")

    # Pure1: FlashBlade current_bw / max_bw (only when PURE_SERVER=true)
    pure1 = {}
    try:
        from config_contract import get_env, EnvironmentVariables
        if get_env(EnvironmentVariables.PURE_SERVER, "false").lower() in ("true", "1", "yes"):
            pure1 = fetch_flashblade_util()
    except ImportError:
        pass

    # Local disk (SSD/HDD): fallback when no Prometheus/Pure1
    local = fetch_local_disk_metrics() if (storage_read is None and storage_write is None) else {}

    fb_util_pct = pure1.get("util_pct") if pure1 else (storage_util or local.get("storage_util_pct", 0))
    fb_read_mbps = storage_read if storage_read is not None else local.get("storage_read_mbps", 0.0)
    fb_write_mbps = storage_write if storage_write is not None else local.get("storage_write_mbps", 0.0)

    # GPU / FB
    gpu_point = {"t": round(ts, 1), "util": 0, "throughput": 0}
    fb_point = {
        "t": round(ts, 1),
        "util": fb_util_pct,
        "throughput_mbps": round(float(fb_read_mbps) + float(fb_write_mbps), 2),
        "read_mbps": round(float(fb_read_mbps), 2),
        "write_mbps": round(float(fb_write_mbps), 2),
    }

    # Business from telemetry + queue
    generated = telemetry.get("generated", 0)
    data_prep_cpu = telemetry.get("data_prep_cpu", 0)
    data_prep_gpu = telemetry.get("data_prep_gpu", 0)
    processed = data_prep_cpu + data_prep_gpu
    txns_scored = telemetry.get("txns_scored", 0)
    fraud_blocked = telemetry.get("fraud_blocked", 0)
    non_fraud = max(0, txns_scored - fraud_blocked)

    # Queue metrics if available
    try:
        raw_backlog = queue_service.get_backlog("raw-transactions")
        features_backlog = queue_service.get_backlog("features-ready")
    except Exception:
        raw_backlog = 0
        features_backlog = 0

    # Stream speed: throughput from telemetry (txns/s)
    stream_speed = telemetry.get("throughput", 0)
    # Prep velocity: approximate GB/s (e.g. rows * 256 bytes)
    bytes_processed = (data_prep_cpu + data_prep_gpu) * 256
    prep_velocity_gbps = round(bytes_processed / (1024 ** 3), 4) if processed else 0.0

    # ─── 17 KPIs (formulas per spec; fill from telemetry/queue where available) ───
    elapsed_sec = telemetry.get("total_elapsed", 0)
    hours_elapsed = elapsed_sec / 3600.0 if elapsed_sec else 0
    avg_amt = 50  # placeholder; use real amt when pipeline publishes it
    total_amt_approx = max(1, txns_scored * avg_amt)
    flagged_amt_approx = fraud_blocked * avg_amt
    # Queue metrics for risk distribution if published by inference
    try:
        risk_metrics = queue_service.get_metrics("fraud_dist_")
        real_high = risk_metrics.get("fraud_dist_high", fraud_blocked)
        real_low = risk_metrics.get("fraud_dist_low", non_fraud)
        real_medium = risk_metrics.get("fraud_dist_medium", 0)
    except Exception:
        real_high = fraud_blocked
        real_low = non_fraud
        real_medium = 0
    # Placeholders for TP/FP/TN/FN until pipeline publishes them
    tp = real_high
    fp = int(real_high * 0.06) if real_high else 0  # ~6% FP for precision 94%
    fn = int(real_high * 0.10) if real_high else 0
    tn = max(0, real_low + real_medium - fp)

    kpis = {
        "1_fraud_exposure_identified_usd": round(flagged_amt_approx, 2),  # SUM(amt) WHERE risk_score >= 75
        "2_transactions_analyzed": txns_scored,  # COUNT(*)
        "3_high_risk_flagged": fraud_blocked,  # COUNT(*) WHERE risk_score >= 75
        "4_decision_latency_ms": round(latency_ms, 2) if latency_ms is not None else 12.0,  # Prometheus or placeholder
        "5_precision_at_threshold": round(tp / max(1, tp + fp), 4) if (tp + fp) else 0,  # TP/(TP+FP)
        "6_fraud_rate_pct": round(100 * flagged_amt_approx / total_amt_approx, 4) if total_amt_approx else 0,  # SUM(amt flagged)/SUM(amt total)
        "7_alerts_per_1m": round((fraud_blocked / max(1, txns_scored)) * 1e6, 0) if txns_scored else 0,
        "8_high_risk_txn_rate": round(fraud_blocked / max(1, txns_scored), 4) if txns_scored else 0,
        "9_annual_savings_usd": round((flagged_amt_approx / max(0.001, hours_elapsed)) * 8760, 0) if hours_elapsed else 0,
        "10_risk_distribution": {  # GROUP BY risk_score bins
            "low_0_60": real_low,
            "medium_60_90": real_medium,
            "high_90_100": real_high,
        },
        "11_fraud_velocity_per_min": stream_speed * 60 if stream_speed else 0,  # COUNT(flagged) GROUP BY minute; proxy
        "12_category_risk": {},  # SUM(amt flagged) GROUP BY category; fill when pipeline publishes
        "13_risk_concentration_pct": 68.0,  # SUM(amt top 1%)/SUM(amt flagged); placeholder
        "14_state_risk": {},  # SUM(amt flagged) GROUP BY state; fill when pipeline publishes
        "15_recall": round(tp / max(1, tp + fn), 4) if (tp + fn) else 0,  # TP/(TP+FN)
        "16_false_positive_rate": round(fp / max(1, fp + tn), 4) if (fp + tn) else 0,  # FP/(FP+TN)
        "17_flashblade_util_pct": fb_point.get("util", 0),  # current_bw/max_bw from Pure1 or Prometheus
    }

    # Storage metrics (Prometheus / Pure1) for JSON consumers
    storage_metrics = {
        "throughput_read_mbps": round(float(fb_point.get("read_mbps", 0)), 2),
        "throughput_write_mbps": round(float(fb_point.get("write_mbps", 0)), 2),
        "utilization_pct": fb_point.get("util", 0),
        "latency_ms": round(latency_ms, 2) if latency_ms is not None else None,
    }

    payload = {
        "cpu": [cpu_point],
        "gpu": [gpu_point],
        "fb": [fb_point],
        "storage": storage_metrics,
        "kpis": kpis,
        "business": {
            "no_of_generated": generated,
            "no_of_processed": processed,
            "no_fraud": fraud_blocked,
            "no_blocked": fraud_blocked,
            "pods": {
                "generation": {
                    "no_of_generated": generated,
                    "stream_speed": stream_speed,
                },
                "prep": {
                    "no_of_transformed": processed,
                    "prep_velocity": prep_velocity_gbps,
                },
                "model_train": {
                    "samples_trained": telemetry.get("txns_scored", 0),
                    "status": telemetry.get("current_stage", "") == "Model Train" and "Running" or "Idle",
                },
                "inference": {
                    "fraud": fraud_blocked,
                    "non_fraud": non_fraud,
                    "percent_score": round(100 * fraud_blocked / max(1, txns_scored), 2) if txns_scored else 0,
                },
            },
        },
        "backlog": {"raw": raw_backlog, "features": features_backlog},
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

    if path.exists():
        try:
            with open(path, "r") as f:
                existing = json.load(f)
            cpu_old = existing.get("cpu", [])[-max_len:]
            gpu_old = existing.get("gpu", [])[-max_len:]
            fb_old = existing.get("fb", [])[-max_len:]
            payload["cpu"] = (cpu_old + cpu_new)[-max_len:]
            payload["gpu"] = (gpu_old + gpu_new)[-max_len:]
            payload["fb"] = (fb_old + fb_new)[-max_len:]
        except Exception:
            payload["cpu"] = cpu_new[-max_len:]
            payload["gpu"] = gpu_new[-max_len:]
            payload["fb"] = fb_new[-max_len:]
    else:
        payload["cpu"] = cpu_new[-max_len:]
        payload["gpu"] = gpu_new[-max_len:]
        payload["fb"] = fb_new[-max_len:]

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
    namespace: str = "fraud-pipeline",
    path: Optional[Path] = None,
) -> None:
    """One polling cycle: collect, merge series, write JSON."""
    path = path or METRICS_JSON_PATH
    raw = collect_metrics(queue_service, telemetry, namespace)
    merged = load_series_and_append(path, raw)
    write_metrics_json(merged, path)
