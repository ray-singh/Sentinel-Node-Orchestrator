"""LangGraph checkpoint adapter for Sentinel integration."""

import json
import logging
from typing import Any, Dict, Optional, Sequence
from datetime import datetime

from langgraph.checkpoint.base import BaseCheckpointSaver, Checkpoint, CheckpointMetadata, CheckpointTuple
from langgraph.checkpoint.serde.base import SerializerProtocol

from .state import TaskCheckpoint, NodeState, NodeType, LLMCallMetadata

logger = logging.getLogger(__name__)


class SentinelCheckpointAdapter(BaseCheckpointSaver):
    """
    Adapter that bridges LangGraph's checkpoint system with Sentinel's TaskCheckpoint.
    
    This allows LangGraph agents to resume execution using checkpoints saved
    by the Sentinel worker system. Implements LangGraph's BaseCheckpointSaver
    interface while delegating storage to TaskCheckpoint objects.
    """
    
    def __init__(
        self,
        task_checkpoint: Optional[TaskCheckpoint] = None,
        serde: Optional[SerializerProtocol] = None,
    ):
        """
        Initialize adapter.
        
        Args:
            task_checkpoint: Existing TaskCheckpoint to resume from
            serde: Serializer for checkpoint data (optional)
        """
        super().__init__(serde=serde)
        self._task_checkpoint = task_checkpoint
        self._checkpoints: Dict[str, Checkpoint] = {}
        self._metadata: Dict[str, CheckpointMetadata] = {}
        
        # If we have an existing checkpoint, convert it to LangGraph format
        if task_checkpoint:
            self._load_from_task_checkpoint(task_checkpoint)
    
    def _load_from_task_checkpoint(self, task_checkpoint: TaskCheckpoint):
        """
        Convert TaskCheckpoint to LangGraph Checkpoint format.
        
        Args:
            task_checkpoint: Sentinel TaskCheckpoint to convert
        """
        # Build LangGraph state from node states
        channel_values = {}
        
        for node_id, node_state in task_checkpoint.node_states.items():
            # Store node outputs in channels
            channel_values[node_id] = {
                "outputs": node_state.outputs,
                "inputs": node_state.inputs,
                "metadata": node_state.metadata,
            }
        
        # Store current position in graph
        channel_values["__current_node__"] = task_checkpoint.current_node
        channel_values["__node_history__"] = task_checkpoint.node_history
        
        # Create LangGraph checkpoint
        checkpoint = Checkpoint(
            v=1,  # checkpoint schema version
            id=f"checkpoint_{task_checkpoint.task_id}_{task_checkpoint.attempts}",
            ts=task_checkpoint.updated_at.isoformat(),
            channel_values=channel_values,
            channel_versions={},  # Will be populated on save
            versions_seen={},
        )
        
        # Store in memory
        checkpoint_id = checkpoint["id"]
        self._checkpoints[checkpoint_id] = checkpoint
        
        # Create metadata
        metadata = CheckpointMetadata(
            source="sentinel_task_checkpoint",
            step=len(task_checkpoint.node_history),
            writes={},
            parents={},
        )
        self._metadata[checkpoint_id] = metadata
        
        logger.info(
            f"Loaded TaskCheckpoint into LangGraph format: "
            f"checkpoint_id={checkpoint_id}, nodes={len(task_checkpoint.node_states)}"
        )
    
    def to_task_checkpoint(
        self,
        task_id: str,
        checkpoint_id: str
    ) -> TaskCheckpoint:
        """
        Convert LangGraph Checkpoint back to TaskCheckpoint.
        
        Args:
            task_id: Task identifier
            checkpoint_id: LangGraph checkpoint ID
            
        Returns:
            TaskCheckpoint object
        """
        checkpoint = self._checkpoints.get(checkpoint_id)
        if not checkpoint:
            raise ValueError(f"Checkpoint {checkpoint_id} not found")
        
        channel_values = checkpoint["channel_values"]
        
        # Extract node states
        node_states = {}
        current_node = channel_values.get("__current_node__", "start")
        node_history = channel_values.get("__node_history__", ["start"])
        
        for node_id, node_data in channel_values.items():
            if node_id.startswith("__"):
                continue  # Skip internal keys
            
            # Reconstruct NodeState
            node_state = NodeState(
                node_id=node_id,
                node_type=NodeType.ANALYZE,  # Default, will be overridden
                inputs=node_data.get("inputs", {}),
                outputs=node_data.get("outputs", {}),
                metadata=node_data.get("metadata", {}),
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow(),
            )
            node_states[node_id] = node_state
        
        # Extract optional agent meta stored in checkpoint
        agent_meta = checkpoint.get("agent_meta", {}) if isinstance(checkpoint, dict) else {}

        # Create TaskCheckpoint
        task_checkpoint = TaskCheckpoint(
            task_id=task_id,
            current_node=current_node,
            node_history=node_history,
            node_states=node_states,
            llm_calls=[],  # Will be populated separately
            cost_so_far=0.0,
            attempts=1,
            checkpoint_version=str(checkpoint.get("v", "1.0")) if isinstance(checkpoint, dict) else "1.0",
            agent_type=agent_meta.get("agent_type", "langgraph"),
            agent_version=agent_meta.get("agent_version"),
            agent_schema_version=agent_meta.get("agent_schema_version"),
            agent_state=agent_meta.get("agent_state"),
            langgraph_checkpoint_id=checkpoint_id,
            langgraph_state=checkpoint,
        )
        
        logger.info(
            f"Converted LangGraph checkpoint to TaskCheckpoint: "
            f"task_id={task_id}, nodes={len(node_states)}"
        )
        
        return task_checkpoint
    
    def put(
        self,
        config: Dict[str, Any],
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Save checkpoint (LangGraph interface).
        
        Args:
            config: Configuration dict
            checkpoint: Checkpoint to save
            metadata: Checkpoint metadata
            new_versions: Version information
            
        Returns:
            Updated config
        """
        checkpoint_id = checkpoint["id"]
        # Persist checkpoint and attach any agent metadata present in config
        # Allow callers to pass agent metadata via config.configurable.agent_meta
        agent_meta = config.get("configurable", {}).get("agent_meta", {}) if isinstance(config, dict) else {}

        # store agent_meta on the checkpoint for round-trip conversion
        if isinstance(checkpoint, dict):
            checkpoint["agent_meta"] = agent_meta

        self._checkpoints[checkpoint_id] = checkpoint
        # store metadata and merge agent_meta into metadata if needed
        metadata_dict = metadata if isinstance(metadata, dict) else getattr(metadata, "__dict__", {})
        if agent_meta:
            try:
                metadata_dict["agent_meta"] = agent_meta
            except Exception:
                pass

        self._metadata[checkpoint_id] = metadata
        
        logger.debug(f"Saved checkpoint: {checkpoint_id}")
        
        return {
            "configurable": {
                "thread_id": config.get("configurable", {}).get("thread_id", "default"),
                "checkpoint_id": checkpoint_id,
            }
        }
    
    def put_writes(
        self,
        config: Dict[str, Any],
        writes: Sequence[tuple[str, Any]],
        task_id: str,
    ) -> None:
        """
        Save pending writes (LangGraph interface).
        
        Args:
            config: Configuration dict
            writes: Writes to save
            task_id: Task identifier
        """
        # Store writes for later application
        checkpoint_id = config.get("configurable", {}).get("checkpoint_id")
        if checkpoint_id and checkpoint_id in self._metadata:
            metadata = self._metadata[checkpoint_id]
            if not hasattr(metadata, "writes"):
                metadata["writes"] = {}
            for channel, value in writes:
                metadata["writes"][channel] = value
        
        logger.debug(f"Saved {len(writes)} writes for checkpoint")
    
    def get_tuple(self, config: Dict[str, Any]) -> Optional[CheckpointTuple]:
        """
        Get checkpoint tuple (LangGraph interface).
        
        Args:
            config: Configuration dict
            
        Returns:
            CheckpointTuple or None
        """
        checkpoint_id = config.get("configurable", {}).get("checkpoint_id")
        
        if not checkpoint_id or checkpoint_id not in self._checkpoints:
            # Return None if no checkpoint exists
            return None
        
        checkpoint = self._checkpoints[checkpoint_id]
        metadata = self._metadata.get(checkpoint_id, CheckpointMetadata(
            source="unknown",
            step=0,
            writes={},
            parents={},
        ))
        
        return CheckpointTuple(
            config=config,
            checkpoint=checkpoint,
            metadata=metadata,
            parent_config=None,
        )
    
    def list(
        self,
        config: Dict[str, Any],
        *,
        filter: Optional[Dict[str, Any]] = None,
        before: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
    ) -> list[CheckpointTuple]:
        """
        List checkpoints (LangGraph interface).
        
        Args:
            config: Configuration dict
            filter: Filter criteria
            before: Return checkpoints before this config
            limit: Maximum number to return
            
        Returns:
            List of CheckpointTuples
        """
        results = []
        
        for checkpoint_id, checkpoint in self._checkpoints.items():
            metadata = self._metadata.get(checkpoint_id, CheckpointMetadata(
                source="unknown",
                step=0,
                writes={},
                parents={},
            ))
            
            checkpoint_config = {
                "configurable": {
                    "thread_id": config.get("configurable", {}).get("thread_id", "default"),
                    "checkpoint_id": checkpoint_id,
                }
            }
            
            results.append(CheckpointTuple(
                config=checkpoint_config,
                checkpoint=checkpoint,
                metadata=metadata,
                parent_config=None,
            ))
        
        # Sort by timestamp (most recent first)
        results.sort(key=lambda x: x.checkpoint["ts"], reverse=True)
        
        if limit:
            results = results[:limit]
        
        return results
