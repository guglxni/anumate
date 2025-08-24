"""
Production-grade Portia SDK client for WeMakeDevs AgentHack 2025.

This module provides a production-ready wrapper around the official Portia SDK
with proper configuration management, error handling, and logging.
"""

import os
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

try:
    from portia import Portia, Config, Plan, PlanRun, PlanRunState
    HAS_PORTIA_SDK = True
except ImportError:
    HAS_PORTIA_SDK = False
    # Define minimal types for development
    Plan = Dict[str, Any]
    PlanRun = Dict[str, Any]
    PlanRunState = str


logger = logging.getLogger(__name__)


class PortiaConfigurationError(Exception):
    """Raised when Portia SDK configuration is invalid or missing."""
    pass


class PortiaSDKClientError(Exception):
    """Raised when Portia SDK operations fail."""
    pass


@dataclass
class PortiaExecutionRequest:
    """Request model for plan execution."""
    plan_content: str
    inputs: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class PortiaExecutionResult:
    """Result model for plan execution."""
    run_id: str
    status: str
    outputs: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class PortiaSDKClient:
    """Production-grade Portia SDK client."""
    
    def __init__(self, api_key: Optional[str] = None, workspace: Optional[str] = None):
        """Initialize Portia SDK client with production configuration.
        
        Args:
            api_key: Portia API key (optional, will use env var if not provided)
            workspace: Portia workspace ID (optional, will use env var if not provided)
            
        Raises:
            PortiaConfigurationError: If configuration is invalid or SDK unavailable
        """
        if not HAS_PORTIA_SDK:
            raise PortiaConfigurationError(
                "Portia SDK not available. Install with: pip install portia-sdk-python"
            )
        
        # Get configuration from environment or parameters
        self.api_key = api_key or os.environ.get('PORTIA_API_KEY')
        self.workspace = workspace or os.environ.get('PORTIA_WORKSPACE')
        
        # Validate configuration
        self._validate_configuration()
        
        # Initialize SDK
        try:
            config = Config(
                api_key=self.api_key,
                workspace=self.workspace
            )
            self.client = Portia(config=config)
            self.base_url = getattr(config, 'base_url', 'https://app.portia.ai')
            
            logger.info(f"Initialized Portia SDK client for workspace: {self.workspace[:8]}...")
            
        except Exception as e:
            raise PortiaConfigurationError(f"Failed to initialize Portia SDK: {e}")
    
    def _validate_configuration(self) -> None:
        """Validate production configuration requirements."""
        if not self.api_key:
            raise PortiaConfigurationError(
                "PORTIA_API_KEY environment variable is required. "
                "Get your API key from: https://app.portia.ai/settings/api-keys"
            )
        
        if not self.workspace:
            raise PortiaConfigurationError(
                "PORTIA_WORKSPACE environment variable is required. "
                "Find your workspace ID at: https://app.portia.ai/settings/workspace"
            )
        
        # Validate API key format (production keys should start with pk_)
        if not self.api_key.startswith('pk_'):
            logger.warning(
                f"API key format may not be production-grade (expected 'pk_' prefix). "
                f"Current format: {self.api_key[:8]}..."
            )
        
        # Validate workspace format (should be UUID)
        if len(self.workspace) != 36 or self.workspace.count('-') != 4:
            logger.warning(
                f"Workspace ID format may not be valid UUID. "
                f"Expected: XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX"
            )
    
    async def create_plan(self, plan_content: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """Create a new plan in Portia.
        
        Args:
            plan_content: The plan definition content
            metadata: Optional metadata for the plan
            
        Returns:
            Plan ID
            
        Raises:
            PortiaSDKClientError: If plan creation fails
        """
        try:
            plan = await self.client.plans.create(
                content=plan_content,
                metadata=metadata or {}
            )
            logger.info(f"Created plan: {plan.id}")
            return plan.id
            
        except Exception as e:
            error_msg = f"Failed to create plan: {e}"
            logger.error(error_msg)
            raise PortiaSDKClientError(error_msg)
    
    async def execute_plan(self, request: PortiaExecutionRequest) -> PortiaExecutionResult:
        """Execute a plan with the given inputs.
        
        Args:
            request: Execution request with plan content and inputs
            
        Returns:
            Execution result
            
        Raises:
            PortiaSDKClientError: If execution fails
        """
        try:
            # Create plan
            plan_id = await self.create_plan(
                plan_content=request.plan_content,
                metadata=request.metadata
            )
            
            # Execute plan
            run = await self.client.plans.execute(
                plan_id=plan_id,
                inputs=request.inputs or {}
            )
            
            logger.info(f"Started plan execution: {run.id}")
            
            return PortiaExecutionResult(
                run_id=run.id,
                status=run.status,
                outputs=getattr(run, 'outputs', None),
                metadata=getattr(run, 'metadata', None)
            )
            
        except Exception as e:
            error_msg = f"Failed to execute plan: {e}"
            logger.error(error_msg)
            raise PortiaSDKClientError(error_msg)
    
    async def get_run_status(self, run_id: str) -> PortiaExecutionResult:
        """Get the status of a plan run.
        
        Args:
            run_id: Plan run ID
            
        Returns:
            Current run status and results
            
        Raises:
            PortiaSDKClientError: If status check fails
        """
        try:
            run = await self.client.runs.get(run_id)
            
            return PortiaExecutionResult(
                run_id=run.id,
                status=run.status,
                outputs=getattr(run, 'outputs', None),
                error=getattr(run, 'error', None),
                metadata=getattr(run, 'metadata', None)
            )
            
        except Exception as e:
            error_msg = f"Failed to get run status: {e}"
            logger.error(error_msg)
            raise PortiaSDKClientError(error_msg)
    
    async def wait_for_completion(self, run_id: str, timeout_seconds: int = 300) -> PortiaExecutionResult:
        """Wait for a plan run to complete.
        
        Args:
            run_id: Plan run ID
            timeout_seconds: Maximum time to wait
            
        Returns:
            Final run result
            
        Raises:
            PortiaSDKClientError: If run fails or times out
        """
        import asyncio
        
        start_time = asyncio.get_event_loop().time()
        
        while True:
            result = await self.get_run_status(run_id)
            
            # Check for completion
            if result.status in ['completed', 'failed', 'cancelled']:
                logger.info(f"Plan run {run_id} finished with status: {result.status}")
                return result
            
            # Check timeout
            if asyncio.get_event_loop().time() - start_time > timeout_seconds:
                error_msg = f"Plan run {run_id} timed out after {timeout_seconds}s"
                logger.error(error_msg)
                raise PortiaSDKClientError(error_msg)
            
            # Wait before next check
            await asyncio.sleep(1)
    
    async def list_plans(self, limit: int = 50) -> List[Dict[str, Any]]:
        """List plans in the workspace.
        
        Args:
            limit: Maximum number of plans to return
            
        Returns:
            List of plan metadata
            
        Raises:
            PortiaSDKClientError: If listing fails
        """
        try:
            plans = await self.client.plans.list(limit=limit)
            return [
                {
                    'id': plan.id,
                    'name': getattr(plan, 'name', None),
                    'created_at': getattr(plan, 'created_at', None),
                    'metadata': getattr(plan, 'metadata', {})
                }
                for plan in plans
            ]
            
        except Exception as e:
            error_msg = f"Failed to list plans: {e}"
            logger.error(error_msg)
            raise PortiaSDKClientError(error_msg)
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on Portia connection.
        
        Returns:
            Health status information
            
        Raises:
            PortiaSDKClientError: If health check fails
        """
        try:
            # Try to list plans as a connectivity test
            plans = await self.list_plans(limit=1)
            
            return {
                'status': 'healthy',
                'workspace': self.workspace,
                'api_key_prefix': self.api_key[:8] + '...',
                'base_url': self.base_url,
                'plans_accessible': len(plans) >= 0
            }
            
        except Exception as e:
            error_msg = f"Health check failed: {e}"
            logger.error(error_msg)
            raise PortiaSDKClientError(error_msg)


# Backward compatibility with old PortiaClient interface
class PortiaClient(PortiaSDKClient):
    """Backward compatibility alias for PortiaSDKClient."""
    
    def __init__(self, *args, **kwargs):
        logger.warning(
            "PortiaClient is deprecated. Use PortiaSDKClient instead. "
            "This alias will be removed in a future version."
        )
        super().__init__(*args, **kwargs)


# Export main classes
__all__ = [
    'PortiaSDKClient',
    'PortiaClient',  # Backward compatibility
    'PortiaConfigurationError',
    'PortiaSDKClientError',
    'PortiaExecutionRequest',
    'PortiaExecutionResult'
]
