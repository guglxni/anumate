"""Plan dependency graph analysis for optimization and cost estimation."""

import networkx as nx
from typing import Dict, List, Set, Tuple, Optional, Any
from dataclasses import dataclass
from enum import Enum
import structlog

from .models import ExecutablePlan, ExecutionFlow, ExecutionStep

logger = structlog.get_logger(__name__)


class DependencyType(Enum):
    """Types of dependencies between steps."""
    
    DATA_FLOW = "data_flow"
    CONTROL_FLOW = "control_flow"
    RESOURCE_DEPENDENCY = "resource_dependency"
    TEMPORAL_DEPENDENCY = "temporal_dependency"


@dataclass
class DependencyEdge:
    """Represents a dependency edge in the graph."""
    
    source_step: str
    target_step: str
    dependency_type: DependencyType
    weight: float = 1.0
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class CriticalPath:
    """Represents a critical path in the execution graph."""
    
    steps: List[str]
    total_duration: float
    total_cost: float
    bottlenecks: List[str]
    parallelizable_segments: List[List[str]]


@dataclass
class ParallelizationOpportunity:
    """Represents an opportunity for parallelization."""
    
    parallel_steps: List[str]
    estimated_speedup: float
    resource_requirements: Dict[str, Any]
    constraints: List[str]


@dataclass
class DependencyAnalysisResult:
    """Result of dependency graph analysis."""
    
    graph: nx.DiGraph
    critical_paths: List[CriticalPath]
    parallelization_opportunities: List[ParallelizationOpportunity]
    execution_levels: List[List[str]]
    total_estimated_duration: float
    total_estimated_cost: float
    complexity_metrics: Dict[str, float]
    optimization_recommendations: List[str]


