"""Demo of token bucket rate limiting."""

import asyncio
import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from redis.asyncio import Redis
from src.rate_limiter import TokenBucketRateLimiter
from src.config import settings

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def demo_basic_rate_limiting():
    """Demonstrate basic token bucket behavior."""
    logger.info("=" * 70)
    logger.info("Basic Rate Limiting Demo")
    logger.info("=" * 70)
    
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    
    # Create rate limiter with small capacity for demo
    limiter = TokenBucketRateLimiter(
        redis=redis,
        capacity=5.0,  # 5 tokens max
        refill_rate=1.0,  # 1 token per second
    )
    
    key = "demo:user123"
    
    # Reset first
    await limiter.reset(key)
    
    logger.info(f"\n📊 Bucket config: capacity=5, refill_rate=1/sec")
    
    # Test 1: Consume tokens rapidly
    logger.info("\n🔥 Test 1: Consume 5 tokens rapidly...")
    for i in range(5):
        allowed, remaining, retry_after = await limiter.consume(key, tokens=1.0)
        logger.info(
            f"  Request {i+1}: allowed={allowed}, remaining={remaining:.2f}"
        )
    
    # Test 2: Hit rate limit
    logger.info("\n🚫 Test 2: Exceed rate limit...")
    allowed, remaining, retry_after = await limiter.consume(key, tokens=1.0)
    logger.info(
        f"  Request 6: allowed={allowed}, remaining={remaining:.2f}, "
        f"retry_after={retry_after}ms"
    )
    
    if not allowed:
        logger.info(f"  ⏳ Waiting {retry_after/1000:.2f}s for token refill...")
        await asyncio.sleep(retry_after / 1000.0)
        
        allowed, remaining, retry_after = await limiter.consume(key, tokens=1.0)
        logger.info(f"  After wait: allowed={allowed}, remaining={remaining:.2f}")
    
    # Test 3: Check remaining
    logger.info("\n📈 Test 3: Check remaining tokens...")
    remaining = await limiter.check_remaining(key)
    logger.info(f"  Remaining tokens (without consuming): {remaining:.2f}")
    
    # Test 4: Wait for refill
    logger.info("\n⏰ Test 4: Wait 2 seconds for refill...")
    await asyncio.sleep(2.0)
    
    stats = await limiter.get_stats(key)
    logger.info(f"  Stats after refill: {stats}")
    
    await redis.close()
    logger.info("\n" + "=" * 70)


async def demo_multi_tenant():
    """Demonstrate per-tenant rate limiting."""
    logger.info("=" * 70)
    logger.info("Multi-Tenant Rate Limiting Demo")
    logger.info("=" * 70)
    
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    
    limiter = TokenBucketRateLimiter(
        redis=redis,
        capacity=10.0,
        refill_rate=2.0,
    )
    
    # Different tenants with different limits
    tenants = [
        ("tenant:free", 3.0, 0.5),      # Free tier: 3 tokens, 0.5/sec
        ("tenant:pro", 10.0, 2.0),      # Pro tier: 10 tokens, 2/sec
        ("tenant:enterprise", 50.0, 10.0),  # Enterprise: 50 tokens, 10/sec
    ]
    
    logger.info("\n🏢 Setting up tenant rate limits...")
    for key, capacity, refill_rate in tenants:
        await limiter.set_capacity(key, capacity, refill_rate)
        logger.info(f"  {key}: capacity={capacity}, refill={refill_rate}/sec")
    
    # Simulate requests
    logger.info("\n📊 Simulating concurrent requests...")
    
    async def make_requests(tenant_key: str, count: int):
        results = {"allowed": 0, "denied": 0}
        for i in range(count):
            allowed, remaining, retry_after = await limiter.consume(tenant_key, tokens=1.0)
            if allowed:
                results["allowed"] += 1
            else:
                results["denied"] += 1
            await asyncio.sleep(0.1)
        return tenant_key, results
    
    # Run concurrent requests for all tenants
    tasks = [
        make_requests("tenant:free", 5),
        make_requests("tenant:pro", 12),
        make_requests("tenant:enterprise", 60),
    ]
    
    results = await asyncio.gather(*tasks)
    
    logger.info("\n✅ Results:")
    for tenant_key, stats in results:
        logger.info(f"  {tenant_key}: allowed={stats['allowed']}, denied={stats['denied']}")
    
    # Check final stats
    logger.info("\n📈 Final stats for all tenants:")
    for key, _, _ in tenants:
        stats = await limiter.get_stats(key)
        logger.info(f"  {key}: tokens={stats['tokens']:.2f}/{stats['capacity']}")
    
    await redis.close()
    logger.info("\n" + "=" * 70)


