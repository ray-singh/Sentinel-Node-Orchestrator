# LangGraph Integration

This document explains the LangGraph integration in Sentinel-Node-Orchestrator, enabling graph-based agent execution with checkpoint resumption.

## Overview

The LangGraph integration provides:
- **Graph-based agent execution** using LangGraph's StateGraph
- **Checkpoint adapter** bridging LangGraph's checkpoint system with Sentinel's TaskCheckpoint
- **Automatic resume** from any graph node after worker crashes
- **State versioning** for backward compatibility
- **Bidirectional conversion** between LangGraph and Sentinel state formats

## Architecture

```
┌─────────────────────┐
│   Worker / API      │
│                     │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  LangGraphAgent     │  ← Implements Agent interface
│                     │
│  - StateGraph       │  ← LangGraph graph definition
│  - Node functions   │  ← Async nodes (search, analyze, etc.)
│  - execute_node()   │  ← Executes graph with checkpoint
└──────────┬──────────┘
           │
           ▼
┌─────────────────────────────────────┐
│  SentinelCheckpointAdapter          │  ← Implements BaseCheckpointSaver
│                                     │
│  LangGraph Checkpoint ⇄ TaskCheckpoint│
│                                     │
│  - put()        - get_tuple()       │  ← LangGraph interface
│  - list()       - conversion logic  │
└──────────┬──────────────────────────┘
           │
           ▼
┌─────────────────────┐
│  Redis / Storage    │  ← Persisted checkpoints
└─────────────────────┘
```

## Components

### 1. SentinelCheckpointAdapter

**File:** `src/langgraph_adapter.py`

The adapter implements LangGraph's `BaseCheckpointSaver` interface and converts between:
- **LangGraph Checkpoint** → channel values, version, metadata
- **Sentinel TaskCheckpoint** → node states, current node, history, versioning

#### Key Methods

```python
class SentinelCheckpointAdapter(BaseCheckpointSaver):
    def put(self, config, checkpoint, metadata) -> RunnableConfig
        """Save a LangGraph checkpoint (called by LangGraph during execution)"""
    
    def get_tuple(self, config) -> Optional[CheckpointTuple]
        """Retrieve checkpoint for resumption"""
    
    def list(self, config, filter, before, limit) -> List[CheckpointTuple]
        """List checkpoints with filtering"""
    
    def to_task_checkpoint(self, task_id, checkpoint_id) -> TaskCheckpoint
        """Convert LangGraph checkpoint → TaskCheckpoint"""
    
    def _load_from_task_checkpoint(self, task_checkpoint: TaskCheckpoint)
        """Convert TaskCheckpoint → LangGraph checkpoint"""
```

#### State Mapping

**LangGraph → Sentinel:**
```python
# LangGraph stores state in channel_values
checkpoint = {
    "channel_values": {
        "search": {"results": [...]},      # Node outputs
        "analyze": {"analysis": "..."},
        "__current_node__": "analyze",      # Internal tracking
        "__node_history__": ["search"],
    },
    "version": "v1",
    "id": "checkpoint_123_0",
}

# Converted to Sentinel TaskCheckpoint
task_checkpoint = TaskCheckpoint(
    task_id="123",
    current_node="analyze",
    node_history=["search"],
    node_states={
        "search": NodeState(outputs={"results": [...]}),
        "analyze": NodeState(outputs={"analysis": "..."}),
    },
    checkpoint_version="1.0",
    agent_type="langgraph",
    langgraph_checkpoint_id="checkpoint_123_0",
    langgraph_state={...},  # Raw LangGraph state preserved
)
```

**Sentinel → LangGraph:**
The reverse conversion restores channel values from node states, enabling LangGraph to resume execution from the checkpointed state.

### 2. LangGraphAgent

**File:** `src/agent.py`

Implements the `Agent` interface using LangGraph's StateGraph.

#### Graph Structure

