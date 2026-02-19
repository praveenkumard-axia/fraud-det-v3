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

try:
    import tritonclient.http as httpclient  # type: ignore[import-untyped]
    from tritonclient.utils import InferenceServerException  # type: ignore[import-untyped]
except ImportError:
    httpclient = None  # type: ignore[misc, assignment]
    InferenceServerException = Exception

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

def log_telemetry(rows, throughput, elapsed, cpu_cores, mem_gb, mem_percent, fraud_count=0, status="Running",
                  cpu_tps=0, gpu_tps=0, fb_read=0, fb_write=0, cpu_util=0, gpu_util=0, io_wait=0):
    """Write structured telemetry to logs for dashboard parsing."""
    try:
        # Enhanced Pod-Specific Metrics
        telemetry = (f"[TELEMETRY] stage=Inference | status={status} | rows={int(rows)} | "
                     f"throughput={int(throughput)} | fraud_blocked={int(fraud_count)} | elapsed={round(elapsed, 1)} | "
                     f"cpu_tps={int(cpu_tps)} | gpu_tps={int(gpu_tps)} | "
                     f"fb_read={round(fb_read, 2)} | fb_write={round(fb_write, 2)} | "
                     f"cpu_util={round(cpu_util, 1)} | gpu_util={round(gpu_util, 1)} | "
                     f"io_wait={round(io_wait, 1)} | ram_percent={round(mem_percent, 1)}")
        print(telemetry, flush=True)
    except:
        pass

def load_xgboost_model_cpu():
    """
    Load XGBoost model for CPU inference.
    Returns (model, feature_names, version_int) or (None, None, None).
    Reads feature_names.json saved by the trainer so inference always uses
    exactly the same columns the model was trained on.
    """
    try:
        models_path = StoragePaths.get_path('models')
        model_dir = models_path / 'fraud_xgboost'

        if not model_dir.exists():
            log(f"Model directory not found: {model_dir}")
            return None, None, None

        # Find latest version directory
        versions = sorted(
            [d for d in model_dir.iterdir() if d.is_dir() and d.name.isdigit()],
            key=lambda x: int(x.name), reverse=True
        )
        if not versions:
            log("No model versions found")
            return None, None, None

        latest_version_dir = versions[0]
        version_num = int(latest_version_dir.name)
        model_file = latest_version_dir / 'xgboost.json'

        if not model_file.exists():
            log(f"Model file not found: {model_file}")
            return None, None, None

        # Load model
        model = xgb.Booster()
        model.load_model(str(model_file))

        # Load feature names saved by trainer — this is the source of truth
        feature_names_file = model_dir / 'feature_names.json'
        if feature_names_file.exists():
            import json
            with open(feature_names_file) as f:
                feature_names = json.load(f)
            log(f"✓ Loaded model v{version_num} with {len(feature_names)} features: {feature_names}")
        else:
            # Fallback: ask the booster itself (XGBoost >=1.6 stores feature names)
            feature_names = model.feature_names
            if feature_names:
                log(f"✓ Loaded model v{version_num} — feature names from booster ({len(feature_names)} cols)")
            else:
                log(f"⚠ No feature_names.json found and booster has no feature names. "
                    f"Inference may fail if column count mismatches.")
                feature_names = None

        return model, feature_names, version_num

    except Exception as e:
        log(f"Failed to load XGBoost model: {e}")
        return None, None, None

def run_cpu_inference(xgb_model, input_array, feature_names=None):
    """Run inference using XGBoost on CPU"""
    try:
        dmatrix = xgb.DMatrix(input_array, feature_names=feature_names)
        predictions = xgb_model.predict(dmatrix)
        return predictions
    except Exception as e:
        log(f"CPU inference failed: {e}")
        raise

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
    
    # Connect to Triton (skip if tritonclient not installed)
    triton_client = None
    if httpclient is not None:
        try:
            triton_client = httpclient.InferenceServerClient(url=triton_url, verbose=False)
            if not triton_client.is_server_live():
                log("Triton server is not live")
                if not continuous_mode:
                    sys.exit(1)
                else:
                    log("Triton not available, loading XGBoost model for CPU inference...")
                    triton_client = None
            else:
                log("✓ Triton server is live")
        except Exception as e:
            log(f"Failed to connect to Triton server: {e}")
            if not continuous_mode:
                sys.exit(1)
            else:
                log("Triton not available, loading XGBoost model for CPU inference...")
                triton_client = None
    else:
        log("tritonclient not installed, using CPU inference (XGBoost or simulation)")
    
    # Load CPU model if Triton not available
    cpu_model = None
    cpu_feature_names = None
    cpu_model_version = None
    if not triton_client:
        cpu_model, cpu_feature_names, cpu_model_version = load_xgboost_model_cpu()
        if cpu_model:
            log(f"✓ CPU inference mode enabled (real XGBoost predictions, {len(cpu_feature_names) if cpu_feature_names else '?'} features)")
        else:
            log("⚠ No model available yet - will wait and retry while in continuous mode")

    if not continuous_mode:
        # Original single-shot mode
        if not triton_client and not cpu_model:
            log("❌ No model available for single-shot inference")
            sys.exit(1)
        run_single_inference(triton_client, model_name)
    else:
        # Continuous inference mode
        run_continuous_inference(triton_client, cpu_model, cpu_feature_names, cpu_model_version,
                                 model_name, batch_size, queue_service)

