#!/usr/bin/env python3
"""
Pod 1: Data Generator (Continuous Mode)
Generates synthetic credit card transactions continuously.
Features:
- Continuous generation with rate limiting
- Queue-based publishing
- Backlog-aware throttling
- FlashBlade archiving
"""

import os
import sys
import time
import signal
import subprocess
import pickle
import threading
from pathlib import Path
from datetime import datetime

# Optional: psutil for resource monitoring
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import json

# Import queue and config
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from queue_interface import get_queue_service
from config_contract import QueueTopics, StoragePaths, GenerationRateLimits, BacklogThresholds

STOP_FLAG = False

def get_process_memory():
    if PSUTIL_AVAILABLE:
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / (1024 * 1024)  # MB
    return 0.0

def get_cpu_usage():
    if PSUTIL_AVAILABLE:
        return psutil.cpu_percent(interval=None)
    return 0.0

# Transaction categories with realistic distribution
CATEGORIES = [
    'gas_transport', 'grocery_pos', 'misc_pos', 'misc_net', 'shopping_net',
    'shopping_pos', 'grocery_net', 'entertainment', 'food_dining', 'home',
    'kids_pets', 'travel', 'health_fitness', 'personal_care'
]
CATEGORY_WEIGHTS = np.array([
    0.243, 0.226, 0.106, 0.092, 0.083, 0.080, 0.079, 0.037,
    0.019, 0.012, 0.008, 0.005, 0.005, 0.004
])

# US states weighted by population
US_STATES = [
    'CA', 'TX', 'FL', 'NY', 'PA', 'IL', 'OH', 'GA', 'NC', 'MI',
    'NJ', 'VA', 'WA', 'AZ', 'MA', 'TN', 'IN', 'MO', 'MD', 'WI',
    'CO', 'MN', 'SC', 'AL', 'LA', 'KY', 'OR', 'OK', 'CT', 'UT',
    'IA', 'NV', 'AR', 'MS', 'KS', 'NM', 'NE', 'ID', 'WV', 'HI',
    'NH', 'ME', 'MT', 'RI', 'DE', 'SD', 'ND', 'AK', 'VT', 'WY'
]
STATE_WEIGHTS = np.array([
    0.118, 0.087, 0.065, 0.059, 0.039, 0.038, 0.035, 0.032, 0.031, 0.030,
    0.027, 0.026, 0.023, 0.022, 0.021, 0.021, 0.020, 0.018, 0.018, 0.018,
    0.017, 0.017, 0.015, 0.015, 0.014, 0.013, 0.013, 0.012, 0.011, 0.010,
    0.010, 0.009, 0.009, 0.009, 0.009, 0.006, 0.006, 0.006, 0.005, 0.004,
    0.004, 0.004, 0.003, 0.003, 0.003, 0.003, 0.002, 0.002, 0.002, 0.002
])

# String pool sizes for Faker-generated data
POOL_SIZES = {
    'first': 1_000,
    'last': 1_500,
    'street': 5_000,
    'city': 1_000,
    'merchant': 2_000,
    'job': 500,
    'trans_num': 10_000,
    'dob': 2_500,
}


def log(msg):
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} | {msg}", flush=True)

def log_telemetry(rows, throughput, elapsed, cpu_cores, mem_gb, mem_percent, status="Running"):
    """Write structured telemetry to logs for dashboard parsing."""
    try:
        telemetry = f"[TELEMETRY] stage=Ingest | status={status} | rows={int(rows)} | throughput={int(throughput)} | elapsed={round(elapsed, 1)} | cpu_cores={round(cpu_cores, 1)} | ram_gb={round(mem_gb, 2)} | ram_percent={round(mem_percent, 1)}"
        print(telemetry, flush=True)
    except: 
        pass


def signal_handler(signum, frame):
    global STOP_FLAG
    log("Shutdown signal received")
    STOP_FLAG = True


def generate_pools(output_path: Path) -> Path:
    """Generate string pools using Faker (one-time startup cost)."""
    from faker import Faker
    
    log("Generating string pools...")
    fake = Faker()
    Faker.seed(42)
    
    pools = {
        'first': np.array([fake.first_name() for _ in range(POOL_SIZES['first'])]),
        'last': np.array([fake.last_name() for _ in range(POOL_SIZES['last'])]),
        'street': np.array([fake.street_address() for _ in range(POOL_SIZES['street'])]),
        'city': np.array([fake.city() for _ in range(POOL_SIZES['city'])]),
        'merchant': np.array([f"{fake.company().replace(',', '')} {fake.company_suffix()}" 
                             for _ in range(POOL_SIZES['merchant'])]),
        'job': np.array([fake.job().replace(',', ' ') for _ in range(POOL_SIZES['job'])]),
        'trans_num': np.array([fake.uuid4().replace('-', '') for _ in range(POOL_SIZES['trans_num'])]),
        'dob': np.array([fake.date_of_birth(minimum_age=18, maximum_age=85).strftime('%Y-%m-%d') 
                        for _ in range(POOL_SIZES['dob'])]),
        'categories': np.array(CATEGORIES),
        'category_weights': CATEGORY_WEIGHTS / CATEGORY_WEIGHTS.sum(),
        'states': np.array(US_STATES),
        'state_weights': STATE_WEIGHTS / STATE_WEIGHTS.sum(),
    }
    
    pools_file = output_path / "_pools.pkl"
    with open(pools_file, 'wb') as f:
        pickle.dump(pools, f)
    
    total = sum(POOL_SIZES.values())
    log(f"  Created {total:,} pooled values")
    return pools_file


