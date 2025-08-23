"""
Policy violation reporting and alerting system.

This module provides comprehensive reporting and alerting capabilities
for policy violations, including real-time notifications, audit trails,
and compliance reporting.
"""

import time
import json
import logging
from typing import Dict, Any, List, Optional, Callable, Set
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from collections import defaultdict, deque
import asyncio

try:
    from .middleware import PolicyViolation
    from .drift_detector import DriftAlert, DriftSeverity
except ImportError:
    from middleware import PolicyViolation
    from drift_detector import DriftAlert, DriftSeverity

logger = logging.getLogger(__name__)


class AlertChannel(Enum):
    """Alert delivery channels."""
    EMAIL = "email"
    SLACK = "slack"
    WEBHOOK = "webhook"
    SMS = "sms"
    PAGERDUTY = "pagerduty"
    LOG = "log"


class ReportFormat(Enum):
    """Report output formats."""
    JSON = "json"
    CSV = "csv"
    PDF = "pdf"
    HTML = "html"
    XLSX = "xlsx"


@dataclass
class AlertRule:
    """Configuration for violation alerting."""
    rule_id: str
    name: str
    description: str
    enabled: bool = True
    
    # Matching criteria
    policy_patterns: List[str] = field(default_factory=list)
    violation_types: List[str] = field(default_factory=list)
    severity_levels: List[str] = field(default_factory=list)
    tenant_ids: List[str] = field(default_factory=list)
    
    # Thresholds
    min_severity: str = "LOW"
    rate_limit: Optional[int] = None  # Max alerts per hour
    escalation_threshold: int = 5  # Escalate after N violations
    
    # Delivery
    channels: List[AlertChannel] = field(default_factory=list)
    recipients: List[str] = field(default_factory=list)
    
    # Timing
    quiet_hours: Optional[Dict[str, Any]] = None
    escalation_delay: int = 3600  # 1 hour


@dataclass
class ViolationReport:
    """Comprehensive violation report."""
    report_id: str
    title: str
    description: str
    generated_at: float
    period_start: float
    period_end: float
    
    # Summary statistics
    total_violations: int
    unique_policies: int
    unique_users: int
    unique_tenants: int
    
    # Breakdown by category
    violations_by_policy: Dict[str, int]
    violations_by_type: Dict[str, int]
    violations_by_severity: Dict[str, int]
    violations_by_tenant: Dict[str, int]
    violations_by_user: Dict[str, int]
    
    # Trends
    hourly_trend: List[Dict[str, Any]]
    daily_trend: List[Dict[str, Any]]
    
    # Top violators
    top_policies: List[Dict[str, Any]]
    top_users: List[Dict[str, Any]]
    top_resources: List[Dict[str, Any]]
    
    # Recommendations
    recommendations: List[str]
    
    # Raw data (optional)
    include_raw_data: bool = False
    violations: List[PolicyViolation] = field(default_factory=list)


