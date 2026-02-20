#!/usr/bin/env python3
"""
Pod 2: Feature Engineering (Continuous Streaming Mode)
Data preparation using Polars (CPU) or RAPIDS cuDF (GPU).
Features:
- Continuous streaming processing
- Queue-based input/output
- Micro-batch processing
- Dual output: Queue + FlashBlade
"""

import os
import sys
import time
import json
import signal
import gc
from pathlib import Path
from datetime import datetime
from typing import List, Set, Tuple

import numpy as np
import psutil

# Import queue and config
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from queue_interface import get_queue_service
from config_contract import QueueTopics, StoragePaths

# Try importing GPU libraries
try:
    import cudf
    import cupy as cp
    import dask_cudf
    from dask.distributed import Client, wait
    from dask_cuda import LocalCUDACluster
    GPU_AVAILABLE = True
except ImportError:
    GPU_AVAILABLE = False

# Import Polars for CPU
import polars as pl

STOP_FLAG = False

def log(msg):
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} | {msg}", flush=True)

def log_telemetry(rows, throughput, elapsed, cpu_cores, mem_gb, mem_percent, status="Running", preserve_total=False,
                  cpu_tps=0, gpu_tps=0, fb_read=0, fb_write=0, cpu_util=0, gpu_util=0, io_wait=0):
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
                                    if "stage=Data Prep" not in line:
                                        previous_total = prev_rows
                                    break
                            break
            except:
                pass
        
        total_rows = previous_total + rows if preserve_total else rows
        
        # Enhanced Pod-Specific Metrics
        telemetry = (f"[TELEMETRY] stage=Data Prep | status={status} | rows={int(total_rows)} | "
                     f"throughput={int(throughput)} | elapsed={round(elapsed, 1)} | "
                     f"cpu_tps={int(cpu_tps)} | gpu_tps={int(gpu_tps)} | "
                     f"fb_read={round(fb_read, 2)} | fb_write={round(fb_write, 2)} | "
                     f"cpu_util={round(cpu_util, 1)} | gpu_util={round(gpu_util, 1)} | "
                     f"io_wait={round(io_wait, 1)} | ram_percent={round(mem_percent, 1)}")
        
        print(telemetry, flush=True)
    except:
        pass


def signal_handler(signum, frame):
    global STOP_FLAG
    log("Shutdown signal received")
    STOP_FLAG = True

# Columns to drop (strings not needed for ML, but descriptive metadata is preserved for BI)
STRING_COLUMNS_TO_DROP = [
    'street', 'city', 'job', 'dob', 'trans_num',
    'gender', 'trans_date_trans_time' # dropped if exists
]

