# Sentinel-Node-Orchestrator

High-availability, distributed AI agent orchestration system that closes the reliability gap in production LLM workflows.

Sentinel ensures long-running, multi-step agent tasks survive worker crashes by checkpointing execution state to Redis and allowing other workers to resume from the last saved step. It also tracks LLM cost per call and provides primitives for rate-limiting.

## 🚀 Quick Start

**One-line setup (Docker):**

```bash
./start.sh
```

Or using Make:

```bash
make up && make demo
```

This starts the complete stack (Redis, API, Workers, Watcher, Prometheus, Grafana, Jaeger) and submits sample tasks.

**Access the system:**
- � **Grafana Dashboard**: http://localhost:3000 (admin/admin)
- 🔍 **Jaeger Traces**: http://localhost:16686
- 📈 **Prometheus**: http://localhost:9090
- 🌐 **API Docs**: http://localhost:8000/docs

## What this repo contains
- `src/state.py` — Pydantic models for task metadata and checkpoints with versioning
- `src/redis_saver.py` — Redis-backed checkpoint saver and atomic helper APIs
- `src/rate_limiter.py` — **Token-bucket rate limiter with atomic Lua scripts**
- `src/agent.py` — **Agent abstraction layer for pluggable agent implementations**
- `src/langgraph_adapter.py` — **LangGraph checkpoint adapter for graph-based agent execution with resume**
- `src/worker.py` — Async worker that claims tasks, executes nodes, checkpoints state, heartbeats and renews leases
- `src/watcher.py` — Watcher service that detects dead workers and requeues tasks
- `src/api.py` — FastAPI controller to create and manage tasks
- `src/llm.py` — **OpenAI integration with automatic cost tracking**
- `examples/` — runnable demos: checkpoint, worker, watcher, API, LLM, rate limit, agent, LangGraph demos
- `tests/` — pytest async tests for schemas and Redis saver
- `requirements.txt` and `.env.example`

## Quickstart

### Docker (Recommended)

Complete stack with one command:

```bash
# 1. Copy environment template
cp .env.example .env

# 2. Add your OpenAI API key to .env
# Edit .env and set: OPENAI_API_KEY=sk-your-key-here

# 3. Start all services
docker-compose up -d
```

This starts:
- Redis (state storage)
- API server on http://localhost:8000
- 2x Workers (task processors)
- Watcher (failure detection)
- Prometheus on http://localhost:9090
- Grafana on http://localhost:3000 (admin/admin)
- Jaeger on http://localhost:16686

**Access:**
- API docs: http://localhost:8000/docs
- Grafana dashboard: http://localhost:3000
- Jaeger traces: http://localhost:16686

See [docs/docker-setup.md](docs/docker-setup.md) for detailed Docker guide.

### Local Development (Python)

1. Create and activate a virtualenv (macOS zsh):

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Set up OpenAI API key (required for LLM integration):

```bash
export OPENAI_API_KEY='your-api-key-here'
# Or create .env file:
echo "OPENAI_API_KEY=your-api-key-here" > .env
```

4. Start Redis (Docker):

```bash
docker run -d -p 6379:6379 redis:7-alpine
```

5. Run components (each in its own terminal):

- API server (accepts task submissions):

```bash
uvicorn src.api:app --reload --host 0.0.0.0 --port 8000
```

- Worker (processes tasks):

```bash
python3 examples/worker_demo.py     # multi-worker or single-task demos available
```

- Watcher (detects failed workers and requeues):

```bash
python3 examples/watcher_demo.py
```

## Demo & Development Commands

### Using the Demo Script

Submit sample tasks and watch progress:

```bash
# Submit 3 sample tasks
python demo.py

# Submit tasks and watch real-time progress
python demo.py --watch

# Submit custom number of tasks
python demo.py --count 5 --watch
```

### Using Make Commands

```bash
# Quick commands
make help         # Show all available commands
make up           # Start all services
make demo         # Run interactive demo
make logs         # View all logs
make status       # Show service status
make down         # Stop all services

# Development
make test         # Run test suite
make logs-api     # View API logs only
make logs-workers # View worker logs
make metrics      # Show current metrics

# Monitoring
make grafana      # Open Grafana dashboard
make jaeger       # Open Jaeger traces
make prometheus   # Open Prometheus UI
```

### Docker Compose Commands

```bash
# View logs
docker-compose logs -f              # All services
docker-compose logs -f api          # API only
docker-compose logs -f worker-1     # Worker 1 only

# Restart services
docker-compose restart              # All services
docker-compose restart worker-1     # Single service

# Scale workers
docker-compose up -d --scale worker-1=5

# Stop and cleanup
docker-compose down                 # Stop (keep data)
docker-compose down -v              # Stop and remove volumes
```

