#!/usr/bin/env python3
"""
Backend Server for Dashboard v4
Orchestrates 4 pods and aggregates telemetry for real-time dashboard
"""

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

from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

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


# ==================== Data Models ====================

class ScaleConfig(BaseModel):
    cpu_prep_pods: int = 1
    gpu_prep_pods: int = 1
    cpu_infer_pods: int = 1
    gpu_infer_pods: int = 1
    generator_speed: int = 50000


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
            "cpu_percent": 0,
            "ram_percent": 0,
            "fraud_blocked": 0,
            "txns_scored": 0,
        }
        
        # Configuration
        self.scale_config = ScaleConfig()
        
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
            }
            self.start_time = None
    
    def update_telemetry(self, stage: str, status: str, rows: int, throughput: int, 
                         elapsed: float, cpu_percent: float, ram_percent: float):
        """Update telemetry from pod output"""
        with self.lock:
            self.telemetry["current_stage"] = stage
            self.telemetry["current_status"] = status
            self.telemetry["throughput"] = throughput
            self.telemetry["cpu_percent"] = cpu_percent
            self.telemetry["ram_percent"] = ram_percent
            
            # Map stage to appropriate counter
            if stage == "Ingest":
                self.telemetry["generated"] = rows
            elif stage == "Data Prep":
                # Split between CPU and GPU (simulate 40/60 split)
                self.telemetry["data_prep_cpu"] = int(rows * 0.4)
                self.telemetry["data_prep_gpu"] = int(rows * 0.6)
                self.telemetry["txns_scored"] = rows
            elif stage == "Model Train":
                self.telemetry["txns_scored"] = rows
            elif stage == "Inference":
                # Split between CPU and GPU (simulate 30/70 split)
                self.telemetry["inference_cpu"] = int(rows * 0.3)
                self.telemetry["inference_gpu"] = int(rows * 0.7)
                self.telemetry["txns_scored"] = rows
            
            # Calculate fraud metrics (0.5% fraud rate, $50 avg transaction)
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
            if "=" in part and "[TELEMETRY]" not in part:
                key, value = part.split("=", 1)
                key = key.strip()
                value = value.strip()
                
                if key in ["stage", "status"]:
                    data[key] = value
                elif key in ["rows", "throughput"]:
                    data[key] = int(value)
                elif key in ["elapsed", "cpu_cores", "ram_gb", "ram_percent"]:
                    data[key] = float(value)
        
        return data
    except Exception as e:
        print(f"Failed to parse telemetry: {e}")
        return None


def run_pod_async(pod_name: str, script_path: str):
    """Run a pod in background and capture telemetry"""
    print(f"Starting pod: {pod_name}")
    
    try:
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["OUTPUT_DIR"] = str(BASE_DIR / "run_data_output")
        env["INPUT_DIR"] = str(BASE_DIR / "run_data_output")
        
        if pod_name == "data-prep":
            env["INPUT_DIR"] = str(BASE_DIR / "run_data_output")
            env["OUTPUT_DIR"] = str(BASE_DIR / "run_features_output")
        elif pod_name == "model-build":
            env["INPUT_DIR"] = str(BASE_DIR / "run_features_output")
            env["OUTPUT_DIR"] = str(BASE_DIR / "run_models_output")
        
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
            print(f"[{pod_name}] {line}")
            
            # Parse telemetry
            telemetry = parse_telemetry_line(line)
            if telemetry:
                state.update_telemetry(
                    stage=telemetry.get("stage", "Unknown"),
                    status=telemetry.get("status", "Running"),
                    rows=telemetry.get("rows", 0),
                    throughput=telemetry.get("throughput", 0),
                    elapsed=telemetry.get("elapsed", 0.0),
                    cpu_percent=telemetry.get("ram_percent", 0.0),  # Using ram as proxy for CPU
                    ram_percent=telemetry.get("ram_percent", 0.0)
                )
        
        process.wait()
        
        if pod_name in state.processes:
            del state.processes[pod_name]
        
        print(f"Pod {pod_name} completed with code {process.returncode}")
        
    except Exception as e:
        print(f"Error running pod {pod_name}: {e}")
        if pod_name in state.processes:
            del state.processes[pod_name]


