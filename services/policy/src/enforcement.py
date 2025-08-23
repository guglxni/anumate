"""
Policy enforcement integration module.

This module provides a unified interface for policy enforcement,
integrating middleware, drift detection, and violation reporting.
"""

import logging
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass
import asyncio

try:
    from .engine import PolicyEngine
    from .middleware import PolicyEnforcementMiddleware, PolicyEnforcementConfig, PolicyRedactionFilter
    from .drift_detector import PolicyDriftDetector, DriftAlert
    from .violation_reporter import ViolationReporter, AlertRule, AlertChannel, create_default_alert_rules
except ImportError:
    from engine import PolicyEngine
    from middleware import PolicyEnforcementMiddleware, PolicyEnforcementConfig, PolicyRedactionFilter
    from drift_detector import PolicyDriftDetector, DriftAlert
    from violation_reporter import ViolationReporter, AlertRule, AlertChannel, create_default_alert_rules

logger = logging.getLogger(__name__)


@dataclass
class PolicyEnforcementStats:
    """Statistics for policy enforcement system."""
    total_evaluations: int
    total_violations: int
    total_alerts: int
    active_drift_alerts: int
    policies_loaded: int
    enforcement_enabled: bool
    drift_detection_enabled: bool
    violation_reporting_enabled: bool


