# OpenTelemetry Tracing & Prometheus Metrics Implementation

## Summary

Comprehensive observability has been added to Sentinel Node Orchestrator, including:

1. **OpenTelemetry distributed tracing** with Jaeger backend
2. **Enhanced Prometheus metrics** with multi-dimensional labels
3. **Grafana dashboard** with 15 visualization panels
4. **Docker Compose** stack for one-command observability setup
5. **Automatic instrumentation** for FastAPI and Redis

## Files Created

### Core Infrastructure
- `src/tracing.py` - OpenTelemetry SDK setup with span decorators
- `docker-compose.observability.yml` - Complete observability stack (Redis, Prometheus, Grafana, Jaeger)
- `docs/observability.md` - Comprehensive observability documentation

### Configuration
- `observability/prometheus.yml` - Prometheus scrape configuration
- `observability/grafana-datasources.yml` - Grafana datasource provisioning
- `observability/grafana-dashboards.yml` - Dashboard auto-import config
- `dashboards/sentinel-dashboard.json` - Pre-built Grafana dashboard with 15 panels

## Files Modified

### Dependencies
- `requirements.txt` - Added OpenTelemetry packages:
  - `opentelemetry-api>=1.22.0`
  - `opentelemetry-sdk>=1.22.0`
  - `opentelemetry-exporter-otlp>=1.22.0`
  - `opentelemetry-instrumentation-fastapi>=0.43b0`
  - `opentelemetry-instrumentation-redis>=0.43b0`

### Metrics Enhancement
- `src/metrics.py` - Enhanced with labels:
  - Task metrics: `tenant_id`, `agent_type`, `task_type`
  - LLM metrics: `model`, `tenant_id`, `node_type`, `token_type`
  - Node metrics: `node_type`, `status`
  - Rate limit: `tenant_id`
  - Added new metrics: `TASK_DURATION`, `LLM_COST`, `NODE_EXECUTIONS`, `NODE_DURATION`, `RATE_LIMIT_TOKENS`, `CHECKPOINT_SIZE_BYTES`, `WORKER_HEARTBEATS`, `ACTIVE_WORKERS`, `WORKER_TASKS`

### Tracing Instrumentation
- `src/api.py` - Auto-instrument FastAPI on startup with OpenTelemetry
- `src/worker.py` - Added tracing spans and attributes for:
  - Task execution (task_id, tenant_id, agent_type, task_type)
  - Node execution (node_id, node_type, tenant_id)
  - Span events for completion/failure
- `src/llm.py` - Added span attributes for LLM calls:
  - Model, temperature, token counts, cost, latency
  - Enhanced metrics with labels (model, tenant_id, token_type)

### Documentation
- `README.md` - Added Observability section with quick start guide

## Metrics Categories

### Task Metrics
```python
sentinel_tasks_started_total{tenant_id, agent_type, task_type}
sentinel_tasks_completed_total{tenant_id, agent_type, task_type}
sentinel_tasks_failed_total{tenant_id, agent_type, task_type}
sentinel_task_duration_seconds{tenant_id, agent_type, task_type}
```

### LLM Metrics
```python
sentinel_llm_calls_total{model, tenant_id, node_type}
sentinel_llm_tokens_total{model, tenant_id, token_type}  # prompt/completion
sentinel_llm_latency_seconds{model, tenant_id}
sentinel_llm_cost_usd_total{model, tenant_id}
```

### Node Metrics
```python
sentinel_node_executions_total{node_type, status}  # success/error
sentinel_node_duration_seconds{node_type}
```

### Infrastructure Metrics
```python
sentinel_active_workers
sentinel_worker_current_tasks{worker_id}
sentinel_worker_heartbeats_total{worker_id}
sentinel_rate_limit_hits_total{tenant_id}
sentinel_rate_limit_tokens_remaining{tenant_id}
sentinel_checkpoints_saved_total{task_id}
sentinel_checkpoints_restored_total{task_id}
sentinel_checkpoint_size_bytes{task_id}
sentinel_requeues_total{reason}
```

## Tracing Spans

### Automatic Spans
- FastAPI endpoints (via auto-instrumentation)
- Redis operations (via auto-instrumentation)

