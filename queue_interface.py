#!/usr/bin/env python3
"""
Queue Interface Abstraction
Provides a unified interface for queue operations.
DevOps can implement this with Kafka, RabbitMQ, Redis Streams, etc.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Callable
import threading
import time
from collections import deque
import json


class QueueInterface(ABC):
    """Abstract base class for queue implementations"""
    
    @abstractmethod
    def publish(self, topic: str, message: Dict[str, Any]) -> bool:
        """
        Publish a message to a topic/queue
        
        Args:
            topic: Topic/queue name
            message: Message data as dictionary
            
        Returns:
            True if successful, False otherwise
        """
        pass
    
    @abstractmethod
    def publish_batch(self, topic: str, messages: List[Dict[str, Any]]) -> bool:
        """
        Publish multiple messages to a topic/queue
        
        Args:
            topic: Topic/queue name
            messages: List of message dictionaries
            
        Returns:
            True if successful, False otherwise
        """
        pass
    
    @abstractmethod
    def consume(self, topic: str, timeout: float = 1.0) -> Optional[Dict[str, Any]]:
        """
        Consume a single message from a topic/queue
        
        Args:
            topic: Topic/queue name
            timeout: Timeout in seconds
            
        Returns:
            Message dictionary or None if no message available
        """
        pass
    
    @abstractmethod
    def consume_batch(self, topic: str, batch_size: int = 100, timeout: float = 1.0) -> List[Dict[str, Any]]:
        """
        Consume multiple messages from a topic/queue
        
        Args:
            topic: Topic/queue name
            batch_size: Maximum number of messages to consume
            timeout: Timeout in seconds
            
        Returns:
            List of message dictionaries (may be empty)
        """
        pass
    
    @abstractmethod
    def get_backlog(self, topic: str) -> int:
        """
        Get the current backlog/depth of a queue
        
        Args:
            topic: Topic/queue name
            
        Returns:
            Number of messages waiting in queue
        """
        pass
    
    @abstractmethod
    def clear(self, topic: str) -> bool:
        """
        Clear all messages from a queue
        
        Args:
            topic: Topic/queue name
            
        Returns:
            True if successful
        """
        pass


class InMemoryQueue(QueueInterface):
    """
    In-memory queue implementation for development/testing
    This is what YOU (backend dev) will use for local testing
    DevOps will replace this with KafkaQueue in production
    """
    
    def __init__(self):
        self.queues: Dict[str, deque] = {}
        self.locks: Dict[str, threading.Lock] = {}
    
    def _get_queue(self, topic: str) -> deque:
        """Get or create a queue for a topic"""
        if topic not in self.queues:
            self.queues[topic] = deque()
            self.locks[topic] = threading.Lock()
        return self.queues[topic]
    
    def _get_lock(self, topic: str) -> threading.Lock:
        """Get lock for a topic"""
        if topic not in self.locks:
            self.locks[topic] = threading.Lock()
        return self.locks[topic]
    
    def publish(self, topic: str, message: Dict[str, Any]) -> bool:
        """Publish a single message"""
        try:
            queue = self._get_queue(topic)
            lock = self._get_lock(topic)
            
            with lock:
                # Serialize to JSON and back to ensure data is serializable
                serialized = json.dumps(message)
                deserialized = json.loads(serialized)
                queue.append(deserialized)
            
            return True
        except Exception as e:
            print(f"Error publishing to {topic}: {e}")
            return False
    
    def publish_batch(self, topic: str, messages: List[Dict[str, Any]]) -> bool:
        """Publish multiple messages"""
        try:
            queue = self._get_queue(topic)
            lock = self._get_lock(topic)
            
            with lock:
                for message in messages:
                    serialized = json.dumps(message)
                    deserialized = json.loads(serialized)
                    queue.append(deserialized)
            
            return True
        except Exception as e:
            print(f"Error publishing batch to {topic}: {e}")
            return False
    
    def consume(self, topic: str, timeout: float = 1.0) -> Optional[Dict[str, Any]]:
        """Consume a single message"""
        queue = self._get_queue(topic)
        lock = self._get_lock(topic)
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            with lock:
                if queue:
                    return queue.popleft()
            
            # Small sleep to avoid busy waiting
            time.sleep(0.01)
        
        return None
    
    def consume_batch(self, topic: str, batch_size: int = 100, timeout: float = 1.0) -> List[Dict[str, Any]]:
        """Consume multiple messages"""
        queue = self._get_queue(topic)
        lock = self._get_lock(topic)
        
        messages = []
        start_time = time.time()
        
        while len(messages) < batch_size and time.time() - start_time < timeout:
            with lock:
                while queue and len(messages) < batch_size:
                    messages.append(queue.popleft())
            
            # If we got some messages, return them
            if messages:
                break
            
            # Small sleep to avoid busy waiting
            time.sleep(0.01)
        
        return messages
    
    def get_backlog(self, topic: str) -> int:
        """Get current queue depth"""
        queue = self._get_queue(topic)
        lock = self._get_lock(topic)
        
        with lock:
            return len(queue)
    
    def clear(self, topic: str) -> bool:
        """Clear all messages from queue"""
        try:
            queue = self._get_queue(topic)
            lock = self._get_lock(topic)
            
            with lock:
                queue.clear()
            
            return True
        except Exception as e:
            print(f"Error clearing {topic}: {e}")
            return False


class RedisQueue(QueueInterface):
    """
    Redis implementation of the queue interface.
    Enables communication between different processes.
    """
    
    def __init__(self, redis_url: str):
        try:
            import redis
            self.redis = redis.from_url(redis_url)
            self.redis.ping()
        except ImportError:
            print("Error: 'redis' package not installed. Run 'pip install redis'")
            raise
        except Exception as e:
            print(f"Error connecting to Redis: {e}")
            raise
            
    def publish(self, topic: str, message: Dict[str, Any]) -> bool:
        try:
            self.redis.rpush(topic, json.dumps(message))
            return True
        except Exception as e:
            print(f"Error publishing to Redis {topic}: {e}")
            return False
            
    def publish_batch(self, topic: str, messages: List[Dict[str, Any]]) -> bool:
        try:
            if not messages:
                return True
            serialized_messages = [json.dumps(m) for m in messages]
            self.redis.rpush(topic, *serialized_messages)
            return True
        except Exception as e:
            print(f"Error publishing batch to Redis {topic}: {e}")
            return False
            
    def consume(self, topic: str, timeout: float = 1.0) -> Optional[Dict[str, Any]]:
        try:
            # blpop returns (topic, message)
            result = self.redis.blpop(topic, timeout=max(1, int(timeout)))
            if result:
                return json.loads(result[1])
            return None
        except Exception as e:
            print(f"Error consuming from Redis {topic}: {e}")
            return None
            
    def consume_batch(self, topic: str, batch_size: int = 100, timeout: float = 1.0) -> List[Dict[str, Any]]:
        messages = []
        # First try to get one message with timeout
        msg = self.consume(topic, timeout)
        if msg:
            messages.append(msg)
            # Then try to get more messages quickly without blocking
            while len(messages) < batch_size:
                # lpop returns a single message or None
                result = self.redis.lpop(topic)
                if result:
                    messages.append(json.loads(result))
                else:
                    break
        return messages
        
    def get_backlog(self, topic: str) -> int:
        try:
            return self.redis.llen(topic)
        except Exception as e:
            print(f"Error getting backlog from Redis {topic}: {e}")
            return 0
            
    def clear(self, topic: str) -> bool:
        try:
            self.redis.delete(topic)
            return True
        except Exception as e:
            print(f"Error clearing Redis {topic}: {e}")
            return False


# Global queue service instance cache
_queue_service_instance = None


def get_queue_service() -> QueueInterface:
    """Get the configured queue service (singleton pattern)"""
    global _queue_service_instance
    
    if _queue_service_instance is None:
        from config_contract import get_env, EnvironmentVariables
        queue_type = get_env(EnvironmentVariables.QUEUE_TYPE, "inmemory").lower()
        
        if queue_type == "redis":
            redis_url = get_env(EnvironmentVariables.REDIS_URL, "redis://localhost:6379/0")
            _queue_service_instance = RedisQueue(redis_url)
        else:
            # Fallback to in-memory for local testing/dev
            _queue_service_instance = InMemoryQueue()
            
    return _queue_service_instance
