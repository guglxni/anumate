# Anumate Platform E2E Test Suite

Comprehensive end-to-end testing framework for the Anumate automation platform, validating the complete golden path flow from Capsule creation through execution and receipt generation.

## Overview

This test suite implements **A.30 - End-to-end golden path testing** with comprehensive coverage of:

- **Golden Path Flow**: Capsule → Plan → GhostRun → Execute → Receipt
- **Service Integration**: Cross-service communication and data consistency
- **Performance Validation**: SLO compliance testing
- **Mock Connectors**: Realistic testing without external dependencies
- **Failure Scenarios**: Error handling and resilience testing

## Architecture

```
tests/
├── conftest.py                 # Shared fixtures and configuration
├── test_runner.py              # Automated test execution
├── pyproject.toml              # Pytest and coverage configuration
├── e2e/                        # End-to-end tests
│   ├── test_golden_path.py     # Main golden path flow tests
│   └── mock_connectors/        # Mock connector implementations
│       └── connector_service.py
├── performance/                # Performance and SLO tests  
│   └── test_slo_validation.py  # SLO compliance validation
├── integration/                # Service integration tests
│   └── test_service_integration.py
└── results/                    # Test results and reports
    ├── coverage_html/          # HTML coverage reports
    └── *.json                  # Test execution results
```

## Test Categories

### 1. Golden Path Tests (`e2e/`)

**Complete flow validation:**
- ✅ Capsule registration and storage
- ✅ Plan compilation from Capsule
- ✅ GhostRun preflight simulation
- ✅ Approval workflow (optional)
- ✅ Execution orchestration via Portia
- ✅ Receipt generation and verification
- ✅ End-to-end data integrity

**Key test cases:**
- `test_golden_path_without_approval()` - Standard automation flow
- `test_golden_path_with_approval()` - High-risk operations requiring approval
- `test_concurrent_golden_paths()` - Scalability and concurrent execution

### 2. Performance Tests (`performance/`)

**SLO Validation:**
- 🎯 **Preflight P95 < 1.5s** - GhostRun simulation performance
- ⚡ **Approval Propagation < 2s** - Approval workflow latency
- 🎯 **Execute Success ≥ 99%** - Execution reliability
- 📡 **Webhook Lag P95 < 5s** - Event processing performance

**Test scenarios:**
- Load testing with concurrent operations
- Performance baseline establishment
- SLO compliance monitoring
- Degradation under stress

### 3. Integration Tests (`integration/`)

**Service-to-Service Communication:**
- Registry ↔ Plan Compiler integration
- Plan Compiler ↔ GhostRun integration
- GhostRun ↔ Approvals integration
- Approvals ↔ Orchestrator integration
- Orchestrator ↔ Receipt integration
- Event bus cross-service communication

**Data Consistency:**
- Cross-service data integrity
- Reference consistency validation
- Transaction boundary testing

### 4. Mock Connectors (`e2e/mock_connectors/`)

**Realistic Testing Environment:**
- HTTP Request Connector - Mock API calls
- Data Transform Connector - Mock data processing
- Database Connector - Mock database operations
- External API Connector - Mock third-party integrations

**Features:**
- Configurable response delays
- Failure simulation (error rates)
- Request/response logging
- Performance metrics

## Quick Start

### Prerequisites

1. **Services Running**: Ensure all Anumate services are healthy
2. **Dependencies**: Install test dependencies
3. **Database**: PostgreSQL with test schema
4. **Redis**: For service registry and caching
5. **NATS**: For event bus functionality

```bash
# Check service health
python tests/test_runner.py --check-services

# Install test dependencies
pip install pytest pytest-asyncio pytest-cov httpx

# Start mock connector service (for isolated testing)
python tests/test_runner.py --start-mocks
```

### Running Tests

```bash
# Run all test suites
python tests/test_runner.py --test-suite all --verbose

# Run specific test suites
python tests/test_runner.py --test-suite e2e
python tests/test_runner.py --test-suite performance  
python tests/test_runner.py --test-suite integration

# Run with coverage
python tests/test_runner.py --test-suite e2e --coverage

# Run specific test
pytest tests/e2e/test_golden_path.py::TestGoldenPathFlow::test_golden_path_without_approval -v
```

### Manual pytest Execution

```bash
# Golden path tests
pytest tests/e2e/ -m golden_path -v --run-e2e

# Performance tests
pytest tests/performance/ -m performance -v --run-performance

# Integration tests
pytest tests/integration/ -m integration -v

# All E2E tests with coverage
pytest tests/ -m e2e --cov=src --cov-report=html --run-e2e
```

## Configuration

### Environment Variables

