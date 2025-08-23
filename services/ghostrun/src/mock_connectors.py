"""Mock connector system for GhostRun simulation."""

import random
import time
from typing import Any, Dict, List, Optional

from .models import MockConnectorResponse, RiskLevel


class MockConnectorRegistry:
    """Registry of mock connectors for simulation."""
    
    def __init__(self) -> None:
        self._connectors: Dict[str, "MockConnector"] = {}
        self._register_default_connectors()
    
    def register_connector(self, name: str, connector: "MockConnector") -> None:
        """Register a mock connector."""
        self._connectors[name] = connector
    
    def get_connector(self, name: str) -> Optional["MockConnector"]:
        """Get a mock connector by name."""
        return self._connectors.get(name)
    
    def list_connectors(self) -> List[str]:
        """List all registered connector names."""
        return list(self._connectors.keys())
    
    def _register_default_connectors(self) -> None:
        """Register default mock connectors."""
        # Payment connectors
        self.register_connector("stripe", StripeConnector())
        self.register_connector("paypal", PayPalConnector())
        self.register_connector("square", SquareConnector())
        
        # Communication connectors
        self.register_connector("sendgrid", SendGridConnector())
        self.register_connector("twilio", TwilioConnector())
        self.register_connector("slack", SlackConnector())
        
        # Cloud connectors
        self.register_connector("aws", AWSConnector())
        self.register_connector("gcp", GCPConnector())
        self.register_connector("azure", AzureConnector())
        
        # Database connectors
        self.register_connector("postgresql", PostgreSQLConnector())
        self.register_connector("mongodb", MongoDBConnector())
        self.register_connector("redis", RedisConnector())
        
        # Generic HTTP connector
        self.register_connector("http", HTTPConnector())


class MockConnector:
    """Base class for mock connectors."""
    
    def __init__(self, name: str, base_latency_ms: int = 100) -> None:
        self.name = name
        self.base_latency_ms = base_latency_ms
        self._supported_tools: Dict[str, Dict[str, Any]] = {}
    
    def register_tool(
        self, 
        tool_name: str, 
        actions: List[str],
        risk_level: RiskLevel = RiskLevel.LOW,
        typical_latency_ms: int = 100
    ) -> None:
        """Register a tool with supported actions."""
        self._supported_tools[tool_name] = {
            "actions": actions,
            "risk_level": risk_level,
            "typical_latency_ms": typical_latency_ms
        }
    
    def supports_tool(self, tool_name: str) -> bool:
        """Check if connector supports a tool."""
        return tool_name in self._supported_tools
    
    def supports_action(self, tool_name: str, action: str) -> bool:
        """Check if connector supports a specific action."""
        if not self.supports_tool(tool_name):
            return False
        return action in self._supported_tools[tool_name]["actions"]
    
    def simulate_call(
        self, 
        tool_name: str, 
        action: str, 
        parameters: Dict[str, Any],
        overrides: Optional[Dict[str, Any]] = None
    ) -> MockConnectorResponse:
        """Simulate a connector call."""
        
        # Check if tool/action is supported
        if not self.supports_action(tool_name, action):
            return MockConnectorResponse(
                connector_name=self.name,
                tool_name=tool_name,
                action=action,
                success=False,
                response_data={"error": f"Unsupported action: {action}"},
                response_time_ms=50,
                simulation_notes=[f"Action {action} not supported by {self.name}"]
            )
        
        # Apply overrides if provided
        tool_config = self._supported_tools[tool_name].copy()
        if overrides:
            tool_config.update(overrides)
        
        # Simulate response
        return self._generate_mock_response(tool_name, action, parameters, tool_config)
    
    def _generate_mock_response(
        self, 
        tool_name: str, 
        action: str, 
        parameters: Dict[str, Any],
        tool_config: Dict[str, Any]
    ) -> MockConnectorResponse:
        """Generate a mock response for the action."""
        
        # Calculate simulated latency
        base_latency = tool_config.get("typical_latency_ms", self.base_latency_ms)
        latency_variance = int(base_latency * 0.3)  # 30% variance
        simulated_latency = base_latency + random.randint(-latency_variance, latency_variance)
        
        # Determine success probability based on action risk
        risk_level = tool_config.get("risk_level", RiskLevel.LOW)
        success_probability = self._get_success_probability(risk_level)
        success = random.random() < success_probability
        
        # Generate mock response data
        response_data = self._generate_response_data(tool_name, action, parameters, success)
        
        # Generate simulation notes
        notes = [
            f"Simulated {action} call to {self.name}",
            f"Risk level: {risk_level.value}",
            f"Success probability: {success_probability:.2f}"
        ]
        
        return MockConnectorResponse(
            connector_name=self.name,
            tool_name=tool_name,
            action=action,
            success=success,
            response_data=response_data,
            response_time_ms=simulated_latency,
            simulation_notes=notes
        )
    
    def _get_success_probability(self, risk_level: RiskLevel) -> float:
        """Get success probability based on risk level."""
        probabilities = {
            RiskLevel.LOW: 0.98,
            RiskLevel.MEDIUM: 0.95,
            RiskLevel.HIGH: 0.90,
            RiskLevel.CRITICAL: 0.85
        }
        return probabilities.get(risk_level, 0.95)
    
    def _generate_response_data(
        self, 
        tool_name: str, 
        action: str, 
        parameters: Dict[str, Any],
        success: bool
    ) -> Dict[str, Any]:
        """Generate mock response data. Override in subclasses."""
        if success:
            return {
                "status": "success",
                "message": f"Mock {action} completed successfully",
                "data": {"mock": True, "simulated": True}
            }
        else:
            return {
                "status": "error",
                "message": f"Mock {action} failed",
                "error_code": "SIMULATION_ERROR",
                "data": {"mock": True, "simulated": True}
            }


