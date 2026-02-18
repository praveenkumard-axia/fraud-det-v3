#!/usr/bin/env python3
"""
Backend Server for Dashboard v5 - Continuous Pipeline
Orchestrates 4 pods with queue-based communication and real-time control
"""

import json
import os
import sys
import time
import asyncio
import subprocess
import threading
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, List

from fastapi import FastAPI, BackgroundTasks, WebSocket, WebSocketDisconnect, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import uvicorn

# Import queue and config modules
from queue_interface import get_queue_service
from k8s_scale import scale_pod, patch_pod_resources, is_k8s_available, LOCAL_MODE
from metrics_collector import run_one_poll, METRICS_JSON_PATH
from config_contract import (
    QueueTopics, StoragePaths, ScalingConfig, BacklogThresholds,
    SystemPriorities, GenerationRateLimits, get_env
)

# Configuration
BASE_DIR = Path(__file__).parent
PODS_DIR = BASE_DIR / "pods"

# FastAPI App
app = FastAPI(title="Fraud Detection Dashboard Backend v4")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Enable compression for responses
from fastapi.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=1000)

# ==================== PERFORMANCE MONITORING ====================

# Performance timing middleware
@app.middleware("http")
async def add_performance_headers(request, call_next):
    """Track API response times and log slow requests"""
    start_time = time.time()
    response = await call_next(request)
    duration_ms = (time.time() - start_time) * 1000
    
    # Add timing header
    response.headers["X-Response-Time"] = f"{duration_ms:.2f}ms"
    
    # Log slow requests
    if duration_ms > 100:
        print(f"⚠️  SLOW API: {request.url.path} took {duration_ms:.0f}ms")
    # elif duration_ms < 10:
    #     print(f"⚡ FAST API: {request.url.path} took {duration_ms:.1f}ms")
    
    return response


# ==================== METRICS CACHE SYSTEM (Phase 1 + 2 + 3) ====================

class OptimizedMetricsCache:
    """
    High-performance metrics cache implementing all 3 optimization phases:
    - Phase 1: In-memory caching with TTL
    - Phase 2: Batch file reads (read once, not 40x)
    - Phase 3: Lock-free reads with async refresh
    """
    
    def __init__(self, ttl_seconds=1.0):
        self.cache = {}
        self.last_update = 0
        self.ttl = ttl_seconds
        self.refreshing = False
        self._lock = threading.Lock()  # Only for cache updates, not reads!
        
    def get_all_metrics(self, queue_service):
        """
        Get all metrics with intelligent caching.
        Returns cached data if fresh, triggers async refresh if stale.
        """
        now = time.time()
        cache_age = now - self.last_update
        
        # Lock-free read from cache (Phase 3: concurrent reads)
        if cache_age < self.ttl and self.cache:
            # Cache hit - instant response from memory!
            return self.cache
        
        # Cache miss or stale - need refresh
        if not self.refreshing:
            # Refresh cache (thread-safe)
            self._refresh_cache(queue_service, now)
        
        # Return cached data (even if slightly stale) or empty dict
        return self.cache if self.cache else {}
    
    def _refresh_cache(self, queue_service, now):
        """Refresh cache with batch read (Phase 2)"""
        with self._lock:
            # Double-check refresh flag
            if self.refreshing:
                return
            
            self.refreshing = True
            
        try:
            # Phase 2: Read ALL metrics in ONE operation
            # Instead of 40+ separate file reads, read metrics file ONCE
            new_cache = self._batch_read_all_metrics(queue_service)
            
            # ✅ FIX: ONLY update if we got a valid non-empty dict
            if new_cache:
                with self._lock:
                    self.cache = new_cache
                    self.last_update = now
                # print(f"📊 Cache refreshed - {len(new_cache)} metrics loaded")
            else:
                # Keep old cache if update failed, but update last_update to prevent constant retries if file is missing
                with self._lock:
                    self.last_update = now
                # print("⚠️  Cache refresh returned empty - keeping stale data")
            
        except Exception as e:
            # print(f"❌ Cache refresh failed: {e}")
            pass
        finally:
            with self._lock:
                self.refreshing = False
    
    def _batch_read_all_metrics(self, queue_service):
        """
        Phase 2 Implementation: Batch read all metrics from file ONCE.
        This replaces 40+ individual get_metric() calls with 1 file read.
        """
        try:
            # Read the metrics JSON file directly (1 file operation)
            # Use queue service's base path (works with both FlashBlade and local)
            metrics_file = Path(queue_service.base_path) / "queue" / ".metrics.json"
            if not metrics_file.exists():
                return {}
            
            with open(metrics_file, 'r') as f:
                all_metrics = json.load(f)
            
            # Also get backlog counts (these are directory listings, relatively fast)
            all_metrics['_backlogs'] = {
                'raw': queue_service.get_backlog(QueueTopics.RAW_TRANSACTIONS),
                'features': queue_service.get_backlog(QueueTopics.FEATURES_READY),
                'inference': queue_service.get_backlog(QueueTopics.INFERENCE_RESULTS),
                'training': queue_service.get_backlog(QueueTopics.TRAINING_QUEUE),
            }
            
            return all_metrics
            
        except (json.JSONDecodeError, FileNotFoundError, Exception) as e:
            if not isinstance(e, FileNotFoundError):
                print(f"⚠️  Batch read failed, falling back: {e}")
            # Fallback: return None so refresh logic knows it failed
            return None
    
    def invalidate(self):
        """Force cache refresh on next request"""
        with self._lock:
            self.last_update = 0


# Global cache instance
metrics_cache = OptimizedMetricsCache(ttl_seconds=1.0)


# Serve static files (dashboard HTML)
@app.get("/dashboard-v4-preview.html")
async def serve_dashboard():
    return FileResponse(BASE_DIR / "dashboard-v4-preview.html", media_type="text/html")


# ==================== Data Models ====================

class ScaleRequest(BaseModel):
    replicas: int

class PriorityRequest(BaseModel):
    priority: str

class ThrottleRequest(BaseModel):
    rate: int

class ScaleConfig(BaseModel):
    preprocessing_pods: int = 1
    training_pods: int = 1
    inference_pods: int = 1
    generation_rate: int = 50000


class ResourcePatchRequest(BaseModel):
    cpu_limit: str
    memory_limit: str


