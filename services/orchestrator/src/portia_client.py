"""Portia Runtime client for plan execution."""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional
from uuid import uuid4

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

try:
    from anumate_core_config import settings
except ImportError:
    # Fallback settings for development
    class MockSettings:
        PORTIA_BASE_URL = "http://localhost:8080"
        PORTIA_API_KEY = "mock-api-key"
    settings = MockSettings()
try:
    from anumate_errors import AnumateError
except ImportError:
    # Fallback error class for development
    class AnumateError(Exception):
        pass
# Tracing removed for development compatibility
def trace_async(name):
    """Mock trace_async decorator for development."""
    def decorator(func):
        return func
    return decorator

from .models import (
    Clarification,
    ClarificationStatus,
    ExecutionStatusEnum,
    PortiaPlan,
    PortiaPlanRun,
    RetryPolicy,
)

logger = logging.getLogger(__name__)


class PortiaClientError(AnumateError):
    """Portia client error."""
    pass


class PortiaClient:
    """Client for interacting with Portia Runtime."""
    
    def __init__(self, base_url: Optional[str] = None, timeout: float = 30.0):
        """Initialize Portia client.
        
        Args:
            base_url: Portia base URL (defaults to settings)
            timeout: Request timeout in seconds
        """
        self.base_url = base_url or settings.PORTIA_BASE_URL
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
    
    async def __aenter__(self):
        """Async context manager entry."""
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "anumate-orchestrator/0.1.0",
            }
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    @property
    def client(self) -> httpx.AsyncClient:
        """Get HTTP client."""
        if not self._client:
            raise PortiaClientError("Client not initialized. Use async context manager.")
        return self._client
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.RequestError),
    )
    async def create_plan(self, plan: PortiaPlan) -> PortiaPlan:
        """Create a plan in Portia Runtime.
        
        Args:
            plan: Plan to create
            
        Returns:
            Created plan with Portia metadata
            
        Raises:
            PortiaClientError: If plan creation fails
        """
        try:
            response = await self.client.post(
                "/api/v1/plans",
                json=plan.model_dump(exclude_unset=True)
            )
            response.raise_for_status()
            
            plan_data = response.json()
            logger.info(f"Created Portia plan: {plan_data.get('plan_id')}")
            
            return PortiaPlan(**plan_data)
            
        except httpx.HTTPStatusError as e:
            error_msg = f"Failed to create Portia plan: {e.response.status_code}"
            if e.response.content:
                try:
                    error_detail = e.response.json()
                    error_msg += f" - {error_detail.get('message', 'Unknown error')}"
                except json.JSONDecodeError:
                    error_msg += f" - {e.response.text}"
            
            logger.error(error_msg)
            raise PortiaClientError(error_msg) from e
            
        except httpx.RequestError as e:
            error_msg = f"Request failed when creating Portia plan: {e}"
            logger.error(error_msg)
            raise PortiaClientError(error_msg) from e
    
    async def get_plan(self, plan_id: str) -> Optional[PortiaPlan]:
        """Get a plan from Portia Runtime.
        
        Args:
            plan_id: Plan ID to retrieve
            
        Returns:
            Plan if found, None otherwise
            
        Raises:
            PortiaClientError: If request fails
        """
        try:
            response = await self.client.get(f"/api/v1/plans/{plan_id}")
            
            if response.status_code == 404:
                return None
                
            response.raise_for_status()
            return PortiaPlan(**response.json())
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            error_msg = f"Failed to get Portia plan {plan_id}: {e.response.status_code}"
            logger.error(error_msg)
            raise PortiaClientError(error_msg) from e
            
        except httpx.RequestError as e:
            error_msg = f"Request failed when getting Portia plan {plan_id}: {e}"
            logger.error(error_msg)
            raise PortiaClientError(error_msg) from e
    
    @trace_async("portia_client.create_run")
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.RequestError),
    )
    async def create_run(
        self,
        plan_id: str,
        parameters: Optional[Dict[str, Any]] = None,
        variables: Optional[Dict[str, Any]] = None,
        triggered_by: Optional[str] = None,
    ) -> PortiaPlanRun:
        """Create a plan run in Portia Runtime.
        
        Args:
            plan_id: Plan ID to execute
            parameters: Execution parameters
            variables: Runtime variables
            triggered_by: User who triggered execution
            
        Returns:
            Created plan run
            
        Raises:
            PortiaClientError: If run creation fails
        """
        run_data = {
            "plan_id": plan_id,
            "parameters": parameters or {},
            "variables": variables or {},
            "triggered_by": triggered_by or "system",
        }
        
        try:
            response = await self.client.post(
                "/api/v1/runs",
                json=run_data
            )
            response.raise_for_status()
            
            run_result = response.json()
            logger.info(f"Created Portia run: {run_result.get('run_id')}")
            
            return PortiaPlanRun(**run_result)
            
        except httpx.HTTPStatusError as e:
            error_msg = f"Failed to create Portia run: {e.response.status_code}"
            if e.response.content:
                try:
                    error_detail = e.response.json()
                    error_msg += f" - {error_detail.get('message', 'Unknown error')}"
                except json.JSONDecodeError:
                    error_msg += f" - {e.response.text}"
            
            logger.error(error_msg)
            raise PortiaClientError(error_msg) from e
            
        except httpx.RequestError as e:
            error_msg = f"Request failed when creating Portia run: {e}"
            logger.error(error_msg)
            raise PortiaClientError(error_msg) from e
    
    @trace_async("portia_client.get_run")
    async def get_run(self, run_id: str) -> Optional[PortiaPlanRun]:
        """Get a plan run from Portia Runtime.
        
        Args:
            run_id: Run ID to retrieve
            
        Returns:
            Plan run if found, None otherwise
            
        Raises:
            PortiaClientError: If request fails
        """
        try:
            response = await self.client.get(f"/api/v1/runs/{run_id}")
            
            if response.status_code == 404:
                return None
                
            response.raise_for_status()
            return PortiaPlanRun(**response.json())
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            error_msg = f"Failed to get Portia run {run_id}: {e.response.status_code}"
            logger.error(error_msg)
            raise PortiaClientError(error_msg) from e
            
        except httpx.RequestError as e:
            error_msg = f"Request failed when getting Portia run {run_id}: {e}"
            logger.error(error_msg)
            raise PortiaClientError(error_msg) from e
    
    @trace_async("portia_client.pause_run")
    async def pause_run(self, run_id: str) -> bool:
        """Pause a running plan execution.
        
        Args:
            run_id: Run ID to pause
            
        Returns:
            True if paused successfully
            
        Raises:
            PortiaClientError: If pause fails
        """
        try:
            response = await self.client.post(f"/api/v1/runs/{run_id}/pause")
            response.raise_for_status()
            
            logger.info(f"Paused Portia run: {run_id}")
            return True
            
        except httpx.HTTPStatusError as e:
            error_msg = f"Failed to pause Portia run {run_id}: {e.response.status_code}"
            logger.error(error_msg)
            raise PortiaClientError(error_msg) from e
            
        except httpx.RequestError as e:
            error_msg = f"Request failed when pausing Portia run {run_id}: {e}"
            logger.error(error_msg)
            raise PortiaClientError(error_msg) from e
    
    @trace_async("portia_client.resume_run")
    async def resume_run(self, run_id: str) -> bool:
        """Resume a paused plan execution.
        
        Args:
            run_id: Run ID to resume
            
        Returns:
            True if resumed successfully
            
        Raises:
            PortiaClientError: If resume fails
        """
        try:
            response = await self.client.post(f"/api/v1/runs/{run_id}/resume")
            response.raise_for_status()
            
            logger.info(f"Resumed Portia run: {run_id}")
            return True
            
        except httpx.HTTPStatusError as e:
            error_msg = f"Failed to resume Portia run {run_id}: {e.response.status_code}"
            logger.error(error_msg)
            raise PortiaClientError(error_msg) from e
            
        except httpx.RequestError as e:
            error_msg = f"Request failed when resuming Portia run {run_id}: {e}"
            logger.error(error_msg)
            raise PortiaClientError(error_msg) from e
    
    @trace_async("portia_client.cancel_run")
    async def cancel_run(self, run_id: str) -> bool:
        """Cancel a plan execution.
        
        Args:
            run_id: Run ID to cancel
            
        Returns:
            True if cancelled successfully
            
        Raises:
            PortiaClientError: If cancel fails
        """
        try:
            response = await self.client.post(f"/api/v1/runs/{run_id}/cancel")
            response.raise_for_status()
            
            logger.info(f"Cancelled Portia run: {run_id}")
            return True
            
        except httpx.HTTPStatusError as e:
            error_msg = f"Failed to cancel Portia run {run_id}: {e.response.status_code}"
            logger.error(error_msg)
            raise PortiaClientError(error_msg) from e
            
        except httpx.RequestError as e:
            error_msg = f"Request failed when cancelling Portia run {run_id}: {e}"
            logger.error(error_msg)
            raise PortiaClientError(error_msg) from e
    
    @trace_async("portia_client.get_clarifications")
    async def get_clarifications(self, run_id: str) -> List[Clarification]:
        """Get clarifications for a plan run.
        
        Args:
            run_id: Run ID to get clarifications for
            
        Returns:
            List of clarifications
            
        Raises:
            PortiaClientError: If request fails
        """
        try:
            response = await self.client.get(f"/api/v1/runs/{run_id}/clarifications")
            response.raise_for_status()
            
            clarifications_data = response.json()
            return [Clarification(**c) for c in clarifications_data.get("clarifications", [])]
            
        except httpx.HTTPStatusError as e:
            error_msg = f"Failed to get clarifications for run {run_id}: {e.response.status_code}"
            logger.error(error_msg)
            raise PortiaClientError(error_msg) from e
            
        except httpx.RequestError as e:
            error_msg = f"Request failed when getting clarifications for run {run_id}: {e}"
            logger.error(error_msg)
            raise PortiaClientError(error_msg) from e
    
    @trace_async("portia_client.respond_to_clarification")
    async def respond_to_clarification(
        self,
        clarification_id: str,
        approved: bool,
        approver_id: str,
        reason: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Clarification:
        """Respond to a clarification request.
        
        Args:
            clarification_id: Clarification ID
            approved: Whether the clarification is approved
            approver_id: ID of the approver
            reason: Reason for approval/rejection
            metadata: Additional response metadata
            
        Returns:
            Updated clarification
            
        Raises:
            PortiaClientError: If response fails
        """
        response_data = {
            "approved": approved,
            "approver_id": approver_id,
            "reason": reason,
            "metadata": metadata or {},
        }
        
        try:
            response = await self.client.post(
                f"/api/v1/clarifications/{clarification_id}/respond",
                json=response_data
            )
            response.raise_for_status()
            
            clarification_data = response.json()
            logger.info(f"Responded to clarification {clarification_id}: {'approved' if approved else 'rejected'}")
            
            return Clarification(**clarification_data)
            
        except httpx.HTTPStatusError as e:
            error_msg = f"Failed to respond to clarification {clarification_id}: {e.response.status_code}"
            logger.error(error_msg)
            raise PortiaClientError(error_msg) from e
            
        except httpx.RequestError as e:
            error_msg = f"Request failed when responding to clarification {clarification_id}: {e}"
            logger.error(error_msg)
            raise PortiaClientError(error_msg) from e
    
    @trace_async("portia_client.health_check")
    async def health_check(self) -> bool:
        """Check Portia Runtime health.
        
        Returns:
            True if healthy, False otherwise
        """
        try:
            response = await self.client.get("/health")
            return response.status_code == 200
            
        except Exception as e:
            logger.warning(f"Portia health check failed: {e}")
            return False