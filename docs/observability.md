# Observability Setup

This document describes the observability infrastructure for Sentinel Node Orchestrator, including metrics, tracing, and visualization.

## Architecture

The observability stack consists of:

1. **Prometheus** - Metrics collection and storage
2. **Grafana** - Metrics visualization and dashboards
3. **Jaeger** - Distributed tracing with OpenTelemetry
4. **Prometheus Python Client** - Application-level metrics export
5. **OpenTelemetry SDK** - Distributed tracing instrumentation

## Quick Start

### 1. Start Observability Stack

```bash
# Start Redis, Prometheus, Grafana, and Jaeger
docker-compose -f docker-compose.observability.yml up -d

# Verify all services are running
docker-compose -f docker-compose.observability.yml ps
```

### 2. Install OpenTelemetry Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure OpenTelemetry Endpoint

Set the OTLP endpoint environment variable (default is localhost:4317):

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
```

### 4. Start Application with Tracing

```bash
# Start API server (will automatically instrument with tracing)
python -m uvicorn src.api:app --host 0.0.0.0 --port 8000

# Start worker (will emit traces to Jaeger)
python examples/run_system.py
```

## Accessing Dashboards

- **Grafana**: http://localhost:3000 (admin/admin)
- **Prometheus**: http://localhost:9090
- **Jaeger UI**: http://localhost:16686

## Metrics

### Task Metrics

Labeled by `tenant_id`, `agent_type`, `task_type`:

- `sentinel_tasks_started_total` - Counter of tasks started
- `sentinel_tasks_completed_total` - Counter of tasks completed successfully
- `sentinel_tasks_failed_total` - Counter of tasks that failed
- `sentinel_task_duration_seconds` - Histogram of task execution duration

### LLM Metrics

Labeled by `model`, `tenant_id`, `node_type`, `token_type`:

- `sentinel_llm_calls_total` - Counter of LLM API calls
- `sentinel_llm_tokens_total` - Counter of tokens consumed (prompt/completion)
- `sentinel_llm_latency_seconds` - Histogram of LLM call latency
- `sentinel_llm_cost_usd_total` - Counter of cumulative LLM costs in USD

### Node Execution Metrics

Labeled by `node_type`, `status`:

- `sentinel_node_executions_total` - Counter of node executions (success/error)
- `sentinel_node_duration_seconds` - Histogram of node execution duration

### Rate Limiting Metrics

Labeled by `tenant_id`:

- `sentinel_rate_limit_hits_total` - Counter of rate limit hits
- `sentinel_rate_limit_tokens_remaining` - Gauge of remaining tokens in bucket

### Checkpoint Metrics

Labeled by `task_id`:

- `sentinel_checkpoints_saved_total` - Counter of checkpoints saved
- `sentinel_checkpoints_restored_total` - Counter of checkpoints restored
- `sentinel_checkpoint_size_bytes` - Histogram of checkpoint size

### Worker Metrics

Labeled by `worker_id`:

- `sentinel_worker_heartbeats_total` - Counter of worker heartbeats
- `sentinel_active_workers` - Gauge of active workers
- `sentinel_worker_current_tasks` - Gauge of current tasks per worker

### Requeue Metrics

Labeled by `reason`:

- `sentinel_requeues_total` - Counter of task requeues (lease_expired, worker_crash, error)

## Tracing

### Automatic Instrumentation

The following components are automatically instrumented with OpenTelemetry:

1. **FastAPI Endpoints** - All API requests create root spans
2. **Redis Operations** - Database calls are traced
3. **Task Execution** - Each task execution creates a span
4. **Node Execution** - Individual node processing is traced
5. **LLM Calls** - LLM API calls are traced with token/cost attributes

### Span Attributes

#### Task Spans
- `task_id` - Unique task identifier
- `tenant_id` - Tenant ID for multi-tenancy
- `agent_type` - Agent implementation (prompt-based, langgraph)
- `task_type` - Type of task being executed
- `worker_id` - Worker processing the task

#### Node Spans
- `node_id` - Node identifier
- `node_type` - Type of node (search, analyze, summarize, complete)
- `task_id` - Parent task ID
- `tenant_id` - Tenant ID

#### LLM Spans
- `llm_model` - Model name (gpt-4o, gpt-3.5-turbo, etc.)
- `llm_temperature` - Sampling temperature
- `llm_max_tokens` - Maximum tokens requested
- `llm_prompt_tokens` - Tokens in prompt
- `llm_completion_tokens` - Tokens in completion
- `llm_total_tokens` - Total tokens consumed
- `llm_cost_usd` - Cost of the call in USD
- `llm_latency_ms` - Latency in milliseconds

### Viewing Traces

1. Open Jaeger UI at http://localhost:16686
2. Select service: `sentinel-orchestrator`
3. Search by:
   - Operation name (e.g., `execute_task`, `execute_node`, `chat_completion`)
   - Tags (e.g., `tenant_id`, `task_id`, `llm_model`)
   - Duration threshold
4. View trace timeline and span details

## Grafana Dashboard

The pre-configured Grafana dashboard includes:

### Overview Panels
- Task throughput (tasks/sec) by tenant
- Active workers count
- Task success rate percentage

### Cost Tracking
- LLM cost per tenant over time
- Total cumulative cost by tenant
- Cost breakdown by model

### Performance Metrics
- LLM latency percentiles (p50, p95, p99)
- Node execution duration percentiles
- Task duration percentiles

### Resource Usage
- LLM token usage (prompt vs completion)
- Rate limit hits by tenant
- Checkpoint operations rate

### Reliability
- Node executions by type and status (success/error)
- Requeues by reason
- Worker heartbeats

## Custom Queries

### Prometheus Queries

**Cost per tenant per hour:**
```promql
rate(sentinel_llm_cost_usd_total[1h]) * 3600
```

**Average task duration by type:**
```promql
rate(sentinel_task_duration_seconds_sum[5m]) / rate(sentinel_task_duration_seconds_count[5m])
```

**LLM token efficiency (completions per prompt token):**
```promql
rate(sentinel_llm_tokens_total{token_type="completion"}[5m]) / rate(sentinel_llm_tokens_total{token_type="prompt"}[5m])
```

**Error rate by node type:**
```promql
rate(sentinel_node_executions_total{status="error"}[5m]) / rate(sentinel_node_executions_total[5m])
```

## Alerting

### Recommended Alerts

Create alerts in Prometheus for:

1. **High error rate:**
   ```promql
   rate(sentinel_tasks_failed_total[5m]) / rate(sentinel_tasks_started_total[5m]) > 0.1
   ```

2. **High LLM costs:**
   ```promql
   rate(sentinel_llm_cost_usd_total[1h]) * 3600 > 100
   ```

3. **Worker health:**
   ```promql
   sentinel_active_workers < 1
   ```

4. **High latency:**
   ```promql
   histogram_quantile(0.95, rate(sentinel_llm_latency_seconds_bucket[5m])) > 10
   ```

5. **Rate limit saturation:**
   ```promql
   rate(sentinel_rate_limit_hits_total[5m]) > 10
   ```

## Production Considerations

### Metrics Retention

Configure Prometheus retention in `observability/prometheus.yml`:

```yaml
global:
  scrape_interval: 15s
  
