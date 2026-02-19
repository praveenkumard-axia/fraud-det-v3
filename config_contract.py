#!/usr/bin/env python3
"""
Configuration Contracts
This file defines the interface between Backend Development and DevOps.
Backend developers use these configurations, DevOps implements them.
"""

from typing import Dict, Any
from pathlib import Path
import os


class QueueTopics:
    """
    Queue topic definitions
    DevOps must create these topics in Kafka/RabbitMQ with specified configurations
    """
    
    RAW_TRANSACTIONS = "raw-transactions"
    FEATURES_READY = "features-ready"
    INFERENCE_RESULTS = "inference-results"
    TRAINING_QUEUE = "training-queue"
    
    # Topic configurations (for DevOps reference)
    CONFIGS = {
        RAW_TRANSACTIONS: {
            "partitions": 16,
            "retention_hours": 24,
            "description": "Raw transaction data from generator"
        },
        FEATURES_READY: {
            "partitions": 16,
            "retention_hours": 12,
            "description": "Preprocessed features ready for inference/training"
        },
        INFERENCE_RESULTS: {
            "partitions": 8,
            "retention_hours": 6,
            "description": "Inference results from model"
        },
        TRAINING_QUEUE: {
            "partitions": 4,
            "retention_hours": 48,
            "description": "Training data batches"
        }
    }


class StoragePaths:
    """
    Storage path definitions
    DevOps must mount FlashBlade or NFS at these paths
    """
    
    CPU_BASE_PATH = Path("/mnt/cpu-fb")
    GPU_BASE_PATH = Path("/mnt/gpu-fb")
    
    RAW_DATA = Path("raw")
    FEATURES = Path("features")
    MODELS = Path("models")
    RESULTS = Path("results")
    
    # Fallback to local paths for development
    @classmethod
    def get_path(cls, path_type: str, volume: str = "cpu") -> Path:
        """Get storage path based on volume and type"""
        base = cls.CPU_BASE_PATH if volume == "cpu" else cls.GPU_BASE_PATH
        
        # Check override environment variables
        if volume == "cpu":
            base = Path(os.getenv("CPU_VOLUME_PATH", str(base)))
        else:
            base = Path(os.getenv("GPU_VOLUME_PATH", str(base)))

        sub_path = {
            "raw": cls.RAW_DATA,
            "features": cls.FEATURES,
            "models": cls.MODELS,
            "results": cls.RESULTS
        }.get(path_type, Path(""))

        path = base / sub_path
        
        # Fallback to local paths if not mounted
        if not base.exists():
            local_base = Path(__file__).parent
            path = local_base / "run_queue_data" / volume / sub_path
        
        path.mkdir(parents=True, exist_ok=True)
        return path


class ScalingConfig:
    """
    Kubernetes deployment configurations
    DevOps must configure kubectl access for these deployments
    """
    
    DEPLOYMENTS = {
        "data-gather": {
            "min_replicas": 1,
            "max_replicas": 1,  # Usually only 1 generator
            "default_replicas": 1
        },
        "preprocessing": {
            "min_replicas": 1,
            "max_replicas": 1,
            "default_replicas": 1
        },
        "training": {
            "min_replicas": 0,  # Can be 0 when not training
            "max_replicas": 1,
            "default_replicas": 1
        },
        "inference": {
            "min_replicas": 1,
            "max_replicas": 1,
            "default_replicas": 1
        },
        "preprocessing-gpu": {
            "min_replicas": 0,
            "max_replicas": 1,
            "default_replicas": 1
        },
        "inference-gpu": {
            "min_replicas": 0,
            "max_replicas": 1,
            "default_replicas": 1
        }
    }
    
    # Scaling commands (for DevOps to implement)
    SCALE_COMMAND_TEMPLATE = "kubectl scale deployment/{deployment} --replicas={replicas}"


class BacklogThresholds:
    """
    Backlog thresholds for triggering alerts/throttling
    """
    
    THRESHOLDS = {
        QueueTopics.RAW_TRANSACTIONS: {
            "warning": 1500000,     
            "critical": 3000000,
            "action": "throttle_generation"
        },
        QueueTopics.FEATURES_READY: {
            "warning": 250000,
            "critical": 500000,
            "action": "scale_inference"
        },
        QueueTopics.INFERENCE_RESULTS: {
            "warning": 100000,
            "critical": 200000,
            "action": "alert_only"
        }
    }


class SystemPriorities:
    """
    System priority modes
    """
    
    INFERENCE = "inference"
    TRAINING = "training"
    BALANCED = "balanced"
    
    VALID_PRIORITIES = [INFERENCE, TRAINING, BALANCED]


class GenerationRateLimits:
    """
    Data generation rate limits all values are row/sec
    """
    
    MIN_RATE = 1000     
    MAX_RATE = 1000000   
    DEFAULT_RATE = 100000


