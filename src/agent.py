"""Agent abstraction layer for interchangeable agent implementations."""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from datetime import datetime

from .state import NodeType, NodeState, LLMCallMetadata, TaskMetadata
from .llm import get_llm_client, LLMClient

logger = logging.getLogger(__name__)


class Agent(ABC):
    """
    Abstract base class for agents.
    
    Workers use this interface to execute task nodes without knowing
    the specific agent implementation (prompt-based, LangGraph, custom, etc.).
    """
    
    @abstractmethod
    async def execute_node(
        self,
        node_id: str,
        node_type: NodeType,
        inputs: Dict[str, Any],
        metadata: TaskMetadata,
        effects: Optional[Any] = None,
    ) -> tuple[NodeState, Optional[LLMCallMetadata]]:
        """
        Execute a single node in the task graph.
        
        Args:
            node_id: Unique identifier for this node
            node_type: Type of node (SEARCH, ANALYZE, SUMMARIZE, etc.)
            inputs: Input data for the node
            metadata: Task metadata for context (tenant_id, params, etc.)
            
        Returns:
            Tuple of (NodeState with outputs, optional LLM metadata)
        """
        pass
    
    @abstractmethod
    async def initialize(self, metadata: TaskMetadata) -> None:
        """
        Initialize agent for a new task execution.
        
        Called once before executing any nodes. Use this to set up
        agent state, load models, configure prompt templates, etc.
        
        Args:
            metadata: Task metadata
        """
        pass
    
    @abstractmethod
    async def cleanup(self) -> None:
        """
        Clean up agent resources after task completion or failure.
        
        Called after all nodes complete or when task is cancelled.
        """
        pass
    
    @property
    @abstractmethod
    def agent_type(self) -> str:
        """Return the agent type identifier (e.g., 'prompt-based', 'langgraph')."""
        pass


