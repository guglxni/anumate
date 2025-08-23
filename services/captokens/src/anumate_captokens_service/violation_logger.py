"""
Violation Logger Service
=======================

Service for logging capability violations and security events.
Provides comprehensive security monitoring and alerting.
"""

import logging
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc

from .models import CapabilityViolation
from .capability_checker import CapabilityCheckResult

logger = logging.getLogger(__name__)


@dataclass
class ViolationContext:
    """Context information for capability violations."""
    endpoint: Optional[str] = None
    http_method: Optional[str] = None
    client_ip: Optional[str] = None
    user_agent: Optional[str] = None
    token_id: Optional[str] = None
    subject: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class ViolationSeverity:
    """Violation severity levels."""
    LOW = "low"
    MEDIUM = "medium" 
    HIGH = "high"
    CRITICAL = "critical"


class ViolationType:
    """Types of capability violations."""
    INSUFFICIENT_CAPABILITY = "insufficient_capability"
    INVALID_TOKEN = "invalid_token"
    TOOL_BLOCKED = "tool_blocked"
    EXPIRED_TOKEN = "expired_token"
    REPLAY_ATTACK = "replay_attack"
    MALFORMED_REQUEST = "malformed_request"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"


class ViolationLogger:
    """
    Service for logging and managing capability violations.
    
    Features:
    - Comprehensive violation logging
    - Severity-based alerting
    - Pattern detection for security threats
    - Integration with SIEM systems
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def log_capability_violation(
        self,
        tenant_id: str,
        violation_type: str,
        attempted_action: str,
        check_result: Optional[CapabilityCheckResult] = None,
        context: Optional[ViolationContext] = None
    ) -> str:
        """
        Log a capability violation.
        
        Args:
            tenant_id: Tenant ID
            violation_type: Type of violation
            attempted_action: Action that was attempted
            check_result: Result from capability check
            context: Additional context information
            
        Returns:
            Violation ID
        """
        try:
            context = context or ViolationContext()
            
            # Determine severity based on violation type and context
            severity = self._determine_severity(violation_type, context)
            
            # Create violation record
            violation = CapabilityViolation(
                violation_id=uuid.uuid4(),
                tenant_id=tenant_id,
                token_id=context.token_id,
                violation_type=violation_type,
                attempted_action=attempted_action,
                required_capability=", ".join(check_result.required_capabilities) if check_result else None,
                provided_capabilities=check_result.matched_rules if check_result else None,
                endpoint=context.endpoint,
                http_method=context.http_method,
                client_ip=context.client_ip,
                user_agent=context.user_agent,
                subject=context.subject,
                extra_metadata=context.metadata or {},
                severity=severity
            )
            
            self.db.add(violation)
            await self.db.commit()
            
            # Log to application logs
            log_level = self._get_log_level(severity)
            logger.log(
                log_level,
                f"Capability violation: {violation_type} - {attempted_action}",
                extra={
                    "violation_id": str(violation.violation_id),
                    "tenant_id": tenant_id,
                    "violation_type": violation_type,
                    "attempted_action": attempted_action,
                    "severity": severity,
                    "client_ip": context.client_ip,
                    "subject": context.subject
                }
            )
            
            # Trigger alerts for high-severity violations
            if severity in [ViolationSeverity.HIGH, ViolationSeverity.CRITICAL]:
                await self._trigger_security_alert(violation)
            
            return str(violation.violation_id)
            
        except Exception as e:
            logger.error(f"Failed to log capability violation: {e}", exc_info=True)
            await self.db.rollback()
            raise
    
    async def log_token_violation(
        self,
        tenant_id: str,
        token_id: Optional[str],
        subject: Optional[str],
        violation_type: str,
        attempted_action: str,
        context: Optional[ViolationContext] = None
    ) -> str:
        """
        Log a token-related violation.
        
        Args:
            tenant_id: Tenant ID
            token_id: Token ID (if available)
            subject: Subject (if available)
            violation_type: Type of violation
            attempted_action: Action that was attempted
            context: Additional context information
            
        Returns:
            Violation ID
        """
        context = context or ViolationContext()
        context.token_id = token_id
        context.subject = subject
        
        return await self.log_capability_violation(
            tenant_id=tenant_id,
            violation_type=violation_type,
            attempted_action=attempted_action,
            check_result=None,
            context=context
        )
    
    async def get_violations_by_tenant(
        self,
        tenant_id: str,
        limit: int = 100,
        offset: int = 0,
        severity: Optional[str] = None,
        violation_type: Optional[str] = None
    ) -> List[CapabilityViolation]:
        """
        Get violations for a tenant with filtering.
        
        Args:
            tenant_id: Tenant ID
            limit: Maximum number of results
            offset: Offset for pagination
            severity: Filter by severity
            violation_type: Filter by violation type
            
        Returns:
            List of violations
        """
        try:
            query = select(CapabilityViolation).where(
                CapabilityViolation.tenant_id == tenant_id
            )
            
            if severity:
                query = query.where(CapabilityViolation.severity == severity)
            
            if violation_type:
                query = query.where(CapabilityViolation.violation_type == violation_type)
            
            query = query.order_by(desc(CapabilityViolation.created_at)).limit(limit).offset(offset)
            
            result = await self.db.execute(query)
            return result.scalars().all()
            
        except Exception as e:
            logger.error(f"Failed to get violations: {e}")
            return []
    
    async def get_violation_stats(self, tenant_id: str, hours: int = 24) -> Dict[str, Any]:
        """
        Get violation statistics for a tenant.
        
        Args:
            tenant_id: Tenant ID
            hours: Number of hours to analyze
            
        Returns:
            Violation statistics
        """
        try:
            from sqlalchemy import func
            from datetime import timedelta
            
            since = datetime.utcnow() - timedelta(hours=hours)
            
            # Total violations
            total_query = select(func.count(CapabilityViolation.violation_id)).where(
                and_(
                    CapabilityViolation.tenant_id == tenant_id,
                    CapabilityViolation.created_at >= since
                )
            )
            total_result = await self.db.execute(total_query)
            total_violations = total_result.scalar() or 0
            
            # Violations by type
            type_query = select(
                CapabilityViolation.violation_type,
                func.count(CapabilityViolation.violation_id)
            ).where(
                and_(
                    CapabilityViolation.tenant_id == tenant_id,
                    CapabilityViolation.created_at >= since
                )
            ).group_by(CapabilityViolation.violation_type)
            
            type_result = await self.db.execute(type_query)
            violations_by_type = dict(type_result.fetchall())
            
            # Violations by severity
            severity_query = select(
                CapabilityViolation.severity,
                func.count(CapabilityViolation.violation_id)
            ).where(
                and_(
                    CapabilityViolation.tenant_id == tenant_id,
                    CapabilityViolation.created_at >= since
                )
            ).group_by(CapabilityViolation.severity)
            
            severity_result = await self.db.execute(severity_query)
            violations_by_severity = dict(severity_result.fetchall())
            
            # Top violated actions
            action_query = select(
                CapabilityViolation.attempted_action,
                func.count(CapabilityViolation.violation_id)
            ).where(
                and_(
                    CapabilityViolation.tenant_id == tenant_id,
                    CapabilityViolation.created_at >= since
                )
            ).group_by(CapabilityViolation.attempted_action).limit(10)
            
            action_result = await self.db.execute(action_query)
            top_violated_actions = dict(action_result.fetchall())
            
            return {
                "period_hours": hours,
                "total_violations": total_violations,
                "violations_by_type": violations_by_type,
                "violations_by_severity": violations_by_severity,
                "top_violated_actions": top_violated_actions,
                "generated_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to get violation stats: {e}")
            return {}
    
    def _determine_severity(self, violation_type: str, context: ViolationContext) -> str:
        """Determine violation severity based on type and context."""
        # Critical violations
        if violation_type in [ViolationType.REPLAY_ATTACK, ViolationType.MALFORMED_REQUEST]:
            return ViolationSeverity.CRITICAL
        
        # High severity violations
        if violation_type in [ViolationType.INVALID_TOKEN, ViolationType.RATE_LIMIT_EXCEEDED]:
            return ViolationSeverity.HIGH
        
        # Medium severity violations (default)
        if violation_type in [ViolationType.INSUFFICIENT_CAPABILITY, ViolationType.TOOL_BLOCKED]:
            return ViolationSeverity.MEDIUM
        
        # Low severity violations
        if violation_type == ViolationType.EXPIRED_TOKEN:
            return ViolationSeverity.LOW
        
        # Default to medium
        return ViolationSeverity.MEDIUM
    
    def _get_log_level(self, severity: str) -> int:
        """Get logging level based on severity."""
        severity_to_level = {
            ViolationSeverity.LOW: logging.INFO,
            ViolationSeverity.MEDIUM: logging.WARNING,
            ViolationSeverity.HIGH: logging.ERROR,
            ViolationSeverity.CRITICAL: logging.CRITICAL
        }
        return severity_to_level.get(severity, logging.WARNING)
    
    async def _trigger_security_alert(self, violation: CapabilityViolation) -> None:
        """Trigger security alert for high-severity violations."""
        try:
            # In a production environment, this would:
            # 1. Send alerts to security team via email/Slack
            # 2. Create incidents in incident management system
            # 3. Trigger automated responses (rate limiting, IP blocking)
            # 4. Send to SIEM systems
            
            alert_message = (
                f"HIGH SEVERITY SECURITY VIOLATION\n"
                f"Violation ID: {violation.violation_id}\n"
                f"Type: {violation.violation_type}\n"
                f"Action: {violation.attempted_action}\n"
                f"Tenant: {violation.tenant_id}\n"
                f"Client IP: {violation.client_ip}\n"
                f"Subject: {violation.subject}\n"
                f"Time: {violation.created_at}\n"
            )
            
            logger.critical(
                f"SECURITY ALERT: {violation.violation_type}",
                extra={
                    "alert": True,
                    "violation_id": str(violation.violation_id),
                    "tenant_id": str(violation.tenant_id),
                    "severity": violation.severity,
                    "alert_message": alert_message
                }
            )
            
            # TODO: Implement actual alerting mechanisms:
            # await send_email_alert(alert_message)
            # await send_slack_alert(violation)
            # await create_incident(violation)
            
        except Exception as e:
            logger.error(f"Failed to trigger security alert: {e}")
    
    async def cleanup_old_violations(self, tenant_id: str, days: int = 90) -> int:
        """
        Clean up old violation records.
        
        Args:
            tenant_id: Tenant ID
            days: Number of days to retain
            
        Returns:
            Number of violations cleaned up
        """
        try:
            from datetime import timedelta
            
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            # Delete old violations
            delete_query = select(CapabilityViolation).where(
                and_(
                    CapabilityViolation.tenant_id == tenant_id,
                    CapabilityViolation.created_at < cutoff_date
                )
            )
            
            result = await self.db.execute(delete_query)
            violations_to_delete = result.scalars().all()
            
            for violation in violations_to_delete:
                await self.db.delete(violation)
            
            await self.db.commit()
            
            count = len(violations_to_delete)
            logger.info(f"Cleaned up {count} old violation records for tenant {tenant_id}")
            
            return count
            
        except Exception as e:
            logger.error(f"Failed to cleanup old violations: {e}")
            await self.db.rollback()
            return 0
