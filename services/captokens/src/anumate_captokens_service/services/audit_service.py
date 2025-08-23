"""
Audit Service for CapTokens
===========================

Production-grade audit logging service for comprehensive token operation tracking.
"""

import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc
from sqlalchemy.sql import func

from ..models import TokenAuditLog
from anumate_logging import get_logger

logger = get_logger(__name__)


class AuditService:
    """
    Production-grade audit service for capability token operations.
    
    Features:
    - Immutable audit trails
    - Performance optimized queries
    - Compliance-ready structure
    - Correlation ID tracking
    - Error resilience
    """
    
    def __init__(self, db_session: AsyncSession):
        self.db = db_session
    
    async def log_operation(
        self,
        tenant_id: UUID,
        token_id: UUID,
        operation: str,
        status: str,
        request_data: Optional[Dict[str, Any]] = None,
        response_data: Optional[Dict[str, Any]] = None,
        error_details: Optional[Dict[str, Any]] = None,
        endpoint: Optional[str] = None,
        http_method: Optional[str] = None,
        client_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
        authenticated_subject: Optional[str] = None,
        authentication_method: Optional[str] = None,
        duration_ms: Optional[int] = None,
        correlation_id: Optional[UUID] = None,
        trace_id: Optional[str] = None,
        span_id: Optional[str] = None,
    ) -> UUID:
        """
        Log a token operation to the audit trail.
        
        Args:
            tenant_id: Tenant identifier
            token_id: Token identifier
            operation: Operation type (issue, verify, refresh, revoke, cleanup)
            status: Operation status (success, failure, warning)
            request_data: Sanitized request data
            response_data: Sanitized response data
            error_details: Error information if applicable
            endpoint: API endpoint accessed
            http_method: HTTP method used
            client_ip: Client IP address
            user_agent: Client user agent
            authenticated_subject: Authenticated subject
            authentication_method: Authentication method used
            duration_ms: Operation duration in milliseconds
            correlation_id: Request correlation ID
            trace_id: Distributed tracing trace ID
            span_id: Distributed tracing span ID
            
        Returns:
            Audit record ID
        """
        try:
            audit_record = TokenAuditLog(
                tenant_id=tenant_id,
                token_id=token_id,
                operation=operation,
                status=status,
                request_data=request_data or {},
                response_data=response_data or {},
                error_details=error_details,
                endpoint=endpoint,
                http_method=http_method,
                client_ip=client_ip,
                user_agent=user_agent,
                authenticated_subject=authenticated_subject,
                authentication_method=authentication_method,
                duration_ms=duration_ms,
                correlation_id=correlation_id or uuid.uuid4(),
                trace_id=trace_id,
                span_id=span_id,
            )
            
            self.db.add(audit_record)
            await self.db.commit()
            
            logger.info(
                "Audit log created",
                extra={
                    "audit_id": str(audit_record.audit_id),
                    "tenant_id": str(tenant_id),
                    "token_id": str(token_id),
                    "operation": operation,
                    "status": status,
                    "correlation_id": str(audit_record.correlation_id),
                }
            )
            
            return audit_record.audit_id
            
        except Exception as e:
            logger.error(
                "Failed to create audit log",
                extra={
                    "error": str(e),
                    "tenant_id": str(tenant_id),
                    "token_id": str(token_id),
                    "operation": operation,
                    "status": status,
                }
            )
            await self.db.rollback()
            raise
    
    async def get_token_audit_trail(
        self,
        tenant_id: UUID,
        token_id: Optional[UUID] = None,
        operation: Optional[str] = None,
        status: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[TokenAuditLog]:
        """
        Retrieve audit trail records with flexible filtering.
        
        Args:
            tenant_id: Tenant identifier
            token_id: Filter by specific token ID
            operation: Filter by operation type
            status: Filter by operation status
            start_date: Filter records after this date
            end_date: Filter records before this date
            limit: Maximum number of records to return
            offset: Number of records to skip
            
        Returns:
            List of audit log records
        """
        try:
            query = select(TokenAuditLog).where(TokenAuditLog.tenant_id == tenant_id)
            
            # Apply filters
            if token_id:
                query = query.where(TokenAuditLog.token_id == token_id)
            if operation:
                query = query.where(TokenAuditLog.operation == operation)
            if status:
                query = query.where(TokenAuditLog.status == status)
            if start_date:
                query = query.where(TokenAuditLog.created_at >= start_date)
            if end_date:
                query = query.where(TokenAuditLog.created_at <= end_date)
            
            # Order by most recent first
            query = query.order_by(desc(TokenAuditLog.created_at))
            
            # Apply pagination
            query = query.offset(offset).limit(limit)
            
            result = await self.db.execute(query)
            records = result.scalars().all()
            
            logger.info(
                "Retrieved audit trail",
                extra={
                    "tenant_id": str(tenant_id),
                    "token_id": str(token_id) if token_id else None,
                    "operation": operation,
                    "status": status,
                    "record_count": len(records),
                    "limit": limit,
                    "offset": offset,
                }
            )
            
            return list(records)
            
        except Exception as e:
            logger.error(
                "Failed to retrieve audit trail",
                extra={
                    "error": str(e),
                    "tenant_id": str(tenant_id),
                    "token_id": str(token_id) if token_id else None,
                }
            )
            raise
    
    async def get_audit_statistics(
        self,
        tenant_id: UUID,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Get audit statistics for monitoring and reporting.
        
        Args:
            tenant_id: Tenant identifier
            start_date: Statistics start date
            end_date: Statistics end date
            
        Returns:
            Dictionary containing audit statistics
        """
        try:
            base_query = select(TokenAuditLog).where(TokenAuditLog.tenant_id == tenant_id)
            
            if start_date:
                base_query = base_query.where(TokenAuditLog.created_at >= start_date)
            if end_date:
                base_query = base_query.where(TokenAuditLog.created_at <= end_date)
            
            # Count total operations
            total_result = await self.db.execute(
                select(func.count(TokenAuditLog.audit_id)).select_from(base_query.subquery())
            )
            total_operations = total_result.scalar() or 0
            
            # Count by operation type
            operation_stats_result = await self.db.execute(
                select(
                    TokenAuditLog.operation,
                    func.count(TokenAuditLog.audit_id).label('count')
                ).select_from(base_query.subquery()).group_by(TokenAuditLog.operation)
            )
            operation_stats = {row.operation: row.count for row in operation_stats_result}
            
            # Count by status
            status_stats_result = await self.db.execute(
                select(
                    TokenAuditLog.status,
                    func.count(TokenAuditLog.audit_id).label('count')
                ).select_from(base_query.subquery()).group_by(TokenAuditLog.status)
            )
            status_stats = {row.status: row.count for row in status_stats_result}
            
            # Average duration for successful operations
            avg_duration_result = await self.db.execute(
                select(func.avg(TokenAuditLog.duration_ms)).select_from(
                    base_query.where(
                        and_(
                            TokenAuditLog.status == 'success',
                            TokenAuditLog.duration_ms.isnot(None)
                        )
                    ).subquery()
                )
            )
            avg_duration = avg_duration_result.scalar() or 0
            
            statistics = {
                "total_operations": total_operations,
                "operations_by_type": operation_stats,
                "operations_by_status": status_stats,
                "average_duration_ms": round(float(avg_duration), 2),
                "period": {
                    "start_date": start_date.isoformat() if start_date else None,
                    "end_date": end_date.isoformat() if end_date else None,
                }
            }
            
            logger.info(
                "Retrieved audit statistics",
                extra={
                    "tenant_id": str(tenant_id),
                    "total_operations": total_operations,
                    "statistics": statistics,
                }
            )
            
            return statistics
            
        except Exception as e:
            logger.error(
                "Failed to retrieve audit statistics",
                extra={
                    "error": str(e),
                    "tenant_id": str(tenant_id),
                }
            )
            raise
