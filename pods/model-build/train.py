#!/usr/bin/env python3
"""
Pod 3: Model Training (Optimized)
Trains XGBoost models using Polars for data loading and automated backend selection.
Optimizations:
- Polars for fast CPU data loading
- Single path execution (no redundant CPU vs GPU comparison)
- Automatic Triton config generation with dynamic batching
"""

import os
import sys
import gc
import json
import time
import logging
import psutil
from pathlib import Path
from datetime import datetime
from typing import Tuple, List, Dict, Any

# CPU imports
import polars as pl
import numpy as np
import xgboost as xgb

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s'
)
log = logging.getLogger(__name__)

def log_telemetry(rows, throughput, elapsed, cpu_cores, mem_gb, mem_percent, status="Running", preserve_total=False):
    """Write structured telemetry to logs for dashboard parsing."""
    try:
        # Read previous total if preserving
        previous_total = 0
        if preserve_total:
            # Parse last telemetry entry from logs to get previous row count
            try:
                with open("pipeline_report.txt", "r") as f:
                    lines = f.readlines()
                    for line in reversed(lines[-100:]):  # Check last 100 lines
                        if "[TELEMETRY]" in line and "stage=" in line:
                            # Parse the previous stage's row count
                            parts = line.split("|")
                            for part in parts:
                                if "rows=" in part:
                                    prev_rows = int(part.split("=")[1].strip())
                                    # Only preserve if from different stage
                                    if "stage=Model Train" not in line:
                                        previous_total = prev_rows
                                    break
                            break
            except:
                pass
        
        total_rows = (previous_total + rows) if preserve_total else rows
        telemetry = f"[TELEMETRY] stage=Model Train | status={status} | rows={int(total_rows)} | throughput={int(throughput)} | elapsed={round(elapsed, 1)} | cpu_cores={round(cpu_cores, 1)} | ram_gb={round(mem_gb, 2)} | ram_percent={round(mem_percent, 1)}"
        print(telemetry, flush=True)
    except:
        pass

# Check for GPU availability
try:
    import cudf
    import cupy as cp
    GPU_AVAILABLE = True
except ImportError:
    GPU_AVAILABLE = False

# Features for model training (aligned with prepare.py output)
FEATURE_COLUMNS = [
    'amt', 'lat', 'long', 'city_pop', 'unix_time', 'merch_lat', 'merch_long',
    'merch_zipcode', 'zip', 'amt_log', 'hour_of_day', 'day_of_week',
    'is_weekend', 'is_night', 'distance_km', 'category_encoded', 'state_encoded',
    'gender_encoded', 'city_pop_log', 'zip_region'
]

# Columns to exclude (IDs, raw text, etc.)
EXCLUDE_COLUMNS = [
    'transaction_id', 'trans_date_trans_time', 'cc_num', 'merchant', 'category',
    'first', 'last', 'gender', 'street', 'city', 'state', 'job', 'dob',
    'trans_num', 'is_fraud'
]