class MetricsConfig:
    """
    Metrics and monitoring configuration
    DevOps must configure Prometheus/OpenTelemetry to scrape these
    """
    
    METRICS_PORT = 8000
    METRICS_PATH = "/metrics"
    
    # Metric names (Prometheus format)
    METRICS = {
        "transactions_generated_total": "Counter: Total transactions generated",
        "transactions_preprocessed_total": "Counter: Total transactions preprocessed",
        "transactions_inferred_total": "Counter: Total transactions inferred",
        "queue_depth_current": "Gauge: Current queue depth by topic",
        "processing_latency_seconds": "Histogram: Processing latency by stage",
        "pod_count_current": "Gauge: Current pod count by deployment",
        "backlog_pressure_percent": "Gauge: Backlog pressure percentage by queue",
        "generation_rate_current": "Gauge: Current generation rate",
        "system_priority": "Gauge: Current system priority (0=training, 1=inference)"
    }


class EnvironmentVariables:
    """
    Environment variables that pods expect
    DevOps must set these in Kubernetes deployments
    """
    
    # Storage configuration (FlashBlade-based queuing)
    FLASHBLADE_ENABLED = "FLASHBLADE_ENABLED"
    FLASHBLADE_PATH = "FLASHBLADE_PATH"
    
    # Dual-Volume Configuration
    CPU_VOLUME_PATH = "CPU_VOLUME_PATH"
    GPU_VOLUME_PATH = "GPU_VOLUME_PATH"
    INPUT_PATH = "INPUT_PATH"
    OUTPUT_PATH = "OUTPUT_PATH"
    OUTPUT_PATH_SECONDARY = "OUTPUT_PATH_SECONDARY"
    
    # File-based queue configuration
    POLL_INTERVAL_SECONDS = "POLL_INTERVAL_SECONDS"  # How often to check for new files
    BATCH_FILE_SIZE = "BATCH_FILE_SIZE"  # Rows per file
    MAX_FILES_PER_POLL = "MAX_FILES_PER_POLL"  # Max files to process per iteration
    
    # Pod-specific configuration
    GENERATION_RATE = "GENERATION_RATE"
    BATCH_SIZE = "BATCH_SIZE"
    
    # System configuration
    SYSTEM_PRIORITY = "SYSTEM_PRIORITY"
    ENABLE_METRICS = "ENABLE_METRICS"

    # Prometheus metrics (1s polling -> JSON)
    PROMETHEUS_URL = "PROMETHEUS_URL"
    PROMETHEUS_READ_THROUGHPUT_QUERY = "PROMETHEUS_READ_THROUGHPUT_QUERY"
    PROMETHEUS_WRITE_THROUGHPUT_QUERY = "PROMETHEUS_WRITE_THROUGHPUT_QUERY"
    PROMETHEUS_UTIL_QUERY = "PROMETHEUS_UTIL_QUERY"
    PROMETHEUS_LATENCY_QUERY = "PROMETHEUS_LATENCY_QUERY"

    # Pure1 API (FlashBlade current_bw / max_bw)
    PURE1_API_TOKEN = "PURE1_API_TOKEN"
    PURE1_ARRAY_ID = "PURE1_ARRAY_ID"

    # Pure Storage / FlashBlade mode: when "true", enables Pure1 and FB-specific Prometheus metrics
    PURE_SERVER = "PURE_SERVER"

    # Defaults
    DEFAULTS = {
        FLASHBLADE_ENABLED: "false",
        FLASHBLADE_PATH: "/mnt/flashblade",
        POLL_INTERVAL_SECONDS: "1",  # Check for new files every 1 second
        BATCH_FILE_SIZE: "10000",  # 10k rows per file (~3-5 MB)
        MAX_FILES_PER_POLL: "50",  # Process up to 50 files per iteration
        GENERATION_RATE: str(GenerationRateLimits.DEFAULT_RATE),
        BATCH_SIZE: "50000",
        SYSTEM_PRIORITY: SystemPriorities.BALANCED,
        ENABLE_METRICS: "true",
        PURE_SERVER: "false"  # set "true" to enable Pure1 + FlashBlade metrics
    }


class FileQueuePaths:
    """
    Directory structure for file-based queuing on FlashBlade
    """
    
    # Stage 1: Raw transactions (Generator -> Data Prep)
    RAW_PENDING = "queue/raw-transactions/pending"
    RAW_PROCESSING = "queue/raw-transactions/processing"
    RAW_COMPLETED = "queue/raw-transactions/completed"
    
    # Stage 2: Features (Data Prep -> Inference)
    FEATURES_PENDING = "queue/features-ready/pending"
    FEATURES_PROCESSING = "queue/features-ready/processing"
    FEATURES_COMPLETED = "queue/features-ready/completed"
    
    # Stage 3: Inference results
    RESULTS_PENDING = "queue/inference-results/pending"
    RESULTS_PROCESSING = "queue/inference-results/processing"
    RESULTS_COMPLETED = "queue/inference-results/completed"
    
    # Training data
    TRAINING_PENDING = "queue/training-queue/pending"
    TRAINING_PROCESSING = "queue/training-queue/processing"
    TRAINING_COMPLETED = "queue/training-queue/completed"


# Helper function to get environment variable with default
def get_env(key: str, default: Any = None) -> str:
    """Get environment variable with fallback to default"""
    import os
    return os.getenv(key, EnvironmentVariables.DEFAULTS.get(key, default))