# Retention: 15 days
storage:
  tsdb:
    retention.time: 15d
```

### High Cardinality Labels

Be cautious with high cardinality labels like `task_id` in metrics. Consider:
- Aggregating by tenant/type instead
- Using tracing for per-task visibility
- Implementing metric sampling for high-volume tenants

### Sampling for Tracing

For high-volume production:

```python
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased

# Sample 10% of traces
sampler = TraceIdRatioBased(0.1)
```

### Sensitive Data

Avoid logging sensitive data in span attributes:
- Don't include full prompts or completions
- Redact API keys and credentials
- Hash or truncate user IDs if necessary

## Troubleshooting

### Metrics not appearing in Prometheus

1. Check Prometheus targets: http://localhost:9090/targets
2. Verify application is exposing metrics on port 9091:
   ```bash
   curl http://localhost:9091/metrics
   ```
3. Check Prometheus logs:
   ```bash
   docker-compose -f docker-compose.observability.yml logs prometheus
   ```

### Traces not appearing in Jaeger

1. Verify OTLP endpoint configuration:
   ```bash
   echo $OTEL_EXPORTER_OTLP_ENDPOINT
   ```
2. Check Jaeger collector health:
   ```bash
   curl http://localhost:14269/
   ```
3. Verify OpenTelemetry SDK initialization in application logs

### Grafana dashboard not loading

1. Check datasource configuration in Grafana UI
2. Verify Prometheus is accessible from Grafana:
   ```bash
   docker-compose -f docker-compose.observability.yml exec grafana curl http://prometheus:9090/-/healthy
   ```
3. Re-import dashboard from `dashboards/sentinel-dashboard.json`

## References

- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)
- [Jaeger Documentation](https://www.jaegertracing.io/docs/)
- [OpenTelemetry Python](https://opentelemetry.io/docs/instrumentation/python/)