### Manual Spans
- Task execution: `task_id`, `tenant_id`, `agent_type`, `task_type`
- Node execution: `node_id`, `node_type`, `tenant_id`, `task_id`
- LLM calls: `model`, `temperature`, `tokens`, `cost`, `latency`

### Span Events
- `task_completed` - Task successfully finished
- `task_failed` - Task encountered error
- `node_completed` - Node executed successfully
- `node_failed` - Node execution failed

## Dashboard Panels

The Grafana dashboard includes 15 panels:

1. **Task Throughput** - Tasks/sec by tenant (started/completed/failed)
2. **Active Workers** - Current worker count
3. **Task Success Rate** - Percentage of successful tasks
4. **LLM Cost per Tenant** - USD/min by tenant and model
5. **LLM Token Usage** - Tokens/min (prompt vs completion)
6. **LLM Latency** - p50/p95/p99 by model
7. **Node Execution Duration** - p50/p95 by node type
8. **Rate Limit Hits** - Violations by tenant
9. **Checkpoint Operations** - Save/restore rates
10. **Node Executions** - Success/error by type
11. **LLM Calls by Model** - Pie chart of model distribution
12. **Task Duration** - p50/p95/p99 execution time
13. **Worker Heartbeats** - Worker health by ID
14. **Requeues by Reason** - Lease expired/crash/error
15. **Total Cost by Tenant** - Cumulative USD spend

## Usage

### Start Observability Stack

```bash
docker-compose -f docker-compose.observability.yml up -d
```

### Access Dashboards

- **Grafana**: http://localhost:3000 (admin/admin)
- **Prometheus**: http://localhost:9090
- **Jaeger UI**: http://localhost:16686

### Configure Application

```bash
# Set OTLP endpoint (default: localhost:4317)
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317

# Start API (auto-instruments with tracing)
uvicorn src.api:app --host 0.0.0.0 --port 8000

# Start worker (traces task execution)
python examples/run_system.py
```

### View Traces in Jaeger

1. Open http://localhost:16686
2. Select service: `sentinel-orchestrator`
3. Search by tags: `tenant_id`, `task_id`, `llm_model`
4. View trace timeline with spans

### Query Metrics in Prometheus

Example queries:

```promql
# Cost per tenant per hour
rate(sentinel_llm_cost_usd_total[1h]) * 3600

# Average task duration by type
rate(sentinel_task_duration_seconds_sum[5m]) / rate(sentinel_task_duration_seconds_count[5m])

# Error rate by node type
rate(sentinel_node_executions_total{status="error"}[5m]) / rate(sentinel_node_executions_total[5m])
```

## Integration Points

### API Server
- FastAPI auto-instrumentation on startup
- All endpoints traced automatically
- Request context propagated to workers

### Worker
- Task execution spans with metadata
- Node execution sub-spans
- LLM call spans with cost attributes
- Span events for lifecycle tracking

### LLM Client
- Automatic span attributes on chat_completion
- Token counts, cost, latency recorded
- Per-tenant and per-model metrics

### Redis Operations
- Auto-instrumented with OpenTelemetry
- Database calls visible in traces
- No code changes required

## Production Considerations

### Sampling
For high-volume production, enable sampling:

```python
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased

# Sample 10% of traces
sampler = TraceIdRatioBased(0.1)
```

### High Cardinality
Avoid high cardinality labels like `task_id` in metrics. Use tracing for per-task visibility.

### Sensitive Data
Don't log full prompts/completions in span attributes. Redact credentials and PII.

### Retention
Configure Prometheus retention:

```yaml
storage:
  tsdb:
    retention.time: 15d
```

## Next Steps

- [ ] Add alerting rules to Prometheus
- [ ] Configure Grafana alerts for high costs/errors
- [ ] Implement metric sampling for high-volume tenants
- [ ] Add custom dashboards per tenant
- [ ] Export traces to external APM (Datadog, New Relic)

## References

- [docs/observability.md](../docs/observability.md) - Complete documentation
- [dashboards/sentinel-dashboard.json](../dashboards/sentinel-dashboard.json) - Dashboard JSON
- [docker-compose.observability.yml](../docker-compose.observability.yml) - Stack configuration
