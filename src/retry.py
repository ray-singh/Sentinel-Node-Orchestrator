"""Retry utilities with exponential backoff for async operations.

Provides `retry_async` to call an async callable with retries, exponential
backoff and jitter.
"""
import asyncio
import random
import logging
from typing import Callable, Any

logger = logging.getLogger(__name__)


async def retry_async(func: Callable[..., Any], *args, retries: int = 3, backoff: float = 0.5, factor: float = 2.0, max_delay: float = 30.0, jitter: float = 0.1, **kwargs):
    """Retry an async function with exponential backoff.

    Args:
        func: Async callable
        retries: Number of attempts (including first)
        backoff: Initial backoff in seconds
        factor: Multiplier per retry
        max_delay: Maximum delay between retries
        jitter: Fractional jitter to apply
    """
    attempt = 0
    last_exc = None

    while attempt < retries:
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_exc = e
            attempt += 1
            if attempt >= retries:
                logger.debug(f"Exhausted retries ({retries}) for {func}: {e}")
                raise

            # Compute delay
            delay = min(backoff * (factor ** (attempt - 1)), max_delay)
            # Apply jitter
            jitter_amount = delay * jitter * random.random()
            delay = delay + jitter_amount

            logger.warning(f"Retry {attempt}/{retries} for {func.__name__} after {delay:.2f}s due to: {e}")
            await asyncio.sleep(delay)

    # If we exit loop without returning, raise last exception
    if last_exc:
        raise last_exc
