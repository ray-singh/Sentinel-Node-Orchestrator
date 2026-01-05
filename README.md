# Sentinel-Node-Orchestrator

High-availability, distributed AI agent orchestration system designed to solve the reliability gap in production LLM workflows.

AI agents in production face a critical reliability gap: when a container crashes mid-task, the work is lost. Sentinel solves this with fault-tolerant checkpointing, automatic resume, and first-class rate-limiting and cost-tracking.

## Proposed Architecture

**Controller (FastAPI)**: REST API that accepts tasks and manages the Redis queue.

**Workers (Python + LangGraph)**: Multiple containers that lease tasks, execute nodes, and checkpoint state after each step.

**State Store (Redis)**: Stores task metadata, checkpoints, leases, heartbeats, rate-limits, and cost data.

**Heartbeat Monitor**: Background process that detects crashed workers and re-queues their tasks.

### Prerequisites
- Python 3.11+
- Redis 7.0+
- Docker (optional, for containerized deployment)