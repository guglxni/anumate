"""Plan Compiler engine - transforms Capsules to ExecutablePlans."""

import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from pydantic import BaseModel

from .models import (
    CompilationRequest,
    CompilationResult,
    ExecutablePlan,
    ExecutionFlow,
    ExecutionStep,
    PlanMetadata,
    ResourceRequirement,
    SecurityContext,
)
from .dependency_resolver import DependencyResolver
from .optimizer import PlanOptimizer
from .validator import PlanValidator
from .cache_service import get_cache_service

logger = structlog.get_logger(__name__)


class CapsuleDefinition(BaseModel):
    """Simplified Capsule definition for compilation."""
    
    name: str
    version: str
    description: Optional[str] = None
    automation: Dict[str, Any]
    tools: List[str] = []
    policies: List[str] = []
    dependencies: List[str] = []
    metadata: Dict[str, Any] = {}


class PlanCompiler:
    """Main Plan Compiler engine."""
    
    def __init__(
        self,
        dependency_resolver: Optional[DependencyResolver] = None,
        optimizer: Optional[PlanOptimizer] = None,
        validator: Optional[PlanValidator] = None
    ):
        self.dependency_resolver = dependency_resolver or DependencyResolver()
        self.optimizer = optimizer or PlanOptimizer()
        self.validator = validator or PlanValidator()
        self.cache_service = get_cache_service()
        self.compiler_version = "1.0.0"
    
    async def compile_capsule(
        self,
        capsule: CapsuleDefinition,
        tenant_id: UUID,
        compiled_by: UUID,
        request: Optional[CompilationRequest] = None
    ) -> CompilationResult:
        """Compile a Capsule to an ExecutablePlan."""
        
        start_time = time.time()
        
        try:
            logger.info(
                "Starting capsule compilation",
                capsule_name=capsule.name,
                capsule_version=capsule.version,
                tenant_id=str(tenant_id)
            )
            
            # Check cache first if caching is enabled
            if request and request.cache_result:
                # Create a cache key based on capsule content and compilation settings
                cache_key = self._generate_compilation_cache_key(capsule, request)
                cached_plan = await self.cache_service.get(cache_key, tenant_id)
                
                if cached_plan:
                    logger.info(
                        "Using cached compilation result",
                        capsule_name=capsule.name,
                        plan_hash=cached_plan.plan_hash,
                        cache_key=cache_key
                    )
                    
                    return CompilationResult(
                        success=True,
                        plan=cached_plan,
                        compilation_time=0.0,  # Cached result
                        resolved_dependencies=cached_plan.metadata.resolved_dependencies
                    )
            
            # Step 1: Resolve dependencies
            dependency_result = await self._resolve_dependencies(capsule, tenant_id)
            if not dependency_result.success and request and request.validate_dependencies:
                return CompilationResult(
                    success=False,
                    errors=[f"Dependency resolution failed: {', '.join(dependency_result.unresolved_dependencies)}"],
                    compilation_time=time.time() - start_time,
                    unresolved_dependencies=dependency_result.unresolved_dependencies,
                    dependency_conflicts=dependency_result.conflicts
                )
            
            # Step 2: Transform automation to execution flows
            flows = await self._transform_automation_to_flows(capsule.automation)
            
            # Step 3: Extract security context
            security_context = self._extract_security_context(capsule)
            
            # Step 4: Extract resource requirements
            resource_requirements = self._extract_resource_requirements(capsule)
            
            # Step 5: Create plan metadata
            metadata = PlanMetadata(
                source_capsule_id=UUID('00000000-0000-0000-0000-000000000000'),  # Would be real ID in production
                source_capsule_name=capsule.name,
                source_capsule_version=capsule.version,
                source_capsule_checksum="placeholder_checksum",  # Would be real checksum
                compiled_by=compiled_by,
                compiler_version=self.compiler_version,
                resolved_dependencies=dependency_result.resolved,
                optimization_level=request.optimization_level if request else "standard"
            )
            
            # Step 6: Create executable plan
            plan = ExecutablePlan.create(
                tenant_id=tenant_id,
                name=capsule.name,
                version=capsule.version,
                description=capsule.description,
                flows=flows,
                main_flow=flows[0].flow_id if flows else "main",
                metadata=metadata,
                resource_requirements=resource_requirements,
                security_context=security_context,
                configuration=request.configuration if request else {},
                variables=request.variables if request else {}
            )
            
            # Step 7: Optimize plan
            if request and request.optimization_level != "none":
                plan = await self.optimizer.optimize_plan(plan, request.optimization_level)
            
            # Step 8: Validate plan
            validation_result = await self.validator.validate_plan(plan)
            
            compilation_time = time.time() - start_time
            
            # Cache the compiled plan if successful and caching is enabled
            if validation_result.valid and plan and request and request.cache_result:
                cache_key = self._generate_compilation_cache_key(capsule, request)
                await self.cache_service.put(
                    plan,
                    tags=[
                        f"capsule:{capsule.name}",
                        f"version:{capsule.version}",
                        f"optimization:{request.optimization_level}",
                        "compiled"
                    ]
                )
                
                logger.info(
                    "Compiled plan cached successfully",
                    capsule_name=capsule.name,
                    plan_hash=plan.plan_hash,
                    cache_key=cache_key
                )
            
            logger.info(
                "Capsule compilation completed",
                capsule_name=capsule.name,
                plan_hash=plan.plan_hash,
                compilation_time=compilation_time,
                success=validation_result.valid
            )
            
            return CompilationResult(
                success=validation_result.valid,
                plan=plan if validation_result.valid else None,
                errors=validation_result.errors,
                warnings=validation_result.warnings,
                compilation_time=compilation_time,
                resolved_dependencies=dependency_result.resolved,
                unresolved_dependencies=dependency_result.unresolved_dependencies,
                dependency_conflicts=dependency_result.conflicts
            )
            
        except Exception as e:
            compilation_time = time.time() - start_time
            logger.error(
                "Capsule compilation failed",
                capsule_name=capsule.name,
                error=str(e),
                compilation_time=compilation_time
            )
            
            return CompilationResult(
                success=False,
                errors=[f"Compilation error: {str(e)}"],
                compilation_time=compilation_time
            )
    
    async def _resolve_dependencies(self, capsule: CapsuleDefinition, tenant_id: UUID) -> Any:
        """Resolve Capsule dependencies."""
        if not capsule.dependencies:
            return type('DependencyResult', (), {
                'success': True,
                'resolved': [],
                'unresolved_dependencies': [],
                'conflicts': []
            })()
        
        return await self.dependency_resolver.resolve_dependencies(
            capsule.dependencies,
            tenant_id
        )
    
    async def _transform_automation_to_flows(self, automation: Dict[str, Any]) -> List[ExecutionFlow]:
        """Transform Capsule automation definition to execution flows."""
        
        flows = []
        
        # Handle different automation formats
        if "workflow" in automation:
            # Workflow-based automation
            workflow = automation["workflow"]
            flow = await self._transform_workflow_to_flow(workflow)
            flows.append(flow)
            
        elif "steps" in automation:
            # Step-based automation
            steps = automation["steps"]
            flow = await self._transform_steps_to_flow(steps)
            flows.append(flow)
            
        elif "pipelines" in automation:
            # Pipeline-based automation
            for pipeline_name, pipeline_def in automation["pipelines"].items():
                flow = await self._transform_pipeline_to_flow(pipeline_name, pipeline_def)
                flows.append(flow)
        
        else:
            # Default: create a simple flow
            flow = ExecutionFlow(
                flow_id="main",
                name="Main Flow",
                description="Default execution flow",
                steps=[
                    ExecutionStep(
                        step_id="default_step",
                        name="Default Step",
                        step_type="action",
                        action="execute",
                        parameters=automation
                    )
                ]
            )
            flows.append(flow)
        
        return flows
    
    async def _transform_workflow_to_flow(self, workflow: Dict[str, Any]) -> ExecutionFlow:
        """Transform workflow definition to execution flow."""
        
        steps = []
        
        # Extract workflow steps
        workflow_steps = workflow.get("steps", [])
        
        for i, step_def in enumerate(workflow_steps):
            step = ExecutionStep(
                step_id=step_def.get("id", f"step_{i}"),
                name=step_def.get("name", f"Step {i+1}"),
                description=step_def.get("description"),
                step_type=step_def.get("type", "action"),
                action=step_def.get("action"),
                tool=step_def.get("tool"),
                parameters=step_def.get("parameters", {}),
                inputs=step_def.get("inputs", {}),
                outputs=step_def.get("outputs", {}),
                depends_on=step_def.get("depends_on", []),
                conditions=step_def.get("conditions", []),
                retry_policy=step_def.get("retry"),
                timeout=step_def.get("timeout"),
                metadata=step_def.get("metadata", {}),
                tags=step_def.get("tags", [])
            )
            steps.append(step)
        
        return ExecutionFlow(
            flow_id=workflow.get("id", "main"),
            name=workflow.get("name", "Main Workflow"),
            description=workflow.get("description"),
            steps=steps,
            parallel_execution=workflow.get("parallel", False),
            max_concurrency=workflow.get("max_concurrency"),
            on_failure=workflow.get("on_failure", "stop"),
            rollback_steps=workflow.get("rollback_steps", []),
            metadata=workflow.get("metadata", {})
        )
    
    async def _transform_steps_to_flow(self, steps_def: List[Dict[str, Any]]) -> ExecutionFlow:
        """Transform steps definition to execution flow."""
        
        steps = []
        
        for i, step_def in enumerate(steps_def):
            step = ExecutionStep(
                step_id=step_def.get("id", f"step_{i}"),
                name=step_def.get("name", f"Step {i+1}"),
                description=step_def.get("description"),
                step_type=step_def.get("type", "action"),
                action=step_def.get("action"),
                tool=step_def.get("tool"),
                parameters=step_def.get("parameters", {}),
                inputs=step_def.get("inputs", {}),
                outputs=step_def.get("outputs", {}),
                depends_on=step_def.get("depends_on", []),
                conditions=step_def.get("conditions", []),
                retry_policy=step_def.get("retry"),
                timeout=step_def.get("timeout"),
                metadata=step_def.get("metadata", {}),
                tags=step_def.get("tags", [])
            )
            steps.append(step)
        
        return ExecutionFlow(
            flow_id="main",
            name="Main Flow",
            description="Main execution flow",
            steps=steps
        )
    
    async def _transform_pipeline_to_flow(self, pipeline_name: str, pipeline_def: Dict[str, Any]) -> ExecutionFlow:
        """Transform pipeline definition to execution flow."""
        
        steps = []
        
        # Extract pipeline stages as steps
        stages = pipeline_def.get("stages", [])
        
        for i, stage_def in enumerate(stages):
            step = ExecutionStep(
                step_id=stage_def.get("id", f"{pipeline_name}_stage_{i}"),
                name=stage_def.get("name", f"Stage {i+1}"),
                description=stage_def.get("description"),
                step_type="action",
                action=stage_def.get("action"),
                tool=stage_def.get("tool"),
                parameters=stage_def.get("parameters", {}),
                inputs=stage_def.get("inputs", {}),
                outputs=stage_def.get("outputs", {}),
                depends_on=stage_def.get("depends_on", []),
                conditions=stage_def.get("conditions", []),
                retry_policy=stage_def.get("retry"),
                timeout=stage_def.get("timeout"),
                metadata=stage_def.get("metadata", {}),
                tags=stage_def.get("tags", [])
            )
            steps.append(step)
        
        return ExecutionFlow(
            flow_id=pipeline_name,
            name=pipeline_def.get("name", pipeline_name),
            description=pipeline_def.get("description"),
            steps=steps,
            parallel_execution=pipeline_def.get("parallel", False),
            max_concurrency=pipeline_def.get("max_concurrency"),
            on_failure=pipeline_def.get("on_failure", "stop"),
            rollback_steps=pipeline_def.get("rollback_steps", []),
            metadata=pipeline_def.get("metadata", {})
        )
    
    def _extract_security_context(self, capsule: CapsuleDefinition) -> SecurityContext:
        """Extract security context from Capsule."""
        
        return SecurityContext(
            allowed_tools=capsule.tools,
            required_capabilities=capsule.metadata.get("required_capabilities", []),
            policy_refs=capsule.policies,
            requires_approval=capsule.metadata.get("requires_approval", False),
            approval_rules=capsule.metadata.get("approval_rules", []),
            data_classification=capsule.metadata.get("data_classification"),
            pii_handling=capsule.metadata.get("pii_handling")
        )
    
    def _extract_resource_requirements(self, capsule: CapsuleDefinition) -> ResourceRequirement:
        """Extract resource requirements from Capsule."""
        
        resources = capsule.metadata.get("resources", {})
        
        return ResourceRequirement(
            cpu=resources.get("cpu"),
            memory=resources.get("memory"),
            storage=resources.get("storage"),
            network_access=resources.get("network_access", True),
            external_services=resources.get("external_services", []),
            runtime=resources.get("runtime"),
            capabilities=resources.get("capabilities", [])
        )
    
    def _generate_compilation_cache_key(self, capsule: CapsuleDefinition, request: CompilationRequest) -> str:
        """Generate a cache key for compilation results."""
        
        import hashlib
        import json
        
        # Create cache key from capsule content and compilation settings
        cache_data = {
            "capsule_name": capsule.name,
            "capsule_version": capsule.version,
            "capsule_automation": capsule.automation,
            "capsule_tools": sorted(capsule.tools),
            "capsule_policies": sorted(capsule.policies),
            "capsule_dependencies": sorted(capsule.dependencies),
            "optimization_level": request.optimization_level,
            "validate_dependencies": request.validate_dependencies,
            "variables": request.variables,
            "configuration": request.configuration,
            "compiler_version": self.compiler_version
        }
        
        cache_string = json.dumps(cache_data, sort_keys=True, default=str)
        return hashlib.sha256(cache_string.encode()).hexdigest()[:32]