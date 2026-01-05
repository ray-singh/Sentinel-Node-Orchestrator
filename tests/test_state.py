import pytest
from datetime import datetime

from src.state import (
    NodeState,
    NodeType,
    TaskCheckpoint,
    LLMCallMetadata,
)


def test_state_serialization_roundtrip():
    """Ensure TaskCheckpoint serializes and deserializes cleanly."""
    now = datetime.utcnow()

    node = NodeState(
        node_id="n1",
        node_type=NodeType.SEARCH,
        inputs={"q": "value"},
        outputs={"r": [1, 2, 3]},
        started_at=now,
        completed_at=now,
    )

    cp = TaskCheckpoint(
        task_id="t1",
        current_node="n1",
        node_history=["start", "n1"],
        node_states={"n1": node},
        attempts=1,
        cost_so_far=0.12,
        llm_calls=[
            LLMCallMetadata(
                model="gpt-test",
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
                cost_usd=0.01,
                latency_ms=100.0,
            )
        ],
    )

    # Serialize to JSON and back
    j = cp.model_dump_json()
    cp2 = TaskCheckpoint.model_validate_json(j)

    assert cp2.task_id == cp.task_id
    assert cp2.current_node == cp.current_node
    assert "n1" in cp2.node_states
    assert cp2.node_states["n1"].outputs["r"] == [1, 2, 3]
