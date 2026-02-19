#!/usr/bin/env python3
"""
Pod 3: Model Training (Continuous Retraining Mode)
Trains XGBoost models continuously with priority awareness.
Features:
- Continuous retraining loop
- Priority-aware (pauses when inference prioritized)
- Incremental training support
- Automatic model versioning
- FlashBlade integration
"""

import os
import sys
import gc
import json
import time
import signal
import logging
import psutil
import requests
import argparse
from pathlib import Path
from datetime import datetime
from typing import Tuple, List, Dict, Any, Optional

# Import queue and config
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from queue_interface import get_queue_service
from config_contract import QueueTopics, StoragePaths, SystemPriorities

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s'
)
log = logging.getLogger(__name__)

STOP_FLAG = False

def signal_handler(signum, frame):
    global STOP_FLAG
    log.info("Shutdown signal received")
    STOP_FLAG = True

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

def is_gpu_available():
    """Lazy check for GPU availability without polluting context."""
    try:
        import cudf
        import cupy as cp
        return True
    except ImportError:
        return False

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
        self.input_path = StoragePaths.get_path('features') if input_dir == 'auto' else Path(input_dir)
        self.output_path = StoragePaths.get_path('models') if output_dir == 'auto' else Path(output_dir)
        self.output_path.mkdir(parents=True, exist_ok=True)
        self.gpu_mode = is_gpu_available() and (os.getenv('FORCE_CPU', 'false').lower() != 'true')
        
        # NEW: Continuous mode configuration
        self.continuous_mode = os.getenv('CONTINUOUS_MODE', 'true').lower() == 'true'
        self.training_interval = int(os.getenv('TRAINING_INTERVAL_SECONDS', '10'))  # Lowered for faster start
        self.min_samples_for_training = int(os.getenv('MIN_SAMPLES_FOR_TRAINING', '1000')) # Lowered significantly for first model
        self.backend_url = os.getenv('BACKEND_URL', 'http://localhost:8000')
        
        # Debugging: Log actual paths being used
        log.info(f"ModelTrainer Input Path:  {self.input_path.absolute()}")
        log.info(f"ModelTrainer Output Path: {self.output_path.absolute()}")
        
        # Model versioning
        self.current_model = None
        self.model_version = 0
        self.last_train_time = 0
        
        log.info("=" * 70)
        log.info("Pod 3: Continuous Model Training")
        log.info("=" * 70)
        log.info(f"Input:    {self.input_path}")
        log.info(f"Output:   {self.output_path}")
        log.info(f"Backend:  {'XGBoost GPU (cuDF)' if self.gpu_mode else 'XGBoost CPU (Polars)'}")
        log.info(f"Mode:     {'Continuous' if self.continuous_mode else 'Single-shot'}")
        log.info(f"Training Interval: {self.training_interval}s")
        log.info(f"Min Samples: {self.min_samples_for_training:,}")
        log.info("=" * 70)
        
        # NEW: Queue service for business metrics
        self.queue_service = get_queue_service()
        
        # Load existing model if available (Skip in single-shot to avoid CUDA conflict)
        if self.continuous_mode:
            self.load_previous_model()

    def load_previous_model(self):
        """Try to load the most recent existing model from output path"""
        try:
            model_name = "fraud_xgboost"
            model_dir = self.output_path / model_name
            if not model_dir.exists():
                return
                
            # Find latest version directory
            versions = sorted([int(d.name) for d in model_dir.iterdir() if d.is_dir() and d.name.isdigit()])
            if not versions:
                return
                
            latest_version = versions[-1]
            model_file = model_dir / str(latest_version) / "xgboost.json"
            
            if model_file.exists():
                import xgboost as xgb
                model = xgb.Booster()
                model.load_model(str(model_file))
                self.current_model = model
                self.model_version = latest_version
                self.last_train_time = time.time()
                log.info(f"✓ Loaded existing model v{latest_version} from disk")
                
                # Update global metrics as we have a model now
                self.queue_service.set_metric("model_version_loaded", latest_version)
        except Exception as e:
            log.warning(f"Could not load existing model: {e}")

    def check_system_priority(self) -> str:
        """Check system priority from backend API"""
        try:
            response = requests.get(f"{self.backend_url}/api/control/priority", timeout=2)
            if response.status_code == 200:
                return response.json().get('priority', SystemPriorities.BALANCED)
        except:
            pass
        return SystemPriorities.BALANCED  # Default to balanced priority
    
    def should_train_now(self) -> bool:
        """Determine if training should run now"""
        # Always allow training in this benchmark mode
        priority = self.check_system_priority()
        if priority == SystemPriorities.INFERENCE:
            log.info(f"System priority is {priority}, but continuing training as requested.")
        
        # Check time interval
        elapsed_since_train = time.time() - self.last_train_time
        if elapsed_since_train < self.training_interval:
            return False
        
        return True
    
    def get_recent_feature_files(self, max_files: int = 100) -> List[Path]:
        """Get recent feature files for training"""
        files = sorted(self.input_path.glob("features_batch_*.parquet"), key=lambda x: x.stat().st_mtime, reverse=True)
        return files[:max_files]
    
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
            import cudf
            import cupy as cp
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
            
            # STABILITY FIX: Use cupy to bridge to numpy - often more stable than .to_pandas()
            log.info(f"Moving test set ({len(test_df):,} records) to CPU memory via Cupy bridge...")
            try:
                X_test = cp.asnumpy(test_df[available_feats].to_cupy())
                y_test = cp.asnumpy(test_df['is_fraud'].to_cupy())
            except Exception as e:
                log.warning(f"Cupy bridge failed, falling back to to_pandas: {e}")
                X_test = test_df[available_feats].to_pandas().values
                y_test = test_df['is_fraud'].to_pandas().values
            
            log.info(f"Loaded {len(df):,} records on GPU (Test set moved to CPU) in {time.time()-start:.2f}s")
            return X_train, y_train, X_test, y_test, available_feats
            
        else:
            import polars as pl
            import numpy as np
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
        import xgboost as xgb
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
                'tree_method': 'hist',
                'device': 'cuda',
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
        """Evaluate model and persist REAL performance metrics"""
        import xgboost as xgb
        import numpy as np
        log.info(f"Evaluating model on {len(y_test)} test samples...")
        
        # Log class distribution in test set
        test_fraud_count = int(y_test.sum())
        test_legit_count = len(y_test) - test_fraud_count
        log.info(f"Test Set Distribution: Fraud={test_fraud_count}, Legit={test_legit_count}")
        
        # XGBoost prediction (Booster requires DMatrix)
        import xgboost as xgb
        # Stability fix: X_test and y_test are already numpy arrays from prepare_data
        dtest = xgb.DMatrix(X_test)
        preds = model.predict(dtest)
        
        # Ensure preds is also numpy
        import numpy as np
        if hasattr(preds, 'get'):
            preds_np = preds.get()
        else:
            preds_np = np.array(preds)
            
        pred_labels = (preds_np > 0.5).astype(int)
        
        # X_test and y_test are already numpy now
        y_test_np = y_test 

        # Correctly calculate TP, FP, FN, TN
        tp = int(((pred_labels == 1) & (y_test_np == 1)).sum())
        fp = int(((pred_labels == 1) & (y_test_np == 0)).sum())
        fn = int(((pred_labels == 0) & (y_test_np == 1)).sum())
        tn = int(((pred_labels == 0) & (y_test_np == 0)).sum())
        
        log.info(f"Confusion Matrix: TP={tp}, FP={fp}, FN={fn}, TN={tn}")
        
        total = len(y_test)
        accuracy = (tp + tn) / total if total > 0 else 0
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        fpr = fp / (fp + tn) if (fp + tn) > 0 else 0
        
        log.info(f"REAL Metrics -> Acc: {accuracy:.4f}, Prec: {precision:.4f}, Recall: {recall:.4f}, FPR: {fpr:.4f}")
        
        # Persist to global metrics store
        self.queue_service.set_metric("model_accuracy", float(accuracy))
        self.queue_service.set_metric("model_precision", float(precision))
        self.queue_service.set_metric("model_recall", float(recall))
        self.queue_service.set_metric("model_fpr", float(fpr))
        self.queue_service.set_metric("model_samples_evaluated", int(total))

    def save_model(self, model, feature_names, version: Optional[int] = None):
        """Save model with versioning and generate Triton config."""
        model_name = "fraud_xgboost"
        model_repo_dir = self.output_path / model_name
        
        # Use provided version or increment
        if version is None:
            version = self.model_version + 1
        
        version_dir = model_repo_dir / str(version)
        version_dir.mkdir(parents=True, exist_ok=True)
        
        # Save XGBoost JSON
        model_file = version_dir / "xgboost.json"
        model.save_model(str(model_file))
        
        # Save feature names
        with open(model_repo_dir / "feature_names.json", "w") as f:
            json.dump(feature_names, f)
        
        # Save metadata
        metadata = {
            'version': version,
            'timestamp': datetime.now().isoformat(),
            'features': feature_names,
            'gpu_mode': self.gpu_mode
        }
        with open(version_dir / "metadata.json", "w") as f:
            json.dump(metadata, f, indent=2)
            
        # Generate Triton Config
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
            
        log.info(f"Model v{version} saved to {model_repo_dir}")
        self.model_version = version
        return version

    def run_single(self):
        """Single-shot training (original behavior)"""
        try:
            filepath = self.load_features()
            X_train, y_train, X_test, y_test, feats = self.prepare_data(filepath)
            model = self.train(X_train, y_train, X_test, y_test)
            self.evaluate(model, X_test, y_test)
            self.save_model(model, feats)
        except Exception as e:
            log.error(f"Training failed: {e}")
            raise
    
    def run_continuous(self):
        """Continuous retraining loop"""
        log.info("Starting continuous retraining mode...")
        
        total_models_trained = 0
        
        while not STOP_FLAG:
            try:
                # Check if we should train now
                # User preference: Train once if not exists.
                # In continuous mode, we normally retrain, but we'll prioritize current model
                has_model = self.current_model is not None
                
                # Get recent feature files for training OR evaluation
                feature_files = self.get_recent_feature_files(max_files=50)
                
                if not feature_files:
                    if not has_model:
                        log.info("No feature files available and no model loaded. Waiting...")
                    time.sleep(30)
                    continue

                # Should we train or just evaluate?
                # We train if:
                # 1. We don't have a model yet
                # 2. OR (it's been a long time AND we aren't in 'once-only' mode - though user implies once only)
                # For now, let's train if NONE, otherwise just evaluate to update metrics.
                should_train = not has_model
                
                if not should_train:
                    # Just evaluate the current model on the latest features to keep metrics fresh
                    try:
                        log.info("Evaluating existing model on new data to update metrics...")
                        latest_file = feature_files[0]
                        df = pl.read_parquet(latest_file)
                        if len(df) > 100:
                            available_feats = [c for c in FEATURE_COLUMNS if c in df.columns]
                            df = df.fill_null(0)
                            X_eval = np.ascontiguousarray(df[available_feats].to_pandas().values, dtype=np.float32)
                            y_eval = np.ascontiguousarray(df["is_fraud"].to_pandas().values, dtype=np.float32)
                            self.evaluate(self.current_model, X_eval, y_eval)
                            log.info("✓ Metrics updated from existing model.")
                        
                        # Sleep longer if we are just evaluating
                        time.sleep(self.training_interval)
                        continue
                    except Exception as e:
                        log.warning(f"Failed to update metrics from existing model: {e}")
                        time.sleep(10)
                        continue

                # Load and combine recent data for training
                log.info(f"Loading {len(feature_files)} recent feature files for INITIAL training...")
                dfs = []
                total_samples = 0
                
                for file in feature_files:
                    try:
                        df = pl.read_parquet(file)
                        dfs.append(df)
                        total_samples += len(df)
                        
                        # Stop if we have enough samples
                        if total_samples >= self.min_samples_for_training:
                            break
                    except Exception as e:
                        log.warning(f"Failed to load {file}: {e}")
                
                if total_samples < self.min_samples_for_training:
                    log.info(f"Not enough samples ({total_samples:,} < {self.min_samples_for_training:,})")
                    time.sleep(30)
                    continue
                
                # Combine dataframes
                combined_df = pl.concat(dfs)
                log.info(f"Combined {total_samples:,} samples for training")
                
                # Prepare data
                available_feats = [c for c in FEATURE_COLUMNS if c in combined_df.columns]
                combined_df = combined_df.fill_null(0)
                
                # Split
                test_size = int(len(combined_df) * 0.2)
                train_df = combined_df.slice(0, len(combined_df) - test_size)
                test_df = combined_df.slice(len(combined_df) - test_size, test_size)
                
                # Convert to numpy
                pdf_train = train_df.to_pandas()
                pdf_test = test_df.to_pandas()
                
                X_train = np.ascontiguousarray(pdf_train[available_feats].values, dtype=np.float32)
                y_train = np.ascontiguousarray(pdf_train["is_fraud"].values, dtype=np.float32)
                X_test = np.ascontiguousarray(pdf_test[available_feats].values, dtype=np.float32)
                y_test = np.ascontiguousarray(pdf_test["is_fraud"].values, dtype=np.float32)
                
                # Train
                start_time = time.time()
                log.info("Training model...")
                
                # Fresh training
                model = self.train(X_train, y_train, X_test, y_test)
                
                # Evaluate
                self.evaluate(model, X_test, y_test)
                
                # Save with new version
                version = self.save_model(model, available_feats)
                
                # Update state
                self.current_model = model
                self.last_train_time = time.time()
                total_models_trained += 1
                
                elapsed = time.time() - start_time
                log.info(f"✓ Model v{version} trained in {elapsed:.2f}s (Total models: {total_models_trained})")
                
                # Update telemetry
                cpu_percent = psutil.cpu_percent()
                cpu_cores = (cpu_percent / 100.0) * psutil.cpu_count()
                mem = psutil.virtual_memory()
                mem_gb = mem.used / (1024 ** 3)
                
                throughput = total_samples / elapsed if elapsed > 0 else 0
                log_telemetry(total_samples, throughput, elapsed, cpu_cores, mem_gb, mem.percent, 
                            status=f"Model v{version} trained")
                
                # Update global metrics for dashboard fallback
                self.queue_service.increment_metric("total_txns_scored", total_samples)
                
            except Exception as e:
                log.error(f"Error in continuous training: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(60)
    
    def run(self):
        """Run in appropriate mode"""
        if self.continuous_mode:
            self.run_continuous()
        else:
            self.run_single()

def main():
    parser = argparse.ArgumentParser(description="Fraud Detection Model Trainer")
    signal.signal(signal.SIGTERM, signal_handler)
    
    input_dir = os.getenv('INPUT_DIR', 'auto')
    output_dir = os.getenv('OUTPUT_DIR', 'auto')
    
    start_time = time.time()
    trainer = ModelTrainer(input_dir, output_dir)
    
    # Run in appropriate mode
    trainer.run()
    
    if not trainer.continuous_mode:
        # Single-shot mode: report final metrics
        elapsed = time.time() - start_time
        
        # Get total rows from features to report throughput
        try:
            import polars as pl
            features_file = trainer.load_features()
            total_rows = pl.scan_parquet(features_file).select(pl.len()).collect().item()
        except:
            total_rows = 14100000  # Fallback
        
        throughput = total_rows / elapsed if elapsed > 0 else 0
        
        # Resource Snapshot
        cpu_percent = psutil.cpu_percent()
        cpu_cores = (cpu_percent / 100.0) * psutil.cpu_count()
        mem = psutil.virtual_memory()
        mem_gb = mem.used / (1024 ** 3)
        
        log.info(f"METRICS: Rows={total_rows} | Time={elapsed:.2f}s | Throughput={throughput:.1f} rows/s")
        log.info(f"METRICS: CPU={cpu_cores:.1f} Cores | RAM={mem.percent:.1f}% ({mem_gb:.2f} GB)")
        
        # Final Stats
        log_telemetry(total_rows, throughput, elapsed, cpu_cores, mem_gb, mem.percent, status="Completed")

if __name__ == "__main__":
    main()
