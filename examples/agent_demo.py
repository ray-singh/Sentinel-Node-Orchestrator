"""Demo of agent abstraction layer with custom agent implementations."""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agent import Agent, PromptBasedAgent, create_agent, register_agent
from src.state import NodeType, NodeState, TaskMetadata, LLMCallMetadata
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MockAgent(Agent):
    """
    Mock agent for testing without LLM calls.
    
    Returns simple mock outputs for each node type.
    """
    
    async def initialize(self, metadata: TaskMetadata) -> None:
        logger.info(f"MockAgent initialized for task {metadata.task_id}")
    
    async def cleanup(self) -> None:
        logger.info("MockAgent cleaned up")
    
    @property
    def agent_type(self) -> str:
        return "mock"
    
    async def execute_node(
        self,
        node_id: str,
        node_type: NodeType,
        inputs: Dict[str, Any],
        metadata: TaskMetadata,
    ) -> tuple[NodeState, Optional[LLMCallMetadata]]:
        """Execute node with mock outputs."""
        started_at = datetime.utcnow()
        
        # Simulate some work
        await asyncio.sleep(0.1)
        
        # Generate mock output based on node type
        if node_type == NodeType.SEARCH:
            outputs = {
                "results": ["Mock result 1", "Mock result 2", "Mock result 3"],
                "query": inputs.get("query", "unknown"),
            }
        elif node_type == NodeType.ANALYZE:
            outputs = {
                "analysis": "Mock analysis of the data",
                "key_findings": ["Finding 1", "Finding 2"],
            }
        elif node_type == NodeType.SUMMARIZE:
            outputs = {
                "summary": "Mock summary of the analysis",
            }
        else:
            outputs = {
                "result": f"Mock output from {node_id}",
            }
        
        completed_at = datetime.utcnow()
        
        node_state = NodeState(
            node_id=node_id,
            node_type=node_type,
            inputs=inputs,
            outputs=outputs,
            metadata={"mock": True},
            started_at=started_at,
            completed_at=completed_at,
        )
        
        return node_state, None


async def demo_agent_abstraction():
    """Demonstrate different agent implementations."""
    logger.info("=" * 70)
    logger.info("Agent Abstraction Demo")
    logger.info("=" * 70)
    
    # Create mock task metadata
    metadata = TaskMetadata(
        task_id="demo-123",
        tenant_id="tenant-demo",
        task_type="research",
        task_params={"query": "What is fault tolerance?"},
        status="queued",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    
    # Test 1: PromptBasedAgent (without LLM calls - will use mock if no API key)
    logger.info("\n📌 Test 1: PromptBasedAgent")
    prompt_agent = create_agent("prompt-based", default_model="gpt-4o-mini")
    
    logger.info(f"  Agent type: {prompt_agent.agent_type}")
    
    await prompt_agent.initialize(metadata)
    
    # Execute a non-LLM node
    node_state, llm_meta = await prompt_agent.execute_node(
        node_id="start",
        node_type=NodeType.START,
        inputs={},
        metadata=metadata,
    )
    
    logger.info(f"  Node outputs: {node_state.outputs}")
    logger.info(f"  LLM metadata: {llm_meta}")
    
    await prompt_agent.cleanup()
    
    # Test 2: MockAgent (custom implementation)
    logger.info("\n📌 Test 2: MockAgent (custom)")
    
    # Register custom agent
    register_agent("mock", MockAgent)
    
    mock_agent = create_agent("mock")
    logger.info(f"  Agent type: {mock_agent.agent_type}")
    
    await mock_agent.initialize(metadata)
    
    # Execute different node types
    for node_id, node_type in [
        ("search", NodeType.SEARCH),
        ("analyze", NodeType.ANALYZE),
        ("summarize", NodeType.SUMMARIZE),
    ]:
        node_state, llm_meta = await mock_agent.execute_node(
            node_id=node_id,
            node_type=node_type,
            inputs={"prev_outputs": {}},
            metadata=metadata,
        )
        
        logger.info(f"  {node_type.value} outputs: {node_state.outputs}")
    
    await mock_agent.cleanup()
    
    # Test 3: Agent factory with error handling
    logger.info("\n📌 Test 3: Agent factory error handling")
    
    try:
        invalid_agent = create_agent("invalid-type")
    except ValueError as e:
        logger.info(f"  ✅ Caught expected error: {e}")
    
    logger.info("\n" + "=" * 70)
    logger.info("🎉 Agent Abstraction Demo completed!")
    logger.info("=" * 70)


async def demo_agent_with_worker_pattern():
    """Demonstrate agent usage in worker-like pattern."""
    logger.info("=" * 70)
    logger.info("Agent with Worker Pattern Demo")
    logger.info("=" * 70)
    
    # Register custom agent
    register_agent("mock", MockAgent)
    
    # Create task
    metadata = TaskMetadata(
        task_id="task-456",
        tenant_id="tenant-test",
        task_type="pipeline",
        task_params={"query": "Explain checkpointing"},
        status="queued",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    
    # Create agent
    agent = create_agent("mock")
    
    logger.info(f"\n🚀 Executing task with {agent.agent_type} agent...")
    
    # Initialize agent for task
    await agent.initialize(metadata)
    
    # Simulate node sequence
    node_sequence = [
        ("search", NodeType.SEARCH),
        ("analyze", NodeType.ANALYZE),
        ("summarize", NodeType.SUMMARIZE),
    ]
    
    prev_outputs = {}
    
    for node_id, node_type in node_sequence:
        logger.info(f"\n  Executing node: {node_id} ({node_type.value})")
        
        node_state, llm_meta = await agent.execute_node(
            node_id=node_id,
            node_type=node_type,
            inputs={"prev_outputs": prev_outputs},
            metadata=metadata,
        )
        
        logger.info(f"    ✅ Completed in {node_state.metadata.get('execution_time_ms', 0):.0f}ms")
        logger.info(f"    Output keys: {list(node_state.outputs.keys())}")
        
        # Pass outputs to next node
        prev_outputs = node_state.outputs
    
    # Cleanup
    await agent.cleanup()
    
    logger.info("\n" + "=" * 70)
    logger.info("✅ Worker pattern demo completed!")
    logger.info("=" * 70)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "worker":
        # Run worker-pattern demo
        asyncio.run(demo_agent_with_worker_pattern())
    else:
        # Run basic agent demo
        asyncio.run(demo_agent_abstraction())
