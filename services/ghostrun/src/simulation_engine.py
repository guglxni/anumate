"""Core simulation engine for GhostRun dry-run execution."""

import asyncio
import time
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from .models import (
    FlowSimulationResult,
    GhostRunRequest,
    PreflightReport,
    PreflightRecommendation,
    RiskLevel,
    SimulationMetrics,
    StepSimulationResult,
    ExecutablePlan,
    ExecutionFlow,
    ExecutionStep,
)
from .mock_connectors import mock_connector_registry
from .risk_analyzer import RiskAnalyzer
from .validation_engine import ValidationEngine


class SimulationEngine:
    """Core engine for simulating ExecutablePlan execution."""
    
    def __init__(self) -> None:
        self.risk_analyzer = RiskAnalyzer()
        self.validation_engine = ValidationEngine()
    
    async def simulate_plan(
        self, 
        plan: ExecutablePlan, 
        request: GhostRunRequest
    ) -> Tuple[PreflightReport, SimulationMetrics]:
        """Simulate execution of an ExecutablePlan."""
        
        start_time = time.time()
        
        # Phase 1: Plan loading and validation
        plan_load_start = time.time()
        await self._validate_plan_structure(plan)
        plan_load_time = time.time() - plan_load_start
        
        # Phase 2: Validation
        validation_start = time.time()
        validation_issues = await self.validation_engine.validate_plan(plan, request)
        validation_time = time.time() - validation_start
        
        # Phase 3: Simulation
        simulation_start = time.time()
        flow_results = await self._simulate_flows(plan, request)
        simulation_time = time.time() - simulation_start
        
        # Phase 4: Report generation
        report_start = time.time()
        report = await self._generate_preflight_report(
            plan, request, flow_results, validation_issues, start_time
        )
        report_time = time.time() - report_start
        
        # Calculate metrics
        total_steps = sum(len(flow.steps) for flow in plan.flows)
        total_connectors = len(set(
            step.tool for flow in plan.flows for step in flow.steps 
            if step.tool and mock_connector_registry.get_connector(step.tool)
        ))
        total_api_calls = sum(
            len(result.connector_responses) 
            for flow_result in flow_results 
            for result in flow_result.step_results
        )
        
        metrics = SimulationMetrics.create_from_timing(
            start_time=start_time,
            plan_load_time=plan_load_time,
            validation_time=validation_time,
            simulation_time=simulation_time,
            report_time=report_time,
            steps_count=total_steps,
            connectors_count=total_connectors,
            api_calls_count=total_api_calls
        )
        
        return report, metrics
    
    async def _validate_plan_structure(self, plan: ExecutablePlan) -> None:
        """Validate basic plan structure."""
        if not plan.flows:
            raise ValueError("ExecutablePlan must have at least one flow")
        
        # Validate main flow exists
        main_flow_ids = [flow.flow_id for flow in plan.flows]
        if plan.main_flow not in main_flow_ids:
            raise ValueError(f"Main flow '{plan.main_flow}' not found in plan flows")
        
        # Validate step dependencies
        for flow in plan.flows:
            step_ids = [step.step_id for step in flow.steps]
            for step in flow.steps:
                for dep in step.depends_on:
                    if dep not in step_ids:
                        raise ValueError(
                            f"Step '{step.step_id}' depends on non-existent step '{dep}'"
                        )
    
    async def _simulate_flows(
        self, 
        plan: ExecutablePlan, 
        request: GhostRunRequest
    ) -> List[FlowSimulationResult]:
        """Simulate all flows in the plan."""
        
        flow_results = []
        
        for flow in plan.flows:
            flow_result = await self._simulate_flow(flow, plan, request)
            flow_results.append(flow_result)
        
        return flow_results
    
    async def _simulate_flow(
        self, 
        flow: ExecutionFlow, 
        plan: ExecutablePlan, 
        request: GhostRunRequest
    ) -> FlowSimulationResult:
        """Simulate execution of a single flow."""
        
        step_results = []
        total_execution_time = 0
        flow_issues = []
        
        # Build dependency graph
        dependency_graph = self._build_dependency_graph(flow.steps)
        
        # Simulate steps in dependency order
        execution_order = self._get_execution_order(dependency_graph)
        
        for step_id in execution_order:
            step = next(s for s in flow.steps if s.step_id == step_id)
            
            try:
                step_result = await self._simulate_step(step, plan, request)
                step_results.append(step_result)
                total_execution_time += step_result.execution_time_ms
                
            except Exception as e:
                # Handle step simulation errors
                error_result = StepSimulationResult(
                    step_id=step.step_id,
                    step_name=step.name,
                    would_execute=False,
                    execution_time_ms=0,
                    validation_passed=False,
                    validation_issues=[f"Simulation error: {str(e)}"],
                    risk_level=RiskLevel.CRITICAL
                )
                step_results.append(error_result)
                flow_issues.append(f"Step {step.step_id} simulation failed: {str(e)}")
        
        # Analyze flow-level risks
        overall_risk = self._calculate_flow_risk(step_results)
        would_complete = all(result.would_execute for result in step_results)
        critical_path = self._identify_critical_path(step_results, dependency_graph)
        
        return FlowSimulationResult(
            flow_id=flow.flow_id,
            flow_name=flow.name,
            would_complete=would_complete,
            total_execution_time_ms=total_execution_time,
            step_results=step_results,
            flow_issues=flow_issues,
            overall_risk_level=overall_risk,
            critical_path_steps=critical_path
        )
    
    async def _simulate_step(
        self, 
        step: ExecutionStep, 
        plan: ExecutablePlan, 
        request: GhostRunRequest
    ) -> StepSimulationResult:
        """Simulate execution of a single step."""
        
        # Validate step
        validation_passed, validation_issues = await self._validate_step(step, plan)
        
        # Simulate connector calls
        connector_responses = []
        execution_time = 0
        
        if step.tool and request.mock_external_calls:
            connector = mock_connector_registry.get_connector(step.tool)
            if connector:
                # Get connector overrides
                overrides = request.connector_overrides.get(step.tool, {})
                
                # Simulate the action
                response = connector.simulate_call(
                    tool_name=step.tool,
                    action=step.action or "execute",
                    parameters=step.parameters,
                    overrides=overrides
                )
                connector_responses.append(response)
                execution_time += response.response_time_ms
            else:
                # Unknown connector - create a generic response
                validation_issues.append(f"Unknown connector: {step.tool}")
        
        # Add base step execution time
        base_execution_time = step.timeout or 1000  # Default 1 second
        execution_time += base_execution_time
        
        # Analyze step risks
        risk_level, risk_factors = await self.risk_analyzer.analyze_step_risk(
            step, connector_responses
        )
        
        # Check dependencies
        dependency_issues = self._check_step_dependencies(step)
        
        # Generate simulated outputs
        simulated_outputs = self._generate_step_outputs(step, connector_responses)
        
        # Determine if step would execute
        would_execute = (
            validation_passed and 
            len(dependency_issues) == 0 and
            all(resp.success for resp in connector_responses)
        )
        
        return StepSimulationResult(
            step_id=step.step_id,
            step_name=step.name,
            would_execute=would_execute,
            execution_time_ms=execution_time,
            connector_responses=connector_responses,
            validation_passed=validation_passed,
            validation_issues=validation_issues,
            risk_level=risk_level,
            risk_factors=risk_factors,
            dependency_issues=dependency_issues,
            simulated_outputs=simulated_outputs
        )
    
    async def _validate_step(
        self, 
        step: ExecutionStep, 
        plan: ExecutablePlan
    ) -> Tuple[bool, List[str]]:
        """Validate a single step."""
        issues = []
        
        # Check required fields
        if not step.step_id:
            issues.append("Step ID is required")
        
        if not step.name:
            issues.append("Step name is required")
        
        # Check tool availability
        if step.tool:
            connector = mock_connector_registry.get_connector(step.tool)
            if not connector:
                issues.append(f"Connector '{step.tool}' not available")
            elif step.action and not connector.supports_action(step.tool, step.action):
                issues.append(f"Action '{step.action}' not supported by connector '{step.tool}'")
        
        # Check security context
        if plan.security_context.allowed_tools:
            if step.tool and step.tool not in plan.security_context.allowed_tools:
                issues.append(f"Tool '{step.tool}' not in allowed tools list")
        
        return len(issues) == 0, issues
    
    def _build_dependency_graph(self, steps: List[ExecutionStep]) -> Dict[str, List[str]]:
        """Build dependency graph from steps."""
        graph = {}
        for step in steps:
            graph[step.step_id] = step.depends_on.copy()
        return graph
    
    def _get_execution_order(self, dependency_graph: Dict[str, List[str]]) -> List[str]:
        """Get execution order using topological sort."""
        # Simple topological sort implementation
        in_degree = {node: 0 for node in dependency_graph}
        
        # Calculate in-degrees
        for node in dependency_graph:
            for dep in dependency_graph[node]:
                if dep in in_degree:
                    in_degree[dep] += 1
        
        # Find nodes with no dependencies
        queue = [node for node, degree in in_degree.items() if degree == 0]
        result = []
        
        while queue:
            node = queue.pop(0)
            result.append(node)
            
            # Update in-degrees of dependent nodes
            for dependent in dependency_graph:
                if node in dependency_graph[dependent]:
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        queue.append(dependent)
        
        return result
    
    def _calculate_flow_risk(self, step_results: List[StepSimulationResult]) -> RiskLevel:
        """Calculate overall risk level for a flow."""
        if not step_results:
            return RiskLevel.LOW
        
        # Count risk levels
        risk_counts = {level: 0 for level in RiskLevel}
        for result in step_results:
            risk_counts[result.risk_level] += 1
        
        # Determine overall risk
        if risk_counts[RiskLevel.CRITICAL] > 0:
            return RiskLevel.CRITICAL
        elif risk_counts[RiskLevel.HIGH] > 0:
            return RiskLevel.HIGH
        elif risk_counts[RiskLevel.MEDIUM] > 0:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW
    
    def _identify_critical_path(
        self, 
        step_results: List[StepSimulationResult],
        dependency_graph: Dict[str, List[str]]
    ) -> List[str]:
        """Identify critical path steps (longest execution time path)."""
        # Simple implementation - return steps with highest execution times
        sorted_steps = sorted(
            step_results, 
            key=lambda x: x.execution_time_ms, 
            reverse=True
        )
        
        # Return top 3 longest steps as critical path
        return [step.step_id for step in sorted_steps[:3]]
    
    def _check_step_dependencies(self, step: ExecutionStep) -> List[str]:
        """Check step dependencies for issues."""
        issues = []
        
        # For simulation, we assume dependencies are satisfied
        # In a real implementation, this would check actual dependency states
        
        return issues
    
    def _generate_step_outputs(
        self, 
        step: ExecutionStep, 
        connector_responses: List[Any]
    ) -> Dict[str, Any]:
        """Generate simulated step outputs."""
        outputs = {}
        
        # Generate outputs based on step configuration
        for output_key, output_mapping in step.outputs.items():
            if connector_responses:
                # Use data from connector responses
                outputs[output_key] = f"simulated_value_from_{step.step_id}"
            else:
                # Generate generic output
                outputs[output_key] = f"simulated_{output_key}"
        
        return outputs
    
    async def _generate_preflight_report(
        self,
        plan: ExecutablePlan,
        request: GhostRunRequest,
        flow_results: List[FlowSimulationResult],
        validation_issues: List[str],
        start_time: float
    ) -> PreflightReport:
        """Generate comprehensive preflight report."""
        
        # Calculate overall metrics
        total_steps = sum(len(result.step_results) for result in flow_results)
        steps_with_issues = sum(
            1 for result in flow_results 
            for step in result.step_results 
            if not step.validation_passed or step.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]
        )
        high_risk_steps = sum(
            1 for result in flow_results 
            for step in result.step_results 
            if step.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]
        )
        
        total_estimated_duration = sum(result.total_execution_time_ms for result in flow_results)
        
        # Determine overall status
        execution_feasible = all(result.would_complete for result in flow_results)
        overall_risk = self._calculate_overall_risk(flow_results)
        overall_status = "PASS" if execution_feasible and len(validation_issues) == 0 else "FAIL"
        
        # Collect issues
        critical_issues = validation_issues.copy()
        warnings = []
        
        for flow_result in flow_results:
            critical_issues.extend(flow_result.flow_issues)
            for step_result in flow_result.step_results:
                if step_result.risk_level == RiskLevel.CRITICAL:
                    critical_issues.extend(step_result.validation_issues)
                elif step_result.risk_level in [RiskLevel.HIGH, RiskLevel.MEDIUM]:
                    warnings.extend(step_result.validation_issues)
        
        # Generate recommendations
        recommendations = await self._generate_recommendations(flow_results, validation_issues)
        
        # Analyze resources and security
        resource_requirements = self._analyze_resource_requirements(plan, flow_results)
        security_issues = await self._analyze_security_issues(plan, flow_results)
        policy_violations = []  # Would integrate with policy service
        
        # Identify performance bottlenecks
        performance_bottlenecks = self._identify_performance_bottlenecks(flow_results)
        
        simulation_duration = int((time.time() - start_time) * 1000)
        
        return PreflightReport(
            run_id=uuid4(),  # Generate a unique run_id for the report
            plan_hash=plan.plan_hash,
            simulation_duration_ms=simulation_duration,
            overall_status=overall_status,
            overall_risk_level=overall_risk,
            execution_feasible=execution_feasible,
            flow_results=flow_results,
            total_estimated_duration_ms=total_estimated_duration,
            estimated_cost=None,  # Would calculate based on resource usage
            critical_issues=critical_issues,
            warnings=warnings,
            recommendations=recommendations,
            resource_requirements=resource_requirements,
            security_issues=security_issues,
            policy_violations=policy_violations,
            performance_bottlenecks=performance_bottlenecks,
            total_steps=total_steps,
            steps_with_issues=steps_with_issues,
            high_risk_steps=high_risk_steps
        )
    
    def _calculate_overall_risk(self, flow_results: List[FlowSimulationResult]) -> RiskLevel:
        """Calculate overall risk level across all flows."""
        if not flow_results:
            return RiskLevel.LOW
        
        max_risk = RiskLevel.LOW
        for result in flow_results:
            if result.overall_risk_level.value > max_risk.value:
                max_risk = result.overall_risk_level
        
        return max_risk
    
    async def _generate_recommendations(
        self, 
        flow_results: List[FlowSimulationResult],
        validation_issues: List[str]
    ) -> List[PreflightRecommendation]:
        """Generate recommendations based on simulation results."""
        recommendations = []
        
        # Recommendation for high-risk steps
        high_risk_steps = []
        for flow_result in flow_results:
            for step_result in flow_result.step_results:
                if step_result.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
                    high_risk_steps.append(step_result.step_id)
        
        if high_risk_steps:
            recommendations.append(PreflightRecommendation(
                type="risk_mitigation",
                severity=RiskLevel.HIGH,
                title="High-Risk Steps Detected",
                description=f"Found {len(high_risk_steps)} high-risk steps that require attention",
                suggested_actions=[
                    "Review step configurations for high-risk operations",
                    "Consider adding approval requirements for critical steps",
                    "Implement additional error handling and rollback procedures"
                ],
                affected_steps=high_risk_steps
            ))
        
        # Recommendation for performance optimization
        slow_steps = []
        for flow_result in flow_results:
            for step_result in flow_result.step_results:
                if step_result.execution_time_ms > 5000:  # > 5 seconds
                    slow_steps.append(step_result.step_id)
        
        if slow_steps:
            recommendations.append(PreflightRecommendation(
                type="performance_optimization",
                severity=RiskLevel.MEDIUM,
                title="Performance Optimization Opportunities",
                description=f"Found {len(slow_steps)} steps with long execution times",
                suggested_actions=[
                    "Consider parallelizing independent operations",
                    "Optimize connector configurations for better performance",
                    "Add timeout configurations to prevent hanging operations"
                ],
                affected_steps=slow_steps
            ))
        
        return recommendations
    
    def _analyze_resource_requirements(
        self, 
        plan: ExecutablePlan, 
        flow_results: List[FlowSimulationResult]
    ) -> Dict[str, Any]:
        """Analyze resource requirements based on simulation."""
        
        total_execution_time = sum(result.total_execution_time_ms for result in flow_results)
        concurrent_steps = max(len(result.step_results) for result in flow_results) if flow_results else 0
        
        return {
            "estimated_cpu_usage": f"{concurrent_steps * 100}m",  # 100m per concurrent step
            "estimated_memory_usage": f"{concurrent_steps * 128}Mi",  # 128Mi per concurrent step
            "estimated_network_calls": sum(
                len(step.connector_responses) 
                for result in flow_results 
                for step in result.step_results
            ),
            "estimated_duration_seconds": total_execution_time / 1000,
            "concurrent_operations": concurrent_steps
        }
    
    async def _analyze_security_issues(
        self, 
        plan: ExecutablePlan, 
        flow_results: List[FlowSimulationResult]
    ) -> List[str]:
        """Analyze security issues from simulation."""
        issues = []
        
        # Check for tools not in allowlist
        if plan.security_context.allowed_tools:
            for flow_result in flow_results:
                for step_result in flow_result.step_results:
                    for response in step_result.connector_responses:
                        if response.connector_name not in plan.security_context.allowed_tools:
                            issues.append(
                                f"Step {step_result.step_id} uses non-allowed tool: {response.connector_name}"
                            )
        
        # Check for high-risk operations without approval
        if not plan.security_context.requires_approval:
            high_risk_operations = [
                step_result.step_id for flow_result in flow_results 
                for step_result in flow_result.step_results
                if step_result.risk_level == RiskLevel.CRITICAL
            ]
            if high_risk_operations:
                issues.append(
                    f"Critical risk operations detected but no approval required: {high_risk_operations}"
                )
        
        return issues
    
    def _identify_performance_bottlenecks(
        self, 
        flow_results: List[FlowSimulationResult]
    ) -> List[str]:
        """Identify performance bottlenecks."""
        bottlenecks = []
        
        for flow_result in flow_results:
            # Find steps that take more than 50% of total flow time
            flow_time = flow_result.total_execution_time_ms
            threshold = flow_time * 0.5
            
            for step_result in flow_result.step_results:
                if step_result.execution_time_ms > threshold:
                    bottlenecks.append(
                        f"Step {step_result.step_id} takes {step_result.execution_time_ms}ms "
                        f"({step_result.execution_time_ms/flow_time*100:.1f}% of flow time)"
                    )
        
        return bottlenecks