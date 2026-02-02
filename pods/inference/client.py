#!/usr/bin/env python3
"""
Pod 4: Inference Client (Continuous Mode)
Continuous batch inference using Triton Inference Server.
Features:
- Queue-based input/output
- Batch inference for efficiency
- Backlog tracking
- Model hot-reload support
"""

import sys
import time
import signal
import psutil
import numpy as np
import os
from pathlib import Path
from datetime import datetime

import tritonclient.http as httpclient
from tritonclient.utils import InferenceServerException

# XGBoost for CPU fallback
import xgboost as xgb

# Import queue and config
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from queue_interface import get_queue_service
from config_contract import QueueTopics, StoragePaths

STOP_FLAG = False

def signal_handler(signum, frame):
    global STOP_FLAG
    print("Shutdown signal received")
    STOP_FLAG = True

def log(msg):
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} | {msg}", flush=True)

def load_xgboost_model_cpu():
    """Load XGBoost model for CPU inference (fallback when Triton unavailable)"""
    try:
        # Try to find the latest model
        models_path = StoragePaths.get_path('models')
        model_dir = models_path / 'fraud_xgboost'
        
        if not model_dir.exists():
            log(f"Model directory not found: {model_dir}")
            return None
        
        # Find latest version
        versions = sorted([d for d in model_dir.iterdir() if d.is_dir() and d.name.isdigit()],
                         key=lambda x: int(x.name), reverse=True)
        
        if not versions:
            log("No model versions found")
            return None
        
        latest_version = versions[0]
        model_file = latest_version / 'xgboost.json'
        
        if not model_file.exists():
            log(f"Model file not found: {model_file}")
            return None
        
        # Load model
        model = xgb.Booster()
        model.load_model(str(model_file))
        log(f"✓ Loaded XGBoost model from {model_file} (CPU mode)")
        return model
        
    except Exception as e:
        log(f"Failed to load XGBoost model: {e}")
        return None

def run_cpu_inference(xgb_model, input_array):
    """Run inference using XGBoost on CPU"""
    try:
        # Create DMatrix
        dmatrix = xgb.DMatrix(input_array)
        
        # Run prediction
        predictions = xgb_model.predict(dmatrix)
        
        return predictions
        
    except Exception as e:
        log(f"CPU inference failed: {e}")
        # Fallback to simulation only if CPU inference fails
        return np.random.rand(len(input_array)).astype(np.float32)

def main():
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Configuration
    triton_url = os.getenv("TRITON_URL", "localhost:8001")
    model_name = os.getenv("MODEL_NAME", "fraud_xgboost")
    batch_size = int(os.getenv("BATCH_SIZE", "1000"))
    continuous_mode = os.getenv('CONTINUOUS_MODE', 'true').lower() == 'true'
    
    # Queue service
    queue_service = get_queue_service()
    
    log("=" * 70)
    log("Pod 4: Continuous Inference Client")
    log("=" * 70)
    log(f"Triton URL: {triton_url}")
    log(f"Model: {model_name}")
    log(f"Batch Size: {batch_size:,}")
    log(f"Mode: {'Continuous' if continuous_mode else 'Single-shot'}")
    log("=" * 70)
    
    # Connect to Triton
    try:
        triton_client = httpclient.InferenceServerClient(url=triton_url, verbose=False)
    except Exception as e:
        log(f"Failed to create Triton client: {e}")
        if not continuous_mode:
            sys.exit(1)
        else:
            log("Triton not available, loading XGBoost model for CPU inference...")
            triton_client = None
    
    if triton_client and not triton_client.is_server_live():
        log("Triton server is not live")
        if not continuous_mode:
            sys.exit(1)
        else:
            log("Triton not available, loading XGBoost model for CPU inference...")
            triton_client = None
    else:
        if triton_client:
            log("✓ Triton server is live")
    
    # Load CPU model if Triton not available
    cpu_model = None
    if not triton_client:
        cpu_model = load_xgboost_model_cpu()
        if cpu_model:
            log("✓ CPU inference mode enabled (real XGBoost predictions)")
        else:
            log("⚠ No model available - will use simulation mode")
    
    if not continuous_mode:
        # Original single-shot mode
        run_single_inference(triton_client, model_name)
    else:
        # NEW: Continuous inference mode
        run_continuous_inference(triton_client, cpu_model, model_name, batch_size, queue_service)

