"""Prometheus metrics for Sentinel Node Orchestrator.

Exports counters and histograms used across the system.
Starts an HTTP server on `settings.prometheus_port` when `start()` is called.
"""
from prometheus_client import Counter, Histogram, Gauge, start_http_server
from .config import settings
import logging

logger = logging.getLogger(__name__)


# Task lifecycle (with labels)
TASKS_STARTED = Counter(
    "sentinel_tasks_started_total", 
    "Total tasks started",
    ["tenant_id", "agent_type", "task_type"]
)
TASKS_COMPLETED = Counter(
    "sentinel_tasks_completed_total", 
    "Total tasks completed successfully",
    ["tenant_id", "agent_type", "task_type"]
)
TASKS_FAILED = Counter(
    "sentinel_tasks_failed_total", 
    "Total tasks failed",
    ["tenant_id", "agent_type", "task_type"]
)
TASK_DURATION = Histogram(
    "sentinel_task_duration_seconds",
    "Task execution duration in seconds",
    ["tenant_id", "agent_type", "task_type"]
)

# LLM calls (with labels)
LLM_CALLS = Counter(
    "sentinel_llm_calls_total", 
    "Total LLM calls made",
    ["model", "tenant_id", "node_type"]
)
LLM_TOKENS = Counter(
    "sentinel_llm_tokens_total", 
    "Total LLM tokens consumed",
    ["model", "tenant_id", "token_type"]  # token_type: prompt, completion
)
LLM_LATENCY = Histogram(
    "sentinel_llm_latency_seconds", 
    "LLM call latency in seconds",
    ["model", "tenant_id"]
)
LLM_COST = Counter(
    "sentinel_llm_cost_usd_total",
    "Total LLM cost in USD",
    ["model", "tenant_id"]
)

# Node execution
NODE_EXECUTIONS = Counter(
    "sentinel_node_executions_total",
    "Total node executions",
    ["node_type", "status"]  # status: success, error
)
NODE_DURATION = Histogram(
    "sentinel_node_duration_seconds",
    "Node execution duration in seconds",
    ["node_type"]
)

# Requeues and rate limits
REQUEUES = Counter(
    "sentinel_requeues_total", 
    "Total task requeues due to lease expiry or failures",
    ["reason"]  # reason: lease_expired, worker_crash, error
)
RATE_LIMIT_HITS = Counter(
    "sentinel_rate_limit_hits_total", 
    "Total rate limit hits",
    ["tenant_id"]
)
RATE_LIMIT_TOKENS = Gauge(
    "sentinel_rate_limit_tokens_remaining",
    "Current tokens remaining in rate limit bucket",
    ["tenant_id"]
)

# Checkpoints
CHECKPOINTS_SAVED = Counter(
    "sentinel_checkpoints_saved_total", 
    "Total checkpoints saved",
    ["task_id"]
)
CHECKPOINTS_RESTORED = Counter(
    "sentinel_checkpoints_restored_total", 
    "Total checkpoints restored",
    ["task_id"]
)
CHECKPOINT_SIZE_BYTES = Histogram(
    "sentinel_checkpoint_size_bytes",
    "Checkpoint size in bytes",
    ["task_id"]
)

# Workers
WORKER_HEARTBEATS = Counter(
    "sentinel_worker_heartbeats_total",
    "Total worker heartbeats sent",
    ["worker_id"]
)
ACTIVE_WORKERS = Gauge(
    "sentinel_active_workers",
    "Number of active workers"
)
WORKER_TASKS = Gauge(
    "sentinel_worker_current_tasks",
    "Current tasks being processed by workers",
    ["worker_id"]
)


def start(prometheus_port: int = 8001):
    try:
        start_http_server(prometheus_port)
        logger.info(f"Prometheus metrics server started on :{prometheus_port}")
    except Exception as e:
        logger.exception(f"Failed to start Prometheus server: {e}")
