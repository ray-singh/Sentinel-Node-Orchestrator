"""Demo of async worker claiming and executing tasks."""

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


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def setup_test_tasks():
    """Create some test tasks in Redis."""
    logger.info("Setting up test tasks...")
    
    saver = await create_redis_saver(settings.redis_url)
    
    # Create 3 test tasks
    for i in range(1, 4):
        task_id = f"demo_task_{i}"
        meta = TaskMetadata(
            task_id=task_id,
            status=TaskStatus.QUEUED,
            tenant_id="demo_tenant",
            task_type="analyze_documents",
            task_params={
                "documents": [f"doc{i}_1.pdf", f"doc{i}_2.pdf"],
                "query": "financial analysis"
            },
            cost_limit=5.0,
        )
        await saver.save_task_metadata(meta)
        logger.info(f"Created task: {task_id}")
    
    await saver.redis.close()
    logger.info("Test tasks created!")


async def run_worker_demo():
    """Run worker demo with multiple workers."""
    logger.info("=" * 60)
    logger.info("Async Worker Demo")
    logger.info("=" * 60)
    
    # Setup test tasks
    await setup_test_tasks()
    
    logger.info("\nStarting 2 workers to process tasks...\n")
    
    # Create 2 workers
    worker1 = AsyncWorker(worker_id="demo-worker-1")
    worker2 = AsyncWorker(worker_id="demo-worker-2")
    
    # Run both workers concurrently
    try:
        await asyncio.gather(
            worker1.run(),
            worker2.run(),
        )
    except KeyboardInterrupt:
        logger.info("\nDemo interrupted by user")
    finally:
        logger.info("\nDemo completed!")


async def run_single_task_demo():
    """Run a single task through one worker to demonstrate checkpoint/resume."""
    logger.info("=" * 60)
    logger.info("Single Task Checkpoint Demo")
    logger.info("=" * 60)
    
    # Create a task
    task_id = "checkpoint_demo_task"
    saver = await create_redis_saver(settings.redis_url)
    
    meta = TaskMetadata(
        task_id=task_id,
        status=TaskStatus.QUEUED,
        tenant_id="demo_tenant",
        task_type="analysis",
        task_params={"query": "test"},
        cost_limit=5.0,
    )
    await saver.save_task_metadata(meta)
    logger.info(f"Created task: {task_id}\n")
    
    # Worker 1 starts processing
    logger.info("Worker 1 claiming and starting task...")
    worker1 = AsyncWorker(worker_id="worker-1")
    await worker1.start()
    
    claimed = await worker1.saver.claim_task(task_id, worker1.worker_id, 300)
    if claimed:
        logger.info("✅ Task claimed by worker-1")
        
        # Start execution but simulate crash after 2 nodes
        try:
            # Manually execute first 2 nodes
            checkpoint = await worker1.saver.load_checkpoint(task_id)
            if not checkpoint:
                from src.state import TaskCheckpoint
                checkpoint = TaskCheckpoint(
                    task_id=task_id,
                    current_node="start",
                    node_history=["start"],
                    attempts=1,
                )
            
            # Execute search node
            from src.state import NodeState, NodeType
            search_state = NodeState(
                node_id="search",
                node_type=NodeType.SEARCH,
                inputs={"query": "test"},
                outputs={"results": ["result1", "result2"]},
            )
            checkpoint.current_node = "search"
            checkpoint.node_history.append("search")
            checkpoint.node_states["search"] = search_state
            await worker1.saver.save_checkpoint(task_id, checkpoint)
            logger.info("✅ Completed 'search' node, checkpoint saved")
            
            # Execute analyze node
            analyze_state = NodeState(
                node_id="analyze",
                node_type=NodeType.ANALYZE,
                inputs={"data": search_state.outputs},
                outputs={"insights": ["insight1", "insight2"]},
            )
            checkpoint.current_node = "analyze"
            checkpoint.node_history.append("analyze")
            checkpoint.node_states["analyze"] = analyze_state
            await worker1.saver.save_checkpoint(task_id, checkpoint)
            logger.info("✅ Completed 'analyze' node, checkpoint saved")
            
            # Simulate crash
            logger.info("\n💥 SIMULATING WORKER CRASH!\n")
            await worker1.saver.release_task(task_id, TaskStatus.QUEUED)
            await worker1.stop()
            
        except Exception as e:
            logger.error(f"Error: {e}")
    
    # Wait a moment
    await asyncio.sleep(1)
    
    # Worker 2 picks up the task
    logger.info("Worker 2 claiming and resuming task...")
    worker2 = AsyncWorker(worker_id="worker-2")
    await worker2.start()
    
    claimed = await worker2.saver.claim_task(task_id, worker2.worker_id, 300)
    if claimed:
        logger.info("✅ Task claimed by worker-2")
        
        # Load checkpoint and resume
        checkpoint = await worker2.saver.load_checkpoint(task_id)
        if checkpoint:
            logger.info(f"✅ Loaded checkpoint from node: {checkpoint.current_node}")
            logger.info(f"   Node history: {checkpoint.node_history}")
            logger.info(f"   Previous nodes executed: {list(checkpoint.node_states.keys())}")
            
            # Execute remaining nodes
            logger.info("\n🔄 Resuming execution from checkpoint...")
            
            # Execute summarize node
            from src.state import NodeState, NodeType
            summarize_state = NodeState(
                node_id="summarize",
                node_type=NodeType.SUMMARIZE,
                inputs={"data": checkpoint.node_states["analyze"].outputs},
                outputs={"summary": "Final summary"},
            )
            checkpoint.current_node = "summarize"
            checkpoint.node_history.append("summarize")
            checkpoint.node_states["summarize"] = summarize_state
            await worker2.saver.save_checkpoint(task_id, checkpoint)
            logger.info("✅ Completed 'summarize' node, checkpoint saved")
            
            # Complete task
            complete_state = NodeState(
                node_id="complete",
                node_type=NodeType.COMPLETE,
                inputs={"summary": summarize_state.outputs},
                outputs={"status": "done"},
            )
            checkpoint.current_node = "complete"
            checkpoint.node_history.append("complete")
            checkpoint.node_states["complete"] = complete_state
            await worker2.saver.save_checkpoint(task_id, checkpoint)
            logger.info("✅ Completed 'complete' node, checkpoint saved")
            
            # Mark task complete
            meta = await worker2.saver.load_task_metadata(task_id)
            meta.status = TaskStatus.COMPLETED
            meta.result = {"final_summary": "Task completed successfully after resume"}
            await worker2.saver.save_task_metadata(meta)
            
            logger.info("\n🎉 Task completed successfully!")
            logger.info(f"   Total nodes executed: {len(checkpoint.node_states)}")
            logger.info(f"   Node sequence: {' → '.join(checkpoint.node_history)}")
    
    await worker2.stop()
    await saver.redis.close()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "checkpoint":
        # Run single task checkpoint demo
        asyncio.run(run_single_task_demo())
    else:
        # Run multi-worker demo
        # Note: This will run indefinitely, press Ctrl+C to stop
        asyncio.run(run_worker_demo())
