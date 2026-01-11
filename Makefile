.PHONY: help build up down restart logs status test clean demo install dev

# Default target
help:
	@echo "Sentinel Node Orchestrator - Development Commands"
	@echo ""
	@echo "Quick Start:"
	@echo "  make install    Install Python dependencies (local dev)"
	@echo "  make up         Start all services with Docker Compose"
	@echo "  make demo       Submit sample tasks and watch progress"
	@echo ""
	@echo "Docker Commands:"
	@echo "  make build      Build Docker images"
	@echo "  make down       Stop all services"
	@echo "  make restart    Restart all services"
	@echo "  make logs       View logs from all services"
	@echo "  make status     Show service status"
	@echo "  make clean      Remove all containers and volumes"
	@echo ""
	@echo "Development:"
	@echo "  make dev        Start services in development mode"
	@echo "  make test       Run test suite"
	@echo "  make lint       Run code linters"
	@echo "  make format     Format code with black"
	@echo ""
	@echo "Monitoring:"
	@echo "  make grafana    Open Grafana dashboard"
	@echo "  make prometheus Open Prometheus UI"
	@echo "  make jaeger     Open Jaeger tracing UI"
	@echo "  make metrics    Show current metrics"

# Install Python dependencies for local development
install:
	@echo "Installing Python dependencies..."
	python3 -m venv .venv || true
	. .venv/bin/activate && pip install -r requirements.txt
	@echo "Done! Activate with: source .venv/bin/activate"

# Build Docker images
build:
	@echo "Building Docker images..."
	docker-compose build --pull

# Start all services
up:
	@echo "Starting all services..."
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "Created .env from .env.example"; \
		echo "⚠️  Please edit .env and add your OPENAI_API_KEY"; \
	fi
	docker-compose up -d
	@echo "Waiting for services to be ready..."
	@sleep 5
	@make status
	@echo ""
	@echo "✓ Services are running!"
	@echo "  API: http://localhost:8000/docs"
	@echo "  Grafana: http://localhost:3000 (admin/admin)"
	@echo "  Jaeger: http://localhost:16686"

# Stop all services
down:
	@echo "Stopping all services..."
	docker-compose down

# Restart all services
restart:
	@echo "Restarting all services..."
	docker-compose restart

# View logs
logs:
	docker-compose logs -f

# View API logs only
logs-api:
	docker-compose logs -f api

# View worker logs
logs-workers:
	docker-compose logs -f worker-1 worker-2

# Show service status
status:
	@echo "Service Status:"
	@docker-compose ps

# Run test suite
test:
	@echo "Running tests..."
	PYTHONPATH=. pytest tests/ -v --asyncio-mode=auto

# Run tests in Docker
test-docker:
	@echo "Running tests in Docker..."
	docker-compose exec -T api pytest tests/ -v --asyncio-mode=auto

# Clean up everything
clean:
	@echo "Removing all containers, networks, and volumes..."
	docker-compose down -v
	@echo "Cleaned up!"

# Run demo script
demo:
	@echo "Running demo..."
	python demo.py --watch

# Submit sample tasks
demo-submit:
	@echo "Submitting sample tasks..."
	python demo.py --count 3

# Development mode (with hot reload)
dev:
	@echo "Starting in development mode..."
	docker-compose up

# Open Grafana dashboard
grafana:
	@echo "Opening Grafana dashboard..."
	@open http://localhost:3000 || xdg-open http://localhost:3000 || echo "Open http://localhost:3000"

# Open Prometheus UI
prometheus:
	@echo "Opening Prometheus UI..."
	@open http://localhost:9090 || xdg-open http://localhost:9090 || echo "Open http://localhost:9090"

# Open Jaeger tracing UI
jaeger:
	@echo "Opening Jaeger UI..."
	@open http://localhost:16686 || xdg-open http://localhost:16686 || echo "Open http://localhost:16686"

# Show current metrics
metrics:
	@echo "Fetching current metrics..."
	@curl -s http://localhost:9091/metrics | grep -E "^sentinel_" | head -20

# Lint code
lint:
	@echo "Running linters..."
	@if command -v ruff > /dev/null; then \
		ruff check src/ tests/; \
	else \
		echo "ruff not installed. Install with: pip install ruff"; \
	fi

# Format code
format:
	@echo "Formatting code..."
	@if command -v black > /dev/null; then \
		black src/ tests/ examples/; \
	else \
		echo "black not installed. Install with: pip install black"; \
	fi

# Health check
health:
	@echo "Checking service health..."
	@curl -s http://localhost:8000/health | python -m json.tool

# Scale workers
scale-workers:
	@echo "Scaling to $(WORKERS) workers..."
	@docker-compose up -d --scale worker-1=$(WORKERS)

# Backup Redis data
backup:
	@echo "Backing up Redis data..."
	@docker-compose exec redis redis-cli BGSAVE
	@echo "Backup initiated. Data saved to Redis volume."

# Show Redis keys
redis-keys:
	@echo "Redis keys:"
	@docker-compose exec redis redis-cli KEYS "*" | head -20

# Access Redis CLI
redis-cli:
	@docker-compose exec redis redis-cli

# Show environment
env:
	@echo "Current environment:"
	@docker-compose exec api env | grep -E "REDIS_URL|WORKER_ID|ENABLE_METRICS|LOG_LEVEL"

# Check prerequisites
check:
	@echo "Checking prerequisites..."
	@command -v docker >/dev/null 2>&1 || { echo "Docker not installed"; exit 1; }
	@command -v docker-compose >/dev/null 2>&1 || { echo "Docker Compose not installed"; exit 1; }
	@docker info >/dev/null 2>&1 || { echo "Docker daemon not running"; exit 1; }
	@echo "✓ All prerequisites met"

# Quick start script
quickstart: check
	@echo "Running quick start..."
	@./start.sh
