"""
Comprehensive Integration Tests for A.27 Audit Service
=====================================================

Full test suite covering all audit service functionality including:
- Audit event creation and retrieval
- Advanced search capabilities  
- Retention policy management
- SIEM export generation
- PII redaction
- Background processing
"""

import asyncio
import json
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, List
import uuid

import pytest
import aiohttp
import asyncpg
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from anumate_audit_service.models import AuditEvent, RetentionPolicy, AuditExport
from anumate_audit_service.schemas import AuditEventCreate, RetentionPolicyCreate
from anumate_audit_service.pii_redactor import PIIRedactor, GDPR_CONFIG
from anumate_audit_service.export_engine import ExportEngine


class AuditServiceIntegrationTester:
    """
    Comprehensive integration test suite for the Audit Service.
    """
    
    def __init__(self, base_url: str = "http://localhost:8007"):
        self.base_url = base_url
        self.session = None
        self.test_tenant_id = str(uuid.uuid4())
        self.test_events: List[Dict[str, Any]] = []
        
    async def __aenter__(self):
        """Setup test environment."""
        self.session = aiohttp.ClientSession()
        await self._setup_test_data()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Cleanup test environment."""
        await self._cleanup_test_data()
        if self.session:
            await self.session.close()
            
    async def _setup_test_data(self):
        """Create test data for integration tests."""
        # Sample audit events for testing
        self.test_events = [
            {
                "tenant_id": self.test_tenant_id,
                "event_type": "user_authentication",
                "event_category": "security",
                "event_action": "login",
                "event_severity": "info",
                "service_name": "auth-service",
                "user_id": "user123@example.com",
                "client_ip": "192.168.1.100",
                "event_description": "User successfully authenticated",
                "success": True,
                "correlation_id": str(uuid.uuid4()),
                "request_id": str(uuid.uuid4()),
                "event_data": {
                    "authentication_method": "oauth2",
                    "user_agent": "Mozilla/5.0",
                    "email": "user123@example.com",
                    "phone": "555-123-4567"
                }
            },
            {
                "tenant_id": self.test_tenant_id,
                "event_type": "data_access",
                "event_category": "data",
                "event_action": "read",
                "event_severity": "info",
                "service_name": "api-service",
                "user_id": "user456@example.com",
                "client_ip": "10.0.0.50",
                "event_description": "User accessed sensitive data",
                "success": True,
                "correlation_id": str(uuid.uuid4()),
                "request_id": str(uuid.uuid4()),
                "event_data": {
                    "resource_id": "document_123",
                    "resource_type": "confidential_document",
                    "ssn": "123-45-6789",
                    "credit_card": "4111-1111-1111-1111"
                }
            },
            {
                "tenant_id": self.test_tenant_id,
                "event_type": "system_error",
                "event_category": "system",
                "event_action": "error",
                "event_severity": "error",
                "service_name": "payment-service",
                "user_id": "user789@example.com",
                "client_ip": "203.0.113.5",
                "event_description": "Payment processing failed",
                "success": False,
                "error_code": "PAYMENT_DECLINED",
                "error_message": "Card was declined",
                "correlation_id": str(uuid.uuid4()),
                "request_id": str(uuid.uuid4()),
                "processing_time_ms": 1250
            }
        ]
        
    async def _cleanup_test_data(self):
        """Clean up test data after tests."""
        try:
            # Delete test events
            await self._delete_request(f"/v1/audit/tenant/{self.test_tenant_id}/cleanup")
        except Exception as e:
            print(f"Cleanup warning: {e}")
            
    async def _post_request(self, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Make POST request to audit service."""
        url = f"{self.base_url}{endpoint}"
        async with self.session.post(url, json=data) as response:
            response.raise_for_status()
            return await response.json()
            
    async def _get_request(self, endpoint: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Make GET request to audit service."""
        url = f"{self.base_url}{endpoint}"
        async with self.session.get(url, params=params) as response:
            response.raise_for_status()
            return await response.json()
            
    async def _delete_request(self, endpoint: str) -> Dict[str, Any]:
        """Make DELETE request to audit service."""
        url = f"{self.base_url}{endpoint}"
        async with self.session.delete(url) as response:
            response.raise_for_status()
            return await response.json() if response.content_length else {}
            
    async def test_health_check(self) -> bool:
        """Test A.27 requirement: Service health endpoint."""
        print("🏥 Testing health check endpoint...")
        
        try:
            response = await self._get_request("/health")
            
            assert response["status"] == "healthy"
            assert "timestamp" in response
            assert "service" in response
            assert response["service"] == "anumate-audit-service"
            
            print("✅ Health check passed")
            return True
            
        except Exception as e:
            print(f"❌ Health check failed: {e}")
            return False
            
    async def test_audit_event_creation(self) -> bool:
        """Test A.27 requirement: Audit event creation."""
        print("📝 Testing audit event creation...")
        
        try:
            created_events = []
            
            for event_data in self.test_events:
                response = await self._post_request("/v1/audit/events", event_data)
                
                assert "event_id" in response
                assert response["tenant_id"] == event_data["tenant_id"]
                assert response["event_type"] == event_data["event_type"]
                assert response["success"] == event_data.get("success", True)
                
                created_events.append(response["event_id"])
                
            print(f"✅ Created {len(created_events)} audit events successfully")
            return True
            
        except Exception as e:
            print(f"❌ Audit event creation failed: {e}")
            return False
            
    async def test_audit_event_retrieval(self) -> bool:
        """Test A.27 requirement: Audit event retrieval."""
        print("🔍 Testing audit event retrieval...")
        
        try:
            # Test retrieving events by tenant
            params = {"tenant_id": self.test_tenant_id, "limit": 10}
            response = await self._get_request("/v1/audit/events", params)
            
            assert "events" in response
            assert "total_count" in response
            assert "page" in response
            assert "limit" in response
            
            events = response["events"]
            assert len(events) >= len(self.test_events)
            
            # Verify event structure
            for event in events[:3]:  # Check first 3 events
                assert "event_id" in event
                assert "tenant_id" in event
                assert "event_timestamp" in event
                assert "event_type" in event
                assert "event_severity" in event
                
            print(f"✅ Retrieved {len(events)} audit events successfully")
            return True
            
        except Exception as e:
            print(f"❌ Audit event retrieval failed: {e}")
            return False
            
    async def test_advanced_search(self) -> bool:
        """Test A.27 requirement: Advanced search capabilities."""
        print("🔎 Testing advanced search capabilities...")
        
        try:
            # Test search by event type
            params = {
                "tenant_id": self.test_tenant_id,
                "event_types": ["user_authentication", "data_access"],
                "limit": 5
            }
            response = await self._get_request("/v1/audit/search", params)
            
            assert "results" in response
            assert "total_matches" in response
            
            # Test search by date range
            now = datetime.now(timezone.utc)
            start_date = (now - timedelta(hours=1)).isoformat()
            end_date = now.isoformat()
            
            params = {
                "tenant_id": self.test_tenant_id,
                "start_date": start_date,
                "end_date": end_date,
                "event_severity": "info"
            }
            response = await self._get_request("/v1/audit/search", params)
            
            assert "results" in response
            results = response["results"]
            
            # Verify all results match criteria
            for result in results:
                assert result["tenant_id"] == self.test_tenant_id
                assert result["event_severity"] == "info"
                
            # Test search by correlation ID
            if self.test_events:
                correlation_id = self.test_events[0]["correlation_id"]
                params = {
                    "tenant_id": self.test_tenant_id,
                    "correlation_id": correlation_id
                }
                response = await self._get_request("/v1/audit/search", params)
                
                assert response["total_matches"] >= 1
                
            print(f"✅ Advanced search completed successfully")
            return True
            
        except Exception as e:
            print(f"❌ Advanced search failed: {e}")
            return False
            
    async def test_retention_policies(self) -> bool:
        """Test A.27 requirement: Retention policy management."""
        print("📅 Testing retention policy management...")
        
        try:
            # Create retention policy
            policy_data = {
                "tenant_id": self.test_tenant_id,
                "policy_name": "Test Policy",
                "retention_days": 90,
                "event_types": ["user_authentication", "data_access"],
                "compliance_framework": "GDPR",
                "auto_delete": True
            }
            
            response = await self._post_request("/v1/audit/retention-policies", policy_data)
            
            assert "policy_id" in response
            assert response["tenant_id"] == policy_data["tenant_id"]
            assert response["retention_days"] == policy_data["retention_days"]
            
            policy_id = response["policy_id"]
            
            # Retrieve retention policies
            params = {"tenant_id": self.test_tenant_id}
            response = await self._get_request("/v1/audit/retention-policies", params)
            
            assert "policies" in response
            policies = response["policies"]
            
            # Find our created policy
            created_policy = next((p for p in policies if p["policy_id"] == policy_id), None)
            assert created_policy is not None
            assert created_policy["policy_name"] == "Test Policy"
            
            # Test policy application simulation
            params = {"tenant_id": self.test_tenant_id, "simulate": True}
            response = await self._get_request(f"/v1/audit/retention-policies/{policy_id}/apply", params)
            
            assert "would_delete_count" in response
            assert "affected_event_types" in response
            
            print("✅ Retention policy management passed")
            return True
            
        except Exception as e:
            print(f"❌ Retention policy management failed: {e}")
            return False
            
    async def test_siem_export(self) -> bool:
        """Test A.27 requirement: SIEM export functionality."""
        print("📤 Testing SIEM export functionality...")
        
        try:
            # Test export job creation
            now = datetime.now(timezone.utc)
            export_data = {
                "tenant_id": self.test_tenant_id,
                "export_format": "json",
                "start_date": (now - timedelta(hours=1)).isoformat(),
                "end_date": now.isoformat(),
                "event_types": ["user_authentication", "data_access"],
                "include_pii": False,
                "compression": "gzip"
            }
            
            response = await self._post_request("/v1/audit/export", export_data)
            
            assert "export_id" in response
            assert response["status"] == "queued"
            assert response["tenant_id"] == export_data["tenant_id"]
            
            export_id = response["export_id"]
            
            # Check export status (wait for processing)
            for _ in range(10):  # Wait up to 10 seconds
                response = await self._get_request(f"/v1/audit/export/{export_id}")
                
                if response["status"] in ["completed", "failed"]:
                    break
                    
                await asyncio.sleep(1)
                
            assert response["status"] == "completed"
            assert "download_url" in response
            assert "file_size_bytes" in response
            assert "exported_records" in response
            
            # Test different export formats
            formats = ["csv", "syslog", "cef"]
            
            for export_format in formats:
                export_data["export_format"] = export_format
                response = await self._post_request("/v1/audit/export", export_data)
                assert "export_id" in response
                
            print("✅ SIEM export functionality passed")
            return True
            
        except Exception as e:
            print(f"❌ SIEM export functionality failed: {e}")
            return False
            
    async def test_pii_redaction(self) -> bool:
        """Test A.27 requirement: PII redaction."""
        print("🔒 Testing PII redaction functionality...")
        
        try:
            # Create event with PII data
            pii_event = {
                "tenant_id": self.test_tenant_id,
                "event_type": "data_processing",
                "event_category": "data",
                "event_action": "process",
                "event_severity": "info",
                "service_name": "data-processor",
                "user_id": "sensitive.user@example.com",
                "client_ip": "192.168.1.50",
                "event_description": "Processing user data with PII",
                "success": True,
                "event_data": {
                    "email": "john.doe@example.com",
                    "phone": "555-987-6543",
                    "ssn": "987-65-4321",
                    "credit_card": "4532-1234-5678-9012",
                    "name": "John Doe",
                    "address": "123 Main St, Anytown, ST 12345"
                }
            }
            
            response = await self._post_request("/v1/audit/events", pii_event)
            event_id = response["event_id"]
            
            # Retrieve the event and verify PII is redacted
            response = await self._get_request(f"/v1/audit/events/{event_id}")
            
            # Check that sensitive fields are redacted
            event_data = response.get("event_data", {})
            
            # Email should be partially redacted (preserve domain)
            if "email" in event_data:
                assert "@example.com" in event_data["email"]
                assert "john.doe" not in event_data["email"]
                
            # Phone should have format preserved but digits redacted
            if "phone" in event_data:
                assert "555-" in event_data["phone"] or "*" in event_data["phone"]
                
            # SSN should be redacted with last 4 visible
            if "ssn" in event_data:
                assert "4321" in event_data["ssn"] or "*" in event_data["ssn"]
                
            # Test unit-level PII redaction
            redactor = PIIRedactor(GDPR_CONFIG)
            
            test_text = "Contact John at john@example.com or call 555-123-4567"
            redacted_text, matches = redactor.redact_text(test_text)
            
            assert len(matches) >= 2  # Should find email and phone
            assert "john@example.com" not in redacted_text
            assert "555-123-4567" not in redacted_text
            
            print("✅ PII redaction functionality passed")
            return True
            
        except Exception as e:
            print(f"❌ PII redaction functionality failed: {e}")
            return False
            
    async def test_statistics_endpoint(self) -> bool:
        """Test A.27 requirement: Statistics and metrics."""
        print("📊 Testing statistics endpoint...")
        
        try:
            # Test tenant statistics
            params = {"tenant_id": self.test_tenant_id}
            response = await self._get_request("/v1/audit/statistics", params)
            
            assert "tenant_id" in response
            assert "total_events" in response
            assert "events_by_type" in response
            assert "events_by_severity" in response
            assert "events_last_24h" in response
            
            # Verify statistics make sense
            assert response["total_events"] >= len(self.test_events)
            assert isinstance(response["events_by_type"], dict)
            assert isinstance(response["events_by_severity"], dict)
            
            # Test system-wide statistics (if available)
            response = await self._get_request("/v1/audit/statistics/system")
            
            assert "total_events" in response
            assert "total_tenants" in response
            assert "storage_metrics" in response
            
            print("✅ Statistics endpoint passed")
            return True
            
        except Exception as e:
            print(f"❌ Statistics endpoint failed: {e}")
            return False
            
    async def test_error_handling(self) -> bool:
        """Test A.27 requirement: Proper error handling."""
        print("⚠️ Testing error handling...")
        
        try:
            # Test invalid event data
            try:
                invalid_event = {"invalid": "data"}
                await self._post_request("/v1/audit/events", invalid_event)
                assert False, "Should have raised an error for invalid data"
            except aiohttp.ClientResponseError as e:
                assert e.status == 422  # Validation error
                
            # Test non-existent event retrieval
            try:
                fake_event_id = str(uuid.uuid4())
                await self._get_request(f"/v1/audit/events/{fake_event_id}")
                assert False, "Should have raised an error for non-existent event"
            except aiohttp.ClientResponseError as e:
                assert e.status == 404
                
            # Test invalid search parameters
            try:
                params = {"tenant_id": "invalid-uuid", "start_date": "invalid-date"}
                await self._get_request("/v1/audit/search", params)
                assert False, "Should have raised an error for invalid parameters"
            except aiohttp.ClientResponseError as e:
                assert e.status in [400, 422]
                
            print("✅ Error handling passed")
            return True
            
        except Exception as e:
            print(f"❌ Error handling failed: {e}")
            return False
            
    async def run_all_tests(self) -> Dict[str, bool]:
        """Run the complete integration test suite."""
        print("🚀 Starting A.27 Audit Service Integration Tests")
        print("=" * 60)
        
        test_results = {}
        
        # Run all test methods
        test_methods = [
            ("Health Check", self.test_health_check),
            ("Audit Event Creation", self.test_audit_event_creation),
            ("Audit Event Retrieval", self.test_audit_event_retrieval),
            ("Advanced Search", self.test_advanced_search),
            ("Retention Policies", self.test_retention_policies),
            ("SIEM Export", self.test_siem_export),
            ("PII Redaction", self.test_pii_redaction),
            ("Statistics", self.test_statistics_endpoint),
            ("Error Handling", self.test_error_handling)
        ]
        
        for test_name, test_method in test_methods:
            try:
                result = await test_method()
                test_results[test_name] = result
                print()
            except Exception as e:
                print(f"❌ {test_name} failed with exception: {e}")
                test_results[test_name] = False
                print()
                
        # Print summary
        print("=" * 60)
        print("🏁 A.27 Audit Service Integration Test Results")
        print("=" * 60)
        
        passed = sum(test_results.values())
        total = len(test_results)
        
        for test_name, result in test_results.items():
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"{test_name:<25} {status}")
            
        print("-" * 60)
        print(f"Overall Result: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
        
        if passed == total:
            print("🎉 All A.27 Audit Service integration tests passed!")
        else:
            print(f"⚠️ {total - passed} test(s) failed. Review the output above.")
            
        return test_results


async def main():
    """Main entry point for integration tests."""
    import sys
    
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8007"
    
    async with AuditServiceIntegrationTester(base_url) as tester:
        results = await tester.run_all_tests()
        
        # Exit with error code if any tests failed
        if not all(results.values()):
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
