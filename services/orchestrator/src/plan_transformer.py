"""Transform ExecutablePlans to Portia format."""

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

# Tracing removed for development compatibility
def trace(name):
    """Mock trace decorator for development."""
    def decorator(func):
        return func
    return decorator

from .models import PortiaPlan, RetryPolicy

logger = logging.getLogger(__name__)


class PlanTransformationError(Exception):
    """Plan transformation error."""
    pass


class PlanTransformer:
    """Transforms ExecutablePlans to Portia Plans."""
    
    @trace("plan_transformer.transform_executable_plan")
    def transform_executable_plan(
        self,
        executable_plan: Dict[str, Any],
        tenant_id: UUID,
        triggered_by: str,
    ) -> PortiaPlan:
        """Transform ExecutablePlan to Portia Plan format.
        
        Args:
            executable_plan: ExecutablePlan data
            tenant_id: Tenant ID
            triggered_by: User who triggered execution
            
        Returns:
            Portia Plan
            
        Raises:
            PlanTransformationError: If transformation fails
        """
        try:
            # Extract basic plan information
            plan_id = f"anumate-{executable_plan['plan_hash'][:8]}"
            name = executable_plan.get('name', 'Unnamed Plan')
            description = executable_plan.get('description')
            
            # Transform execution flows to Portia steps
            steps = self._transform_flows_to_steps(
                executable_plan.get('flows', []),
                executable_plan.get('main_flow')
            )
            
            # Extract variables and configuration
            variables = {
                **executable_plan.get('variables', {}),
                **executable_plan.get('configuration', {}),
                'tenant_id': str(tenant_id),
                'plan_hash': executable_plan['plan_hash'],
            }
            
            # Extract timeout and retry policy
            timeout = self._extract_timeout(executable_plan)
            retry_policy = self._extract_retry_policy(executable_plan)
            
            return PortiaPlan(
                plan_id=plan_id,
                name=name,
                description=description,
                steps=steps,
                variables=variables,
                created_by=triggered_by,
                timeout=timeout,
                retry_policy=retry_policy,
            )
            
        except Exception as e:
            error_msg = f"Failed to transform ExecutablePlan: {e}"
            logger.error(error_msg)
            raise PlanTransformationError(error_msg) from e  
  
    def _transform_flows_to_steps(
        self,
        flows: List[Dict[str, Any]],
        main_flow_id: Optional[str],
    ) -> List[Dict[str, Any]]:
        """Transform execution flows to Portia steps.
        
        Args:
            flows: List of execution flows
            main_flow_id: Main flow identifier
            
        Returns:
            List of Portia steps
        """
        if not flows:
            return []
        
        # Find main flow or use first flow
        main_flow = None
        for flow in flows:
            if flow.get('flow_id') == main_flow_id:
                main_flow = flow
                break
        
        if not main_flow:
            main_flow = flows[0]
        
        # Transform steps from main flow
        portia_steps = []
        for step in main_flow.get('steps', []):
            portia_step = self._transform_execution_step(step)
            portia_steps.append(portia_step)
        
        return portia_steps
    
    def _transform_execution_step(self, step: Dict[str, Any]) -> Dict[str, Any]:
        """Transform an execution step to Portia format.
        
        Args:
            step: Execution step data
            
        Returns:
            Portia step
        """
        portia_step = {
            'id': step.get('step_id'),
            'name': step.get('name'),
            'type': step.get('step_type', 'action'),
        }
        
        # Add description if present
        if step.get('description'):
            portia_step['description'] = step['description']
        
        # Add action and tool information
        if step.get('action'):
            portia_step['action'] = step['action']
        
        if step.get('tool'):
            portia_step['tool'] = step['tool']
        
        # Add parameters and inputs
        if step.get('parameters'):
            portia_step['parameters'] = step['parameters']
        
        if step.get('inputs'):
            portia_step['inputs'] = step['inputs']
        
        # Add outputs mapping
        if step.get('outputs'):
            portia_step['outputs'] = step['outputs']
        
        # Add dependencies
        if step.get('depends_on'):
            portia_step['depends_on'] = step['depends_on']
        
        # Add conditions
        if step.get('conditions'):
            portia_step['conditions'] = step['conditions']
        
        # Add retry policy
        if step.get('retry_policy'):
            portia_step['retry'] = step['retry_policy']
        
        # Add timeout
        if step.get('timeout'):
            portia_step['timeout'] = step['timeout']
        
        # Add metadata and tags
        if step.get('metadata'):
            portia_step['metadata'] = step['metadata']
        
        if step.get('tags'):
            portia_step['tags'] = step['tags']
        
        return portia_step
    
    def _extract_timeout(self, executable_plan: Dict[str, Any]) -> Optional[int]:
        """Extract timeout from ExecutablePlan.
        
        Args:
            executable_plan: ExecutablePlan data
            
        Returns:
            Timeout in seconds or None
        """
        # Check resource requirements for timeout
        resource_req = executable_plan.get('resource_requirements', {})
        if isinstance(resource_req, dict):
            timeout = resource_req.get('timeout')
            if timeout:
                return int(timeout)
        
        # Check configuration for timeout
        config = executable_plan.get('configuration', {})
        timeout = config.get('timeout')
        if timeout:
            return int(timeout)
        
        return None
    
    def _extract_retry_policy(self, executable_plan: Dict[str, Any]) -> Optional[RetryPolicy]:
        """Extract retry policy from ExecutablePlan.
        
        Args:
            executable_plan: ExecutablePlan data
            
        Returns:
            Retry policy or None
        """
        # Check configuration for retry policy
        config = executable_plan.get('configuration', {})
        retry_config = config.get('retry_policy')
        
        if retry_config and isinstance(retry_config, dict):
            return RetryPolicy(**retry_config)
        
        return None