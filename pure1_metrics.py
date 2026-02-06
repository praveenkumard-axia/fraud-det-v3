"""
Pure1 API fetcher for FlashBlade utilization: current_bw / max_bw.
Configure via env: PURE1_API_TOKEN, PURE1_ARRRAY_ID (or FLASHBLADE_ARRAY_NAME).
"""

import os
from typing import Any, Dict, Optional

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


def fetch_flashblade_util() -> Dict[str, Any]:
    """
    Fetch FlashBlade utilization (current_bw / max_bw) from Pure1 REST API.
    Returns dict with: util_pct (0-100), current_bw_mbps, max_bw_mbps.
    Requires PURE_SERVER=true to enable; otherwise returns {}.
    Env vars:
      PURE_SERVER - set "true" to enable Pure1/FB metrics
      PURE1_API_TOKEN - Pure1 API token
      PURE1_ARRAY_ID or FLASHBLADE_ARRAY_NAME - target array
      PURE1_API_BASE - optional, default https://api.pure1.purestorage.com
    """
    if os.getenv("PURE_SERVER", "false").strip().lower() not in ("true", "1", "yes"):
        return {}
    token = os.getenv("PURE1_API_TOKEN", "").strip()
    array_id = os.getenv("PURE1_ARRAY_ID") or os.getenv("FLASHBLADE_ARRAY_NAME", "").strip()
    base = os.getenv("PURE1_API_BASE", "https://api.pure1.purestorage.com").rstrip("/")

    if not REQUESTS_AVAILABLE or not token or not array_id:
        return {}

    try:
        headers = {"Authorization": f"Bearer {token}"}
        # Pure1 arrays endpoint - get array details and performance
        # Arrays: GET /api/1.2/arrays
        # Array performance: GET /api/1.2/arrays/performance
        url = f"{base}/api/1.2/arrays"
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code != 200:
            return {}

        data = r.json()
        items = data.get("items", [])
        arr = next((a for a in items if a.get("id") == array_id or a.get("name") == array_id), None)
        if not arr:
            return {}

        # Array performance - bandwidth and capacity
        perf_url = f"{base}/api/1.2/arrays/performance"
        r2 = requests.get(perf_url, headers=headers, params={"names": arr.get("name")}, timeout=5)
        if r2.status_code != 200:
            return {}

        perf_data = r2.json()
        perf_items = perf_data.get("items", [])
        if not perf_items:
            return {}

        p = perf_items[0]
        # Pure1 performance schema: input_percent, output_percent, or bytes_per_sec
        # Common fields: read_bandwidth, write_bandwidth (bytes/s)
        current_read = p.get("bytes_per_read", 0) or p.get("read_bandwidth", 0) or 0
        current_write = p.get("bytes_per_write", 0) or p.get("write_bandwidth", 0) or 0
        current_bw = float(current_read or 0) + float(current_write or 0)

        # Max bandwidth from array model (e.g. FlashBlade//S at 75 GB/s = 76800 MB/s)
        # Pure1 array object may have provisioned/usable capacity; max bandwidth is model-specific
        max_bw_mbps = float(arr.get("max_bandwidth", 0) or 76800)  # default 75 GB/s
        if max_bw_mbps <= 0:
            max_bw_mbps = 76800

        current_bw_mbps = current_bw / (1024 * 1024)
        util_pct = min(100, round(100 * current_bw_mbps / max_bw_mbps, 2)) if max_bw_mbps > 0 else 0

        return {
            "util_pct": util_pct,
            "current_bw_mbps": round(current_bw_mbps, 2),
            "max_bw_mbps": round(max_bw_mbps, 2),
        }
    except Exception:
        return {}
