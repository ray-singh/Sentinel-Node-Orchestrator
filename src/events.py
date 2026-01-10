"""Event emitter utilities to record lifecycle and audit events to Redis stream.

Small helper to push structured events to `stream:events` for observability.
"""
import json
import logging
from typing import Any, Dict

import redis.asyncio as redis

logger = logging.getLogger(__name__)

STREAM_KEY = "stream:events"


async def emit_event(redis_client: redis.Redis, event_type: str, payload: Dict[str, Any]) -> None:
    """Emit an event to the Redis stream.

    Args:
        redis_client: Redis client instance
        event_type: Short event type string
        payload: JSON-serializable payload
    """
    try:
        data = {
            "type": event_type,
            "payload": json.dumps(payload),
        }
        await redis_client.xadd(STREAM_KEY, data)
    except Exception as e:
        logger.exception(f"Failed to emit event {event_type}: {e}")
