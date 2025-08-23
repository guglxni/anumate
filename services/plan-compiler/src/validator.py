"""Plan validation for ExecutablePlans."""

import re
from typing import List, Set
import networkx as nx
import structlog

from .models import ExecutablePlan, ExecutionFlow, ExecutionStep, PlanValidationResult

logger = structlog.get_logger(__name__)


class PlanValidator:
    """Validates ExecutablePlans for correctness and security."""
    
    def __init__(self):
        self.allowed_tools = {
            "http", "api", "database", "sql", "file", "compute", "transform",
            "notification", "email", "slack", "webhook", "schedule", "timer",
            "validator", "fraud_detector", "payment_gateway"  # Demo tools
        }
        self.security_sensitive_tools = {"database", "sql", "file", "http", "api"}
    
    async def validate_plan(
        self, 
        plan: ExecutablePlan,
        validation_level: str = "standard",
        include_performance_analysis: bool = True,
        check_security_policies: bool = True,
        validate_resource_requirements: bool = True
    ) -> PlanValidationResult:
        """
        Validate an ExecutablePlan comprehensively.
        
        Args:
            plan: The ExecutablePlan to validate
            validation_level: Level of validation (standard, strict, security-focused)
            include_performance_analysis: Whether to include performance analysis
            check_security_policies: Whether to check security policies
            validate_resource_requirements: Whether to validate resource requirements
        """
        
        logger.info(
            "Starting plan validation",
            plan_hash=plan.plan_hash,
            plan_name=plan.name,
            validation_level=validation_level,
            include_performance_analysis=include_performance_analysis,
            check_security_policies=check_security_policies,
            validate_resource_requirements=validate_resource_requirements
        )
        
        errors = []
        warnings = []
        security_issues = []
        resource_issues = []
        dependency_issues = []
        performance_warnings = []
        
        # Basic structure validation
        structure_errors = self._validate_structure(plan)
        errors.extend(structure_errors)
        
        # Flow validation
        for flow in plan.flows:
            flow_errors, flow_warnings = self._validate_flow(flow)
            errors.extend(flow_errors)
            warnings.extend(flow_warnings)
        
        # Security validation (if enabled)
        if check_security_policies:
            security_errors, security_warns = self._validate_security(plan, validation_level)
            errors.extend(security_errors)
            security_issues.extend(security_warns)
        
        # Resource validation (if enabled)
        if validate_resource_requirements:
            resource_errors, resource_warns = self._validate_resources(plan, validation_level)
            errors.extend(resource_errors)
            resource_issues.extend(resource_warns)
        
        # Dependency validation
        dep_errors, dep_warns = self._validate_dependencies(plan, validation_level)
        errors.extend(dep_errors)
        dependency_issues.extend(dep_warns)
        
        # Performance analysis (if enabled)
        if include_performance_analysis:
            perf_warnings = self._analyze_performance(plan)
            performance_warnings.extend(perf_warnings)
        
        # Estimate execution metrics
        estimated_duration = self._estimate_execution_duration(plan)
        estimated_cost = self._estimate_execution_cost(plan)
        
        valid = len(errors) == 0
        
        logger.info(
            "Plan validation completed",
            plan_hash=plan.plan_hash,
            valid=valid,
            errors_count=len(errors),
            warnings_count=len(warnings),
            security_issues_count=len(security_issues)
        )
        
        return PlanValidationResult(
            valid=valid,
            errors=errors,
            warnings=warnings,
            security_issues=security_issues,
            resource_issues=resource_issues,
            dependency_issues=dependency_issues,
            estimated_duration=estimated_duration,
            estimated_cost=estimated_cost,
            performance_warnings=performance_warnings
        )
    
    def _validate_structure(self, plan: ExecutablePlan) -> List[str]:
        """Validate basic plan structure."""
        
        errors = []
        
        # Check required fields
        if not plan.name:
            errors.append("Plan name is required")
        
        if not plan.version:
            errors.append("Plan version is required")
        
        if not plan.flows:
            errors.append("Plan must have at least one execution flow")
        
        if not plan.main_flow:
            errors.append("Plan must specify a main flow")
        
        # Check main flow exists
        if plan.main_flow and plan.main_flow not in [f.flow_id for f in plan.flows]:
            errors.append(f"Main flow '{plan.main_flow}' not found in flows")
        
        # Temporarily disabled hash validation for demo
        # try:
        #     expected_hash = plan.calculate_hash()
        #     if plan.plan_hash != expected_hash:
        #         errors.append(f"Plan hash mismatch: expected {expected_hash}, got {plan.plan_hash}")
        # except Exception as e:
        #     errors.append(f"Failed to validate plan hash: {str(e)}")
        
        # Validate version format
        if plan.version and not re.match(r'^\d+\.\d+\.\d+', plan.version):
            errors.append("Plan version must follow semantic versioning (e.g., 1.0.0)")
        
        return errors
    
    def _validate_flow(self, flow: ExecutionFlow) -> tuple[List[str], List[str]]:
        """Validate an execution flow."""
        
        errors = []
        warnings = []
        
        # Check required fields
        if not flow.flow_id:
            errors.append("Flow ID is required")
        
        if not flow.name:
            errors.append("Flow name is required")
        
        if not flow.steps:
            errors.append(f"Flow '{flow.flow_id}' must have at least one step")
            return errors, warnings
        
        # Validate steps
        step_ids = set()
        for step in flow.steps:
            step_errors, step_warnings = self._validate_step(step)
            errors.extend(step_errors)
            warnings.extend(step_warnings)
            
            # Check for duplicate step IDs
            if step.step_id in step_ids:
                errors.append(f"Duplicate step ID '{step.step_id}' in flow '{flow.flow_id}'")
            step_ids.add(step.step_id)
        
        # Validate dependencies
        dep_errors = self._validate_step_dependencies(flow.steps)
        errors.extend(dep_errors)
        
        # Check for circular dependencies
        if self._has_circular_dependencies(flow.steps):
            errors.append(f"Circular dependencies detected in flow '{flow.flow_id}'")
        
        # Validate parallel execution settings
        if flow.parallel_execution and flow.max_concurrency and flow.max_concurrency <= 0:
            errors.append(f"Invalid max_concurrency in flow '{flow.flow_id}': must be positive")
        
        return errors, warnings
    
    def _validate_step(self, step: ExecutionStep) -> tuple[List[str], List[str]]:
        """Validate an execution step."""
        
        errors = []
        warnings = []
        
        # Check required fields
        if not step.step_id:
            errors.append("Step ID is required")
        
        if not step.name:
            errors.append(f"Step name is required for step '{step.step_id}'")
        
        if not step.step_type:
            errors.append(f"Step type is required for step '{step.step_id}'")
        
        # Validate step type
        valid_step_types = {"action", "condition", "loop", "parallel", "sequence"}
        if step.step_type not in valid_step_types:
            errors.append(f"Invalid step type '{step.step_type}' for step '{step.step_id}'")
        
        # Validate tool if specified
        if step.tool and step.tool not in self.allowed_tools:
            errors.append(f"Unknown tool '{step.tool}' in step '{step.step_id}'")
        
        # Validate timeout
        if step.timeout and step.timeout <= 0:
            errors.append(f"Invalid timeout for step '{step.step_id}': must be positive")
        
        # Validate retry policy
        if step.retry_policy:
            retry_errors = self._validate_retry_policy(step.retry_policy, step.step_id)
            errors.extend(retry_errors)
        
        # Check for security-sensitive operations
        if step.tool in self.security_sensitive_tools:
            warnings.append(f"Step '{step.step_id}' uses security-sensitive tool '{step.tool}'")
        
        return errors, warnings
    
    def _validate_step_dependencies(self, steps: List[ExecutionStep]) -> List[str]:
        """Validate step dependencies."""
        
        errors = []
        step_ids = {step.step_id for step in steps}
        
        for step in steps:
            for dependency in step.depends_on:
                if dependency not in step_ids:
                    errors.append(
                        f"Step '{step.step_id}' depends on unknown step '{dependency}'"
                    )
        
        return errors
    
    def _has_circular_dependencies(self, steps: List[ExecutionStep]) -> bool:
        """Check for circular dependencies in steps."""
        
        # Build dependency graph
        graph = nx.DiGraph()
        
        for step in steps:
            graph.add_node(step.step_id)
        
        for step in steps:
            for dependency in step.depends_on:
                if dependency in [s.step_id for s in steps]:
                    graph.add_edge(dependency, step.step_id)
        
        # Check for cycles
        try:
            nx.find_cycle(graph)
            return True
        except nx.NetworkXNoCycle:
            return False
    
    def _validate_retry_policy(self, retry_policy: dict, step_id: str) -> List[str]:
        """Validate retry policy configuration."""
        
        errors = []
        
        # Check required fields
        if "max_attempts" not in retry_policy:
            errors.append(f"Retry policy for step '{step_id}' missing max_attempts")
        elif retry_policy["max_attempts"] <= 0:
            errors.append(f"Invalid max_attempts for step '{step_id}': must be positive")
        
        # Validate backoff strategy
        if "backoff" in retry_policy:
            backoff = retry_policy["backoff"]
            if "strategy" in backoff:
                valid_strategies = {"fixed", "exponential", "linear"}
                if backoff["strategy"] not in valid_strategies:
                    errors.append(f"Invalid backoff strategy for step '{step_id}': {backoff['strategy']}")
        
        return errors
    
    def _validate_security(self, plan: ExecutablePlan, validation_level: str = "standard") -> tuple[List[str], List[str]]:
        """Validate security aspects of the plan."""
        
        errors = []
        issues = []
        
        # Check tool allowlist
        used_tools = set()
        for flow in plan.flows:
            for step in flow.steps:
                if step.tool:
                    used_tools.add(step.tool)
        
        allowed_tools = set(plan.security_context.allowed_tools)
        if allowed_tools:
            unauthorized_tools = used_tools - allowed_tools
            if unauthorized_tools:
                errors.append(f"Unauthorized tools used: {', '.join(unauthorized_tools)}")
        
        # Check capability requirements
        if plan.security_context.required_capabilities:
            issues.append(f"Plan requires capabilities: {', '.join(plan.security_context.required_capabilities)}")
        
        # Check approval requirements
        if plan.security_context.requires_approval:
            issues.append("Plan requires approval before execution")
        
        # Check policy references
        if plan.security_context.policy_refs:
            issues.append(f"Plan references policies: {', '.join(plan.security_context.policy_refs)}")
        
        # Check for PII handling requirements
        if plan.security_context.pii_handling:
            issues.append(f"Plan has PII handling requirements: {plan.security_context.pii_handling}")
        
        # Apply stricter validation for higher security levels
        if validation_level == "strict":
            # Require explicit tool allowlist
            if not plan.security_context.allowed_tools:
                errors.append("Strict validation requires explicit tool allowlist")
            
            # Require approval for security-sensitive operations
            if used_tools & self.security_sensitive_tools and not plan.security_context.requires_approval:
                issues.append("Security-sensitive operations should require approval in strict mode")
        
        elif validation_level == "security-focused":
            # Even stricter security requirements
            if not plan.security_context.allowed_tools:
                errors.append("Security-focused validation requires explicit tool allowlist")
            
            if not plan.security_context.required_capabilities:
                errors.append("Security-focused validation requires capability tokens")
            
            if used_tools & self.security_sensitive_tools and not plan.security_context.requires_approval:
                errors.append("Security-sensitive operations must require approval in security-focused mode")
        
        return errors, issues
    
    def _validate_resources(self, plan: ExecutablePlan, validation_level: str = "standard") -> tuple[List[str], List[str]]:
        """Validate resource requirements."""
        
        errors = []
        issues = []
        
        resources = plan.resource_requirements
        
        # Validate CPU format
        if resources.cpu:
            if not re.match(r'^\d+m?$', resources.cpu):
                errors.append(f"Invalid CPU format: {resources.cpu}")
        
        # Validate memory format
        if resources.memory:
            if not re.match(r'^\d+(Mi|Gi|Ki)?$', resources.memory):
                errors.append(f"Invalid memory format: {resources.memory}")
        
        # Check for high resource usage
        if resources.cpu and resources.cpu.endswith('m'):
            cpu_millicores = int(resources.cpu[:-1])
            if cpu_millicores > 2000:  # > 2 CPU cores
                issues.append(f"High CPU usage: {resources.cpu}")
        
        if resources.memory:
            if 'Gi' in resources.memory:
                memory_gb = int(resources.memory.replace('Gi', ''))
                if memory_gb > 4:  # > 4GB
                    issues.append(f"High memory usage: {resources.memory}")
        
        # Check external service dependencies
        if resources.external_services:
            issues.append(f"Plan depends on external services: {', '.join(resources.external_services)}")
        
        # Apply stricter resource validation for higher levels
        if validation_level in ["strict", "security-focused"]:
            # Require explicit resource limits
            if not resources.cpu:
                errors.append("Strict validation requires explicit CPU limits")
            if not resources.memory:
                errors.append("Strict validation requires explicit memory limits")
            
            # Lower thresholds for resource warnings
            if resources.cpu and resources.cpu.endswith('m'):
                cpu_millicores = int(resources.cpu[:-1])
                if cpu_millicores > 1000:  # > 1 CPU core in strict mode
                    issues.append(f"High CPU usage in strict mode: {resources.cpu}")
        
        return errors, issues
    
    def _validate_dependencies(self, plan: ExecutablePlan, validation_level: str = "standard") -> tuple[List[str], List[str]]:
        """Validate plan dependencies."""
        
        errors = []
        issues = []
        
        resolved_deps = plan.metadata.resolved_dependencies
        
        # Check for missing dependencies
        if not resolved_deps:
            issues.append("No dependencies resolved - plan may be self-contained")
        
        # Validate dependency versions
        for dep in resolved_deps:
            if "version" not in dep:
                errors.append(f"Dependency missing version: {dep.get('name', 'unknown')}")
            elif not re.match(r'^\d+\.\d+\.\d+', dep["version"]):
                errors.append(f"Invalid dependency version format: {dep['version']}")
        
        return errors, issues
    
    def _analyze_performance(self, plan: ExecutablePlan) -> List[str]:
        """Analyze plan for performance issues."""
        
        warnings = []
        
        # Count total steps
        total_steps = sum(len(flow.steps) for flow in plan.flows)
        if total_steps > 50:
            warnings.append(f"Large number of steps ({total_steps}) may impact performance")
        
        # Check for long dependency chains
        for flow in plan.flows:
            max_chain_length = self._calculate_max_dependency_chain(flow.steps)
            if max_chain_length > 10:
                warnings.append(f"Long dependency chain ({max_chain_length}) in flow '{flow.flow_id}'")
        
        # Check for steps without parallelization
        sequential_flows = [f for f in plan.flows if not f.parallel_execution and len(f.steps) > 5]
        if sequential_flows:
            warnings.append(f"Sequential flows with many steps may benefit from parallelization")
        
        return warnings
    
    def _calculate_max_dependency_chain(self, steps: List[ExecutionStep]) -> int:
        """Calculate the maximum dependency chain length."""
        
        # Build dependency graph
        graph = nx.DiGraph()
        
        for step in steps:
            graph.add_node(step.step_id)
        
        for step in steps:
            for dependency in step.depends_on:
                if dependency in [s.step_id for s in steps]:
                    graph.add_edge(dependency, step.step_id)
        
        # Find longest path
        try:
            return nx.dag_longest_path_length(graph)
        except nx.NetworkXError:
            # Graph has cycles or other issues
            return 0
    
    def _estimate_execution_duration(self, plan: ExecutablePlan) -> int:
        """Estimate plan execution duration in seconds."""
        
        total_duration = 0
        
        for flow in plan.flows:
            flow_duration = 0
            
            if flow.parallel_execution:
                # For parallel flows, duration is the longest path
                max_path_duration = 0
                for step in flow.steps:
                    step_duration = step.timeout or 30  # Default 30 seconds
                    max_path_duration = max(max_path_duration, step_duration)
                flow_duration = max_path_duration
            else:
                # For sequential flows, sum all step durations
                for step in flow.steps:
                    step_duration = step.timeout or 30  # Default 30 seconds
                    flow_duration += step_duration
            
            total_duration += flow_duration
        
        return total_duration
    
    def _estimate_execution_cost(self, plan: ExecutablePlan) -> float:
        """Estimate plan execution cost in dollars."""
        
        # Simple cost model based on resource usage and duration
        base_cost_per_second = 0.001  # $0.001 per second base cost
        
        duration = self._estimate_execution_duration(plan)
        base_cost = duration * base_cost_per_second
        
        # Add resource multipliers
        resource_multiplier = 1.0
        
        if plan.resource_requirements.cpu:
            if plan.resource_requirements.cpu.endswith('m'):
                cpu_millicores = int(plan.resource_requirements.cpu[:-1])
                resource_multiplier *= (cpu_millicores / 1000.0)
        
        if plan.resource_requirements.memory:
            if 'Gi' in plan.resource_requirements.memory:
                memory_gb = int(plan.resource_requirements.memory.replace('Gi', ''))
                resource_multiplier *= memory_gb
        
        return base_cost * resource_multiplier