class PromptBasedAgent(Agent):
    """
    Simple prompt-based agent that calls LLM with node-specific prompts.
    
    This is the default implementation that replaces the previous inline
    LLM calls in the worker. Each node type maps to a specific prompt template.
    """
    
    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        default_model: str = "gpt-4o-mini",
        temperature: float = 0.7,
        max_tokens: int = 500,
    ):
        """
        Initialize prompt-based agent.
        
        Args:
            llm_client: LLM client instance (or uses global client)
            default_model: Default model to use for LLM calls
            temperature: Sampling temperature
            max_tokens: Maximum tokens per response
        """
        self.llm_client = llm_client or get_llm_client()
        self.default_model = default_model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._task_context: Optional[Dict[str, Any]] = None
    
    async def initialize(self, metadata: TaskMetadata) -> None:
        """Store task context for use in prompts."""
        self._task_context = {
            "task_id": metadata.task_id,
            "task_type": metadata.task_type,
            "task_params": metadata.task_params,
            "tenant_id": metadata.tenant_id,
        }
        logger.info(f"Initialized PromptBasedAgent for task {metadata.task_id}")
    
    async def cleanup(self) -> None:
        """Clear task context."""
        self._task_context = None
        logger.info("Cleaned up PromptBasedAgent")
    
    @property
    def agent_type(self) -> str:
        return "prompt-based"
    
    async def execute_node(
        self,
        node_id: str,
        node_type: NodeType,
        inputs: Dict[str, Any],
        metadata: TaskMetadata,
        effects: Optional[Any] = None,
    ) -> tuple[NodeState, Optional[LLMCallMetadata]]:
        """Execute node using prompt-based LLM calls."""
        started_at = datetime.utcnow()
        
        # Check if this node requires LLM
        if node_type not in [NodeType.SEARCH, NodeType.ANALYZE, NodeType.SUMMARIZE]:
            # Non-LLM node - simulate simple computation
            outputs = {
                "result": f"Output from {node_id}",
                "data": [1, 2, 3],
            }
            
            node_state = NodeState(
                node_id=node_id,
                node_type=node_type,
                inputs=inputs,
                outputs=outputs,
                metadata={"execution_time_ms": 100},
                started_at=started_at,
                completed_at=datetime.utcnow(),
            )
            
            return node_state, None
        
        # LLM-based node - construct prompt and call LLM
        prompt, system = self._build_prompt(node_type, inputs, metadata)
        
        try:
            response, llm_metadata = await self.llm_client.simple_prompt(
                prompt=prompt,
                system=system,
                model=self.default_model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            
            outputs = {
                "llm_response": response,
                "processed": True,
                "node_type": node_type.value,
            }
            
            completed_at = datetime.utcnow()
            
            node_state = NodeState(
                node_id=node_id,
                node_type=node_type,
                inputs=inputs,
                outputs=outputs,
                metadata={
                    "execution_time_ms": (completed_at - started_at).total_seconds() * 1000,
                    "model": llm_metadata.model,
                    "tokens": llm_metadata.total_tokens,
                    "cost": llm_metadata.cost_usd,
                },
                started_at=started_at,
                completed_at=completed_at,
            )
            
            logger.info(
                f"Executed {node_type.value} node {node_id}: "
                f"tokens={llm_metadata.total_tokens}, cost=${llm_metadata.cost_usd:.6f}"
            )
            
            return node_state, llm_metadata
        
        except Exception as e:
            logger.error(f"LLM call failed for node {node_id}: {e}", exc_info=True)
            
            # Return error state
            completed_at = datetime.utcnow()
            
            node_state = NodeState(
                node_id=node_id,
                node_type=node_type,
                inputs=inputs,
                outputs={
                    "error": str(e),
                    "processed": False,
                },
                metadata={"execution_time_ms": (completed_at - started_at).total_seconds() * 1000},
                started_at=started_at,
                completed_at=completed_at,
            )
            
            return node_state, None
    
    def _build_prompt(
        self,
        node_type: NodeType,
        inputs: Dict[str, Any],
        metadata: TaskMetadata,
    ) -> tuple[str, str]:
        """
        Build prompt and system message for node type.
        
        Args:
            node_type: Type of node
            inputs: Input data
            metadata: Task metadata
            
        Returns:
            Tuple of (user_prompt, system_message)
        """
        prev_outputs = inputs.get("prev_outputs", {})
        query = metadata.task_params.get("query", "")
        
        if node_type == NodeType.SEARCH:
            system = "You are a research assistant that finds and extracts relevant information."
            prompt = f"Search and extract information about: {query or inputs.get('query', 'the given topic')}"
            
        elif node_type == NodeType.ANALYZE:
            system = "You are an analytical assistant that identifies patterns and insights."
            data = inputs.get("data", prev_outputs)
            prompt = f"Analyze the following data and provide insights:\n\n{data}"
            
        elif node_type == NodeType.SUMMARIZE:
            system = "You are a summarization assistant that creates concise summaries."
            data = inputs.get("data", prev_outputs)
            prompt = f"Summarize the following analysis:\n\n{data}"
            
        else:
            system = "You are a helpful assistant."
            prompt = f"Process this task: {inputs}"
        
        return prompt, system


class LangGraphAgent(Agent):
    """
    LangGraph-based agent with stateful graph execution and checkpointing.
    
    This agent uses LangGraph's graph execution engine to run complex,
    stateful agent workflows with built-in support for resuming from
    checkpoints via the SentinelCheckpointAdapter.
    """
    
    def __init__(
        self,
        graph_definition: Optional[Dict[str, Any]] = None,
        llm_client: Optional[LLMClient] = None,
        checkpoint_adapter: Optional[Any] = None,
    ):
        """
        Initialize LangGraph agent.
        
        Args:
            graph_definition: Graph configuration (nodes, edges, state schema)
            llm_client: LLM client for node execution
            checkpoint_adapter: SentinelCheckpointAdapter instance
        """
        self.graph_definition = graph_definition or {}
        self.llm_client = llm_client or get_llm_client()
        self.checkpoint_adapter = checkpoint_adapter
        self._graph = None
        self._app = None
        self._task_context: Optional[Dict[str, Any]] = None
    
    async def initialize(self, metadata: TaskMetadata) -> None:
        """Initialize LangGraph graph and build execution app."""
        from langgraph.graph import StateGraph, END
        from .langgraph_adapter import SentinelCheckpointAdapter
        
        logger.info(f"Initializing LangGraphAgent for task {metadata.task_id}")
        
        # Store task context
        self._task_context = {
            "task_id": metadata.task_id,
            "task_type": metadata.task_type,
            "task_params": metadata.task_params,
            "tenant_id": metadata.tenant_id,
        }
        
        # Build graph from definition or create default
        if self.graph_definition:
            self._graph = self._build_graph_from_definition(self.graph_definition)
        else:
            self._graph = self._build_default_graph()
        
        # Create checkpoint adapter if not provided
        if not self.checkpoint_adapter:
            self.checkpoint_adapter = SentinelCheckpointAdapter()
        
        # Compile graph into executable app
        self._app = self._graph.compile(checkpointer=self.checkpoint_adapter)
        
        logger.info(f"LangGraphAgent initialized with {len(self._graph.nodes)} nodes")
    
    def _build_default_graph(self):
        """Build a default research-style graph."""
        from langgraph.graph import StateGraph, END
        from typing import TypedDict
        
        # Define state schema
        class AgentState(TypedDict):
            query: str
            search_results: str
            analysis: str
            summary: str
            current_node: str
        
        # Create graph
        graph = StateGraph(AgentState)
        
        # Add nodes
        graph.add_node("search", self._search_node)
        graph.add_node("analyze", self._analyze_node)
        graph.add_node("summarize", self._summarize_node)
        
        # Add edges
        graph.set_entry_point("search")
        graph.add_edge("search", "analyze")
        graph.add_edge("analyze", "summarize")
        graph.add_edge("summarize", END)
        
        return graph
    
    def _build_graph_from_definition(self, definition: Dict[str, Any]):
        """Build graph from configuration dict."""
        from langgraph.graph import StateGraph, END

        # Expected definition format:
        # {
        #   "entry_point": "search",
        #   "nodes": [
        #       {"id": "search", "type": "search", "prompt": "Search: {query}"},
        #       {"id": "analyze", "type": "analyze", "prompt": "Analyze: {search_results}"},
        #   ],
        #   "edges": [["search", "analyze"], ["analyze", "summarize"]]
        # }

        NodeDef = definition.get("nodes", [])
        edges = definition.get("edges", [])
        entry = definition.get("entry_point")

        # Define a simple dynamic state schema as a dict-backed TypedDict substitute
        # LangGraph's StateGraph accepts a typing.TypedDict class; we use a minimal
        # dynamic approach by creating a simple TypedDict-like class via type().
        try:
            from typing import TypedDict

            class DynamicState(TypedDict, total=False):
                pass
        except Exception:
            DynamicState = dict

        graph = StateGraph(DynamicState)

        # Helper to make node functions
        def make_node_fn(node_cfg: Dict[str, Any]):
            node_type = node_cfg.get("type", "generic")
            prompt_template = node_cfg.get("prompt")

            async def node_fn(state: Dict[str, Any]):
                # Build prompt based on template or node type
                prompt = None
                system = None
                if prompt_template:
                    try:
                        prompt = prompt_template.format(**state)
                    except Exception:
                        prompt = str(prompt_template)
                else:
                    if node_type == "search":
                        system = "You are a research assistant that finds and extracts relevant information."
                        prompt = f"Search and extract information about: {state.get('query', '')}"
                    elif node_type == "analyze":
                        system = "You are an analytical assistant that identifies patterns and insights."
                        prompt = f"Analyze the following data and provide insights:\n\n{state.get('search_results', '')}"
                    elif node_type == "summarize":
                        system = "You are a summarization assistant that creates concise summaries."
                        prompt = f"Summarize the following analysis:\n\n{state.get('analysis', '')}"
                    else:
                        prompt = str(node_cfg.get("prompt", f"Process node {node_cfg.get('id')}"))

                # If this node is non-LLM (type may be start/complete), return minimal state
                if node_type in ["start", "complete"]:
                    return {"current_node": node_cfg.get("id")}

                # Call LLM and capture metadata
                try:
                    response, metadata = await self.llm_client.simple_prompt(
                        prompt=prompt,
                        system=system,
                        max_tokens=node_cfg.get("max_tokens", 300),
                    )
                except Exception as e:
                    # propagate error to graph
                    raise

                # Map outputs into state keys if provided
                out_key = node_cfg.get("output_key") or ("search_results" if node_type == "search" else ("analysis" if node_type == "analyze" else "summary"))

                # Attach LLM metadata alongside output for later extraction
                state[out_key] = response
                # store metadata list
                llm_calls = state.get("_llm_calls", [])
                if metadata is not None:
                    # convert Pydantic model to dict if needed
                    try:
                        llm_calls.append(metadata.model_dump())
                    except Exception:
                        # fallback if it's already a dict
                        llm_calls.append(metadata)
                state["_llm_calls"] = llm_calls

                state["current_node"] = node_cfg.get("id")
                return state

            return node_fn

        # Add nodes to graph
        node_map = {}
        for n in NodeDef:
            node_id = n.get("id")
            if not node_id:
                continue
            fn = make_node_fn(n)
            graph.add_node(node_id, fn)
            node_map[node_id] = n

        # Wire edges
        if entry:
            try:
                graph.set_entry_point(entry)
            except Exception:
                pass

        for a, b in edges:
            try:
                graph.add_edge(a, b)
            except Exception:
                pass

        # If no entry set, default to 'start' if present
        if not entry:
            if "start" in node_map:
                graph.set_entry_point("start")

        return graph
    
    async def _search_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Search node implementation."""
        query = state.get("query", self._task_context.get("task_params", {}).get("query", ""))
        
        response, metadata = await self.llm_client.simple_prompt(
            prompt=f"Search and extract information about: {query}",
            system="You are a research assistant that finds and extracts relevant information.",
            max_tokens=300,
        )
        
        return {
            "search_results": response,
            "current_node": "search",
        }
    
    async def _analyze_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze node implementation."""
        search_results = state.get("search_results", "")
        
        response, metadata = await self.llm_client.simple_prompt(
            prompt=f"Analyze the following data and provide insights:\n\n{search_results}",
            system="You are an analytical assistant that identifies patterns and insights.",
            max_tokens=300,
        )
        
        return {
            "analysis": response,
            "current_node": "analyze",
        }
    
    async def _summarize_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Summarize node implementation."""
        analysis = state.get("analysis", "")
        
        response, metadata = await self.llm_client.simple_prompt(
            prompt=f"Summarize the following analysis:\n\n{analysis}",
            system="You are a summarization assistant that creates concise summaries.",
            max_tokens=200,
        )
        
        return {
            "summary": response,
            "current_node": "summarize",
        }
    
    async def cleanup(self) -> None:
        """Clean up LangGraph resources."""
        self._graph = None
        self._app = None
        self._task_context = None
        logger.info("Cleaned up LangGraphAgent")
    
    @property
    def agent_type(self) -> str:
        return "langgraph"
    
    async def execute_node(
        self,
        node_id: str,
        node_type: NodeType,
        inputs: Dict[str, Any],
        metadata: TaskMetadata,
        effects: Optional[Any] = None,
    ) -> tuple[NodeState, Optional[LLMCallMetadata]]:
        """
        Execute node via LangGraph graph.
        
        This method integrates with the worker's node execution loop by
        invoking the LangGraph app and extracting results.
        """
        started_at = datetime.utcnow()
        
        if not self._app:
            raise RuntimeError("LangGraphAgent not initialized. Call initialize() first.")
        
        # Build initial state
        initial_state = {
            "query": metadata.task_params.get("query", ""),
            "current_node": node_id,
            **inputs.get("prev_outputs", {}),
        }
        
        # Configure thread for checkpointing
        config = {
            "configurable": {
                "thread_id": metadata.task_id,
                "checkpoint_id": f"checkpoint_{metadata.task_id}_{node_id}",
            }
        }
        
        try:
            # Invoke graph (async)
            # For single node execution, we invoke and extract just this node's output
            result = await self._app.ainvoke(initial_state, config=config)
            
            # Extract outputs
            outputs = {
                "search_results": result.get("search_results", ""),
                "analysis": result.get("analysis", ""),
                "summary": result.get("summary", ""),
                "current_node": result.get("current_node", node_id),
            }
            
            completed_at = datetime.utcnow()
            
            # Create node state
            node_state = NodeState(
                node_id=node_id,
                node_type=node_type,
                inputs=inputs,
                outputs=outputs,
                metadata={
                    "execution_time_ms": (completed_at - started_at).total_seconds() * 1000,
                    "langgraph": True,
                },
                started_at=started_at,
                completed_at=completed_at,
            )
            # Extract LLM metadata from graph execution if present
            llm_metadata = None
            try:
                llm_calls = result.get("_llm_calls") or result.get("llm_calls")
                if llm_calls and isinstance(llm_calls, list):
                    # Attach raw llm_calls to node metadata for the worker to persist
                    node_state.metadata["llm_calls"] = llm_calls

                    # Use the last call as representative for return value
                    last = llm_calls[-1]
                    if isinstance(last, dict):
                        try:
                            llm_metadata = LLMCallMetadata.model_validate(last)
                        except Exception:
                            # Best-effort construction
                            llm_metadata = LLMCallMetadata(
                                model=last.get("model", self.llm_client.default_model),
                                prompt_tokens=int(last.get("prompt_tokens", 0) or 0),
                                completion_tokens=int(last.get("completion_tokens", 0) or 0),
                                total_tokens=int(last.get("total_tokens", 0) or 0),
                                cost_usd=float(last.get("cost_usd", 0.0) or 0.0),
                                latency_ms=float(last.get("latency_ms", 0.0) or 0.0),
                            )
                    elif isinstance(last, LLMCallMetadata):
                        llm_metadata = last
            except Exception:
                llm_metadata = None
            
            logger.info(f"Executed LangGraph node {node_id}: outputs={list(outputs.keys())}")
            
            return node_state, llm_metadata
        
        except Exception as e:
            logger.error(f"LangGraph node execution failed for {node_id}: {e}", exc_info=True)
            
            completed_at = datetime.utcnow()
            
            # Return error state
            node_state = NodeState(
                node_id=node_id,
                node_type=node_type,
                inputs=inputs,
                outputs={
                    "error": str(e),
                    "processed": False,
                },
                metadata={"execution_time_ms": (completed_at - started_at).total_seconds() * 1000},
                started_at=started_at,
                completed_at=completed_at,
            )
            
            return node_state, None


# Agent registry
_AGENT_REGISTRY: Dict[str, type[Agent]] = {
    "prompt-based": PromptBasedAgent,
    "langgraph": LangGraphAgent,
}


def create_agent(agent_type: str = "prompt-based", **kwargs) -> Agent:
    """
    Factory function to create agent instances.
    
    Args:
        agent_type: Type of agent to create ('prompt-based', 'langgraph', etc.)
        **kwargs: Agent-specific configuration
        
    Returns:
        Agent instance
        
    Raises:
        ValueError: If agent_type is not registered
    """
    agent_class = _AGENT_REGISTRY.get(agent_type)
    
    if not agent_class:
        raise ValueError(
            f"Unknown agent type: {agent_type}. "
            f"Available types: {list(_AGENT_REGISTRY.keys())}"
        )
    
    return agent_class(**kwargs)


def register_agent(agent_type: str, agent_class: type[Agent]) -> None:
    """
    Register a custom agent implementation.
    
    Args:
        agent_type: Unique identifier for the agent type
        agent_class: Agent class (must inherit from Agent)
    """
    if not issubclass(agent_class, Agent):
        raise TypeError(f"{agent_class} must inherit from Agent")
    
    _AGENT_REGISTRY[agent_type] = agent_class
    logger.info(f"Registered agent type: {agent_type}")
