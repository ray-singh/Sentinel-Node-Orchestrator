"""Watcher service that monitors worker heartbeats and requeues failed tasks."""

import asyncio
import logging
import os
import signal
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set

import redis.asyncio as redis

from .config import settings
from .redis_saver import RedisCheckpointSaver
from .state import TaskMetadata, TaskStatus, WorkerHeartbeat

logger = logging.getLogger(__name__)


class WatcherService:
    """
    Monitors worker health and task leases, requeuing tasks from failed workers.
    
    Responsibilities:
    - Detect expired worker heartbeats
    - Identify tasks with expired leases
    - Requeue tasks from dead workers
    - Track worker lifecycle events
    - Emit metrics and alerts
    """
    
    def __init__(
        self,
        redis_url: Optional[str] = None,
        scan_interval: int = 10,
        heartbeat_timeout: int = 30,
        lease_grace_period: int = 5,
    ):
        """
        Initialize watcher service.
        
        Args:
            redis_url: Redis connection URL
            scan_interval: Seconds between scans
            heartbeat_timeout: Seconds before heartbeat is considered expired
            lease_grace_period: Additional seconds before reclaiming lease
        """
        self.redis_url = redis_url or settings.redis_url
        self.scan_interval = scan_interval
        self.heartbeat_timeout = heartbeat_timeout
        self.lease_grace_period = lease_grace_period
        
        self.redis_client: Optional[redis.Redis] = None
        self.saver: Optional[RedisCheckpointSaver] = None
        self.running = False
        
        # Tracking
        self.known_workers: Set[str] = set()
        self.dead_workers: Set[str] = set()
        self.requeue_count = 0
        self.scan_count = 0
        
        logger.info("Watcher service initialized")
    
    async def start(self):
        """Start the watcher service."""
        logger.info("Starting watcher service...")
        
        # Connect to Redis
        self.redis_client = await redis.from_url(self.redis_url, decode_responses=False)
        self.saver = RedisCheckpointSaver(self.redis_client)
        
        self.running = True
        logger.info("Watcher service started")
    
    async def stop(self):
        """Stop the watcher service."""
        logger.info("Stopping watcher service...")
        self.running = False
        
        if self.redis_client:
            await self.redis_client.close()
        
        logger.info(f"Watcher stopped. Stats: {self.scan_count} scans, {self.requeue_count} tasks requeued")
    
    async def run(self):
        """Main watcher loop."""
        await self.start()
        
        try:
            logger.info(f"Watcher entering main loop (scan interval: {self.scan_interval}s)")
            
            while self.running:
                try:
                    await self._scan_and_recover()
                    self.scan_count += 1
                    await asyncio.sleep(self.scan_interval)
                except Exception as e:
                    logger.error(f"Error in watcher scan: {e}", exc_info=True)
                    await asyncio.sleep(self.scan_interval)
        
        except asyncio.CancelledError:
            logger.info("Watcher main loop cancelled")
        finally:
            await self.stop()
    
    async def _scan_and_recover(self):
        """Scan for dead workers and expired leases, then recover tasks."""
        logger.debug("Starting watcher scan...")
        
        # 1. Check worker heartbeats
        dead_workers = await self._detect_dead_workers()
        
        if dead_workers:
            logger.warning(f"Detected {len(dead_workers)} dead workers: {dead_workers}")
            
            # 2. Requeue tasks from dead workers
            for worker_id in dead_workers:
                requeued = await self._requeue_worker_tasks(worker_id)
                self.requeue_count += requeued
                
                if requeued > 0:
                    logger.warning(f"Requeued {requeued} tasks from dead worker {worker_id}")
        
        # 3. Clean up expired leases (catches any edge cases)
        expired = await self.saver.cleanup_expired_leases()
        if expired > 0:
            logger.warning(f"Cleaned up {expired} expired leases")
            self.requeue_count += expired
        
        # 4. Update active worker list
        await self._update_worker_list()
        
        logger.debug(f"Scan complete. Active workers: {len(self.known_workers)}, Total requeued: {self.requeue_count}")
    
    async def _detect_dead_workers(self) -> List[str]:
        """
        Detect workers with expired heartbeats.
        
        Returns:
            List of dead worker IDs
        """
        dead_workers = []
        
        # Scan for all worker heartbeat keys
        cursor = 0
        while True:
            cursor, keys = await self.redis_client.scan(
                cursor,
                match="worker:*:hb",
                count=100
            )
            
            for key in keys:
                worker_id = key.decode().split(":")[1]
                
                # Check if key exists (TTL-based detection)
                exists = await self.redis_client.exists(key)
                
                if not exists:
                    # Heartbeat expired
                    if worker_id in self.known_workers:
                        dead_workers.append(worker_id)
                        self.dead_workers.add(worker_id)
                        logger.warning(f"Worker {worker_id} heartbeat expired")
            
            if cursor == 0:
                break
        
        return dead_workers
    
    async def _requeue_worker_tasks(self, worker_id: str) -> int:
        """
        Requeue all tasks owned by a dead worker.
        
        Args:
            worker_id: Dead worker identifier
            
        Returns:
            Number of tasks requeued
        """
        requeued = 0
        
        # Scan for all task metadata
        cursor = 0
        while True:
            cursor, keys = await self.redis_client.scan(
                cursor,
                match="task:*:meta",
                count=100
            )
            
            for key in keys:
                task_id = key.decode().split(":")[1]
                
                # Load metadata
                meta = await self.saver.load_task_metadata(task_id)
                
                if meta and meta.owner == worker_id:
                    if meta.status in [TaskStatus.LEASED, TaskStatus.IN_PROGRESS]:
                        # Requeue the task
                        await self._requeue_task(task_id, meta, worker_id)
                        requeued += 1
            
            if cursor == 0:
                break
        
        return requeued
    
    async def _requeue_task(
        self,
        task_id: str,
        meta: TaskMetadata,
        dead_worker_id: str
    ):
        """
        Requeue a single task and emit event.
        
        Args:
            task_id: Task to requeue
            meta: Task metadata
            dead_worker_id: ID of the dead worker
        """
        logger.info(f"Requeuing task {task_id} from dead worker {dead_worker_id}")
        
        # Update status
        old_status = meta.status
        meta.status = TaskStatus.QUEUED
        meta.owner = None
        meta.lease_expires = None
        meta.updated_at = datetime.utcnow()
        
        # Increment attempts
        meta.attempts += 1
        
        # Check max attempts
        if meta.attempts >= meta.max_attempts:
            logger.error(f"Task {task_id} exceeded max attempts ({meta.max_attempts}), marking as failed")
            meta.status = TaskStatus.FAILED
            meta.error = f"Exceeded max retry attempts after worker {dead_worker_id} failure"
        
        await self.saver.save_task_metadata(meta)
        
        # Emit event to stream (if stream exists)
        await self._emit_event({
            "event": "task_requeued",
            "task_id": task_id,
            "dead_worker": dead_worker_id,
            "old_status": old_status.value,
            "new_status": meta.status.value,
            "attempts": meta.attempts,
            "timestamp": datetime.utcnow().isoformat(),
        })
        
        logger.info(f"Task {task_id} requeued (attempt {meta.attempts}/{meta.max_attempts})")
    
    async def _update_worker_list(self):
        """Update the set of known active workers."""
        current_workers = set()
        
        # Scan for all worker heartbeat keys
        cursor = 0
        while True:
            cursor, keys = await self.redis_client.scan(
                cursor,
                match="worker:*:hb",
                count=100
            )
            
            for key in keys:
                worker_id = key.decode().split(":")[1]
                current_workers.add(worker_id)
            
            if cursor == 0:
                break
        
        # Detect new workers
        new_workers = current_workers - self.known_workers
        if new_workers:
            logger.info(f"New workers detected: {new_workers}")
        
        # Detect departed workers (beyond those already flagged as dead)
        departed = self.known_workers - current_workers - self.dead_workers
        if departed:
            logger.info(f"Workers gracefully stopped: {departed}")
        
        self.known_workers = current_workers
    
    async def _emit_event(self, event: Dict):
        """
        Emit an event to Redis stream.
        
        Args:
            event: Event data dictionary
        """
        try:
            # Check if stream exists or create it
            stream_key = "stream:events"
            
            # XADD to stream
            await self.redis_client.xadd(
                stream_key,
                event,
                maxlen=10000  # Keep last 10K events
            )
            
            logger.debug(f"Emitted event: {event.get('event')}")
        except Exception as e:
            logger.error(f"Failed to emit event: {e}")
    
    async def get_stats(self) -> Dict:
        """
        Get watcher statistics.
        
        Returns:
            Dictionary of stats
        """
        return {
            "active_workers": len(self.known_workers),
            "dead_workers": len(self.dead_workers),
            "scan_count": self.scan_count,
            "requeue_count": self.requeue_count,
            "running": self.running,
        }
    
    async def get_active_workers(self) -> List[Dict]:
        """
        Get list of active workers with their details.
        
        Returns:
            List of worker info dictionaries
        """
        workers = []
        
        for worker_id in self.known_workers:
            key = f"worker:{worker_id}:hb"
            data = await self.redis_client.get(key)
            
            if data:
                try:
                    heartbeat = WorkerHeartbeat.model_validate_json(data)
                    workers.append({
                        "worker_id": heartbeat.worker_id,
                        "hostname": heartbeat.hostname,
                        "pid": heartbeat.pid,
                        "current_task": heartbeat.current_task,
                        "last_beat": heartbeat.last_beat.isoformat(),
                        "uptime_seconds": (datetime.utcnow() - heartbeat.started_at).total_seconds(),
                    })
                except Exception as e:
                    logger.error(f"Failed to parse heartbeat for {worker_id}: {e}")
        
        return workers


async def create_watcher(**kwargs) -> WatcherService:
    """
    Factory function to create a watcher service.
    
    Args:
        **kwargs: Arguments passed to WatcherService constructor
        
    Returns:
        WatcherService instance
    """
    return WatcherService(**kwargs)


def main():
    """Run watcher as a standalone service."""
    import sys
    
    # Setup logging
    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create watcher
    watcher = WatcherService(
        scan_interval=int(os.getenv("WATCHER_SCAN_INTERVAL", "10")),
        heartbeat_timeout=int(os.getenv("WATCHER_HEARTBEAT_TIMEOUT", "30")),
    )
    
    # Handle shutdown signals
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}, shutting down...")
        watcher.running = False
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Run watcher
        loop.run_until_complete(watcher.run())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        loop.close()
        sys.exit(0)


if __name__ == "__main__":
    main()
