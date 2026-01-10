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
from .rate_limiter import TokenBucketRateLimiter
from .agent import Agent, create_agent
from .state import (
    NodeState,
    NodeType,
    TaskCheckpoint,
    TaskMetadata,
    TaskStatus,
    WorkerHeartbeat,
    LLMCallMetadata,
)
from .effects import SideEffectManager
from .retry import retry_async
from .events import emit_event
from .tracing import add_span_attributes, add_span_event, trace_async

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
        agent: Optional[Agent] = None,
        agent_type: str = "prompt-based",
    ):
        """
        Initialize async worker.
        
        Args:
            worker_id: Unique worker identifier
            redis_url: Redis connection URL
            heartbeat_interval: Seconds between heartbeats
            lease_duration: Task lease duration in seconds
            agent: Agent instance (or will create based on agent_type)
            agent_type: Type of agent to create if agent not provided
        """
        self.worker_id = worker_id or settings.worker_id or f"worker-{os.getpid()}"
        self.redis_url = redis_url or settings.redis_url
        self.heartbeat_interval = heartbeat_interval or settings.worker_heartbeat_interval
        self.lease_duration = lease_duration or settings.lease_duration
        
        # Agent for task execution
        self.agent = agent or create_agent(agent_type)
        
        self.redis_client: Optional[redis.Redis] = None
        self.saver: Optional[RedisCheckpointSaver] = None
        self.rate_limiter: Optional[TokenBucketRateLimiter] = None
        self.running = False
        self.current_task_id: Optional[str] = None
        
        # Background tasks
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._lease_renewal_task: Optional[asyncio.Task] = None
        
        self.hostname = socket.gethostname()
        self.pid = os.getpid()
        self.started_at = datetime.utcnow()
        
        logger.info(
            f"Worker {self.worker_id} initialized on {self.hostname} "
            f"with agent type: {self.agent.agent_type}"
        )
    
    async def start(self):
        """Start the worker and background tasks."""
        logger.info(f"Starting worker {self.worker_id}...")
        
        # Connect to Redis
        self.redis_client = await redis.from_url(self.redis_url, decode_responses=False)
        self.saver = RedisCheckpointSaver(self.redis_client)
        
        # Initialize rate limiter with decode_responses=True client
        redis_decoded = await redis.from_url(self.redis_url, decode_responses=True)
        self.rate_limiter = TokenBucketRateLimiter(
            redis=redis_decoded,
            capacity=settings.default_rate_limit,
            refill_rate=settings.rate_limit_refill_rate,
        )
        
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
            # Add tracing attributes
            try:
                add_span_attributes(
                    task_id=task_id,
                    worker_id=self.worker_id
                )
            except Exception:
                pass
            
            try:
                from .metrics import TASKS_STARTED, TASKS_COMPLETED, TASKS_FAILED
            except Exception:
                TASKS_STARTED = TASKS_COMPLETED = TASKS_FAILED = None
            if TASKS_STARTED:
                # Load metadata first to get labels
                meta_temp = await self.saver.load_task_metadata(task_id)
                if meta_temp:
                    TASKS_STARTED.labels(
                        tenant_id=meta_temp.tenant_id,
                        agent_type=meta_temp.agent_type,
                        task_type=meta_temp.task_type
                    ).inc()
            # Load task metadata
            meta = await self.saver.load_task_metadata(task_id)
            if not meta:
                logger.error(f"Task {task_id} metadata not found")
                return
            
            # Add more tracing attributes
            try:
                add_span_attributes(
                    tenant_id=meta.tenant_id,
                    agent_type=meta.agent_type,
                    task_type=meta.task_type
                )
            except Exception:
                pass
            
            # Instantiate agent for this task based on metadata
            # Save old agent to restore later
            old_agent = self.agent
            try:
                self.agent = create_agent(meta.agent_type)
                await self.agent.initialize(meta)
            
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
            try:
                if TASKS_COMPLETED:
                    TASKS_COMPLETED.labels(
                        tenant_id=meta.tenant_id,
                        agent_type=meta.agent_type,
                        task_type=meta.task_type
                    ).inc()
                add_span_event("task_completed", {"task_id": task_id})
            except Exception:
                pass
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
                try:
                    if TASKS_FAILED:
                        TASKS_FAILED.labels(
                            tenant_id=meta.tenant_id,
                            agent_type=meta.agent_type,
                            task_type=meta.task_type
                        ).inc()
                    add_span_event("task_failed", {"task_id": task_id, "error": str(e)})
                except Exception:
                    pass
        
        finally:
            # Cleanup agent resources created for this task
            try:
                if self.agent:
                    await self.agent.cleanup()
            except Exception:
                logger.exception("Error cleaning up agent")
            # Restore previous agent (if any)
            self.agent = old_agent
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
        Execute a single node using the agent abstraction.
        
        Args:
            node_id: Node identifier
            node_type: Type of node
            checkpoint: Current checkpoint state
            meta: Task metadata
            
        Returns:
            NodeState with results
        """
        # Get inputs from previous node
        prev_outputs = {}
        if checkpoint.node_history:
            prev_node = checkpoint.node_history[-1]
            if prev_node in checkpoint.node_states:
                prev_outputs = checkpoint.node_states[prev_node].outputs
        
        inputs = {
            "prev_outputs": prev_outputs,
            "query": meta.task_params.get("query", ""),
        }
        task_id = checkpoint.task_id
        started_at = datetime.utcnow()
        
        logger.info(f"Node {node_id} executing with inputs: {prev_outputs}")
        
        # For LLM nodes, enforce rate limit before execution
        if node_type in [NodeType.SEARCH, NodeType.ANALYZE, NodeType.SUMMARIZE]:
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
        
        # Create SideEffectManager for idempotent external effects
        effects_mgr = SideEffectManager(self.redis_client)

        # Add tracing for node execution
        try:
            add_span_attributes(
                node_id=node_id,
                node_type=node_type.value,
                task_id=task_id,
                tenant_id=meta.tenant_id
            )
        except Exception:
            pass

        # Determine retry policy from task params or defaults
        retry_cfg = meta.task_params.get("retry_policy", {}) if isinstance(meta.task_params, dict) else {}
        retries = int(retry_cfg.get("retries", 3))
        backoff = float(retry_cfg.get("backoff", 0.5))
        factor = float(retry_cfg.get("factor", 2.0))
        max_delay = float(retry_cfg.get("max_delay", 30.0))
        jitter = float(retry_cfg.get("jitter", 0.1))

        async def _call_agent():
            return await self.agent.execute_node(
                node_id=node_id,
                node_type=node_type,
                inputs=inputs,
                metadata=meta,
                effects=effects_mgr,
            )

        # Execute with retries/backoff
        try:
            node_state, llm_metadata = await retry_async(
                _call_agent,
                retries=retries,
                backoff=backoff,
                factor=factor,
                max_delay=max_delay,
                jitter=jitter,
            )
            
            # Emit node completion event
            await emit_event(self.redis_client, "node_completed", {
                "task_id": task_id,
                "node_id": node_id,
                "node_type": node_type.value,
                "worker_id": self.worker_id,
            })
            
            # Track node metrics
            try:
                from .metrics import NODE_EXECUTIONS, NODE_DURATION
                NODE_EXECUTIONS.labels(node_type=node_type.value, status="success").inc()
                duration_s = (datetime.utcnow() - started_at).total_seconds()
                NODE_DURATION.labels(node_type=node_type.value).observe(duration_s)
                add_span_event("node_completed", {"node_id": node_id, "duration_s": duration_s})
            except Exception:
                pass

        except Exception as e:
            # Emit failure event and record error in node state
            await emit_event(self.redis_client, "node_failed", {
                "task_id": task_id,
                "node_id": node_id,
                "node_type": node_type.value,
                "worker_id": self.worker_id,
                "error": str(e),
            })
            
            # Track node error metrics
            try:
                from .metrics import NODE_EXECUTIONS
                NODE_EXECUTIONS.labels(node_type=node_type.value, status="error").inc()
                add_span_event("node_failed", {"node_id": node_id, "error": str(e)})
            except Exception:
                pass
            
            # Create error node state
            completed_at = datetime.utcnow()
            node_state = NodeState(
                node_id=node_id,
                node_type=node_type,
                inputs=inputs,
                outputs={"error": str(e), "processed": False},
                metadata={"execution_time_ms": (completed_at - started_at).total_seconds() * 1000},
                started_at=started_at,
                completed_at=completed_at,
                error=str(e),
            )
            llm_metadata = None
        
        # Track LLM cost and persist any LLM call metadata returned by agent
        # Collect all LLM call entries: those returned directly and any attached to node_state.metadata
        llm_calls_list = []
        if llm_metadata:
            llm_calls_list.append(llm_metadata)

        # Node state may contain a list of llm call dicts under metadata['llm_calls'] (LangGraph)
        meta_calls = node_state.metadata.get("llm_calls") if isinstance(node_state.metadata, dict) else None
        if meta_calls and isinstance(meta_calls, list):
            for entry in meta_calls:
                if isinstance(entry, LLMCallMetadata):
                    llm_calls_list.append(entry)
                elif isinstance(entry, dict):
                    try:
                        llm_calls_list.append(LLMCallMetadata.model_validate(entry))
                    except Exception:
                        try:
                            # Fallback construction
                            llm_calls_list.append(LLMCallMetadata(
                                model=entry.get("model", self.agent.llm_client.default_model if hasattr(self.agent, 'llm_client') else ""),
                                prompt_tokens=int(entry.get("prompt_tokens", 0) or 0),
                                completion_tokens=int(entry.get("completion_tokens", 0) or 0),
                                total_tokens=int(entry.get("total_tokens", 0) or 0),
                                cost_usd=float(entry.get("cost_usd", 0.0) or 0.0),
                                latency_ms=float(entry.get("latency_ms", 0.0) or 0.0),
                            ))
                        except Exception:
                            # Skip malformed entries
                            continue

        # If we have any llm calls, increment cost once and append all to checkpoint
        if llm_calls_list:
            total_cost = 0.0
            for call in llm_calls_list:
                try:
                    total_cost += float(call.cost_usd or 0.0)
                except Exception:
                    pass

            if total_cost > 0:
                new_total = await self.saver.increment_cost(checkpoint.task_id, total_cost)
                checkpoint.cost_so_far = new_total
            else:
                new_total = checkpoint.cost_so_far

            # Append validated metadata objects
            for call in llm_calls_list:
                checkpoint.llm_calls.append(call)

            logger.info(f"LLM calls cost: ${total_cost:.4f}, total: ${new_total:.2f}")
        
        return node_state
    
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
