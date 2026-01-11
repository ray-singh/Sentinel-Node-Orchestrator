# Docker Setup Guide

Complete guide for running Sentinel Node Orchestrator with Docker Compose.

## Prerequisites

- Docker 20.10+
- Docker Compose 2.0+
- OpenAI API key (for LLM calls)

## Quick Start

### 1. Configure Environment

Copy the example environment file:

```bash
cp .env.example .env
```

Edit `.env` and add your OpenAI API key:

```bash
OPENAI_API_KEY=sk-your-actual-key-here
```

### 2. Start All Services

```bash
docker-compose up -d
```

This starts:
- **Redis** (port 6379) - State storage
- **API Server** (port 8000) - REST endpoints
- **Worker 1 & 2** - Task processors
- **Watcher** - Dead worker detection
- **Prometheus** (port 9090) - Metrics
- **Grafana** (port 3000) - Dashboards
- **Jaeger** (port 16686) - Tracing

### 3. Verify Services

Check all services are healthy:

```bash
docker-compose ps
```

Test API health:

```bash
curl http://localhost:8000/health
```

### 4. Access Dashboards

- **API**: http://localhost:8000/docs (Swagger UI)
- **Grafana**: http://localhost:3000 (admin/admin)
- **Prometheus**: http://localhost:9090
- **Jaeger**: http://localhost:16686
- **Metrics**: http://localhost:9091/metrics

## Common Operations

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f api
docker-compose logs -f worker-1

# Last 100 lines
docker-compose logs --tail=100 worker-2
```

### Restart Services

```bash
# Restart single service
docker-compose restart worker-1

# Restart all
docker-compose restart
```

### Scale Workers

```bash
# Add more workers
docker-compose up -d --scale worker-1=3

# Or edit docker-compose.yml and add worker-3, worker-4, etc.
```

### Stop Services

```bash
# Stop all (keeps data)
docker-compose stop

# Stop and remove containers (keeps volumes)
docker-compose down

# Remove everything including volumes
docker-compose down -v
```

### Rebuild Images

After code changes:

```bash
# Rebuild and restart
docker-compose up -d --build

# Force rebuild without cache
docker-compose build --no-cache
docker-compose up -d
```

## Development Workflow

### Hot Reload

The API and workers mount source code as volumes with hot reload enabled:

1. Edit code in `src/` or `examples/`
2. API auto-reloads (uvicorn `--reload`)
3. Workers need manual restart:

```bash
docker-compose restart worker-1 worker-2
```

### Interactive Shell

Access container shell for debugging:

```bash
# API container
docker-compose exec api bash

# Worker container
docker-compose exec worker-1 bash

# Run Python REPL
docker-compose exec api python
```

### Run Tests

```bash
# Run tests inside container
docker-compose exec api pytest tests/ -v

# Or from host (requires .venv)
PYTHONPATH=. pytest tests/ -v
```

## Debugging

### Check Container Health

```bash
# Container status
docker-compose ps

# Inspect specific container
docker inspect sentinel-api

# Check resource usage
docker stats
```

### Redis Data Inspection

```bash
# Access Redis CLI
docker-compose exec redis redis-cli

# Inside Redis:
> KEYS task:*
> HGETALL task:abc123:meta
> GET task:abc123:checkpoint
```

### Network Issues

```bash
# Test connectivity between containers
docker-compose exec worker-1 ping redis
docker-compose exec worker-1 curl http://api:8000/health

# Check network
docker network inspect sentinel-network
```

### Performance Tuning

Edit `docker-compose.yml` resource limits:

```yaml
worker-1:
  deploy:
    resources:
      limits:
        cpus: '2'      # Increase CPU
        memory: 1G     # Increase RAM
```

## Production Considerations

### Environment Variables

For production, use secrets management:

```bash
# Docker secrets
echo "sk-prod-key" | docker secret create openai_api_key -

# Update docker-compose.yml
services:
  api:
    secrets:
      - openai_api_key
    environment:
      - OPENAI_API_KEY_FILE=/run/secrets/openai_api_key
```

### Persistent Volumes

Volumes are configured for persistence:
- `redis-data` - Task state and checkpoints
- `prometheus-data` - Metrics history
- `grafana-data` - Dashboard configs

Backup volumes:

```bash
# Backup Redis data
docker run --rm -v sentinel_redis-data:/data -v $(pwd):/backup \
  alpine tar czf /backup/redis-backup.tar.gz /data

# Restore
docker run --rm -v sentinel_redis-data:/data -v $(pwd):/backup \
  alpine tar xzf /backup/redis-backup.tar.gz -C /
```

### Health Checks

All services have health checks configured. Monitor with:

```bash
docker-compose ps --format json | jq '.[] | {name: .Name, health: .Health}'
```

### Logging

Configure centralized logging:

```yaml
services:
  api:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

Or use external logging driver (e.g., Fluentd, Splunk).

## Troubleshooting

### Port Conflicts

If ports are already in use:

```bash
# Check what's using a port
lsof -i :8000

# Change ports in docker-compose.yml
ports:
  - "8001:8000"  # Map to different host port
```

### Container Crashes

```bash
# View crash logs
docker-compose logs --tail=50 worker-1

# Check exit code
docker-compose ps

# Restart with verbose logging
docker-compose up worker-1
```

### Out of Memory

```bash
# Check memory usage
docker stats

# Increase limits or reduce workers
docker-compose down
# Edit docker-compose.yml memory limits
docker-compose up -d
```

### Slow Performance

- Check Redis memory: `docker-compose exec redis redis-cli INFO memory`
- Monitor CPU: `docker stats`
- Check network latency between containers
- Review logs for rate limiting or retries

## Advanced Configuration

### Custom Prometheus Config

Edit `observability/prometheus.yml` and reload:

```bash
# Edit config
vim observability/prometheus.yml

# Reload without restart
curl -X POST http://localhost:9090/-/reload
```

### Custom Grafana Dashboards

1. Create dashboard in UI (http://localhost:3000)
2. Export JSON
3. Save to `dashboards/` directory
4. Restart Grafana:

```bash
docker-compose restart grafana
```

### Multi-Environment Setup

Create environment-specific compose files:

```bash
# Development
docker-compose -f docker-compose.yml up

# Staging
docker-compose -f docker-compose.yml -f docker-compose.staging.yml up

# Production
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up
```

## Integration with CI/CD

Example GitHub Actions workflow:

```yaml
- name: Start services
  run: |
    cp .env.example .env
    echo "OPENAI_API_KEY=${{ secrets.OPENAI_API_KEY }}" >> .env
    docker-compose up -d
    
- name: Wait for health
  run: |
    timeout 60 bash -c 'until curl -f http://localhost:8000/health; do sleep 2; done'
    
- name: Run tests
  run: docker-compose exec -T api pytest tests/ -v
```

## References

- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [Docker Best Practices](https://docs.docker.com/develop/dev-best-practices/)
- [Sentinel Observability Guide](./observability.md)
