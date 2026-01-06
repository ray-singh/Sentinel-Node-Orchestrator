"""FastAPI controller for task submission and management."""

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import redis.asyncio as redis

from .config import settings
from .redis_saver import RedisCheckpointSaver
from .state import TaskMetadata, TaskStatus

logger = logging.getLogger(__name__)


# Request/Response models
class CreateTaskRequest(BaseModel):
    """Request to create a new task."""
    task_type: str = Field(..., description="Type of task to execute")
    task_params: Dict[str, Any] = Field(default_factory=dict, description="Task parameters")
    tenant_id: str = Field(..., description="Tenant identifier for cost tracking")
    cost_limit: Optional[float] = Field(None, description="Maximum cost in USD")
    max_attempts: int = Field(3, description="Maximum retry attempts")


class TaskResponse(BaseModel):
    """Response containing task information."""
    task_id: str
    status: str
    tenant_id: str
    task_type: str
    task_params: Dict[str, Any]
    cost_so_far: float
    attempts: int
    max_attempts: int
    owner: Optional[str] = None
    created_at: str
    updated_at: str
    completed_at: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class TaskListResponse(BaseModel):
    """Response containing list of tasks."""
    tasks: List[TaskResponse]
    total: int


class TaskStatsResponse(BaseModel):
    """Response containing task statistics."""
    total_tasks: int
    queued: int
    leased: int
    in_progress: int
    completed: int
    failed: int
    retrying: int


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    redis_connected: bool
    timestamp: str


# FastAPI app
app = FastAPI(
    title="Sentinel Node Orchestrator API",
    description="Fault-tolerant AI agent orchestration system",
    version="0.1.0",
)

# Global state
redis_client: Optional[redis.Redis] = None
saver: Optional[RedisCheckpointSaver] = None


@app.on_event("startup")
async def startup_event():
    """Initialize Redis connection on startup."""
    global redis_client, saver
    
    logger.info("Starting FastAPI controller...")
    redis_client = await redis.from_url(settings.redis_url, decode_responses=False)
    saver = RedisCheckpointSaver(redis_client)
    logger.info("FastAPI controller started successfully")


@app.on_event("shutdown")
async def shutdown_event():
    """Close Redis connection on shutdown."""
    global redis_client
    
    logger.info("Shutting down FastAPI controller...")
    if redis_client:
        await redis_client.aclose()
    logger.info("FastAPI controller shut down")


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    redis_connected = False
    
    if redis_client:
        try:
            await redis_client.ping()
            redis_connected = True
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
    
    return HealthResponse(
        status="healthy" if redis_connected else "unhealthy",
        redis_connected=redis_connected,
        timestamp=datetime.utcnow().isoformat(),
    )


@app.post("/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(request: CreateTaskRequest):
    """
    Create and submit a new task.
    
    The task will be queued and picked up by an available worker.
    """
    # Generate unique task ID
    task_id = f"task_{uuid.uuid4().hex[:12]}"
    
    # Create task metadata
    metadata = TaskMetadata(
        task_id=task_id,
        status=TaskStatus.QUEUED,
        tenant_id=request.tenant_id,
        task_type=request.task_type,
        task_params=request.task_params,
        cost_limit=request.cost_limit or settings.default_cost_limit,
        max_attempts=request.max_attempts,
    )
    
    # Save to Redis
    await saver.save_task_metadata(metadata)
    
    logger.info(f"Created task {task_id} for tenant {request.tenant_id}")
    
    return _metadata_to_response(metadata)


@app.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str):
    """Get task details by ID."""
    metadata = await saver.load_task_metadata(task_id)
    
    if not metadata:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found"
        )
    
    return _metadata_to_response(metadata)