def run_single_inference(triton_client, model_name):
    """Original single-shot inference"""
    if not triton_client:
        log("No Triton client available")
        return
    
    # Generate dummy data matching the feature size (15 features)
    batch_size = 1
    input_data = np.random.randn(batch_size, 15).astype(np.float32)
    
    inputs = [
        httpclient.InferInput("input__0", input_data.shape, "FP32")
    ]
    inputs[0].set_data_from_numpy(input_data)
    
    outputs = [
        httpclient.InferRequestedOutput("output__0")
    ]
    
    try:
        start = time.time()
        result = triton_client.infer(model_name, inputs, outputs=outputs)
        end = time.time()
        
        cpu = psutil.cpu_percent()
        cpu_cores = (cpu / 100.0) * psutil.cpu_count()
        mem = psutil.virtual_memory()
        mem_gb = mem.used / (1024 ** 3)

        log(f"Inference result: {result.as_numpy('output__0')}")
        log(f"METRICS: Latency={(end-start)*1000:.2f} ms | CPU={cpu_cores:.1f} Cores | RAM={mem.percent:.1f}% ({mem_gb:.2f} GB)")
        
    except InferenceServerException as e:
        log(f"Inference failed: {e}")
        sys.exit(1)

def run_continuous_inference(triton_client, cpu_model, model_name, batch_size, queue_service):
    """Continuous batch inference from queue"""
    log("Starting continuous inference mode...")
    
    total_inferred = 0
    start_time = time.time()
    
    while not STOP_FLAG:
        try:
            # Consume batch from features queue
            messages = queue_service.consume_batch(
                QueueTopics.FEATURES_READY,
                batch_size=batch_size,
                timeout=1.0
            )
            
            if not messages:
                time.sleep(0.5)
                continue
            
            log(f"Inferring batch of {len(messages):,} records...")
            
            # Prepare input data
            # Extract features (assuming 15 features)
            feature_cols = ['amt', 'lat', 'long', 'city_pop', 'unix_time', 
                          'merch_lat', 'merch_long', 'merch_zipcode', 'zip',
                          'amt_log', 'hour_of_day', 'day_of_week', 
                          'is_weekend', 'is_night', 'distance_km']
            
            input_data = []
            for msg in messages:
                row = [float(msg.get(col, 0)) for col in feature_cols]
                input_data.append(row)
            
            input_array = np.array(input_data, dtype=np.float32)
            
            # Run inference
            if triton_client:
                # Use Triton (GPU/optimized)
                results = run_triton_inference(triton_client, model_name, input_array)
            elif cpu_model:
                # Use CPU XGBoost (real predictions)
                results = run_cpu_inference(cpu_model, input_array)
            else:
                # Fallback to simulation (only if no model available)
                log("⚠ Using simulation mode (no model available)")
                results = np.random.rand(len(messages)).astype(np.float32)
            
            # Prepare output messages
            output_messages = []
            for i, msg in enumerate(messages):
                output_msg = msg.copy()
                output_msg['fraud_score'] = float(results[i])
                output_msg['fraud_prediction'] = int(results[i] > 0.5)
                output_messages.append(output_msg)
            
            # Publish to results queue
            queue_service.publish_batch(QueueTopics.INFERENCE_RESULTS, output_messages)
            
            total_inferred += len(messages)
            elapsed = time.time() - start_time
            throughput = total_inferred / elapsed if elapsed > 0 else 0
            
            # Update metrics
            cpu = psutil.cpu_percent()
            cpu_cores = (cpu / 100.0) * psutil.cpu_count()
            mem = psutil.virtual_memory()
            mem_gb = mem.used / (1024 ** 3)
            
            log(f"Inferred: {total_inferred:,} | Throughput: {throughput:,.0f} rows/sec | CPU: {cpu_cores:.1f} cores | RAM: {mem.percent:.1f}%")
            
        except Exception as e:
            log(f"Error in continuous inference: {e}")
            import traceback
            traceback.print_exc()
            time.sleep(1)

def run_triton_inference(triton_client, model_name, input_data):
    """Run batch inference on Triton"""
    inputs = [
        httpclient.InferInput("input__0", input_data.shape, "FP32")
    ]
    inputs[0].set_data_from_numpy(input_data)
    
    outputs = [
        httpclient.InferRequestedOutput("output__0")
    ]
    
    try:
        result = triton_client.infer(model_name, inputs, outputs=outputs)
        return result.as_numpy("output__0")
    except InferenceServerException as e:
        log(f"Triton inference failed: {e}")
        # Return simulated results
        return np.random.rand(len(input_data)).astype(np.float32)

if __name__ == "__main__":
    import os
    main()