Default graph:
```
┌────────┐     ┌─────────┐     ┌───────────┐
│ search │ --> │ analyze │ --> │ summarize │ --> END
└────────┘     └─────────┘     └───────────┘
```

Each node is an async function that:
1. Receives state (inputs from previous nodes)
2. Calls LLM (via `llm_client.simple_prompt`)
3. Returns updated state (outputs)

#### Node Implementation Example

```python
async def _search_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
    """Search node - retrieves information."""
    query = state.get("query", "")
    
    prompt = f"Search for information about: {query}"
    response = await self._llm_client.simple_prompt(
        user_prompt=prompt,
        model="gpt-4o-mini",
    )
    
    return {
        "search_results": response,
        "query": query,
    }
```

#### Execution Flow

```python
# 1. Initialize agent
agent = LangGraphAgent(llm_client, checkpoint_adapter)
await agent.initialize(metadata)

# 2. Execute node with checkpointing
node_state, llm_meta = await agent.execute_node(
    node_id="search",
    node_type=NodeType.SEARCH,
    inputs={"query": "test"},
    metadata=metadata,
)

# 3. LangGraph:
#    - Executes graph node
#    - Calls checkpoint_adapter.put() automatically
#    - Saves state to checkpoint

# 4. Resume after crash
checkpoint_tuple = checkpoint_adapter.get_tuple(config)
# LangGraph resumes from last saved state
```

### 3. TaskCheckpoint Schema

**File:** `src/state.py`

Extended with versioning and agent-specific fields:

```python
class TaskCheckpoint(BaseModel):
    task_id: str
    current_node: str
    node_history: List[str]
    node_states: Dict[str, NodeState]
    
    # LangGraph-specific
    langgraph_checkpoint_id: Optional[str]
    langgraph_state: Dict[str, Any]
    
    # Versioning
    checkpoint_version: str = "1.0"       # Schema version
    agent_type: str = "prompt-based"      # Agent implementation type
    agent_state: Optional[Dict[str, Any]]  # Agent-specific data
    
    # Execution metadata
    attempts: int
    cost_so_far: float
    llm_calls: List[LLMCallMetadata]
    
    # Timestamps
    created_at: datetime
    updated_at: datetime
```

**Versioning Strategy:**
- `checkpoint_version`: Schema version for backward compatibility
- `agent_type`: Identifies which agent created the checkpoint
- `agent_state`: Opaque dict for agent-specific state

This allows:
- Migration between checkpoint schema versions
- Different agents (prompt-based, langgraph, custom) to coexist
- Agent-specific state without schema coupling

## Usage

### Basic Execution

```python
from src.agent import create_agent
from src.state import TaskMetadata, NodeType

# Create LangGraph agent
agent = create_agent("langgraph")

# Initialize with task metadata
await agent.initialize(metadata)

# Execute nodes
node_state, llm_meta = await agent.execute_node(
    node_id="search",
    node_type=NodeType.SEARCH,
    inputs={"query": "explain Redis"},
    metadata=metadata,
)

print(node_state.outputs["search_results"])
```

### With Checkpoint Resumption

```python
from src.langgraph_adapter import SentinelCheckpointAdapter

# Create adapter (can load existing TaskCheckpoint)
checkpoint_adapter = SentinelCheckpointAdapter(
    task_checkpoint=existing_checkpoint  # Optional
)

# Create agent with adapter
agent = create_agent("langgraph", checkpoint_adapter=checkpoint_adapter)
await agent.initialize(metadata)

# Execute - checkpoints saved automatically
node_state, _ = await agent.execute_node(...)

# Simulate crash
await agent.cleanup()

# Resume: create new agent with same adapter
agent2 = create_agent("langgraph", checkpoint_adapter=checkpoint_adapter)
await agent2.initialize(metadata)

# Continue from where it left off
node_state2, _ = await agent2.execute_node(...)
```

### Custom Graph Definition

