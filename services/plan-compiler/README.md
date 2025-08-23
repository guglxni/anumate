# Plan Compiler Service

The Plan Compiler service transforms Capsules into ExecutablePlans that can be executed by the Orchestrator service.

## Overview

The Plan Compiler takes a Capsule definition (YAML configuration) and compiles it into an ExecutablePlan - a structured, optimized execution plan that includes:

- Resolved dependencies
- Optimized execution order
- Generated plan_hash for integrity
- Validation results
- Compilation metadata

## Key Features

- **Capsule → ExecutablePlan Transformation**: Converts YAML Capsules to executable plans
- **Dependency Resolution**: Resolves and validates Capsule dependencies
- **Plan Optimization**: Optimizes execution order and resource usage
- **Integrity Verification**: Generates plan_hash for ExecutablePlan integrity
- **Validation**: Comprehensive validation and error reporting
- **Caching**: Caches compiled plans by plan_hash for efficiency
- **Async/Sync Compilation**: Supports both asynchronous and synchronous compilation
- **Advanced Validation**: Multiple validation levels (standard, strict, security-focused)

## API Endpoints

### Compilation Endpoints

#### POST /v1/compile
Compile a Capsule to ExecutablePlan with async/sync support.

**Query Parameters:**
- `async_compilation` (boolean, default: true): Whether to compile asynchronously

**Request Body:**
```json
{
  "capsule_definition": { ... },
  "optimization_level": "standard|performance",
  "validate_dependencies": true,
  "cache_result": true,
  "variables": {},
  "configuration": {}
}
```

#### GET /v1/compile/status/{job_id}
Get compilation job status and optionally the full result.

**Query Parameters:**
- `include_result` (boolean, default: false): Include full compilation result

### Plan Management Endpoints

#### GET /v1/plans/{plan_hash}
Retrieve a compiled ExecutablePlan by hash.

**Query Parameters:**
- `include_cache_metadata` (boolean, default: false): Include cache metadata

#### POST /v1/plans/{plan_hash}/validate
Validate an ExecutablePlan with configurable validation options.

**Request Body:**
```json
{
  "validation_level": "standard|strict|security-focused",
  "include_performance_analysis": true,
  "check_security_policies": true,
  "validate_resource_requirements": true
}
```

#### GET /v1/plans
List cached plans with filtering and pagination.

**Query Parameters:**
- `limit` (int, 1-100, default: 50): Number of plans to return
- `offset` (int, default: 0): Number of plans to skip
- `name_filter` (string): Filter by plan name (partial match)
- `optimization_level` (string): Filter by optimization level
- `validation_status` (string): Filter by validation status

## Architecture

The service consists of:

- **Compiler Engine**: Core compilation logic with async support
- **Dependency Resolver**: Resolves Capsule dependencies
- **Plan Optimizer**: Optimizes execution plans for performance
- **Validator**: Multi-level validation with security checks
- **Cache Manager**: Manages plan caching by hash with metadata
- **API Layer**: Comprehensive REST API endpoints
- **Job Manager**: Handles async compilation jobs

## Usage

### Programmatic Usage

```python
from src.compiler import PlanCompiler
from src.models import CapsuleDefinition

compiler = PlanCompiler()
result = await compiler.compile_capsule(capsule, tenant_id, user_id)

if result.success:
    executable_plan = result.plan
    plan_hash = executable_plan.plan_hash
else:
    errors = result.errors
```

### API Usage

```bash
# Start the API server
uvicorn api.main:app --host 0.0.0.0 --port 8000

# Compile a capsule asynchronously
curl -X POST "http://localhost:8000/v1/compile" \
  -H "X-Tenant-ID: tenant-uuid" \
  -H "X-User-ID: user-uuid" \
  -H "Content-Type: application/json" \
  -d @capsule.json

# Check compilation status
curl "http://localhost:8000/v1/compile/status/{job_id}?include_result=true" \
  -H "X-Tenant-ID: tenant-uuid"

# Get compiled plan
curl "http://localhost:8000/v1/plans/{plan_hash}" \
  -H "X-Tenant-ID: tenant-uuid"

# Validate plan with strict validation
curl -X POST "http://localhost:8000/v1/plans/{plan_hash}/validate" \
  -H "X-Tenant-ID: tenant-uuid" \
  -H "Content-Type: application/json" \
  -d '{"validation_level": "strict"}'
```

## Demo

Run the comprehensive API demo:

```bash
# Start the API server
uvicorn api.main:app --host 0.0.0.0 --port 8000

# In another terminal, run the demo
python demo_api_endpoints.py
```

## Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Run API tests specifically
python -m pytest tests/test_api.py -v

# Run with coverage
python -m pytest tests/ --cov=src --cov=api --cov-report=html
```