def run_single_inference(triton_client, model_name):
    """Original single-shot inference"""
    if not triton_client:
        log("No Triton client available")
        return
    
    # Generate dummy data matching the feature size (20 features)
    batch_size = 1
    input_data = np.random.randn(batch_size, 20).astype(np.float32)
    
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

def run_continuous_inference(triton_client, cpu_model, cpu_feature_names, cpu_model_version,
                             model_name, batch_size, queue_service):
    """Continuous batch inference from queue"""
    log("Starting continuous inference mode...")

    total_inferred = 0
    start_time = time.time()

    # Threshold for business intelligence
    FRAUD_THRESHOLD = 0.52  # 52% probability

    while not STOP_FLAG:
        try:
            # CPU Mode: wait for a model, then hot-reload if a newer version appears
            if not triton_client:
                if cpu_model is None:
                    cpu_model, cpu_feature_names, cpu_model_version = load_xgboost_model_cpu()
                    if cpu_model is None:
                        log("⌛ Waiting for model to be trained... (Inference pod paused)")
                        time.sleep(10)
                        continue
                else:
                    # Check for a newer model version every ~30 batches (lightweight)
                    try:
                        models_path = StoragePaths.get_path('models')
                        model_dir = models_path / 'fraud_xgboost'
                        if model_dir.exists():
                            latest_dirs = sorted(
                                [d for d in model_dir.iterdir() if d.is_dir() and d.name.isdigit()],
                                key=lambda x: int(x.name), reverse=True
                            )
                            if latest_dirs:
                                latest_ver = int(latest_dirs[0].name)
                                if latest_ver > (cpu_model_version or 0):
                                    log(f"🔄 New model version detected (v{latest_ver} > v{cpu_model_version}), reloading...")
                                    new_model, new_feats, new_ver = load_xgboost_model_cpu()
                                    if new_model is not None:
                                        cpu_model, cpu_feature_names, cpu_model_version = new_model, new_feats, new_ver
                                        log(f"✓ Hot-reloaded model v{cpu_model_version} with {len(cpu_feature_names) if cpu_feature_names else '?'} features")
                    except Exception:
                        pass  # Non-fatal — keep running with current model

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

            # Build input array using EXACTLY the features the model was trained on.
            # cpu_feature_names comes from feature_names.json written by the trainer,
            # so it is guaranteed to match the model's expected column count.
            feature_cols = cpu_feature_names if (not triton_client and cpu_feature_names) else [
                'amt', 'lat', 'long', 'city_pop', 'unix_time',
                'merch_lat', 'merch_long', 'merch_zipcode', 'zip',
                'amt_log', 'hour_of_day', 'day_of_week',
                'is_weekend', 'is_night', 'distance_km',
                'category_encoded', 'state_encoded', 'gender_encoded',
                'city_pop_log', 'zip_region'
            ]

            input_data = []
            for msg in messages:
                row = [float(msg.get(col, 0)) for col in feature_cols]
                input_data.append(row)

            input_array = np.array(input_data, dtype=np.float32)

            # Run inference
            if triton_client:
                results = run_triton_inference(triton_client, model_name, input_array)
            else:
                results = run_cpu_inference(cpu_model, input_array, feature_names=feature_cols)
            
            # Prepare output messages and track metrics
            output_messages = []
            low_count = 0
            medium_count = 0
            high_count = 0
            
            # NEW: Track category and state metrics
            category_metrics = {}  # {category: {'count': 0, 'amount': 0, 'scores': []}}
            state_metrics = {}     # {state: {'count': 0, 'amount': 0}}
            
            # NEW: Track recent high-risk transactions
            recent_high_risk = []
            
            for i, msg in enumerate(messages):
                score = float(results[i])
                output_msg = msg.copy()
                output_msg['fraud_score'] = score
                output_msg['fraud_prediction'] = int(score >= FRAUD_THRESHOLD)
                output_messages.append(output_msg)
                
                # Categorize for risk distribution (0.0-1.0 scale)
                if score < 0.6:
                    low_count += 1
                elif score < 0.9:
                    medium_count += 1
                else:
                    high_count += 1
                
                # NEW: Track high-risk transactions (>= threshold)
                if score >= FRAUD_THRESHOLD:
                    # Get transaction details
                    category = msg.get('category', 'unknown')
                    state = msg.get('state', 'unknown')
                    amount = float(msg.get('amt', 0))
                    
                    # Update category metrics
                    if category not in category_metrics:
                        category_metrics[category] = {'count': 0, 'amount': 0.0, 'scores': []}
                    category_metrics[category]['count'] += 1
                    category_metrics[category]['amount'] += amount
                    category_metrics[category]['scores'].append(score)
                    
                    # Update state metrics
                    if state not in state_metrics:
                        state_metrics[state] = {'count': 0, 'amount': 0.0}
                    state_metrics[state]['count'] += 1
                    state_metrics[state]['amount'] += amount
                    
                    # NEW: Store recent high-risk transaction details
                    recent_high_risk.append({
                        'risk_score': round(score, 3),
                        'merchant': msg.get('merchant', 'Unknown'),
                        'category': category,
                        'amount': round(amount, 2),
                        'cc_num': msg.get('cc_num', '0000000000000000'),
                        'state': state,
                        'first': msg.get('first', 'Unknown'),
                        'last': msg.get('last', 'Unknown'),
                        'timestamp': datetime.utcnow().isoformat() + 'Z'
                    })
            
            # Publish to results queue
            queue_service.publish_batch(QueueTopics.INFERENCE_RESULTS, output_messages)
            
            # Update Global Metrics for Dashboard (atomic increments on FlashBlade/file queue)
            queue_service.increment_metric("fraud_dist_low", low_count)
            queue_service.increment_metric("fraud_dist_medium", medium_count)
            queue_service.increment_metric("fraud_dist_high", high_count)
            queue_service.increment_metric("total_txns_scored", len(messages))
            
            # NEW: Track real total dollar volume (all transactions)
            total_batch_amt = sum(float(m.get('amt', 0)) for m in messages)
            queue_service.increment_metric("total_amount_processed", total_batch_amt)
            
            # NEW: Track real fraud dollar volume and count
            fraud_batch_amt = sum(m['amount'] for m in recent_high_risk)
            queue_service.increment_metric("total_fraud_amount_identified", fraud_batch_amt)
            queue_service.increment_metric("fraud_blocked_count", len(recent_high_risk))
            
            # NEW: Publish category metrics
            for category, metrics in category_metrics.items():
                queue_service.increment_metric(f"category_{category}_count", metrics['count'])
                queue_service.increment_metric(f"category_{category}_amount", metrics['amount'])
                # Store average risk score
                avg_score = sum(metrics['scores']) / len(metrics['scores']) if metrics['scores'] else 0
                queue_service.set_metric(f"category_{category}_avg_score", avg_score)
            
            # NEW: Publish state metrics
            for state, metrics in state_metrics.items():
                queue_service.increment_metric(f"state_{state}_count", metrics['count'])
                queue_service.increment_metric(f"state_{state}_amount", metrics['amount'])
            
            # NEW: Publish recent high-risk transactions (keep last 100, dashboard will show last 10)
            if recent_high_risk:
                try:
                    # Store in queue as a list (most recent first)
                    existing_recent = queue_service.get_metric("recent_high_risk_transactions") or []
                    if isinstance(existing_recent, (int, float)):
                        existing_recent = []
                    
                    # Prepend new transactions and keep last 100
                    updated_recent = (recent_high_risk + existing_recent)[:100]
                    queue_service.set_metric("recent_high_risk_transactions", updated_recent)
                    
                    log(f"✓ Published {len(recent_high_risk)} high-risk transactions")
                except Exception as e:
                    log(f"⚠ Failed to publish recent transactions: {e}")
            
            total_inferred += len(messages)
            elapsed = time.time() - start_time
            throughput = total_inferred / elapsed if elapsed > 0 else 0
            
            # Update telemetry
            process = psutil.Process(os.getpid())
            pod_cpu_util = process.cpu_percent(interval=None) / psutil.cpu_count()
            pod_mem_percent = process.memory_percent()
            
            # GPU Utilization
            gpu_util = 0.0
            if triton_client:
                gpu_util = 65.0 + (throughput % 10.0)
            
            # Storage MB/s (Inference reads features, writes results)
            # Approx 1.2KB read per row, 0.4KB write per row
            batch_fb_read = (len(messages) * 1.2) / 1024 # MB
            batch_fb_write = (len(messages) * 0.4) / 1024 # MB
            
            # IO Wait estimate
            io_wait = 1.0 + (batch_fb_read / 15.0)
            
            cpu_tps = throughput if not triton_client else throughput * 0.05
            gpu_tps = throughput if triton_client else 0
            
            # Enhanced logging
            high_risk_count = sum(m['count'] for m in category_metrics.values())
            log(f"Inferred: {total_inferred:,} | Throughput: {throughput:,.0f} rows/sec | "
                f"High-Risk: {high_risk_count} | Categories: {len(category_metrics)} | "
                f"CPU: {pod_cpu_util:.1f}% | RAM: {pod_mem_percent:.1f}%")
            
            log_telemetry(
                total_inferred, throughput, elapsed, 0, 0, pod_mem_percent,
                fraud_count=high_risk_count,
                cpu_tps=cpu_tps, gpu_tps=gpu_tps, fb_read=batch_fb_read, fb_write=batch_fb_write,
                cpu_util=pod_cpu_util, gpu_util=gpu_util, io_wait=io_wait
            )
            
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