```python
# Define custom graph structure
graph_definition = {
    "nodes": ["fetch", "process", "validate"],
    "edges": [
        ("fetch", "process"),
        ("process", "validate"),
    ],
    "node_functions": {
        "fetch": my_fetch_function,
        "process": my_process_function,
        "validate": my_validate_function,
    }
}

agent = create_agent("langgraph", graph_definition=graph_definition)
```

## Testing

Run the demo script:

```bash
# Test checkpoint adapter conversion
python examples/langgraph_demo.py adapter

# Test basic execution (requires OPENAI_API_KEY)
export OPENAI_API_KEY='your-key'
python examples/langgraph_demo.py basic

# Test checkpoint resumption
python examples/langgraph_demo.py checkpoint
```

## Integration with Worker

The worker already supports pluggable agents via the `Agent` interface. LangGraphAgent integrates seamlessly:

```python
# In worker_demo.py or src/worker.py
from src.agent import create_agent

# Worker creates agent based on task metadata
agent = create_agent(
    agent_type=metadata.task_params.get("agent_type", "prompt-based"),
    checkpoint_adapter=checkpoint_adapter,
)

# Worker calls execute_node - works with any Agent implementation
node_state, llm_meta = await agent.execute_node(
    node_id=current_node,
    node_type=node_type,
    inputs=inputs,
    metadata=metadata,
)

# Checkpoint saved automatically via adapter
```

## Benefits

### 1. Graph-Based Execution
- Complex multi-node workflows
- Conditional branching (can be added)
- Parallel node execution (can be added)
- Visual graph representation

### 2. Resumption
- Worker crashes don't lose progress
- Resume from exact node position
- State preserved across restarts
- Cost tracking continues accurately

### 3. Versioning
- Schema evolution support
- Multiple agent types coexist
- Backward compatibility
- Migration paths

### 4. Flexibility
- Custom graph definitions
- Pluggable node functions
- LLM model selection per node
- Agent-specific extensions

## Limitations & TODOs

### Current Limitations
1. **LLM metadata extraction**: Currently returns `None` for `llm_metadata` in `execute_node()`. Need to capture token usage and costs from graph execution.
2. **Custom graph building**: `_build_graph_from_definition()` falls back to default graph. Custom graph parsing not yet implemented.
3. **Conditional edges**: Not yet supported (LangGraph supports this).
4. **Parallel execution**: Sequential execution only.

### Planned Improvements
1. Extract LLM metadata from LangGraph execution context
2. Support custom graph definitions from config
3. Add conditional edges based on node outputs
4. Implement parallel node execution
5. Add graph visualization tools
6. Integration tests with worker crash/resume scenarios
7. Performance benchmarks vs prompt-based agent

## Comparison: LangGraph vs Prompt-Based Agent

| Feature | Prompt-Based Agent | LangGraph Agent |
|---------|-------------------|-----------------|
| **Execution** | Sequential LLM calls | Graph-based nodes |
| **State** | Simple dict | Channel values |
| **Resumption** | Node-level | Node-level + internal state |
| **Complexity** | Simple | Complex workflows |
| **LLM Calls** | Direct API | Via node functions |
| **Checkpointing** | Manual | Automatic (via adapter) |
| **Flexibility** | Limited | High (custom graphs) |
| **Overhead** | Low | Medium |
| **Best for** | Simple tasks | Multi-step reasoning |

## References

- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [LangGraph Checkpoints](https://langchain-ai.github.io/langgraph/concepts/persistence/)
- [Agent Abstraction](../src/agent.py)
- [Checkpoint Adapter](../src/langgraph_adapter.py)
- [Demo Scripts](../examples/langgraph_demo.py)

## Summary

The LangGraph integration extends Sentinel-Node-Orchestrator with sophisticated graph-based agent execution while maintaining the core checkpoint resumption capability. The checkpoint adapter bridges the two systems transparently, allowing workers to resume LangGraph execution from any node after crashes.

Key achievement: **Graph state ⇄ TaskCheckpoint conversion with full versioning support.**
