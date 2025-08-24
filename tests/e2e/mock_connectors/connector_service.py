"""
Mock Connector Framework for E2E Testing

This module provides mock implementations of various connectors used in Anumate
Capsules. These mocks simulate real connector behavior for testing purposes
without requiring external dependencies.
"""

import asyncio
import json
import random
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from uuid import uuid4

from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field


class MockConnectorRequest(BaseModel):
    """Request to execute a mock connector"""
    connector_type: str
    operation: str
    config: Dict[str, Any]
    context: Optional[Dict[str, Any]] = Field(default_factory=dict)
    timeout_ms: int = 30000


class MockConnectorResponse(BaseModel):
    """Response from a mock connector"""
    success: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    execution_time_ms: int
    connector_type: str
    operation: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MockConnectorBase:
    """Base class for mock connectors"""
    
    def __init__(self, name: str, response_delay_ms: int = 100):
        self.name = name
        self.response_delay_ms = response_delay_ms
        self.call_count = 0
        self.error_rate = 0.0  # 0.0 = never fail, 1.0 = always fail
        self.call_history: List[Dict] = []
    
    def set_error_rate(self, rate: float):
        """Set error rate for testing failure scenarios"""
        self.error_rate = max(0.0, min(1.0, rate))
    
    async def execute(self, operation: str, config: Dict, context: Dict = None) -> MockConnectorResponse:
        """Execute the connector operation"""
        start_time = time.time()
        self.call_count += 1
        
        # Simulate processing delay
        await asyncio.sleep(self.response_delay_ms / 1000.0)
        
        # Record call in history
        call_record = {
            "timestamp": datetime.utcnow().isoformat(),
            "operation": operation,
            "config": config,
            "context": context or {},
            "call_number": self.call_count
        }
        self.call_history.append(call_record)
        
        # Simulate random failures based on error rate
        if random.random() < self.error_rate:
            execution_time = int((time.time() - start_time) * 1000)
            return MockConnectorResponse(
                success=False,
                error=f"Mock failure in {self.name} (simulated)",
                execution_time_ms=execution_time,
                connector_type=self.name,
                operation=operation,
                metadata={"simulated_failure": True, "call_count": self.call_count}
            )
        
        # Execute the actual operation
        try:
            result = await self._execute_operation(operation, config, context or {})
            execution_time = int((time.time() - start_time) * 1000)
            
            return MockConnectorResponse(
                success=True,
                result=result,
                execution_time_ms=execution_time,
                connector_type=self.name,
                operation=operation,
                metadata={"call_count": self.call_count}
            )
            
        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            return MockConnectorResponse(
                success=False,
                error=str(e),
                execution_time_ms=execution_time,
                connector_type=self.name,
                operation=operation,
                metadata={"call_count": self.call_count}
            )
    
    async def _execute_operation(self, operation: str, config: Dict, context: Dict) -> Dict:
        """Override in subclasses to implement specific connector logic"""
        raise NotImplementedError("Subclasses must implement _execute_operation")
    
    def get_stats(self) -> Dict:
        """Get connector statistics"""
        return {
            "name": self.name,
            "call_count": self.call_count,
            "error_rate": self.error_rate,
            "response_delay_ms": self.response_delay_ms,
            "recent_calls": self.call_history[-10:]  # Last 10 calls
        }
    
    def reset_stats(self):
        """Reset connector statistics"""
        self.call_count = 0
        self.call_history.clear()


class MockHTTPConnector(MockConnectorBase):
    """Mock HTTP request connector"""
    
    def __init__(self):
        super().__init__("http_request", response_delay_ms=100)
        self.mock_responses = {
            "https://api.example.com/data": {
                "GET": {"status": "success", "data": [{"id": 1, "status": "active"}, {"id": 2, "status": "inactive"}]},
                "POST": {"status": "created", "id": 123},
                "PUT": {"status": "updated", "id": 123},
                "DELETE": {"status": "deleted"}
            },
            "https://api.example.com/results": {
                "POST": {"status": "stored", "result_id": str(uuid4())}
            }
        }
    
    async def _execute_operation(self, operation: str, config: Dict, context: Dict) -> Dict:
        method = config.get("method", "GET").upper()
        url = config.get("url", "")
        timeout = config.get("timeout", 30)
        
        # Simulate timeout if configured timeout is very low
        if timeout < 1:
            raise Exception("Request timeout")
        
        # Return mock response based on URL and method
        if url in self.mock_responses and method in self.mock_responses[url]:
            response_data = self.mock_responses[url][method].copy()
            
            # Add some dynamic data
            response_data["timestamp"] = datetime.utcnow().isoformat()
            response_data["request_id"] = str(uuid4())
            
            return {
                "status_code": 200,
                "headers": {"Content-Type": "application/json"},
                "body": response_data,
                "request_config": config
            }
        else:
            # Default response for unknown URLs
            return {
                "status_code": 200,
                "headers": {"Content-Type": "application/json"},
                "body": {"status": "success", "message": f"Mock {method} response for {url}"},
                "request_config": config
            }


