"""Redis-based checkpoint saver for LangGraph state persistence."""

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import redis.asyncio as redis
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.base import Checkpoint as LangGraphCheckpoint

from .state import TaskCheckpoint, TaskMetadata, TaskStatus

logger = logging.getLogger(__name__)


class RedisCheckpointSaver(BaseCheckpointSaver):
    """
    Custom checkpoint saver that stores LangGraph state in Redis.
    
    Implements the LangGraph BaseCheckpointSaver interface while adding
    fault-tolerance features like lease management and atomic state updates.
    """
    
    def __init__(
        self,
        redis_client: redis.Redis,
        checkpoint_ttl: int = 86400 * 7,  # 7 days
    ):
        """
        Initialize Redis checkpoint saver.
        
        Args:
            redis_client: Async Redis client instance
            checkpoint_ttl: Time-to-live for checkpoints in seconds
        """
        super().__init__()
        self.redis = redis_client
        self.checkpoint_ttl = checkpoint_ttl
    
    async def save_checkpoint(
        self,
        task_id: str,
        checkpoint: TaskCheckpoint,
        update_metadata: bool = True
    ) -> None:
        """
        Save checkpoint to Redis atomically.
        
        Args:
            task_id: Unique task identifier
            checkpoint: Complete checkpoint state
            update_metadata: Whether to update task metadata
        """
        checkpoint.updated_at = datetime.utcnow()
        
        # Serialize checkpoint
        checkpoint_key = f"task:{task_id}:checkpoint"
        checkpoint_data = checkpoint.model_dump_json()
        
        async with self.redis.pipeline(transaction=True) as pipe:
            # Save checkpoint with TTL
            pipe.set(checkpoint_key, checkpoint_data, ex=self.checkpoint_ttl)
            
            if update_metadata:
                # Update task metadata
                meta_key = f"task:{task_id}:meta"
                pipe.hset(meta_key, mapping={
                    "current_node": checkpoint.current_node,
                    "attempts": checkpoint.attempts,
                    "cost_so_far": checkpoint.cost_so_far,
                    "updated_at": checkpoint.updated_at.isoformat(),
                })
            
            await pipe.execute()
        
        logger.info(f"Saved checkpoint for task {task_id} at node {checkpoint.current_node}")
    
    async def load_checkpoint(self, task_id: str) -> Optional[TaskCheckpoint]:
        """
        Load checkpoint from Redis.
        
        Args:
            task_id: Unique task identifier
            
        Returns:
            TaskCheckpoint if found, None otherwise
        """
        checkpoint_key = f"task:{task_id}:checkpoint"
        data = await self.redis.get(checkpoint_key)
        
        if data is None:
            logger.warning(f"No checkpoint found for task {task_id}")
            return None
        
        checkpoint = TaskCheckpoint.model_validate_json(data)
        logger.info(f"Loaded checkpoint for task {task_id} at node {checkpoint.current_node}")
        return checkpoint
    
    async def save_task_metadata(self, metadata: TaskMetadata) -> None:
        """
        Save or update task metadata.
        
        Args:
            metadata: Task metadata to save
        """
        meta_key = f"task:{metadata.task_id}:meta"
        
        # Convert to dict and handle datetime serialization
        data = metadata.model_dump()
        redis_data = {}
        for key, value in data.items():
            if isinstance(value, datetime):
                redis_data[key] = value.isoformat()
            elif value is not None:
                redis_data[key] = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
        
        await self.redis.hset(meta_key, mapping=redis_data)
        logger.debug(f"Saved metadata for task {metadata.task_id}")
    
    async def load_task_metadata(self, task_id: str) -> Optional[TaskMetadata]:
        """
        Load task metadata from Redis.
        
        Args:
            task_id: Unique task identifier
            
        Returns:
            TaskMetadata if found, None otherwise
        """
        meta_key = f"task:{task_id}:meta"
        data = await self.redis.hgetall(meta_key)
        
        if not data:
            return None
        
        # Decode bytes and parse JSON where needed
        decoded = {}
        for key, value in data.items():
            key_str = key.decode() if isinstance(key, bytes) else key
            value_str = value.decode() if isinstance(value, bytes) else value
            
            # Try to parse JSON for complex fields
            if key_str in ["task_params", "result"]:
                try:
                    decoded[key_str] = json.loads(value_str)
                except (json.JSONDecodeError, ValueError):
                    decoded[key_str] = value_str
            else:
                decoded[key_str] = value_str
        
        return TaskMetadata.model_validate(decoded)
    
    async def claim_task(
        self,
        task_id: str,
        worker_id: str,
        lease_duration: int = 300
    ) -> bool:
        """
        Atomically claim a task for execution using Lua script.
        
        Args:
            task_id: Task to claim
            worker_id: Worker claiming the task
            lease_duration: Lease duration in seconds
            
        Returns:
            True if claim successful, False otherwise
        """
        # Lua script for atomic claim
        claim_script = """
        local meta_key = KEYS[1]
        local worker_id = ARGV[1]
        local lease_expires = ARGV[2]
        
        local current_status = redis.call('HGET', meta_key, 'status')
        local current_owner = redis.call('HGET', meta_key, 'owner')
        
        -- Can claim if queued or if lease expired
        if current_status == 'queued' or (current_status == 'leased' and current_owner == worker_id) then
            redis.call('HMSET', meta_key,
                'status', 'leased',
                'owner', worker_id,
                'lease_expires', lease_expires,
                'updated_at', ARGV[3]
            )
            return 1
        end
        
        return 0
        """
        
        meta_key = f"task:{task_id}:meta"
        lease_expires = (datetime.utcnow() + timedelta(seconds=lease_duration)).isoformat()
        updated_at = datetime.utcnow().isoformat()
        
        result = await self.redis.eval(
            claim_script,
            1,
            meta_key,
            worker_id,
            lease_expires,
            updated_at
        )
        
        claimed = bool(result)
        if claimed:
            logger.info(f"Worker {worker_id} claimed task {task_id}")
        else:
            logger.warning(f"Worker {worker_id} failed to claim task {task_id}")
        
        return claimed
    
    async def release_task(
        self,
        task_id: str,
        status: TaskStatus = TaskStatus.QUEUED
    ) -> None:
        """
        Release a task back to the queue.
        
        Args:
            task_id: Task to release
            status: New status for the task
        """
        meta_key = f"task:{task_id}:meta"
        
        await self.redis.hset(meta_key, mapping={
            "status": status.value,
            "owner": "",
            "lease_expires": "",
            "updated_at": datetime.utcnow().isoformat(),
        })
        
        logger.info(f"Released task {task_id} with status {status}")
    
    async def increment_cost(
        self,
        task_id: str,
        cost_delta: float
    ) -> float:
        """
        Atomically increment task cost.
        
        Args:
            task_id: Task identifier
            cost_delta: Cost to add (in USD)
            
        Returns:
            New total cost
        """
        meta_key = f"task:{task_id}:meta"
        new_cost = await self.redis.hincrbyfloat(meta_key, "cost_so_far", cost_delta)
        
        # Also update checkpoint cost
        checkpoint = await self.load_checkpoint(task_id)
        if checkpoint:
            checkpoint.cost_so_far = new_cost
            await self.save_checkpoint(task_id, checkpoint, update_metadata=False)
        
        return new_cost
    
    async def cleanup_expired_leases(self) -> int:
        """
        Find and release expired leases.
        
        Returns:
            Number of leases cleaned up
        """
        # Scan for all task metadata keys
        cursor = 0
        cleaned = 0
        now = datetime.utcnow()
        
        while True:
            cursor, keys = await self.redis.scan(
                cursor,
                match="task:*:meta",
                count=100
            )
            
            for key in keys:
                meta_data = await self.redis.hgetall(key)
                if not meta_data:
                    continue
                
                status = meta_data.get(b"status", b"").decode()
                lease_expires_str = meta_data.get(b"lease_expires", b"").decode()
                
                if status == "leased" and lease_expires_str:
                    try:
                        lease_expires = datetime.fromisoformat(lease_expires_str)
                        if now > lease_expires:
                            task_id = key.decode().split(":")[1]
                            await self.release_task(task_id, TaskStatus.QUEUED)
                            cleaned += 1
                            logger.warning(f"Cleaned up expired lease for task {task_id}")
                    except (ValueError, IndexError):
                        pass
            
            if cursor == 0:
                break
        
        return cleaned


async def create_redis_saver(
    redis_url: str = "redis://localhost:6379",
    **kwargs
) -> RedisCheckpointSaver:
    """
    Factory function to create Redis checkpoint saver.
    
    Args:
        redis_url: Redis connection URL
        **kwargs: Additional arguments for RedisCheckpointSaver
        
    Returns:
        Configured RedisCheckpointSaver instance
    """
    redis_client = await redis.from_url(redis_url, decode_responses=False)
    return RedisCheckpointSaver(redis_client, **kwargs)