class ModelTrainer:
    def __init__(self, input_dir: str, output_dir: str):
        self.input_path = Path(input_dir)
        self.output_path = Path(output_dir)
        self.output_path.mkdir(parents=True, exist_ok=True)
        self.gpu_mode = GPU_AVAILABLE and (os.getenv('FORCE_CPU', 'false').lower() != 'true')
        
        log.info("=" * 70)
        log.info("Pod 3: Optimized Model Training")
        log.info("=" * 70)
        log.info(f"Input:   {self.input_path}")
        log.info(f"Output:  {self.output_path}")
        log.info(f"Backend: {'XGBoost GPU (cuDF)' if self.gpu_mode else 'XGBoost CPU (Polars)'}")
        log.info("=" * 70)

    def load_features(self) -> Path:
        """Find the most recent features file."""
        files = sorted(self.input_path.glob("features_*.parquet"))
        if not files:
            raise FileNotFoundError(f"No feature files found in {self.input_path}")
        filepath = files[-1]
        log.info(f"Loading features from: {filepath.name}")
        return filepath

    def prepare_data(self, filepath: Path) -> Tuple[Any, Any, Any, Any, List[str]]:
        """Load and split data using Polars (CPU) or cuDF/Dask (GPU)."""
        start = time.time()
        
        if self.gpu_mode:
            # GPU Path (simplified for this script, assumes single GPU fit or dask flow)
            df = cudf.read_parquet(filepath)
            df = df.fillna(0) # Simple imputation
            available_feats = [c for c in FEATURE_COLUMNS if c in df.columns]
            
            # Simple split
            split_idx = int(len(df) * 0.8)
            train_df = df.iloc[:split_idx]
            test_df = df.iloc[split_idx:]
            
            X_train = train_df[available_feats]
            y_train = train_df['is_fraud']
            X_test = test_df[available_feats]
            y_test = test_df['is_fraud']
            
            log.info(f"Loaded {len(df):,} records on GPU in {time.time()-start:.2f}s")
            return X_train, y_train, X_test, y_test, available_feats
            
        else:
            # CPU Path with Polars
            df = pl.read_parquet(filepath)
            
            # Handle missing columns safely
            available_feats = [c for c in FEATURE_COLUMNS if c in df.columns]
            missing = [c for c in FEATURE_COLUMNS if c not in df.columns]
            if missing:
                log.warning(f"Missing features: {missing}")

            # Fill nulls
            df = df.fill_null(0)
            
            # Convert to numpy for XGBoost 
            # Note: newer XGBoost supports Polars directly but let's be safe with numpy
            # Split
            test_size = int(len(df) * 0.2)
            train_df = df.slice(0, len(df) - test_size)
            test_df = df.slice(len(df) - test_size, test_size)
            
            # Convert to pandas first (most robust path for XGBoost <-> Numpy)
            pdf_train = train_df.to_pandas()
            pdf_test = test_df.to_pandas()
            
            X_train = np.ascontiguousarray(pdf_train[available_feats].values, dtype=np.float32)
            y_train = np.ascontiguousarray(pdf_train["is_fraud"].values, dtype=np.float32)
            X_test = np.ascontiguousarray(pdf_test[available_feats].values, dtype=np.float32)
            y_test = np.ascontiguousarray(pdf_test["is_fraud"].values, dtype=np.float32)
            
            log.info(f"Loaded {len(df):,} records on CPU in {time.time()-start:.2f}s")
            return X_train, y_train, X_test, y_test, available_feats

    def train(self, X_train, y_train, X_test, y_test):
        """Train XGBoost model."""
        start = time.time()
        
        # Calculate scale_pos_weight for imbalance
        if self.gpu_mode:
            fraud_count = float(y_train.sum())
            total_count = len(y_train)
        else:
            fraud_count = np.sum(y_train)
            total_count = len(y_train)
            
        normal_count = total_count - fraud_count
        scale_pos_weight = normal_count / max(fraud_count, 1) if fraud_count > 0 else 1.0
        
        # DMatrix
        if self.gpu_mode:
            dtrain = xgb.DMatrix(X_train, label=y_train)
            dtest = xgb.DMatrix(X_test, label=y_test)
            params = {
                'objective': 'binary:logistic',
                'eval_metric': ['auc', 'logloss'],
                'max_depth': 8,
                'learning_rate': 0.1,
                'scale_pos_weight': scale_pos_weight,
                'tree_method': 'gpu_hist',
            }
        else:
            dtrain = xgb.DMatrix(X_train, label=y_train)
            dtest = xgb.DMatrix(X_test, label=y_test)
            params = {
                'objective': 'binary:logistic',
                'eval_metric': ['auc', 'logloss'],
                'max_depth': 8,
                'learning_rate': 0.1,
                'scale_pos_weight': scale_pos_weight,
                'tree_method': 'hist',
                'nthread': 1,
            }
        
        log.info(f"Training model...")
        model = xgb.train(
            params, dtrain,
            num_boost_round=100,
            evals=[(dtrain, 'train'), (dtest, 'test')],
            early_stopping_rounds=10,
            verbose_eval=False
        )
        
        log.info(f"Training completed in {time.time()-start:.2f}s")
        return model

    def evaluate(self, model, X_test, y_test):
        """Evaluate model."""
        dtest = xgb.DMatrix(X_test)
        preds = model.predict(dtest)
        pred_labels = (preds > 0.5).astype(int)
        
        if self.gpu_mode:
            # Convert to numpy for reporting if needed, or keep cupy
            # Simplified for verify script
            pass
        else:
            accuracy = (pred_labels == y_test).mean()
            log.info(f"Accuracy: {accuracy:.4f}")

    def save_model(self, model, feature_names):
        """Save model and generate Triton config."""
        model_name = "fraud_xgboost"
        model_repo_dir = self.output_path / model_name
        version_dir = model_repo_dir / "1"
        version_dir.mkdir(parents=True, exist_ok=True)
        
        # Save XGBoost JSON
        model_file = version_dir / "xgboost.json"
        model.save_model(str(model_file))
        
        # Save feature names
        with open(model_repo_dir / "feature_names.json", "w") as f:
            json.dump(feature_names, f)
            
        # Generate Triton Config
        # Dynamic batching enabled
        # Instance group optimized based on CPU/GPU
        instance_kind = "KIND_GPU" if self.gpu_mode else "KIND_CPU"
        instance_count = 1 if self.gpu_mode else 2
        
        config = f'''name: "{model_name}"
backend: "fil"
max_batch_size: 32768
input [
  {{
    name: "input__0"
    data_type: TYPE_FP32
    dims: [ {len(feature_names)} ]
  }}
]
output [
  {{
    name: "output__0"
    data_type: TYPE_FP32
    dims: [ 1 ]
  }}
]
instance_group [
  {{
    count: {instance_count}
    kind: {instance_kind}
  }}
]
dynamic_batching {{
  preferred_batch_size: [ 256, 1024, 4096, 32768 ]
  max_queue_delay_microseconds: 100
}}
parameters [
  {{
    key: "model_type"
    value: {{ string_value: "xgboost_json" }}
  }},
  {{
    key: "output_class"
    value: {{ string_value: "false" }}
  }},
  {{
    key: "fil_implementation"
    value: {{ string_value: "treelite" }} 
  }}
]
'''
        with open(model_repo_dir / "config.pbtxt", "w") as f:
            f.write(config)
            
        log.info(f"Model saved to {model_repo_dir}")

    def run(self):
        try:
            filepath = self.load_features()
            X_train, y_train, X_test, y_test, feats = self.prepare_data(filepath)
            model = self.train(X_train, y_train, X_test, y_test)
            self.evaluate(model, X_test, y_test)
            self.save_model(model, feats)
        except Exception as e:
            log.error(f"Training failed: {e}")
            raise