class MockDataTransformConnector(MockConnectorBase):
    """Mock data transformation connector"""
    
    def __init__(self):
        super().__init__("data_transform", response_delay_ms=50)
    
    async def _execute_operation(self, operation: str, config: Dict, context: Dict) -> Dict:
        operation_type = config.get("operation", "filter")
        
        # Sample data for transformation
        sample_data = [
            {"id": 1, "status": "active", "value": 100},
            {"id": 2, "status": "inactive", "value": 200},
            {"id": 3, "status": "active", "value": 150},
            {"id": 4, "status": "pending", "value": 75}
        ]
        
        # Use data from context if available
        input_data = context.get("input_data", sample_data)
        
        if operation_type == "filter":
            criteria = config.get("criteria", {})
            result = []
            for item in input_data:
                match = True
                for key, expected_value in criteria.items():
                    if item.get(key) != expected_value:
                        match = False
                        break
                if match:
                    result.append(item)
        
        elif operation_type == "map":
            mapping = config.get("mapping", {})
            result = []
            for item in input_data:
                new_item = item.copy()
                for old_key, new_key in mapping.items():
                    if old_key in new_item:
                        new_item[new_key] = new_item.pop(old_key)
                result.append(new_item)
        
        elif operation_type == "sort":
            sort_key = config.get("sort_key", "id")
            reverse = config.get("reverse", False)
            result = sorted(input_data, key=lambda x: x.get(sort_key, 0), reverse=reverse)
        
        elif operation_type == "reduce":
            # Sum values
            total = sum(item.get("value", 0) for item in input_data)
            result = {"total": total, "count": len(input_data)}
        
        else:
            # Default: pass through
            result = input_data
        
        return {
            "operation": operation_type,
            "input_count": len(input_data),
            "output_count": len(result) if isinstance(result, list) else 1,
            "result": result,
            "config": config
        }


class MockDatabaseConnector(MockConnectorBase):
    """Mock database operations connector"""
    
    def __init__(self):
        super().__init__("database_write", response_delay_ms=200)
        self.mock_database = {
            "users": [
                {"id": 1, "name": "Alice", "status": "active"},
                {"id": 2, "name": "Bob", "status": "pending"},
                {"id": 3, "name": "Charlie", "status": "inactive"}
            ]
        }
    
    async def _execute_operation(self, operation: str, config: Dict, context: Dict) -> Dict:
        table = config.get("table", "users")
        db_operation = config.get("operation", "select")
        conditions = config.get("conditions", {})
        
        if table not in self.mock_database:
            self.mock_database[table] = []
        
        table_data = self.mock_database[table]
        
        if db_operation == "select":
            result = []
            for record in table_data:
                match = True
                for key, value in conditions.items():
                    if record.get(key) != value:
                        match = False
                        break
                if match:
                    result.append(record.copy())
        
        elif db_operation == "insert":
            new_record = config.get("data", {})
            new_record["id"] = max([r.get("id", 0) for r in table_data], default=0) + 1
            table_data.append(new_record)
            result = {"inserted_id": new_record["id"], "record": new_record}
        
        elif db_operation == "update":
            updates = config.get("data", {})
            updated_count = 0
            
            for record in table_data:
                match = True
                for key, value in conditions.items():
                    if record.get(key) != value:
                        match = False
                        break
                if match:
                    record.update(updates)
                    updated_count += 1
            
            result = {"updated_count": updated_count}
        
        elif db_operation == "delete":
            original_count = len(table_data)
            self.mock_database[table] = [
                record for record in table_data
                if not all(record.get(k) == v for k, v in conditions.items())
            ]
            deleted_count = original_count - len(self.mock_database[table])
            result = {"deleted_count": deleted_count}
        
        else:
            result = {"error": f"Unknown operation: {db_operation}"}
        
        return {
            "table": table,
            "operation": db_operation,
            "conditions": conditions,
            "result": result,
            "timestamp": datetime.utcnow().isoformat()
        }