class DependencyAnalyzer:
    """Analyzes plan dependencies for optimization and cost estimation."""
    
    def __init__(self):
        self.step_cost_estimators = {
            "action": self._estimate_action_step_cost,
            "condition": self._estimate_condition_step_cost,
            "loop": self._estimate_loop_step_cost,
            "parallel": self._estimate_parallel_step_cost,
            "transform": self._estimate_transform_step_cost
        }
        
        self.step_duration_estimators = {
            "action": self._estimate_action_step_duration,
            "condition": self._estimate_condition_step_duration,
            "loop": self._estimate_loop_step_duration,
            "parallel": self._estimate_parallel_step_duration,
            "transform": self._estimate_transform_step_duration
        }
    
    async def analyze_plan_dependencies(self, plan: ExecutablePlan) -> DependencyAnalysisResult:
        """Perform comprehensive dependency analysis on a plan."""
        
        logger.info(
            "Starting dependency analysis",
            plan_hash=plan.plan_hash,
            flows_count=len(plan.flows)
        )
        
        # Build comprehensive dependency graph
        graph = await self._build_dependency_graph(plan)
        
        # Find critical paths
        critical_paths = await self._find_critical_paths(graph)
        
        # Identify parallelization opportunities
        parallelization_opportunities = await self._identify_parallelization_opportunities(graph)
        
        # Calculate execution levels
        execution_levels = await self._calculate_execution_levels(graph)
        
        # Estimate total duration and cost
        total_duration, total_cost = await self._estimate_total_execution_metrics(graph, critical_paths)
        
        # Calculate complexity metrics
        complexity_metrics = await self._calculate_complexity_metrics(graph)
        
        # Generate optimization recommendations
        optimization_recommendations = await self._generate_optimization_recommendations(
            graph, critical_paths, parallelization_opportunities, complexity_metrics
        )
        
        result = DependencyAnalysisResult(
            graph=graph,
            critical_paths=critical_paths,
            parallelization_opportunities=parallelization_opportunities,
            execution_levels=execution_levels,
            total_estimated_duration=total_duration,
            total_estimated_cost=total_cost,
            complexity_metrics=complexity_metrics,
            optimization_recommendations=optimization_recommendations
        )
        
        logger.info(
            "Dependency analysis completed",
            plan_hash=plan.plan_hash,
            critical_paths_count=len(critical_paths),
            parallelization_opportunities_count=len(parallelization_opportunities),
            total_duration=total_duration,
            total_cost=total_cost
        )
        
        return result
    
    async def _build_dependency_graph(self, plan: ExecutablePlan) -> nx.DiGraph:
        """Build a comprehensive dependency graph from the plan."""
        
        graph = nx.DiGraph()
        
        # Process each flow
        for flow in plan.flows:
            await self._add_flow_to_graph(graph, flow)
        
        # Add inter-flow dependencies if multiple flows exist
        if len(plan.flows) > 1:
            await self._add_inter_flow_dependencies(graph, plan.flows)
        
        # Enrich graph with metadata
        await self._enrich_graph_metadata(graph, plan)
        
        return graph
    
    async def _add_flow_to_graph(self, graph: nx.DiGraph, flow: ExecutionFlow):
        """Add a flow's steps and dependencies to the graph."""
        
        # Add all steps as nodes
        for step in flow.steps:
            graph.add_node(
                step.step_id,
                step=step,
                flow_id=flow.flow_id,
                estimated_duration=await self._estimate_step_duration(step),
                estimated_cost=await self._estimate_step_cost(step),
                resource_requirements=self._extract_step_resources(step)
            )
        
        # Add explicit dependencies
        for step in flow.steps:
            for dependency in step.depends_on:
                if graph.has_node(dependency):
                    edge = DependencyEdge(
                        source_step=dependency,
                        target_step=step.step_id,
                        dependency_type=DependencyType.CONTROL_FLOW,
                        weight=1.0
                    )
                    graph.add_edge(
                        dependency,
                        step.step_id,
                        dependency_edge=edge,
                        weight=edge.weight
                    )
        
        # Add implicit data flow dependencies
        await self._add_data_flow_dependencies(graph, flow.steps)
        
        # Add resource dependencies
        await self._add_resource_dependencies(graph, flow.steps)
    
    async def _add_data_flow_dependencies(self, graph: nx.DiGraph, steps: List[ExecutionStep]):
        """Add data flow dependencies based on input/output relationships."""
        
        # Build output to step mapping
        output_producers = {}
        for step in steps:
            for output_key in step.outputs.keys():
                output_producers[output_key] = step.step_id
        
        # Add dependencies based on input requirements
        for step in steps:
            for input_key, input_source in step.inputs.items():
                if input_source in output_producers:
                    producer_step = output_producers[input_source]
                    if producer_step != step.step_id and not graph.has_edge(producer_step, step.step_id):
                        edge = DependencyEdge(
                            source_step=producer_step,
                            target_step=step.step_id,
                            dependency_type=DependencyType.DATA_FLOW,
                            weight=0.5,
                            metadata={"data_key": input_key}
                        )
                        graph.add_edge(
                            producer_step,
                            step.step_id,
                            dependency_edge=edge,
                            weight=edge.weight
                        )
    
    async def _add_resource_dependencies(self, graph: nx.DiGraph, steps: List[ExecutionStep]):
        """Add resource-based dependencies."""
        
        # Group steps by resource requirements
        resource_groups = {}
        for step in steps:
            tool = step.tool or "default"
            if tool not in resource_groups:
                resource_groups[tool] = []
            resource_groups[tool].append(step.step_id)
        
        # Add sequential dependencies for steps using exclusive resources
        exclusive_tools = ["database", "file_system", "network"]
        
        for tool, step_ids in resource_groups.items():
            if tool in exclusive_tools and len(step_ids) > 1:
                # Sort by step order (assuming step_id contains ordering info)
                sorted_steps = sorted(step_ids)
                
                for i in range(len(sorted_steps) - 1):
                    current_step = sorted_steps[i]
                    next_step = sorted_steps[i + 1]
                    
                    if not graph.has_edge(current_step, next_step):
                        edge = DependencyEdge(
                            source_step=current_step,
                            target_step=next_step,
                            dependency_type=DependencyType.RESOURCE_DEPENDENCY,
                            weight=0.3,
                            metadata={"resource": tool}
                        )
                        graph.add_edge(
                            current_step,
                            next_step,
                            dependency_edge=edge,
                            weight=edge.weight
                        )
    
    async def _add_inter_flow_dependencies(self, graph: nx.DiGraph, flows: List[ExecutionFlow]):
        """Add dependencies between different flows."""
        
        # For now, assume flows are independent unless explicitly connected
        # In a more sophisticated implementation, this would analyze cross-flow data dependencies
        pass
    
    async def _enrich_graph_metadata(self, graph: nx.DiGraph, plan: ExecutablePlan):
        """Enrich graph nodes and edges with additional metadata."""
        
        # Add plan-level metadata to graph
        graph.graph['plan_hash'] = plan.plan_hash
        graph.graph['tenant_id'] = str(plan.tenant_id)
        graph.graph['optimization_level'] = plan.metadata.optimization_level
        
        # Calculate node centrality metrics
        try:
            betweenness = nx.betweenness_centrality(graph)
            closeness = nx.closeness_centrality(graph)
            
            for node_id in graph.nodes():
                graph.nodes[node_id]['betweenness_centrality'] = betweenness.get(node_id, 0.0)
                graph.nodes[node_id]['closeness_centrality'] = closeness.get(node_id, 0.0)
        except:
            # Handle cases where centrality cannot be calculated
            pass
    
    async def _find_critical_paths(self, graph: nx.DiGraph) -> List[CriticalPath]:
        """Find critical paths in the execution graph."""
        
        critical_paths = []
        
        try:
            # Find all simple paths from sources to sinks
            sources = [n for n in graph.nodes() if graph.in_degree(n) == 0]
            sinks = [n for n in graph.nodes() if graph.out_degree(n) == 0]
            
            for source in sources:
                for sink in sinks:
                    try:
                        # Find longest path (critical path)
                        path = nx.dag_longest_path(graph, weight='estimated_duration')
                        
                        if path:
                            total_duration = sum(
                                graph.nodes[step]['estimated_duration'] for step in path
                            )
                            total_cost = sum(
                                graph.nodes[step]['estimated_cost'] for step in path
                            )
                            
                            # Identify bottlenecks (steps with high duration)
                            bottlenecks = [
                                step for step in path
                                if graph.nodes[step]['estimated_duration'] > total_duration * 0.2
                            ]
                            
                            # Identify parallelizable segments
                            parallelizable_segments = await self._find_parallelizable_segments(graph, path)
                            
                            critical_path = CriticalPath(
                                steps=path,
                                total_duration=total_duration,
                                total_cost=total_cost,
                                bottlenecks=bottlenecks,
                                parallelizable_segments=parallelizable_segments
                            )
                            
                            critical_paths.append(critical_path)
                    except:
                        # Handle cases where longest path cannot be found
                        continue
        except:
            # Fallback: create a simple critical path from topological sort
            try:
                topo_order = list(nx.topological_sort(graph))
                if topo_order:
                    total_duration = sum(
                        graph.nodes[step]['estimated_duration'] for step in topo_order
                    )
                    total_cost = sum(
                        graph.nodes[step]['estimated_cost'] for step in topo_order
                    )
                    
                    critical_path = CriticalPath(
                        steps=topo_order,
                        total_duration=total_duration,
                        total_cost=total_cost,
                        bottlenecks=[],
                        parallelizable_segments=[]
                    )
                    
                    critical_paths.append(critical_path)
            except:
                pass
        
        return critical_paths
    
    async def _find_parallelizable_segments(self, graph: nx.DiGraph, path: List[str]) -> List[List[str]]:
        """Find segments of a path that can be parallelized."""
        
        segments = []
        current_segment = []
        
        for i, step in enumerate(path):
            # Check if this step can run in parallel with previous steps
            can_parallelize = True
            
            if i > 0:
                # Check if there are direct dependencies
                for prev_step in current_segment:
                    if graph.has_edge(prev_step, step):
                        can_parallelize = False
                        break
            
            if can_parallelize and current_segment:
                current_segment.append(step)
            else:
                if current_segment and len(current_segment) > 1:
                    segments.append(current_segment)
                current_segment = [step]
        
        if current_segment and len(current_segment) > 1:
            segments.append(current_segment)
        
        return segments
    
    async def _identify_parallelization_opportunities(self, graph: nx.DiGraph) -> List[ParallelizationOpportunity]:
        """Identify opportunities for parallelization."""
        
        opportunities = []
        
        # Find independent subgraphs
        try:
            # Get topological generations (levels that can run in parallel)
            generations = list(nx.topological_generations(graph))
            
            for generation in generations:
                if len(generation) > 1:
                    # Calculate potential speedup
                    sequential_duration = sum(
                        graph.nodes[step]['estimated_duration'] for step in generation
                    )
                    parallel_duration = max(
                        graph.nodes[step]['estimated_duration'] for step in generation
                    )
                    
                    estimated_speedup = sequential_duration / parallel_duration if parallel_duration > 0 else 1.0
                    
                    # Aggregate resource requirements
                    resource_requirements = {}
                    constraints = []
                    
                    for step in generation:
                        step_resources = graph.nodes[step]['resource_requirements']
                        for resource, amount in step_resources.items():
                            resource_requirements[resource] = resource_requirements.get(resource, 0) + amount
                    
                    # Check for resource conflicts
                    exclusive_resources = set()
                    for step in generation:
                        step_obj = graph.nodes[step]['step']
                        if step_obj.tool in ["database", "file_system"]:
                            if step_obj.tool in exclusive_resources:
                                constraints.append(f"Resource conflict: {step_obj.tool}")
                            exclusive_resources.add(step_obj.tool)
                    
                    opportunity = ParallelizationOpportunity(
                        parallel_steps=list(generation),
                        estimated_speedup=estimated_speedup,
                        resource_requirements=resource_requirements,
                        constraints=constraints
                    )
                    
                    opportunities.append(opportunity)
        except:
            # Handle cases where topological generations cannot be calculated
            pass
        
        return opportunities
    
    async def _calculate_execution_levels(self, graph: nx.DiGraph) -> List[List[str]]:
        """Calculate execution levels (topological generations)."""
        
        try:
            return [list(generation) for generation in nx.topological_generations(graph)]
        except:
            # Fallback: return all nodes as a single level
            return [list(graph.nodes())]
    
    async def _estimate_total_execution_metrics(
        self,
        graph: nx.DiGraph,
        critical_paths: List[CriticalPath]
    ) -> Tuple[float, float]:
        """Estimate total execution duration and cost."""
        
        if critical_paths:
            # Use the longest critical path
            longest_path = max(critical_paths, key=lambda p: p.total_duration)
            return longest_path.total_duration, longest_path.total_cost
        else:
            # Fallback: sum all node durations and costs
            total_duration = sum(
                graph.nodes[node]['estimated_duration'] for node in graph.nodes()
            )
            total_cost = sum(
                graph.nodes[node]['estimated_cost'] for node in graph.nodes()
            )
            return total_duration, total_cost
    
    async def _calculate_complexity_metrics(self, graph: nx.DiGraph) -> Dict[str, float]:
        """Calculate complexity metrics for the graph."""
        
        metrics = {}
        
        try:
            # Basic graph metrics
            metrics['node_count'] = graph.number_of_nodes()
            metrics['edge_count'] = graph.number_of_edges()
            metrics['density'] = nx.density(graph)
            
            # Connectivity metrics
            if graph.number_of_nodes() > 0:
                metrics['average_degree'] = sum(dict(graph.degree()).values()) / graph.number_of_nodes()
            else:
                metrics['average_degree'] = 0.0
            
            # Complexity indicators
            metrics['max_depth'] = len(nx.dag_longest_path(graph)) if nx.is_directed_acyclic_graph(graph) else 0
            metrics['width'] = max(len(generation) for generation in nx.topological_generations(graph)) if nx.is_directed_acyclic_graph(graph) else 0
            
            # Parallelization potential
            total_nodes = graph.number_of_nodes()
            if total_nodes > 0:
                parallel_nodes = sum(
                    len(generation) for generation in nx.topological_generations(graph)
                    if len(generation) > 1
                )
                metrics['parallelization_ratio'] = parallel_nodes / total_nodes
            else:
                metrics['parallelization_ratio'] = 0.0
            
        except Exception as e:
            logger.warning("Failed to calculate some complexity metrics", error=str(e))
            # Provide default values
            metrics.update({
                'node_count': graph.number_of_nodes(),
                'edge_count': graph.number_of_edges(),
                'density': 0.0,
                'average_degree': 0.0,
                'max_depth': 0,
                'width': 0,
                'parallelization_ratio': 0.0
            })
        
        return metrics
    
    async def _generate_optimization_recommendations(
        self,
        graph: nx.DiGraph,
        critical_paths: List[CriticalPath],
        parallelization_opportunities: List[ParallelizationOpportunity],
        complexity_metrics: Dict[str, float]
    ) -> List[str]:
        """Generate optimization recommendations based on analysis."""
        
        recommendations = []
        
        # Analyze critical paths
        if critical_paths:
            longest_path = max(critical_paths, key=lambda p: p.total_duration)
            
            if longest_path.bottlenecks:
                recommendations.append(
                    f"Optimize bottleneck steps: {', '.join(longest_path.bottlenecks)}"
                )
            
            if longest_path.parallelizable_segments:
                recommendations.append(
                    f"Consider parallelizing {len(longest_path.parallelizable_segments)} segments"
                )
        
        # Analyze parallelization opportunities
        high_speedup_opportunities = [
            opp for opp in parallelization_opportunities
            if opp.estimated_speedup > 2.0 and not opp.constraints
        ]
        
        if high_speedup_opportunities:
            recommendations.append(
                f"Enable parallel execution for {len(high_speedup_opportunities)} step groups "
                f"(potential {max(opp.estimated_speedup for opp in high_speedup_opportunities):.1f}x speedup)"
            )
        
        # Analyze complexity
        if complexity_metrics.get('parallelization_ratio', 0) < 0.3:
            recommendations.append("Consider restructuring plan to increase parallelization opportunities")
        
        if complexity_metrics.get('max_depth', 0) > 20:
            recommendations.append("Plan has deep dependency chain - consider breaking into smaller plans")
        
        if complexity_metrics.get('density', 0) > 0.7:
            recommendations.append("High dependency density detected - review if all dependencies are necessary")
        
        # Resource optimization
        resource_conflicts = []
        for opp in parallelization_opportunities:
            resource_conflicts.extend(opp.constraints)
        
        if resource_conflicts:
            recommendations.append("Resolve resource conflicts to enable better parallelization")
        
        return recommendations
    
    async def _estimate_step_duration(self, step: ExecutionStep) -> float:
        """Estimate execution duration for a step."""
        
        estimator = self.step_duration_estimators.get(step.step_type, self._estimate_default_step_duration)
        return await estimator(step)
    
    async def _estimate_step_cost(self, step: ExecutionStep) -> float:
        """Estimate execution cost for a step."""
        
        estimator = self.step_cost_estimators.get(step.step_type, self._estimate_default_step_cost)
        return await estimator(step)
    
    def _extract_step_resources(self, step: ExecutionStep) -> Dict[str, float]:
        """Extract resource requirements from a step."""
        
        resources = {
            'cpu': 1.0,  # Default CPU units
            'memory': 128.0,  # Default memory in MB
            'network': 0.0,
            'storage': 0.0
        }
        
        # Adjust based on step type and tool
        if step.tool == "database":
            resources['cpu'] = 0.5
            resources['memory'] = 256.0
            resources['network'] = 10.0
        elif step.tool == "http":
            resources['cpu'] = 0.3
            resources['memory'] = 64.0
            resources['network'] = 50.0
        elif step.tool == "compute":
            resources['cpu'] = 2.0
            resources['memory'] = 512.0
        
        return resources
    
    # Duration estimation methods
    async def _estimate_action_step_duration(self, step: ExecutionStep) -> float:
        """Estimate duration for action steps."""
        base_duration = 5.0  # 5 seconds base
        
        if step.tool == "database":
            return base_duration * 0.5
        elif step.tool == "http":
            return base_duration * 2.0
        elif step.tool == "compute":
            return base_duration * 3.0
        
        return base_duration
    
    async def _estimate_condition_step_duration(self, step: ExecutionStep) -> float:
        """Estimate duration for condition steps."""
        return 1.0  # Conditions are typically fast
    
    async def _estimate_loop_step_duration(self, step: ExecutionStep) -> float:
        """Estimate duration for loop steps."""
        iterations = step.parameters.get('iterations', 10)
        inner_duration = 5.0  # Estimated inner duration
        return iterations * inner_duration
    
    async def _estimate_parallel_step_duration(self, step: ExecutionStep) -> float:
        """Estimate duration for parallel steps."""
        return 10.0  # Parallel coordination overhead
    
    async def _estimate_transform_step_duration(self, step: ExecutionStep) -> float:
        """Estimate duration for transform steps."""
        return 3.0  # Transform operations are typically fast
    
    async def _estimate_default_step_duration(self, step: ExecutionStep) -> float:
        """Default duration estimation."""
        return 5.0
    
    # Cost estimation methods
    async def _estimate_action_step_cost(self, step: ExecutionStep) -> float:
        """Estimate cost for action steps."""
        base_cost = 0.01  # $0.01 base cost
        
        if step.tool == "database":
            return base_cost * 2.0
        elif step.tool == "http":
            return base_cost * 1.5
        elif step.tool == "compute":
            return base_cost * 5.0
        
        return base_cost
    
    async def _estimate_condition_step_cost(self, step: ExecutionStep) -> float:
        """Estimate cost for condition steps."""
        return 0.001  # Very low cost
    
    async def _estimate_loop_step_cost(self, step: ExecutionStep) -> float:
        """Estimate cost for loop steps."""
        iterations = step.parameters.get('iterations', 10)
        inner_cost = 0.01
        return iterations * inner_cost
    
    async def _estimate_parallel_step_cost(self, step: ExecutionStep) -> float:
        """Estimate cost for parallel steps."""
        return 0.02  # Parallel coordination cost
    
    async def _estimate_transform_step_cost(self, step: ExecutionStep) -> float:
        """Estimate cost for transform steps."""
        return 0.005  # Low cost for transforms
    
    async def _estimate_default_step_cost(self, step: ExecutionStep) -> float:
        """Default cost estimation."""
        return 0.01