# Worker script (runs in subprocess for true parallelism)
WORKER_SCRIPT = '''
import sys, pickle, time
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from pathlib import Path

def generate_chunk(pools, n, rng, fraud_rate, base_time):
    """Generate n transactions using vectorized operations."""
    
    # Timestamps: Direct INT64 generation
    # OPTIMIZATION: Removed string conversion for timestamp
    unix_times = rng.integers(base_time, base_time + 31536000, size=n, dtype=np.int64)
    
    # Geographic data (US bounds) - Float32
    lats = rng.uniform(25.0, 48.0, n).astype(np.float32)
    longs = rng.uniform(-125.0, -70.0, n).astype(np.float32)
    
    # Merchant location perturbation
    merch_lats = lats + rng.normal(0, 0.5, n).astype(np.float32)
    merch_longs = longs + rng.normal(0, 0.5, n).astype(np.float32)
    
    # Transaction amounts (lognormal distribution) - Float32
    amts = np.clip(np.abs(rng.lognormal(3.5, 1.5, n)), 1.0, 25000.0).astype(np.float32)
    
    # Pool sampling indices (Int32 is sufficient for indices)
    idx = lambda pool: rng.integers(0, len(pools[pool]), n, dtype=np.int32)
    
    # Data Construction
    # OPTIMIZATION: Direct pyarrow construction would be even faster, 
    # but dictionary -> Table -> Parquet is robust and readable.
    # Using specific PyArrow types for efficiency.
    
    data = {
        # 'trans_date_trans_time': Use unix_time directly instead
        'unix_time': unix_times, # Keep raw int64 for efficiency
        
        'cc_num': rng.integers(4000000000000000, 5000000000000000, size=n, dtype=np.int64),
        'merchant': pools['merchant'][idx('merchant')],
        'category': pools['categories'][rng.choice(len(pools['categories']), size=n, p=pools['category_weights'])],
        'amt': amts,
        'first': pools['first'][idx('first')],
        'last': pools['last'][idx('last')],
        'gender': np.where(rng.random(n) < 0.5, 'M', 'F'),
        'street': pools['street'][idx('street')],
        'city': pools['city'][idx('city')],
        'state': pools['states'][rng.choice(len(pools['states']), size=n, p=pools['state_weights'])],
        'zip': rng.integers(10000, 99999, size=n, dtype=np.int32),
        'lat': lats,
        'long': longs,
        'city_pop': rng.integers(1000, 2000000, size=n, dtype=np.int32),
        'job': pools['job'][idx('job')],
        'dob': pools['dob'][idx('dob')],
        'trans_num': pools['trans_num'][idx('trans_num')],
        
        # Redundant but kept for compatibility with original schema if needed
        'merch_lat': merch_lats,
        'merch_long': merch_longs,
        'is_fraud': (rng.random(n) < fraud_rate).astype(np.int8),
        'merch_zipcode': rng.integers(10000, 99999, size=n, dtype=np.int32),
    }
    
    return data

# Parse args
worker_id = int(sys.argv[1])
output_dir = Path(sys.argv[2])
chunk_size = int(sys.argv[3])
duration = int(sys.argv[4])
pools_file = sys.argv[5]
fraud_rate = float(sys.argv[6])

# Load pools and init RNG
with open(pools_file, 'rb') as f:
    pools = pickle.load(f)
rng = np.random.default_rng(seed=worker_id * 54321 + int(time.time() * 1000) % 100000)
base_time = 1704067200  # 2024-01-01

# Generate until duration expires
start = time.time()
file_count = 0

# Define Schema for better performance
schema = pa.schema([
    ('unix_time', pa.int64()),
    ('cc_num', pa.int64()),
    ('merchant', pa.string()),
    ('category', pa.string()),
    ('amt', pa.float32()),
    ('first', pa.string()),
    ('last', pa.string()),
    ('gender', pa.string()),
    ('street', pa.string()),
    ('city', pa.string()),
    ('state', pa.string()),
    ('zip', pa.int32()),
    ('lat', pa.float32()),
    ('long', pa.float32()),
    ('city_pop', pa.int32()),
    ('job', pa.string()),
    ('dob', pa.string()),
    ('trans_num', pa.string()),
    ('merch_lat', pa.float32()),
    ('merch_long', pa.float32()),
    ('is_fraud', pa.int8()),
    ('merch_zipcode', pa.int32()),
])

try:
    # Continuous mode if duration is 0
    is_continuous = (duration == 0)
    
    while is_continuous or (time.time() - start) < duration:
        data = generate_chunk(pools, chunk_size, rng, fraud_rate, base_time)
        table = pa.Table.from_pydict(data, schema=schema)
        output_file = output_dir / f"worker_{worker_id:03d}_{file_count:05d}.parquet"
        pq.write_table(table, output_file, compression='snappy')
        file_count += 1
except Exception as e:
    # Just exit if error, minimal logging in worker
    pass
'''