class MockExternalAPIConnector(MockConnectorBase):
    """Mock external API integration connector"""
    
    def __init__(self):
        super().__init__("external_api", response_delay_ms=300)
        self.webhook_queue = []
        self.notification_count = 0
    
    async def _execute_operation(self, operation: str, config: Dict, context: Dict) -> Dict:
        api_endpoint = config.get("api_endpoint", "")
        method = config.get("method", "POST")
        sensitive_data = config.get("sensitive_data", False)
        
        if "notify" in api_endpoint:
            self.notification_count += 1
            result = {
                "notification_id": str(uuid4()),
                "status": "sent",
                "endpoint": api_endpoint,
                "method": method,
                "timestamp": datetime.utcnow().isoformat(),
                "sensitive_data_handling": "redacted" if sensitive_data else "normal"
            }
        
        elif "webhook" in api_endpoint:
            webhook_id = str(uuid4())
            self.webhook_queue.append({
                "id": webhook_id,
                "endpoint": api_endpoint,
                "payload": context.get("webhook_data", {}),
                "scheduled_time": datetime.utcnow().isoformat()
            })
            result = {
                "webhook_id": webhook_id,
                "status": "queued",
                "endpoint": api_endpoint
            }
        
        elif "integration" in api_endpoint:
            result = {
                "integration_id": str(uuid4()),
                "status": "processed",
                "endpoint": api_endpoint,
                "data_points": random.randint(10, 100),
                "processing_time_ms": random.randint(50, 500)
            }
        
        else:
            # Generic external API call
            result = {
                "response_id": str(uuid4()),
                "status": "success",
                "endpoint": api_endpoint,
                "method": method,
                "response_code": 200
            }
        
        return result


class MockConnectorRegistry:
    """Registry of all mock connectors"""
    
    def __init__(self):
        self.connectors = {
            "http_request": MockHTTPConnector(),
            "data_transform": MockDataTransformConnector(),
            "database_write": MockDatabaseConnector(),
            "external_api": MockExternalAPIConnector()
        }
    
    def get_connector(self, connector_type: str) -> Optional[MockConnectorBase]:
        """Get a connector by type"""
        return self.connectors.get(connector_type)
    
    def set_global_error_rate(self, rate: float):
        """Set error rate for all connectors"""
        for connector in self.connectors.values():
            connector.set_error_rate(rate)
    
    def reset_all_stats(self):
        """Reset statistics for all connectors"""
        for connector in self.connectors.values():
            connector.reset_stats()
    
    def get_all_stats(self) -> Dict[str, Dict]:
        """Get statistics for all connectors"""
        return {
            connector_type: connector.get_stats()
            for connector_type, connector in self.connectors.items()
        }
    
    async def execute(self, request: MockConnectorRequest) -> MockConnectorResponse:
        """Execute a connector request"""
        connector = self.get_connector(request.connector_type)
        if not connector:
            return MockConnectorResponse(
                success=False,
                error=f"Unknown connector type: {request.connector_type}",
                execution_time_ms=0,
                connector_type=request.connector_type,
                operation=request.operation
            )
        
        return await connector.execute(request.operation, request.config, request.context)


# FastAPI app for mock connector service
def create_mock_connector_app() -> FastAPI:
    """Create FastAPI app for mock connector service"""
    app = FastAPI(
        title="Anumate Mock Connector Service",
        description="Mock connectors for E2E testing",
        version="1.0.0"
    )
    
    registry = MockConnectorRegistry()
    
    @app.post("/connectors/execute", response_model=MockConnectorResponse)
    async def execute_connector(request: MockConnectorRequest):
        """Execute a mock connector"""
        return await registry.execute(request)
    
    @app.get("/connectors/types")
    async def list_connector_types():
        """List available connector types"""
        return {
            "connector_types": list(registry.connectors.keys()),
            "count": len(registry.connectors)
        }
    
    @app.get("/connectors/stats")
    async def get_connector_stats():
        """Get statistics for all connectors"""
        return registry.get_all_stats()
    
    @app.post("/connectors/reset-stats")
    async def reset_connector_stats():
        """Reset statistics for all connectors"""
        registry.reset_all_stats()
        return {"message": "Statistics reset successfully"}
    
    @app.post("/connectors/set-error-rate")
    async def set_error_rate(rate: float):
        """Set error rate for all connectors (0.0 to 1.0)"""
        if not 0.0 <= rate <= 1.0:
            raise HTTPException(status_code=400, detail="Error rate must be between 0.0 and 1.0")
        
        registry.set_global_error_rate(rate)
        return {"message": f"Error rate set to {rate} for all connectors"}
    
    @app.get("/health")
    async def health_check():
        """Health check endpoint"""
        return {
            "status": "healthy",
            "service": "mock-connector-service",
            "connectors_available": len(registry.connectors),
            "timestamp": datetime.utcnow().isoformat()
        }
    
    return app


# Standalone server for mock connectors (for testing outside of E2E framework)
if __name__ == "__main__":
    import uvicorn
    
    app = create_mock_connector_app()
    print("🚀 Starting Mock Connector Service on http://localhost:9000")
    print("📚 API Documentation available at http://localhost:9000/docs")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=9000,
        log_level="info",
        reload=False
    )