async def demo_burst_handling():
    """Demonstrate burst request handling."""
    logger.info("=" * 70)
    logger.info("Burst Request Handling Demo")
    logger.info("=" * 70)
    
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    
    limiter = TokenBucketRateLimiter(
        redis=redis,
        capacity=10.0,
        refill_rate=5.0,  # 5 tokens per second
    )
    
    key = "demo:burst"
    await limiter.reset(key)
    
    logger.info("\n💥 Sending burst of 15 requests...")
    
    allowed_count = 0
    denied_count = 0
    
    for i in range(15):
        allowed, remaining, retry_after = await limiter.consume(key, tokens=1.0)
        
        status = "✅ ALLOWED" if allowed else "❌ DENIED"
        logger.info(
            f"  Request {i+1:2d}: {status} | remaining={remaining:.2f} | "
            f"retry_after={retry_after}ms"
        )
        
        if allowed:
            allowed_count += 1
        else:
            denied_count += 1
        
        await asyncio.sleep(0.05)  # Small delay between requests
    
    logger.info(f"\n📊 Summary: {allowed_count} allowed, {denied_count} denied")
    
    # Wait for refill and try again
    logger.info("\n⏰ Waiting 2 seconds for refill...")
    await asyncio.sleep(2.0)
    
    stats = await limiter.get_stats(key)
    logger.info(f"  After refill: {stats['tokens']:.2f} tokens available")
    
    await redis.close()
    logger.info("\n" + "=" * 70)


async def demo_task_rate_limiting():
    """Simulate rate limiting in task execution."""
    logger.info("=" * 70)
    logger.info("Task Execution Rate Limiting Demo")
    logger.info("=" * 70)
    
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    
    limiter = TokenBucketRateLimiter(
        redis=redis,
        capacity=5.0,
        refill_rate=1.0,
    )
    
    tenant_id = "tenant:demo"
    await limiter.reset(f"tenant:{tenant_id}")
    
    async def execute_task_with_rate_limit(task_id: int):
        """Simulate task execution with rate limiting."""
        key = f"tenant:{tenant_id}"
        
        # Try to consume token
        allowed, remaining, retry_after = await limiter.consume(key, tokens=1.0)
        
        if not allowed:
            logger.info(
                f"  Task {task_id}: ⏳ Rate limited, waiting {retry_after/1000:.2f}s..."
            )
            await asyncio.sleep(retry_after / 1000.0)
            
            # Retry
            allowed, remaining, retry_after = await limiter.consume(key, tokens=1.0)
            
            if not allowed:
                logger.error(f"  Task {task_id}: ❌ Still rate limited after retry!")
                return False
        
        # Execute task
        logger.info(
            f"  Task {task_id}: ✅ Executing (remaining={remaining:.2f} tokens)"
        )
        await asyncio.sleep(0.2)  # Simulate work
        logger.info(f"  Task {task_id}: 🎉 Completed")
        return True
    
    logger.info(f"\n🚀 Executing 8 tasks for {tenant_id}...")
    logger.info(f"   Rate limit: 5 tokens, 1 token/sec\n")
    
    tasks = [execute_task_with_rate_limit(i) for i in range(1, 9)]
    results = await asyncio.gather(*tasks)
    
    success_count = sum(results)
    logger.info(f"\n📊 Completed {success_count}/{len(tasks)} tasks")
    
    await redis.close()
    logger.info("\n" + "=" * 70)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        demo_type = sys.argv[1]
        
        if demo_type == "basic":
            asyncio.run(demo_basic_rate_limiting())
        elif demo_type == "tenant":
            asyncio.run(demo_multi_tenant())
        elif demo_type == "burst":
            asyncio.run(demo_burst_handling())
        elif demo_type == "task":
            asyncio.run(demo_task_rate_limiting())
        else:
            print(f"Unknown demo type: {demo_type}")
            print("Available: basic, tenant, burst, task")
    else:
        # Run all demos
        asyncio.run(demo_basic_rate_limiting())
        print("\n")
        asyncio.run(demo_multi_tenant())
        print("\n")
        asyncio.run(demo_burst_handling())
        print("\n")
        asyncio.run(demo_task_rate_limiting())