def main():
    input_dir = os.getenv('INPUT_DIR', 'fraud_dectection_anuuj_features')
    output_dir = os.getenv('OUTPUT_DIR', 'fraud_dectection_anuuj_models')
    
    start_time = time.time()
    trainer = ModelTrainer(input_dir, output_dir)
    
    # Get total rows from features to report throughput
    try:
        features_file = trainer.load_features()
        total_rows = pl.scan_parquet(features_file).select(pl.len()).collect().item()
    except:
        total_rows = 14100000 # Fallback
        
    trainer.run()
    elapsed = time.time() - start_time
    throughput = total_rows / elapsed if elapsed > 0 else 0
    
    # Resource Snapshot for Master Script
    cpu_percent = psutil.cpu_percent()
    cpu_cores = (cpu_percent / 100.0) * psutil.cpu_count()
    mem = psutil.virtual_memory()
    mem_gb = mem.used / (1024 ** 3)
    
    log.info(f"METRICS: Rows={total_rows} | Time={elapsed:.2f}s | Throughput={throughput:.1f} rows/s")
    log.info(f"METRICS: CPU={cpu_cores:.1f} Cores | RAM={mem.percent:.1f}% ({mem_gb:.2f} GB)")
    
    # Final Stats update with cumulative tracking
    log_telemetry(total_rows, throughput, elapsed, cpu_cores, mem_gb, mem.percent, status="Completed")

if __name__ == "__main__":
    main()
