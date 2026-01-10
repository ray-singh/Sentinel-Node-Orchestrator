"""Utilities for idempotent external side-effects.

This module provides a small `SideEffectManager` that uses Redis to ensure
that external side-effects (DB writes, uploads, notifications) are applied
at-most-once per task/effect-key. It follows a simple pattern:

- Before performing the effect, acquire a lock (SETNX) for `effects:{task_id}:{effect_key}`.
- If the lock already exists, read stored result (if any) and return it.
- If lock acquired, execute the effect and persist result under `effect_result:{task_id}:{effect_key}`.
- Release the lock (or keep the record so subsequent resumes can read it).

This provides a pragmatic idempotency pattern that the worker's nodes
can use when performing external writes.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable, Optional
import asyncio

import redis.asyncio as redis

logger = logging.getLogger(__name__)


class SideEffectManager:
    """Manage idempotent side-effects using Redis.

    Usage:
        manager = SideEffectManager(redis_client)
        result = await manager.run_once(task_id, "upload:doc42", upload_fn, s3_path)
    """

    def __init__(self, redis_client: redis.Redis, namespace: str = "effects"):
        self.redis = redis_client
        self.namespace = namespace

    def _lock_key(self, task_id: str, effect_key: str) -> str:
        return f"{self.namespace}:{task_id}:{effect_key}:lock"

    def _result_key(self, task_id: str, effect_key: str) -> str:
        return f"{self.namespace}:{task_id}:{effect_key}:result"

    async def run_once(self, task_id: str, effect_key: str, func: Callable[..., Any], *args, ttl: int = 60, **kwargs) -> Any:
        """Run `func` once for the given task/effect key.

        - If a stored result exists, return it.
        - Otherwise try to acquire the lock (SETNX). If lock cannot be acquired, wait for result.
        - If lock acquired, execute function and store result.

        Args:
            task_id: task identifier
            effect_key: unique effect identifier within task
            func: callable to run (can be async or sync)
            ttl: lock TTL in seconds
        """
        result_key = self._result_key(task_id, effect_key)
        lock_key = self._lock_key(task_id, effect_key)

        # Check for existing result
        existing = await self.redis.get(result_key)
        if existing:
            try:
                return json.loads(existing)
            except Exception:
                return existing

        # Try to acquire lock
        acquired = await self.redis.set(lock_key, "1", nx=True, ex=ttl)
        if not acquired:
            # Another worker is performing the effect. Wait for result to appear.
            logger.debug(f"Waiting for effect result: {task_id} / {effect_key}")
            for _ in range(30):
                await asyncio.sleep(0.5)
                existing = await self.redis.get(result_key)
                if existing:
                    try:
                        return json.loads(existing)
                    except Exception:
                        return existing
            raise RuntimeError("Timeout waiting for idempotent effect result")

        # We have the lock - perform the effect
        try:
            if asyncio.iscoroutinefunction(func):
                res = await func(*args, **kwargs)
            else:
                res = func(*args, **kwargs)

            # Persist result as JSON if possible
            try:
                payload = json.dumps(res)
            except Exception:
                payload = json.dumps({"_repr": str(res)})

            await self.redis.set(result_key, payload)
            return res
        except Exception as e:
            # Remove lock so others can retry
            await self.redis.delete(lock_key)
            logger.exception("Side-effect failed, lock released")
            raise