class StripeConnector(MockConnector):
    """Mock Stripe payment connector."""
    
    def __init__(self) -> None:
        super().__init__("stripe", base_latency_ms=200)
        
        # Register Stripe tools and actions
        self.register_tool(
            "payment", 
            ["charge", "refund", "capture", "cancel"],
            risk_level=RiskLevel.HIGH,
            typical_latency_ms=300
        )
        self.register_tool(
            "customer", 
            ["create", "update", "delete", "retrieve"],
            risk_level=RiskLevel.MEDIUM,
            typical_latency_ms=150
        )
        self.register_tool(
            "subscription", 
            ["create", "update", "cancel", "retrieve"],
            risk_level=RiskLevel.HIGH,
            typical_latency_ms=250
        )
    
    def _generate_response_data(
        self, 
        tool_name: str, 
        action: str, 
        parameters: Dict[str, Any],
        success: bool
    ) -> Dict[str, Any]:
        """Generate Stripe-specific mock response data."""
        if tool_name == "payment":
            if success:
                return {
                    "id": f"ch_mock_{random.randint(1000, 9999)}",
                    "amount": parameters.get("amount", 1000),
                    "currency": parameters.get("currency", "usd"),
                    "status": "succeeded" if action == "charge" else "refunded",
                    "created": int(time.time())
                }
            else:
                return {
                    "error": {
                        "type": "card_error",
                        "code": "card_declined",
                        "message": "Your card was declined."
                    }
                }
        
        return super()._generate_response_data(tool_name, action, parameters, success)


class PayPalConnector(MockConnector):
    """Mock PayPal payment connector."""
    
    def __init__(self) -> None:
        super().__init__("paypal", base_latency_ms=400)
        
        self.register_tool(
            "payment", 
            ["create", "execute", "refund"],
            risk_level=RiskLevel.HIGH,
            typical_latency_ms=500
        )
        self.register_tool(
            "payout", 
            ["create", "get", "cancel"],
            risk_level=RiskLevel.CRITICAL,
            typical_latency_ms=600
        )


class SquareConnector(MockConnector):
    """Mock Square payment connector."""
    
    def __init__(self) -> None:
        super().__init__("square", base_latency_ms=250)
        
        self.register_tool(
            "payment", 
            ["charge", "refund"],
            risk_level=RiskLevel.HIGH,
            typical_latency_ms=300
        )


class SendGridConnector(MockConnector):
    """Mock SendGrid email connector."""
    
    def __init__(self) -> None:
        super().__init__("sendgrid", base_latency_ms=150)
        
        self.register_tool(
            "email", 
            ["send", "send_bulk", "get_stats"],
            risk_level=RiskLevel.MEDIUM,
            typical_latency_ms=200
        )
        self.register_tool(
            "template", 
            ["create", "update", "delete"],
            risk_level=RiskLevel.LOW,
            typical_latency_ms=100
        )


class TwilioConnector(MockConnector):
    """Mock Twilio communication connector."""
    
    def __init__(self) -> None:
        super().__init__("twilio", base_latency_ms=300)
        
        self.register_tool(
            "sms", 
            ["send", "get_status"],
            risk_level=RiskLevel.MEDIUM,
            typical_latency_ms=400
        )
        self.register_tool(
            "voice", 
            ["call", "hangup", "get_recording"],
            risk_level=RiskLevel.HIGH,
            typical_latency_ms=500
        )


class SlackConnector(MockConnector):
    """Mock Slack connector."""
    
    def __init__(self) -> None:
        super().__init__("slack", base_latency_ms=200)
        
        self.register_tool(
            "message", 
            ["send", "update", "delete"],
            risk_level=RiskLevel.LOW,
            typical_latency_ms=250
        )
        self.register_tool(
            "channel", 
            ["create", "invite", "archive"],
            risk_level=RiskLevel.MEDIUM,
            typical_latency_ms=300
        )


