"""
Anumate Platform E2E Test Configuration

This module provides shared pytest fixtures and configuration for end-to-end testing
of the complete Anumate platform, including the golden path:
Capsule → Plan → GhostRun → Execute
"""

import asyncio
import json
import os
import time
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, AsyncGenerator
from uuid import UUID

import httpx
import pytest
import pytest_asyncio
from pydantic import BaseModel, Field

# Test environment configuration
TEST_CONFIG = {
    "services": {
        "registry": {"host": "localhost", "port": 8010, "timeout": 30},
        "policy": {"host": "localhost", "port": 8020, "timeout": 30}, 
        "plan_compiler": {"host": "localhost", "port": 8030, "timeout": 60},
        "ghostrun": {"host": "localhost", "port": 8040, "timeout": 90},
        "orchestrator": {"host": "localhost", "port": 8050, "timeout": 120},
        "approvals": {"host": "localhost", "port": 8060, "timeout": 30},
        "captokens": {"host": "localhost", "port": 8070, "timeout": 30},
        "receipt": {"host": "localhost", "port": 8080, "timeout": 30},
        "eventbus": {"host": "localhost", "port": 8090, "timeout": 30},
        "integration": {"host": "localhost", "port": 8100, "timeout": 30},
    },
    "database": {
        "host": "localhost",
        "port": 5432,
        "database": "anumate_e2e_test",
        "user": "anumate_admin",
        "password": "dev_password"
    },
    "redis": {
        "host": "localhost",
        "port": 6379,
        "db": 1  # Use different db for tests
    },
    "nats": {
        "servers": ["nats://localhost:4222"]
    },
    "test_tenant_id": "12345678-1234-1234-1234-123456789012",
    "slo_targets": {
        "preflight_p95_ms": 1500,  # GhostRun preflight < 1.5s
        "approval_propagation_ms": 2000,  # Approval < 2s
        "execute_success_rate": 0.99,  # Execute ≥ 99%
        "webhook_lag_p95_ms": 5000,  # Webhook lag < 5s
    }
}


class TestCapsule(BaseModel):
    """Test capsule for E2E testing"""
    name: str
    version: str = "1.0.0"
    description: str
    metadata: Dict = Field(default_factory=dict)
    requires_approval: bool = False
    capabilities: List[str] = Field(default_factory=list)
    steps: List[Dict] = Field(default_factory=list)


class TestServiceClient:
    """HTTP client for service communication during tests"""
    
    def __init__(self, service_name: str, base_url: str, timeout: int = 30):
        self.service_name = service_name
        self.base_url = base_url
        self.timeout = timeout
        self.client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            headers={"X-Tenant-Id": TEST_CONFIG["test_tenant_id"]}
        )
    
    async def health_check(self) -> bool:
        """Check if service is healthy"""
        try:
            response = await self.client.get("/health")
            return response.status_code == 200
        except Exception:
            return False
    
    async def wait_for_health(self, max_wait: int = 60) -> bool:
        """Wait for service to become healthy"""
        start_time = time.time()
        while time.time() - start_time < max_wait:
            if await self.health_check():
                return True
            await asyncio.sleep(1)
        return False
    
    async def get(self, path: str, **kwargs) -> httpx.Response:
        """GET request"""
        return await self.client.get(path, **kwargs)
    
    async def post(self, path: str, **kwargs) -> httpx.Response:
        """POST request"""
        return await self.client.post(path, **kwargs)
    
    async def put(self, path: str, **kwargs) -> httpx.Response:
        """PUT request"""
        return await self.client.put(path, **kwargs)
    
    async def delete(self, path: str, **kwargs) -> httpx.Response:
        """DELETE request"""
        return await self.client.delete(path, **kwargs)
    
    async def close(self):
        """Close client"""
        await self.client.aclose()


