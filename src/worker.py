"""Async worker that claims tasks, executes nodes, and checkpoints state."""

import asyncio
import logging
import os
import signal
import socket
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import redis.asyncio as redis

from .config import settings
from .redis_saver import RedisCheckpointSaver
from .state import (
    NodeState,
    NodeType,
    TaskCheckpoint,
    TaskMetadata,
    TaskStatus,
    WorkerHeartbeat,
    LLMCallMetadata,
)

logger = logging.getLogger(__name__)


class AsyncWorker:
    """
    Fault-tolerant async worker that processes tasks with checkpointing.
    
    Responsibilities:
    - Claim tasks from Redis queue
    - Execute nodes with LangGraph
    - Save checkpoints after each node
    - Renew leases periodically
    - Send heartbeats
    - Resume from checkpoints on task assignment
    """
    
    def __init__(
        self,
        worker_id: Optional[str] = None,
        redis_url: Optional[str] = None,
        heartbeat_interval: int = None,
        lease_duration: int = None,
    ):
        """
        Initialize async worker.
        
        Args:
            worker_id: Unique worker identifier
            redis_url: Redis connection URL
            heartbeat_interval: Seconds between heartbeats
            lease_duration: Task lease duration in seconds
        """
        self.worker_id = worker_id or settings.worker_id or f"worker-{os.getpid()}"
        self.redis_url = redis_url or settings.redis_url
        self.heartbeat_interval = heartbeat_interval or settings.worker_heartbeat_interval
        self.lease_duration = lease_duration or settings.lease_duration
        
        self.redis_client: Optional[redis.Redis] = None
        self.saver: Optional[RedisCheckpointSaver] = None
        self.running = False
        self.current_task_id: Optional[str] = None
        
        # Background tasks
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._lease_renewal_task: Optional[asyncio.Task] = None
        
        self.hostname = socket.gethostname()
        self.pid = os.getpid()
        self.started_at = datetime.utcnow()
        
        logger.info(f"Worker {self.worker_id} initialized on {self.hostname}")
    
    async def start(self):
        """Start the worker and background tasks."""
        logger.info(f"Starting worker {self.worker_id}...")
        
        # Connect to Redis
        self.redis_client = await redis.from_url(self.redis_url, decode_responses=False)
        self.saver = RedisCheckpointSaver(self.redis_client)
        
        self.running = True
        
        # Start background tasks
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        self._lease_renewal_task = asyncio.create_task(self._lease_renewal_loop())
        
        logger.info(f"Worker {self.worker_id} started successfully")
    
    async def stop(self):
        """Stop the worker gracefully."""
        logger.info(f"Stopping worker {self.worker_id}...")
        self.running = False
        
        # Cancel background tasks
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        if self._lease_renewal_task:
            self._lease_renewal_task.cancel()
        
        # Release current task if any
        if self.current_task_id:
            await self.saver.release_task(self.current_task_id, TaskStatus.QUEUED)
            logger.info(f"Released task {self.current_task_id}")
        
        # Cleanup Redis connection
        if self.redis_client:
            await self.redis_client.close()
        
        logger.info(f"Worker {self.worker_id} stopped")
    
    async def _heartbeat_loop(self):
        """Background task that sends periodic heartbeats."""
        try:
            while self.running:
                await self._send_heartbeat()
                await asyncio.sleep(self.heartbeat_interval)
        except asyncio.CancelledError:
            logger.debug("Heartbeat loop cancelled")
        except Exception as e:
            logger.error(f"Heartbeat loop error: {e}", exc_info=True)
    
    async def _send_heartbeat(self):
        """Send heartbeat to Redis with TTL."""
        heartbeat = WorkerHeartbeat(
            worker_id=self.worker_id,
            pid=self.pid,
            version="0.1.0",
            current_task=self.current_task_id,
            hostname=self.hostname,
            started_at=self.started_at,
        )
        
        key = f"worker:{self.worker_id}:hb"
        # Set with TTL = 3x heartbeat interval for safety
        ttl = self.heartbeat_interval * 3
        
        await self.redis_client.set(
            key,
            heartbeat.model_dump_json(),
            ex=ttl
        )
        
        logger.debug(f"Heartbeat sent: {self.worker_id}")
    
    async def _lease_renewal_loop(self):
        """Background task that renews task leases."""
        try:
            while self.running:
                await asyncio.sleep(self.lease_duration // 3)  # Renew at 1/3 interval
                
                if self.current_task_id:
                    await self._renew_lease(self.current_task_id)
        except asyncio.CancelledError:
            logger.debug("Lease renewal loop cancelled")
        except Exception as e:
            logger.error(f"Lease renewal loop error: {e}", exc_info=True)
    
    async def _renew_lease(self, task_id: str):
        """Renew lease for current task."""
        meta = await self.saver.load_task_metadata(task_id)
        if meta and meta.owner == self.worker_id:
            new_expiry = datetime.utcnow() + timedelta(seconds=self.lease_duration)
            meta.lease_expires = new_expiry
            await self.saver.save_task_metadata(meta)
            logger.debug(f"Renewed lease for task {task_id}")
    
    async def claim_next_task(self) -> Optional[str]:
        """
        Attempt to claim the next available task.
        
        Returns:
            Task ID if claimed, None otherwise
        """
        # Scan for queued tasks
        # In production, use Redis Streams XREADGROUP instead of scan
        cursor = 0
        while True:
            cursor, keys = await self.redis_client.scan(
                cursor,
                match="task:*:meta",
                count=10
            )
            
            for key in keys:
                task_id = key.decode().split(":")[1]
                
                # Attempt to claim
                claimed = await self.saver.claim_task(
                    task_id,
                    self.worker_id,
                    self.lease_duration
                )
                
                if claimed:
                    logger.info(f"Claimed task {task_id}")
                    return task_id
            
            if cursor == 0:
                break
        
        return None
    
    async def execute_task(self, task_id: str):
        """
        Execute a task from start or resume from checkpoint.
        
        Args:
            task_id: Task to execute
        """
        self.current_task_id = task_id
        
        try:
            # Load task metadata
            meta = await self.saver.load_task_metadata(task_id)
            if not meta:
                logger.error(f"Task {task_id} metadata not found")
                return
            
            # Check for existing checkpoint (resume scenario)
            checkpoint = await self.saver.load_checkpoint(task_id)
            
            if checkpoint:
                logger.info(f"Resuming task {task_id} from node {checkpoint.current_node}")
                await self._resume_from_checkpoint(task_id, checkpoint, meta)
            else:
                logger.info(f"Starting task {task_id} from beginning")
                await self._execute_from_start(task_id, meta)
            
            # Mark task complete
            meta.status = TaskStatus.COMPLETED
            meta.completed_at = datetime.utcnow()
            meta.result = {"status": "success", "message": "Task completed"}
            await self.saver.save_task_metadata(meta)
            
            logger.info(f"Task {task_id} completed successfully")
        
        except Exception as e:
            logger.error(f"Task {task_id} failed: {e}", exc_info=True)
            
            # Update metadata with error
            meta = await self.saver.load_task_metadata(task_id)
            if meta:
                meta.status = TaskStatus.FAILED
                meta.error = str(e)
                meta.attempts += 1
                await self.saver.save_task_metadata(meta)
        
        finally:
            self.current_task_id = None
    
    async def _execute_from_start(self, task_id: str, meta: TaskMetadata):
        """Execute task from the beginning."""
        # Initialize checkpoint
        checkpoint = TaskCheckpoint(
            task_id=task_id,
            current_node="start",
            node_history=["start"],
            attempts=meta.attempts + 1,
        )
        
        await self.saver.save_checkpoint(task_id, checkpoint)
        
        # Execute node sequence
        await self._execute_node_sequence(task_id, checkpoint, meta)
    
    async def _resume_from_checkpoint(
        self,
        task_id: str,
        checkpoint: TaskCheckpoint,
        meta: TaskMetadata
    ):
        """Resume task execution from checkpoint."""
        logger.info(
            f"Resuming from node {checkpoint.current_node}, "
            f"history: {checkpoint.node_history}, "
            f"cost so far: ${checkpoint.cost_so_far:.2f}"
        )
        
        # Increment attempt counter
        checkpoint.attempts += 1
        await self.saver.save_checkpoint(task_id, checkpoint)
        
        # Continue execution from checkpoint
        await self._execute_node_sequence(task_id, checkpoint, meta)
    
    async def _execute_node_sequence(
        self,
        task_id: str,
        checkpoint: TaskCheckpoint,
        meta: TaskMetadata
    ):
        """
        Execute the sequence of nodes with checkpointing.
        
        This is a simplified demo sequence. In production, this would be
        driven by LangGraph's state machine.
        """
        # Define simple node sequence (demo)
        node_sequence = [
            ("search", NodeType.SEARCH),
            ("analyze", NodeType.ANALYZE),
            ("summarize", NodeType.SUMMARIZE),
            ("complete", NodeType.COMPLETE),
        ]
        
        # Find where to resume
        last_node = checkpoint.current_node
        start_idx = 0
        
        if last_node != "start":
            for i, (node_id, _) in enumerate(node_sequence):
                if node_id == last_node:
                    start_idx = i + 1
                    break
        
        # Execute remaining nodes
        for node_id, node_type in node_sequence[start_idx:]:
            logger.info(f"Executing node: {node_id}")
            
            # Execute node (integrate with LangGraph here)
            node_state = await self._execute_node(
                node_id,
                node_type,
                checkpoint,
                meta
            )
            
            # Update checkpoint
            checkpoint.current_node = node_id
            checkpoint.node_history.append(node_id)
            checkpoint.node_states[node_id] = node_state
            checkpoint.updated_at = datetime.utcnow()
            
            # Save checkpoint after each node
            await self.saver.save_checkpoint(task_id, checkpoint)
            
            logger.info(f"Node {node_id} completed, checkpoint saved")
    
    async def _execute_node(
        self,
        node_id: str,
        node_type: NodeType,
        checkpoint: TaskCheckpoint,
        meta: TaskMetadata
    ) -> NodeState:
        """
        Execute a single node.
        
        Args:
            node_id: Node identifier
            node_type: Type of node
            checkpoint: Current checkpoint state
            meta: Task metadata
            
        Returns:
            NodeState with results
        """
        started_at = datetime.utcnow()
        
        # Get inputs from previous node
        prev_outputs = {}
        if checkpoint.node_history:
            prev_node = checkpoint.node_history[-1]
            if prev_node in checkpoint.node_states:
                prev_outputs = checkpoint.node_states[prev_node].outputs
        
        # Simulate node execution
        # In production, this would call LangGraph node execution
        logger.info(f"Node {node_id} executing with inputs: {prev_outputs}")
        
        # Call LLM for nodes that need it
        outputs = {}
        
        if node_type in [NodeType.SEARCH, NodeType.ANALYZE, NodeType.SUMMARIZE]:
            # Enforce rate limit before LLM call
            rate_limit_key = f"tenant:{meta.tenant_id}"
            tokens_needed = 1.0  # 1 token per LLM call
            
            allowed, remaining, retry_after_ms = await self.rate_limiter.consume(
                rate_limit_key,
                tokens=tokens_needed,
            )
            
            if not allowed:
                logger.warning(
                    f"Rate limit exceeded for tenant {meta.tenant_id}: "
                    f"retry after {retry_after_ms}ms"
                )
                # Sleep and retry
                await asyncio.sleep(retry_after_ms / 1000.0)
                # Try again
                allowed, remaining, retry_after_ms = await self.rate_limiter.consume(
                    rate_limit_key,
                    tokens=tokens_needed,
                )
                if not allowed:
                    raise RuntimeError(
                        f"Rate limit still exceeded after retry for tenant {meta.tenant_id}"
                    )
            
            logger.info(
                f"Rate limit check passed: tenant={meta.tenant_id}, "
                f"remaining={remaining:.2f} tokens"
            )
            
            try:
                # Real LLM call
                outputs, llm_metadata = await self._call_llm(
                    node_id,
                    node_type,
                    {"prev_outputs": prev_outputs, "query": meta.task_params.get("query", "")},
                    meta
                )
                
                # Track cost
                cost = llm_metadata.cost_usd
                new_total = await self.saver.increment_cost(checkpoint.task_id, cost)
                checkpoint.cost_so_far = new_total
                checkpoint.llm_calls.append(llm_metadata)
                
                logger.info(f"LLM call cost: ${cost:.4f}, total: ${new_total:.2f}")
            
            except Exception as e:
                logger.warning(f"LLM call failed for {node_id}, using fallback: {e}")
                # Fallback to simple output if LLM fails
                outputs = {
                    "result": f"Fallback output from {node_id}",
                    "error": str(e),
                }
        else:
            # Non-LLM nodes
            await asyncio.sleep(0.3)
            outputs = {
                "result": f"Output from {node_id}",
                "data": [1, 2, 3],
            }
        
        completed_at = datetime.utcnow()
        
        # Create node state
        node_state = NodeState(
            node_id=node_id,
            node_type=node_type,
            inputs={"prev_outputs": prev_outputs},
            outputs=outputs,
            metadata={"execution_time_ms": (completed_at - started_at).total_seconds() * 1000},
            started_at=started_at,
            completed_at=completed_at,
        )
        
        return node_state
    
    async def _call_llm(
        self,
        node_id: str,
        node_type: NodeType,
        inputs: Dict[str, Any],
        meta: TaskMetadata
    ) -> tuple[Dict[str, Any], LLMCallMetadata]:
        """
        Call LLM with real API integration.
        
        Constructs appropriate prompts based on node type and calls OpenAI.
        """
        from .llm import get_llm_client
        
        llm_client = get_llm_client()
        
        # Construct prompt based on node type
        if node_type == NodeType.SEARCH:
            prompt = f"Search and extract information about: {inputs.get('query', 'data')}"
            system = "You are a research assistant that finds and extracts relevant information."
        
        elif node_type == NodeType.ANALYZE:
            data = inputs.get('prev_outputs', inputs.get('data', {}))
            prompt = f"Analyze the following data and provide insights:\n\n{data}"
            system = "You are an analytical assistant that identifies patterns and insights."
        
        elif node_type == NodeType.SUMMARIZE:
            data = inputs.get('prev_outputs', inputs.get('data', {}))
            prompt = f"Summarize the following analysis:\n\n{data}"
            system = "You are a summarization assistant that creates concise summaries."
        
        else:
            # Generic prompt
            prompt = f"Process this task: {inputs}"
            system = "You are a helpful assistant."
        
        # Call LLM
        response, metadata = await llm_client.simple_prompt(
            prompt=prompt,
            system=system,
            model=settings.default_llm_model,
            temperature=0.7,
            max_tokens=500,
        )
        
        # Structure output
        outputs = {
            "llm_response": response,
            "processed": True,
        }
        
        return outputs, metadata
    
    async def run(self):
        """Main worker loop that claims and processes tasks."""
        await self.start()
        
        try:
            logger.info(f"Worker {self.worker_id} entering main loop")
            
            while self.running:
                # Try to claim a task
                task_id = await self.claim_next_task()
                
                if task_id:
                    # Execute the task
                    await self.execute_task(task_id)
                else:
                    # No tasks available, wait before retrying
                    logger.debug("No tasks available, waiting...")
                    await asyncio.sleep(5)
        
        except asyncio.CancelledError:
            logger.info("Worker main loop cancelled")
        except Exception as e:
            logger.error(f"Worker main loop error: {e}", exc_info=True)
        finally:
            await self.stop()


async def create_worker(**kwargs) -> AsyncWorker:
    """
    Factory function to create and initialize a worker.
    
    Args:
        **kwargs: Arguments passed to AsyncWorker constructor
        
    Returns:
        Initialized AsyncWorker instance
    """
    worker = AsyncWorker(**kwargs)
    return worker


def main():
    """Run worker as a standalone process."""
    import sys
    
    # Setup logging
    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create worker
    worker = AsyncWorker()
    
    # Handle shutdown signals
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}, shutting down...")
        worker.running = False
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Run worker
        loop.run_until_complete(worker.run())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        loop.close()
        sys.exit(0)


if __name__ == "__main__":
    main()
