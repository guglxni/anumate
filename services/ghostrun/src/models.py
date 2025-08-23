"""GhostRun service data models."""

import sys
import os
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

# Import ExecutablePlan from plan-compiler service
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'plan-compiler', 'src'))
from models import ExecutablePlan, ExecutionStep, ExecutionFlow, SecurityContext, PlanMetadata


class SimulationStatus(str, Enum):
    """Simulation status enumeration."""
    PENDING = "pending"
    RUNNING = "running" 
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RiskLevel(str, Enum):
    """Risk level enumeration."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class MockConnectorResponse(BaseModel):
    """Mock response from a connector during simulation."""
    
    connector_name: str = Field(..., description="Name of the connector")
    tool_name: str = Field(..., description="Tool being called")
    action: str = Field(..., description="Action being performed")
    
    # Mock response data
    success: bool = Field(..., description="Whether the action would succeed")
    response_data: Dict[str, Any] = Field(default_factory=dict, description="Mock response data")
    response_time_ms: int = Field(..., description="Simulated response time in milliseconds")
    
    # Simulation metadata
    simulated: bool = Field(default=True, description="Indicates this is a simulated response")
    simulation_notes: List[str] = Field(default_factory=list, description="Simulation notes")


class StepSimulationResult(BaseModel):
    """Result of simulating a single execution step."""
    
    step_id: str = Field(..., description="Step identifier")
    step_name: str = Field(..., description="Step name")
    
    # Execution simulation
    would_execute: bool = Field(..., description="Whether step would execute")
    execution_time_ms: int = Field(..., description="Estimated execution time")
    
    # Mock responses
    connector_responses: List[MockConnectorResponse] = Field(
        default_factory=list, 
        description="Mock connector responses"
    )
    
    # Validation results
    validation_passed: bool = Field(..., description="Whether step validation passed")
    validation_issues: List[str] = Field(default_factory=list, description="Validation issues")
    
    # Risk assessment
    risk_level: RiskLevel = Field(default=RiskLevel.LOW, description="Risk level")
    risk_factors: List[str] = Field(default_factory=list, description="Identified risk factors")
    
    # Dependencies
    dependency_issues: List[str] = Field(default_factory=list, description="Dependency issues")
    
    # Outputs
    simulated_outputs: Dict[str, Any] = Field(
        default_factory=dict, 
        description="Simulated step outputs"
    )


class FlowSimulationResult(BaseModel):
    """Result of simulating an execution flow."""
    
    flow_id: str = Field(..., description="Flow identifier")
    flow_name: str = Field(..., description="Flow name")
    
    # Overall flow results
    would_complete: bool = Field(..., description="Whether flow would complete successfully")
    total_execution_time_ms: int = Field(..., description="Total estimated execution time")
    
    # Step results
    step_results: List[StepSimulationResult] = Field(
        default_factory=list,
        description="Individual step simulation results"
    )
    
    # Flow-level issues
    flow_issues: List[str] = Field(default_factory=list, description="Flow-level issues")
    
    # Risk assessment
    overall_risk_level: RiskLevel = Field(default=RiskLevel.LOW, description="Overall risk level")
    critical_path_steps: List[str] = Field(
        default_factory=list,
        description="Steps on the critical path"
    )


class PreflightRecommendation(BaseModel):
    """Recommendation from preflight analysis."""
    
    type: str = Field(..., description="Recommendation type")
    severity: RiskLevel = Field(..., description="Recommendation severity")
    title: str = Field(..., description="Recommendation title")
    description: str = Field(..., description="Detailed description")
    
    # Actionable information
    suggested_actions: List[str] = Field(
        default_factory=list,
        description="Suggested actions to address the issue"
    )
    
    # Context
    affected_steps: List[str] = Field(
        default_factory=list,
        description="Steps affected by this recommendation"
    )
    
    # References
    documentation_links: List[str] = Field(
        default_factory=list,
        description="Links to relevant documentation"
    )


class PreflightReport(BaseModel):
    """Comprehensive preflight validation report."""
    
    # Report identification
    report_id: UUID = Field(default_factory=uuid4, description="Unique report ID")
    run_id: UUID = Field(..., description="GhostRun simulation ID")
    plan_hash: str = Field(..., description="ExecutablePlan hash")
    
    # Report metadata
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Report generation timestamp"
    )
    simulation_duration_ms: int = Field(..., description="Total simulation duration")
    
    # Overall assessment
    overall_status: str = Field(..., description="Overall preflight status")
    overall_risk_level: RiskLevel = Field(..., description="Overall risk assessment")
    execution_feasible: bool = Field(..., description="Whether execution is feasible")
    
    # Simulation results
    flow_results: List[FlowSimulationResult] = Field(
        default_factory=list,
        description="Flow simulation results"
    )
    
    # Analysis results
    total_estimated_duration_ms: int = Field(..., description="Total estimated execution time")
    estimated_cost: Optional[float] = Field(None, description="Estimated execution cost")
    
    # Issues and recommendations
    critical_issues: List[str] = Field(default_factory=list, description="Critical issues found")
    warnings: List[str] = Field(default_factory=list, description="Warnings")
    recommendations: List[PreflightRecommendation] = Field(
        default_factory=list,
        description="Recommendations for improvement"
    )
    
    # Resource analysis
    resource_requirements: Dict[str, Any] = Field(
        default_factory=dict,
        description="Analyzed resource requirements"
    )
    
    # Security analysis
    security_issues: List[str] = Field(default_factory=list, description="Security issues")
    policy_violations: List[str] = Field(default_factory=list, description="Policy violations")
    
    # Performance analysis
    performance_bottlenecks: List[str] = Field(
        default_factory=list,
        description="Identified performance bottlenecks"
    )
    
    # Summary statistics
    total_steps: int = Field(..., description="Total number of steps")
    steps_with_issues: int = Field(..., description="Number of steps with issues")
    high_risk_steps: int = Field(..., description="Number of high-risk steps")


class GhostRunRequest(BaseModel):
    """Request to start a GhostRun simulation."""
    
    plan_hash: str = Field(..., description="ExecutablePlan hash to simulate")
    
    # Simulation configuration
    simulation_mode: str = Field(default="full", description="Simulation mode: full, fast, security")
    include_performance_analysis: bool = Field(
        default=True,
        description="Whether to include performance analysis"
    )
    include_cost_estimation: bool = Field(
        default=True,
        description="Whether to include cost estimation"
    )
    
    # Mock configuration
    mock_external_calls: bool = Field(
        default=True,
        description="Whether to mock external API calls"
    )
    connector_overrides: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Override settings for specific connectors"
    )
    
    # Validation options
    strict_validation: bool = Field(
        default=False,
        description="Whether to use strict validation rules"
    )
    
    # Context
    execution_context: Dict[str, Any] = Field(
        default_factory=dict,
        description="Execution context for simulation"
    )


class GhostRunStatus(BaseModel):
    """Status of a GhostRun simulation."""
    
    # Run identification
    run_id: UUID = Field(..., description="Unique run ID")
    tenant_id: UUID = Field(..., description="Tenant ID")
    plan_hash: str = Field(..., description="ExecutablePlan hash")
    
    # Status information
    status: SimulationStatus = Field(..., description="Current simulation status")
    progress: float = Field(default=0.0, description="Completion progress (0.0 to 1.0)")
    current_step: Optional[str] = Field(None, description="Currently simulating step")
    
    # Timing
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Run creation time"
    )
    started_at: Optional[datetime] = Field(None, description="Simulation start time")
    completed_at: Optional[datetime] = Field(None, description="Simulation completion time")
    
    # Results
    report: Optional[PreflightReport] = Field(None, description="Preflight report (when completed)")
    error_message: Optional[str] = Field(None, description="Error message (if failed)")
    
    # Performance metrics
    simulation_metrics: Dict[str, Any] = Field(
        default_factory=dict,
        description="Simulation performance metrics"
    )


class SimulationMetrics(BaseModel):
    """Performance metrics for simulation execution."""
    
    # Timing metrics
    total_duration_ms: int = Field(..., description="Total simulation duration")
    plan_loading_time_ms: int = Field(..., description="Time to load ExecutablePlan")
    validation_time_ms: int = Field(..., description="Time for validation")
    simulation_time_ms: int = Field(..., description="Time for actual simulation")
    report_generation_time_ms: int = Field(..., description="Time to generate report")
    
    # Resource metrics
    memory_usage_mb: float = Field(..., description="Peak memory usage in MB")
    cpu_usage_percent: float = Field(..., description="Average CPU usage percentage")
    
    # Simulation statistics
    steps_simulated: int = Field(..., description="Number of steps simulated")
    connectors_mocked: int = Field(..., description="Number of connectors mocked")
    api_calls_simulated: int = Field(..., description="Number of API calls simulated")
    
    # Performance indicators
    simulation_efficiency: float = Field(
        ...,
        description="Simulation efficiency score (0.0 to 1.0)"
    )
    
    @classmethod
    def create_from_timing(
        cls,
        start_time: float,
        plan_load_time: float,
        validation_time: float,
        simulation_time: float,
        report_time: float,
        steps_count: int,
        connectors_count: int,
        api_calls_count: int
    ) -> "SimulationMetrics":
        """Create metrics from timing measurements."""
        end_time = time.time()
        total_duration = int((end_time - start_time) * 1000)
        
        # Calculate efficiency based on steps per second
        efficiency = min(1.0, steps_count / max(1, total_duration / 1000) / 10)
        
        return cls(
            total_duration_ms=total_duration,
            plan_loading_time_ms=int(plan_load_time * 1000),
            validation_time_ms=int(validation_time * 1000),
            simulation_time_ms=int(simulation_time * 1000),
            report_generation_time_ms=int(report_time * 1000),
            memory_usage_mb=0.0,  # Would be measured in real implementation
            cpu_usage_percent=0.0,  # Would be measured in real implementation
            steps_simulated=steps_count,
            connectors_mocked=connectors_count,
            api_calls_simulated=api_calls_count,
            simulation_efficiency=efficiency
        )