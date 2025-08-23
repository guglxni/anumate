"""
Usage Tracker Service
====================

Service for tracking capability token usage patterns and analytics.
Provides insights into token usage for security monitoring and optimization.
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc, func

from .models import TokenUsageTracking

logger = logging.getLogger(__name__)


@dataclass
class UsageContext:
    """Context information for token usage tracking."""
    endpoint: Optional[str] = None
    http_method: Optional[str] = None
    client_ip: Optional[str] = None
    user_agent: Optional[str] = None
    response_time_ms: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None


class UsageTracker:
    """
    Service for tracking and analyzing capability token usage.
    
    Features:
    - Detailed usage analytics
    - Performance monitoring
    - Pattern detection for anomaly detection
    - Usage optimization insights
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def track_token_usage(
        self,
        tenant_id: str,
        token_id: str,
        action_performed: str,
        capabilities_used: List[str],
        success: bool = True,
        context: Optional[UsageContext] = None
    ) -> str:
        """
        Track successful token usage.
        
        Args:
            tenant_id: Tenant ID
            token_id: Token ID
            action_performed: Action that was performed
            capabilities_used: List of capabilities that were used
            success: Whether the action was successful
            context: Additional context information
            
        Returns:
            Usage tracking ID
        """
        try:
            context = context or UsageContext()
            
            # Create usage tracking record
            usage = TokenUsageTracking(
                usage_id=uuid.uuid4(),
                tenant_id=tenant_id,
                token_id=token_id,
                action_performed=action_performed,
                capabilities_used=capabilities_used,
                success=success,
                endpoint=context.endpoint,
                http_method=context.http_method,
                client_ip=context.client_ip,
                user_agent=context.user_agent,
                response_time_ms=context.response_time_ms,
                extra_metadata=context.metadata or {}
            )
            
            self.db.add(usage)
            await self.db.commit()
            
            logger.debug(
                f"Token usage tracked: {action_performed}",
                extra={
                    "usage_id": str(usage.usage_id),
                    "tenant_id": tenant_id,
                    "token_id": token_id,
                    "action": action_performed,
                    "capabilities": capabilities_used,
                    "success": success
                }
            )
            
            return str(usage.usage_id)
            
        except Exception as e:
            logger.error(f"Failed to track token usage: {e}", exc_info=True)
            await self.db.rollback()
            raise
    
    async def get_usage_stats(
        self,
        tenant_id: str,
        hours: int = 24,
        token_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get usage statistics for a tenant or specific token.
        
        Args:
            tenant_id: Tenant ID
            hours: Number of hours to analyze
            token_id: Optional token ID to filter by
            
        Returns:
            Usage statistics
        """
        try:
            since = datetime.utcnow() - timedelta(hours=hours)
            
            base_filter = and_(
                TokenUsageTracking.tenant_id == tenant_id,
                TokenUsageTracking.created_at >= since
            )
            
            if token_id:
                base_filter = and_(base_filter, TokenUsageTracking.token_id == token_id)
            
            # Total usage count
            total_query = select(func.count(TokenUsageTracking.usage_id)).where(base_filter)
            total_result = await self.db.execute(total_query)
            total_usage = total_result.scalar() or 0
            
            # Successful vs failed usage
            success_query = select(
                TokenUsageTracking.success,
                func.count(TokenUsageTracking.usage_id)
            ).where(base_filter).group_by(TokenUsageTracking.success)
            
            success_result = await self.db.execute(success_query)
            success_stats = dict(success_result.fetchall())
            
            # Usage by action
            action_query = select(
                TokenUsageTracking.action_performed,
                func.count(TokenUsageTracking.usage_id)
            ).where(base_filter).group_by(TokenUsageTracking.action_performed).limit(10)
            
            action_result = await self.db.execute(action_query)
            usage_by_action = dict(action_result.fetchall())
            
            # Usage by capability
            # Note: This is a simplified aggregation; in practice you'd need more complex JSON handling
            capability_query = select(
                func.count(TokenUsageTracking.usage_id)
            ).where(base_filter)
            
            # Average response time
            response_time_query = select(
                func.avg(TokenUsageTracking.response_time_ms)
            ).where(
                and_(
                    base_filter,
                    TokenUsageTracking.response_time_ms.isnot(None)
                )
            )
            
            response_time_result = await self.db.execute(response_time_query)
            avg_response_time = response_time_result.scalar()
            
            # Usage by hour (for trend analysis)
            hourly_query = select(
                func.date_trunc('hour', TokenUsageTracking.created_at).label('hour'),
                func.count(TokenUsageTracking.usage_id)
            ).where(base_filter).group_by('hour').order_by('hour')
            
            hourly_result = await self.db.execute(hourly_query)
            hourly_usage = [(row[0].isoformat(), row[1]) for row in hourly_result.fetchall()]
            
            # Most active tokens
            token_query = select(
                TokenUsageTracking.token_id,
                func.count(TokenUsageTracking.usage_id)
            ).where(base_filter).group_by(TokenUsageTracking.token_id).limit(10)
            
            token_result = await self.db.execute(token_query)
            most_active_tokens = [(str(row[0]), row[1]) for row in token_result.fetchall()]
            
            return {
                "period_hours": hours,
                "total_usage": total_usage,
                "success_rate": success_stats.get(True, 0) / max(total_usage, 1) * 100,
                "successful_usage": success_stats.get(True, 0),
                "failed_usage": success_stats.get(False, 0),
                "usage_by_action": usage_by_action,
                "avg_response_time_ms": float(avg_response_time) if avg_response_time else None,
                "hourly_usage": hourly_usage,
                "most_active_tokens": most_active_tokens,
                "generated_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to get usage stats: {e}")
            return {}
    
    async def get_token_usage_history(
        self,
        tenant_id: str,
        token_id: str,
        limit: int = 100,
        offset: int = 0
    ) -> List[TokenUsageTracking]:
        """
        Get usage history for a specific token.
        
        Args:
            tenant_id: Tenant ID
            token_id: Token ID
            limit: Maximum number of results
            offset: Offset for pagination
            
        Returns:
            List of usage tracking records
        """
        try:
            query = select(TokenUsageTracking).where(
                and_(
                    TokenUsageTracking.tenant_id == tenant_id,
                    TokenUsageTracking.token_id == token_id
                )
            ).order_by(desc(TokenUsageTracking.created_at)).limit(limit).offset(offset)
            
            result = await self.db.execute(query)
            return result.scalars().all()
            
        except Exception as e:
            logger.error(f"Failed to get token usage history: {e}")
            return []
    
    async def detect_usage_anomalies(
        self,
        tenant_id: str,
        hours: int = 24
    ) -> List[Dict[str, Any]]:
        """
        Detect anomalous usage patterns.
        
        Args:
            tenant_id: Tenant ID
            hours: Number of hours to analyze
            
        Returns:
            List of detected anomalies
        """
        try:
            anomalies = []
            since = datetime.utcnow() - timedelta(hours=hours)
            
            # High failure rate tokens
            failure_query = select(
                TokenUsageTracking.token_id,
                func.count(TokenUsageTracking.usage_id).label('total'),
                func.sum(func.cast(~TokenUsageTracking.success, func.INTEGER)).label('failures')
            ).where(
                and_(
                    TokenUsageTracking.tenant_id == tenant_id,
                    TokenUsageTracking.created_at >= since
                )
            ).group_by(TokenUsageTracking.token_id).having(
                func.count(TokenUsageTracking.usage_id) > 10
            )
            
            failure_result = await self.db.execute(failure_query)
            for row in failure_result.fetchall():
                token_id, total, failures = row
                failure_rate = (failures or 0) / total
                if failure_rate > 0.5:  # More than 50% failure rate
                    anomalies.append({
                        "type": "high_failure_rate",
                        "token_id": str(token_id),
                        "failure_rate": failure_rate,
                        "total_attempts": total,
                        "severity": "high" if failure_rate > 0.8 else "medium"
                    })
            
            # Unusually high usage frequency
            frequency_query = select(
                TokenUsageTracking.token_id,
                func.count(TokenUsageTracking.usage_id).label('usage_count')
            ).where(
                and_(
                    TokenUsageTracking.tenant_id == tenant_id,
                    TokenUsageTracking.created_at >= since
                )
            ).group_by(TokenUsageTracking.token_id)
            
            frequency_result = await self.db.execute(frequency_query)
            usage_counts = [row[1] for row in frequency_result.fetchall()]
            
            if usage_counts:
                avg_usage = sum(usage_counts) / len(usage_counts)
                threshold = avg_usage * 3  # 3x average usage
                
                for row in frequency_result.fetchall():
                    token_id, usage_count = row
                    if usage_count > threshold:
                        anomalies.append({
                            "type": "unusual_high_frequency",
                            "token_id": str(token_id),
                            "usage_count": usage_count,
                            "average_usage": avg_usage,
                            "severity": "medium"
                        })
            
            # Tokens with unusual response times
            response_time_query = select(
                TokenUsageTracking.token_id,
                func.avg(TokenUsageTracking.response_time_ms).label('avg_response_time')
            ).where(
                and_(
                    TokenUsageTracking.tenant_id == tenant_id,
                    TokenUsageTracking.created_at >= since,
                    TokenUsageTracking.response_time_ms.isnot(None)
                )
            ).group_by(TokenUsageTracking.token_id)
            
            response_time_result = await self.db.execute(response_time_query)
            response_times = [row[1] for row in response_time_result.fetchall()]
            
            if response_times:
                avg_response_time = sum(response_times) / len(response_times)
                slow_threshold = avg_response_time * 2  # 2x average response time
                
                for row in response_time_result.fetchall():
                    token_id, token_avg_response = row
                    if token_avg_response > slow_threshold:
                        anomalies.append({
                            "type": "slow_response_time",
                            "token_id": str(token_id),
                            "avg_response_time_ms": float(token_avg_response),
                            "baseline_avg_ms": avg_response_time,
                            "severity": "low"
                        })
            
            logger.info(f"Detected {len(anomalies)} usage anomalies for tenant {tenant_id}")
            return anomalies
            
        except Exception as e:
            logger.error(f"Failed to detect usage anomalies: {e}")
            return []
    
    async def get_capability_usage_insights(
        self,
        tenant_id: str,
        hours: int = 168  # 1 week default
    ) -> Dict[str, Any]:
        """
        Get insights about capability usage patterns.
        
        Args:
            tenant_id: Tenant ID
            hours: Number of hours to analyze
            
        Returns:
            Capability usage insights
        """
        try:
            since = datetime.utcnow() - timedelta(hours=hours)
            
            # Get all usage records for analysis
            query = select(TokenUsageTracking).where(
                and_(
                    TokenUsageTracking.tenant_id == tenant_id,
                    TokenUsageTracking.created_at >= since
                )
            )
            
            result = await self.db.execute(query)
            usage_records = result.scalars().all()
            
            if not usage_records:
                return {"message": "No usage data available for analysis"}
            
            # Analyze capability usage patterns
            capability_usage = {}
            capability_actions = {}
            unused_capabilities = set()
            
            for record in usage_records:
                for capability in record.capabilities_used:
                    # Track capability frequency
                    capability_usage[capability] = capability_usage.get(capability, 0) + 1
                    
                    # Track actions per capability
                    if capability not in capability_actions:
                        capability_actions[capability] = set()
                    capability_actions[capability].add(record.action_performed)
            
            # Convert sets to lists for JSON serialization
            capability_actions = {
                cap: list(actions) for cap, actions in capability_actions.items()
            }
            
            # Sort capabilities by usage
            sorted_capabilities = sorted(
                capability_usage.items(), key=lambda x: x[1], reverse=True
            )
            
            return {
                "period_hours": hours,
                "total_records_analyzed": len(usage_records),
                "capability_usage_frequency": dict(sorted_capabilities),
                "capability_action_mapping": capability_actions,
                "most_used_capability": sorted_capabilities[0][0] if sorted_capabilities else None,
                "least_used_capability": sorted_capabilities[-1][0] if sorted_capabilities else None,
                "unique_capabilities_used": len(capability_usage),
                "generated_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to get capability usage insights: {e}")
            return {}
    
    async def cleanup_old_usage_records(self, tenant_id: str, days: int = 30) -> int:
        """
        Clean up old usage tracking records.
        
        Args:
            tenant_id: Tenant ID
            days: Number of days to retain
            
        Returns:
            Number of records cleaned up
        """
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            # Delete old usage records
            delete_query = select(TokenUsageTracking).where(
                and_(
                    TokenUsageTracking.tenant_id == tenant_id,
                    TokenUsageTracking.created_at < cutoff_date
                )
            )
            
            result = await self.db.execute(delete_query)
            records_to_delete = result.scalars().all()
            
            for record in records_to_delete:
                await self.db.delete(record)
            
            await self.db.commit()
            
            count = len(records_to_delete)
            logger.info(f"Cleaned up {count} old usage tracking records for tenant {tenant_id}")
            
            return count
            
        except Exception as e:
            logger.error(f"Failed to cleanup old usage records: {e}")
            await self.db.rollback()
            return 0
