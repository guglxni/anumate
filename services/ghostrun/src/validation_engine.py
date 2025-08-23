"""Validation engine for ExecutablePlan validation."""

from typing import Any, Dict, List

from .models import GhostRunRequest, ExecutablePlan


class ValidationEngine:
    """Validates ExecutablePlans for simulation readiness."""
    
    def __init__(self) -> None:
        self.required_step_fields = ["step_id", "name", "step_type"]
        self.required_flow_fields = ["flow_id", "name", "steps"]
        self.valid_step_types = {
            "action", "condition", "loop", "parallel", "sequential", "approval"
        }
    
    async def validate_plan(
        self, 
        plan: ExecutablePlan, 
        request: GhostRunRequest
    ) -> List[str]:
        """Validate an ExecutablePlan for simulation."""
        
        issues = []
        
        # Validate plan structure
        structure_issues = await self._validate_plan_structure(plan)
        issues.extend(structure_issues)
        
        # Validate flows
        flow_issues = await self._validate_flows(plan)
        issues.extend(flow_issues)
        
        # Validate security context
        security_issues = await self._validate_security_context(plan)
        issues.extend(security_issues)
        
        # Validate resource requirements
        resource_issues = await self._validate_resource_requirements(plan)
        issues.extend(resource_issues)
        
        # Validate against request constraints
        request_issues = await self._validate_against_request(plan, request)
        issues.extend(request_issues)
        
        return issues
    
    async def _validate_plan_structure(self, plan: ExecutablePlan) -> List[str]:
        """Validate basic plan structure."""
        issues = []
        
        # Check required fields
        if not plan.plan_id:
            issues.append("Plan ID is required")
        
        if not plan.plan_hash:
            issues.append("Plan hash is required")
        
        if not plan.tenant_id:
            issues.append("Tenant ID is required")
        
        if not plan.name:
            issues.append("Plan name is required")
        
        if not plan.version:
            issues.append("Plan version is required")
        
        # Validate flows exist
        if not plan.flows:
            issues.append("Plan must have at least one flow")
        
        # Validate main flow exists
        if plan.main_flow:
            flow_ids = [flow.flow_id for flow in plan.flows]
            if plan.main_flow not in flow_ids:
                issues.append(f"Main flow '{plan.main_flow}' not found in plan flows")
        else:
            issues.append("Main flow must be specified")
        
        return issues
    
    async def _validate_flows(self, plan: ExecutablePlan) -> List[str]:
        """Validate all flows in the plan."""
        issues = []
        
        flow_ids = set()
        
        for flow in plan.flows:
            # Check for duplicate flow IDs
            if flow.flow_id in flow_ids:
                issues.append(f"Duplicate flow ID: {flow.flow_id}")
            flow_ids.add(flow.flow_id)
            
            # Validate individual flow
            flow_issues = await self._validate_flow(flow)
            issues.extend(flow_issues)
        
        return issues
    
    async def _validate_flow(self, flow: Any) -> List[str]:
        """Validate a single execution flow."""
        issues = []
        
        # Check required fields
        for field in self.required_flow_fields:
            if not hasattr(flow, field) or not getattr(flow, field):
                issues.append(f"Flow {flow.flow_id}: Missing required field '{field}'")
        
        # Validate steps
        if not flow.steps:
            issues.append(f"Flow {flow.flow_id}: Must have at least one step")
        else:
            step_issues = await self._validate_steps(flow.steps, flow.flow_id)
            issues.extend(step_issues)
        
        # Validate concurrency settings
        if flow.parallel_execution and flow.max_concurrency:
            if flow.max_concurrency <= 0:
                issues.append(f"Flow {flow.flow_id}: max_concurrency must be positive")
            elif flow.max_concurrency > len(flow.steps):
                issues.append(
                    f"Flow {flow.flow_id}: max_concurrency ({flow.max_concurrency}) "
                    f"exceeds number of steps ({len(flow.steps)})"
                )
        
        # Validate failure handling
        valid_failure_strategies = {"stop", "continue", "rollback"}
        if flow.on_failure not in valid_failure_strategies:
            issues.append(
                f"Flow {flow.flow_id}: Invalid failure strategy '{flow.on_failure}'. "
                f"Must be one of: {valid_failure_strategies}"
            )
        
        return issues
    
    async def _validate_steps(self, steps: List[Any], flow_id: str) -> List[str]:
        """Validate steps in a flow."""
        issues = []
        
        step_ids = set()
        
        for step in steps:
            # Check for duplicate step IDs
            if step.step_id in step_ids:
                issues.append(f"Flow {flow_id}: Duplicate step ID '{step.step_id}'")
            step_ids.add(step.step_id)
            
            # Validate individual step
            step_issues = await self._validate_step(step, flow_id)
            issues.extend(step_issues)
        
        # Validate dependencies
        dependency_issues = await self._validate_step_dependencies(steps, flow_id)
        issues.extend(dependency_issues)
        
        return issues
    
    async def _validate_step(self, step: Any, flow_id: str) -> List[str]:
        """Validate a single execution step."""
        issues = []
        
        step_prefix = f"Flow {flow_id}, Step {step.step_id}"
        
        # Check required fields
        for field in self.required_step_fields:
            if not hasattr(step, field) or not getattr(step, field):
                issues.append(f"{step_prefix}: Missing required field '{field}'")
        
        # Validate step type
        if hasattr(step, 'step_type') and step.step_type:
            if step.step_type not in self.valid_step_types:
                issues.append(
                    f"{step_prefix}: Invalid step type '{step.step_type}'. "
                    f"Must be one of: {self.valid_step_types}"
                )
        
        # Validate action and tool consistency
        if hasattr(step, 'action') and step.action:
            if not hasattr(step, 'tool') or not step.tool:
                issues.append(f"{step_prefix}: Action specified but no tool provided")
        
        # Validate timeout
        if hasattr(step, 'timeout') and step.timeout is not None:
            if step.timeout <= 0:
                issues.append(f"{step_prefix}: Timeout must be positive")
            elif step.timeout > 3600000:  # 1 hour
                issues.append(f"{step_prefix}: Timeout exceeds maximum (1 hour)")
        
        # Validate retry policy
        if hasattr(step, 'retry_policy') and step.retry_policy:
            retry_issues = await self._validate_retry_policy(step.retry_policy, step_prefix)
            issues.extend(retry_issues)
        
        # Validate parameters
        if hasattr(step, 'parameters') and step.parameters:
            param_issues = await self._validate_step_parameters(step.parameters, step_prefix)
            issues.extend(param_issues)
        
        return issues
    
    async def _validate_retry_policy(self, retry_policy: Dict[str, Any], step_prefix: str) -> List[str]:
        """Validate retry policy configuration."""
        issues = []
        
        # Validate max_attempts
        if "max_attempts" in retry_policy:
            max_attempts = retry_policy["max_attempts"]
            if not isinstance(max_attempts, int) or max_attempts < 1:
                issues.append(f"{step_prefix}: max_attempts must be a positive integer")
            elif max_attempts > 10:
                issues.append(f"{step_prefix}: max_attempts exceeds recommended maximum (10)")
        
        # Validate delay
        if "delay" in retry_policy:
            delay = retry_policy["delay"]
            if not isinstance(delay, (int, float)) or delay < 0:
                issues.append(f"{step_prefix}: retry delay must be non-negative")
            elif delay > 60000:  # 1 minute
                issues.append(f"{step_prefix}: retry delay exceeds recommended maximum (60s)")
        
        # Validate backoff strategy
        if "backoff" in retry_policy:
            valid_backoff = {"fixed", "linear", "exponential"}
            if retry_policy["backoff"] not in valid_backoff:
                issues.append(
                    f"{step_prefix}: Invalid backoff strategy. Must be one of: {valid_backoff}"
                )
        
        return issues
    
    async def _validate_step_parameters(
        self, 
        parameters: Dict[str, Any], 
        step_prefix: str
    ) -> List[str]:
        """Validate step parameters."""
        issues = []
        
        # Check for potentially dangerous parameters
        dangerous_keys = {"password", "secret", "private_key", "api_key"}
        for key in parameters:
            if key.lower() in dangerous_keys:
                issues.append(
                    f"{step_prefix}: Potentially sensitive parameter '{key}' should use secrets management"
                )
        
        # Validate parameter values
        for key, value in parameters.items():
            if isinstance(value, str) and len(value) > 10000:
                issues.append(f"{step_prefix}: Parameter '{key}' value is very large (>10KB)")
            elif isinstance(value, (list, dict)) and len(str(value)) > 50000:
                issues.append(f"{step_prefix}: Parameter '{key}' structure is very large (>50KB)")
        
        return issues
    
    async def _validate_step_dependencies(self, steps: List[Any], flow_id: str) -> List[str]:
        """Validate step dependencies within a flow."""
        issues = []
        
        step_ids = {step.step_id for step in steps}
        
        for step in steps:
            if hasattr(step, 'depends_on') and step.depends_on:
                for dep_id in step.depends_on:
                    if dep_id not in step_ids:
                        issues.append(
                            f"Flow {flow_id}, Step {step.step_id}: "
                            f"Depends on non-existent step '{dep_id}'"
                        )
        
        # Check for circular dependencies
        circular_deps = await self._detect_circular_dependencies(steps)
        if circular_deps:
            issues.append(f"Flow {flow_id}: Circular dependencies detected: {circular_deps}")
        
        return issues
    
    async def _detect_circular_dependencies(self, steps: List[Any]) -> List[str]:
        """Detect circular dependencies in steps."""
        step_map = {step.step_id: step for step in steps}
        visited = set()
        rec_stack = set()
        cycles = []
        
        def dfs(step_id: str, path: List[str]) -> None:
            if step_id in rec_stack:
                # Found a cycle
                cycle_start = path.index(step_id)
                cycle = path[cycle_start:] + [step_id]
                cycles.append(" -> ".join(cycle))
                return
            
            if step_id in visited:
                return
            
            visited.add(step_id)
            rec_stack.add(step_id)
            
            step = step_map.get(step_id)
            if step and hasattr(step, 'depends_on'):
                for dep_id in step.depends_on:
                    if dep_id in step_map:
                        dfs(dep_id, path + [step_id])
            
            rec_stack.remove(step_id)
        
        # Check each step
        for step in steps:
            if step.step_id not in visited:
                dfs(step.step_id, [])
        
        return cycles
    
    async def _validate_security_context(self, plan: ExecutablePlan) -> List[str]:
        """Validate security context configuration."""
        issues = []
        
        security_context = plan.security_context
        
        # Validate allowed tools
        if security_context.allowed_tools:
            # Check that all tools used in plan are in allowed list
            used_tools = set()
            for flow in plan.flows:
                for step in flow.steps:
                    if hasattr(step, 'tool') and step.tool:
                        used_tools.add(step.tool)
            
            disallowed_tools = used_tools - set(security_context.allowed_tools)
            if disallowed_tools:
                issues.append(f"Tools used but not in allowed list: {disallowed_tools}")
        
        # Validate capability requirements
        if security_context.required_capabilities:
            for capability in security_context.required_capabilities:
                if not isinstance(capability, str) or not capability.strip():
                    issues.append("Invalid capability requirement: must be non-empty string")
        
        # Validate policy references
        if security_context.policy_refs:
            for policy_ref in security_context.policy_refs:
                if not isinstance(policy_ref, str) or not policy_ref.strip():
                    issues.append("Invalid policy reference: must be non-empty string")
        
        # Validate approval rules
        if security_context.approval_rules:
            for rule in security_context.approval_rules:
                if not isinstance(rule, str) or not rule.strip():
                    issues.append("Invalid approval rule: must be non-empty string")
        
        return issues
    
    async def _validate_resource_requirements(self, plan: ExecutablePlan) -> List[str]:
        """Validate resource requirements."""
        issues = []
        
        resource_req = plan.resource_requirements
        
        # Validate CPU requirements
        if resource_req.cpu:
            if not self._is_valid_resource_spec(resource_req.cpu):
                issues.append(f"Invalid CPU specification: {resource_req.cpu}")
        
        # Validate memory requirements
        if resource_req.memory:
            if not self._is_valid_resource_spec(resource_req.memory):
                issues.append(f"Invalid memory specification: {resource_req.memory}")
        
        # Validate storage requirements
        if resource_req.storage:
            if not self._is_valid_resource_spec(resource_req.storage):
                issues.append(f"Invalid storage specification: {resource_req.storage}")
        
        # Validate external services
        if resource_req.external_services:
            for service in resource_req.external_services:
                if not isinstance(service, str) or not service.strip():
                    issues.append("Invalid external service: must be non-empty string")
        
        return issues
    
    def _is_valid_resource_spec(self, spec: str) -> bool:
        """Validate resource specification format (e.g., '100m', '1Gi')."""
        import re
        
        # Pattern for Kubernetes resource specifications
        pattern = r'^\d+(\.\d+)?[mMkKgGtT]?[iI]?$'
        return bool(re.match(pattern, spec))
    
    async def _validate_against_request(
        self, 
        plan: ExecutablePlan, 
        request: GhostRunRequest
    ) -> List[str]:
        """Validate plan against simulation request constraints."""
        issues = []
        
        # Validate simulation mode
        valid_modes = {"full", "fast", "security"}
        if request.simulation_mode not in valid_modes:
            issues.append(f"Invalid simulation mode: {request.simulation_mode}")
        
        # Validate connector overrides
        if request.connector_overrides:
            for connector_name, overrides in request.connector_overrides.items():
                if not isinstance(overrides, dict):
                    issues.append(f"Connector override for '{connector_name}' must be a dictionary")
        
        # Check if plan hash matches request
        if request.plan_hash != plan.plan_hash:
            issues.append(
                f"Plan hash mismatch: request={request.plan_hash}, plan={plan.plan_hash}"
            )
        
        return issues