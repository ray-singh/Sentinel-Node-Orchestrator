# Sentinel-Node-Orchestrator

High-availability, distributed AI agent orchestration system that closes the reliability gap in production LLM workflows.

Sentinel ensures long-running, multi-step agent tasks survive worker crashes by checkpointing execution state to Redis and allowing other workers to resume from the last saved step. It also tracks LLM cost per call and provides primitives for rate-limiting.

## What this repo contains
- `src/state.py` — Pydantic models for task metadata and checkpoints
- `src/redis_saver.py` — Redis-backed checkpoint saver and atomic helper APIs
- `src/worker.py` — Async worker that claims tasks, executes nodes, checkpoints state, heartbeats and renews leases
- `src/watcher.py` — Watcher service that detects dead workers and requeues tasks
- `src/api.py` — FastAPI controller to create and manage tasks
- `examples/` — runnable demos: checkpoint, worker, watcher, API demos
- `tests/` — pytest async tests for schemas and Redis saver
- `requirements.txt` and `.env.example`

## Quickstart (local)

1. Create and activate a virtualenv (macOS zsh):

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Start Redis (Docker):

```bash
docker run -d -p 6379:6379 redis:7-alpine
```

4. Run components (each in its own terminal):

- API server (accepts task submissions):

```bash
python3 -m src.api
# or with uvicorn:
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

5. Run the API demo (after API server is running):

```bash
python3 examples/api_demo.py
```

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

See `src/api.py` for full request/response models.

## Demos
- `examples/checkpoint_demo.py` — simple checkpoint save/load/resume flow
- `examples/worker_demo.py` — run workers to claim and process tasks
- `examples/watcher_demo.py` — simulate worker crash and automatic requeue
- `examples/api_demo.py` — exercises the FastAPI controller

## Testing

Run tests (requires a local Redis instance):

```bash
docker run -d -p 6379:6379 redis:7-alpine
pytest -q
```

## Next steps / roadmap
- Rate-limiting (Redis token-bucket) and tenant quotas
- Kubernetes manifests for scalable deployment
- Prometheus metrics and tracing
- CI with Redis test fixture (or fakeredis)

## License
MIT

---