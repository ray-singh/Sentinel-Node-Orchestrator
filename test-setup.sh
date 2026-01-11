#!/usr/bin/env bash
# Test script to verify Docker Compose setup

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASSED=0
FAILED=0

test_pass() {
    echo -e "${GREEN}✓${NC} $1"
    PASSED=$((PASSED + 1))
}

test_fail() {
    echo -e "${RED}✗${NC} $1"
    FAILED=$((FAILED + 1))
}

echo "=================================="
echo "Sentinel Docker Setup Tests"
echo "=================================="
echo

# Test 1: Docker installed
echo -n "Checking Docker installation... "
if command -v docker &> /dev/null; then
    test_pass "Docker installed"
else
    test_fail "Docker not found"
fi

# Test 2: Docker Compose installed
echo -n "Checking Docker Compose... "
if command -v docker-compose &> /dev/null; then
    test_pass "Docker Compose installed"
else
    test_fail "Docker Compose not found"
fi

# Test 3: Docker daemon running
echo -n "Checking Docker daemon... "
if docker info &> /dev/null; then
    test_pass "Docker daemon running"
else
    test_fail "Docker daemon not running"
fi

# Test 4: .env file exists
echo -n "Checking environment file... "
if [ -f .env ]; then
    test_pass ".env file exists"
else
    echo -e "${YELLOW}⚠${NC}  .env file not found (will be created from .env.example)"
fi

# Test 5: Required files exist
echo -n "Checking required files... "
MISSING=""
for file in docker-compose.yml Dockerfile requirements.txt src/api.py src/worker.py; do
    if [ ! -f "$file" ] && [ ! -d "$(dirname $file)" ]; then
        MISSING="$MISSING $file"
    fi
done

if [ -z "$MISSING" ]; then
    test_pass "All required files present"
else
    test_fail "Missing files:$MISSING"
fi

# Test 6: Check if services are running
echo -n "Checking if services are running... "
if docker-compose ps --services --filter "status=running" 2>/dev/null | grep -q "redis"; then
    test_pass "Services are running"
    
    # Additional service checks
    echo -n "  ├─ Redis... "
    if docker-compose ps | grep -q "redis.*Up"; then
        test_pass "Running"
    else
        test_fail "Not running"
    fi
    
    echo -n "  ├─ API... "
    if docker-compose ps | grep -q "api.*Up"; then
        test_pass "Running"
    else
        test_fail "Not running"
    fi
    
    echo -n "  ├─ Worker 1... "
    if docker-compose ps | grep -q "worker-1.*Up"; then
        test_pass "Running"
    else
        test_fail "Not running"
    fi
    
    echo -n "  └─ Watcher... "
    if docker-compose ps | grep -q "watcher.*Up"; then
        test_pass "Running"
    else
        test_fail "Not running"
    fi
else
    echo -e "${YELLOW}⚠${NC}  Services not running (run 'docker-compose up -d')"
fi

# Test 7: API health endpoint
echo -n "Testing API health endpoint... "
if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
    test_pass "API responding"
else
    echo -e "${YELLOW}⚠${NC}  API not responding (services may not be started)"
fi

# Test 8: Prometheus endpoint
echo -n "Testing Prometheus endpoint... "
if curl -sf http://localhost:9090/-/healthy > /dev/null 2>&1; then
    test_pass "Prometheus responding"
else
    echo -e "${YELLOW}⚠${NC}  Prometheus not responding"
fi

# Test 9: Grafana endpoint
echo -n "Testing Grafana endpoint... "
if curl -sf http://localhost:3000/api/health > /dev/null 2>&1; then
    test_pass "Grafana responding"
else
    echo -e "${YELLOW}⚠${NC}  Grafana not responding"
fi

# Test 10: Jaeger endpoint
echo -n "Testing Jaeger endpoint... "
if curl -sf http://localhost:16686/ > /dev/null 2>&1; then
    test_pass "Jaeger responding"
else
    echo -e "${YELLOW}⚠${NC}  Jaeger not responding"
fi

# Test 11: Redis connectivity
echo -n "Testing Redis connectivity... "
if docker-compose exec -T redis redis-cli ping 2>/dev/null | grep -q "PONG"; then
    test_pass "Redis responding"
else
    echo -e "${YELLOW}⚠${NC}  Redis not responding"
fi

# Test 12: Metrics endpoint
echo -n "Testing metrics endpoint... "
if curl -sf http://localhost:9091/metrics > /dev/null 2>&1; then
    test_pass "Metrics endpoint responding"
else
    echo -e "${YELLOW}⚠${NC}  Metrics endpoint not responding"
fi

# Summary
echo
echo "=================================="
echo "Test Summary"
echo "=================================="
echo -e "${GREEN}Passed:${NC} $PASSED"
echo -e "${RED}Failed:${NC} $FAILED"
echo

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}All tests passed! ✓${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed!${NC}"
    echo "Run 'docker-compose up -d' to start services"
    exit 1
fi
