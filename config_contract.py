#!/usr/bin/env python3
"""
Configuration Contracts
This file defines the interface between Backend Development and DevOps.
Backend developers use these configurations, DevOps implements them.
"""

from typing import Dict, Any
from pathlib import Path


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
    
    BASE_PATH = Path("/mnt/flashblade")
    
    RAW_DATA = BASE_PATH / "raw-data"
    FEATURES = BASE_PATH / "features"
    MODELS = BASE_PATH / "models"
    INFERENCE_LOGS = BASE_PATH / "inference-logs"
    
    # Fallback to local paths for development
    @classmethod
    def get_path(cls, path_type: str) -> Path:
        """Get storage path with fallback to local for development"""
        paths = {
            "raw_data": cls.RAW_DATA,
            "features": cls.FEATURES,
            "models": cls.MODELS,
            "inference_logs": cls.INFERENCE_LOGS
        }
        
        path = paths.get(path_type, cls.BASE_PATH)
        
        # If FlashBlade not mounted, use local paths
        if not cls.BASE_PATH.exists():
            local_base = Path(__file__).parent
            fallback_paths = {
                "raw_data": local_base / "run_data_output",
                "features": local_base / "run_features_output",
                "models": local_base / "run_models_output",
                "inference_logs": local_base / "run_inference_output"
            }
            path = fallback_paths.get(path_type, local_base)
        
        # Create directory if it doesn't exist
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
            "max_replicas": 10,
            "default_replicas": 1
        },
        "training": {
            "min_replicas": 0,  # Can be 0 when not training
            "max_replicas": 2,
            "default_replicas": 1
        },
        "inference": {
            "min_replicas": 1,
            "max_replicas": 20,
            "default_replicas": 2
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
            "warning": 1500000,      # Increase for 1M trigger demo
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
    Data generation rate limits
    """
    
    MIN_RATE = 1000      # rows/sec
    MAX_RATE = 100000    # rows/sec
    DEFAULT_RATE = 50000 # rows/sec


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
    
    # Queue configuration
    QUEUE_TYPE = "QUEUE_TYPE"  # "inmemory", "kafka", "rabbitmq", "redis"
    KAFKA_BOOTSTRAP_SERVERS = "KAFKA_BOOTSTRAP_SERVERS"
    REDIS_URL = "REDIS_URL"
    
    # Storage configuration
    FLASHBLADE_ENABLED = "FLASHBLADE_ENABLED"
    FLASHBLADE_PATH = "FLASHBLADE_PATH"
    
    # Pod-specific configuration
    GENERATION_RATE = "GENERATION_RATE"
    BATCH_SIZE = "BATCH_SIZE"
    CONSUMER_GROUP = "CONSUMER_GROUP"
    
    # System configuration
    SYSTEM_PRIORITY = "SYSTEM_PRIORITY"
    ENABLE_METRICS = "ENABLE_METRICS"
    
    # Defaults
    DEFAULTS = {
        QUEUE_TYPE: "inmemory",
        KAFKA_BOOTSTRAP_SERVERS: "localhost:9092",
        REDIS_URL: "redis://localhost:6379/0",
        FLASHBLADE_ENABLED: "false",
        FLASHBLADE_PATH: "/mnt/flashblade",
        GENERATION_RATE: str(GenerationRateLimits.DEFAULT_RATE),
        BATCH_SIZE: "50000",
        CONSUMER_GROUP: "fraud-pipeline",
        SYSTEM_PRIORITY: SystemPriorities.INFERENCE,
        ENABLE_METRICS: "true"
    }


# Helper function to get environment variable with default
def get_env(key: str, default: Any = None) -> str:
    """Get environment variable with fallback to default"""
    import os
    return os.getenv(key, EnvironmentVariables.DEFAULTS.get(key, default))