def run_pipeline_sequence():
    """Run all 4 pods in sequence"""
    state.is_running = True
    state.start_time = time.time()
    
    try:
        # Pod 1: Data Generation
        run_pod_async("data-gather", str(PODS_DIR / "data-gather" / "gather.py"))
        
        # Pod 2: Data Prep
        run_pod_async("data-prep", str(PODS_DIR / "data-prep" / "prepare.py"))
        
        # Pod 3: Model Training
        run_pod_async("model-build", str(PODS_DIR / "model-build" / "train.py"))
        
        # Pod 4: Inference (skip if Triton not available)
        # run_pod_async("inference", str(PODS_DIR / "inference" / "client.py"))
        
    finally:
        state.is_running = False
        print("Pipeline sequence completed")


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
    
    # Calculate backlog (simulated)
    total_generated = tel["generated"]
    total_processed = tel["data_prep_cpu"] + tel["data_prep_gpu"]
    backlog = max(0, total_generated - total_processed)
    
    # Calculate business metrics
    fraud_rate = 0.005
    avg_txn_amount = 50
    fraud_blocked = tel["fraud_blocked"]
    fraud_prevented_usd = fraud_blocked * avg_txn_amount
    
    # Simulated throughput split
    total_throughput = tel["throughput"]
    gpu_throughput = int(total_throughput * 0.7)
    cpu_throughput = int(total_throughput * 0.3)
    
    # FlashBlade metrics (simulated based on data velocity)
    data_velocity_gbps = (total_throughput * 256) / (1024**3)  # 256 bytes per row
    flashblade_util = min(15, int(data_velocity_gbps * 10))  # Cap at 15%
    
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
            "txns_scored": tel["txns_scored"],
            "fraud_blocked": fraud_blocked,
            "throughput": total_throughput
        },
        "fraud_dist": {
            "low": int(tel["txns_scored"] * 0.65),
            "medium": int(tel["txns_scored"] * 0.25),
            "high": int(tel["txns_scored"] * 0.10)
        },
        "flashblade": {
            "read": 1200 + (flashblade_util * 10),  # Simulated
            "write": 850 + (flashblade_util * 5),
            "util": flashblade_util,
            "headroom": round(100 / max(1, flashblade_util), 1)
        },
        "status": {
            "live": state.is_running,
            "elapsed": elapsed_str,
            "stage": tel["current_stage"],
            "status": tel["current_status"]
        }
    }


@app.post("/api/control/start")
async def start_pipeline(background_tasks: BackgroundTasks):
    """Start the pipeline"""
    if state.is_running:
        return {"success": False, "message": "Pipeline already running"}
    
    # Reset telemetry
    state.reset()
    
    # Run in background
    background_tasks.add_task(run_pipeline_sequence)
    
    return {"success": True, "message": "Pipeline started"}


@app.post("/api/control/stop")
async def stop_pipeline():
    """Stop all running pods"""
    if not state.is_running:
        return {"success": False, "message": "Pipeline not running"}
    
    # Terminate all processes
    for pod_name, process in list(state.processes.items()):
        try:
            process.terminate()
            process.wait(timeout=5)
        except Exception as e:
            print(f"Error stopping {pod_name}: {e}")
            process.kill()
    
    state.processes.clear()
    state.is_running = False
    
    return {"success": True, "message": "Pipeline stopped"}


@app.post("/api/control/reset")
async def reset_pipeline():
    """Reset all telemetry"""
    state.reset()
    return {"success": True, "message": "Pipeline reset"}


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
    """Get current scaling configuration"""
    return state.scale_config.dict()


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