class PolicyEnforcementSystem:
    """Unified policy enforcement system."""
    
    def __init__(self,
                 config: Optional[PolicyEnforcementConfig] = None,
                 policy_loader: Optional[Callable[[], Dict[str, str]]] = None,
                 storage_backend: Optional[Callable] = None,
                 notification_backend: Optional[Callable] = None):
        """
        Initialize policy enforcement system.
        
        Args:
            config: Policy enforcement configuration
            policy_loader: Function to load policies
            storage_backend: Backend for persistent storage
            notification_backend: Backend for notifications
        """
        self.config = config or PolicyEnforcementConfig()
        self.policy_loader = policy_loader
        
        # Core components
        self.engine = PolicyEngine()
        self.middleware = PolicyEnforcementMiddleware(
            app=None,  # Will be set when middleware is applied
            config=self.config,
            policy_loader=policy_loader
        )
        
        # Optional components based on configuration
        self.drift_detector = None
        if self.config.drift_detection_enabled:
            self.drift_detector = PolicyDriftDetector(self.engine)
        
        self.violation_reporter = None
        if hasattr(self.config, 'violation_reporting_enabled') and self.config.violation_reporting_enabled:
            self.violation_reporter = ViolationReporter(
                storage_backend=storage_backend,
                notification_backend=notification_backend
            )
        
        # Redaction filter
        self.redaction_filter = PolicyRedactionFilter(self.engine)
        
        # Statistics
        self.stats = PolicyEnforcementStats(
            total_evaluations=0,
            total_violations=0,
            total_alerts=0,
            active_drift_alerts=0,
            policies_loaded=0,
            enforcement_enabled=self.config.enabled,
            drift_detection_enabled=self.config.drift_detection_enabled,
            violation_reporting_enabled=getattr(self.config, 'violation_reporting_enabled', False)
        )
        
        # Wire up components
        self._setup_component_integration()
    
    def _setup_component_integration(self):
        """Set up integration between components."""
        # Connect middleware to violation reporter
        if self.violation_reporter:
            self.middleware.add_violation_handler(self.violation_reporter.record_violation)
        
        # Connect drift detector to violation reporter
        if self.drift_detector and self.violation_reporter:
            self.drift_detector.add_alert_handler(self._handle_drift_alert)
        
        # Set up default alert rules if violation reporter is available
        if self.violation_reporter:
            for rule in create_default_alert_rules():
                self.violation_reporter.add_alert_rule(rule)
            
            # Add default notification handlers
            try:
                from violation_reporter import log_notification_handler, webhook_notification_handler
                self.violation_reporter.add_notification_handler(AlertChannel.LOG, log_notification_handler)
                self.violation_reporter.add_notification_handler(AlertChannel.WEBHOOK, webhook_notification_handler)
            except ImportError:
                # Fallback for when running as module
                pass
    
    def get_middleware(self, app):
        """Get configured middleware for FastAPI application."""
        self.middleware.app = app
        return self.middleware
    
    def load_policies(self, policies: Dict[str, str]):
        """Load policies into the enforcement system."""
        loaded_count = 0
        
        for policy_name, policy_source in policies.items():
            try:
                # Compile and cache policy
                result = self.engine.compile_policy(policy_source, policy_name)
                if result.success:
                    loaded_count += 1
                    logger.info(f"Loaded policy: {policy_name}")
                else:
                    logger.error(f"Failed to load policy {policy_name}: {result.error_message}")
            
            except Exception as e:
                logger.error(f"Error loading policy {policy_name}: {e}")
        
        self.stats.policies_loaded = loaded_count
        logger.info(f"Loaded {loaded_count} policies into enforcement system")
    
    def add_policy(self, name: str, source: str) -> bool:
        """Add a single policy to the enforcement system."""
        try:
            result = self.engine.compile_policy(source, name)
            if result.success:
                self.stats.policies_loaded += 1
                logger.info(f"Added policy: {name}")
                return True
            else:
                logger.error(f"Failed to add policy {name}: {result.error_message}")
                return False
        
        except Exception as e:
            logger.error(f"Error adding policy {name}: {e}")
            return False
    
    def remove_policy(self, name: str) -> bool:
        """Remove a policy from the enforcement system."""
        try:
            # Remove from engine cache
            if name in self.engine._compiled_policies:
                del self.engine._compiled_policies[name]
                self.stats.policies_loaded -= 1
                logger.info(f"Removed policy: {name}")
                return True
            else:
                logger.warning(f"Policy not found: {name}")
                return False
        
        except Exception as e:
            logger.error(f"Error removing policy {name}: {e}")
            return False
    
    def evaluate_policy(self, 
                       policy_name: str,
                       data: Dict[str, Any],
                       context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Evaluate a specific policy against data."""
        import time
        
        start_time = time.time()
        
        try:
            # Get cached policy
            policy = self.engine.get_cached_policy(policy_name)
            if not policy:
                return {
                    'success': False,
                    'error': f'Policy not found: {policy_name}'
                }
            
            # Evaluate policy
            result = self.engine.evaluate_policy(policy, data, context)
            evaluation_time = time.time() - start_time
            
            # Update statistics
            self.stats.total_evaluations += 1
            
            # Record evaluation for drift detection
            if self.drift_detector and result.success:
                self.drift_detector.record_evaluation(
                    policy_name=policy_name,
                    evaluation_result=result.evaluation,
                    evaluation_time=evaluation_time,
                    context=context or {}
                )
            
            if result.success:
                return {
                    'success': True,
                    'allowed': result.evaluation.allowed,
                    'matched_rules': result.evaluation.matched_rules,
                    'actions': result.evaluation.actions,
                    'evaluation_time': evaluation_time
                }
            else:
                return {
                    'success': False,
                    'error': result.error_message
                }
        
        except Exception as e:
            logger.error(f"Error evaluating policy {policy_name}: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def redact_data(self, 
                   data: Any,
                   policies: List[str],
                   context: Dict[str, Any]) -> Any:
        """Apply data redaction using specified policies."""
        try:
            return self.redaction_filter.redact_data(data, policies, context)
        except Exception as e:
            logger.error(f"Error applying data redaction: {e}")
            return data
    
    def add_alert_rule(self, rule: AlertRule):
        """Add an alert rule to the violation reporter."""
        if self.violation_reporter:
            self.violation_reporter.add_alert_rule(rule)
        else:
            logger.warning("Violation reporter not enabled, cannot add alert rule")
    
    def get_drift_alerts(self, policy_name: Optional[str] = None) -> List[DriftAlert]:
        """Get active drift alerts."""
        if self.drift_detector:
            return self.drift_detector.get_active_alerts(policy_name=policy_name)
        else:
            return []
    
    def get_violation_report(self,
                           start_time: float,
                           end_time: float,
                           **kwargs):
        """Generate a violation report."""
        if self.violation_reporter:
            return self.violation_reporter.generate_violation_report(
                start_time=start_time,
                end_time=end_time,
                **kwargs
            )
        else:
            logger.warning("Violation reporter not enabled, cannot generate report")
            return None
    
    def get_policy_metrics(self, policy_name: str) -> Dict[str, Any]:
        """Get comprehensive metrics for a policy."""
        metrics = {}
        
        # Basic policy info
        policy = self.engine.get_cached_policy(policy_name)
        if policy:
            metrics['policy_loaded'] = True
            metrics['policy_name'] = policy.name
        else:
            metrics['policy_loaded'] = False
            return metrics
        
        # Drift metrics
        if self.drift_detector:
            drift_metrics = self.drift_detector.get_drift_metrics(policy_name)
            metrics['drift'] = drift_metrics
        
        # Violation statistics
        if self.violation_reporter:
            # Get recent violations for this policy
            recent_violations = [
                v for v in self.violation_reporter.recent_violations
                if v.policy_name == policy_name
            ]
            
            metrics['violations'] = {
                'total_recent': len(recent_violations),
                'by_severity': {},
                'by_type': {}
            }
            
            # Breakdown by severity and type
            from collections import defaultdict
            severity_counts = defaultdict(int)
            type_counts = defaultdict(int)
            
            for violation in recent_violations:
                severity_counts[violation.severity] += 1
                type_counts[violation.violation_type] += 1
            
            metrics['violations']['by_severity'] = dict(severity_counts)
            metrics['violations']['by_type'] = dict(type_counts)
        
        return metrics
    
    def get_system_stats(self) -> PolicyEnforcementStats:
        """Get system-wide enforcement statistics."""
        # Update dynamic stats
        if self.drift_detector:
            self.stats.active_drift_alerts = len(self.drift_detector.get_active_alerts())
        
        if self.violation_reporter:
            reporter_stats = self.violation_reporter.get_statistics()
            self.stats.total_violations = reporter_stats['total_violations']
            self.stats.total_alerts = reporter_stats['total_alerts_sent']
        
        return self.stats
    
    def _handle_drift_alert(self, alert: DriftAlert):
        """Handle drift alerts from the drift detector."""
        if self.violation_reporter:
            # Convert drift alert to violation for reporting
            from .middleware import PolicyViolation
            import uuid
            
            violation = PolicyViolation(
                violation_id=str(uuid.uuid4()),
                policy_name=alert.policy_name,
                rule_name=f"drift_detection_{alert.drift_type.value}",
                violation_type="POLICY_DRIFT",
                severity=alert.severity.value.upper(),
                message=alert.description,
                user_id=None,
                tenant_id=alert.tenant_id,
                resource_path="system",
                timestamp=alert.detection_time,
                context=alert.context,
                remediation_actions=[{
                    'type': 'INVESTIGATE',
                    'suggestions': alert.remediation_suggestions
                }]
            )
            
            self.violation_reporter.record_violation(violation)
    
    def health_check(self) -> Dict[str, Any]:
        """Perform health check on enforcement system."""
        health = {
            'status': 'healthy',
            'components': {},
            'timestamp': time.time()
        }
        
        # Check engine
        try:
            test_policy = 'policy "test" { rule "test" { when true then allow() } }'
            result = self.engine.compile_policy(test_policy)
            health['components']['engine'] = 'healthy' if result.success else 'unhealthy'
        except Exception as e:
            health['components']['engine'] = f'error: {e}'
            health['status'] = 'degraded'
        
        # Check middleware
        health['components']['middleware'] = 'healthy' if self.middleware else 'disabled'
        
        # Check drift detector
        if self.drift_detector:
            health['components']['drift_detector'] = 'healthy'
        else:
            health['components']['drift_detector'] = 'disabled'
        
        # Check violation reporter
        if self.violation_reporter:
            health['components']['violation_reporter'] = 'healthy'
        else:
            health['components']['violation_reporter'] = 'disabled'
        
        return health
    
    def cleanup(self):
        """Clean up resources and old data."""
        try:
            # Clear old data from components
            if self.drift_detector:
                self.drift_detector.clear_old_data()
            
            if self.violation_reporter:
                self.violation_reporter.clear_old_data()
            
            # Clear engine cache if needed
            if len(self.engine._compiled_policies) > 100:  # Arbitrary limit
                self.engine.clear_cache()
                logger.info("Cleared policy engine cache")
            
            logger.info("Policy enforcement system cleanup completed")
        
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")


# Utility functions for easy setup

def create_enforcement_system(
    policies: Optional[Dict[str, str]] = None,
    enable_drift_detection: bool = True,
    enable_violation_reporting: bool = True,
    **config_kwargs
) -> PolicyEnforcementSystem:
    """Create a fully configured policy enforcement system."""
    
    # Create configuration
    config = PolicyEnforcementConfig(
        drift_detection_enabled=enable_drift_detection,
        **config_kwargs
    )
    
    # Add violation reporting to config
    config.violation_reporting_enabled = enable_violation_reporting
    
    # Create system
    system = PolicyEnforcementSystem(config=config)
    
    # Load policies if provided
    if policies:
        system.load_policies(policies)
    
    return system


def setup_fastapi_enforcement(app, 
                             policies: Dict[str, str],
                             **kwargs) -> PolicyEnforcementSystem:
    """Set up policy enforcement for a FastAPI application."""
    
    # Create enforcement system
    system = create_enforcement_system(policies=policies, **kwargs)
    
    # Add middleware to app
    middleware = system.get_middleware(app)
    app.middleware("http")(middleware)
    
    # Add health check endpoint
    @app.get("/policy/health")
    async def policy_health():
        return system.health_check()
    
    # Add stats endpoint
    @app.get("/policy/stats")
    async def policy_stats():
        return system.get_system_stats()
    
    logger.info("Policy enforcement configured for FastAPI application")
    return system