@app.get("/tasks", response_model=TaskListResponse)
async def list_tasks(
    status_filter: Optional[str] = None,
    tenant_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
):
    """
    List tasks with optional filtering.
    
    Args:
        status_filter: Filter by task status (queued, leased, completed, failed, etc.)
        tenant_id: Filter by tenant ID
        limit: Maximum number of tasks to return
        offset: Number of tasks to skip
    """
    tasks = []
    
    # Scan for all task metadata
    cursor = 0
    while True:
        cursor, keys = await redis_client.scan(
            cursor,
            match="task:*:meta",
            count=100
        )
        
        for key in keys:
            task_id = key.decode().split(":")[1]
            metadata = await saver.load_task_metadata(task_id)
            
            if metadata:
                # Apply filters
                if status_filter and metadata.status.value != status_filter:
                    continue
                if tenant_id and metadata.tenant_id != tenant_id:
                    continue
                
                tasks.append(_metadata_to_response(metadata))
        
        if cursor == 0:
            break
    
    # Sort by created_at descending
    tasks.sort(key=lambda t: t.created_at, reverse=True)
    
    # Apply pagination
    total = len(tasks)
    tasks = tasks[offset:offset + limit]
    
    return TaskListResponse(tasks=tasks, total=total)


@app.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_task(task_id: str):
    """
    Cancel a task.
    
    Only tasks in queued or leased status can be cancelled.
    """
    metadata = await saver.load_task_metadata(task_id)
    
    if not metadata:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found"
        )
    
    if metadata.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel task in {metadata.status.value} status"
        )
    
    # Release task and mark as failed
    await saver.release_task(task_id, TaskStatus.FAILED)
    
    # Update metadata
    metadata.status = TaskStatus.FAILED
    metadata.error = "Cancelled by user"
    metadata.completed_at = datetime.utcnow()
    await saver.save_task_metadata(metadata)
    
    logger.info(f"Cancelled task {task_id}")
    
    return None


@app.get("/stats", response_model=TaskStatsResponse)
async def get_stats():
    """Get task statistics across all statuses."""
    stats = {
        "total_tasks": 0,
        "queued": 0,
        "leased": 0,
        "in_progress": 0,
        "completed": 0,
        "failed": 0,
        "retrying": 0,
    }
    
    # Scan all tasks
    cursor = 0
    while True:
        cursor, keys = await redis_client.scan(
            cursor,
            match="task:*:meta",
            count=100
        )
        
        for key in keys:
            task_id = key.decode().split(":")[1]
            metadata = await saver.load_task_metadata(task_id)
            
            if metadata:
                stats["total_tasks"] += 1
                status_key = metadata.status.value.lower().replace("-", "_")
                if status_key in stats:
                    stats[status_key] += 1
        
        if cursor == 0:
            break
    
    return TaskStatsResponse(**stats)


@app.get("/tenants/{tenant_id}/costs")
async def get_tenant_costs(tenant_id: str):
    """
    Get cost summary for a tenant.
    
    Returns total costs across all tasks.
    """
    total_cost = 0.0
    task_count = 0
    
    # Scan all tasks for this tenant
    cursor = 0
    while True:
        cursor, keys = await redis_client.scan(
            cursor,
            match="task:*:meta",
            count=100
        )
        
        for key in keys:
            task_id = key.decode().split(":")[1]
            metadata = await saver.load_task_metadata(task_id)
            
            if metadata and metadata.tenant_id == tenant_id:
                task_count += 1
                total_cost += metadata.cost_so_far
        
        if cursor == 0:
            break
    
    return {
        "tenant_id": tenant_id,
        "total_cost_usd": round(total_cost, 4),
        "task_count": task_count,
        "average_cost_usd": round(total_cost / task_count, 4) if task_count > 0 else 0.0,
    }


def _metadata_to_response(metadata: TaskMetadata) -> TaskResponse:
    """Convert TaskMetadata to TaskResponse."""
    return TaskResponse(
        task_id=metadata.task_id,
        status=metadata.status.value,
        tenant_id=metadata.tenant_id,
        task_type=metadata.task_type,
        task_params=metadata.task_params,
        cost_so_far=metadata.cost_so_far,
        attempts=metadata.attempts,
        max_attempts=metadata.max_attempts,
        owner=metadata.owner,
        created_at=metadata.created_at.isoformat(),
        updated_at=metadata.updated_at.isoformat(),
        completed_at=metadata.completed_at.isoformat() if metadata.completed_at else None,
        result=metadata.result,
        error=metadata.error,
    )


if __name__ == "__main__":
    import uvicorn
    
    # Setup logging
    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Run server
    uvicorn.run(
        "src.api:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level=settings.log_level.lower(),
    )