```bash
# Service endpoints (default: localhost)
export ANUMATE_REGISTRY_URL="http://localhost:8010"
export ANUMATE_PLAN_COMPILER_URL="http://localhost:8030"
export ANUMATE_GHOSTRUN_URL="http://localhost:8040"
export ANUMATE_ORCHESTRATOR_URL="http://localhost:8050"
export ANUMATE_APPROVALS_URL="http://localhost:8060"
export ANUMATE_CAPTOKENS_URL="http://localhost:8070"
export ANUMATE_RECEIPT_URL="http://localhost:8080"
export ANUMATE_EVENTBUS_URL="http://localhost:8090"
export ANUMATE_INTEGRATION_URL="http://localhost:8100"

# Database
export ANUMATE_DB_URL="postgresql://anumate_admin:dev_password@localhost:5432/anumate_e2e_test"

# Test configuration
export ANUMATE_TEST_TENANT_ID="12345678-1234-1234-1234-123456789012"
export ANUMATE_TEST_TIMEOUT="300"
export ANUMATE_TEST_PARALLEL="true"
```

### Service Port Configuration

| Service | Default Port | Health Endpoint |
|---------|--------------|-----------------|
| Registry | 8010 | `/health` |
| Policy | 8020 | `/health` |
| Plan Compiler | 8030 | `/health` |
| GhostRun | 8040 | `/health` |
| Orchestrator | 8050 | `/health` |
| Approvals | 8060 | `/health` |
| CapTokens | 8070 | `/health` |
| Receipt | 8080 | `/health` |
| EventBus | 8090 | `/health` |
| Integration | 8100 | `/health` |
| Mock Connectors | 9000 | `/health` |

## Test Data

### Sample Test Capsule

```yaml
name: "e2e-test-capsule"
version: "1.0.0"
description: "End-to-end test automation capsule"
capabilities:
  - http_request
  - data_transform
steps:
  - name: "fetch_data"
    type: "http_request"
    config:
      method: "GET"
      url: "https://api.example.com/data"
      timeout: 30
  - name: "process_data"
    type: "data_transform"
    config:
      operation: "filter"
      criteria:
        status: "active"
```

### Mock Response Examples

```json
{
  "http_request": {
    "status_code": 200,
    "headers": {"Content-Type": "application/json"},
    "body": {
      "status": "success",
      "data": [
        {"id": 1, "status": "active"},
        {"id": 2, "status": "inactive"}
      ]
    }
  }
}
```

## Performance SLO Targets

| Metric | Target | Test Method |
|--------|--------|-------------|
| **Preflight P95** | < 1.5s | GhostRun simulation latency |
| **Approval Propagation** | < 2s | Request → Grant time |
| **Execute Success Rate** | ≥ 99% | Reliability over 100+ runs |
| **Webhook Lag P95** | < 5s | Event processing latency |
| **End-to-End Flow** | < 60s | Complete golden path |

## Results and Reporting

### Test Results

Results are automatically saved to `tests/results/` with timestamps:

```bash
tests/results/
├── e2e_results_20250824_143022.json
├── e2e_latest.json
├── performance_results_20250824_143155.json
├── integration_latest.json
└── all_suites_results_20250824_144500.json
```

### Coverage Reports

HTML coverage reports are generated in `tests/results/coverage_html/`:

```bash
# View coverage report
open tests/results/coverage_html/index.html
```

### Performance Metrics

Performance test results include detailed timing analysis:

```json
{
  "suite": "performance",
  "slo_compliance": {
    "preflight_p95": true,
    "approval_propagation": true,
    "execute_success_rate": true
  },
  "metrics": {
    "preflight_p95_ms": 1234.5,
    "approval_mean_ms": 456.7,
    "success_rate": 0.99
  }
}
```

## Troubleshooting

### Common Issues

**Services Not Healthy**
```bash
# Check individual service status
curl http://localhost:8010/health  # Registry
curl http://localhost:8030/health  # Plan Compiler
curl http://localhost:8040/health  # GhostRun

# Check service logs
docker logs anumate-registry
docker logs anumate-plan-compiler
```

**Database Connection Issues**
```bash
# Verify database is running
docker ps | grep postgres

# Test connection
psql -h localhost -U anumate_admin -d anumate_e2e_test -c "SELECT 1;"
```

**Test Timeouts**
```bash
# Increase timeout for slow environments
export ANUMATE_TEST_TIMEOUT="600"

# Run tests with longer timeout
pytest tests/e2e/ --timeout=600
```

**Mock Connector Issues**
```bash
# Start mock service manually
python tests/e2e/mock_connectors/connector_service.py

# Check mock service
curl http://localhost:9000/health
curl http://localhost:9000/connectors/types
```

