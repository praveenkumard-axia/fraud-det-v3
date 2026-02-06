"""
Local disk metrics (SSD/HDD) for machines without Pure Storage.
Uses psutil to read disk I/O from /proc/diskstats (Linux) or equivalent.
Returns throughput (read/write MB/s) and estimated utilization %.
"""

import os
import time
from typing import Any, Dict, Optional

# Module-level state for delta calculation (1s polling)
_last_sample: Optional[tuple] = None


def fetch_local_disk_metrics() -> Dict[str, Any]:
    """
    Fetch disk throughput from local SSD/HDD via psutil.
    Returns: storage_read_mbps, storage_write_mbps, storage_util_pct (0-100).
    Env: LOCAL_DISK_MAX_MBPS - max theoretical throughput for util % (default 500 for SSD).
    """
    try:
        import psutil
    except ImportError:
        return {}

    global _last_sample
    now = time.time()
    try:
        counters = psutil.disk_io_counters()
    except Exception:
        return {}
    if counters is None:
        return {}

    read_bytes = getattr(counters, "read_bytes", 0) or 0
    write_bytes = getattr(counters, "write_bytes", 0) or 0

    read_mbps = 0.0
    write_mbps = 0.0
    if _last_sample is not None:
        prev_time, prev_read, prev_write = _last_sample
        dt = now - prev_time
        if dt > 0:
            read_mbps = (read_bytes - prev_read) / (1024 * 1024) / dt
            write_mbps = (write_bytes - prev_write) / (1024 * 1024) / dt
            read_mbps = max(0, read_mbps)
            write_mbps = max(0, write_mbps)

    _last_sample = (now, read_bytes, write_bytes)

    # Utilization: current throughput / max (SSD ~500 MB/s, HDD ~150 MB/s)
    max_mbps = float(os.getenv("LOCAL_DISK_MAX_MBPS", "500"))
    total_mbps = read_mbps + write_mbps
    util_pct = min(100, round(100 * total_mbps / max_mbps, 2)) if max_mbps > 0 else 0

    return {
        "storage_read_mbps": round(read_mbps, 2),
        "storage_write_mbps": round(write_mbps, 2),
        "storage_util_pct": util_pct,
        "fb_read_mbps": round(read_mbps, 2),
        "fb_write_mbps": round(write_mbps, 2),
    }
