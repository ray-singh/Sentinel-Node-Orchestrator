"""Demo of watcher service detecting worker failures and requeuing tasks."""

import asyncio
import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import settings
from src.redis_saver import create_redis_saver
from src.state import TaskMetadata, TaskStatus
from src.worker import AsyncWorker
from src.watcher import WatcherService


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def setup_test_task():
    """Create a test task."""
    logger.info("Setting up test task...")
    
    saver = await create_redis_saver(settings.redis_url)
    
    task_id = "watcher_demo_task"
    meta = TaskMetadata(
        task_id=task_id,
        status=TaskStatus.QUEUED,
        tenant_id="demo_tenant",
        task_type="long_running_task",
        task_params={"data": "test"},
        cost_limit=5.0,
        max_attempts=3,
    )
    await saver.save_task_metadata(meta)
    logger.info(f"Created task: {task_id}")
    
    await saver.redis.close()
    return task_id


async def simulate_worker_crash_scenario():
    """
    Simulate a scenario where:
    1. Worker claims a task and starts working
    2. Worker crashes without releasing the task
    3. Watcher detects the dead worker and requeues the task
    4. Another worker picks up the task
    """
    logger.info("=" * 70)
    logger.info("Watcher Demo: Worker Crash Detection & Task Requeue")
    logger.info("=" * 70)
    
    # Create task
    task_id = await setup_test_task()
    
    # Start watcher in background
    logger.info("\n🔍 Starting watcher service...")
    watcher = WatcherService(
        scan_interval=3,  # Fast scan for demo
        heartbeat_timeout=10,
    )
    watcher_task = asyncio.create_task(watcher.run())
    
    # Wait for watcher to start
    await asyncio.sleep(1)
    
    # Start worker 1
    logger.info("\n👷 Worker-1 starting and claiming task...")
    worker1 = AsyncWorker(
        worker_id="demo-worker-1",
        heartbeat_interval=2,  # Frequent heartbeats for demo
        lease_duration=10,  # Short lease for demo
    )
    await worker1.start()
    
    # Worker 1 claims the task
    claimed = await worker1.saver.claim_task(task_id, worker1.worker_id, 10)
    if claimed:
        logger.info(f"✅ Worker-1 claimed task {task_id}")
        
        # Check initial stats
        stats = await watcher.get_stats()
        logger.info(f"📊 Watcher stats: {stats}")
        
        # Send a few heartbeats
        logger.info("\n💓 Worker-1 sending heartbeats...")
        for i in range(3):
            await worker1._send_heartbeat()
            await asyncio.sleep(2)
            logger.info(f"   Heartbeat {i+1} sent")
        
        # Show active workers
        active = await watcher.get_active_workers()
        logger.info(f"\n🟢 Active workers detected by watcher: {len(active)}")
        for w in active:
            logger.info(f"   - {w['worker_id']} on {w['hostname']} (PID: {w['pid']})")
        
        # Simulate crash - stop worker WITHOUT releasing task or sending final heartbeat
        logger.info("\n💥 SIMULATING WORKER CRASH (no graceful shutdown)...")
        worker1.running = False
        if worker1._heartbeat_task:
            worker1._heartbeat_task.cancel()
        if worker1._lease_renewal_task:
            worker1._lease_renewal_task.cancel()
        
        # Don't release task or close connection - simulate hard crash
        # await worker1.saver.release_task(task_id, TaskStatus.QUEUED)  # NOT CALLED
        logger.info("   Worker-1 crashed without releasing task!")
        
        # Wait for heartbeat to expire
        logger.info(f"\n⏳ Waiting for heartbeat to expire (timeout: {watcher.heartbeat_timeout}s)...")
        await asyncio.sleep(12)  # Wait slightly longer than timeout
        
        # Check if watcher detected the failure
        logger.info("\n🔍 Watcher scanning for dead workers...")
        await asyncio.sleep(5)  # Give watcher time to scan
        
        # Check task status
        saver = await create_redis_saver(settings.redis_url)
        meta = await saver.load_task_metadata(task_id)
        
        if meta.status == TaskStatus.QUEUED:
            logger.info(f"✅ WATCHER SUCCESSFULLY REQUEUED TASK!")
            logger.info(f"   Task status: {meta.status}")
            logger.info(f"   Task owner: {meta.owner}")
            logger.info(f"   Attempts: {meta.attempts}")
        else:
            logger.warning(f"⚠️  Task status: {meta.status}, owner: {meta.owner}")
        
        # Start worker 2 to pick up the task
        logger.info("\n👷 Worker-2 starting to claim requeued task...")
        worker2 = AsyncWorker(
            worker_id="demo-worker-2",
            heartbeat_interval=2,
            lease_duration=30,
        )
        await worker2.start()
        
        claimed2 = await worker2.saver.claim_task(task_id, worker2.worker_id, 30)
        if claimed2:
            logger.info(f"✅ Worker-2 successfully claimed task {task_id}")
            logger.info("   Task can now be resumed from checkpoint!")
            
            # Load checkpoint to show resume capability
            checkpoint = await worker2.saver.load_checkpoint(task_id)
            if checkpoint:
                logger.info(f"   Checkpoint found: {checkpoint.node_history}")
        else:
            logger.error("❌ Worker-2 failed to claim task")
        
        # Show final stats
        stats = await watcher.get_stats()
        logger.info(f"\n📊 Final watcher stats:")
        logger.info(f"   Active workers: {stats['active_workers']}")
        logger.info(f"   Dead workers detected: {stats['dead_workers']}")
        logger.info(f"   Total scans: {stats['scan_count']}")
        logger.info(f"   Tasks requeued: {stats['requeue_count']}")
        
        # Cleanup
        await worker2.stop()
        await saver.redis.close()
    
    # Stop watcher
    watcher.running = False
    await watcher_task
    
    logger.info("\n" + "=" * 70)
    logger.info("🎉 Demo completed successfully!")
    logger.info("=" * 70)


async def run_continuous_monitoring():
    """Run watcher in continuous monitoring mode."""
    logger.info("=" * 70)
    logger.info("Watcher Service - Continuous Monitoring Mode")
    logger.info("=" * 70)
    logger.info("\nPress Ctrl+C to stop\n")
    
    watcher = WatcherService(
        scan_interval=5,
        heartbeat_timeout=15,
    )
    
    try:
        await watcher.run()
    except KeyboardInterrupt:
        logger.info("\nStopping watcher...")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "monitor":
        # Run continuous monitoring
        asyncio.run(run_continuous_monitoring())
    else:
        # Run crash scenario demo
        asyncio.run(simulate_worker_crash_scenario())
