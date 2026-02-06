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
    url = os.getenv("PROMETHEUS_URL", "http://prometheus:9090").strip()
    if not url:
        return {}

    # Default queries: node_exporter disk throughput (bytes/s -> MB/s)
    read_q = os.getenv(
        "PROMETHEUS_READ_THROUGHPUT_QUERY",
        "sum(rate(node_disk_read_bytes_total[1m])) / 1024 / 1024",
    )
    write_q = os.getenv(
        "PROMETHEUS_WRITE_THROUGHPUT_QUERY",
        "sum(rate(node_disk_written_bytes_total[1m])) / 1024 / 1024",
    )
    util_q = os.getenv("PROMETHEUS_UTIL_QUERY", "100")  # e.g. flashblade_util_percent
    latency_q = os.getenv("PROMETHEUS_LATENCY_QUERY", "0")  # e.g. histogram_quantile

    read_mbps = _prometheus_query(url, read_q)
    write_mbps = _prometheus_query(url, write_q)
    util_pct = _prometheus_query(url, util_q) if util_q else None
    latency_ms = _prometheus_query(url, latency_q) if latency_q else None

    # FlashBlade-specific if provided and PURE_SERVER=true; else use node_disk (local disk) metrics
    pure_server = os.getenv("PURE_SERVER", "false").strip().lower() in ("true", "1", "yes")
    fb_read_q = os.getenv("PROMETHEUS_FB_READ_QUERY", "").strip() if pure_server else ""
    fb_write_q = os.getenv("PROMETHEUS_FB_WRITE_QUERY", "").strip() if pure_server else ""
    fb_read = _prometheus_query(url, fb_read_q) if fb_read_q else read_mbps
    fb_write = _prometheus_query(url, fb_write_q) if fb_write_q else write_mbps

    out = {
        "storage_read_mbps": round(read_mbps, 2) if read_mbps is not None else None,
        "storage_write_mbps": round(write_mbps, 2) if write_mbps is not None else None,
        "storage_util_pct": round(util_pct, 2) if util_pct is not None else None,
        "latency_ms": round(latency_ms, 2) if latency_ms is not None else None,
        "fb_read_mbps": round(fb_read, 2) if fb_read is not None else None,
        "fb_write_mbps": round(fb_write, 2) if fb_write is not None else None,
    }
    return {k: v for k, v in out.items() if v is not None}
