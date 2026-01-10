"""Utilities for migrating TaskCheckpoint schema versions and agent-specific schemas.

This module provides a simple registry of migration functions keyed by
checkpoint_version strings. Migrations should be pure functions that accept
and return a `TaskCheckpoint` instance. New migrations can be added to
`_MIGRATIONS` and `migrate()` will apply any needed steps to update an
older checkpoint to the current schema.
"""
from typing import Callable, Dict

from .state import TaskCheckpoint
import logging

logger = logging.getLogger(__name__)

_MIGRATIONS: Dict[str, Callable[[TaskCheckpoint], TaskCheckpoint]] = {}

CURRENT_VERSION = "1.1"


def register_migration(from_version: str):
    def _inner(fn: Callable[[TaskCheckpoint], TaskCheckpoint]):
        _MIGRATIONS[from_version] = fn
        return fn
    return _inner


@register_migration("1.0")
def migrate_1_0_to_1_1(cp: TaskCheckpoint) -> TaskCheckpoint:
    """Example migration from 1.0 → 1.1.

    - Ensure `agent_version` and `agent_schema_version` fields exist.
    - Normalize `agent_state` to be a dict if None.
    """
    if cp.agent_state is None:
        cp.agent_state = {}

    # If agent_version not present, try to infer from agent_state
    if not getattr(cp, "agent_version", None):
        inferred = cp.agent_state.get("version") if isinstance(cp.agent_state, dict) else None
        if inferred:
            cp.agent_version = str(inferred)

    # Set schema version default
    if not getattr(cp, "agent_schema_version", None):
        cp.agent_schema_version = "v1"

    cp.checkpoint_version = "1.1"
    logger.info(f"Migrated checkpoint {cp.task_id} to version {cp.checkpoint_version}")
    return cp


def migrate(cp: TaskCheckpoint) -> TaskCheckpoint:
    """Migrate a TaskCheckpoint to the latest supported version.

    Applies migrations sequentially if needed.
    """
    current = getattr(cp, "checkpoint_version", None) or "1.0"
    if current == CURRENT_VERSION:
        return cp

    # Very simple linear migration map: apply migrations for versions < CURRENT_VERSION
    version_order = ["1.0", "1.1"]
    try:
        start_idx = version_order.index(current)
    except ValueError:
        # Unknown version - attempt best-effort
        logger.warning(f"Unknown checkpoint_version={current} for task {cp.task_id}")
        start_idx = 0

    for v in version_order[start_idx:]:
        if v == CURRENT_VERSION:
            break
        migrator = _MIGRATIONS.get(v)
        if migrator:
            cp = migrator(cp)

    # Ensure final version set
    cp.checkpoint_version = CURRENT_VERSION
    return cp