### Debug Mode

Enable detailed debugging:

```bash
# Verbose pytest output
pytest tests/e2e/ -v -s --tb=long

# Enable debug logging
export ANUMATE_LOG_LEVEL="DEBUG"

# Capture service output
python tests/test_runner.py --test-suite e2e --verbose 2>&1 | tee test_debug.log
```

### Service Dependencies

The test suite requires these services to be running:

1. **PostgreSQL** - Data persistence
2. **Redis** - Service registry and caching  
3. **NATS** - Event bus
4. **All Anumate Services** - Registry, Plan Compiler, GhostRun, etc.

**Docker Compose Setup:**
```bash
# Start infrastructure services
docker-compose -f ops/docker-compose.infrastructure.yml up -d

# Start Anumate services
docker-compose -f ops/docker-compose.yml up -d

# Verify all services
python tests/test_runner.py --check-services
```

## Extending Tests

### Adding New Test Cases

1. **Golden Path Extensions:**
   ```python
   # tests/e2e/test_golden_path.py
   @pytest.mark.golden_path
   async def test_golden_path_with_custom_approval(e2e_context, custom_capsule):
       # Your test implementation
   ```

2. **Performance Tests:**
   ```python
   # tests/performance/test_slo_validation.py
   @pytest.mark.performance
   async def test_custom_slo_validation(e2e_context, performance_requirements):
       # Your performance test
   ```

3. **Integration Tests:**
   ```python
   # tests/integration/test_service_integration.py
   @pytest.mark.integration
   async def test_new_service_integration(e2e_context):
       # Your integration test
   ```

### Custom Mock Connectors

```python
# tests/e2e/mock_connectors/custom_connector.py
class MockCustomConnector(MockConnectorBase):
    def __init__(self):
        super().__init__("custom_connector", response_delay_ms=150)
    
    async def _execute_operation(self, operation: str, config: Dict, context: Dict) -> Dict:
        # Your custom connector logic
        return {"result": "custom response"}
```

### Custom Fixtures

```python
# tests/conftest.py
@pytest.fixture
async def custom_test_data():
    """Your custom test data fixture"""
    return {"custom": "data"}
```

## CI/CD Integration

### GitHub Actions

```yaml
# .github/workflows/e2e-tests.yml
name: E2E Tests
on: [push, pull_request]
jobs:
  e2e-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Start Services
        run: docker-compose up -d
      - name: Run E2E Tests
        run: python tests/test_runner.py --test-suite all
      - name: Upload Results
        uses: actions/upload-artifact@v3
        with:
          name: test-results
          path: tests/results/
```

### Jenkins Pipeline

```groovy
// Jenkinsfile
pipeline {
    agent any
    stages {
        stage('Setup') {
            steps {
                sh 'docker-compose up -d'
                sh 'pip install -r requirements-test.txt'
            }
        }
        stage('E2E Tests') {
            steps {
                sh 'python tests/test_runner.py --test-suite all --coverage'
            }
            post {
                always {
                    publishHTML([
                        allowMissing: false,
                        alwaysLinkToLastBuild: true,
                        keepAll: true,
                        reportDir: 'tests/results/coverage_html',
                        reportFiles: 'index.html',
                        reportName: 'Coverage Report'
                    ])
                }
            }
        }
    }
}
```

## Contributing

### Test Development Guidelines

1. **Follow naming conventions:** `test_*` for functions, `Test*` for classes
2. **Use appropriate markers:** `@pytest.mark.e2e`, `@pytest.mark.performance`, etc.
3. **Implement proper cleanup:** Use fixtures and context managers
4. **Add comprehensive assertions:** Validate all expected behaviors
5. **Include performance expectations:** Document expected timing
6. **Handle errors gracefully:** Test both success and failure scenarios

### Code Quality

```bash
# Run linting
flake8 tests/
black tests/
isort tests/

# Type checking  
mypy tests/

# Security scanning
bandit -r tests/
```

## License

This test suite is part of the Anumate platform and follows the same licensing terms.

---

## Summary

This comprehensive E2E test suite provides complete validation of the Anumate platform's core functionality, ensuring reliability, performance, and correctness of the automation platform. The golden path tests validate the complete user journey, while performance and integration tests ensure the platform meets its operational requirements.

**Key Features:**
- ✅ Complete golden path flow validation  
- 🎯 SLO compliance testing
- 🔧 Mock connector framework
- 📊 Comprehensive reporting
- 🚀 Automated test execution
- 🔍 End-to-end data integrity validation

Ready for production deployment and continuous validation of the Anumate automation platform!