class E2ETestContext:
    """Context for E2E test execution"""
    
    def __init__(self):
        self.test_id = str(uuid.uuid4())
        self.tenant_id = TEST_CONFIG["test_tenant_id"]
        self.services: Dict[str, TestServiceClient] = {}
        self.metrics: Dict[str, List[float]] = {
            "preflight_times": [],
            "approval_times": [],
            "execute_times": [],
            "webhook_lags": []
        }
        self.test_data: Dict = {}
        self.cleanup_tasks: List = []
    
    async def setup_services(self):
        """Initialize service clients"""
        for name, config in TEST_CONFIG["services"].items():
            base_url = f"http://{config['host']}:{config['port']}"
            self.services[name] = TestServiceClient(
                service_name=name,
                base_url=base_url,
                timeout=config['timeout']
            )
    
    async def wait_for_services(self) -> Dict[str, bool]:
        """Wait for all services to be healthy"""
        results = {}
        tasks = []
        
        for name, client in self.services.items():
            tasks.append((name, client.wait_for_health()))
        
        for name, task in tasks:
            results[name] = await task
            if not results[name]:
                print(f"⚠️  Service {name} failed to become healthy")
            else:
                print(f"✅ Service {name} is healthy")
        
        return results
    
    async def cleanup(self):
        """Clean up test resources"""
        # Execute cleanup tasks
        for task in reversed(self.cleanup_tasks):
            try:
                await task()
            except Exception as e:
                print(f"Cleanup task failed: {e}")
        
        # Close service clients
        for client in self.services.values():
            await client.close()
    
    def record_timing(self, metric_name: str, duration_ms: float):
        """Record timing metric"""
        if metric_name in self.metrics:
            self.metrics[metric_name].append(duration_ms)


@pytest_asyncio.fixture(scope="session")
async def e2e_context() -> AsyncGenerator[E2ETestContext, None]:
    """E2E test context fixture"""
    context = E2ETestContext()
    
    try:
        # Setup services
        await context.setup_services()
        
        # Wait for services to be ready
        service_health = await context.wait_for_services()
        
        # Check if critical services are healthy
        critical_services = ["registry", "plan_compiler", "ghostrun", "orchestrator"]
        unhealthy_critical = [
            name for name in critical_services
            if not service_health.get(name, False)
        ]
        
        if unhealthy_critical:
            pytest.skip(f"Critical services unhealthy: {unhealthy_critical}")
        
        print(f"🚀 E2E test environment ready (test_id: {context.test_id})")
        yield context
        
    finally:
        await context.cleanup()
        print(f"🧹 E2E test cleanup complete (test_id: {context.test_id})")


@pytest_asyncio.fixture
async def test_capsule() -> TestCapsule:
    """Sample test capsule for E2E testing"""
    return TestCapsule(
        name=f"test-capsule-{int(time.time())}",
        version="1.0.0",
        description="End-to-end test capsule",
        metadata={
            "test_id": str(uuid.uuid4()),
            "created_at": datetime.utcnow().isoformat(),
            "test_type": "e2e_golden_path"
        },
        requires_approval=False,
        capabilities=["http_request", "data_transform"],
        steps=[
            {
                "name": "fetch_data",
                "type": "http_request",
                "config": {
                    "method": "GET",
                    "url": "https://api.example.com/data",
                    "timeout": 30
                }
            },
            {
                "name": "process_data",
                "type": "data_transform",
                "config": {
                    "operation": "filter",
                    "criteria": {"status": "active"}
                }
            },
            {
                "name": "store_result",
                "type": "http_request",
                "config": {
                    "method": "POST",
                    "url": "https://api.example.com/results",
                    "timeout": 30
                }
            }
        ]
    )


