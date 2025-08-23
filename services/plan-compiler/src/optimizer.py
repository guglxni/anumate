"""Plan optimization for ExecutablePlans."""

import networkx as nx
from typing import Dict, List, Set, Optional
import structlog

from .models import ExecutablePlan, ExecutionFlow, ExecutionStep
from .dependency_analyzer import DependencyAnalyzer, DependencyAnalysisResult
from .cache_service import get_cache_service

logger = structlog.get_logger(__name__)


class PlanOptimizer:
    """Optimizes ExecutablePlans for performance and resource usage."""
    
    def __init__(self):
        self.optimization_strategies = {
            "none": self._no_optimization,
            "basic": self._basic_optimization,
            "standard": self._standard_optimization,
            "aggressive": self._aggressive_optimization
        }
        self.dependency_analyzer = DependencyAnalyzer()
        self.cache_service = get_cache_service()
        
        # Optimization cache for expensive operations
        self._optimization_cache: Dict[str, ExecutablePlan] = {}
    
    async def optimize_plan(self, plan: ExecutablePlan, optimization_level: str = "standard") -> ExecutablePlan:
        """Optimize an ExecutablePlan based on the optimization level."""
        
        logger.info(
            "Starting plan optimization",
            plan_hash=plan.plan_hash,
            optimization_level=optimization_level
        )
        
        # Check optimization cache first
        cache_key = f"{plan.plan_hash}:{optimization_level}"
        if cache_key in self._optimization_cache:
            logger.info(
                "Using cached optimization result",
                plan_hash=plan.plan_hash,
                optimization_level=optimization_level
            )
            return self._optimization_cache[cache_key]
        
        if optimization_level not in self.optimization_strategies:
            logger.warning(
                "Unknown optimization level, using standard",
                requested_level=optimization_level
            )
            optimization_level = "standard"
        
        # Perform dependency analysis for advanced optimizations
        dependency_analysis = None
        if optimization_level in ["standard", "aggressive"]:
            dependency_analysis = await self.dependency_analyzer.analyze_plan_dependencies(plan)
            
            # Update plan metadata with analysis results
            plan.metadata.estimated_duration = dependency_analysis.total_estimated_duration
            plan.metadata.estimated_cost = dependency_analysis.total_estimated_cost
        
        # Apply optimization strategy
        optimizer_func = self.optimization_strategies[optimization_level]
        optimized_plan = await optimizer_func(plan, dependency_analysis)
        
        # Update metadata with optimization info
        optimized_plan.metadata.optimization_level = optimization_level
        optimized_plan.metadata.optimization_notes.append(
            f"Applied {optimization_level} optimization"
        )
        
        # Add dependency analysis insights to metadata
        if dependency_analysis:
            optimized_plan.metadata.optimization_notes.extend(
                dependency_analysis.optimization_recommendations
            )
        
        # Recalculate plan hash after optimization
        optimized_plan.plan_hash = optimized_plan.calculate_hash()
        
        # Cache the optimization result
        self._optimization_cache[cache_key] = optimized_plan
        
        # Cache the optimized plan in the main cache service
        await self.cache_service.put(
            optimized_plan,
            tags=[f"optimization:{optimization_level}", "optimized"]
        )
        
        logger.info(
            "Plan optimization completed",
            original_hash=plan.plan_hash,
            optimized_hash=optimized_plan.plan_hash,
            optimization_level=optimization_level,
            estimated_duration=optimized_plan.metadata.estimated_duration,
            estimated_cost=optimized_plan.metadata.estimated_cost
        )
        
        return optimized_plan
    
    async def _no_optimization(self, plan: ExecutablePlan, dependency_analysis: Optional[DependencyAnalysisResult] = None) -> ExecutablePlan:
        """No optimization - return plan as-is."""
        return plan
    
    async def _basic_optimization(self, plan: ExecutablePlan, dependency_analysis: Optional[DependencyAnalysisResult] = None) -> ExecutablePlan:
        """Basic optimization - remove redundant steps and optimize simple sequences."""
        
        optimized_flows = []
        
        for flow in plan.flows:
            optimized_flow = await self._optimize_flow_basic(flow, dependency_analysis)
            optimized_flows.append(optimized_flow)
        
        # Create new plan with optimized flows
        optimized_plan = ExecutablePlan.create(
            tenant_id=plan.tenant_id,
            name=plan.name,
            version=plan.version,
            description=plan.description,
            flows=optimized_flows,
            main_flow=plan.main_flow,
            metadata=plan.metadata,
            resource_requirements=plan.resource_requirements,
            security_context=plan.security_context,
            configuration=plan.configuration,
            variables=plan.variables
        )
        
        return optimized_plan
    
    async def _standard_optimization(self, plan: ExecutablePlan, dependency_analysis: Optional[DependencyAnalysisResult] = None) -> ExecutablePlan:
        """Standard optimization - includes basic optimizations plus parallelization."""
        
        # Start with basic optimization
        plan = await self._basic_optimization(plan, dependency_analysis)
        
        optimized_flows = []
        
        for flow in plan.flows:
            # Apply parallelization optimization using dependency analysis
            optimized_flow = await self._optimize_flow_parallelization(flow, dependency_analysis)
            optimized_flows.append(optimized_flow)
        
        # Apply cost-based optimizations if analysis is available
        if dependency_analysis:
            optimized_flows = await self._apply_cost_optimizations(optimized_flows, dependency_analysis)
        
        # Create new plan with optimized flows
        optimized_plan = ExecutablePlan.create(
            tenant_id=plan.tenant_id,
            name=plan.name,
            version=plan.version,
            description=plan.description,
            flows=optimized_flows,
            main_flow=plan.main_flow,
            metadata=plan.metadata,
            resource_requirements=plan.resource_requirements,
            security_context=plan.security_context,
            configuration=plan.configuration,
            variables=plan.variables
        )
        
        return optimized_plan
    
    async def _aggressive_optimization(self, plan: ExecutablePlan, dependency_analysis: Optional[DependencyAnalysisResult] = None) -> ExecutablePlan:
        """Aggressive optimization - includes all optimizations plus advanced techniques."""
        
        # Start with standard optimization
        plan = await self._standard_optimization(plan, dependency_analysis)
        
        optimized_flows = []
        
        for flow in plan.flows:
            # Apply advanced optimizations
            optimized_flow = await self._optimize_flow_advanced(flow, dependency_analysis)
            optimized_flows.append(optimized_flow)
        
        # Apply graph-based optimizations if analysis is available
        if dependency_analysis:
            optimized_flows = await self._apply_graph_optimizations(optimized_flows, dependency_analysis)
        
        # Create new plan with optimized flows
        optimized_plan = ExecutablePlan.create(
            tenant_id=plan.tenant_id,
            name=plan.name,
            version=plan.version,
            description=plan.description,
            flows=optimized_flows,
            main_flow=plan.main_flow,
            metadata=plan.metadata,
            resource_requirements=plan.resource_requirements,
            security_context=plan.security_context,
            configuration=plan.configuration,
            variables=plan.variables
        )
        
        return optimized_plan
    
    async def _optimize_flow_basic(self, flow: ExecutionFlow) -> ExecutionFlow:
        """Apply basic optimizations to a flow."""
        
        optimized_steps = []
        
        # Remove duplicate steps
        seen_steps = set()
        for step in flow.steps:
            step_signature = self._get_step_signature(step)
            if step_signature not in seen_steps:
                optimized_steps.append(step)
                seen_steps.add(step_signature)
        
        # Merge consecutive steps with same tool where possible
        merged_steps = self._merge_consecutive_steps(optimized_steps)
        
        return ExecutionFlow(
            flow_id=flow.flow_id,
            name=flow.name,
            description=flow.description,
            steps=merged_steps,
            parallel_execution=flow.parallel_execution,
            max_concurrency=flow.max_concurrency,
            on_failure=flow.on_failure,
            rollback_steps=flow.rollback_steps,
            metadata=flow.metadata
        )
    
    async def _optimize_flow_parallelization(self, flow: ExecutionFlow) -> ExecutionFlow:
        """Optimize flow for parallel execution."""
        
        # Build dependency graph
        dependency_graph = self._build_dependency_graph(flow.steps)
        
        # Identify steps that can run in parallel
        parallel_groups = self._identify_parallel_groups(dependency_graph)
        
        # Update flow configuration for parallelization
        optimized_flow = ExecutionFlow(
            flow_id=flow.flow_id,
            name=flow.name,
            description=flow.description,
            steps=flow.steps,
            parallel_execution=len(parallel_groups) > 1,
            max_concurrency=min(len(parallel_groups), 10),  # Reasonable default
            on_failure=flow.on_failure,
            rollback_steps=flow.rollback_steps,
            metadata={
                **flow.metadata,
                "parallel_groups": len(parallel_groups),
                "parallelization_optimized": True
            }
        )
        
        return optimized_flow
    
    async def _optimize_flow_advanced(self, flow: ExecutionFlow) -> ExecutionFlow:
        """Apply advanced optimizations to a flow."""
        
        # Start with parallelization optimization
        flow = await self._optimize_flow_parallelization(flow)
        
        # Apply resource-aware optimization
        optimized_steps = self._optimize_resource_usage(flow.steps)
        
        # Apply caching optimization
        cached_steps = self._optimize_step_caching(optimized_steps)
        
        return ExecutionFlow(
            flow_id=flow.flow_id,
            name=flow.name,
            description=flow.description,
            steps=cached_steps,
            parallel_execution=flow.parallel_execution,
            max_concurrency=flow.max_concurrency,
            on_failure=flow.on_failure,
            rollback_steps=flow.rollback_steps,
            metadata={
                **flow.metadata,
                "advanced_optimization": True
            }
        )
    
    def _get_step_signature(self, step: ExecutionStep) -> str:
        """Generate a signature for step deduplication."""
        return f"{step.step_type}:{step.action}:{step.tool}:{hash(str(sorted(step.parameters.items())))}"
    
    def _merge_consecutive_steps(self, steps: List[ExecutionStep]) -> List[ExecutionStep]:
        """Merge consecutive steps that can be combined."""
        
        if len(steps) <= 1:
            return steps
        
        merged_steps = [steps[0]]
        
        for current_step in steps[1:]:
            previous_step = merged_steps[-1]
            
            # Check if steps can be merged
            if self._can_merge_steps(previous_step, current_step):
                # Merge the steps
                merged_step = self._merge_two_steps(previous_step, current_step)
                merged_steps[-1] = merged_step
            else:
                merged_steps.append(current_step)
        
        return merged_steps
    
    def _can_merge_steps(self, step1: ExecutionStep, step2: ExecutionStep) -> bool:
        """Check if two steps can be merged."""
        
        # Only merge steps with same tool and compatible actions
        if step1.tool != step2.tool:
            return False
        
        # Don't merge if step2 depends on step1
        if step1.step_id in step2.depends_on:
            return False
        
        # Don't merge if they have different retry policies
        if step1.retry_policy != step2.retry_policy:
            return False
        
        # Only merge simple action steps
        if step1.step_type != "action" or step2.step_type != "action":
            return False
        
        return True
    
    def _merge_two_steps(self, step1: ExecutionStep, step2: ExecutionStep) -> ExecutionStep:
        """Merge two compatible steps."""
        
        # Combine parameters
        merged_parameters = {**step1.parameters, **step2.parameters}
        
        # Combine inputs and outputs
        merged_inputs = {**step1.inputs, **step2.inputs}
        merged_outputs = {**step1.outputs, **step2.outputs}
        
        # Combine dependencies
        merged_depends_on = list(set(step1.depends_on + step2.depends_on))
        
        return ExecutionStep(
            step_id=f"{step1.step_id}_merged_{step2.step_id}",
            name=f"{step1.name} + {step2.name}",
            description=f"Merged: {step1.description or step1.name} and {step2.description or step2.name}",
            step_type=step1.step_type,
            action=step1.action,
            tool=step1.tool,
            parameters=merged_parameters,
            inputs=merged_inputs,
            outputs=merged_outputs,
            depends_on=merged_depends_on,
            conditions=step1.conditions + step2.conditions,
            retry_policy=step1.retry_policy,
            timeout=max(step1.timeout or 0, step2.timeout or 0) or None,
            metadata={
                **step1.metadata,
                **step2.metadata,
                "merged_from": [step1.step_id, step2.step_id]
            },
            tags=list(set(step1.tags + step2.tags))
        )
    
    def _build_dependency_graph(self, steps: List[ExecutionStep]) -> nx.DiGraph:
        """Build a dependency graph from execution steps."""
        
        graph = nx.DiGraph()
        
        # Add all steps as nodes
        for step in steps:
            graph.add_node(step.step_id, step=step)
        
        # Add dependency edges
        for step in steps:
            for dependency in step.depends_on:
                if dependency in [s.step_id for s in steps]:
                    graph.add_edge(dependency, step.step_id)
        
        return graph
    
    def _identify_parallel_groups(self, graph: nx.DiGraph) -> List[Set[str]]:
        """Identify groups of steps that can run in parallel."""
        
        # Use topological sorting to identify levels
        try:
            # Get topological generations (levels)
            generations = list(nx.topological_generations(graph))
            return [set(generation) for generation in generations]
        except nx.NetworkXError:
            # Graph has cycles, return individual steps
            return [{node} for node in graph.nodes()]
    
    def _optimize_resource_usage(self, steps: List[ExecutionStep]) -> List[ExecutionStep]:
        """Optimize steps for resource usage."""
        
        optimized_steps = []
        
        for step in steps:
            # Add resource hints to step metadata
            optimized_step = ExecutionStep(
                step_id=step.step_id,
                name=step.name,
                description=step.description,
                step_type=step.step_type,
                action=step.action,
                tool=step.tool,
                parameters=step.parameters,
                inputs=step.inputs,
                outputs=step.outputs,
                depends_on=step.depends_on,
                conditions=step.conditions,
                retry_policy=step.retry_policy,
                timeout=step.timeout,
                metadata={
                    **step.metadata,
                    "resource_optimized": True,
                    "estimated_cpu": self._estimate_cpu_usage(step),
                    "estimated_memory": self._estimate_memory_usage(step)
                },
                tags=step.tags
            )
            optimized_steps.append(optimized_step)
        
        return optimized_steps
    
    def _optimize_step_caching(self, steps: List[ExecutionStep]) -> List[ExecutionStep]:
        """Optimize steps for caching."""
        
        optimized_steps = []
        
        for step in steps:
            # Add caching hints for idempotent operations
            cache_key = None
            if self._is_cacheable_step(step):
                cache_key = self._generate_cache_key(step)
            
            optimized_step = ExecutionStep(
                step_id=step.step_id,
                name=step.name,
                description=step.description,
                step_type=step.step_type,
                action=step.action,
                tool=step.tool,
                parameters=step.parameters,
                inputs=step.inputs,
                outputs=step.outputs,
                depends_on=step.depends_on,
                conditions=step.conditions,
                retry_policy=step.retry_policy,
                timeout=step.timeout,
                metadata={
                    **step.metadata,
                    "cache_optimized": True,
                    "cache_key": cache_key,
                    "cacheable": cache_key is not None
                },
                tags=step.tags
            )
            optimized_steps.append(optimized_step)
        
        return optimized_steps
    
    def _estimate_cpu_usage(self, step: ExecutionStep) -> str:
        """Estimate CPU usage for a step."""
        
        # Simple heuristics based on step type and tool
        if step.tool in ["database", "sql"]:
            return "50m"
        elif step.tool in ["http", "api"]:
            return "100m"
        elif step.tool in ["compute", "transform"]:
            return "200m"
        else:
            return "100m"  # Default
    
    def _estimate_memory_usage(self, step: ExecutionStep) -> str:
        """Estimate memory usage for a step."""
        
        # Simple heuristics based on step type and tool
        if step.tool in ["database", "sql"]:
            return "128Mi"
        elif step.tool in ["http", "api"]:
            return "64Mi"
        elif step.tool in ["compute", "transform"]:
            return "256Mi"
        else:
            return "128Mi"  # Default
    
    def _is_cacheable_step(self, step: ExecutionStep) -> bool:
        """Check if a step is cacheable (idempotent)."""
        
        # Steps that are typically cacheable
        cacheable_actions = ["read", "get", "fetch", "query", "validate", "transform"]
        
        if step.action and any(action in step.action.lower() for action in cacheable_actions):
            return True
        
        # Check step metadata for caching hints
        if step.metadata.get("idempotent", False):
            return True
        
        return False
    
    def _generate_cache_key(self, step: ExecutionStep) -> str:
        """Generate a cache key for a step."""
        
        import hashlib
        import json
        
        # Create cache key from step signature
        cache_data = {
            "action": step.action,
            "tool": step.tool,
            "parameters": step.parameters,
            "inputs": step.inputs
        }
        
        cache_string = json.dumps(cache_data, sort_keys=True)
        return hashlib.md5(cache_string.encode()).hexdigest()[:16]
    
    async def _optimize_flow_basic(self, flow: ExecutionFlow, dependency_analysis: Optional[DependencyAnalysisResult] = None) -> ExecutionFlow:
        """Apply basic optimizations to a flow with optional dependency analysis."""
        
        optimized_steps = []
        
        # Remove duplicate steps
        seen_steps = set()
        for step in flow.steps:
            step_signature = self._get_step_signature(step)
            if step_signature not in seen_steps:
                optimized_steps.append(step)
                seen_steps.add(step_signature)
        
        # Merge consecutive steps with same tool where possible
        merged_steps = self._merge_consecutive_steps(optimized_steps)
        
        # Apply dependency analysis insights if available
        if dependency_analysis:
            merged_steps = await self._apply_dependency_insights_basic(merged_steps, dependency_analysis)
        
        return ExecutionFlow(
            flow_id=flow.flow_id,
            name=flow.name,
            description=flow.description,
            steps=merged_steps,
            parallel_execution=flow.parallel_execution,
            max_concurrency=flow.max_concurrency,
            on_failure=flow.on_failure,
            rollback_steps=flow.rollback_steps,
            metadata=flow.metadata
        )
    
    async def _optimize_flow_parallelization(self, flow: ExecutionFlow, dependency_analysis: Optional[DependencyAnalysisResult] = None) -> ExecutionFlow:
        """Optimize flow for parallel execution with dependency analysis."""
        
        # Build dependency graph
        dependency_graph = self._build_dependency_graph(flow.steps)
        
        # Use dependency analysis if available, otherwise fall back to local analysis
        if dependency_analysis and dependency_analysis.parallelization_opportunities:
            parallel_groups = [opp.parallel_steps for opp in dependency_analysis.parallelization_opportunities]
            max_concurrency = min(max(len(group) for group in parallel_groups), 10)
        else:
            # Identify steps that can run in parallel
            parallel_groups = self._identify_parallel_groups(dependency_graph)
            max_concurrency = min(len(parallel_groups), 10)
        
        # Update flow configuration for parallelization
        optimized_flow = ExecutionFlow(
            flow_id=flow.flow_id,
            name=flow.name,
            description=flow.description,
            steps=flow.steps,
            parallel_execution=len(parallel_groups) > 1,
            max_concurrency=max_concurrency,
            on_failure=flow.on_failure,
            rollback_steps=flow.rollback_steps,
            metadata={
                **flow.metadata,
                "parallel_groups": len(parallel_groups),
                "parallelization_optimized": True,
                "dependency_analysis_used": dependency_analysis is not None
            }
        )
        
        return optimized_flow
    
    async def _optimize_flow_advanced(self, flow: ExecutionFlow, dependency_analysis: Optional[DependencyAnalysisResult] = None) -> ExecutionFlow:
        """Apply advanced optimizations to a flow with dependency analysis."""
        
        # Start with parallelization optimization
        flow = await self._optimize_flow_parallelization(flow, dependency_analysis)
        
        # Apply resource-aware optimization
        optimized_steps = self._optimize_resource_usage(flow.steps)
        
        # Apply caching optimization
        cached_steps = self._optimize_step_caching(optimized_steps)
        
        # Apply critical path optimizations if analysis is available
        if dependency_analysis and dependency_analysis.critical_paths:
            cached_steps = await self._optimize_critical_paths(cached_steps, dependency_analysis.critical_paths)
        
        return ExecutionFlow(
            flow_id=flow.flow_id,
            name=flow.name,
            description=flow.description,
            steps=cached_steps,
            parallel_execution=flow.parallel_execution,
            max_concurrency=flow.max_concurrency,
            on_failure=flow.on_failure,
            rollback_steps=flow.rollback_steps,
            metadata={
                **flow.metadata,
                "advanced_optimization": True,
                "critical_path_optimized": dependency_analysis is not None and len(dependency_analysis.critical_paths) > 0
            }
        )
    
    async def _apply_dependency_insights_basic(self, steps: List[ExecutionStep], dependency_analysis: DependencyAnalysisResult) -> List[ExecutionStep]:
        """Apply basic dependency analysis insights to steps."""
        
        optimized_steps = []
        
        for step in steps:
            # Add dependency analysis metadata
            optimized_step = ExecutionStep(
                step_id=step.step_id,
                name=step.name,
                description=step.description,
                step_type=step.step_type,
                action=step.action,
                tool=step.tool,
                parameters=step.parameters,
                inputs=step.inputs,
                outputs=step.outputs,
                depends_on=step.depends_on,
                conditions=step.conditions,
                retry_policy=step.retry_policy,
                timeout=step.timeout,
                metadata={
                    **step.metadata,
                    "dependency_analysis_applied": True,
                    "estimated_duration": dependency_analysis.graph.nodes.get(step.step_id, {}).get('estimated_duration', 0),
                    "estimated_cost": dependency_analysis.graph.nodes.get(step.step_id, {}).get('estimated_cost', 0)
                },
                tags=step.tags
            )
            optimized_steps.append(optimized_step)
        
        return optimized_steps
    
    async def _apply_cost_optimizations(self, flows: List[ExecutionFlow], dependency_analysis: DependencyAnalysisResult) -> List[ExecutionFlow]:
        """Apply cost-based optimizations using dependency analysis."""
        
        optimized_flows = []
        
        for flow in flows:
            optimized_steps = []
            
            for step in flow.steps:
                # Get cost information from dependency analysis
                step_cost = dependency_analysis.graph.nodes.get(step.step_id, {}).get('estimated_cost', 0)
                
                # Apply cost optimizations
                optimized_step = step
                
                # If step is expensive, add retry policy to avoid re-execution
                if step_cost > 0.1 and not step.retry_policy:
                    optimized_step = ExecutionStep(
                        step_id=step.step_id,
                        name=step.name,
                        description=step.description,
                        step_type=step.step_type,
                        action=step.action,
                        tool=step.tool,
                        parameters=step.parameters,
                        inputs=step.inputs,
                        outputs=step.outputs,
                        depends_on=step.depends_on,
                        conditions=step.conditions,
                        retry_policy={"max_attempts": 3, "backoff": "exponential"},
                        timeout=step.timeout,
                        metadata={
                            **step.metadata,
                            "cost_optimized": True,
                            "estimated_cost": step_cost
                        },
                        tags=step.tags
                    )
                
                optimized_steps.append(optimized_step)
            
            optimized_flow = ExecutionFlow(
                flow_id=flow.flow_id,
                name=flow.name,
                description=flow.description,
                steps=optimized_steps,
                parallel_execution=flow.parallel_execution,
                max_concurrency=flow.max_concurrency,
                on_failure=flow.on_failure,
                rollback_steps=flow.rollback_steps,
                metadata={
                    **flow.metadata,
                    "cost_optimized": True
                }
            )
            
            optimized_flows.append(optimized_flow)
        
        return optimized_flows
    
    async def _apply_graph_optimizations(self, flows: List[ExecutionFlow], dependency_analysis: DependencyAnalysisResult) -> List[ExecutionFlow]:
        """Apply graph-based optimizations using dependency analysis."""
        
        optimized_flows = []
        
        for flow in flows:
            # Reorder steps based on critical path analysis
            if dependency_analysis.critical_paths:
                reordered_steps = await self._reorder_steps_by_critical_path(flow.steps, dependency_analysis.critical_paths)
            else:
                reordered_steps = flow.steps
            
            # Apply parallelization opportunities
            parallel_optimized_steps = await self._apply_parallelization_opportunities(
                reordered_steps, dependency_analysis.parallelization_opportunities
            )
            
            optimized_flow = ExecutionFlow(
                flow_id=flow.flow_id,
                name=flow.name,
                description=flow.description,
                steps=parallel_optimized_steps,
                parallel_execution=True,  # Enable parallel execution for graph-optimized flows
                max_concurrency=min(len(dependency_analysis.parallelization_opportunities), 20),
                on_failure=flow.on_failure,
                rollback_steps=flow.rollback_steps,
                metadata={
                    **flow.metadata,
                    "graph_optimized": True,
                    "critical_path_count": len(dependency_analysis.critical_paths),
                    "parallelization_opportunities": len(dependency_analysis.parallelization_opportunities)
                }
            )
            
            optimized_flows.append(optimized_flow)
        
        return optimized_flows
    
    async def _optimize_critical_paths(self, steps: List[ExecutionStep], critical_paths: List) -> List[ExecutionStep]:
        """Optimize steps based on critical path analysis."""
        
        # Identify bottleneck steps from critical paths
        bottleneck_steps = set()
        for path in critical_paths:
            bottleneck_steps.update(path.bottlenecks)
        
        optimized_steps = []
        
        for step in steps:
            if step.step_id in bottleneck_steps:
                # Optimize bottleneck steps
                optimized_step = ExecutionStep(
                    step_id=step.step_id,
                    name=step.name,
                    description=step.description,
                    step_type=step.step_type,
                    action=step.action,
                    tool=step.tool,
                    parameters=step.parameters,
                    inputs=step.inputs,
                    outputs=step.outputs,
                    depends_on=step.depends_on,
                    conditions=step.conditions,
                    retry_policy=step.retry_policy,
                    timeout=max(step.timeout or 0, 300) or 300,  # Increase timeout for bottlenecks
                    metadata={
                        **step.metadata,
                        "bottleneck_optimized": True,
                        "is_bottleneck": True
                    },
                    tags=step.tags + ["bottleneck"]
                )
                optimized_steps.append(optimized_step)
            else:
                optimized_steps.append(step)
        
        return optimized_steps
    
    async def _reorder_steps_by_critical_path(self, steps: List[ExecutionStep], critical_paths: List) -> List[ExecutionStep]:
        """Reorder steps to prioritize critical path execution."""
        
        if not critical_paths:
            return steps
        
        # Get the longest critical path
        longest_path = max(critical_paths, key=lambda p: p.total_duration)
        critical_step_ids = set(longest_path.steps)
        
        # Separate critical and non-critical steps
        critical_steps = [step for step in steps if step.step_id in critical_step_ids]
        non_critical_steps = [step for step in steps if step.step_id not in critical_step_ids]
        
        # Reorder: critical steps first, then non-critical
        return critical_steps + non_critical_steps
    
    async def _apply_parallelization_opportunities(self, steps: List[ExecutionStep], opportunities: List) -> List[ExecutionStep]:
        """Apply parallelization opportunities to steps."""
        
        optimized_steps = []
        
        # Create a mapping of steps that can be parallelized
        parallel_step_groups = {}
        for i, opportunity in enumerate(opportunities):
            if opportunity.estimated_speedup > 1.5 and not opportunity.constraints:
                for step_id in opportunity.parallel_steps:
                    parallel_step_groups[step_id] = f"parallel_group_{i}"
        
        for step in steps:
            if step.step_id in parallel_step_groups:
                # Mark step as parallelizable
                optimized_step = ExecutionStep(
                    step_id=step.step_id,
                    name=step.name,
                    description=step.description,
                    step_type=step.step_type,
                    action=step.action,
                    tool=step.tool,
                    parameters=step.parameters,
                    inputs=step.inputs,
                    outputs=step.outputs,
                    depends_on=step.depends_on,
                    conditions=step.conditions,
                    retry_policy=step.retry_policy,
                    timeout=step.timeout,
                    metadata={
                        **step.metadata,
                        "parallel_group": parallel_step_groups[step.step_id],
                        "parallelizable": True
                    },
                    tags=step.tags + ["parallelizable"]
                )
                optimized_steps.append(optimized_step)
            else:
                optimized_steps.append(step)
        
        return optimized_steps