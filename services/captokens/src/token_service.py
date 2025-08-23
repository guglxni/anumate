"""
Capability Tokens Service Implementation

A.22: Token verification service for Ed25519/JWT capability tokens
Provides centralized token management with audit trails.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
import asyncio
import uuid
import time

from sqlalchemy import Column, String, DateTime, Integer, Text, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from sqlalchemy.orm import selectinload

from cryptography.hazmat.primitives.asymmetric import ed25519
from anumate_capability_tokens import (
    issue_capability_token, 
    verify_capability_token,
    check_capability,
    CapabilityToken,
    InMemoryReplayGuard,
    ReplayGuard
)

logger = logging.getLogger(__name__)
Base = declarative_base()


class TokenRecord(Base):
    """Database record for issued tokens."""
    __tablename__ = "tokens"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    token_id = Column(String(255), unique=True, nullable=False, index=True)
    tenant_id = Column(String(255), nullable=False, index=True)
    subject = Column(String(255), nullable=False)
    capabilities = Column(ARRAY(String), nullable=False)
    issued_at = Column(DateTime(timezone=True), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked = Column(Boolean, default=False, nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(String(255), nullable=True)
    

class TokenUsageAudit(Base):
    """Audit trail for token usage."""
    __tablename__ = "token_usage_audit"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    token_id = Column(String(255), nullable=False, index=True)
    tenant_id = Column(String(255), nullable=False, index=True)
    action = Column(String(50), nullable=False)  # issued, verified, used, revoked
    capability_checked = Column(String(255), nullable=True)
    client_ip = Column(String(45), nullable=True)  # IPv4/IPv6
    user_agent = Column(Text, nullable=True)
    result = Column(String(50), nullable=False)  # success, failure, expired, revoked
    error_message = Column(Text, nullable=True)
    timestamp = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)


class TokenService:
    """
    Capability token service with verification and audit trails.
    
    Implements A.22 requirements:
    - Ed25519/JWT capability tokens
    - ≤5 minute expiry enforcement  
    - Capability-based access control
    - Token verification service
    - Audit trail for compliance
    """
    
    def __init__(
        self, 
        private_key: ed25519.Ed25519PrivateKey,
        public_key: ed25519.Ed25519PublicKey,
        db_session: AsyncSession,
        replay_guard: Optional[ReplayGuard] = None
    ):
        self.private_key = private_key
        self.public_key = public_key
        self.db_session = db_session
        self.replay_guard = replay_guard or InMemoryReplayGuard()
        
    async def issue_token(
        self,
        tenant_id: str,
        subject: str,
        capabilities: List[str],
        ttl_seconds: int = 300,  # 5 minutes default
        created_by: Optional[str] = None
    ) -> CapabilityToken:
        """
        Issue a new capability token.
        
        Args:
            tenant_id: Tenant identifier
            subject: Subject (user/service) identifier
            capabilities: List of capability strings
            ttl_seconds: TTL in seconds (max 300 = 5 minutes)
            created_by: Token issuer identifier
            
        Returns:
            CapabilityToken with JWT and metadata
            
        Raises:
            ValueError: If TTL exceeds 5 minutes
        """
        # A.22 requirement: ≤5 minute expiry
        if ttl_seconds > 300:
            raise ValueError("Token TTL cannot exceed 5 minutes (300 seconds)")
            
        # Issue token using the package
        capability_token = issue_capability_token(
            private_key=self.private_key,
            sub=subject,
            capabilities=capabilities,
            ttl_secs=ttl_seconds,
            tenant_id=tenant_id
        )
        
        # Store in database for audit/revocation
        token_record = TokenRecord(
            token_id=capability_token.token_id,
            tenant_id=tenant_id,
            subject=subject,
            capabilities=capabilities,
            issued_at=capability_token.issued_at,
            expires_at=capability_token.expires_at,
            created_by=created_by
        )
        
        self.db_session.add(token_record)
        
        # Add audit record
        await self._add_audit_record(
            token_id=capability_token.token_id,
            tenant_id=tenant_id,
            action="issued",
            result="success"
        )
        
        await self.db_session.commit()
        logger.info(f"Issued capability token {capability_token.token_id} for {subject}")
        
        return capability_token
    
    async def verify_token(
        self, 
        token: str,
        client_ip: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Dict[str, any]:
        """
        Verify a capability token.
        
        Args:
            token: JWT token string
            client_ip: Client IP for audit
            user_agent: User agent for audit
            
        Returns:
            Decoded token payload
            
        Raises:
            ValueError: If token is invalid, expired, or revoked
        """
        try:
            # Verify using the package
            payload = verify_capability_token(
                public_key=self.public_key,
                token=token,
                replay_guard=self.replay_guard
            )
            
            token_id = payload["jti"]
            tenant_id = payload["tenant_id"]
            
            # Check if token is revoked in database
            result = await self.db_session.execute(
                select(TokenRecord).where(
                    and_(
                        TokenRecord.token_id == token_id,
                        TokenRecord.revoked == False
                    )
                )
            )
            token_record = result.scalar_one_or_none()
            
            if not token_record:
                await self._add_audit_record(
                    token_id=token_id,
                    tenant_id=tenant_id,
                    action="verified",
                    result="revoked",
                    error_message="Token has been revoked",
                    client_ip=client_ip,
                    user_agent=user_agent
                )
                raise ValueError("Token has been revoked")
            
            # Add successful verification audit
            await self._add_audit_record(
                token_id=token_id,
                tenant_id=tenant_id,
                action="verified", 
                result="success",
                client_ip=client_ip,
                user_agent=user_agent
            )
            
            await self.db_session.commit()
            return payload
            
        except ValueError as e:
            # Try to extract token info for audit even if verification failed
            try:
                import jwt
                unverified = jwt.decode(token, options={"verify_signature": False})
                token_id = unverified.get("jti", "unknown")
                tenant_id = unverified.get("tenant_id", "unknown")
            except:
                token_id = "unknown"
                tenant_id = "unknown"
                
            await self._add_audit_record(
                token_id=token_id,
                tenant_id=tenant_id,
                action="verified",
                result="failure",
                error_message=str(e),
                client_ip=client_ip,
                user_agent=user_agent
            )
            await self.db_session.commit()
            raise
    
    async def check_capability(
        self,
        token: str, 
        required_capability: str,
        client_ip: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Tuple[bool, Optional[Dict[str, any]]]:
        """
        Check if token has a specific capability.
        
        Args:
            token: JWT token string
            required_capability: Capability to check for
            client_ip: Client IP for audit
            user_agent: User agent for audit
            
        Returns:
            Tuple of (has_capability, token_payload)
        """
        try:
            payload = await self.verify_token(token, client_ip, user_agent)
            capabilities = payload.get("capabilities", [])
            has_cap = required_capability in capabilities
            
            token_id = payload["jti"]
            tenant_id = payload["tenant_id"]
            
            # Add capability check audit
            await self._add_audit_record(
                token_id=token_id,
                tenant_id=tenant_id,
                action="capability_check",
                capability_checked=required_capability,
                result="success" if has_cap else "insufficient_capability",
                client_ip=client_ip,
                user_agent=user_agent
            )
            
            await self.db_session.commit()
            return has_cap, payload
            
        except ValueError:
            return False, None
    
    async def revoke_token(self, token_id: str, tenant_id: str, revoked_by: Optional[str] = None):
        """
        Revoke a capability token.
        
        Args:
            token_id: Token ID to revoke
            tenant_id: Tenant ID for security
            revoked_by: Who revoked the token
        """
        result = await self.db_session.execute(
            select(TokenRecord).where(
                and_(
                    TokenRecord.token_id == token_id,
                    TokenRecord.tenant_id == tenant_id
                )
            )
        )
        token_record = result.scalar_one_or_none()
        
        if not token_record:
            raise ValueError("Token not found")
        
        if token_record.revoked:
            raise ValueError("Token already revoked")
        
        # Mark as revoked
        token_record.revoked = True
        token_record.revoked_at = datetime.now(timezone.utc)
        
        # Add audit record
        await self._add_audit_record(
            token_id=token_id,
            tenant_id=tenant_id,
            action="revoked",
            result="success"
        )
        
        await self.db_session.commit()
        logger.info(f"Revoked token {token_id} by {revoked_by}")
    
    async def refresh_token(
        self,
        token: str,
        tenant_id: str,
        extend_ttl: Optional[int] = None,
        refreshed_by: Optional[str] = None
    ) -> CapabilityToken:
        """
        Refresh a capability token before expiry.
        
        Args:
            token: Current JWT token to refresh
            tenant_id: Tenant ID for security
            extend_ttl: Extended TTL in seconds (max 300, defaults to remaining time)
            refreshed_by: Who refreshed the token
            
        Returns:
            New CapabilityToken with extended expiry
            
        Raises:
            ValueError: If token is invalid, expired, or revoked
        """
        # First verify the current token
        try:
            payload = verify_capability_token(
                public_key=self.public_key,
                token=token,
                replay_guard=self.replay_guard
            )
        except ValueError as e:
            await self._add_audit_record(
                token_id="unknown",
                tenant_id=tenant_id,
                action="refresh_failed",
                result="invalid_token",
                error_message=str(e)
            )
            raise ValueError(f"Cannot refresh invalid token: {e}")
        
        old_token_id = payload["jti"]
        
        # Verify tenant matches
        if payload["tenant_id"] != tenant_id:
            await self._add_audit_record(
                token_id=old_token_id,
                tenant_id=tenant_id,
                action="refresh_failed",
                result="tenant_mismatch"
            )
            raise ValueError("Token tenant does not match request tenant")
        
        # Check if token exists in database and is not revoked
        result = await self.db_session.execute(
            select(TokenRecord).where(
                and_(
                    TokenRecord.token_id == old_token_id,
                    TokenRecord.tenant_id == tenant_id,
                    TokenRecord.revoked == False
                )
            )
        )
        token_record = result.scalar_one_or_none()
        
        if not token_record:
            await self._add_audit_record(
                token_id=old_token_id,
                tenant_id=tenant_id,
                action="refresh_failed",
                result="token_not_found_or_revoked"
            )
            raise ValueError("Token not found or already revoked")
        
        # Calculate new TTL
        if extend_ttl is None:
            # Default: extend by remaining time or 60 seconds, whichever is less
            remaining_time = payload["exp"] - int(time.time())
            extend_ttl = min(remaining_time, 60)
        
        if extend_ttl > 300:  # A.22 requirement: ≤5 minutes
            raise ValueError("Extended TTL cannot exceed 5 minutes (300 seconds)")
        
        # Issue new token with same capabilities
        new_token = await self.issue_token(
            tenant_id=tenant_id,
            subject=payload["sub"],
            capabilities=payload["capabilities"],
            ttl_seconds=extend_ttl,
            created_by=refreshed_by or "refresh"
        )
        
        # Revoke the old token
        token_record.revoked = True
        token_record.revoked_at = datetime.now(timezone.utc)
        
        # Add audit records for both operations
        await self._add_audit_record(
            token_id=old_token_id,
            tenant_id=tenant_id,
            action="refreshed_old",
            result="success"
        )
        
        await self._add_audit_record(
            token_id=new_token.token_id,
            tenant_id=tenant_id,
            action="refreshed_new",
            result="success"
        )
        
        await self.db_session.commit()
        logger.info(f"Refreshed token {old_token_id} -> {new_token.token_id} for {payload['sub']}")
        
        return new_token
    
    async def get_token_audit_trail(
        self, 
        tenant_id: str,
        token_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, any]]:
        """
        Get audit trail for tokens.
        
        Args:
            tenant_id: Tenant identifier
            token_id: Specific token ID (optional)
            limit: Max results
            
        Returns:
            List of audit records
        """
        query = select(TokenUsageAudit).where(TokenUsageAudit.tenant_id == tenant_id)
        
        if token_id:
            query = query.where(TokenUsageAudit.token_id == token_id)
        
        query = query.order_by(TokenUsageAudit.timestamp.desc()).limit(limit)
        
        result = await self.db_session.execute(query)
        records = result.scalars().all()
        
        return [
            {
                "id": str(record.id),
                "token_id": record.token_id,
                "tenant_id": record.tenant_id,
                "action": record.action,
                "capability_checked": record.capability_checked,
                "client_ip": record.client_ip,
                "user_agent": record.user_agent,
                "result": record.result,
                "error_message": record.error_message,
                "timestamp": record.timestamp.isoformat()
            }
            for record in records
        ]
    
    async def cleanup_expired_tokens(self):
        """Clean up expired tokens from database."""
        now = datetime.now(timezone.utc)
        
        # Find expired tokens
        result = await self.db_session.execute(
            select(TokenRecord).where(
                and_(
                    TokenRecord.expires_at < now,
                    TokenRecord.revoked == False
                )
            )
        )
        expired_tokens = result.scalars().all()
        
        # Mark as revoked
        for token in expired_tokens:
            token.revoked = True
            token.revoked_at = now
            
            await self._add_audit_record(
                token_id=token.token_id,
                tenant_id=token.tenant_id,
                action="expired",
                result="automatic_cleanup"
            )
        
        await self.db_session.commit()
        logger.info(f"Cleaned up {len(expired_tokens)} expired tokens")
        
        return len(expired_tokens)
    
    async def _add_audit_record(
        self,
        token_id: str,
        tenant_id: str,
        action: str,
        result: str,
        capability_checked: Optional[str] = None,
        error_message: Optional[str] = None,
        client_ip: Optional[str] = None,
        user_agent: Optional[str] = None
    ):
        """Add an audit record."""
        audit_record = TokenUsageAudit(
            token_id=token_id,
            tenant_id=tenant_id,
            action=action,
            capability_checked=capability_checked,
            client_ip=client_ip,
            user_agent=user_agent,
            result=result,
            error_message=error_message,
            timestamp=datetime.now(timezone.utc)
        )
        
        self.db_session.add(audit_record)


class TokenCleanupService:
    """Background service for token cleanup."""
    
    def __init__(self, token_service: TokenService, cleanup_interval: int = 300):
        self.token_service = token_service
        self.cleanup_interval = cleanup_interval  # 5 minutes default
        self.running = False
        
    async def start(self):
        """Start the cleanup service."""
        self.running = True
        logger.info("Started token cleanup service")
        
        while self.running:
            try:
                await self.token_service.cleanup_expired_tokens()
                await asyncio.sleep(self.cleanup_interval)
            except Exception as e:
                logger.error(f"Error in token cleanup: {e}")
                await asyncio.sleep(60)  # Short retry delay
                
    def stop(self):
        """Stop the cleanup service."""
        self.running = False
        logger.info("Stopped token cleanup service")
