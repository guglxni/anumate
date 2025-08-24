"""
Capability tokens client for token verification.
"""

import logging
from typing import List

import httpx

logger = logging.getLogger(__name__)


async def verify_token(base: str, token: str, required_caps: List[str]) -> None:
    """
    Verify capability token has required capabilities.
    
    Args:
        base: CapTokens service base URL
        token: Capability token to verify
        required_caps: List of required capabilities
        
    Raises:
        httpx.HTTPStatusError: If verification fails or token lacks capabilities
    """
    logger.info(f"Verifying token for capabilities: {required_caps}")
    
    verify_request = {
        "token": token,
        "required_capabilities": required_caps
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{base.rstrip('/')}/v1/captokens/verify",
            json=verify_request,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 403:
            error_detail = "Token lacks required capabilities"
            try:
                result = response.json()
                error_detail = result.get("detail", error_detail)
            except:
                pass
            logger.error(f"Token verification failed: {error_detail}")
            raise httpx.HTTPStatusError(
                f"Insufficient capabilities: {error_detail}",
                request=response.request,
                response=response
            )
        
        response.raise_for_status()
        logger.info("Token verification successful")