@pytest_asyncio.fixture
async def test_capsule_with_approval() -> TestCapsule:
    """Test capsule that requires approval"""
    return TestCapsule(
        name=f"approval-capsule-{int(time.time())}",
        version="1.0.0",
        description="End-to-end test capsule requiring approval",
        metadata={
            "test_id": str(uuid.uuid4()),
            "requires_manual_review": True,
            "risk_level": "medium"
        },
        requires_approval=True,
        capabilities=["http_request", "database_write", "external_api"],
        steps=[
            {
                "name": "update_user_data",
                "type": "database_write",
                "config": {
                    "table": "users",
                    "operation": "update",
                    "conditions": {"status": "pending"}
                }
            },
            {
                "name": "notify_external_system",
                "type": "external_api",
                "config": {
                    "api_endpoint": "https://partner.api.com/notify",
                    "method": "POST",
                    "sensitive_data": True
                }
            }
        ]
    )


@pytest.fixture
def performance_requirements() -> Dict[str, float]:
    """SLO performance requirements for testing"""
    return TEST_CONFIG["slo_targets"]


@pytest.fixture
def mock_connector_registry() -> Dict[str, Dict]:
    """Registry of mock connectors for testing"""
    return {
        "http_request": {
            "name": "Mock HTTP Connector",
            "description": "Mock HTTP requests for testing",
            "capabilities": ["GET", "POST", "PUT", "DELETE"],
            "response_delay_ms": 100
        },
        "data_transform": {
            "name": "Mock Data Transform Connector",
            "description": "Mock data transformation for testing", 
            "capabilities": ["filter", "map", "reduce", "sort"],
            "response_delay_ms": 50
        },
        "database_write": {
            "name": "Mock Database Connector",
            "description": "Mock database operations for testing",
            "capabilities": ["insert", "update", "delete"],
            "response_delay_ms": 200
        },
        "external_api": {
            "name": "Mock External API Connector",
            "description": "Mock external API calls for testing",
            "capabilities": ["webhook", "notification", "integration"],
            "response_delay_ms": 300
        }
    }


class GoldenPathMetrics:
    """Metrics collection for golden path testing"""
    
    def __init__(self):
        self.reset()
    
    def reset(self):
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.capsule_register_time: Optional[datetime] = None
        self.plan_compile_time: Optional[datetime] = None
        self.ghostrun_complete_time: Optional[datetime] = None
        self.approval_time: Optional[datetime] = None
        self.execute_start_time: Optional[datetime] = None
        self.execute_complete_time: Optional[datetime] = None
        self.receipt_time: Optional[datetime] = None
        
        self.timings: Dict[str, float] = {}
        self.success_count: int = 0
        self.failure_count: int = 0
        self.errors: List[Dict] = []
    
    def start_flow(self):
        """Start timing the golden path flow"""
        self.start_time = datetime.utcnow()
    
    def mark_capsule_registered(self):
        self.capsule_register_time = datetime.utcnow()
        if self.start_time:
            self.timings["capsule_register_ms"] = (
                self.capsule_register_time - self.start_time
            ).total_seconds() * 1000
    
    def mark_plan_compiled(self):
        self.plan_compile_time = datetime.utcnow()
        if self.capsule_register_time:
            self.timings["plan_compile_ms"] = (
                self.plan_compile_time - self.capsule_register_time
            ).total_seconds() * 1000
    
    def mark_ghostrun_complete(self):
        self.ghostrun_complete_time = datetime.utcnow()
        if self.plan_compile_time:
            self.timings["ghostrun_ms"] = (
                self.ghostrun_complete_time - self.plan_compile_time
            ).total_seconds() * 1000
    
    def mark_approval_complete(self):
        self.approval_time = datetime.utcnow()
        if self.ghostrun_complete_time:
            self.timings["approval_ms"] = (
                self.approval_time - self.ghostrun_complete_time
            ).total_seconds() * 1000
    
    def mark_execute_start(self):
        self.execute_start_time = datetime.utcnow()
    
    def mark_execute_complete(self, success: bool = True):
        self.execute_complete_time = datetime.utcnow()
        if self.execute_start_time:
            self.timings["execute_ms"] = (
                self.execute_complete_time - self.execute_start_time
            ).total_seconds() * 1000
        
        if success:
            self.success_count += 1
        else:
            self.failure_count += 1
    
    def mark_receipt_generated(self):
        self.receipt_time = datetime.utcnow()
        if self.execute_complete_time:
            self.timings["receipt_ms"] = (
                self.receipt_time - self.execute_complete_time
            ).total_seconds() * 1000
    
    def complete_flow(self):
        """Complete timing the golden path flow"""
        self.end_time = datetime.utcnow()
        if self.start_time:
            self.timings["total_flow_ms"] = (
                self.end_time - self.start_time
            ).total_seconds() * 1000
    
    def record_error(self, stage: str, error: str, details: Dict = None):
        """Record an error during the flow"""
        self.errors.append({
            "stage": stage,
            "error": error,
            "details": details or {},
            "timestamp": datetime.utcnow().isoformat()
        })
    
    def get_summary(self) -> Dict:
        """Get metrics summary"""
        total_runs = self.success_count + self.failure_count
        success_rate = self.success_count / total_runs if total_runs > 0 else 0
        
        return {
            "total_runs": total_runs,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "success_rate": success_rate,
            "timings": self.timings,
            "errors": self.errors,
            "slo_compliance": {
                "preflight_p95": self.timings.get("ghostrun_ms", 0) <= TEST_CONFIG["slo_targets"]["preflight_p95_ms"],
                "approval_propagation": self.timings.get("approval_ms", 0) <= TEST_CONFIG["slo_targets"]["approval_propagation_ms"],
                "execute_success_rate": success_rate >= TEST_CONFIG["slo_targets"]["execute_success_rate"],
            }
        }


