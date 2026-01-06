"""Demo of FastAPI controller - submit tasks and check status."""

import asyncio
import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

API_BASE_URL = "http://localhost:8000"


async def demo_api_workflow():
    """
    Demonstrate the complete API workflow:
    1. Create tasks via API
    2. Check task status
    3. List all tasks
    4. Get statistics
    5. Check tenant costs
    """
    logger.info("=" * 70)
    logger.info("FastAPI Controller Demo")
    logger.info("=" * 70)
    
    async with httpx.AsyncClient() as client:
        # Health check
        logger.info("\n🏥 Checking API health...")
        response = await client.get(f"{API_BASE_URL}/health")
        health = response.json()
        logger.info(f"✅ API Status: {health['status']}")
        logger.info(f"   Redis Connected: {health['redis_connected']}")
        
        # Create multiple tasks
        logger.info("\n📝 Creating tasks...")
        task_ids = []
        
        for i in range(3):
            task_data = {
                "task_type": "analyze_documents",
                "task_params": {
                    "documents": [f"doc{i}_1.pdf", f"doc{i}_2.pdf"],
                    "query": f"analysis query {i+1}"
                },
                "tenant_id": "demo_tenant",
                "cost_limit": 5.0,
                "max_attempts": 3,
            }
            
            response = await client.post(f"{API_BASE_URL}/tasks", json=task_data)
            
            if response.status_code == 201:
                task = response.json()
                task_ids.append(task["task_id"])
                logger.info(f"✅ Created task: {task['task_id']}")
                logger.info(f"   Type: {task['task_type']}")
                logger.info(f"   Status: {task['status']}")
            else:
                logger.error(f"❌ Failed to create task: {response.text}")
        
        # Wait a moment
        await asyncio.sleep(1)
        
        # Check individual task status
        logger.info(f"\n🔍 Checking status of first task...")
        response = await client.get(f"{API_BASE_URL}/tasks/{task_ids[0]}")
        
        if response.status_code == 200:
            task = response.json()
            logger.info(f"✅ Task {task['task_id']}")
            logger.info(f"   Status: {task['status']}")
            logger.info(f"   Owner: {task['owner']}")
            logger.info(f"   Cost: ${task['cost_so_far']:.2f}")
            logger.info(f"   Attempts: {task['attempts']}/{task['max_attempts']}")
        
        # List all tasks
        logger.info(f"\n📋 Listing all tasks...")
        response = await client.get(f"{API_BASE_URL}/tasks")
        
        if response.status_code == 200:
            data = response.json()
            logger.info(f"✅ Found {data['total']} total tasks")
            for task in data['tasks'][:5]:  # Show first 5
                logger.info(f"   - {task['task_id']}: {task['status']} ({task['task_type']})")
        
        # Filter by status
        logger.info(f"\n🔎 Listing queued tasks...")
        response = await client.get(f"{API_BASE_URL}/tasks?status_filter=queued")
        
        if response.status_code == 200:
            data = response.json()
            logger.info(f"✅ Found {data['total']} queued tasks")
        
        # Get statistics
        logger.info(f"\n📊 Getting statistics...")
        response = await client.get(f"{API_BASE_URL}/stats")
        
        if response.status_code == 200:
            stats = response.json()
            logger.info(f"✅ Task Statistics:")
            logger.info(f"   Total: {stats['total_tasks']}")
            logger.info(f"   Queued: {stats['queued']}")
            logger.info(f"   Leased: {stats['leased']}")
            logger.info(f"   In Progress: {stats['in_progress']}")
            logger.info(f"   Completed: {stats['completed']}")
            logger.info(f"   Failed: {stats['failed']}")
        
        # Get tenant costs
        logger.info(f"\n💰 Getting tenant costs...")
        response = await client.get(f"{API_BASE_URL}/tenants/demo_tenant/costs")
        
        if response.status_code == 200:
            costs = response.json()
            logger.info(f"✅ Tenant: {costs['tenant_id']}")
            logger.info(f"   Total Cost: ${costs['total_cost_usd']:.4f}")
            logger.info(f"   Task Count: {costs['task_count']}")
            logger.info(f"   Average Cost: ${costs['average_cost_usd']:.4f}")
        
        # Cancel a task (optional)
        if len(task_ids) > 0:
            logger.info(f"\n❌ Cancelling a task...")
            response = await client.delete(f"{API_BASE_URL}/tasks/{task_ids[-1]}")
            
            if response.status_code == 204:
                logger.info(f"✅ Task {task_ids[-1]} cancelled")
                
                # Verify cancellation
                response = await client.get(f"{API_BASE_URL}/tasks/{task_ids[-1]}")
                if response.status_code == 200:
                    task = response.json()
                    logger.info(f"   Status: {task['status']}")
                    logger.info(f"   Error: {task['error']}")
    
    logger.info("\n" + "=" * 70)
    logger.info("🎉 API Demo completed!")
    logger.info("=" * 70)


async def demo_with_worker_processing():
    """
    Demonstrate end-to-end workflow:
    1. Start API
    2. Submit tasks
    3. Worker processes them
    4. Check results
    """
    logger.info("=" * 70)
    logger.info("End-to-End Demo: API + Worker")
    logger.info("=" * 70)
    logger.info("\nPrerequisites:")
    logger.info("1. API server running: python3 src/api.py")
    logger.info("2. Worker running: python3 -m src.worker")
    logger.info("3. Redis running: docker run -d -p 6379:6379 redis:7-alpine")
    logger.info("\nPress Ctrl+C to stop\n")
    
    async with httpx.AsyncClient() as client:
        # Create a task
        logger.info("📝 Creating task via API...")
        task_data = {
            "task_type": "demo_task",
            "task_params": {"data": "test"},
            "tenant_id": "demo_tenant",
            "cost_limit": 5.0,
        }
        
        response = await client.post(f"{API_BASE_URL}/tasks", json=task_data)
        
        if response.status_code == 201:
            task = response.json()
            task_id = task["task_id"]
            logger.info(f"✅ Created task: {task_id}")
            
            # Poll for completion
            logger.info("\n⏳ Waiting for worker to process task...")
            for i in range(30):  # Poll for up to 30 seconds
                await asyncio.sleep(1)
                
                response = await client.get(f"{API_BASE_URL}/tasks/{task_id}")
                if response.status_code == 200:
                    task = response.json()
                    logger.info(f"   [{i+1}s] Status: {task['status']}, Cost: ${task['cost_so_far']:.2f}")
                    
                    if task['status'] in ['completed', 'failed']:
                        logger.info(f"\n🎉 Task finished!")
                        logger.info(f"   Final Status: {task['status']}")
                        logger.info(f"   Total Cost: ${task['cost_so_far']:.2f}")
                        logger.info(f"   Attempts: {task['attempts']}")
                        if task['result']:
                            logger.info(f"   Result: {task['result']}")
                        break
            else:
                logger.warning("\n⏰ Timeout waiting for task completion")
        else:
            logger.error(f"❌ Failed to create task: {response.text}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "e2e":
        # End-to-end demo
        asyncio.run(demo_with_worker_processing())
    else:
        # Basic API demo
        asyncio.run(demo_api_workflow())