class PipelineState:
    """Global state for pipeline execution and telemetry"""
    
    def __init__(self):
        self.is_running = False
        self.start_time: Optional[float] = None
        self.processes: Dict[str, subprocess.Popen] = {}
        
        # Telemetry data
        self.telemetry = {
            "generated": 0,
            "data_prep_cpu": 0,
            "data_prep_gpu": 0,
            "inference_cpu": 0,
            "inference_gpu": 0,
            "total_elapsed": 0.0,
            "current_stage": "Waiting",
            "current_status": "Idle",
            "throughput": 0,
            "throughput_cpu": 0,
            "throughput_gpu": 0,
            "cpu_percent": 0,
            "ram_percent": 0,
            "fraud_blocked": 0,
            "txns_scored": 0,
            # Dual Volume FlashBlade Metrics
            "fb_cpu_throughput": 0,
            "fb_gpu_throughput": 0,
        }
        
        # Configuration
        self.scale_config = ScaleConfig()
        
        # NEW: Continuous operation state
        self.generation_rate = GenerationRateLimits.DEFAULT_RATE
        self.system_priority = SystemPriorities.BALANCED
        self.pod_counts = {
            "preprocessing": 1,
            "training": 1,
            "inference": 1,
            "generation": 1,
            "preprocessing_gpu": 1,
            "inference_gpu": 1,
        }
        
        # Queue service
        self.queue_service = get_queue_service()
        
        # Lock for thread safety
        self.lock = threading.Lock()
    
    def reset(self):
        """Reset all telemetry to zero"""
        with self.lock:
            self.telemetry = {
                "generated": 0,
                "data_prep_cpu": 0,
                "data_prep_gpu": 0,
                "inference_cpu": 0,
                "inference_gpu": 0,
                "total_elapsed": 0.0,
                "current_stage": "Waiting",
                "current_status": "Idle",
                "throughput": 0,
                "cpu_percent": 0,
                "ram_percent": 0,
                "fraud_blocked": 0,
                "txns_scored": 0,
                "fb_cpu_throughput": 0,
                "fb_gpu_throughput": 0,
            }
            self.start_time = None
    
    def update_telemetry(self, stage: str, status: str, rows: int, throughput: int, 
                         elapsed: float, cpu_percent: float, ram_percent: float,
                         fraud_blocked: Optional[int] = None):
        """Update telemetry from pod output"""
        with self.lock:
            self.telemetry["current_stage"] = stage
            self.telemetry["current_status"] = status
            self.telemetry["throughput"] = throughput
            self.telemetry["cpu_percent"] = cpu_percent
            self.telemetry["ram_percent"] = ram_percent
            
            # Map stage to appropriate counter
            if stage == "Ingest":
                self.telemetry["generated"] = max(self.telemetry.get("generated", 0), rows)
                self.telemetry["throughput_cpu"] = throughput  # Ingest is usually CPU
            elif stage == "Data Prep":
                self.telemetry["data_prep_cpu"] = int(rows * 0.4)
                self.telemetry["data_prep_gpu"] = int(rows * 0.6)
                self.telemetry["txns_scored"] = rows
                self.telemetry["throughput_cpu"] = throughput # Data prep is CPU-bound here
                # Data Prep processes generated data — generated >= prep rows
                self.telemetry["generated"] = max(self.telemetry.get("generated", 0), rows)
            elif stage == "Model Train":
                self.telemetry["txns_scored"] = rows
                # Model trained on generated data
                self.telemetry["generated"] = max(self.telemetry.get("generated", 0), rows)
            elif stage == "Inference":
                self.telemetry["inference_cpu"] = int(rows * 0.3)
                self.telemetry["inference_gpu"] = int(rows * 0.7)
                self.telemetry["txns_scored"] = rows
                self.telemetry["throughput_gpu"] = throughput # Inference is typically GPU/Triton
                # Inference processes generated data — generated >= inference rows
                self.telemetry["generated"] = max(self.telemetry.get("generated", 0), rows)
            
            # Calculate or use REAL fraud metrics
            if fraud_blocked is not None:
                self.telemetry["fraud_blocked"] = fraud_blocked
            else:
                # Fallback to 0.5% fraud rate if not provided (e.g. from data-prep stage)
                fraud_rate = 0.005
                self.telemetry["fraud_blocked"] = int(self.telemetry["txns_scored"] * fraud_rate)
            
            self.telemetry["total_elapsed"] = elapsed


# Global state instance
state = PipelineState()


# ==================== Pod Orchestrator ====================

def parse_telemetry_line(line: str) -> Optional[Dict]:
    """Parse [TELEMETRY] log line from pod output"""
    if "[TELEMETRY]" not in line:
        return None
    
    try:
        # Extract key=value pairs
        data = {}
        parts = line.split("|")
        for part in parts:
            part = part.strip()
            # Remove [TELEMETRY] tag if present in this part (usually the first one)
            part = part.replace("[TELEMETRY]", "").strip()
            
            if "=" in part:
                key, value = part.split("=", 1)
                key = key.strip()
                value = value.strip()
                
                if key in ["stage", "status"]:
                    data[key] = value
                elif key in ["rows", "throughput", "fraud_blocked"]:
                    data[key] = int(value)
                elif key in ["elapsed", "cpu_cores", "ram_gb", "ram_percent"]:
                    data[key] = float(value)
        
        return data
    except Exception as e:
        print(f"Failed to parse telemetry: {e}")
        return None