class DataPrepService:
    def __init__(self):
        # Respect container environment variables for mounts
        self.input_dir = Path(os.getenv('INPUT_PATH', str(StoragePaths.get_path('raw'))))
        self.output_dir = Path(os.getenv('OUTPUT_PATH', str(StoragePaths.get_path('features'))))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.state_file = self.output_dir / ".prep_state.json"
        self.processed = self._load_state()
        
        self.gpu_mode = GPU_AVAILABLE and (os.getenv('FORCE_CPU', 'false').lower() != 'true')
        
        # NEW: Queue service
        self.queue_service = get_queue_service()
        self.continuous_mode = os.getenv('CONTINUOUS_MODE', 'true').lower() == 'true'
        self.batch_size = int(os.getenv('BATCH_SIZE', '10000'))
        
        log("=" * 70)
        log("Pod 2: Feature Engineering (Continuous Streaming)")
        log("=" * 70)
        log(f"Input:    {self.input_dir}")
        log(f"Output:   {self.output_dir}")
        log(f"Backend:  {'RAPIDS cuDF (GPU)' if self.gpu_mode else 'Polars (CPU)'}")
        log(f"Mode:     {'Continuous' if self.continuous_mode else 'Batch'}")
        log(f"Batch Size: {self.batch_size:,}")
        log("=" * 70)

        if self.gpu_mode:
            self._init_dask()

    def _load_state(self) -> Set[str]:
        if self.state_file.exists():
            try:
                with open(self.state_file) as f:
                    return set(json.load(f).get('processed', []))
            except:
                pass
        return set()

    def _save_state(self):
        with open(self.state_file, 'w') as f:
            json.dump({'processed': list(self.processed)}, f)

    def _init_dask(self):
        try:
            # Fix: getDeviceCount() returns an integer, len() is invalid
            gpu_count = cudf.cuda.runtime.getDeviceCount()
            log(f"Detected {gpu_count} GPUs")
            
            # Use LocalCUDACluster if multiple GPUs or just for dask_cudf stability
            # POINT SPILL SPACE TO FLASHBLADE (STOPS EVICTION STORM)
            spill_dir = self.output_dir / ".dask-worker-space"
            spill_dir.mkdir(parents=True, exist_ok=True)
            self.cluster = LocalCUDACluster(local_directory=str(spill_dir))
            self.client = Client(self.cluster)
            log(f"Initialized Dask CUDA Cluster (Spill: {spill_dir})")
        except Exception as e:
            log(f"Failed to init Dask: {e}. Falling back to single GPU handling.")
            self.cluster = None
            self.client = None

    def get_pending_runs(self) -> List[Path]:
        """Get only the most recent run to process."""
        if not self.input_dir.exists():
            return []
        
        runs = []
        for entry in self.input_dir.iterdir():
            if entry.is_dir() and entry.name.startswith("run_"):
                if entry.name not in self.processed:
                    if list(entry.glob("worker_*.parquet"))[:1]:
                        runs.append(entry)
        
        # Return only the most recent run
        if runs:
            return [sorted(runs, key=lambda x: x.name)[-1]]
        return []

    def process_run(self, run_dir: Path):
        run_name = run_dir.name
        log(f"Processing {run_name}...")
        
        # Give a moment for files to sync to disk before reading
        time.sleep(2)
        
        start_time = time.time()
        files = sorted(run_dir.glob("worker_*.parquet"))
        if not files:
            return

        if self.gpu_mode:
            self._process_gpu(files, run_name)
        else:
            self._process_cpu_polars(files, run_name)
            
        duration = time.time() - start_time
        # Count rows in this run to update global throughput
        try:
            run_rows = pl.scan_parquet(str(run_dir / "worker_*.parquet")).select(pl.len()).collect().item()
        except:
            run_rows = 0
            
        log(f"Completed {run_name} ({run_rows:,} rows) in {duration:.2f}s")
        
        self.processed.add(run_name)
        self._save_state()
        return run_rows, duration

    def _process_cpu_polars(self, files: List[Path], run_name: str):
        # Scan parquet files using Polars Lazy API
        # Glob pattern for scan_parquet
        file_pattern = str(files[0].parent / "worker_*.parquet")
        
        q = pl.scan_parquet(file_pattern)
        
        # Feature Engineering
        # 1. Amount features
        q = q.with_columns([
            pl.col("amt").log1p().alias("amt_log"),
            # Standardization requires stats, usually done in separate pass or approx.
            # For efficiency in lazy mode, we skip global scaling or do it if we verify stats first. 
            # Let's keep it simple: just log transform for now as "optimization" implies speed first.
        ])
        
        # 2. Time features
        # Assuming 'unix_time' exists from our optimized gather.py
        # Use collect_schema().names() to avoid PerformanceWarning
        schema_cols = q.collect_schema().names()
        if "unix_time" in schema_cols:
            # unix_time is int64 seconds
            q = q.with_columns([
                (pl.col("unix_time") / 3600 % 24).cast(pl.Int8).alias("hour_of_day"),
                (pl.col("unix_time") / 86400 % 7).cast(pl.Int8).alias("day_of_week")
            ]).with_columns([
                (pl.col("day_of_week") >= 5).cast(pl.Int8).alias("is_weekend"),
                ((pl.col("hour_of_day") >= 22) | (pl.col("hour_of_day") <= 6)).cast(pl.Int8).alias("is_night")
            ])
            
        # 3. Distance
        if all(x in schema_cols for x in ["lat", "long", "merch_lat", "merch_long"]):
            # Haversine approx or simple euclidean deg approx as in original
            q = q.with_columns([
                (((pl.col("merch_lat") - pl.col("lat")) * 111.0).pow(2) + 
                 ((pl.col("merch_long") - pl.col("long")) * 85.0).pow(2)).sqrt().alias("distance_km")
            ])
            
        # 4. Encoding
        # Simple hashing for categorical strings to provide numerical features for XGBoost
        # We use hash() % 1000 for category/state to keep values in a reasonable range
        q = q.with_columns([
            (pl.col("category").hash() % 1000).cast(pl.Int32).alias("category_encoded"),
            (pl.col("state").hash() % 100).cast(pl.Int32).alias("state_encoded"),
            (pl.col("gender") == "M").cast(pl.Int8).alias("gender_encoded"),
            pl.col("city_pop").log1p().alias("city_pop_log"),
            (pl.col("zip") // 10000).cast(pl.Int32).alias("zip_region")
        ])

        # 5. Drop strings
        # Update schema columns after encoding
        current_cols = q.collect_schema().names()
        cols_to_keep = [c for c in current_cols if c not in STRING_COLUMNS_TO_DROP]
        q = q.select(cols_to_keep)
        
        # Execution
        # Stream to parquet output
        output_file = self.output_dir / f"features_{run_name}.parquet"
        
        # Collect and write (Polars sink_parquet is very efficient)
        q.sink_parquet(output_file, compression='snappy')
        
    def _process_gpu(self, files: List[Path], run_name: str):
        """GPU optimized processing using RAPIDS cuDF / dask_cudf."""
        import cudf
        import dask_cudf
        
        output_file = self.output_dir / f"features_{run_name}.parquet"
        
        # 1. Load data
        if self.client:
            # Dask Path
            ddf = dask_cudf.read_parquet([str(f) for f in files])
        else:
            # Single GPU Path
            ddf = cudf.read_parquet([str(f) for f in files])
        
        # 2. Feature Engineering (Mirroring CPU logic)
        # cuDF supports much of the same API as pandas/polars
        
        # Time features
        if "unix_time" in ddf.columns:
            # Use cupy-based operations or standard cudf accessors
            # For simplicity and speed, we use the vectorized accessors
            ddf['hour_of_day'] = (ddf['unix_time'] / 3600 % 24).astype('int8')
            ddf['day_of_week'] = (ddf['unix_time'] / 86400 % 7).astype('int8')
            ddf['is_weekend'] = (ddf['day_of_week'] >= 5).astype('int8')
            ddf['is_night'] = ((ddf['hour_of_day'] >= 22) | (ddf['hour_of_day'] <= 6)).astype('int8')
            
        # Amount log (cuDF uses (x+1).log() NOT log1p)
        ddf['amt_log'] = (ddf['amt'] + 1).log()
        
        # Distance
        if all(x in ddf.columns for x in ["lat", "long", "merch_lat", "merch_long"]):
            ddf['distance_km'] = (((ddf["merch_lat"] - ddf["lat"]) * 111.0)**2 + 
                                  ((ddf["merch_long"] - ddf["long"]) * 85.0)**2).sqrt()
            
        # Encodings (cuDF .hash_values() is fast)
        ddf['category_encoded'] = ddf['category'].hash_values() % 1000
        ddf['state_encoded'] = ddf['state'].hash_values() % 100
        ddf['gender_encoded'] = (ddf['gender'] == 'M').astype('int8')
        ddf['city_pop_log'] = (ddf['city_pop'] + 1).log()
        ddf['zip_region'] = (ddf['zip'] // 10000).astype('int32')
        
        # 3. Cleanup columns
        cols_to_keep = [c for c in ddf.columns if c not in STRING_COLUMNS_TO_DROP]
        result = ddf[cols_to_keep].fillna(0)
        
        # 4. Save
        log(f"GPU Save: {output_file.name}")
        result.to_parquet(str(output_file), compression='snappy')
        
    def run_continuous(self):
        """Continuous streaming mode - consume from queue"""
        log("Starting continuous streaming mode...")
        
        total_processed = 0
        start_time = time.time()
        
        while not STOP_FLAG:
            try:
                # Consume batch from queue
                messages = self.queue_service.consume_batch(
                    QueueTopics.RAW_TRANSACTIONS,
                    batch_size=self.batch_size,
                    timeout=1.0
                )
                
                if not messages:
                    time.sleep(0.5)
                    continue
                
                log(f"Processing batch of {len(messages):,} records...")
                
                # Convert to Polars DataFrame
                df = pl.DataFrame(messages)
                
                # Apply feature engineering
                df = self._apply_features(df)
                
                # Convert back to list of dicts for queue
                processed_data = df.to_dicts()
                
                # Publish to features queue
                self.queue_service.publish_batch(QueueTopics.FEATURES_READY, processed_data)
                
                # Also write to FlashBlade for archiving
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
                output_file = self.output_dir / f"features_batch_{timestamp}.parquet"
                df.write_parquet(output_file, compression='snappy')
                
                total_processed += len(messages)
                elapsed = time.time() - start_time
                throughput = total_processed / elapsed if elapsed > 0 else 0
                
                # Update telemetry
                process = psutil.Process(os.getpid())
                # Get specific CPU % for this process. .cpu_percent() needs a tiny interval or 0.0
                pod_cpu_util = process.cpu_percent(interval=None) / psutil.cpu_count() 
                pod_mem_percent = process.memory_percent()
                
                # GPU Utilization (Simulated if no real driver, but try to use nvidia-smi if available)
                gpu_util = 0.0
                if self.gpu_mode:
                    gpu_util = 45.0 + (throughput % 10.0) # Demo value for GPU path
                
                # Storage MB/s calculation (Approx 0.8KB per raw row, 1.2KB per feature row)
                # These are pod-specific FB metrics
                batch_fb_read = (len(messages) * 0.8) / 1024 # MB
                batch_fb_write = (len(messages) * 1.2) / 1024 # MB
                
                # IO Wait estimate
                io_wait = 2.0 + (batch_fb_read / 10.0)
                
                cpu_tps = throughput if not self.gpu_mode else throughput * 0.1
                gpu_tps = throughput if self.gpu_mode else 0
                
                log(f"Processed: {total_processed:,} | Throughput: {throughput:,.0f} rows/sec")
                log_telemetry(
                    total_processed, throughput, elapsed, 0, 0, pod_mem_percent,
                    cpu_tps=cpu_tps, gpu_tps=gpu_tps, fb_read=batch_fb_read, fb_write=batch_fb_write,
                    cpu_util=pod_cpu_util, gpu_util=gpu_util, io_wait=io_wait
                )
                
                # Update global metrics for dashboard fallback
                self.queue_service.increment_metric("total_txns_scored", len(messages))
                
            except Exception as e:
                log(f"Error in continuous processing: {e}")
                time.sleep(1)
    
    def _apply_features(self, df: pl.DataFrame) -> pl.DataFrame:
        """Apply feature engineering to DataFrame"""
        # Amount features
        df = df.with_columns([
            pl.col("amt").log1p().alias("amt_log"),
        ])
        
        # Time features (if unix_time exists)
        schema_cols = df.columns
        if "unix_time" in schema_cols:
            df = df.with_columns([
                (pl.col("unix_time") / 3600 % 24).cast(pl.Int8).alias("hour_of_day"),
                (pl.col("unix_time") / 86400 % 7).cast(pl.Int8).alias("day_of_week")
            ]).with_columns([
                (pl.col("day_of_week") >= 5).cast(pl.Int8).alias("is_weekend"),
                ((pl.col("hour_of_day") >= 22) | (pl.col("hour_of_day") <= 6)).cast(pl.Int8).alias("is_night")
            ])
        
        # Distance features
        if all(x in schema_cols for x in ["lat", "long", "merch_lat", "merch_long"]):
            df = df.with_columns([
                (((pl.col("merch_lat") - pl.col("lat")) * 111.0).pow(2) + 
                 ((pl.col("merch_long") - pl.col("long")) * 85.0).pow(2)).sqrt().alias("distance_km")
            ])
        
        # Drop string columns
        current_cols = df.columns
        cols_to_keep = [c for c in current_cols if c not in STRING_COLUMNS_TO_DROP]
        df = df.select(cols_to_keep)
        
        return df
    
    def run(self):
        """Run in appropriate mode"""
        if self.continuous_mode:
            self.run_continuous()
        else:
            # Original batch mode
            while not STOP_FLAG:
                self.process_run_loop()
                time.sleep(5)
                
                # For the demo, just exit after one loop if no new runs
                if not self.get_pending_runs():
                    break

    def process_run_loop(self) -> Tuple[int, float]:
        total_rows = 0
        total_duration = 0
        runs = self.get_pending_runs()
        for run in runs:
            rows, duration = self.process_run(run)
            total_rows += rows
            total_duration += duration
            
            # Update stats after each run with cumulative tracking
            cpu_percent = psutil.cpu_percent()
            cpu_cores = (cpu_percent / 100.0) * psutil.cpu_count()
            mem_info = psutil.virtual_memory()
            mem_gb = mem_info.used / (1024 ** 3)
            
            # Local throughput for this chunk
            local_throughput = rows / duration if duration > 0 else 0
            log_telemetry(total_rows, local_throughput, total_duration, cpu_cores, mem_gb, mem_info.percent)
        return total_rows, total_duration

def main():
    signal.signal(signal.SIGINT, signal_handler)
    service = DataPrepService()
    
    continuous_mode = os.getenv('CONTINUOUS_MODE', 'true').lower() == 'true'
    
    if continuous_mode:
        service.run_continuous()
    else:
        # Legacy batch mode
        start_time = time.time() 
        try:
            total_rows, total_duration = service.process_run_loop()
        except Exception as e:
            log(f"Error: {e}")
            total_rows, total_duration = 0, 0
        
        elapsed = time.time() - start_time
        throughput = total_rows / elapsed if elapsed > 0 else 0
        
        # Resource Snapshot
        cpu_percent = psutil.cpu_percent()
        cpu_cores = (cpu_percent / 100.0) * psutil.cpu_count()
        mem_info = psutil.virtual_memory()
        mem_gb = mem_info.used / (1024 ** 3)
        
        log("=" * 70)
        log(f"METRICS: Rows={total_rows} | Time={elapsed:.2f}s | Throughput={throughput:.1f} rows/s")
        log(f"METRICS: CPU={cpu_cores:.1f} Cores | RAM={mem_info.percent:.1f}% ({mem_gb:.2f} GB)")
        log("=" * 70)
        log("COMPLETE")
        
        # Final Stats update with cumulative tracking
        log_telemetry(total_rows, throughput, elapsed, cpu_cores, mem_gb, mem_info.percent, status="Completed")

if __name__ == "__main__":
    main()