class AWSConnector(MockConnector):
    """Mock AWS cloud connector."""
    
    def __init__(self) -> None:
        super().__init__("aws", base_latency_ms=100)
        
        self.register_tool(
            "s3", 
            ["put_object", "get_object", "delete_object", "list_objects"],
            risk_level=RiskLevel.MEDIUM,
            typical_latency_ms=150
        )
        self.register_tool(
            "ec2", 
            ["run_instance", "terminate_instance", "describe_instances"],
            risk_level=RiskLevel.HIGH,
            typical_latency_ms=300
        )
        self.register_tool(
            "lambda", 
            ["invoke", "create_function", "delete_function"],
            risk_level=RiskLevel.MEDIUM,
            typical_latency_ms=200
        )


class GCPConnector(MockConnector):
    """Mock Google Cloud Platform connector."""
    
    def __init__(self) -> None:
        super().__init__("gcp", base_latency_ms=120)
        
        self.register_tool(
            "storage", 
            ["upload", "download", "delete", "list"],
            risk_level=RiskLevel.MEDIUM,
            typical_latency_ms=180
        )
        self.register_tool(
            "compute", 
            ["create_instance", "delete_instance", "list_instances"],
            risk_level=RiskLevel.HIGH,
            typical_latency_ms=350
        )


class AzureConnector(MockConnector):
    """Mock Microsoft Azure connector."""
    
    def __init__(self) -> None:
        super().__init__("azure", base_latency_ms=140)
        
        self.register_tool(
            "storage", 
            ["upload_blob", "download_blob", "delete_blob"],
            risk_level=RiskLevel.MEDIUM,
            typical_latency_ms=200
        )
        self.register_tool(
            "vm", 
            ["create", "start", "stop", "delete"],
            risk_level=RiskLevel.HIGH,
            typical_latency_ms=400
        )


class PostgreSQLConnector(MockConnector):
    """Mock PostgreSQL database connector."""
    
    def __init__(self) -> None:
        super().__init__("postgresql", base_latency_ms=50)
        
        self.register_tool(
            "query", 
            ["select", "insert", "update", "delete"],
            risk_level=RiskLevel.MEDIUM,
            typical_latency_ms=75
        )
        self.register_tool(
            "schema", 
            ["create_table", "drop_table", "alter_table"],
            risk_level=RiskLevel.HIGH,
            typical_latency_ms=100
        )


class MongoDBConnector(MockConnector):
    """Mock MongoDB connector."""
    
    def __init__(self) -> None:
        super().__init__("mongodb", base_latency_ms=60)
        
        self.register_tool(
            "document", 
            ["find", "insert", "update", "delete"],
            risk_level=RiskLevel.MEDIUM,
            typical_latency_ms=80
        )
        self.register_tool(
            "collection", 
            ["create", "drop", "index"],
            risk_level=RiskLevel.HIGH,
            typical_latency_ms=120
        )


class RedisConnector(MockConnector):
    """Mock Redis connector."""
    
    def __init__(self) -> None:
        super().__init__("redis", base_latency_ms=20)
        
        self.register_tool(
            "cache", 
            ["get", "set", "delete", "expire"],
            risk_level=RiskLevel.LOW,
            typical_latency_ms=30
        )
        self.register_tool(
            "pubsub", 
            ["publish", "subscribe", "unsubscribe"],
            risk_level=RiskLevel.MEDIUM,
            typical_latency_ms=40
        )


class HTTPConnector(MockConnector):
    """Generic HTTP connector for REST APIs."""
    
    def __init__(self) -> None:
        super().__init__("http", base_latency_ms=200)
        
        self.register_tool(
            "request", 
            ["get", "post", "put", "patch", "delete"],
            risk_level=RiskLevel.MEDIUM,
            typical_latency_ms=250
        )
    
    def _generate_response_data(
        self, 
        tool_name: str, 
        action: str, 
        parameters: Dict[str, Any],
        success: bool
    ) -> Dict[str, Any]:
        """Generate HTTP-specific mock response data."""
        if success:
            status_codes = {"get": 200, "post": 201, "put": 200, "patch": 200, "delete": 204}
            return {
                "status_code": status_codes.get(action, 200),
                "headers": {"content-type": "application/json"},
                "body": {"message": f"Mock {action.upper()} request successful"},
                "url": parameters.get("url", "https://api.example.com/mock")
            }
        else:
            return {
                "status_code": 500,
                "headers": {"content-type": "application/json"},
                "body": {"error": "Internal Server Error"},
                "url": parameters.get("url", "https://api.example.com/mock")
            }


# Global registry instance
mock_connector_registry = MockConnectorRegistry()