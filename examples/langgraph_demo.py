"""Demo of LangGraphAgent with checkpoint resumption."""

import asyncio
import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agent import create_agent
from src.state import TaskMetadata, NodeType
from src.langgraph_adapter import SentinelCheckpointAdapter
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def demo_langgraph_basic():
    """Demonstrate basic LangGraph agent execution."""
    logger.info("=" * 70)
    logger.info("LangGraph Agent Basic Demo")
    logger.info("=" * 70)
    
    # Create task metadata
    metadata = TaskMetadata(
        task_id="langgraph-demo-1",
        tenant_id="tenant-test",
        task_type="research",
        task_params={"query": "What are the benefits of distributed checkpointing?"},
        status="queued",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    
    # Create LangGraph agent
    logger.info("\n🤖 Creating LangGraphAgent...")
    agent = create_agent("langgraph")
    
    # Initialize agent
    await agent.initialize(metadata)
    
    logger.info(f"  Agent type: {agent.agent_type}")
    logger.info(f"  Graph nodes: {len(agent._graph.nodes) if agent._graph else 'N/A'}")
    
    # Execute nodes in sequence
    node_sequence = [
        ("search", NodeType.SEARCH),
        ("analyze", NodeType.ANALYZE),
        ("summarize", NodeType.SUMMARIZE),
    ]
    
    prev_outputs = {}
    
    for node_id, node_type in node_sequence:
        logger.info(f"\n  Executing node: {node_id}")
        
        node_state, llm_meta = await agent.execute_node(
            node_id=node_id,
            node_type=node_type,
            inputs={"prev_outputs": prev_outputs},
            metadata=metadata,
        )
        
        logger.info(f"    ✅ Completed")
        logger.info(f"    Output keys: {list(node_state.outputs.keys())}")
        
        # Show first 100 chars of key outputs
        for key in ["search_results", "analysis", "summary"]:
            if key in node_state.outputs and node_state.outputs[key]:
                value = str(node_state.outputs[key])[:100]
                logger.info(f"    {key}: {value}...")
        
        prev_outputs = node_state.outputs
    
    # Cleanup
    await agent.cleanup()
    
    logger.info("\n" + "=" * 70)
    logger.info("✅ LangGraph basic demo completed!")
    logger.info("=" * 70)


async def demo_langgraph_checkpoint():
    """Demonstrate LangGraph agent with checkpoint resumption."""
    logger.info("=" * 70)
    logger.info("LangGraph Checkpoint Resumption Demo")
    logger.info("=" * 70)
    
    # Create task metadata
    metadata = TaskMetadata(
        task_id="langgraph-demo-2",
        tenant_id="tenant-test",
        task_type="research",
        task_params={"query": "Explain Redis persistence strategies"},
        status="queued",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    
    # Scenario: Execute first node, save checkpoint, then resume
    logger.info("\n📍 Phase 1: Execute search node and checkpoint")
    
    # Create agent with checkpoint adapter
    checkpoint_adapter = SentinelCheckpointAdapter()
    agent = create_agent("langgraph", checkpoint_adapter=checkpoint_adapter)
    
    await agent.initialize(metadata)
    
    # Execute search node
    node_state, llm_meta = await agent.execute_node(
        node_id="search",
        node_type=NodeType.SEARCH,
        inputs={"prev_outputs": {}},
        metadata=metadata,
    )
    
    logger.info(f"  ✅ Search completed")
    logger.info(f"  Checkpoint ID: {checkpoint_adapter._checkpoints.keys()}")
    
    # Simulate crash/cleanup
    await agent.cleanup()
    logger.info("  💥 Simulated worker crash!")
    
    # Phase 2: Resume from checkpoint
    logger.info("\n📍 Phase 2: Resume from checkpoint")
    
    # Create new agent with same checkpoint adapter
    agent2 = create_agent("langgraph", checkpoint_adapter=checkpoint_adapter)
    await agent2.initialize(metadata)
    
    logger.info(f"  ✅ Agent resumed with {len(checkpoint_adapter._checkpoints)} checkpoints")
    
    # Continue execution from analyze node
    node_state2, llm_meta2 = await agent2.execute_node(
        node_id="analyze",
        node_type=NodeType.ANALYZE,
        inputs={"prev_outputs": node_state.outputs},
        metadata=metadata,
    )
    
    logger.info(f"  ✅ Analysis completed after resume")
    
    # Final node
    node_state3, llm_meta3 = await agent2.execute_node(
        node_id="summarize",
        node_type=NodeType.SUMMARIZE,
        inputs={"prev_outputs": node_state2.outputs},
        metadata=metadata,
    )
    
    logger.info(f"  ✅ Summary completed")
    
    if "summary" in node_state3.outputs:
        summary = str(node_state3.outputs["summary"])[:200]
        logger.info(f"\n  Final summary: {summary}...")
    
    await agent2.cleanup()
    
    logger.info("\n" + "=" * 70)
    logger.info("✅ Checkpoint resumption demo completed!")
    logger.info("=" * 70)


async def demo_langgraph_adapter():
    """Demonstrate checkpoint adapter conversions."""
    logger.info("=" * 70)
    logger.info("LangGraph Adapter Demo")
    logger.info("=" * 70)
    
    from src.state import TaskCheckpoint, NodeState
    
    # Create a TaskCheckpoint
    logger.info("\n📦 Creating TaskCheckpoint...")
    
    task_checkpoint = TaskCheckpoint(
        task_id="test-123",
        current_node="analyze",
        node_history=["start", "search"],
        node_states={
            "search": NodeState(
                node_id="search",
                node_type=NodeType.SEARCH,
                inputs={"query": "test"},
                outputs={"results": ["result1", "result2"]},
                metadata={},
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow(),
            ),
        },
        checkpoint_version="1.0",
        agent_type="langgraph",
    )
    
    logger.info(f"  Task ID: {task_checkpoint.task_id}")
    logger.info(f"  Current node: {task_checkpoint.current_node}")
    logger.info(f"  Node states: {len(task_checkpoint.node_states)}")
    
    # Convert to LangGraph checkpoint
    logger.info("\n🔄 Converting to LangGraph format...")
    
    adapter = SentinelCheckpointAdapter(task_checkpoint=task_checkpoint)
    
    logger.info(f"  Checkpoints loaded: {len(adapter._checkpoints)}")
    
    # Get checkpoint tuple
    config = {
        "configurable": {
            "thread_id": task_checkpoint.task_id,
            "checkpoint_id": list(adapter._checkpoints.keys())[0] if adapter._checkpoints else None,
        }
    }
    
    checkpoint_tuple = adapter.get_tuple(config)
    
    if checkpoint_tuple:
        logger.info(f"  ✅ Retrieved checkpoint: {checkpoint_tuple.checkpoint['id']}")
        logger.info(f"  Channels: {list(checkpoint_tuple.checkpoint['channel_values'].keys())}")
    
    # Convert back to TaskCheckpoint
    logger.info("\n🔄 Converting back to TaskCheckpoint...")
    
    if checkpoint_tuple:
        new_task_checkpoint = adapter.to_task_checkpoint(
            task_id=task_checkpoint.task_id,
            checkpoint_id=checkpoint_tuple.checkpoint["id"],
        )
        
        logger.info(f"  ✅ Converted back")
        logger.info(f"  Task ID: {new_task_checkpoint.task_id}")
        logger.info(f"  Current node: {new_task_checkpoint.current_node}")
        logger.info(f"  Node history: {new_task_checkpoint.node_history}")
        logger.info(f"  Agent type: {new_task_checkpoint.agent_type}")
    
    logger.info("\n" + "=" * 70)
    logger.info("✅ Adapter demo completed!")
    logger.info("=" * 70)


if __name__ == "__main__":
    import os
    
    # Check for OpenAI API key
    if not os.getenv("OPENAI_API_KEY"):
        logger.warning("⚠️  OPENAI_API_KEY not set - LLM calls will fail")
        logger.info("   Set it with: export OPENAI_API_KEY='your-key-here'")
        logger.info("   Running adapter demo only...\n")
        asyncio.run(demo_langgraph_adapter())
    else:
        if len(sys.argv) > 1:
            demo_type = sys.argv[1]
            
            if demo_type == "basic":
                asyncio.run(demo_langgraph_basic())
            elif demo_type == "checkpoint":
                asyncio.run(demo_langgraph_checkpoint())
            elif demo_type == "adapter":
                asyncio.run(demo_langgraph_adapter())
            else:
                print(f"Unknown demo type: {demo_type}")
                print("Available: basic, checkpoint, adapter")
        else:
            # Run all demos
            asyncio.run(demo_langgraph_adapter())
            print("\n")
            asyncio.run(demo_langgraph_basic())
            print("\n")
            asyncio.run(demo_langgraph_checkpoint())
