"""Redis-based token bucket rate limiter with atomic operations."""

import logging
import time
from typing import Optional
from datetime import datetime

from redis.asyncio import Redis
from .metrics import RATE_LIMIT_HITS

logger = logging.getLogger(__name__)


# Lua script for atomic token consumption
# Returns: [allowed (1/0), tokens_remaining, retry_after_ms]
CONSUME_TOKENS_SCRIPT = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local tokens_requested = tonumber(ARGV[3])
local now = tonumber(ARGV[4])

-- Get current state
local state = redis.call('HMGET', key, 'tokens', 'last_refill')
local tokens = tonumber(state[1]) or capacity
local last_refill = tonumber(state[2]) or now

-- Calculate tokens to add based on time elapsed
local elapsed = now - last_refill
local tokens_to_add = elapsed * refill_rate

-- Refill tokens (capped at capacity)
tokens = math.min(capacity, tokens + tokens_to_add)

-- Try to consume tokens
local allowed = 0
local retry_after_ms = 0

if tokens >= tokens_requested then
    tokens = tokens - tokens_requested
    allowed = 1
else
    -- Calculate retry time
    local tokens_needed = tokens_requested - tokens
    retry_after_ms = math.ceil((tokens_needed / refill_rate) * 1000)
end

-- Update state
redis.call('HSET', key, 'tokens', tokens, 'last_refill', now)
redis.call('EXPIRE', key, 86400)  -- 24 hour TTL

return {allowed, tokens, retry_after_ms}
"""


class TokenBucketRateLimiter:
    """
    Redis-based token bucket rate limiter.
    
    Implements per-tenant and per-task rate limiting with automatic refill.
    Uses Lua scripts for atomic operations.
    """
    
    def __init__(
        self,
        redis: Redis,
        capacity: float = 100.0,
        refill_rate: float = 10.0,
    ):
        """
        Initialize rate limiter.
        
        Args:
            redis: Redis client
            capacity: Maximum tokens in bucket
            refill_rate: Tokens added per second
        """
        self.redis = redis
        self.capacity = capacity
        self.refill_rate = refill_rate
        self._consume_script = None
    
    async def _ensure_script_loaded(self):
        """Lazy load Lua script."""
        if self._consume_script is None:
            self._consume_script = self.redis.register_script(CONSUME_TOKENS_SCRIPT)
    
    async def consume(
        self,
        key: str,
        tokens: float = 1.0,
        capacity: Optional[float] = None,
        refill_rate: Optional[float] = None,
    ) -> tuple[bool, float, int]:
        """
        Try to consume tokens from bucket.
        
        Args:
            key: Rate limit key (e.g., "tenant:123" or "task:456")
            tokens: Number of tokens to consume
            capacity: Override default capacity
            refill_rate: Override default refill rate
            
        Returns:
            Tuple of (allowed, tokens_remaining, retry_after_ms)
        """
        await self._ensure_script_loaded()
        
        capacity = capacity or self.capacity
        refill_rate = refill_rate or self.refill_rate
        now = time.time()
        
        # Build Redis key
        redis_key = f"ratelimit:{key}"
        
        try:
            result = await self._consume_script(
                keys=[redis_key],
                args=[capacity, refill_rate, tokens, now],
            )
            
            allowed = bool(result[0])
            tokens_remaining = float(result[1])
            retry_after_ms = int(result[2])
            
            if not allowed:
                logger.warning(
                    f"Rate limit exceeded for {key}: "
                    f"requested={tokens}, remaining={tokens_remaining:.2f}, "
                    f"retry_after={retry_after_ms}ms"
                )
                try:
                    RATE_LIMIT_HITS.inc()
                except Exception:
                    pass
            
            return allowed, tokens_remaining, retry_after_ms
        
        except Exception as e:
            logger.error(f"Rate limit check failed for {key}: {e}", exc_info=True)
            # Fail open on errors
            return True, capacity, 0
    
    async def check_remaining(self, key: str) -> float:
        """
        Check remaining tokens without consuming.
        
        Args:
            key: Rate limit key
            
        Returns:
            Number of tokens remaining
        """
        redis_key = f"ratelimit:{key}"
        
        state = await self.redis.hmget(redis_key, "tokens", "last_refill")
        
        if state[0] is None:
            return self.capacity
        
        tokens = float(state[0])
        last_refill = float(state[1] or time.time())
        
        # Calculate refilled tokens
        elapsed = time.time() - last_refill
        tokens_to_add = elapsed * self.refill_rate
        tokens = min(self.capacity, tokens + tokens_to_add)
        
        return tokens
    
    async def reset(self, key: str):
        """
        Reset bucket to full capacity.
        
        Args:
            key: Rate limit key
        """
        redis_key = f"ratelimit:{key}"
        await self.redis.delete(redis_key)
        logger.info(f"Reset rate limit for {key}")
    
    async def set_capacity(
        self,
        key: str,
        capacity: float,
        refill_rate: Optional[float] = None,
    ):
        """
        Set custom capacity for a specific key.
        
        Args:
            key: Rate limit key
            capacity: New capacity
            refill_rate: New refill rate (optional)
        """
        redis_key = f"ratelimit:{key}"
        
        await self.redis.hset(
            redis_key,
            mapping={
                "tokens": capacity,
                "last_refill": time.time(),
            }
        )
        
        if refill_rate is not None:
            await self.redis.hset(redis_key, "refill_rate", refill_rate)
        
        await self.redis.expire(redis_key, 86400)
        
        logger.info(f"Set rate limit for {key}: capacity={capacity}, refill_rate={refill_rate}")
    
    async def get_stats(self, key: str) -> dict:
        """
        Get rate limit statistics.
        
        Args:
            key: Rate limit key
            
        Returns:
            Dict with tokens, last_refill, capacity, refill_rate
        """
        redis_key = f"ratelimit:{key}"
        
        state = await self.redis.hmget(redis_key, "tokens", "last_refill")
        
        if state[0] is None:
            return {
                "tokens": self.capacity,
                "last_refill": None,
                "capacity": self.capacity,
                "refill_rate": self.refill_rate,
            }
        
        tokens = float(state[0])
        last_refill = float(state[1] or time.time())
        
        # Calculate current tokens with refill
        elapsed = time.time() - last_refill
        tokens_to_add = elapsed * self.refill_rate
        current_tokens = min(self.capacity, tokens + tokens_to_add)
        
        return {
            "tokens": current_tokens,
            "last_refill": datetime.fromtimestamp(last_refill).isoformat(),
            "capacity": self.capacity,
            "refill_rate": self.refill_rate,
        }