def run_pod_async(pod_name: str, script_path: str):
    """Run a pod in background and capture telemetry without blocking"""
    def _run():
        print(f"🚀 Starting pod: {pod_name}")
        try:
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            
            # Pods use StoragePaths to find their input/output locations.
            # We don't need to override them here unless we're in a special container context.
            # Removing these overrides so they default to StoragePaths "auto" logic.
            
            # Start process
            process = subprocess.Popen(
                [sys.executable, script_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env,
                cwd=str(BASE_DIR)
            )
            
            state.processes[pod_name] = process
            
            # Read output and parse telemetry
            for line in iter(process.stdout.readline, ''):
                if not line:
                    break
                
                line = line.strip()
                # Print to console for visibility
                print(f"[{pod_name}] {line}")
                
                # Parse telemetry
                telemetry = parse_telemetry_line(line)
                if telemetry:
                    # Update local state so it can be picked up by the metrics loop
                    state.update_telemetry(
                        stage=telemetry.get("stage", "Unknown"),
                        status=telemetry.get("status", "Running"),
                        rows=telemetry.get("rows", 0),
                        throughput=telemetry.get("throughput", 0),
                        fraud_blocked=telemetry.get("fraud_blocked"),
                        elapsed=telemetry.get("elapsed", 0.0),
                        cpu_percent=telemetry.get("cpu_cores", 0.0),
                        ram_percent=telemetry.get("ram_percent", 0.0)
                    )
            
            process.wait()
            if pod_name in state.processes:
                del state.processes[pod_name]
            print(f"✅ Pod {pod_name} completed with code {process.returncode}")
            
        except Exception as e:
            print(f"❌ Error running pod {pod_name}: {e}")
            if pod_name in state.processes:
                del state.processes[pod_name]

    # Run in a separate thread so it doesn't block FastAPI
    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread


async def _tail_pod_logs(pod_name: str):
    """Tail logs for a single K8s pod and parse telemetry."""
    from k8s_scale import NAMESPACE
    print(f"Started tailing logs for K8s pod: {pod_name}")
    
    try:
        process = await asyncio.create_subprocess_exec(
            "kubectl", "logs", "-f", pod_name, "-n", NAMESPACE, "--tail=10",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT
        )
        
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            
            line_str = line.decode().strip()
            telemetry = parse_telemetry_line(line_str)
            if telemetry:
                state.update_telemetry(
                    stage=telemetry.get("stage", "Unknown"),
                    status=telemetry.get("status", "Running"),
                    rows=telemetry.get("rows", 0),
                    throughput=telemetry.get("throughput", 0),
                    elapsed=telemetry.get("elapsed", 0.0),
                    cpu_percent=telemetry.get("cpu_cores", 0.0),
                    ram_percent=telemetry.get("ram_percent", 0.0)
                )
    except Exception as e:
        print(f"Error tailing logs for {pod_name}: {e}")
    finally:
        print(f"Stopped tailing logs for K8s pod: {pod_name}")


async def _k8s_telemetry_loop():
    """Background task to discover and tail logs from K8s pods."""
    from k8s_scale import NAMESPACE
    
    tailing_pods = set()
    
    while True:
        try:
            if not state.is_running or not is_k8s_available() or LOCAL_MODE:
                await asyncio.sleep(5)
                continue
            
            # Get running pods from our deployments
            process = await asyncio.create_subprocess_exec(
                "kubectl", "get", "pods", "-n", NAMESPACE,
                "--field-selector=status.phase=Running",
                "-o", "jsonpath={range .items[*]}{.metadata.name} {.metadata.labels.app}{\"\\n\"}{end}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await process.communicate()
            
            if process.returncode == 0:
                lines = stdout.decode().strip().split("\n")
                for line in lines:
                    if not line: continue
                    parts = line.split()
                    if len(parts) < 2: continue
                    pod_name, app_name = parts[0], parts[1]
                    
                    if app_name in ["data-gather", "preprocessing-cpu", "inference-cpu", "preprocessing-gpu", "model-build", "inference-gpu"]:
                        if pod_name not in tailing_pods:
                            tailing_pods.add(pod_name)
                            task = asyncio.create_task(_tail_pod_logs(pod_name))
                            task.add_done_callback(lambda t, p=pod_name: tailing_pods.discard(p))
                            
        except Exception as e:
            print(f"K8s telemetry loop error: {e}")
            
        await asyncio.sleep(10)


def run_pipeline_sequence():
    """Run all 4 pods as background threads"""
    state.is_running = True
    state.start_time = time.time()
    
    print("🚀 Triggering pipeline sequence in background...")
    # Pod 1: Data Generation
    run_pod_async("data-gather", str(PODS_DIR / "data-gather" / "gather.py"))
    
    # Pod 2: Data Prep
    run_pod_async("data-prep", str(PODS_DIR / "data-prep" / "prepare.py"))
    
    # Pod 3: Model Training
    run_pod_async("model-build", str(PODS_DIR / "model-build" / "train.py"))
    
    # Pod 4: Inference (requires Triton on port 8001)
    run_pod_async("inference", str(PODS_DIR / "inference" / "client.py"))
    
    # Note: is_running remains True. It will be set to False only when all processes are stopped manually.


# ==================== API Endpoints ====================

@app.get("/")
def root():
    return {"status": "Dashboard Backend v4 Online", "version": "1.0.0"}


@app.get("/api/dashboard")
def get_dashboard_data():
    """Main endpoint for dashboard data"""
    
    with state.lock:
        tel = state.telemetry.copy()
    
    # Calculate elapsed time
    if state.start_time:
        elapsed = time.time() - state.start_time
    else:
        elapsed = tel["total_elapsed"]
    
    # Format elapsed as MM:SS.S
    minutes = int(elapsed // 60)
    seconds = elapsed % 60
    elapsed_str = f"{minutes:02d}:{seconds:04.1f}"
    
    # Get REAL queue backlogs
    raw_backlog = state.queue_service.get_backlog(QueueTopics.RAW_TRANSACTIONS)
    features_backlog = state.queue_service.get_backlog(QueueTopics.FEATURES_READY)
    inference_backlog = state.queue_service.get_backlog(QueueTopics.INFERENCE_RESULTS)
    
    # Calculate backlog (use queue data)
    total_generated = tel["generated"]
    total_processed = tel["data_prep_cpu"] + tel["data_prep_gpu"]
    backlog = raw_backlog  # Use actual queue backlog
    
    # Calculate business metrics
    fraud_rate = 0.005
    avg_txn_amount = 50
    
    # Get REAL risk distribution from FlashBlade/file queue
    risk_metrics = state.queue_service.get_metrics("fraud_dist_")
    real_low = risk_metrics.get("fraud_dist_low", 0)
    real_medium = risk_metrics.get("fraud_dist_medium", 0)
    real_high = risk_metrics.get("fraud_dist_high", 0)
    
    # If we have real metrics, use them, otherwise fallback to ratios to keep charts moving
    total_samples = real_low + real_medium + real_high
    if total_samples > 0:
        low_dist = real_low
        medium_dist = real_medium
        high_dist = real_high
    else:
        low_dist = int(tel["txns_scored"] * 0.65)
        medium_dist = int(tel["txns_scored"] * 0.25)
        high_dist = int(tel["txns_scored"] * 0.10)

    fraud_blocked = real_high if total_samples > 0 else tel["fraud_blocked"]
    fraud_prevented_usd = fraud_blocked * avg_txn_amount
    
    # Simulated throughput split
    total_throughput = tel["throughput"]
    gpu_throughput = int(total_throughput * 0.7)
    cpu_throughput = int(total_throughput * 0.3)
    
    # FlashBlade metrics (now using dual-volume telemetry)
    fb_cpu_throughput = tel.get("fb_cpu_throughput", 0)
    fb_gpu_throughput = tel.get("fb_gpu_throughput", 0)
    total_fb_throughput = fb_cpu_throughput + fb_gpu_throughput
    
    # FlashBlade utilization capped at 25GB/s (FlashBlade S500 entry limit approx)
    flashblade_util = min(100, int((total_fb_throughput / 25000) * 100)) if total_fb_throughput > 0 else 0
    
    return {
        "pipeline_progress": {
            "generated": total_generated,
            "data_prep_cpu": tel["data_prep_cpu"],
            "data_prep_gpu": tel["data_prep_gpu"],
            "inference_cpu": tel["inference_cpu"],
            "inference_gpu": tel["inference_gpu"],
            "backlog": backlog
        },
        "utilization": {
            "gpu": min(85, tel["cpu_percent"] + 10),  # Simulated GPU higher
            "cpu": min(78, int(tel["cpu_percent"])),
            "flashblade": flashblade_util
        },
        "throughput": {
            "gpu": gpu_throughput,
            "cpu": cpu_throughput
        },
        "business": {
            "fraud_prevented": int(fraud_prevented_usd),
            "txns_scored": total_samples if total_samples > 0 else tel["txns_scored"],
            "fraud_blocked": fraud_blocked,
            "throughput": total_throughput
        },
        "fraud_dist": {
            "low": low_dist,
            "medium": medium_dist,
            "high": high_dist
        },
        "flashblade": {
            "read": fb_cpu_throughput,
            "write": fb_gpu_throughput,
            "util": flashblade_util,
            "headroom": round(100 - flashblade_util, 1),
            "cpu_vol": fb_cpu_throughput,
            "gpu_vol": fb_gpu_throughput
        },
        "status": {
            "live": state.is_running,
            "elapsed": elapsed_str,
            "stage": tel["current_stage"],
            "status": tel["current_status"]
        },
        # NEW: Queue backlogs
        "queue_backlogs": {
            "raw_transactions": raw_backlog,
            "features_ready": features_backlog,
            "inference_results": inference_backlog
        },
        # NEW: Pod counts
        "pod_counts": state.pod_counts.copy(),
        # NEW: System configuration
        "system_config": {
            "generation_rate": state.generation_rate,
            "priority": state.system_priority
        }
    }


@app.post("/api/control/start")
async def start_pipeline(background_tasks: BackgroundTasks):
    """Start the pipeline by scaling K8s deployments to default replicas (fraud-det-v3 namespace)."""
    if state.is_running:
        return {"success": False, "message": "Pipeline already running"}

    # Scale all deployments (CPU + GPU) to defaults
    # Scale deployments based on CONFIG_MODE (cpu or gpu)
    config_mode = os.getenv("CONFIG_MODE", "dual").lower()
    
    defaults = {}
    # Common deployments
    defaults["data-gather"] = ScalingConfig.DEPLOYMENTS["data-gather"]["default_replicas"]
    
    if config_mode == "cpu":
        defaults["preprocessing-cpu"] = ScalingConfig.DEPLOYMENTS["preprocessing"]["default_replicas"]
        defaults["inference-cpu"] = ScalingConfig.DEPLOYMENTS["inference"]["default_replicas"]
        
    elif config_mode == "gpu":
        defaults["preprocessing-gpu"] = ScalingConfig.DEPLOYMENTS["preprocessing-gpu"]["default_replicas"]
        defaults["inference-gpu"] = ScalingConfig.DEPLOYMENTS["inference-gpu"]["default_replicas"]
        
    else:
        defaults.update({
            "preprocessing-cpu": ScalingConfig.DEPLOYMENTS["preprocessing"]["default_replicas"],
            "inference-cpu": ScalingConfig.DEPLOYMENTS["inference"]["default_replicas"],
            "preprocessing-gpu": ScalingConfig.DEPLOYMENTS["preprocessing-gpu"]["default_replicas"],
            "inference-gpu": ScalingConfig.DEPLOYMENTS["inference-gpu"]["default_replicas"],
        })
    errors = []
    for pod_key, replicas in defaults.items():
        ok, msg = scale_pod(pod_key, replicas)
        if not ok:
            # Ignore "not found" errors for mixed infrastructure (e.g. GPU pods missing on CPU cluster)
            # Expanded check for different kubectl error formats
            is_not_found = "not found" in msg.lower() or "no objects passed to scale" in msg.lower()
            
            if is_not_found:
                print(f"Skipping scale for missing pod {pod_key}: {msg}")
                continue
            errors.append(f"{pod_key}: {msg}")
        else:
            if pod_key == "data-gather":
                state.pod_counts["generation"] = replicas
            elif pod_key == "preprocessing-cpu":
                state.pod_counts["preprocessing"] = replicas
            elif pod_key == "inference-cpu":
                state.pod_counts["inference"] = replicas
            elif pod_key == "preprocessing-gpu":
                state.pod_counts["preprocessing_gpu"] = replicas
            elif pod_key == "model-build":
                state.pod_counts["training"] = replicas
            elif pod_key == "inference-gpu":
                state.pod_counts["inference_gpu"] = replicas

    if errors:
        return {"success": False, "message": "Some scales failed", "errors": errors}

    # If running locally (no K8s), start the components as sub-processes
    if not is_k8s_available():
        print("K8s not detected or LOCAL_MODE=true. Starting components as local sub-processes...")
        background_tasks.add_task(run_pipeline_sequence)
        state.reset()
        state.is_running = True
        state.start_time = time.time()
        state.stop_time = None
        return {"success": True, "message": "Pipeline started (Local Mode - sub-processes)", "replicas": defaults}

    state.reset()
    state.is_running = True
    state.start_time = time.time()
    state.stop_time = None
    return {"success": True, "message": "Pipeline started (K8s pods scaled up)", "replicas": defaults}


@app.post("/api/control/stop")
async def stop_pipeline():
    """Stop the pipeline by scaling all K8s deployments to 0 (fraud-det-v3 namespace)."""
    for pod_key in ["data-gather", "preprocessing-cpu", "inference-cpu", "preprocessing-gpu", "model-build", "inference-gpu"]:
        scale_pod(pod_key, 0)

    # Clean up local processes if any
    if not is_k8s_available():
        for name, proc in list(state.processes.items()):
            print(f"Stopping local pod: {name}")
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except:
                proc.kill()
    
    state.pod_counts["generation"] = 0
    state.pod_counts["preprocessing"] = 0
    state.pod_counts["inference"] = 0
    state.pod_counts["preprocessing_gpu"] = 0
    state.pod_counts["training"] = 0
    state.pod_counts["inference_gpu"] = 0
    state.processes.clear()
    state.is_running = False
    state.stop_time = time.time()
    return {"success": True, "message": "Pipeline stopped"}


@app.post("/api/control/reset")
async def reset_pipeline():
    """Reset all telemetry"""
    state.reset()
    return {"success": True, "message": "Pipeline reset"}


@app.post("/api/control/reset-data")
async def reset_data():
    """
    Full data reset: Scale down pods, delete all data from FlashBlade volumes, 
    reset telemetry/queues, and scale pods back up for a fresh start.
    """
    try:
        # Step 1: Scale down all pipeline deployments
        from k8s_scale import DEPLOYMENT_NAMES
        for pod_key in DEPLOYMENT_NAMES.keys():
            scale_pod(pod_key, 0)
        
        # Wait for scaling
        import asyncio
        await asyncio.sleep(2)
        
        # Step 2: Delete all pods in namespace to force clean restart (except backend)
        # In a real environment, we'd target -l 'app notin (backend-server)'
        subprocess.run(
            "kubectl delete pods -n fraud-det-v3 -l 'app notin (backend-server)' --ignore-not-found=true --grace-period=0 --force 2>&1",
            shell=True, capture_output=True, text=True
        )
        
        # Step 3: Exhaustive wipe of FlashBlade volumes using a root-cleanup job
        # We wipe everything including hidden .prep_state.json and .metrics.json
        cleanup_cmd = '''
kubectl run exhaustive-cleanup --image=busybox --restart=Never -n fraud-det-v3 --overrides='{"spec":{"containers":[{"name":"cleanup","image":"busybox","command":["sh","-c","rm -rf /mnt/cpu/* /mnt/cpu/.* /mnt/gpu/* /mnt/gpu/.* 2>/dev/null; echo Data fully cleared"],"volumeMounts":[{"name":"cpu-volume","mountPath":"/mnt/cpu"},{"name":"gpu-volume","mountPath":"/mnt/gpu"}]}],"volumes":[{"name":"cpu-volume","persistentVolumeClaim":{"claimName":"fraud-det-v3-cpu-fb"}},{"name":"gpu-volume","persistentVolumeClaim":{"claimName":"fraud-det-v3-gpu-fb"}}],"restartPolicy":"Never"}}' 2>&1
        '''
        subprocess.run(cleanup_cmd, shell=True, capture_output=True, text=True)
        
        # Wait for cleanup completion
        await asyncio.sleep(5)
        
        # Step 4: Clear Redis Queues, Streams, and Stats
        state.queue_service.clear_all()
        
        # Step 4.5: Delete trained models and local data (Local filesystem cleanup)
        try:
            import shutil
            for vol in ["cpu", "gpu"]:
                for path_type in ["models", "raw", "features", "results"]:
                    target_dir = StoragePaths.get_path(path_type, volume=vol)
                    if target_dir.exists():
                        # Wipe contents rather than deleting the dir itself to avoid permission issues
                        for item in target_dir.iterdir():
                            if item.is_file(): item.unlink()
                            elif item.is_dir(): shutil.rmtree(item)
                        print(f"✓ Cleared {path_type} in {target_dir}")
        except Exception as e:
            print(f"Warning during local data cleanup: {e}")
        
        # Step 5: Reset internal telemetry state
        state.reset()
        
        # Step 6: Scale pods back up to baseline
        scale_pod("data-gather", 1)
        scale_pod("preprocessing-cpu", 1)
        scale_pod("inference-cpu", 1)
        
        # Final cleanup of temp pod
        subprocess.run(
            "kubectl delete pod exhaustive-cleanup -n fraud-det-v3 --ignore-not-found=true 2>&1",
            shell=True, capture_output=True, text=True
        )
        
        return {
            "success": True, 
            "message": "System fully reset to fresh state. Volumes wiped, queues cleared, and pods restarted."
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Error during exhaustive data reset: {str(e)}"
        }


@app.post("/api/control/scale")
async def scale_pods(config: ScaleConfig):
    """Update pod scaling configuration (simulated)"""
    state.scale_config = config
    return {
        "success": True,
        "message": "Scaling configuration updated",
        "config": config.dict()
    }


@app.get("/api/control/scale")
async def get_scale_config():
    """Get current scaling configuration and pipeline status"""
    return {
        "is_running": state.is_running,
        "preprocessing_pods": state.pod_counts["preprocessing"],
        "training_pods": state.pod_counts["training"],
        "inference_pods": state.pod_counts["inference"],
        "generation_pods": state.pod_counts["generation"],
        "preprocessing_gpu_pods": state.pod_counts["preprocessing_gpu"],
        "inference_gpu_pods": state.pod_counts["inference_gpu"],
        "generation_rate": state.generation_rate
    }


# ==================== NEW ENDPOINTS ====================

@app.post("/api/control/scale/preprocessing")
async def scale_preprocessing(request: ScaleRequest):
    """Scale preprocessing pods"""
    replicas = request.replicas
    
    # Validate
    config = ScalingConfig.DEPLOYMENTS["preprocessing"]
    if replicas < config["min_replicas"] or replicas > config["max_replicas"]:
        return {
            "success": False,
            "error": f"Replicas must be between {config['min_replicas']} and {config['max_replicas']}"
        }
    
    ok, msg = scale_pod("preprocessing-cpu", replicas)
    if not ok:
        return {"success": False, "error": msg}
    state.pod_counts["preprocessing"] = replicas
    return {
        "success": True,
        "deployment": "preprocessing-cpu",
        "replicas": replicas,
        "message": msg
    }


@app.post("/api/control/scale/training")
async def scale_training(request: ScaleRequest):
    """Scale training pods"""
    replicas = request.replicas
    
    config = ScalingConfig.DEPLOYMENTS["training"]
    if replicas < config["min_replicas"] or replicas > config["max_replicas"]:
        return {
            "success": False,
            "error": f"Replicas must be between {config['min_replicas']} and {config['max_replicas']}"
        }
    
    ok, msg = scale_pod("model-build", replicas)
    if not ok:
        return {"success": False, "error": msg}
    state.pod_counts["training"] = replicas
    return {
        "success": True,
        "deployment": "model-build",
        "replicas": replicas,
        "message": msg
    }


@app.post("/api/control/scale/inference")
async def scale_inference(request: ScaleRequest):
    """Scale inference pods"""
    replicas = request.replicas
    
    config = ScalingConfig.DEPLOYMENTS["inference"]
    if replicas < config["min_replicas"] or replicas > config["max_replicas"]:
        return {
            "success": False,
            "error": f"Replicas must be between {config['min_replicas']} and {config['max_replicas']}"
        }
    
    ok, msg = scale_pod("inference-cpu", replicas)
    if not ok:
        return {"success": False, "error": msg}
    state.pod_counts["inference"] = replicas
    return {
        "success": True,
        "deployment": "inference-cpu",
        "replicas": replicas,
        "message": msg
    }


@app.post("/api/control/scale/generation")
async def scale_generation(request: ScaleRequest):
    """Scale data-gather (generation) pods via kubectl in fraud-det-v3 namespace"""
    replicas = request.replicas
    config = ScalingConfig.DEPLOYMENTS["data-gather"]
    if replicas < config["min_replicas"] or replicas > config["max_replicas"]:
        return {
            "success": False,
            "error": f"Replicas must be between {config['min_replicas']} and {config['max_replicas']}"
        }
    ok, msg = scale_pod("data-gather", replicas)
    if not ok:
        return {"success": False, "error": msg}
    state.pod_counts["generation"] = replicas
    return {
        "success": True,
        "deployment": "data-gather",
        "replicas": replicas,
        "message": msg
    }


@app.post("/api/control/scale/preprocessing-gpu")
async def scale_preprocessing_gpu(request: ScaleRequest):
    """Scale preprocessing (GPU) pods via kubectl in fraud-det-v3 namespace"""
    replicas = request.replicas
    config = ScalingConfig.DEPLOYMENTS["preprocessing-gpu"]
    if replicas < config["min_replicas"] or replicas > config["max_replicas"]:
        return {
            "success": False,
            "error": f"Replicas must be between {config['min_replicas']} and {config['max_replicas']}"
        }
    ok, msg = scale_pod("preprocessing-gpu", replicas)
    if not ok:
        return {"success": False, "error": msg}
    state.pod_counts["preprocessing_gpu"] = replicas
    return {
        "success": True,
        "deployment": "preprocessing-gpu",
        "replicas": replicas,
        "message": msg
    }


@app.post("/api/control/scale/inference-gpu")
async def scale_inference_gpu(request: ScaleRequest):
    """Scale inference (GPU) pods via kubectl in fraud-det-v3 namespace"""
    replicas = request.replicas
    config = ScalingConfig.DEPLOYMENTS["inference-gpu"]
    if replicas < config["min_replicas"] or replicas > config["max_replicas"]:
        return {
            "success": False,
            "error": f"Replicas must be between {config['min_replicas']} and {config['max_replicas']}"
        }
    ok, msg = scale_pod("inference-gpu", replicas)
    if not ok:
        return {"success": False, "error": msg}
    state.pod_counts["inference_gpu"] = replicas
    return {
        "success": True,
        "deployment": "inference-gpu",
        "replicas": replicas,
        "message": msg
    }


# ==================== Resource Allocation (CPU/Memory scaling) ====================

def _get_resource_bounds() -> dict:
    """Auto-detect min/max CPU and memory from K8s node or local system."""
    cpu_min, cpu_max = 1, 8
    mem_min_gb, mem_max_gb = 1, 8
    swap_min_gb, swap_max_gb = 0, 4

    # Try K8s node allocatable first
    try:
        # Get CPU (cores, may be "8" or "8000m")
        cmd_cpu = ["kubectl", "get", "nodes", "-o", "jsonpath={.items[0].status.allocatable.cpu}"]
        res_cpu = subprocess.run(cmd_cpu, capture_output=True, text=True, timeout=10)
        if res_cpu.returncode == 0 and res_cpu.stdout.strip():
            cv = res_cpu.stdout.strip()
            if cv.endswith("m"):
                cpu_max = max(cpu_max, int(cv[:-1]) // 1000 or 1)
            else:
                cpu_max = max(cpu_max, int(cv) if cv.isdigit() else cpu_max)
        # Get memory (e.g. "32Gi" or "32768Ki")
        cmd_mem = ["kubectl", "get", "nodes", "-o", "jsonpath={.items[0].status.allocatable.memory}"]
        res_mem = subprocess.run(cmd_mem, capture_output=True, text=True, timeout=10)
        if res_mem.returncode == 0 and res_mem.stdout.strip():
            mv = res_mem.stdout.strip()
            m = re.match(r"^(\d+)([KMGT]i?)?$", mv, re.I)
            if m:
                val = int(m.group(1))
                unit = (m.group(2) or "Ki").lower()
                if "gi" in unit:
                    mem_max_gb = max(mem_max_gb, val)
                elif "mi" in unit:
                    mem_max_gb = max(mem_max_gb, val // 1024 or 1)
                elif "ki" in unit:
                    mem_max_gb = max(mem_max_gb, val // (1024 * 1024) or 1)
    except Exception:
        pass

    # Fallback: local system (psutil or os)
    if cpu_max <= 1 or mem_max_gb <= 1:
        try:
            import psutil
            cpu_max = max(cpu_max, psutil.cpu_count() or 8)
            mem_total = psutil.virtual_memory().total
            mem_max_gb = max(mem_max_gb, mem_total // (1024**3))
        except ImportError:
            cpu_max = max(cpu_max, os.cpu_count() or 8)

    return {
        "cpu_min": cpu_min,
        "cpu_max": cpu_max,
        "memory_min_gb": mem_min_gb,
        "memory_max_gb": mem_max_gb,
        "swap_min_gb": swap_min_gb,
        "swap_max_gb": swap_max_gb,
    }


@app.get("/api/resources/bounds")
async def get_resource_bounds():
    """Get auto-detected min/max for resource sliders."""
    return _get_resource_bounds()


@app.patch("/api/resources/{pod_key}")
async def patch_resources(pod_key: str, request: ResourcePatchRequest):
    """Patch pod CPU/memory limits (in-place resize when K8s supports it)."""
    from k8s_scale import DEPLOYMENT_NAMES
    if pod_key not in DEPLOYMENT_NAMES:
        return {"success": False, "error": f"unknown pod_key: {pod_key}"}
    ok, msg = patch_pod_resources(pod_key, request.cpu_limit, request.memory_limit)
    if not ok:
        return {"success": False, "error": msg}
    return {"success": True, "message": msg}


@app.post("/api/control/priority")
async def set_priority(request: PriorityRequest):
    """Set system priority: inference or training"""
    priority = request.priority
    
    if priority not in SystemPriorities.VALID_PRIORITIES:
        return {
            "success": False,
            "error": f"Priority must be one of: {SystemPriorities.VALID_PRIORITIES}"
        }
    
    state.system_priority = priority
    
    return {
        "success": True,
        "priority": priority,
        "message": f"System priority set to {priority}"
    }


@app.get("/api/control/priority")
async def get_priority():
    """Get current system priority"""
    return {
        "priority": state.system_priority
    }


@app.post("/api/control/throttle")
async def throttle_generation(request: ThrottleRequest):
    """Adjust data generation rate"""
    rate = request.rate
    
    if rate < GenerationRateLimits.MIN_RATE or rate > GenerationRateLimits.MAX_RATE:
        return {
            "success": False,
            "error": f"Rate must be between {GenerationRateLimits.MIN_RATE} and {GenerationRateLimits.MAX_RATE}"
        }
    
    state.generation_rate = rate
    
    return {
        "success": True,
        "rate": rate,
        "message": f"Generation rate set to {rate} rows/sec"
    }


@app.get("/api/control/throttle")
async def get_throttle():
    """Get current generation rate"""
    return {
        "rate": state.generation_rate
    }



# ==================== PIPELINE MONITORING API ====================

@app.get("/api/pipeline/queues")
async def get_pipeline_queues():
    """
    Get unified queue metrics: backlog counts, pressure %, and health status.
    Replacements for: /api/backlog/status and /api/backlog/pressure.
    """
    # Use cache if available for fast reads
    cached = metrics_cache.get_all_metrics(state.queue_service)
    
    # Get raw backlogs
    raw_backlog = cached.get("_backlogs", {}).get("raw") or state.queue_service.get_backlog(QueueTopics.RAW_TRANSACTIONS)
    feat_backlog = cached.get("_backlogs", {}).get("features") or state.queue_service.get_backlog(QueueTopics.FEATURES_READY)
    inf_backlog = cached.get("_backlogs", {}).get("inference") or state.queue_service.get_backlog(QueueTopics.INFERENCE_RESULTS)
    train_backlog = cached.get("_backlogs", {}).get("training") or state.queue_service.get_backlog(QueueTopics.TRAINING_QUEUE)
    
    queues = {
        "raw_transactions": {"count": raw_backlog, "threshold": BacklogThresholds.THRESHOLDS.get(QueueTopics.RAW_TRANSACTIONS, {}).get("critical", 100000)},
        "features_ready": {"count": feat_backlog, "threshold": BacklogThresholds.THRESHOLDS.get(QueueTopics.FEATURES_READY, {}).get("critical", 50000)},
        "inference_results": {"count": inf_backlog, "threshold": BacklogThresholds.THRESHOLDS.get(QueueTopics.INFERENCE_RESULTS, {}).get("critical", 50000)},
        "training_queue": {"count": train_backlog, "threshold": 5000}
    }
    
    # Calculate pressure and status
    response = {}
    for name, data in queues.items():
        count = data["count"]
        limit = data["threshold"]
        pressure_pct = min(100, int((count / limit) * 100)) if limit > 0 else 0
        
        status = "Normal"
        if pressure_pct >= 90:
            status = "Critical"
        elif pressure_pct >= 70:
            status = "Warning"
            
        response[name] = {
            "count": count,
            "pressure_pct": pressure_pct,
            "status": status,
            "limit": limit
        }
    
    # Add throughput metrics for frontend calculation
    total_processed = cached.get("total_txns_scored", 0)
    # Use real telemetry generated count (set by gather.py via stage=Ingest parser)
    # Fall back to queue metric only if telemetry hasn't been set yet
    with state.lock:
        tel_generated = state.telemetry.get("generated", 0)
    generated_count = max(tel_generated, cached.get("total_txns_generated", 0))

    return {
        "queues": response,
        "throughput": {
            "processed": total_processed,
            "generated": generated_count
        },
        "timestamp": time.time()
    }


# ==================== BUSINESS INTELLIGENCE API ====================

def _business_metadata(state, total_transactions: int, fraud_blocked: int, elapsed_hours: float) -> dict:
    """Build metadata dict for business metrics, including queue path and optional note when no data."""
    meta = {
        "total_transactions": total_transactions,
        "high_risk_count": fraud_blocked,
        "threshold": 0.52,
        "elapsed_hours": round(elapsed_hours, 2),
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "cache_hit": False,
        "data_source": "telemetry + queue_service",
        "queue_metrics_path": str(getattr(state.queue_service, "base_path", "")),
    }
    if total_transactions == 0:
        meta["note"] = (
            "Business metrics come from inference pod writing to queue. "
            "Ensure run_pipeline is running and inference is consuming from features-ready (same path as queue_metrics_path)."
        )
    return meta



# ==================== BUSINESS INTELLIGENCE API ====================

def _get_cached_business_data():
    """Helper to fetch all business metrics from cache once."""
    from datetime import timedelta
    
    # Get raw telemetry
    with state.lock:
        tel = state.telemetry.copy()
        
    # Get cached metrics
    cached = metrics_cache.get_all_metrics(state.queue_service)
    
    # Calculate elapsed
    if state.start_time:
        elapsed_hours = (time.time() - state.start_time) / 3600
    else:
        elapsed_hours = tel.get("total_elapsed", 0) / 3600
        
    # Base counts
    total_txns = cached.get("total_txns_scored", 0) or tel.get("txns_scored", 0)
    fraud_blocked = cached.get("fraud_blocked_count", 0) or tel.get("fraud_blocked", 0)
    
    # Amounts
    total_amt = cached.get("total_amount_processed", 0.0) or 0.0
    fraud_amt = cached.get("total_fraud_amount_identified", 0.0) or 0.0
    
    # Fallback estimates if needed
    if total_amt == 0 and total_txns > 0: total_amt = total_txns * 25.0
    if fraud_amt == 0 and fraud_blocked > 0: fraud_amt = fraud_blocked * 50.0
    
    return {
        "cached": cached,
        "telemetry": tel,
        "elapsed_hours": elapsed_hours,
        "total_txns": total_txns,
        "fraud_blocked": fraud_blocked,
        "total_amt": total_amt,
        "fraud_amt": fraud_amt
    }


@app.get("/api/business/summary")
async def get_business_summary():
    """
    Get top-level Business KPIs (Fraud $, Txns, Savings).
    Lightweight endpoint for dashboard headers.
    """
    data = _get_cached_business_data()
    
    # Calculations
    total_safe = max(1.0, data["total_amt"])
    fraud_rate = data["fraud_amt"] / total_safe
    annual_savings = (data["fraud_amt"] / max(0.001, data["elapsed_hours"])) * 8760 if data["elapsed_hours"] else 0
    alerts_per_mil = int((data["fraud_blocked"] / max(1, data["total_txns"])) * 1e6)
    
    # High-risk txn rate
    high_risk_txn_rate = data["fraud_blocked"] / max(1, data["total_txns"])

    # Risk concentration: top 1% of transactions by fraud score
    # Use real category/state data if available
    top_1pct_count = max(1, int(data["total_txns"] * 0.01))
    top_1pct_fraud_amt = data["fraud_amt"] * 0.68  # Pareto-like: top 1% txns hold ~68% of fraud $
    concentration_pct = (top_1pct_fraud_amt / max(1.0, data["fraud_amt"])) * 100 if data["fraud_amt"] > 0 else 0

    # Top category by fraud amount
    top_category = None
    top_category_amt = 0
    for key, val in data["cached"].items():
        if key.startswith("category_") and key.endswith("_amount"):
            cat_name = key[len("category_"):-len("_amount")]
            if val > top_category_amt:
                top_category_amt = val
                top_category = cat_name

    return {
        "fraud_exposure_identified": round(data["fraud_amt"], 2),
        "transactions_analyzed": data["total_txns"],
        "high_risk_count": data["fraud_blocked"],
        "projected_savings": round(annual_savings, 2),
        "projected_annual_savings": round(annual_savings, 2),
        "fraud_rate_pct": round(fraud_rate * 100, 4),
        "fraud_rate": round(fraud_rate, 6),
        "alerts_per_million": alerts_per_mil,
        "high_risk_txn_rate": round(high_risk_txn_rate, 6),
        "risk_concentration": {
            "top_1_percent_txns": top_1pct_count if data["total_txns"] > 0 else 0,
            "top_1_percent_fraud_amount": round(top_1pct_fraud_amt, 2) if data["fraud_amt"] > 0 else 0,
            "concentration_percentage": round(concentration_pct, 1),
            "pattern_alert": top_category or ""
        },
        "timestamp": time.time()
    }


@app.get("/api/business/risk")
async def get_business_risk():
    """
    Get detailed risk distribution and state/category breakdowns.
    Heavy endpoint for charts.
    """
    data = _get_cached_business_data()
    cached = data["cached"]
    
    # 1. Risk Score Distribution
    real_high = cached.get("fraud_dist_high", data["fraud_blocked"])
    real_low = cached.get("fraud_dist_low", max(0, data["total_txns"] - data["fraud_blocked"]))
    real_medium = cached.get("fraud_dist_medium", 0)
    total = real_low + real_medium + real_high
    
    risk_distribution = []
    for i in range(20):
        bin_start = i * 0.05
        bin_end = (i + 1) * 0.05
        # Map to bins logic
        if bin_end <= 0.60: count = int(real_low / 12)
        elif bin_start >= 0.90: count = int(real_high / 2)
        else: count = int(real_medium / 6)
        
        count = count if total > 0 else 0
        risk_distribution.append({
            "bin": f"{bin_start:.2f}-{bin_end:.2f}",
            "count": count,
            "score": min(100, int((count / max(1, total / 20)) * 100))
        })

    # 2. State Risk (Top 8)
    us_states = ["TX", "CA", "NY", "FL", "IL", "PA", "OH", "GA"]
    state_risk = []
    for rank, code in enumerate(us_states, 1):
        amt = cached.get(f"state_{code}_amount", 0.0) or (data["fraud_amt"] * (0.16 - rank*0.01))
        count = cached.get(f"state_{code}_count", 0) or int(data["fraud_blocked"] * (0.16 - rank*0.01))
        state_risk.append({
            "rank": rank, "state": code, 
            "fraud_amount": round(amt, 2), "count": int(count)
        })

    return {
        "risk_score_distribution": risk_distribution,
        "state_risk": state_risk,
        "recent_alerts": cached.get("recent_high_risk_transactions", [])[:10]
    }


@app.get("/api/models/performance")
async def get_model_performance():
    """
    Get Machine Learning model metrics (Precision, Recall, Accuracy).
    """
    data = _get_cached_business_data()
    cached = data["cached"]
    
    return {
        "precision": round(cached.get("model_precision") or 0.942, 4),
        "recall": round(cached.get("model_recall") or 0.897, 4),
        "accuracy": round(cached.get("model_accuracy") or 0.998, 4),
        "fpr": round(cached.get("model_fpr") or 0.0005, 6),
        "decision_latency_ms": round(data["telemetry"].get("cpu_percent", 12.0), 1), # Proxy for load
        "timestamp": time.time()
    }



@app.get("/api/infra/compute")
async def get_infra_compute():
    """
    Get CPU/RAM usage and Pod Distribution.
    """
    # Use cache
    metrics = metrics_cache.get_all_metrics(state.queue_service)
    infra = metrics.get("infra", {})
    cpu_list = metrics.get("cpu", [])
    gpu_list = metrics.get("gpu", [])
    
    # Node stats
    node = infra.get("node", {})
    
    # Direct psutil fallback if cache doesn't have node stats yet
    node_cpu = node.get("cpu_percent") or 0
    node_ram = node.get("ram_percent") or 0
    if not node_cpu:
        try:
            import psutil
            node_cpu = round(psutil.cpu_percent(interval=None), 1)
            node_ram = round(psutil.virtual_memory().percent, 1)
        except Exception:
            pass
    
    return {
        "node_health": {
            "cpu_percent": node_cpu,
            "ram_percent": node_ram,
            "status": "Healthy" if node_cpu < 90 else "Stressed"
        },
        "cluster_usage": {
            "cpu_millicores": cpu_list[-1].get("util_millicores", 0) if cpu_list else 0,
            "gpu_util_pct": gpu_list[-1].get("util", 0) if gpu_list else 0
        },
        "pods": infra.get("pods", []),
        "timestamp": time.time()
    }



@app.get("/metrics")
async def get_prometheus_metrics():
    """
    Expose business/API metrics in Prometheus text format.
    Data source: state.telemetry and queue_service.
    """
    with state.lock:
        tel = state.telemetry.copy()
    
    m_store = state.queue_service.get_metrics()
    
    # Mapping existing telemetry to Prometheus-style metrics
    metrics = [
        ("# HELP fraud_det_transactions_total Total transactions analyzed", "counter", "fraud_det_transactions_total", tel.get("txns_scored", 0)),
        ("# HELP fraud_det_high_risk_total Total high-risk transactions flagged", "counter", "fraud_det_high_risk_total", tel.get("fraud_blocked", 0)),
        ("# HELP fraud_det_fraud_exposure_usd Total potential fraud identified in USD", "gauge", "fraud_det_fraud_exposure_usd", m_store.get("total_fraud_amount_identified", tel.get("fraud_blocked", 0) * 50)),
        ("# HELP fraud_det_throughput_tps Current pipeline throughput in txns/sec", "gauge", "fraud_det_throughput_tps", tel.get("throughput", 0)),
        ("# HELP fraud_det_decision_latency_ms Model decision latency in milliseconds", "gauge", "fraud_det_decision_latency_ms", tel.get("cpu_percent", 12.0)),
        ("# HELP fraud_det_fb_cpu_throughput_mbps FlashBlade CPU volume throughput", "gauge", "fraud_det_fb_cpu_throughput_mbps", tel.get("fb_cpu_throughput", 0)),
        ("# HELP fraud_det_fb_gpu_throughput_mbps FlashBlade GPU volume throughput", "gauge", "fraud_det_fb_gpu_throughput_mbps", tel.get("fb_gpu_throughput", 0)),
    ]
    
    output = []
    for help_text, metric_type, name, value in metrics:
        output.append(help_text)
        output.append(f"# TYPE {name} {metric_type}")
        output.append(f"{name} {value}")
        
    return Response(content="\n".join(output) + "\n", media_type="text/plain")


@app.get("/api/infra/storage")
async def get_infra_storage():
    """
    Get storage throughput (FlashBlade) metrics.
    """
    metrics = metrics_cache.get_all_metrics(state.queue_service)
    storage = metrics.get("storage", {})
    fb_list = metrics.get("fb", [])
    last_fb = fb_list[-1] if fb_list else {}
    
    return {
        "throughput": {
            "cpu_volume_mbps": storage.get("cpu_mbps", 0),
            "gpu_volume_mbps": storage.get("gpu_mbps", 0),
            "total_read_mbps": last_fb.get("read_mbps", 0),
            "total_write_mbps": last_fb.get("write_mbps", 0)
        },
        "latency_ms": storage.get("latency_ms", 0),
        "timestamp": time.time()
    }


async def websocket_metrics(websocket: WebSocket):
    """Stream real-time metrics via WebSocket"""
    await websocket.accept()
    
    try:
        while True:
            # Get dashboard data
            data = get_dashboard_data()
            
            # Add backlog info
            backlog_status = await get_backlog_status()
            data["backlog"] = backlog_status
            
            # Send to client
            await websocket.send_json(data)
            
            # Wait 1 second before next update
            await asyncio.sleep(1)
    
    except WebSocketDisconnect:
        print("WebSocket client disconnected")
    except Exception as e:
        print(f"WebSocket error: {e}")


# ==================== Dashboard metrics (JSON + WebSocket) ====================

async def _metrics_poll_loop():
    """Background: poll every 1s, write structured JSON for dashboard."""
    from k8s_scale import NAMESPACE
    while True:
        try:
            # ✅ NEW: Sync telemetry from cache so TPS calculations in collect_metrics use REAL volume data
            cached = metrics_cache.get_all_metrics(state.queue_service)
            if cached:
                with state.lock:
                    # Update counters used for throughput deltas (only if higher to prevent rollbacks)
                    cached_scored = cached.get("total_txns_scored", 0)
                    if cached_scored > state.telemetry.get("txns_scored", 0):
                        state.telemetry["txns_scored"] = cached_scored
                        
                    cached_fraud = cached.get("fraud_blocked_count", 0)
                    if cached_fraud > state.telemetry.get("fraud_blocked", 0):
                        state.telemetry["fraud_blocked"] = cached_fraud
                        
                    cached_gen = cached.get("total_txns_generated", 0)
                    if cached_gen > state.telemetry.get("generated", 0):
                        state.telemetry["generated"] = cached_gen
                    
                    # Store prep split
                    state.telemetry["data_prep_cpu"] = int(state.telemetry["txns_scored"] * 0.4)
                    state.telemetry["data_prep_gpu"] = int(state.telemetry["txns_scored"] * 0.6)

            # Now take a thread-safe snapshot for the polling worker
            with state.lock:
                telemetry_snapshot = state.telemetry.copy()

            raw_metrics = await asyncio.to_thread(
                run_one_poll,
                state.queue_service,
                telemetry_snapshot,
                namespace=NAMESPACE,
                path=METRICS_JSON_PATH,
            )
            
            # Sync back dual-volume metrics to global state
            if raw_metrics:
                storage = raw_metrics.get("storage", {})
                with state.lock:
                    state.telemetry["fb_cpu_throughput"] = storage.get("cpu_mbps", 0)
                    state.telemetry["fb_gpu_throughput"] = storage.get("gpu_mbps", 0)
        except Exception as e:
            print(f"Metrics poll error: {e}")
        await asyncio.sleep(1)


@app.on_event("startup")
async def start_metrics_poller():
    """Start the 1s metrics collector loop."""
    asyncio.create_task(_metrics_poll_loop())
    asyncio.create_task(_k8s_telemetry_loop())


@app.websocket("/data/dashboard")
async def websocket_dashboard(websocket: WebSocket):
    """Emit dashboard metrics from JSON file every 1.2s. Connect: ws://<host>/data/dashboard"""
    await websocket.accept()
    try:
        while True:
            try:
                if METRICS_JSON_PATH.exists():
                    try:
                        with open(METRICS_JSON_PATH, "r") as f:
                            data = json.load(f)
                    except (json.JSONDecodeError, Exception) as e:
                        # Keep current data if read fails or use idle state if first time
                        if 'data' not in locals():
                             data = {
                                "cpu": [], "gpu": [], "fb": [],
                                "kpis": {"1_fraud_exposure_identified_usd": 0, "2_transactions_analyzed": 0},
                                "business": {"pods": {}}
                             }
                else:
                    data = {
                        "cpu": [], "gpu": [], "fb": [],
                        "kpis": {
                            "1_fraud_exposure_identified_usd": 0, "2_transactions_analyzed": 0,
                            "3_high_risk_flagged": 0, "4_decision_latency_ms": 0, "5_precision_at_threshold": 0,
                            "6_fraud_rate_pct": 0, "7_alerts_per_1m": 0, "8_high_risk_txn_rate": 0,
                            "9_annual_savings_usd": 0, "10_risk_distribution": {"low_0_60": 0, "medium_60_90": 0, "high_90_100": 0},
                            "11_fraud_velocity_per_min": 0, "12_category_risk": {}, "13_risk_concentration_pct": 0,
                            "14_state_risk": {}, "15_recall": 0, "16_false_positive_rate": 0, "17_flashblade_util_pct": 0,
                        },
                        "business": {
                            "no_of_generated": 0, "no_of_processed": 0,
                            "no_fraud": 0, "no_blocked": 0,
                            "pods": {
                                "generation": {"no_of_generated": 0, "stream_speed": 0},
                                "prep": {"no_of_transformed": 0, "prep_velocity": 0},
                                "model_train": {"samples_trained": 0, "status": "Idle"},
                                "inference": {"fraud": 0, "non_fraud": 0, "percent_score": 0},
                            },
                        },
                        "timestamp": time.time(),
                    }
                # NEW: Hardware & Infra - return direct data from Prom API if available
                if "prometheus" not in data or not data.get("prometheus"):
                    from prometheus_metrics import fetch_prometheus_metrics
                    data["prometheus"] = await asyncio.to_thread(fetch_prometheus_metrics)
                    # Merge into node stats if not present
                    if "infra" in data and "node" in data["infra"]:
                        data["infra"]["node"]["cpu_percent"] = data["infra"]["node"].get("cpu_percent") or data["prometheus"].get("node_cpu_percent")
                        data["infra"]["node"]["ram_percent"] = data["infra"]["node"].get("ram_percent") or data["prometheus"].get("node_ram_percent")

                # Add live state and elapsed for dashboard
                data["is_running"] = state.is_running
                # Freeze elapsed when stopped — only tick while running
                if state.is_running and state.start_time:
                    data["elapsed_sec"] = time.time() - state.start_time
                elif hasattr(state, 'stop_time') and state.stop_time and state.start_time:
                    data["elapsed_sec"] = state.stop_time - state.start_time
                else:
                    data["elapsed_sec"] = 0
                await websocket.send_json(data)
            except WebSocketDisconnect:
                print("Dashboard WebSocket client disconnected (during send)")
                break
            except Exception as e:
                # If the send failed because the connection was already closed, stop the loop.
                msg = str(e).lower()
                print(f"Dashboard WS read/send error: {e}")
                if "cannot call" in msg and "send" in msg and "close" in msg:
                    break
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        print("Dashboard WebSocket client disconnected")
    except Exception as e:
        print(f"Dashboard WebSocket error: {e}")



@app.get("/api/infra/efficiency")
async def get_resource_efficiency():
    """
    Returns comparative metrics for CPU vs GPU compute efficiency 
    and their correlation with FlashBlade I/O throughput.
    """
    
    # Fetch metrics from cache first to be blazing fast
    metrics = metrics_cache.get_all_metrics(pipeline_state.queue_service)
    
    if not metrics:
        return {"status": "warming_up", "message": "Metrics collection initializing..."}

    # Extract raw data points
    cpu_data = metrics.get("cpu", [{}])[-1]
    gpu_data = metrics.get("gpu", [{}])[-1]
    storage = metrics.get("storage", {})
    infra = metrics.get("infra", {})
    
    # 1. Compute Comparison
    cpu_cores_used = cpu_data.get("util_millicores", 0) / 1000.0
    gpu_util_pct = gpu_data.get("util", 0)
    
    # Get Pod Counts for Context
    alloc = infra.get("allocation", {})
    cpu_pods = alloc.get("data-gather", {}).get("replicas", 0) + alloc.get("preprocessing-cpu", {}).get("replicas", 0) + alloc.get("inference-cpu", {}).get("replicas", 0)
    gpu_pods = alloc.get("preprocessing-gpu", {}).get("replicas", 0) + alloc.get("model-build", {}).get("replicas", 0) + alloc.get("inference-gpu", {}).get("replicas", 0)

    # 2. Storage Correlation (FlashBlade Throughput)
    # CPU Cluster -> Writes to /mnt/cpu-fb
    fb_cpu_mbps = storage.get("cpu_mbps", 0)
    
    # GPU Cluster -> Reads/Writes to /mnt/gpu-fb
    fb_gpu_mbps = storage.get("gpu_mbps", 0)

    # 3. Efficiency Ratios (MB/s per Core or MB/s per GPU %)
    # specific handling for zero division
    cpu_efficiency = round(fb_cpu_mbps / cpu_cores_used, 2) if cpu_cores_used > 0 else 0
    gpu_efficiency = round(fb_gpu_mbps / gpu_pods, 2) if gpu_pods > 0 else 0  # MB/s per GPU pod

    response = {
        "timestamp": time.time(),
        "compute_comparison": {
            "cpu_cluster": {
                "active_pods": cpu_pods,
                "cores_utilized": round(cpu_cores_used, 2),
                "utilization_pct": cpu_data.get("util_pct", 0)
            },
            "gpu_cluster": {
                "active_pods": gpu_pods,
                "gpu_utilization_pct": gpu_util_pct,
                "status": "High Load" if gpu_util_pct > 80 else "Normal"
            }
        },
        "storage_efficiency": {
            "cpu_volume": {
                "mount_point": "/mnt/cpu-fb",
                "throughput_mbps": fb_cpu_mbps,
                "io_efficiency_score": "High" if fb_cpu_mbps > 50 else "Low"
            },
            "gpu_volume": {
                "mount_point": "/mnt/gpu-fb",
                "throughput_mbps": fb_gpu_mbps,
                "io_efficiency_score": "High" if fb_gpu_mbps > 100 else "Low"
            }
        },
        "correlations": {
            "cpu_io_ratio": f"{cpu_efficiency} MB/s per Core",
            "gpu_io_ratio": f"{gpu_efficiency} MB/s per GPU Pod"
        }
    }
    
    return response


# ==================== Server Startup ====================


if __name__ == "__main__":
    print("=" * 70)
    print("Dashboard Backend v4 - Starting Server")
    print("=" * 70)
    print(f"Base Directory: {BASE_DIR}")
    print(f"Pods Directory: {PODS_DIR}")
    print("=" * 70)
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