def main():
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Configuration
    output_dir = StoragePaths.get_path('raw_data')
    num_workers = int(os.getenv('NUM_WORKERS', '4'))  # Reduced for continuous mode
    chunk_size = int(os.getenv('CHUNK_SIZE', '50000'))  # Smaller batches
    fraud_rate = float(os.getenv('FRAUD_RATE', '0.005'))
    
    # NEW: Continuous mode configuration
    continuous_mode = os.getenv('CONTINUOUS_MODE', 'true').lower() == 'true'
    target_rate = int(os.getenv('GENERATION_RATE', str(GenerationRateLimits.DEFAULT_RATE)))
    backlog_threshold = BacklogThresholds.THRESHOLDS[QueueTopics.RAW_TRANSACTIONS]['warning']
    
    # Set duration (0 for continuous mode)
    if continuous_mode:
        duration = 0  # Continuous mode (no time limit)
    else:
        duration = int(os.getenv('DURATION_SECONDS', '300'))  # Default 5 minutes
    
    # Queue service
    queue_service = get_queue_service()
    
    # Create timestamped output directory
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    run_path = output_dir / f"run_{timestamp}"
    run_path.mkdir(parents=True, exist_ok=True)
    
    # Print configuration
    log("=" * 70)
    log("Pod 1: Continuous Fraud Data Generator")
    log("=" * 70)
    log(f"Output:   {run_path}")
    log(f"Workers:  {num_workers}")
    log(f"Mode:     {'Continuous' if continuous_mode else 'Batch'}")
    log(f"Target Rate: {target_rate:,} rows/sec")
    log(f"Chunk:    {chunk_size:,} rows")
    log(f"Backlog Threshold: {backlog_threshold:,}")
    log("-" * 70)
    
    # Generate string pools
    pools_file = generate_pools(run_path)
    
    # Launch worker processes
    log(f"Launching {num_workers} workers...")
    processes = []
    for i in range(num_workers):
        p = subprocess.Popen(
            [sys.executable, '-c', WORKER_SCRIPT, 
             str(i), str(run_path), str(chunk_size), str(duration), 
             str(pools_file), str(fraud_rate)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        processes.append(p)
    
    # Monitor progress
    start_time = time.time()
    last_bytes = 0
    last_time = start_time
    
    # NEW: Continuous generation loop with backlog checking
    batch_count = 0
    total_rows_generated = 0
    
    while not STOP_FLAG:
        elapsed = time.time() - start_time
        running = sum(1 for p in processes if p.poll() is None)
        
        # Check if we should continue (continuous mode or duration not exceeded)
        if not continuous_mode:
            duration = int(os.getenv('DURATION_SECONDS', '10'))
            if elapsed >= duration + 2 or running == 0:
                break
        
        # NEW: Check backlog and throttle if needed
        try:
            backlog = queue_service.get_backlog(QueueTopics.RAW_TRANSACTIONS)
            if backlog > backlog_threshold:
                log(f"⚠️  Backlog too high ({backlog:,}), pausing generation...")
                time.sleep(5)
                continue
        except:
            backlog = 0
        
        # Update stats every 1 second for live dashboard
        if time.time() - last_time >= 1.0:
            files = list(run_path.glob("worker_*.parquet"))
            current_bytes = sum(f.stat().st_size for f in files) if files else 0
            interval = time.time() - last_time
            speed = ((current_bytes - last_bytes) / (1024**3)) / interval
            total_gb = current_bytes / (1024**3)
            
            # NEW: Publish to queue
            if files:
                # Read files that are NOT being currently written (older than 2 seconds)
                stable_files = [f for f in files if time.time() - f.stat().st_mtime > 2.0]
                
                if stable_files:
                    # Read 50 stable files and publish to FlashBlade queue
                    recent_files = sorted(stable_files, key=lambda x: x.stat().st_mtime, reverse=True)[:50]
                    for file in recent_files:
                        try:
                            # Read parquet and convert to dict for queue
                            table = pq.read_table(file)
                            records = table.to_pydict()
                            # Convert to list of dicts (row-wise)
                            num_rows = len(records[list(records.keys())[0]])
                            
                            batch_data = []
                            for i in range(min(num_rows, 10000)):  # Increased batch size to 10K
                                row = {k: v[i] for k, v in records.items()}
                                # Convert numpy types to Python types for JSON serialization
                                row = {k: (int(v) if isinstance(v, (np.integer, np.int64, np.int32)) 
                                          else float(v) if isinstance(v, (np.floating, np.float32, np.float64))
                                          else str(v) if isinstance(v, (np.str_, bytes))
                                          else v) for k, v in row.items()}
                                batch_data.append(row)
                            
                            if batch_data:
                                queue_service.publish_batch(QueueTopics.RAW_TRANSACTIONS, batch_data)
                                total_rows_generated += len(batch_data)
                        except Exception as e:
                            log(f"Error publishing to queue: {e}")
            
            log(f"[{elapsed:5.1f}s] Files: {len(files):5d} | "
                f"Size: {total_gb:6.2f} GB | Speed: {speed:5.2f} GB/s | Workers: {running} | Backlog: {backlog:,}")
            
            # Resource Monitoring
            try:
                if PSUTIL_AVAILABLE:
                    cpu_percent = psutil.cpu_percent(interval=None)
                    mem_info = psutil.virtual_memory()
                    mem_gb = mem_info.used / (1024**3)
                    log(f"        CPU: {cpu_percent:5.1f}% | RAM: {mem_info.percent:5.1f}% ({mem_gb:.1f} GB) | Queue Published: {total_rows_generated:,}")
                    
                    # Update Dashboard Stats
                    total_rows = len(files) * chunk_size
                    throughput = total_rows / elapsed if elapsed > 0 else 0
                    cpu_cores = (cpu_percent / 100.0) * psutil.cpu_count()
                    log_telemetry(total_rows, throughput, elapsed, cpu_cores, mem_gb, mem_info.percent)
                else:
                    # No psutil, use basic metrics
                    total_rows = len(files) * chunk_size
                    throughput = total_rows / elapsed if elapsed > 0 else 0
                    log_telemetry(total_rows, throughput, elapsed, 0.0, 0.0, 0.0)
            except:
                pass

            last_bytes = current_bytes
            last_time = time.time()
        
        time.sleep(1)
    
    # Cleanup - Wait for workers to finish naturally
    log("Waiting for workers to sync and exit...")
    for p in processes:
        try:
            p.wait(timeout=2)
        except subprocess.TimeoutExpired:
            p.terminate()
    
    # Final stats
    pools_file.unlink(missing_ok=True)
    
    log("=" * 70)
    log("COMPLETE")
    
    # Final Summary for Master Script
    files = list(run_path.glob("worker_*.parquet"))
    total_bytes = sum(f.stat().st_size for f in files) if files else 0
    total_gb = total_bytes / (1024**3)
    
    # Approx row count based on file size or metadata (or just chunk size * files * chunks/file if we knew)
    # We can estimate rows: chunk_size * num_workers * (duration / per_chunk_time? no)
    # Better: Open one file to get rows or trust the known chunk size.
    # Since we are optimizing, opening every file is slow. 
    # Let's just estimate: Size / (Size/Row). 
    # Or count files * chunk_size (approximation if last chunk is full)
    # Actually, we know chunk_size is passed to worker.
    # Worker generates full chunks in loop.
    # Let's count files.
    
    total_rows = len(files) * chunk_size 
    
    elapsed_total = time.time() - start_time
    throughput_rows = total_rows / elapsed_total if elapsed_total > 0 else 0
    
    log(f"METRICS: Rows={total_rows} | Time={elapsed_total:.2f}s | Throughput={throughput_rows:.1f} rows/s | Size={total_gb:.2f} GB")
    
    # Add explicit resource summary
    if PSUTIL_AVAILABLE:
        mem_info = psutil.virtual_memory()
        mem_gb = mem_info.used / (1024 ** 3)
        
        # Calculate Cores used
        # cpu_percent is 0-100 system wide. 
        # To get "Cores", generally for a process we sum per-cpu. 
        # For system wide, 100% = All Cores. 
        # So (percent / 100) * total_cores
        cpu_cores = (psutil.cpu_percent() / 100.0) * psutil.cpu_count()
        
        log(f"METRICS: CPU={cpu_cores:.1f} Cores | RAM={mem_info.percent:.1f}% ({mem_gb:.2f} GB)")
    
    log("=" * 70)
    
    # Final Stats update
    log_telemetry(total_rows, total_rows/elapsed_total if elapsed_total > 0 else 0, elapsed_total, cpu_cores, mem_gb, mem_info.percent, status="Completed")


if __name__ == "__main__":
    main()