See [docs/docker-setup.md](docs/docker-setup.md) for comprehensive Docker guide.

## Core Concepts (brief)
- Tasks: submitted via the FastAPI controller and stored in Redis as `task:{id}:meta` (HASH)
- Checkpoints: serialized `TaskCheckpoint` stored at `task:{id}:checkpoint` (STRING)
- Heartbeats: workers set `worker:{id}:hb` with TTL to indicate liveness
- Lease management: claiming and renewing tasks uses atomic Redis ops (Lua scripts and HSET)
- Watcher: scans heartbeats and leases, requeues tasks when leases expire

## Redis key overview

```
task:{id}:meta          # HASH - task metadata (status, owner, lease_expires, cost)
task:{id}:checkpoint    # STRING - serialized checkpoint state (JSON)
worker:{id}:hb          # STRING - worker heartbeat (with TTL)
ratelimit:tenant:{id}   # HASH - token bucket state (tokens, last_refill)
stream:events           # STREAM - lifecycle and audit events
leases                  # ZSET - optional lease expiry index
cost:tenant:{id}:{date} # HASH - per-tenant cost aggregates
```

## API Endpoints (high level)
- `POST /tasks` — create a new task
- `GET /tasks` — list tasks with optional filters
- `GET /tasks/{task_id}` — fetch task metadata
- `DELETE /tasks/{task_id}` — cancel a queued/leased task
- `GET /stats` — global task stats
- `GET /tenants/{tenant_id}/costs` — tenant cost summary
- `GET /tenants/{tenant_id}/rate-limit` — get tenant rate limit status
- `POST /tenants/{tenant_id}/rate-limit` — set custom rate limit capacity/refill
- `DELETE /tenants/{tenant_id}/rate-limit` — reset tenant rate limit

See `src/api.py` for full request/response models.

## Observability

Sentinel includes comprehensive observability with OpenTelemetry tracing and Prometheus metrics.

### Quick Start

```bash
# Start observability stack (Prometheus, Grafana, Jaeger)
docker-compose -f docker-compose.observability.yml up -d

# Access dashboards:
# - Grafana: http://localhost:3000 (admin/admin)
# - Prometheus: http://localhost:9090
# - Jaeger: http://localhost:16686
```

### Key Metrics

**Task Metrics** (by tenant, agent, task type):
- `sentinel_tasks_started_total`, `sentinel_tasks_completed_total`, `sentinel_tasks_failed_total`
- `sentinel_task_duration_seconds` - Task execution time histogram

**LLM Metrics** (by model, tenant):
- `sentinel_llm_calls_total` - Total LLM API calls
- `sentinel_llm_tokens_total` - Token usage (prompt/completion)
- `sentinel_llm_cost_usd_total` - Cumulative costs
- `sentinel_llm_latency_seconds` - Call latency histogram

**Node Metrics** (by node type, status):
- `sentinel_node_executions_total` - Node executions (success/error)
- `sentinel_node_duration_seconds` - Execution duration

**Infrastructure**:
- `sentinel_active_workers` - Active worker count
- `sentinel_rate_limit_hits_total` - Rate limit violations
- `sentinel_checkpoints_saved_total` - Checkpoint operations

### Distributed Tracing

All operations are automatically traced with OpenTelemetry:
- FastAPI endpoints with request context
- Redis operations
- Task and node execution spans
- LLM calls with token/cost attributes

See [docs/observability.md](docs/observability.md) for detailed configuration.

## Demos
- `examples/checkpoint_demo.py` — simple checkpoint save/load/resume flow
- `examples/worker_demo.py` — run workers to claim and process tasks
- `examples/watcher_demo.py` — simulate worker crash and automatic requeue
- `examples/api_demo.py` — exercises the FastAPI controller
- `examples/llm_demo.py` — OpenAI integration with cost tracking
- `examples/rate_limit_demo.py` — token bucket rate limiting (basic, tenant, burst, task)
- `examples/agent_demo.py` — **agent abstraction with custom implementations**
- `examples/langgraph_demo.py` — **LangGraph agent execution with checkpoint resume**

## Testing

Run tests (requires a local Redis instance):

```bash
docker run -d -p 6379:6379 redis:7-alpine
pytest -q
```

## Next steps / roadmap
- ✅ **OpenTelemetry tracing and Prometheus metrics** - Comprehensive observability
- ✅ Rate-limiting (Redis token-bucket) and tenant quotas
- ✅ LangGraph integration with checkpoint resume
- Kubernetes manifests for scalable deployment
- Replace SCAN with Redis Streams for task queue (XREADGROUP)
- CI with Redis test fixture (or fakeredis)
- Web UI with DAG visualizer

## License
MIT

---