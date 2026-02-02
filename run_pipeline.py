#!/usr/bin/env python3
"""
Spearhead Fraud Detection - Continuous Pipeline Orchestrator
Implements a non-blocking, queue-driven streaming pipeline.
"""

import os
import sys
import time
import subprocess
import signal
import threading
from pathlib import Path
from datetime import datetime

# Set environment variables for all pods and the orchestrator
os.environ["QUEUE_TYPE"] = "redis"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"

# Import config/contracts
BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))
from config_contract import QueueTopics, StoragePaths, GenerationRateLimits
from queue_interface import get_queue_service

# Configuration
PYTHON_EXE = "/home/anuj/Axia/myenv/bin/python"  # Use the virtual environment
THRESHOLD_TO_START = 100_000  # Records needed before starting downstream (Lowered for fast demo)
CHECK_INTERVAL = 2              # Seconds between backlog checks

class ProcessManager:
    def __init__(self):
        self.processes = {}
        self.stop_event = threading.Event()
        self.queue_service = get_queue_service()
        self.lock = threading.Lock()

    def start_pod(self, name, command, env=None):
        """Starts a pod process and spawns a thread to read its output."""
        with self.lock:
            if name in self.processes:
                print(f"[{name}] Already running.")
                return

            # Prepare environment
            pod_env = os.environ.copy()
            pod_env["PYTHONUNBUFFERED"] = "1"
            pod_env["CONTINUOUS_MODE"] = "true"
            pod_env["QUEUE_TYPE"] = "redis"  # Force redis for cross-process comms
            if env:
                pod_env.update(env)

            print(f">>> LAUNCHING POD: {name}")
            
            # Use specific python executable
            full_command = command.replace("python3", PYTHON_EXE)
            
            # Start process
            process = subprocess.Popen(
                full_command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=pod_env,
                cwd=str(BASE_DIR)
            )
            
            self.processes[name] = process
            
            # Start log thread
            thread = threading.Thread(target=self._stream_logs, args=(name, process), daemon=True)
            thread.start()

    def _stream_logs(self, name, process):
        """Streams logs from a process with a prefix."""
        prefix = f"[{name:^12}]"
        for line in iter(process.stdout.readline, ''):
            if line:
                print(f"{prefix} {line.strip()}", flush=True)
        process.stdout.close()

    def stop_all(self):
        """Cleanly shuts down all running pods."""
        print("\n>>> SHUTTING DOWN PIPELINE...")
        self.stop_event.set()
        with self.lock:
            for name, process in self.processes.items():
                print(f"--- Stopping {name} (PID: {process.pid})")
                process.send_signal(signal.SIGTERM)
            
            # Wait a moment
            time.sleep(2)
            
            # Force kill if still running
            for name, process in self.processes.items():
                if process.poll() is None:
                    process.kill()
        print(">>> ALL PODS TERMINATED.")

def main():
    manager = ProcessManager()
    
    # Initialize queue service
    queue = get_queue_service()
    
    # Clear existing queues for a fresh start
    print(">>> Clearing Redis queues and metrics...")
    queue.clear(QueueTopics.RAW_TRANSACTIONS)
    queue.clear(QueueTopics.FEATURES_READY)
    queue.clear(QueueTopics.INFERENCE_RESULTS)
    queue.clear(QueueTopics.TRAINING_QUEUE)
    queue.clear_metrics()

    # Handle Ctrl+C
    def handle_signal(sig, frame):
        manager.stop_all()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    print("="*80)
    print("  SPEARHEAD CONTINUOUS FRAUD DETECTION PIPELINE (REDIS EDITION)")
    print("="*80)
    print(f"Goal: Start Generator, wait for {THRESHOLD_TO_START:,} records in REDIS, then trigger pipeline.")
    print("Status: DECOUPLED | NON-BLOCKING | REDIS QUEUES")
    print("="*80)

    # 1. Start the Data Generator immediately
    manager.start_pod("GENERATOR", "python3 pods/data-gather/gather.py")

    # 2. Wait and Monitor Progress
    downstream_started = False
    start_time = time.time()

    try:
        while not manager.stop_event.is_set():
            # Monitor Redis backlog
            total_records = queue.get_backlog(QueueTopics.RAW_TRANSACTIONS)
            
            elapsed = time.time() - start_time
            
            # Print heart-beat status
            if not downstream_started:
                progress = (total_records / THRESHOLD_TO_START) * 100
                print(f"[MONITOR] Redis Backlog: {total_records:,} / {THRESHOLD_TO_START:,} records ({progress:.1f}%) | Elapsed: {elapsed:.1f}s", flush=True)

            # Check if we hit the threshold to start downstream
            if not downstream_started and total_records >= THRESHOLD_TO_START:
                print(f"\n{'*'*80}")
                print(f"*** MILESTONE REACHED: {total_records:,} RECORDS IN REDIS")
                print(f"*** TRIGGERING DOWNSTREAM STAGES...")
                print(f"{'*'*80}\n")
                
                # Start all downstream pods
                manager.start_pod("DATA-PREP", "python3 pods/data-prep/prepare.py")
                manager.start_pod("TRAINING",  "python3 pods/model-build/train.py")
                manager.start_pod("INFERENCE", "python3 pods/inference/client.py")
                
                downstream_started = True

            time.sleep(CHECK_INTERVAL)

    except Exception as e:
        print(f"Error in Orchestrator: {e}")
        manager.stop_all()

if __name__ == "__main__":
    main()
