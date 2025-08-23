"""Risk analysis engine for GhostRun simulation."""

from typing import Any, List, Tuple

from .models import ExecutionStep, MockConnectorResponse, RiskLevel


class RiskAnalyzer:
    """Analyzes risks in ExecutablePlan steps and flows."""
    
    def __init__(self) -> None:
        # Risk patterns for different operations
        self.high_risk_actions = {
            "delete", "drop", "remove", "terminate", "cancel", "refund", 
            "charge", "payment", "transfer", "withdraw", "debit"
        }
        
        self.medium_risk_actions = {
            "create", "update", "modify", "send", "publish", "execute",
            "start", "stop", "restart", "deploy"
        }
        
        self.high_risk_tools = {
            "stripe", "paypal", "square", "aws", "gcp", "azure",
            "postgresql", "mongodb", "production"
        }
        
        self.critical_risk_patterns = {
            "production", "prod", "live", "master", "main", "critical"
        }
    
    async def analyze_step_risk(
        self, 
        step: ExecutionStep, 
        connector_responses: List[MockConnectorResponse]
    ) -> Tuple[RiskLevel, List[str]]:
        """Analyze risk level for a single step."""
        
        risk_factors = []
        risk_scores = []
        
        # Analyze step action risk
        action_risk, action_factors = self._analyze_action_risk(step)
        risk_scores.append(action_risk)
        risk_factors.extend(action_factors)
        
        # Analyze tool risk
        tool_risk, tool_factors = self._analyze_tool_risk(step)
        risk_scores.append(tool_risk)
        risk_factors.extend(tool_factors)
        
        # Analyze parameter risk
        param_risk, param_factors = self._analyze_parameter_risk(step)
        risk_scores.append(param_risk)
        risk_factors.extend(param_factors)
        
        # Analyze connector response risk
        response_risk, response_factors = self._analyze_response_risk(connector_responses)
        risk_scores.append(response_risk)
        risk_factors.extend(response_factors)
        
        # Analyze step configuration risk
        config_risk, config_factors = self._analyze_configuration_risk(step)
        risk_scores.append(config_risk)
        risk_factors.extend(config_factors)
        
        # Calculate overall risk level
        overall_risk = self._calculate_overall_risk(risk_scores)
        
        return overall_risk, risk_factors
    
    def _analyze_action_risk(self, step: ExecutionStep) -> Tuple[RiskLevel, List[str]]:
        """Analyze risk based on step action."""
        risk_factors = []
        
        if not step.action:
            return RiskLevel.LOW, risk_factors
        
        action_lower = step.action.lower()
        
        # Check for critical risk patterns
        for pattern in self.critical_risk_patterns:
            if pattern in action_lower:
                risk_factors.append(f"Critical pattern '{pattern}' in action")
                return RiskLevel.CRITICAL, risk_factors
        
        # Check for high-risk actions
        if any(high_risk in action_lower for high_risk in self.high_risk_actions):
            risk_factors.append(f"High-risk action: {step.action}")
            return RiskLevel.HIGH, risk_factors
        
        # Check for medium-risk actions
        if any(medium_risk in action_lower for medium_risk in self.medium_risk_actions):
            risk_factors.append(f"Medium-risk action: {step.action}")
            return RiskLevel.MEDIUM, risk_factors
        
        return RiskLevel.LOW, risk_factors
    
    def _analyze_tool_risk(self, step: ExecutionStep) -> Tuple[RiskLevel, List[str]]:
        """Analyze risk based on tool being used."""
        risk_factors = []
        
        if not step.tool:
            return RiskLevel.LOW, risk_factors
        
        tool_lower = step.tool.lower()
        
        # Check for critical patterns in tool name
        for pattern in self.critical_risk_patterns:
            if pattern in tool_lower:
                risk_factors.append(f"Critical environment pattern '{pattern}' in tool")
                return RiskLevel.CRITICAL, risk_factors
        
        # Check for high-risk tools
        if tool_lower in self.high_risk_tools:
            risk_factors.append(f"High-risk tool: {step.tool}")
            return RiskLevel.HIGH, risk_factors
        
        # Database operations are generally medium risk
        if any(db in tool_lower for db in ["sql", "database", "db", "mongo", "redis"]):
            risk_factors.append(f"Database tool: {step.tool}")
            return RiskLevel.MEDIUM, risk_factors
        
        return RiskLevel.LOW, risk_factors
    
    def _analyze_parameter_risk(self, step: ExecutionStep) -> Tuple[RiskLevel, List[str]]:
        """Analyze risk based on step parameters."""
        risk_factors = []
        
        if not step.parameters:
            return RiskLevel.LOW, risk_factors
        
        # Check for sensitive parameters
        sensitive_keys = {
            "password", "secret", "key", "token", "credential", "auth",
            "amount", "price", "cost", "charge", "payment"
        }
        
        param_str = str(step.parameters).lower()
        
        # Check for critical patterns
        for pattern in self.critical_risk_patterns:
            if pattern in param_str:
                risk_factors.append(f"Critical pattern '{pattern}' in parameters")
                return RiskLevel.CRITICAL, risk_factors
        
        # Check for sensitive parameters
        found_sensitive = []
        for key in step.parameters:
            if any(sensitive in key.lower() for sensitive in sensitive_keys):
                found_sensitive.append(key)
        
        if found_sensitive:
            risk_factors.append(f"Sensitive parameters detected: {found_sensitive}")
            return RiskLevel.HIGH, risk_factors
        
        # Check for large monetary amounts
        for key, value in step.parameters.items():
            if isinstance(value, (int, float)):
                if "amount" in key.lower() or "price" in key.lower():
                    if value > 10000:  # > $100 assuming cents
                        risk_factors.append(f"Large monetary amount: {key}={value}")
                        return RiskLevel.HIGH, risk_factors
                    elif value > 1000:  # > $10
                        risk_factors.append(f"Medium monetary amount: {key}={value}")
                        return RiskLevel.MEDIUM, risk_factors
        
        return RiskLevel.LOW, risk_factors
    
    def _analyze_response_risk(
        self, 
        connector_responses: List[MockConnectorResponse]
    ) -> Tuple[RiskLevel, List[str]]:
        """Analyze risk based on connector responses."""
        risk_factors = []
        
        if not connector_responses:
            return RiskLevel.LOW, risk_factors
        
        # Check for failed responses
        failed_responses = [resp for resp in connector_responses if not resp.success]
        if failed_responses:
            risk_factors.append(f"Failed connector responses: {len(failed_responses)}")
            return RiskLevel.HIGH, risk_factors
        
        # Check for high-latency responses
        high_latency_responses = [
            resp for resp in connector_responses 
            if resp.response_time_ms > 5000
        ]
        if high_latency_responses:
            risk_factors.append(f"High-latency responses: {len(high_latency_responses)}")
            return RiskLevel.MEDIUM, risk_factors
        
        # Check for high-risk connectors
        high_risk_connectors = [
            resp for resp in connector_responses 
            if resp.connector_name.lower() in self.high_risk_tools
        ]
        if high_risk_connectors:
            connector_names = [resp.connector_name for resp in high_risk_connectors]
            risk_factors.append(f"High-risk connectors used: {connector_names}")
            return RiskLevel.HIGH, risk_factors
        
        return RiskLevel.LOW, risk_factors
    
    def _analyze_configuration_risk(self, step: ExecutionStep) -> Tuple[RiskLevel, List[str]]:
        """Analyze risk based on step configuration."""
        risk_factors = []
        
        # Check for missing timeout
        if not step.timeout:
            risk_factors.append("No timeout configured - potential for hanging operations")
        elif step.timeout > 300000:  # > 5 minutes
            risk_factors.append(f"Very long timeout: {step.timeout}ms")
            return RiskLevel.MEDIUM, risk_factors
        
        # Check for missing retry policy on high-risk operations
        if not step.retry_policy:
            if step.action and any(
                high_risk in step.action.lower() 
                for high_risk in self.high_risk_actions
            ):
                risk_factors.append("No retry policy for high-risk operation")
                return RiskLevel.MEDIUM, risk_factors
        
        # Check for excessive retry attempts
        if step.retry_policy:
            max_attempts = step.retry_policy.get("max_attempts", 1)
            if max_attempts > 5:
                risk_factors.append(f"Excessive retry attempts: {max_attempts}")
                return RiskLevel.MEDIUM, risk_factors
        
        # Check for missing dependencies on critical steps
        if step.action and any(
            critical in step.action.lower() 
            for critical in ["delete", "drop", "terminate"]
        ):
            if not step.depends_on:
                risk_factors.append("Critical operation with no dependencies")
                return RiskLevel.HIGH, risk_factors
        
        return RiskLevel.LOW, risk_factors
    
    def _calculate_overall_risk(self, risk_scores: List[RiskLevel]) -> RiskLevel:
        """Calculate overall risk from individual risk scores."""
        if not risk_scores:
            return RiskLevel.LOW
        
        # Count occurrences of each risk level
        risk_counts = {level: 0 for level in RiskLevel}
        for risk in risk_scores:
            risk_counts[risk] += 1
        
        # Determine overall risk using weighted approach
        if risk_counts[RiskLevel.CRITICAL] > 0:
            return RiskLevel.CRITICAL
        elif risk_counts[RiskLevel.HIGH] > 0:
            return RiskLevel.HIGH
        elif risk_counts[RiskLevel.MEDIUM] >= 2:  # Multiple medium risks = high risk
            return RiskLevel.HIGH
        elif risk_counts[RiskLevel.MEDIUM] > 0:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW
    
    def analyze_flow_dependencies(
        self, 
        steps: List[ExecutionStep]
    ) -> Tuple[RiskLevel, List[str]]:
        """Analyze risks in flow dependencies."""
        risk_factors = []
        
        # Build dependency graph
        step_map = {step.step_id: step for step in steps}
        
        # Check for circular dependencies
        visited = set()
        rec_stack = set()
        
        def has_cycle(step_id: str) -> bool:
            if step_id in rec_stack:
                return True
            if step_id in visited:
                return False
            
            visited.add(step_id)
            rec_stack.add(step_id)
            
            step = step_map.get(step_id)
            if step:
                for dep in step.depends_on:
                    if has_cycle(dep):
                        return True
            
            rec_stack.remove(step_id)
            return False
        
        # Check each step for cycles
        for step in steps:
            if step.step_id not in visited:
                if has_cycle(step.step_id):
                    risk_factors.append(f"Circular dependency detected involving {step.step_id}")
                    return RiskLevel.CRITICAL, risk_factors
        
        # Check for missing dependencies
        all_step_ids = {step.step_id for step in steps}
        for step in steps:
            for dep in step.depends_on:
                if dep not in all_step_ids:
                    risk_factors.append(f"Step {step.step_id} depends on non-existent step {dep}")
                    return RiskLevel.HIGH, risk_factors
        
        # Check for overly complex dependency chains
        max_chain_length = 0
        for step in steps:
            chain_length = self._calculate_dependency_chain_length(step, step_map, set())
            max_chain_length = max(max_chain_length, chain_length)
        
        if max_chain_length > 10:
            risk_factors.append(f"Very long dependency chain: {max_chain_length} steps")
            return RiskLevel.MEDIUM, risk_factors
        elif max_chain_length > 5:
            risk_factors.append(f"Long dependency chain: {max_chain_length} steps")
        
        return RiskLevel.LOW, risk_factors
    
    def _calculate_dependency_chain_length(
        self, 
        step: ExecutionStep, 
        step_map: dict, 
        visited: set
    ) -> int:
        """Calculate the length of the longest dependency chain for a step."""
        if step.step_id in visited:
            return 0  # Avoid infinite recursion
        
        if not step.depends_on:
            return 1
        
        visited.add(step.step_id)
        max_length = 0
        
        for dep_id in step.depends_on:
            dep_step = step_map.get(dep_id)
            if dep_step:
                dep_length = self._calculate_dependency_chain_length(dep_step, step_map, visited)
                max_length = max(max_length, dep_length)
        
        visited.remove(step.step_id)
        return max_length + 1