class ViolationReporter:
    """Manages policy violation reporting and alerting."""
    
    def __init__(self, 
                 storage_backend: Optional[Callable] = None,
                 notification_backend: Optional[Callable] = None):
        """
        Initialize violation reporter.
        
        Args:
            storage_backend: Function to store violations persistently
            notification_backend: Function to send notifications
        """
        self.storage_backend = storage_backend
        self.notification_backend = notification_backend
        
        # In-memory storage for recent violations
        self.recent_violations: deque = deque(maxlen=10000)
        self.violation_index: Dict[str, List[PolicyViolation]] = defaultdict(list)
        
        # Alert configuration
        self.alert_rules: Dict[str, AlertRule] = {}
        self.alert_history: deque = deque(maxlen=1000)
        self.rate_limits: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
        
        # Notification handlers
        self.notification_handlers: Dict[AlertChannel, Callable] = {}
        
        # Report templates
        self.report_templates: Dict[str, Dict[str, Any]] = {}
        
        # Statistics
        self.stats = {
            'total_violations': 0,
            'total_alerts_sent': 0,
            'last_violation_time': 0,
            'last_alert_time': 0
        }
    
    def record_violation(self, violation: PolicyViolation):
        """Record a policy violation for reporting and alerting."""
        # Store violation
        self.recent_violations.append(violation)
        self.violation_index[violation.policy_name].append(violation)
        
        # Update statistics
        self.stats['total_violations'] += 1
        self.stats['last_violation_time'] = violation.timestamp
        
        # Persist to storage backend if available
        if self.storage_backend:
            try:
                self.storage_backend(violation)
            except Exception as e:
                logger.error(f"Failed to store violation: {e}")
        
        # Check alert rules
        try:
            asyncio.create_task(self._process_violation_alerts(violation))
        except RuntimeError:
            # No event loop running, process synchronously for testing
            import asyncio
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self._process_violation_alerts(violation))
                loop.close()
            except Exception as e:
                logger.error(f"Error processing violation alerts: {e}")
        
        # Log violation
        logger.warning(
            f"Policy violation recorded: {violation.violation_type}",
            extra={
                'violation_id': violation.violation_id,
                'policy_name': violation.policy_name,
                'severity': violation.severity,
                'user_id': violation.user_id,
                'tenant_id': violation.tenant_id
            }
        )
    
    async def _process_violation_alerts(self, violation: PolicyViolation):
        """Process violation against alert rules."""
        for rule_id, rule in self.alert_rules.items():
            if not rule.enabled:
                continue
            
            # Check if violation matches rule criteria
            if not self._violation_matches_rule(violation, rule):
                continue
            
            # Check rate limiting
            if self._is_rate_limited(rule_id, rule):
                continue
            
            # Check quiet hours
            if self._is_quiet_hours(rule):
                continue
            
            # Check escalation threshold
            if self._should_escalate(violation, rule):
                await self._send_escalated_alert(violation, rule)
            else:
                await self._send_standard_alert(violation, rule)
    
    def _violation_matches_rule(self, violation: PolicyViolation, rule: AlertRule) -> bool:
        """Check if violation matches alert rule criteria."""
        # Check policy patterns
        if rule.policy_patterns:
            policy_match = any(
                pattern in violation.policy_name or violation.policy_name.startswith(pattern.rstrip('*'))
                for pattern in rule.policy_patterns
            )
            if not policy_match:
                return False
        
        # Check violation types
        if rule.violation_types and violation.violation_type not in rule.violation_types:
            return False
        
        # Check severity levels
        if rule.severity_levels and violation.severity not in rule.severity_levels:
            return False
        
        # Check tenant IDs
        if rule.tenant_ids and violation.tenant_id not in rule.tenant_ids:
            return False
        
        # Check minimum severity
        severity_order = {'LOW': 1, 'MEDIUM': 2, 'HIGH': 3, 'CRITICAL': 4}
        min_severity_level = severity_order.get(rule.min_severity, 1)
        violation_severity_level = severity_order.get(violation.severity, 1)
        
        if violation_severity_level < min_severity_level:
            return False
        
        return True
    
    def _is_rate_limited(self, rule_id: str, rule: AlertRule) -> bool:
        """Check if alert rule is rate limited."""
        if not rule.rate_limit:
            return False
        
        current_time = time.time()
        hour_ago = current_time - 3600
        
        # Count alerts in the last hour
        recent_alerts = [
            alert_time for alert_time in self.rate_limits[rule_id]
            if alert_time >= hour_ago
        ]
        
        if len(recent_alerts) >= rule.rate_limit:
            logger.debug(f"Alert rule {rule_id} is rate limited")
            return True
        
        return False
    
    def _is_quiet_hours(self, rule: AlertRule) -> bool:
        """Check if current time is within quiet hours."""
        if not rule.quiet_hours:
            return False
        
        now = datetime.now()
        start_hour = rule.quiet_hours.get('start_hour', 0)
        end_hour = rule.quiet_hours.get('end_hour', 0)
        
        if start_hour <= end_hour:
            # Same day quiet hours (e.g., 22:00 to 06:00 next day)
            return start_hour <= now.hour < end_hour
        else:
            # Overnight quiet hours (e.g., 22:00 to 06:00 next day)
            return now.hour >= start_hour or now.hour < end_hour
    
    def _should_escalate(self, violation: PolicyViolation, rule: AlertRule) -> bool:
        """Check if violation should trigger escalation."""
        if not rule.escalation_threshold:
            return False
        
        # Count recent violations for the same policy/user combination
        recent_cutoff = time.time() - rule.escalation_delay
        recent_violations = [
            v for v in self.violation_index[violation.policy_name]
            if (v.timestamp >= recent_cutoff and 
                v.user_id == violation.user_id and
                v.violation_type == violation.violation_type)
        ]
        
        return len(recent_violations) >= rule.escalation_threshold
    
    async def _send_standard_alert(self, violation: PolicyViolation, rule: AlertRule):
        """Send standard violation alert."""
        alert_data = {
            'type': 'policy_violation',
            'severity': violation.severity,
            'violation_id': violation.violation_id,
            'policy_name': violation.policy_name,
            'rule_name': violation.rule_name,
            'violation_type': violation.violation_type,
            'message': violation.message,
            'user_id': violation.user_id,
            'tenant_id': violation.tenant_id,
            'resource_path': violation.resource_path,
            'timestamp': violation.timestamp,
            'context': violation.context,
            'alert_rule': rule.name
        }
        
        await self._send_alert(alert_data, rule)
    
    async def _send_escalated_alert(self, violation: PolicyViolation, rule: AlertRule):
        """Send escalated violation alert."""
        alert_data = {
            'type': 'policy_violation_escalated',
            'severity': 'CRITICAL',
            'violation_id': violation.violation_id,
            'policy_name': violation.policy_name,
            'violation_type': violation.violation_type,
            'message': f"ESCALATED: {violation.message}",
            'user_id': violation.user_id,
            'tenant_id': violation.tenant_id,
            'resource_path': violation.resource_path,
            'timestamp': violation.timestamp,
            'escalation_reason': f"Multiple violations ({rule.escalation_threshold}) within {rule.escalation_delay}s",
            'alert_rule': rule.name
        }
        
        await self._send_alert(alert_data, rule)
    
    async def _send_alert(self, alert_data: Dict[str, Any], rule: AlertRule):
        """Send alert through configured channels."""
        alert_id = f"alert_{int(time.time())}_{hash(str(alert_data))}"
        
        # Record alert in rate limiting
        self.rate_limits[rule.rule_id].append(time.time())
        
        # Send through each configured channel
        for channel in rule.channels:
            try:
                handler = self.notification_handlers.get(channel)
                if handler:
                    await handler(alert_data, rule.recipients)
                else:
                    logger.warning(f"No handler configured for channel: {channel}")
            
            except Exception as e:
                logger.error(f"Failed to send alert via {channel}: {e}")
        
        # Record alert in history
        self.alert_history.append({
            'alert_id': alert_id,
            'rule_id': rule.rule_id,
            'timestamp': time.time(),
            'alert_data': alert_data
        })
        
        # Update statistics
        self.stats['total_alerts_sent'] += 1
        self.stats['last_alert_time'] = time.time()
        
        logger.info(f"Alert sent: {alert_id} via {len(rule.channels)} channels")
    
    def add_alert_rule(self, rule: AlertRule):
        """Add an alert rule."""
        self.alert_rules[rule.rule_id] = rule
        logger.info(f"Added alert rule: {rule.name}")
    
    def remove_alert_rule(self, rule_id: str) -> bool:
        """Remove an alert rule."""
        if rule_id in self.alert_rules:
            del self.alert_rules[rule_id]
            logger.info(f"Removed alert rule: {rule_id}")
            return True
        return False
    
    def add_notification_handler(self, channel: AlertChannel, handler: Callable):
        """Add a notification handler for a channel."""
        self.notification_handlers[channel] = handler
        logger.info(f"Added notification handler for {channel}")
    
    def generate_violation_report(self,
                                 start_time: float,
                                 end_time: float,
                                 title: str = "Policy Violation Report",
                                 include_raw_data: bool = False,
                                 filters: Optional[Dict[str, Any]] = None) -> ViolationReport:
        """Generate a comprehensive violation report."""
        import uuid
        
        # Filter violations by time range
        violations = [
            v for v in self.recent_violations
            if start_time <= v.timestamp <= end_time
        ]
        
        # Apply additional filters
        if filters:
            violations = self._apply_filters(violations, filters)
        
        if not violations:
            return ViolationReport(
                report_id=str(uuid.uuid4()),
                title=title,
                description="No violations found in the specified period",
                generated_at=time.time(),
                period_start=start_time,
                period_end=end_time,
                total_violations=0,
                unique_policies=0,
                unique_users=0,
                unique_tenants=0,
                violations_by_policy={},
                violations_by_type={},
                violations_by_severity={},
                violations_by_tenant={},
                violations_by_user={},
                hourly_trend=[],
                daily_trend=[],
                top_policies=[],
                top_users=[],
                top_resources=[],
                recommendations=[]
            )
        
        # Calculate summary statistics
        unique_policies = len(set(v.policy_name for v in violations))
        unique_users = len(set(v.user_id for v in violations if v.user_id))
        unique_tenants = len(set(v.tenant_id for v in violations if v.tenant_id))
        
        # Breakdown by categories
        violations_by_policy = defaultdict(int)
        violations_by_type = defaultdict(int)
        violations_by_severity = defaultdict(int)
        violations_by_tenant = defaultdict(int)
        violations_by_user = defaultdict(int)
        
        for violation in violations:
            violations_by_policy[violation.policy_name] += 1
            violations_by_type[violation.violation_type] += 1
            violations_by_severity[violation.severity] += 1
            if violation.tenant_id:
                violations_by_tenant[violation.tenant_id] += 1
            if violation.user_id:
                violations_by_user[violation.user_id] += 1
        
        # Generate trends
        hourly_trend = self._generate_hourly_trend(violations, start_time, end_time)
        daily_trend = self._generate_daily_trend(violations, start_time, end_time)
        
        # Top violators
        top_policies = sorted(violations_by_policy.items(), key=lambda x: x[1], reverse=True)[:10]
        top_users = sorted(violations_by_user.items(), key=lambda x: x[1], reverse=True)[:10]
        
        # Top resources
        resource_counts = defaultdict(int)
        for violation in violations:
            resource_counts[violation.resource_path] += 1
        top_resources = sorted(resource_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        
        # Generate recommendations
        recommendations = self._generate_recommendations(violations, violations_by_policy, violations_by_user)
        
        return ViolationReport(
            report_id=str(uuid.uuid4()),
            title=title,
            description=f"Policy violation report for period {datetime.fromtimestamp(start_time)} to {datetime.fromtimestamp(end_time)}",
            generated_at=time.time(),
            period_start=start_time,
            period_end=end_time,
            total_violations=len(violations),
            unique_policies=unique_policies,
            unique_users=unique_users,
            unique_tenants=unique_tenants,
            violations_by_policy=dict(violations_by_policy),
            violations_by_type=dict(violations_by_type),
            violations_by_severity=dict(violations_by_severity),
            violations_by_tenant=dict(violations_by_tenant),
            violations_by_user=dict(violations_by_user),
            hourly_trend=hourly_trend,
            daily_trend=daily_trend,
            top_policies=[{'policy': p, 'count': c} for p, c in top_policies],
            top_users=[{'user_id': u, 'count': c} for u, c in top_users],
            top_resources=[{'resource': r, 'count': c} for r, c in top_resources],
            recommendations=recommendations,
            include_raw_data=include_raw_data,
            violations=violations if include_raw_data else []
        )
    
    def _apply_filters(self, violations: List[PolicyViolation], filters: Dict[str, Any]) -> List[PolicyViolation]:
        """Apply filters to violation list."""
        filtered = violations
        
        if 'policy_names' in filters:
            policy_names = set(filters['policy_names'])
            filtered = [v for v in filtered if v.policy_name in policy_names]
        
        if 'violation_types' in filters:
            violation_types = set(filters['violation_types'])
            filtered = [v for v in filtered if v.violation_type in violation_types]
        
        if 'severity_levels' in filters:
            severity_levels = set(filters['severity_levels'])
            filtered = [v for v in filtered if v.severity in severity_levels]
        
        if 'user_ids' in filters:
            user_ids = set(filters['user_ids'])
            filtered = [v for v in filtered if v.user_id in user_ids]
        
        if 'tenant_ids' in filters:
            tenant_ids = set(filters['tenant_ids'])
            filtered = [v for v in filtered if v.tenant_id in tenant_ids]
        
        return filtered
    
    def _generate_hourly_trend(self, violations: List[PolicyViolation], start_time: float, end_time: float) -> List[Dict[str, Any]]:
        """Generate hourly trend data."""
        hourly_counts = defaultdict(int)
        
        for violation in violations:
            hour = int(violation.timestamp // 3600) * 3600  # Round to hour
            hourly_counts[hour] += 1
        
        # Fill in missing hours with zero counts
        trend = []
        current_hour = int(start_time // 3600) * 3600
        end_hour = int(end_time // 3600) * 3600
        
        while current_hour <= end_hour:
            trend.append({
                'timestamp': current_hour,
                'hour': datetime.fromtimestamp(current_hour).strftime('%Y-%m-%d %H:00'),
                'count': hourly_counts[current_hour]
            })
            current_hour += 3600
        
        return trend
    
    def _generate_daily_trend(self, violations: List[PolicyViolation], start_time: float, end_time: float) -> List[Dict[str, Any]]:
        """Generate daily trend data."""
        daily_counts = defaultdict(int)
        
        for violation in violations:
            day = int(violation.timestamp // 86400) * 86400  # Round to day
            daily_counts[day] += 1
        
        # Fill in missing days with zero counts
        trend = []
        current_day = int(start_time // 86400) * 86400
        end_day = int(end_time // 86400) * 86400
        
        while current_day <= end_day:
            trend.append({
                'timestamp': current_day,
                'date': datetime.fromtimestamp(current_day).strftime('%Y-%m-%d'),
                'count': daily_counts[current_day]
            })
            current_day += 86400
        
        return trend
    
    def _generate_recommendations(self, 
                                violations: List[PolicyViolation],
                                violations_by_policy: Dict[str, int],
                                violations_by_user: Dict[str, int]) -> List[str]:
        """Generate recommendations based on violation patterns."""
        recommendations = []
        
        # High violation policies
        if violations_by_policy:
            top_policy, top_count = max(violations_by_policy.items(), key=lambda x: x[1])
            if top_count > len(violations) * 0.3:  # More than 30% of violations
                recommendations.append(
                    f"Policy '{top_policy}' accounts for {top_count} violations ({top_count/len(violations)*100:.1f}%). "
                    "Consider reviewing policy rules or user training."
                )
        
        # Repeat violators
        repeat_violators = [user for user, count in violations_by_user.items() if count >= 5]
        if repeat_violators:
            recommendations.append(
                f"{len(repeat_violators)} users have 5+ violations. "
                "Consider additional training or access review for repeat violators."
            )
        
        # High severity violations
        critical_violations = [v for v in violations if v.severity == 'CRITICAL']
        if critical_violations:
            recommendations.append(
                f"{len(critical_violations)} critical violations detected. "
                "Immediate investigation and remediation recommended."
            )
        
        # Time-based patterns
        violation_hours = [datetime.fromtimestamp(v.timestamp).hour for v in violations]
        if violation_hours:
            from collections import Counter
            hour_counts = Counter(violation_hours)
            peak_hour, peak_count = hour_counts.most_common(1)[0]
            if peak_count > len(violations) * 0.2:  # More than 20% in one hour
                recommendations.append(
                    f"Peak violations occur at {peak_hour}:00 ({peak_count} violations). "
                    "Consider time-based policy adjustments or monitoring."
                )
        
        return recommendations
    
    def export_report(self, report: ViolationReport, format: ReportFormat, output_path: str):
        """Export report to specified format."""
        if format == ReportFormat.JSON:
            with open(output_path, 'w') as f:
                json.dump(asdict(report), f, indent=2, default=str)
        
        elif format == ReportFormat.CSV:
            import csv
            with open(output_path, 'w', newline='') as f:
                writer = csv.writer(f)
                
                # Write summary
                writer.writerow(['Report Summary'])
                writer.writerow(['Title', report.title])
                writer.writerow(['Generated At', datetime.fromtimestamp(report.generated_at)])
                writer.writerow(['Period', f"{datetime.fromtimestamp(report.period_start)} to {datetime.fromtimestamp(report.period_end)}"])
                writer.writerow(['Total Violations', report.total_violations])
                writer.writerow([])
                
                # Write violations by policy
                writer.writerow(['Violations by Policy'])
                writer.writerow(['Policy Name', 'Count'])
                for policy, count in report.violations_by_policy.items():
                    writer.writerow([policy, count])
        
        else:
            raise ValueError(f"Unsupported export format: {format}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get violation reporting statistics."""
        return {
            **self.stats,
            'active_alert_rules': len(self.alert_rules),
            'recent_violations_count': len(self.recent_violations),
            'alert_history_count': len(self.alert_history)
        }
    
    def clear_old_data(self, retention_hours: int = 24):
        """Clear old violation data to manage memory usage."""
        cutoff_time = time.time() - (retention_hours * 3600)
        
        # Clear old violations
        self.recent_violations = deque(
            [v for v in self.recent_violations if v.timestamp >= cutoff_time],
            maxlen=10000
        )
        
        # Clear old violation index
        for policy_name in list(self.violation_index.keys()):
            self.violation_index[policy_name] = [
                v for v in self.violation_index[policy_name] 
                if v.timestamp >= cutoff_time
            ]
            
            # Remove empty entries
            if not self.violation_index[policy_name]:
                del self.violation_index[policy_name]
        
        # Clear old alert history
        self.alert_history = deque(
            [a for a in self.alert_history if a['timestamp'] >= cutoff_time],
            maxlen=1000
        )
        
        logger.info(f"Cleared violation data older than {retention_hours} hours")


# Default notification handlers

async def log_notification_handler(alert_data: Dict[str, Any], recipients: List[str]):
    """Default log-based notification handler."""
    logger.info(f"ALERT: {alert_data['type']} - {alert_data.get('message', 'No message')}")


async def webhook_notification_handler(alert_data: Dict[str, Any], recipients: List[str]):
    """Webhook notification handler."""
    import aiohttp
    
    for webhook_url in recipients:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=alert_data) as response:
                    if response.status == 200:
                        logger.info(f"Webhook alert sent to {webhook_url}")
                    else:
                        logger.error(f"Webhook alert failed: {response.status}")
        except Exception as e:
            logger.error(f"Webhook notification error: {e}")


# Example alert rules

def create_default_alert_rules() -> List[AlertRule]:
    """Create default alert rules for common scenarios."""
    return [
        AlertRule(
            rule_id="critical_violations",
            name="Critical Policy Violations",
            description="Alert on all critical policy violations",
            severity_levels=["CRITICAL"],
            channels=[AlertChannel.LOG, AlertChannel.WEBHOOK],
            rate_limit=10
        ),
        
        AlertRule(
            rule_id="pii_violations",
            name="PII Policy Violations",
            description="Alert on PII-related policy violations",
            policy_patterns=["*pii*", "*privacy*"],
            channels=[AlertChannel.LOG],
            escalation_threshold=3,
            rate_limit=5
        ),
        
        AlertRule(
            rule_id="repeat_violators",
            name="Repeat Violators",
            description="Alert on users with multiple violations",
            min_severity="MEDIUM",
            escalation_threshold=5,
            channels=[AlertChannel.LOG, AlertChannel.WEBHOOK]
        )
    ]