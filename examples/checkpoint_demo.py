"""Example usage of Redis checkpoint saver."""

import asyncio
import os
from datetime import datetime

from src.config import settings
from src.redis_saver import create_redis_saver
from src.state import (
    NodeState,
    NodeType,
    TaskCheckpoint,
    TaskMetadata,
    TaskStatus,
    LLMCallMetadata,
)


async def example_save_and_resume():
    """Demonstrate saving a checkpoint and resuming from it."""
    
    # Create Redis saver
    print("🔧 Connecting to Redis...")
    saver = await create_redis_saver(settings.redis_url)
    
    task_id = "task_123"
    worker_id = "worker_001"
    
    # Step 1: Create initial task metadata
    print(f"\n📝 Creating task {task_id}...")
    metadata = TaskMetadata(
        task_id=task_id,
        status=TaskStatus.QUEUED,
        tenant_id="tenant_abc",
        task_type="analyze_documents",
        task_params={"documents": ["doc1.pdf", "doc2.pdf"]},
        cost_limit=5.0,
    )
    await saver.save_task_metadata(metadata)
    print(f"✅ Task metadata saved: {metadata.status}")
    
    # Step 2: Worker claims the task
    print(f"\n🔒 Worker {worker_id} claiming task...")
    claimed = await saver.claim_task(task_id, worker_id, lease_duration=300)
    if claimed:
        print(f"✅ Task claimed successfully!")
    else:
        print(f"❌ Failed to claim task")
        return
    
    # Step 3: Execute first node and save checkpoint
    print(f"\n⚙️  Executing 'search' node...")
    
    search_state = NodeState(
        node_id="node_search_1",
        node_type=NodeType.SEARCH,
        inputs={"query": "financial statements"},
        outputs={"results": ["result1", "result2"]},
        started_at=datetime.utcnow(),
        completed_at=datetime.utcnow(),
    )
    
    checkpoint = TaskCheckpoint(
        task_id=task_id,
        current_node="node_search_1",
        node_history=["start", "node_search_1"],
        node_states={"node_search_1": search_state},
        attempts=1,
        cost_so_far=0.15,
        llm_calls=[
            LLMCallMetadata(
                model="gpt-4-turbo",
                prompt_tokens=150,
                completion_tokens=50,
                total_tokens=200,
                cost_usd=0.15,
                latency_ms=850.5,
            )
        ],
    )
    
    await saver.save_checkpoint(task_id, checkpoint)
    print(f"✅ Checkpoint saved at node: {checkpoint.current_node}")
    print(f"💰 Cost so far: ${checkpoint.cost_so_far:.2f}")
    
    # Step 4: Simulate crash and recovery
    print(f"\n💥 Simulating worker crash...")
    await asyncio.sleep(1)
    
    print(f"\n🔄 New worker attempting to resume task...")
    new_worker_id = "worker_002"
    
    # New worker claims the task (simulates lease expiration or explicit release)
    await saver.release_task(task_id, TaskStatus.QUEUED)
    claimed = await saver.claim_task(task_id, new_worker_id, lease_duration=300)
    
    if claimed:
        print(f"✅ Task claimed by {new_worker_id}")
        
        # Load checkpoint to resume
        loaded_checkpoint = await saver.load_checkpoint(task_id)
        if loaded_checkpoint:
            print(f"✅ Checkpoint loaded successfully!")
            print(f"   Current node: {loaded_checkpoint.current_node}")
            print(f"   Node history: {loaded_checkpoint.node_history}")
            print(f"   Previous cost: ${loaded_checkpoint.cost_so_far:.2f}")
            print(f"   Previous LLM calls: {len(loaded_checkpoint.llm_calls)}")
            
            # Continue execution from checkpoint
            print(f"\n⚙️  Resuming at next node: 'analyze'...")
            
            analyze_state = NodeState(
                node_id="node_analyze_1",
                node_type=NodeType.ANALYZE,
                inputs={"data": loaded_checkpoint.node_states["node_search_1"].outputs},
                outputs={"insights": ["insight1", "insight2"]},
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow(),
            )
            
            # Update checkpoint
            loaded_checkpoint.current_node = "node_analyze_1"
            loaded_checkpoint.node_history.append("node_analyze_1")
            loaded_checkpoint.node_states["node_analyze_1"] = analyze_state
            
            # Increment cost
            new_cost = await saver.increment_cost(task_id, 0.25)
            loaded_checkpoint.cost_so_far = new_cost
            
            await saver.save_checkpoint(task_id, loaded_checkpoint)
            print(f"✅ Resumed execution, new cost: ${new_cost:.2f}")
    
    # Step 5: Complete the task
    print(f"\n🎉 Completing task...")
    final_metadata = await saver.load_task_metadata(task_id)
    if final_metadata:
        final_metadata.status = TaskStatus.COMPLETED
        final_metadata.result = {"summary": "Analysis complete"}
        final_metadata.completed_at = datetime.utcnow()
        await saver.save_task_metadata(final_metadata)
        print(f"✅ Task completed: {final_metadata.status}")
    
    # Cleanup
    await saver.redis.close()
    print(f"\n✨ Example completed successfully!")


async def example_lease_cleanup():
    """Demonstrate automatic cleanup of expired leases."""
    
    print("🔧 Connecting to Redis...")
    saver = await create_redis_saver(settings.redis_url)
    
    print("\n🧹 Checking for expired leases...")
    cleaned = await saver.cleanup_expired_leases()
    print(f"✅ Cleaned up {cleaned} expired leases")
    
    await saver.redis.close()


if __name__ == "__main__":
    print("=" * 60)
    print("Sentinel Node Orchestrator - Checkpoint Example")
    print("=" * 60)
    
    # Run the example
    asyncio.run(example_save_and_resume())
    
    print("\n" + "=" * 60)
    print("Lease Cleanup Example")
    print("=" * 60)
    asyncio.run(example_lease_cleanup())
