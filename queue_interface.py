#!/usr/bin/env python3
"""
FlashBlade File-Based Queue Interface
Provides file-based queuing using FlashBlade storage with sequential naming and directory-based state tracking.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from pathlib import Path
import json
import time
import threading
from datetime import datetime


class QueueInterface(ABC):
    """Abstract base class for queue implementations"""
    
    @abstractmethod
    def publish(self, topic: str, message: Dict[str, Any]) -> bool:
        """Publish a message to a topic/queue"""
        pass
    
    @abstractmethod
    def publish_batch(self, topic: str, messages: List[Dict[str, Any]]) -> bool:
        """Publish multiple messages to a topic/queue"""
        pass
    
    @abstractmethod
    def consume(self, topic: str, timeout: float = 1.0) -> Optional[Dict[str, Any]]:
        """Consume a single message from a topic/queue"""
        pass
    
    @abstractmethod
    def consume_batch(self, topic: str, batch_size: int = 100, timeout: float = 1.0) -> List[Dict[str, Any]]:
        """Consume multiple messages from a topic/queue"""
        pass
    
    @abstractmethod
    def get_backlog(self, topic: str) -> int:
        """Get the current backlog/depth of a queue"""
        pass
    
    @abstractmethod
    def clear(self, topic: str) -> bool:
        """Clear all messages from a queue"""
        pass

    @abstractmethod
    def increment_metric(self, name: str, amount: int = 1) -> bool:
        """Atomically increment a global metric"""
        pass

    @abstractmethod
    def set_metric(self, name: str, value: Any) -> bool:
        """Set a global metric to a specific value"""
        pass

    @abstractmethod
    def get_metric(self, name: str) -> Any:
        """Get the value of a specific metric"""
        pass

    @abstractmethod
    def get_metrics(self, prefix: str = "") -> Dict[str, Any]:
        """Get all metrics with given prefix"""
        pass

    @abstractmethod
    def clear_metrics(self) -> bool:
        """Clear all global metrics"""
        pass


class FlashBladeQueue(QueueInterface):
    """
    File-based queue implementation using FlashBlade storage.
    Uses sequential file naming and directory-based state tracking.
    """
    
    def __init__(self, base_path: str = "/mnt/flashblade"):
        self.base_path = Path(base_path)
        self.counters = {}  # Topic -> file counter
        self.counter_lock = threading.Lock()
        self.metrics = {}  # Global metrics
        self.metrics_lock = threading.Lock()
        
        # Create base directory structure
        self._init_directories()
        
        # Load existing counters and metrics
        self._load_counters()
        self._load_metrics()
    
    def _init_directories(self):
        """Initialize directory structure for all topics"""
        from config_contract import FileQueuePaths
        
        # Get all queue paths from config
        queue_paths = [
            FileQueuePaths.RAW_PENDING, FileQueuePaths.RAW_PROCESSING, FileQueuePaths.RAW_COMPLETED,
            FileQueuePaths.FEATURES_PENDING, FileQueuePaths.FEATURES_PROCESSING, FileQueuePaths.FEATURES_COMPLETED,
            FileQueuePaths.RESULTS_PENDING, FileQueuePaths.RESULTS_PROCESSING, FileQueuePaths.RESULTS_COMPLETED,
            FileQueuePaths.TRAINING_PENDING, FileQueuePaths.TRAINING_PROCESSING, FileQueuePaths.TRAINING_COMPLETED
        ]
        
        for path in queue_paths:
            (self.base_path / path).mkdir(parents=True, exist_ok=True)
    
    def _get_topic_paths(self, topic: str) -> Dict[str, Path]:
        """Get pending/processing/completed paths for a topic"""
        from config_contract import FileQueuePaths
        
        # Map topic names to directory paths
        topic_map = {
            "raw-transactions": (FileQueuePaths.RAW_PENDING, FileQueuePaths.RAW_PROCESSING, FileQueuePaths.RAW_COMPLETED),
            "features-ready": (FileQueuePaths.FEATURES_PENDING, FileQueuePaths.FEATURES_PROCESSING, FileQueuePaths.FEATURES_COMPLETED),
            "inference-results": (FileQueuePaths.RESULTS_PENDING, FileQueuePaths.RESULTS_PROCESSING, FileQueuePaths.RESULTS_COMPLETED),
            "training-queue": (FileQueuePaths.TRAINING_PENDING, FileQueuePaths.TRAINING_PROCESSING, FileQueuePaths.TRAINING_COMPLETED)
        }
        
        pending, processing, completed = topic_map.get(topic, (f"queue/{topic}/pending", f"queue/{topic}/processing", f"queue/{topic}/completed"))
        
        return {
            "pending": self.base_path / pending,
            "processing": self.base_path / processing,
            "completed": self.base_path / completed
        }
    
    def _load_counters(self):
        """Load existing file counters from disk"""
        counter_file = self.base_path / "queue" / ".counters.json"
        if counter_file.exists():
            try:
                with open(counter_file, 'r') as f:
                    self.counters = json.load(f)
            except:
                self.counters = {}
    
    def _load_metrics(self):
        """Load global metrics from disk. On error, keep existing in-memory metrics."""
        metrics_file = self.base_path / "queue" / ".metrics.json"
        if not metrics_file.exists():
            return
        try:
            with open(metrics_file, 'r') as f:
                data = json.load(f)
            if isinstance(data, dict):
                self.metrics = data
        except Exception:
            pass

    def _save_metrics(self):
        """Save global metrics to disk"""
        metrics_file = self.base_path / "queue" / ".metrics.json"
        metrics_file.parent.mkdir(parents=True, exist_ok=True)
        with open(metrics_file, 'w') as f:
            json.dump(self.metrics, f)

    def _save_counters(self):
        """Save file counters to disk"""
        counter_file = self.base_path / "queue" / ".counters.json"
        counter_file.parent.mkdir(parents=True, exist_ok=True)
        with open(counter_file, 'w') as f:
            json.dump(self.counters, f)
    
    def _get_next_filename(self, topic: str) -> str:
        """Get next sequential filename for topic"""
        with self.counter_lock:
            if topic not in self.counters:
                self.counters[topic] = 0
            self.counters[topic] += 1
            counter = self.counters[topic]
            self._save_counters()
            return f"batch_{counter:09d}.parquet"
    
    def publish(self, topic: str, message: Dict[str, Any]) -> bool:
        """Publish a single message (writes as JSON file)"""
        return self.publish_batch(topic, [message])
    
    def publish_batch(self, topic: str, messages: List[Dict[str, Any]]) -> bool:
        """Publish batch of messages as a Parquet file"""
        if not messages:
            return True
        
        try:
            import polars as pl
            
            # Convert messages to DataFrame
            df = pl.DataFrame(messages)
            
            # Get next filename
            filename = self._get_next_filename(topic)
            paths = self._get_topic_paths(topic)
            file_path = paths["pending"] / filename
            
            # Write Parquet file
            df.write_parquet(file_path)
            
            return True
        except Exception as e:
            print(f"Error publishing to {topic}: {e}")
            return False
    
    def consume(self, topic: str, timeout: float = 1.0) -> Optional[Dict[str, Any]]:
        """Consume a single message"""
        batch = self.consume_batch(topic, batch_size=1, timeout=timeout)
        return batch[0] if batch else None
    
    def consume_batch(self, topic: str, batch_size: int = 100, timeout: float = 1.0) -> List[Dict[str, Any]]:
        """Consume batch of messages by reading Parquet files"""
        import polars as pl
        
        paths = self._get_topic_paths(topic)
        pending_dir = paths["pending"]
        processing_dir = paths["processing"]
        completed_dir = paths["completed"]
        
        # Get pending files (sorted alphabetically = sequential order)
        pending_files = sorted(pending_dir.glob("batch_*.parquet"))
        
        if not pending_files:
            time.sleep(timeout)
            return []
        
        # Process up to batch_size files
        messages = []
        files_processed = 0
        
        for file_path in pending_files[:batch_size]:
            try:
                # Move to processing (atomic operation)
                processing_path = processing_dir / file_path.name
                file_path.rename(processing_path)
                
                # Read Parquet file
                df = pl.read_parquet(processing_path)
                
                # Convert to list of dicts
                batch_messages = df.to_dicts()
                messages.extend(batch_messages)
                
                # Move to completed
                completed_path = completed_dir / file_path.name
                processing_path.rename(completed_path)
                
                files_processed += 1
                
            except Exception as e:
                print(f"Error consuming from {topic}: {e}")
                # Try to move file back to pending if it's still in processing
                if processing_path.exists():
                    try:
                        processing_path.rename(file_path)
                    except:
                        pass
        
        return messages
    
    def get_backlog(self, topic: str) -> int:
        """Get backlog as count of pending files"""
        paths = self._get_topic_paths(topic)
        pending_files = list(paths["pending"].glob("batch_*.parquet"))
        return len(pending_files)
    
    def clear(self, topic: str) -> bool:
        """Clear all files from pending/processing/completed directories"""
        try:
            paths = self._get_topic_paths(topic)
            
            for dir_type in ["pending", "processing", "completed"]:
                for file in paths[dir_type].glob("batch_*.parquet"):
                    file.unlink()
            
            return True
        except Exception as e:
            print(f"Error clearing {topic}: {e}")
            return False
    
    def increment_metric(self, name: str, amount: float = 1) -> bool:
        """Atomically increment a global metric (amount may be int or float)."""
        with self.metrics_lock:
            self._load_metrics()
            val = self.metrics.get(name, 0)
            if not isinstance(val, (int, float)):
                val = 0
            self.metrics[name] = val + amount
            self._save_metrics()
        return True
    
    def set_metric(self, name: str, value: Any) -> bool:
        """Set a global metric to a specific value"""
        with self.metrics_lock:
            self.metrics[name] = value
            self._save_metrics()
        return True

    def get_metric(self, name: str) -> Any:
        """Get the value of a specific metric"""
        with self.metrics_lock:
            self._load_metrics()
            return self.metrics.get(name)

    def get_metrics(self, prefix: str = "") -> Dict[str, Any]:
        """Get all metrics with given prefix"""
        with self.metrics_lock:
            self._load_metrics()
            return {k: v for k, v in self.metrics.items() if k.startswith(prefix)}
    
    def clear_metrics(self) -> bool:
        """Clear all global metrics"""
        with self.metrics_lock:
            self.metrics.clear()
            self._save_metrics()
        return True


def get_queue_service() -> QueueInterface:
    """Factory function to get queue service instance"""
    from config_contract import StoragePaths, get_env, EnvironmentVariables
    
    # Always use FlashBlade queue (with local fallback)
    flashblade_path = get_env(EnvironmentVariables.FLASHBLADE_PATH, "/mnt/flashblade")
    
    # If FlashBlade not mounted, use local path
    if not Path(flashblade_path).exists():
        from pathlib import Path as P
        local_base = P(__file__).parent / "run_queue_data"
        local_base.mkdir(parents=True, exist_ok=True)
        flashblade_path = str(local_base)
        print(f"FlashBlade not mounted, using local queue: {flashblade_path}")
    
    return FlashBladeQueue(base_path=flashblade_path)