@pytest.fixture
def golden_path_metrics() -> GoldenPathMetrics:
    """Metrics collection fixture for golden path testing"""
    return GoldenPathMetrics()


# Pytest configuration
def pytest_configure(config):
    """Configure pytest for Anumate E2E testing"""
    config.addinivalue_line(
        "markers", 
        "e2e: mark test as end-to-end integration test"
    )
    config.addinivalue_line(
        "markers",
        "golden_path: mark test as golden path flow test"
    )
    config.addinivalue_line(
        "markers",
        "performance: mark test as performance/SLO validation test"
    )
    config.addinivalue_line(
        "markers",
        "slow: mark test as slow running (>10s)"
    )


def pytest_collection_modifyitems(config, items):
    """Modify test collection for E2E tests"""
    for item in items:
        # Add slow marker to tests that might take a while
        if "e2e" in item.keywords or "golden_path" in item.keywords:
            item.add_marker(pytest.mark.slow)
        
        # Skip E2E tests unless explicitly requested
        if "e2e" in item.keywords and not config.getoption("--run-e2e", False):
            item.add_marker(pytest.mark.skip(reason="E2E tests skipped (use --run-e2e to run)"))


def pytest_addoption(parser):
    """Add custom pytest options"""
    parser.addoption(
        "--run-e2e",
        action="store_true",
        default=False,
        help="Run end-to-end tests (requires services to be running)"
    )
    parser.addoption(
        "--run-performance",
        action="store_true", 
        default=False,
        help="Run performance tests for SLO validation"
    )
    parser.addoption(
        "--service-timeout",
        action="store",
        default=60,
        type=int,
        help="Timeout in seconds to wait for services to be ready"
    )


# Test utilities
async def wait_for_condition(condition_func, timeout: int = 30, interval: float = 1.0) -> bool:
    """Wait for a condition to become true"""
    start_time = time.time()
    while time.time() - start_time < timeout:
        if await condition_func():
            return True
        await asyncio.sleep(interval)
    return False


async def poll_until_complete(
    client: TestServiceClient, 
    endpoint: str, 
    completion_condition: callable,
    timeout: int = 60,
    interval: float = 2.0
) -> Optional[Dict]:
    """Poll an endpoint until completion condition is met"""
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        try:
            response = await client.get(endpoint)
            if response.status_code == 200:
                data = response.json()
                if completion_condition(data):
                    return data
        except Exception as e:
            print(f"Polling error: {e}")
        
        await asyncio.sleep(interval)
    
    return None
