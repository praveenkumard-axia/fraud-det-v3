#!/usr/bin/env python3
"""
Master Orchestration Script - Optimized for No-API Demo
Supports running individual stages and providing telemetry via stats.json.
"""

import os
import subprocess
import time
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

# Logger to save all output to a file
class TeeLogger:
    def __init__(self, filename):
        self.terminal = sys.stdout
        self.filename = filename
        # Ensure log file exists
        if not Path(filename).exists():
            with open(filename, "w") as f: f.write("")
        self.log = open(filename, "a", encoding="utf-8")

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)
        self.log.flush()

    def flush(self):
        self.terminal.flush()
        self.log.flush()

BASE_DIR = Path(__file__).resolve().parent
LOG_FILE = BASE_DIR / "pipeline_report.txt"
DATA_OUT = BASE_DIR / "run_data_output"
FEAT_OUT = BASE_DIR / "run_features_output"
MODEL_OUT = BASE_DIR / "run_models_output"
STATS_FILE = BASE_DIR / "stats.json"

ENV = os.environ.copy()
ENV.update({
    "INPUT_DIR": str(DATA_OUT),
    "OUTPUT_DIR": str(DATA_OUT),
    "OMP_NUM_THREADS": "1"
})


def run_step(step_name, command):
    print(f"\n>>> STARTING STAGE: {step_name}")
    print(f"[TELEMETRY] stage={step_name} | status=Running | rows=0 | throughput=0 | elapsed=0.0 | cpu_cores=0.0 | ram_gb=0.0 | ram_percent=0.0", flush=True)
    print("-" * 60)
    
    process = subprocess.Popen(
        command, shell=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, env=ENV, text=True
    )
    for line in iter(process.stdout.readline, ''):
        print(line.strip(), flush=True)
    process.wait()
    
    success = process.returncode == 0
    print("-" * 60)
    return success

def main():
    parser = argparse.ArgumentParser(description="Spearhead.so Pipeline Controller")
    parser.add_argument("--stage", choices=["gather", "prep", "train", "inference", "all"], default="all")
    args = parser.parse_args()

    # Flush log if starting fresh
    if args.stage == "all" or not LOG_FILE.exists():
        with open(LOG_FILE, "w") as f: 
            f.write(f"--- Session Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n")

    sys.stdout = TeeLogger(LOG_FILE)
    
    # Reset telemetry to zero at the start of each run
    print(f"[TELEMETRY] stage=Waiting | status=Ready | rows=0 | throughput=0 | elapsed=0.0 | cpu_cores=0.0 | ram_gb=0.0 | ram_percent=0.0", flush=True)
    
    # 1. Gather
    if args.stage in ["gather", "all"]:
        DATA_OUT.mkdir(exist_ok=True)
        # Use existing gather.py logic
        success = run_step("Ingest", f"python3 {BASE_DIR}/pods/data-gather/gather.py")
        if not success: sys.exit(1)

    # 2. Prepare
    if args.stage in ["prep", "all"]:
        DATA_OUT.mkdir(exist_ok=True)
        FEAT_OUT.mkdir(exist_ok=True)
        ENV["INPUT_DIR"] = str(DATA_OUT)
        ENV["OUTPUT_DIR"] = str(FEAT_OUT)
        success = run_step("Data Prep", f"python3 {BASE_DIR}/pods/data-prep/prepare.py")
        if not success: sys.exit(1)

    # 3. Train
    if args.stage in ["train", "all"]:
        FEAT_OUT.mkdir(exist_ok=True)
        MODEL_OUT.mkdir(exist_ok=True)
        ENV["INPUT_DIR"] = str(FEAT_OUT)
        ENV["OUTPUT_DIR"] = str(MODEL_OUT)
        success = run_step("Model Train", f"python3 {BASE_DIR}/pods/model-build/train.py")
        if not success: sys.exit(1)

    # 4. Inference
    if args.stage in ["inference", "all"]:
        # Run the inference client (verified)
        success = run_step("Inference", f"python3 {BASE_DIR}/pods/inference/client.py")
        if not success: sys.exit(1)

    print("\n✅ Execution complete.")

if __name__ == "__main__":
    main()
