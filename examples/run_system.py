"""Run the complete system: API + Workers + Watcher."""

import asyncio
import logging
import signal
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.worker import AsyncWorker
from src.watcher import WatcherService

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def run_system():
    """
    Run the complete orchestration system with:
    - 2 workers
    - 1 watcher
    
    Note: Start the API server separately with: python3 src/api.py
    """
    logger.info("=" * 70)
    logger.info("Sentinel Node Orchestrator - System Startup")
    logger.info("=" * 70)
    logger.info("\nStarting components:")
    logger.info("  - Worker 1")
    logger.info("  - Worker 2")
    logger.info("  - Watcher Service")
    logger.info("\nAPI: Start separately with 'python3 src/api.py'")
    logger.info("\nPress Ctrl+C to stop all components\n")
    
    # Create components
    worker1 = AsyncWorker(worker_id="worker-1", heartbeat_interval=10, lease_duration=60)
    worker2 = AsyncWorker(worker_id="worker-2", heartbeat_interval=10, lease_duration=60)
    watcher = WatcherService(scan_interval=15, heartbeat_timeout=30)
    
    # Track running state
    running = True
    
    def signal_handler(sig, frame):
        nonlocal running
        logger.info(f"\n\nReceived signal {sig}, initiating graceful shutdown...")
        running = False
        worker1.running = False
        worker2.running = False
        watcher.running = False
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Run all components concurrently
        tasks = await asyncio.gather(
            worker1.run(),
            worker2.run(),
            watcher.run(),
            return_exceptions=True
        )
        
        # Log any exceptions
        for i, task in enumerate(tasks):
            if isinstance(task, Exception):
                logger.error(f"Component {i} failed: {task}", exc_info=task)
    
    except Exception as e:
        logger.error(f"System error: {e}", exc_info=True)
    
    finally:
        logger.info("\n" + "=" * 70)
        logger.info("System shutdown complete")
        logger.info("=" * 70)


if __name__ == "__main__":
    asyncio.run(run_system())
