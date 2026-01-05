"""State schema definitions for task execution and checkpointing."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """Task lifecycle states."""
    QUEUED = "queued"
    LEASED = "leased"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


class NodeType(str, Enum):
    """LangGraph node types."""
    START = "start"
    SEARCH = "search"
    ANALYZE = "analyze"
    SUMMARIZE = "summarize"
    COMPLETE = "complete"


class LLMCallMetadata(BaseModel):
    """Metadata for a single LLM call."""
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    latency_ms: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class NodeState(BaseModel):
    """State for a single node in the agent graph."""
    node_id: str
    node_type: NodeType
    inputs: Dict[str, Any] = Field(default_factory=dict)
    outputs: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None


class TaskCheckpoint(BaseModel):
    """Complete checkpoint state for resuming a task."""
    task_id: str
    current_node: str
    node_history: List[str] = Field(default_factory=list)
    node_states: Dict[str, NodeState] = Field(default_factory=dict)
    
    # LangGraph-specific state
    langgraph_checkpoint_id: Optional[str] = None
    langgraph_state: Dict[str, Any] = Field(default_factory=dict)
    
    # Execution metadata
    attempts: int = 0
    cost_so_far: float = 0.0
    llm_calls: List[LLMCallMetadata] = Field(default_factory=list)
    
    # Artifacts (external references)
    artifact_refs: Dict[str, str] = Field(default_factory=dict)  # key -> S3/MinIO URI
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_heartbeat: Optional[datetime] = None
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }


class TaskMetadata(BaseModel):
    """Task metadata stored in Redis hash."""
    task_id: str
    status: TaskStatus
    tenant_id: str
    
    # Ownership and leasing
    owner: Optional[str] = None  # worker_id
    lease_expires: Optional[datetime] = None
    
    # Progress tracking
    current_node: Optional[str] = None
    attempts: int = 0
    max_attempts: int = 3
    
    # Cost and rate limiting
    cost_so_far: float = 0.0
    cost_limit: Optional[float] = None
    
    # Task definition
    task_type: str
    task_params: Dict[str, Any] = Field(default_factory=dict)
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    
    # Results
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }


class WorkerHeartbeat(BaseModel):
    """Worker heartbeat data."""
    worker_id: str
    pid: int
    version: str
    current_task: Optional[str] = None
    hostname: str
    started_at: datetime
    last_beat: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }


class RateLimitBucket(BaseModel):
    """Token bucket state for rate limiting."""
    tenant_id: str
    tokens: float
    capacity: float
    refill_rate: float  # tokens per second
    last_refill: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }


class CostEvent(BaseModel):
    """Cost tracking event."""
    task_id: str
    tenant_id: str
    llm_model: str
    cost_usd: float
    tokens_used: int
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }
