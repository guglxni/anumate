#!/usr/bin/env python3
"""
Comprehensive integration tests for A.26 Receipt API endpoints
Tests all API endpoints with real service integration
"""

import asyncio
import json
import uuid
import aiohttp
import time
from datetime import datetime, timezone
from typing import Dict, Any, List

class ReceiptServiceIntegrationTester:
    def __init__(self, base_url: str = "http://localhost:8001"):
        self.base_url = base_url
        self.tenant_id = "12345678-1234-1234-1234-123456789012"
        self.session = None
        self.test_results = []
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    def log_test(self, test_name: str, success: bool, details: str):
        """Log test results"""
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status}: {test_name}")
        if details:
            print(f"   Details: {details}")
        
        self.test_results.append({
            "test": test_name,
            "success": success,
            "details": details,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
    
    async def test_service_health(self):
        """Test service health and basic information"""
        try:
            async with self.session.get(f"{self.base_url}/") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self.log_test(
                        "Service Health Check",
                        True,
                        f"Service: {data.get('service')}, Version: {data.get('version')}, Status: {data.get('status')}"
                    )
                    return True
                else:
                    self.log_test("Service Health Check", False, f"HTTP {resp.status}")
                    return False
        except Exception as e:
            self.log_test("Service Health Check", False, f"Connection error: {e}")
            return False
    
    async def test_create_receipt_endpoint(self) -> str:
        """Test POST /v1/receipts - Create receipt"""
        receipt_data = {
            "receipt_type": "execution",
            "subject": "Integration test execution receipt",
            "reference_id": str(uuid.uuid4()),
            "receipt_data": {
                "execution_summary": "Test execution",
                "steps_completed": 3,
                "total_steps": 3,
                "execution_time": "2.5s",
                "capsule_id": str(uuid.uuid4()),
                "plan_version": "1.0.0",
                "plan_hash": "sha256:" + "a" * 64
            },
            "compliance_tags": {
                "environment": "integration-test",
                "region": "us-west-2",
                "user_id": "test-user-123"
            },
            "retention_days": 365
        }
        
        headers = {
            "Content-Type": "application/json",
            "X-Tenant-Id": self.tenant_id
        }
        
        try:
            async with self.session.post(
                f"{self.base_url}/v1/receipts",
                json=receipt_data,
                headers=headers
            ) as resp:
                if resp.status in [200, 201]:  # Accept both 200 and 201 as success
                    data = await resp.json()
                    receipt_id = data.get("receipt_id")
                    self.log_test(
                        "Create Receipt",
                        True,
                        f"Receipt created: {receipt_id}, Signature present: {bool(data.get('signature'))}"
                    )
                    return receipt_id
                else:
                    error_text = await resp.text()
                    self.log_test("Create Receipt", False, f"HTTP {resp.status}: {error_text}")
                    return None
        except Exception as e:
            self.log_test("Create Receipt", False, f"Request error: {e}")
            return None
    
    async def test_get_receipt_endpoint(self, receipt_id: str):
        """Test GET /v1/receipts/{id} - Retrieve receipt"""
        if not receipt_id:
            self.log_test("Get Receipt", False, "No receipt ID to test with")
            return
        
        headers = {"X-Tenant-Id": self.tenant_id}
        
        try:
            async with self.session.get(
                f"{self.base_url}/v1/receipts/{receipt_id}",
                headers=headers
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self.log_test(
                        "Get Receipt",
                        True,
                        f"Receipt retrieved: {data.get('receipt_id')}, Content hash: {data.get('content_hash', '')[:16]}..."
                    )
                    return data
                else:
                    error_text = await resp.text()
                    self.log_test("Get Receipt", False, f"HTTP {resp.status}: {error_text}")
                    return None
        except Exception as e:
            self.log_test("Get Receipt", False, f"Request error: {e}")
            return None
    
    async def test_verify_receipt_endpoint(self, receipt_id: str):
        """Test POST /v1/receipts/{id}/verify - Verify receipt integrity"""
        if not receipt_id:
            self.log_test("Verify Receipt", False, "No receipt ID to test with")
            return
        
        headers = {
            "Content-Type": "application/json",
            "X-Tenant-Id": self.tenant_id
        }
        
        verify_data = {
            "verify_signature": True,
            "verify_worm_storage": False,
            "update_verification_timestamp": True
        }
        
        try:
            async with self.session.post(
                f"{self.base_url}/v1/receipts/{receipt_id}/verify",
                json=verify_data,
                headers=headers
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self.log_test(
                        "Verify Receipt",
                        True,
                        f"Verification result: Valid: {data.get('is_valid')}, Content hash valid: {data.get('content_hash_valid')}, Signature valid: {data.get('signature_valid')}"
                    )
                    return data
                else:
                    error_text = await resp.text()
                    self.log_test("Verify Receipt", False, f"HTTP {resp.status}: {error_text}")
                    return None
        except Exception as e:
            self.log_test("Verify Receipt", False, f"Request error: {e}")
            return None
    
    async def test_audit_logs_endpoint(self):
        """Test GET /v1/receipts/audit - Get audit logs"""
        headers = {"X-Tenant-Id": self.tenant_id}
        
        try:
            async with self.session.get(
                f"{self.base_url}/v1/receipts/audit",
                headers=headers
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # Handle both list response and dict response formats
                    if isinstance(data, list):
                        audit_logs = data
                        self.log_test(
                            "Get Audit Logs",
                            True,
                            f"Retrieved {len(audit_logs)} audit log entries"
                        )
                    else:
                        audit_logs = data.get("audit_logs", [])
                        self.log_test(
                            "Get Audit Logs",
                            True,
                            f"Retrieved {len(audit_logs)} audit log entries"
                        )
                    return data
                else:
                    error_text = await resp.text()
                    self.log_test("Get Audit Logs", False, f"HTTP {resp.status}: {error_text}")
                    return None
        except Exception as e:
            self.log_test("Get Audit Logs", False, f"Request error: {e}")
            return None
    
    async def test_error_conditions(self):
        """Test error handling scenarios"""
        headers = {
            "Content-Type": "application/json",
            "X-Tenant-Id": self.tenant_id
        }
        
        # Test invalid tenant ID
        invalid_headers = {
            "Content-Type": "application/json",
            "X-Tenant-Id": "invalid-tenant-id"
        }
        
        try:
            async with self.session.get(
                f"{self.base_url}/v1/receipts/audit",
                headers=invalid_headers
            ) as resp:
                if resp.status in [400, 422]:  # Accept both validation error codes
                    self.log_test("Invalid Tenant ID", True, f"Properly rejected invalid tenant ID (HTTP {resp.status})")
                else:
                    self.log_test("Invalid Tenant ID", False, f"Expected 400/422, got {resp.status}")
        except Exception as e:
            self.log_test("Invalid Tenant ID", False, f"Request error: {e}")
        
        # Test non-existent receipt
        try:
            fake_receipt_id = str(uuid.uuid4())
            async with self.session.get(
                f"{self.base_url}/v1/receipts/{fake_receipt_id}",
                headers=headers
            ) as resp:
                if resp.status == 404:
                    self.log_test("Non-existent Receipt", True, "Properly returned 404 for non-existent receipt")
                else:
                    self.log_test("Non-existent Receipt", False, f"Expected 404, got {resp.status}")
        except Exception as e:
            self.log_test("Non-existent Receipt", False, f"Request error: {e}")
    
    async def test_api_documentation(self):
        """Test OpenAPI documentation availability"""
        try:
            async with self.session.get(f"{self.base_url}/docs") as resp:
                if resp.status == 200:
                    self.log_test("API Documentation", True, "Swagger UI available at /docs")
                else:
                    self.log_test("API Documentation", False, f"HTTP {resp.status}")
        except Exception as e:
            self.log_test("API Documentation", False, f"Request error: {e}")
        
        try:
            async with self.session.get(f"{self.base_url}/openapi.json") as resp:
                if resp.status == 200:
                    self.log_test("OpenAPI Spec", True, "OpenAPI 3.0 specification available")
                else:
                    self.log_test("OpenAPI Spec", False, f"HTTP {resp.status}")
        except Exception as e:
            self.log_test("OpenAPI Spec", False, f"Request error: {e}")
    
    async def run_comprehensive_integration_test(self):
        """Run all integration tests"""
        print("🚀 Starting A.26 Receipt Service Integration Tests")
        print("=" * 60)
        
        start_time = time.time()
        
        # Test service health
        if not await self.test_service_health():
            print("❌ Service is not healthy, aborting tests")
            return False
        
        # Test API documentation
        await self.test_api_documentation()
        
        # Test main workflow
        receipt_id = await self.test_create_receipt_endpoint()
        if receipt_id:  # Only proceed if we got a receipt ID
            await self.test_get_receipt_endpoint(receipt_id)
            await self.test_verify_receipt_endpoint(receipt_id)
        await self.test_audit_logs_endpoint()
        
        # Test error conditions
        await self.test_error_conditions()
        
        # Calculate results
        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results if result["success"])
        failed_tests = total_tests - passed_tests
        
        elapsed_time = time.time() - start_time
        
        print("\n" + "=" * 60)
        print("🏁 A.26 Integration Test Results")
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {failed_tests}")
        print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
        print(f"Execution Time: {elapsed_time:.2f}s")
        
        if failed_tests == 0:
            print("✅ ALL TESTS PASSED - A.26 Integration Ready!")
            return True
        else:
            print(f"❌ {failed_tests} tests failed - Check issues before deployment")
            return False

async def main():
    """Main integration test runner"""
    async with ReceiptServiceIntegrationTester() as tester:
        success = await tester.run_comprehensive_integration_test()
        
        # Save test results
        test_report = {
            "test_suite": "A.26 Receipt Service Integration",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "success": success,
            "results": tester.test_results
        }
        
        with open("/Users/aaryanguglani/anumate/services/receipt/integration_test_results.json", "w") as f:
            json.dump(test_report, f, indent=2)
        
        print(f"\n📊 Test report saved to integration_test_results.json")
        return 0 if success else 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
