import os
import pytest
from datetime import datetime, timedelta

from src.state import (
    TaskMetadata,
    TaskStatus,
    TaskCheckpoint,
    NodeState,
    NodeType,
)

from src.redis_saver import create_redis_saver


@pytest.fixture(scope="module")
async def saver():
    redis_url = os.getenv("TEST_REDIS_URL", "redis://localhost:6379")
    saver = await create_redis_saver(redis_url)
    yield saver
    # cleanup DB after tests
    try:
        await saver.redis.flushdb()
    finally:
        await saver.redis.close()


@pytest.mark.asyncio
async def test_save_load_metadata(saver):
    task_id = "test_task_meta"
    meta = TaskMetadata(
        task_id=task_id, status=TaskStatus.QUEUED, tenant_id="t1", task_type="test"
    )
    await saver.save_task_metadata(meta)
    loaded = await saver.load_task_metadata(task_id)
    assert loaded is not None
    assert loaded.task_id == task_id
    assert loaded.status == TaskStatus.QUEUED


@pytest.mark.asyncio
async def test_save_load_checkpoint(saver):
    task_id = "test_task_cp"
    n = NodeState(
        node_id="n1",
        node_type=NodeType.SEARCH,
        inputs={"q": "x"},
        outputs={"v": 1},
        started_at=datetime.utcnow(),
        completed_at=datetime.utcnow(),
    )
    cp = TaskCheckpoint(task_id=task_id, current_node="n1", node_history=["n1"], node_states={"n1": n}, attempts=0)
    await saver.save_checkpoint(task_id, cp)
    loaded = await saver.load_checkpoint(task_id)
    assert loaded is not None
    assert loaded.current_node == "n1"
    assert "n1" in loaded.node_states
    assert loaded.node_states["n1"].outputs["v"] == 1


@pytest.mark.asyncio
async def test_claim_release_task(saver):
    task_id = "test_claim"
    meta = TaskMetadata(task_id=task_id, status=TaskStatus.QUEUED, tenant_id="t1", task_type="test")
    await saver.save_task_metadata(meta)
    claimed = await saver.claim_task(task_id, "w1", lease_duration=2)
    assert claimed

    # release and ensure status reset
    await saver.release_task(task_id, TaskStatus.QUEUED)
    loaded = await saver.load_task_metadata(task_id)
    assert loaded.status == TaskStatus.QUEUED
    assert loaded.owner in (None, "")


@pytest.mark.asyncio
async def test_increment_cost(saver):
    task_id = "test_cost"
    meta = TaskMetadata(task_id=task_id, status=TaskStatus.QUEUED, tenant_id="t1", task_type="test", cost_so_far=0.0)
    await saver.save_task_metadata(meta)
    new_cost = await saver.increment_cost(task_id, 0.5)
    assert float(new_cost) >= 0.5
    loaded_meta = await saver.load_task_metadata(task_id)
    assert float(loaded_meta.cost_so_far) >= 0.5


@pytest.mark.asyncio
async def test_cleanup_expired_leases(saver):
    task_id = "test_expired"
    # save metadata with expired lease
    past = datetime.utcnow() - timedelta(seconds=10)
    meta = TaskMetadata(
        task_id=task_id,
        status=TaskStatus.LEASED,
        tenant_id="t1",
        task_type="test",
        owner="w1",
        lease_expires=past,
    )
    await saver.save_task_metadata(meta)
    cleaned = await saver.cleanup_expired_leases()
    assert cleaned >= 1
    loaded = await saver.load_task_metadata(task_id)
    assert loaded.status == TaskStatus.QUEUED
