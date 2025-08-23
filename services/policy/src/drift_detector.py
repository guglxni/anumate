"""
Policy drift detection for compliance monitoring.

This module provides capabilities to detect when system behavior
drifts from defined policies, enabling proactive compliance monitoring.
"""

import time
import json
import logging
from typing import Dict, Any, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict, deque
from enum import Enum

try:
    from .engine import PolicyEngine
    from .evaluator import EvaluationResult
    from .middleware import PolicyViolation
except ImportError:
    from engine import PolicyEngine
    from evaluator import EvaluationResult
    from middleware import PolicyViolation

logger = logging.getLogger(__name__)


class DriftType(Enum):
    """Types of policy drift."""
    COMPLIANCE_DEGRADATION = "compliance_degradation"
    POLICY_BYPASS = "policy_bypass"
    UNEXPECTED_BEHAVIOR = "unexpected_behavior"
    PERFORMANCE_DRIFT = "performance_drift"
    COVERAGE_GAP = "coverage_gap"


class DriftSeverity(Enum):
    """Severity levels for drift detection."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class DriftMetric:
    """Represents a drift detection metric."""
    name: str
    current_value: float
    baseline_value: float
    threshold: float
    drift_percentage: float
    measurement_time: float
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DriftAlert:
    """Represents a drift detection alert."""
    alert_id: str
    drift_type: DriftType
    severity: DriftSeverity
    policy_name: str
    metric_name: str
    description: str
    current_value: float
    expected_value: float
    drift_percentage: float
    detection_time: float
    tenant_id: Optional[str] = None
    affected_resources: List[str] = field(default_factory=list)
    remediation_suggestions: List[str] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ComplianceBaseline:
    """Baseline metrics for compliance monitoring."""
    policy_name: str
    success_rate: float
    average_evaluation_time: float
    rule_coverage: Dict[str, int]
    violation_rate: float
    last_updated: float
    sample_count: int


class PolicyDriftDetector:
    """Detects drift in policy compliance and behavior."""
    
    def __init__(self, 
                 engine: PolicyEngine,
                 baseline_window: int = 3600,  # 1 hour
                 detection_window: int = 300,  # 5 minutes
                 drift_threshold: float = 0.15):  # 15% drift threshold
        """
        Initialize drift detector.
        
        Args:
            engine: Policy engine for evaluation
            baseline_window: Time window for establishing baselines (seconds)
            detection_window: Time window for drift detection (seconds)
            drift_threshold: Threshold for detecting significant drift (percentage)
        """
        self.engine = engine
        self.baseline_window = baseline_window
        self.detection_window = detection_window
        self.drift_threshold = drift_threshold
        
        # Metrics storage
        self.evaluation_metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self.violation_metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self.performance_metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        
        # Baselines
        self.compliance_baselines: Dict[str, ComplianceBaseline] = {}
        self.baseline_update_interval = 3600  # Update baselines every hour
        self.last_baseline_update = 0
        
        # Drift alerts
        self.active_alerts: Dict[str, DriftAlert] = {}
        self.alert_handlers: List[callable] = []
        
        # Configuration
        self.drift_thresholds = {
            DriftType.COMPLIANCE_DEGRADATION: 0.10,  # 10%
            DriftType.POLICY_BYPASS: 0.05,  # 5%
            DriftType.UNEXPECTED_BEHAVIOR: 0.20,  # 20%
            DriftType.PERFORMANCE_DRIFT: 0.25,  # 25%
            DriftType.COVERAGE_GAP: 0.15  # 15%
        }
    
    def record_evaluation(self, 
                         policy_name: str,
                         evaluation_result: EvaluationResult,
                         evaluation_time: float,
                         context: Dict[str, Any]):
        """Record a policy evaluation for drift analysis."""
        timestamp = time.time()
        
        # Record evaluation metrics
        self.evaluation_metrics[policy_name].append({
            'timestamp': timestamp,
            'allowed': evaluation_result.allowed,
            'matched_rules': evaluation_result.matched_rules,
            'action_count': len(evaluation_result.actions),
            'evaluation_time': evaluation_time,
            'context': context
        })
        
        # Record performance metrics
        self.performance_metrics[policy_name].append({
            'timestamp': timestamp,
            'evaluation_time': evaluation_time,
            'rule_count': len(evaluation_result.matched_rules)
        })
        
        # Update baselines if needed
        if timestamp - self.last_baseline_update > self.baseline_update_interval:
            self._update_baselines()
        
        # Check for drift
        self._check_drift(policy_name)
    
    def record_violation(self, violation: PolicyViolation):
        """Record a policy violation for drift analysis."""
        timestamp = time.time()
        
        self.violation_metrics[violation.policy_name].append({
            'timestamp': timestamp,
            'violation_type': violation.violation_type,
            'severity': violation.severity,
            'user_id': violation.user_id,
            'tenant_id': violation.tenant_id,
            'resource_path': violation.resource_path,
            'context': violation.context
        })
        
        # Check for violation pattern drift
        self._check_violation_drift(violation.policy_name)
    
    def _update_baselines(self):
        """Update compliance baselines based on recent data."""
        current_time = time.time()
        baseline_cutoff = current_time - self.baseline_window
        
        for policy_name in self.evaluation_metrics:
            # Filter recent evaluations
            recent_evaluations = [
                eval_data for eval_data in self.evaluation_metrics[policy_name]
                if eval_data['timestamp'] >= baseline_cutoff
            ]
            
            if len(recent_evaluations) < 10:  # Need minimum sample size
                continue
            
            # Calculate baseline metrics
            success_count = sum(1 for e in recent_evaluations if e['allowed'])
            success_rate = success_count / len(recent_evaluations)
            
            avg_eval_time = sum(e['evaluation_time'] for e in recent_evaluations) / len(recent_evaluations)
            
            # Rule coverage analysis
            rule_coverage = defaultdict(int)
            for eval_data in recent_evaluations:
                for rule in eval_data['matched_rules']:
                    rule_coverage[rule] += 1
            
            # Violation rate
            recent_violations = [
                v for v in self.violation_metrics[policy_name]
                if v['timestamp'] >= baseline_cutoff
            ]
            violation_rate = len(recent_violations) / len(recent_evaluations) if recent_evaluations else 0
            
            # Update baseline
            self.compliance_baselines[policy_name] = ComplianceBaseline(
                policy_name=policy_name,
                success_rate=success_rate,
                average_evaluation_time=avg_eval_time,
                rule_coverage=dict(rule_coverage),
                violation_rate=violation_rate,
                last_updated=current_time,
                sample_count=len(recent_evaluations)
            )
        
        self.last_baseline_update = current_time
        logger.info(f"Updated baselines for {len(self.compliance_baselines)} policies")
    
    def _check_drift(self, policy_name: str):
        """Check for drift in policy behavior."""
        if policy_name not in self.compliance_baselines:
            return  # No baseline established yet
        
        baseline = self.compliance_baselines[policy_name]
        current_time = time.time()
        detection_cutoff = current_time - self.detection_window
        
        # Get recent evaluations for drift detection
        recent_evaluations = [
            eval_data for eval_data in self.evaluation_metrics[policy_name]
            if eval_data['timestamp'] >= detection_cutoff
        ]
        
        if len(recent_evaluations) < 5:  # Need minimum sample size
            return
        
        # Check compliance drift
        current_success_rate = sum(1 for e in recent_evaluations if e['allowed']) / len(recent_evaluations)
        compliance_drift = abs(current_success_rate - baseline.success_rate) / baseline.success_rate
        
        if compliance_drift > self.drift_thresholds[DriftType.COMPLIANCE_DEGRADATION]:
            self._create_drift_alert(
                drift_type=DriftType.COMPLIANCE_DEGRADATION,
                policy_name=policy_name,
                metric_name="success_rate",
                current_value=current_success_rate,
                expected_value=baseline.success_rate,
                drift_percentage=compliance_drift * 100,
                description=f"Policy compliance rate drifted from {baseline.success_rate:.2%} to {current_success_rate:.2%}"
            )
        
        # Check performance drift
        current_avg_time = sum(e['evaluation_time'] for e in recent_evaluations) / len(recent_evaluations)
        performance_drift = abs(current_avg_time - baseline.average_evaluation_time) / baseline.average_evaluation_time
        
        if performance_drift > self.drift_thresholds[DriftType.PERFORMANCE_DRIFT]:
            self._create_drift_alert(
                drift_type=DriftType.PERFORMANCE_DRIFT,
                policy_name=policy_name,
                metric_name="evaluation_time",
                current_value=current_avg_time,
                expected_value=baseline.average_evaluation_time,
                drift_percentage=performance_drift * 100,
                description=f"Policy evaluation time drifted from {baseline.average_evaluation_time:.3f}s to {current_avg_time:.3f}s"
            )
        
        # Check rule coverage drift
        current_rule_coverage = defaultdict(int)
        for eval_data in recent_evaluations:
            for rule in eval_data['matched_rules']:
                current_rule_coverage[rule] += 1
        
        self._check_coverage_drift(policy_name, baseline.rule_coverage, dict(current_rule_coverage))
    
    def _check_violation_drift(self, policy_name: str):
        """Check for drift in violation patterns."""
        current_time = time.time()
        detection_cutoff = current_time - self.detection_window
        
        recent_violations = [
            v for v in self.violation_metrics[policy_name]
            if v['timestamp'] >= detection_cutoff
        ]
        
        if not recent_violations:
            return
        
        # Check for unusual violation patterns
        violation_types = defaultdict(int)
        severity_counts = defaultdict(int)
        user_violations = defaultdict(int)
        
        for violation in recent_violations:
            violation_types[violation['violation_type']] += 1
            severity_counts[violation['severity']] += 1
            if violation['user_id']:
                user_violations[violation['user_id']] += 1
        
        # Detect policy bypass attempts (multiple violations from same user)
        for user_id, count in user_violations.items():
            if count >= 5:  # Threshold for suspicious activity
                self._create_drift_alert(
                    drift_type=DriftType.POLICY_BYPASS,
                    policy_name=policy_name,
                    metric_name="user_violations",
                    current_value=count,
                    expected_value=1,
                    drift_percentage=((count - 1) / 1) * 100,
                    description=f"User {user_id} has {count} violations in {self.detection_window}s window",
                    context={'user_id': user_id, 'violation_types': list(violation_types.keys())}
                )
    
    def _check_coverage_drift(self, 
                             policy_name: str,
                             baseline_coverage: Dict[str, int],
                             current_coverage: Dict[str, int]):
        """Check for drift in rule coverage patterns."""
        all_rules = set(baseline_coverage.keys()) | set(current_coverage.keys())
        
        for rule in all_rules:
            baseline_count = baseline_coverage.get(rule, 0)
            current_count = current_coverage.get(rule, 0)
            
            # Check for rules that stopped firing
            if baseline_count > 0 and current_count == 0:
                self._create_drift_alert(
                    drift_type=DriftType.COVERAGE_GAP,
                    policy_name=policy_name,
                    metric_name="rule_coverage",
                    current_value=0,
                    expected_value=baseline_count,
                    drift_percentage=100,
                    description=f"Rule '{rule}' stopped firing (was {baseline_count} times in baseline)",
                    context={'rule_name': rule}
                )
            
            # Check for significant changes in rule firing frequency
            elif baseline_count > 0:
                coverage_drift = abs(current_count - baseline_count) / baseline_count
                if coverage_drift > self.drift_thresholds[DriftType.UNEXPECTED_BEHAVIOR]:
                    self._create_drift_alert(
                        drift_type=DriftType.UNEXPECTED_BEHAVIOR,
                        policy_name=policy_name,
                        metric_name="rule_frequency",
                        current_value=current_count,
                        expected_value=baseline_count,
                        drift_percentage=coverage_drift * 100,
                        description=f"Rule '{rule}' frequency changed from {baseline_count} to {current_count}",
                        context={'rule_name': rule}
                    )
    
    def _create_drift_alert(self,
                           drift_type: DriftType,
                           policy_name: str,
                           metric_name: str,
                           current_value: float,
                           expected_value: float,
                           drift_percentage: float,
                           description: str,
                           context: Dict[str, Any] = None):
        """Create a drift detection alert."""
        import uuid
        
        # Determine severity based on drift percentage
        if drift_percentage >= 50:
            severity = DriftSeverity.CRITICAL
        elif drift_percentage >= 25:
            severity = DriftSeverity.HIGH
        elif drift_percentage >= 15:
            severity = DriftSeverity.MEDIUM
        else:
            severity = DriftSeverity.LOW
        
        # Create alert
        alert = DriftAlert(
            alert_id=str(uuid.uuid4()),
            drift_type=drift_type,
            severity=severity,
            policy_name=policy_name,
            metric_name=metric_name,
            description=description,
            current_value=current_value,
            expected_value=expected_value,
            drift_percentage=drift_percentage,
            detection_time=time.time(),
            context=context or {},
            remediation_suggestions=self._get_remediation_suggestions(drift_type, policy_name)
        )
        
        # Check for duplicate alerts (avoid spam)
        alert_key = f"{policy_name}:{drift_type.value}:{metric_name}"
        if alert_key in self.active_alerts:
            # Update existing alert if drift increased
            existing_alert = self.active_alerts[alert_key]
            if drift_percentage > existing_alert.drift_percentage:
                existing_alert.drift_percentage = drift_percentage
                existing_alert.current_value = current_value
                existing_alert.detection_time = time.time()
                existing_alert.severity = severity
        else:
            # New alert
            self.active_alerts[alert_key] = alert
            
            # Log the alert
            logger.warning(
                f"Policy drift detected: {drift_type.value}",
                extra={
                    'alert_id': alert.alert_id,
                    'policy_name': policy_name,
                    'metric_name': metric_name,
                    'drift_percentage': drift_percentage,
                    'severity': severity.value
                }
            )
            
            # Notify handlers
            for handler in self.alert_handlers:
                try:
                    handler(alert)
                except Exception as e:
                    logger.error(f"Error in drift alert handler: {e}")
    
    def _get_remediation_suggestions(self, drift_type: DriftType, policy_name: str) -> List[str]:
        """Get remediation suggestions for drift type."""
        suggestions = {
            DriftType.COMPLIANCE_DEGRADATION: [
                "Review recent policy changes for unintended effects",
                "Check for changes in input data patterns",
                "Verify policy rules are still appropriate for current use cases",
                "Consider updating policy thresholds or conditions"
            ],
            DriftType.POLICY_BYPASS: [
                "Investigate user behavior patterns for potential abuse",
                "Review access controls and permissions",
                "Consider implementing additional authentication factors",
                "Audit recent system changes that might enable bypasses"
            ],
            DriftType.UNEXPECTED_BEHAVIOR: [
                "Analyze recent changes to system inputs or configuration",
                "Review policy logic for edge cases or unintended interactions",
                "Check for changes in data sources or formats",
                "Validate policy assumptions against current system state"
            ],
            DriftType.PERFORMANCE_DRIFT: [
                "Review system resource utilization and capacity",
                "Check for inefficient policy rules or complex evaluations",
                "Consider optimizing policy compilation or caching",
                "Monitor for external dependencies affecting performance"
            ],
            DriftType.COVERAGE_GAP: [
                "Review policy completeness for current use cases",
                "Check if new scenarios require additional rules",
                "Verify policy deployment and activation status",
                "Consider adding monitoring for uncovered edge cases"
            ]
        }
        
        return suggestions.get(drift_type, ["Contact policy administrator for investigation"])
    
    def get_active_alerts(self, 
                         policy_name: Optional[str] = None,
                         severity: Optional[DriftSeverity] = None) -> List[DriftAlert]:
        """Get active drift alerts with optional filtering."""
        alerts = list(self.active_alerts.values())
        
        if policy_name:
            alerts = [a for a in alerts if a.policy_name == policy_name]
        
        if severity:
            alerts = [a for a in alerts if a.severity == severity]
        
        return sorted(alerts, key=lambda a: a.detection_time, reverse=True)
    
    def acknowledge_alert(self, alert_id: str) -> bool:
        """Acknowledge and remove a drift alert."""
        for key, alert in self.active_alerts.items():
            if alert.alert_id == alert_id:
                del self.active_alerts[key]
                logger.info(f"Acknowledged drift alert: {alert_id}")
                return True
        
        return False
    
    def get_drift_metrics(self, policy_name: str) -> Dict[str, Any]:
        """Get comprehensive drift metrics for a policy."""
        if policy_name not in self.compliance_baselines:
            return {}
        
        baseline = self.compliance_baselines[policy_name]
        current_time = time.time()
        
        # Get recent data
        recent_evaluations = [
            e for e in self.evaluation_metrics[policy_name]
            if e['timestamp'] >= current_time - self.detection_window
        ]
        
        recent_violations = [
            v for v in self.violation_metrics[policy_name]
            if v['timestamp'] >= current_time - self.detection_window
        ]
        
        if not recent_evaluations:
            return {}
        
        # Calculate current metrics
        current_success_rate = sum(1 for e in recent_evaluations if e['allowed']) / len(recent_evaluations)
        current_avg_time = sum(e['evaluation_time'] for e in recent_evaluations) / len(recent_evaluations)
        current_violation_rate = len(recent_violations) / len(recent_evaluations)
        
        return {
            'policy_name': policy_name,
            'baseline': {
                'success_rate': baseline.success_rate,
                'average_evaluation_time': baseline.average_evaluation_time,
                'violation_rate': baseline.violation_rate,
                'sample_count': baseline.sample_count,
                'last_updated': baseline.last_updated
            },
            'current': {
                'success_rate': current_success_rate,
                'average_evaluation_time': current_avg_time,
                'violation_rate': current_violation_rate,
                'sample_count': len(recent_evaluations)
            },
            'drift': {
                'success_rate_drift': abs(current_success_rate - baseline.success_rate) / baseline.success_rate * 100,
                'performance_drift': abs(current_avg_time - baseline.average_evaluation_time) / baseline.average_evaluation_time * 100,
                'violation_rate_drift': abs(current_violation_rate - baseline.violation_rate) / max(baseline.violation_rate, 0.001) * 100
            },
            'active_alerts': len([a for a in self.active_alerts.values() if a.policy_name == policy_name])
        }
    
    def add_alert_handler(self, handler: callable):
        """Add a handler for drift alerts."""
        self.alert_handlers.append(handler)
    
    def clear_old_data(self, retention_hours: int = 24):
        """Clear old metrics data to manage memory usage."""
        cutoff_time = time.time() - (retention_hours * 3600)
        
        for policy_name in list(self.evaluation_metrics.keys()):
            # Filter out old data
            self.evaluation_metrics[policy_name] = deque(
                [e for e in self.evaluation_metrics[policy_name] if e['timestamp'] >= cutoff_time],
                maxlen=1000
            )
            
            self.violation_metrics[policy_name] = deque(
                [v for v in self.violation_metrics[policy_name] if v['timestamp'] >= cutoff_time],
                maxlen=1000
            )
            
            self.performance_metrics[policy_name] = deque(
                [p for p in self.performance_metrics[policy_name] if p['timestamp'] >= cutoff_time],
                maxlen=1000
            )
        
        logger.info(f"Cleared metrics data older than {retention_hours} hours")