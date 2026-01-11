#!/usr/bin/env bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print colored message
print_msg() {
    echo -e "${GREEN}==>${NC} $1"
}

print_error() {
    echo -e "${RED}ERROR:${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}WARNING:${NC} $1"
}

print_info() {
    echo -e "${BLUE}INFO:${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    print_msg "Checking prerequisites..."
    
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        print_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi
    
    if ! docker info &> /dev/null; then
        print_error "Docker daemon is not running. Please start Docker."
        exit 1
    fi
    
    print_info "Docker $(docker --version)"
    print_info "Docker Compose $(docker-compose --version)"
}

# Setup environment file
setup_env() {
    print_msg "Setting up environment..."
    
    if [ ! -f .env ]; then
        if [ -f .env.example ]; then
            cp .env.example .env
            print_info "Created .env from .env.example"
        else
            print_error ".env.example not found"
            exit 1
        fi
    else
        print_info ".env already exists, skipping"
    fi
    
    # Check if OpenAI API key is set
    if grep -q "OPENAI_API_KEY=sk-your-api-key-here" .env || grep -q "OPENAI_API_KEY=$" .env; then
        print_warning "OpenAI API key not configured in .env"
        print_info "Please edit .env and set your OpenAI API key"
        
        read -p "Do you want to enter your API key now? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            read -p "Enter your OpenAI API key: " api_key
            sed -i.bak "s/OPENAI_API_KEY=.*/OPENAI_API_KEY=$api_key/" .env
            rm .env.bak 2>/dev/null || true
            print_info "API key updated in .env"
        fi
    fi
}

# Build Docker images
build_images() {
    print_msg "Building Docker images..."
    docker-compose build --pull
}

# Start services
start_services() {
    print_msg "Starting services..."
    docker-compose up -d
}

# Wait for services to be healthy
wait_for_services() {
    print_msg "Waiting for services to be healthy..."
    
    local max_attempts=30
    local attempt=0
    
    while [ $attempt -lt $max_attempts ]; do
        if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
            print_info "API server is healthy"
            return 0
        fi
        
        attempt=$((attempt + 1))
        echo -n "."
        sleep 2
    done
    
    echo
    print_warning "API server did not become healthy within timeout"
    print_info "Check logs with: docker-compose logs api"
    return 1
}

# Show service status
show_status() {
    print_msg "Service status:"
    docker-compose ps
    echo
}

# Show URLs
show_urls() {
    echo
    print_msg "Sentinel Node Orchestrator is running!"
    echo
    print_info "API Documentation:  ${BLUE}http://localhost:8000/docs${NC}"
    print_info "API Health:         ${BLUE}http://localhost:8000/health${NC}"
    print_info "Grafana Dashboard:  ${BLUE}http://localhost:3000${NC} (admin/admin)"
    print_info "Prometheus:         ${BLUE}http://localhost:9090${NC}"
    print_info "Jaeger Traces:      ${BLUE}http://localhost:16686${NC}"
    print_info "Metrics Endpoint:   ${BLUE}http://localhost:9091/metrics${NC}"
    echo
}

# Show useful commands
show_commands() {
    print_msg "Useful commands:"
    echo
    print_info "View logs:          ${BLUE}docker-compose logs -f${NC}"
    print_info "View API logs:      ${BLUE}docker-compose logs -f api${NC}"
    print_info "View worker logs:   ${BLUE}docker-compose logs -f worker-1${NC}"
    print_info "Stop services:      ${BLUE}docker-compose stop${NC}"
    print_info "Restart services:   ${BLUE}docker-compose restart${NC}"
    print_info "Remove everything:  ${BLUE}docker-compose down -v${NC}"
    echo
    print_info "Submit a test task:"
    echo "  curl -X POST http://localhost:8000/tasks \\"
    echo "    -H 'Content-Type: application/json' \\"
    echo "    -d '{\"task_type\": \"analysis\", \"tenant_id\": \"demo\", \"task_params\": {\"query\": \"test\"}}'"
    echo
}

# Main function
main() {
    echo
    print_msg "Sentinel Node Orchestrator - Quick Start"
    echo "========================================"
    echo
    
    check_prerequisites
    setup_env
    build_images
    start_services
    
    if wait_for_services; then
        show_status
        show_urls
        show_commands
        
        print_msg "Setup complete! 🚀"
        echo
        print_info "To view logs: ${BLUE}docker-compose logs -f${NC}"
        echo
    else
        print_error "Service startup failed. Check logs with: docker-compose logs"
        exit 1
    fi
}

# Run main function
main "$@"
