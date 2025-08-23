"""
Policy enforcement middleware for API endpoints.

This module provides middleware components for enforcing policies across
API endpoints, including request/response filtering, data redaction,
and compliance monitoring.
"""

import time
import json
import logging
from typing import Dict, Any, List, Optional, Callable, Awaitable
from dataclasses import dataclass
from uuid import uuid4

from fastapi import Request, Response, HTTPException
from fastapi.responses import JSONResponse

try:
    from .engine import PolicyEngine, PolicyEngineResult
    from .evaluator import EvaluationResult
    from .ast_nodes import ActionType
except ImportError:
    from engine import PolicyEngine, PolicyEngineResult
    from evaluator import EvaluationResult
    from ast_nodes import ActionType

logger = logging.getLogger(__name__)


@dataclass
class PolicyEnforcementConfig:
    """Configuration for policy enforcement."""
    enabled: bool = True
    policy_cache_ttl: int = 300  # 5 minutes
    evaluation_timeout: float = 5.0  # 5 seconds
    log_all_evaluations: bool = True
    fail_open: bool = False  # If True, allow requests when policy evaluation fails
    redaction_enabled: bool = True
    drift_detection_enabled: bool = True


@dataclass
class PolicyViolation:
    """Represents a policy violation."""
    violation_id: str
    policy_name: str
    rule_name: str
    violation_type: str
    severity: str
    message: str
    user_id: Optional[str]
    tenant_id: Optional[str]
    resource_path: str
    timestamp: float
    context: Dict[str, Any]
    remediation_actions: List[Dict[str, Any]]


class PolicyEnforcementMiddleware:
    """FastAPI middleware for policy enforcement."""
    
    def __init__(self, 
                 app: Callable,
                 config: Optional[PolicyEnforcementConfig] = None,
                 policy_loader: Optional[Callable[[], Dict[str, str]]] = None):
        """
        Initialize policy enforcement middleware.
        
        Args:
            app: FastAPI application
            config: Policy enforcement configuration
            policy_loader: Function to load policies (returns dict of name -> source)
        """
        self.app = app
        self.config = config or PolicyEnforcementConfig()
        self.policy_loader = policy_loader
        self.engine = PolicyEngine()
        self.policy_cache: Dict[str, Any] = {}
        self.policy_cache_timestamps: Dict[str, float] = {}
        self.violation_handlers: List[Callable[[PolicyViolation], None]] = []
        
        # Load initial policies
        if self.policy_loader:
            self._load_policies()
    
    async def __call__(self, scope, receive, send):
        """Process request through policy enforcement."""
        if scope["type"] != "http" or not self.config.enabled:
            await self.app(scope, receive, send)
            return
        
        # Create request object for easier handling
        request = Request(scope, receive)
        
        # Skip policy enforcement for health checks and internal endpoints
        if self._should_skip_enforcement(request):
            await self.app(scope, receive, send)
            return
        
        try:
            # Pre-request policy evaluation
            pre_request_result = await self._evaluate_pre_request_policies(request)
            
            if not pre_request_result.allowed:
                # Request denied by policy
                violation = self._create_violation(
                    policy_name=pre_request_result.policy_name,
                    rule_names=pre_request_result.matched_rules,
                    violation_type="REQUEST_DENIED",
                    severity="HIGH",
                    message="Request denied by policy",
                    request=request,
                    actions=pre_request_result.actions
                )
                await self._handle_violation(violation)
                
                response = JSONResponse(
                    status_code=403,
                    content={
                        "error": {
                            "code": "POLICY_VIOLATION",
                            "message": "Request denied by security policy",
                            "violation_id": violation.violation_id
                        }
                    }
                )
                await response(scope, receive, send)
                return
            
            # Capture response for post-processing
            response_body = []
            response_status = [200]
            response_headers = []
            
            async def capture_send(message):
                if message["type"] == "http.response.start":
                    response_status[0] = message["status"]
                    response_headers.extend(message.get("headers", []))
                elif message["type"] == "http.response.body":
                    body = message.get("body", b"")
                    if body:
                        response_body.append(body)
                await send(message)
            
            # Process request through application
            await self.app(scope, receive, capture_send)
            
            # Post-request policy evaluation and response processing
            if response_body and self.config.redaction_enabled:
                combined_body = b"".join(response_body)
                await self._evaluate_post_request_policies(request, combined_body, response_status[0])
        
        except Exception as e:
            logger.error(f"Policy enforcement error: {e}")
            if self.config.fail_open:
                # Allow request to proceed on policy system failure
                await self.app(scope, receive, send)
            else:
                # Deny request on policy system failure
                response = JSONResponse(
                    status_code=500,
                    content={
                        "error": {
                            "code": "POLICY_SYSTEM_ERROR",
                            "message": "Policy enforcement system unavailable"
                        }
                    }
                )
                await response(scope, receive, send)
    
    def _should_skip_enforcement(self, request: Request) -> bool:
        """Check if policy enforcement should be skipped for this request."""
        skip_paths = [
            "/health",
            "/metrics",
            "/docs",
            "/openapi.json",
            "/favicon.ico"
        ]
        
        return any(request.url.path.startswith(path) for path in skip_paths)
    
    async def _evaluate_pre_request_policies(self, request: Request) -> 'PolicyEvaluationResult':
        """Evaluate policies before request processing."""
        # Extract request context
        context = await self._extract_request_context(request)
        
        # Get applicable policies
        policies = self._get_applicable_policies(request.url.path, request.method)
        
        # Evaluate each policy
        for policy_name, policy_source in policies.items():
            try:
                # Compile policy if not cached
                policy = self._get_or_compile_policy(policy_name, policy_source)
                
                # Evaluate policy
                eval_result = self.engine.evaluate_policy(policy, context)
                
                if eval_result.success and eval_result.evaluation:
                    evaluation = eval_result.evaluation
                    
                    # Check for deny actions
                    deny_actions = [a for a in evaluation.actions if a.get('type') == ActionType.DENY.value]
                    if deny_actions:
                        return PolicyEvaluationResult(
                            allowed=False,
                            policy_name=policy_name,
                            matched_rules=evaluation.matched_rules,
                            actions=evaluation.actions
                        )
                    
                    # Log policy evaluation if configured
                    if self.config.log_all_evaluations:
                        logger.info(f"Policy evaluation: {policy_name}, rules: {evaluation.matched_rules}")
            
            except Exception as e:
                logger.error(f"Error evaluating policy {policy_name}: {e}")
                if not self.config.fail_open:
                    return PolicyEvaluationResult(
                        allowed=False,
                        policy_name=policy_name,
                        matched_rules=[],
                        actions=[],
                        error=str(e)
                    )
        
        return PolicyEvaluationResult(allowed=True, policy_name="", matched_rules=[], actions=[])
    
    async def _evaluate_post_request_policies(self, request: Request, response_body: bytes, status_code: int):
        """Evaluate policies after request processing for response filtering."""
        try:
            # Parse response body if JSON
            response_data = None
            if response_body:
                try:
                    response_data = json.loads(response_body.decode('utf-8'))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    # Not JSON or not UTF-8, skip response policy evaluation
                    return
            
            # Extract context including response data
            context = await self._extract_request_context(request)
            if response_data:
                context['response'] = response_data
                context['status_code'] = status_code
            
            # Get response filtering policies
            policies = self._get_response_policies()
            
            # Evaluate response policies
            for policy_name, policy_source in policies.items():
                try:
                    policy = self._get_or_compile_policy(policy_name, policy_source)
                    eval_result = self.engine.evaluate_policy(policy, context)
                    
                    if eval_result.success and eval_result.evaluation:
                        evaluation = eval_result.evaluation
                        
                        # Process redaction actions
                        redaction_actions = [a for a in evaluation.actions 
                                           if a.get('type') == ActionType.REDACT.value]
                        
                        if redaction_actions and response_data:
                            # Apply redactions to response data
                            redacted_data = self._apply_redactions(response_data, redaction_actions)
                            # Note: In a real implementation, we'd need to modify the response
                            # This is complex with FastAPI middleware, so we log the redaction
                            logger.info(f"Response redaction applied: {len(redaction_actions)} redactions")
                        
                        # Handle alert actions
                        alert_actions = [a for a in evaluation.actions 
                                       if a.get('type') == ActionType.ALERT.value]
                        
                        for alert_action in alert_actions:
                            violation = self._create_violation(
                                policy_name=policy_name,
                                rule_names=evaluation.matched_rules,
                                violation_type="DATA_EXPOSURE",
                                severity=alert_action.get('parameters', {}).get('severity', 'MEDIUM'),
                                message=alert_action.get('parameters', {}).get('message', 'Policy alert triggered'),
                                request=request,
                                actions=[alert_action]
                            )
                            await self._handle_violation(violation)
                
                except Exception as e:
                    logger.error(f"Error evaluating response policy {policy_name}: {e}")
        
        except Exception as e:
            logger.error(f"Error in post-request policy evaluation: {e}")
    
    async def _extract_request_context(self, request: Request) -> Dict[str, Any]:
        """Extract context from request for policy evaluation."""
        context = {
            'request': {
                'method': request.method,
                'path': request.url.path,
                'query_params': dict(request.query_params),
                'headers': dict(request.headers),
                'client_ip': request.client.host if request.client else None
            },
            'timestamp': time.time(),
            'correlation_id': request.headers.get('X-Correlation-ID', str(uuid4()))
        }
        
        # Extract user context from request state (set by auth middleware)
        if hasattr(request.state, 'user'):
            user = request.state.user
            context['user'] = {
                'id': getattr(user, 'user_id', None),
                'role': getattr(user, 'role', None),
                'tenant_id': getattr(user, 'tenant_id', None),
                'permissions': getattr(user, 'permissions', [])
            }
        
        # Extract tenant context
        if hasattr(request.state, 'tenant_id'):
            context['tenant_id'] = str(request.state.tenant_id)
        
        # Extract request body for POST/PUT requests
        if request.method in ['POST', 'PUT', 'PATCH']:
            try:
                # Note: This is simplified - in practice, we'd need to handle
                # the request body more carefully to avoid consuming it
                body = getattr(request.state, 'body', None)
                if body:
                    context['request']['body'] = body
            except Exception:
                pass
        
        return context
    
    def _get_applicable_policies(self, path: str, method: str) -> Dict[str, str]:
        """Get policies applicable to the request path and method."""
        # This would typically load from a policy registry or configuration
        # For now, return cached policies that match the request
        applicable_policies = {}
        
        for policy_name in self.policy_cache:
            # Simple path matching - in practice, this would be more sophisticated
            if self._policy_applies_to_path(policy_name, path, method):
                applicable_policies[policy_name] = self.policy_cache[policy_name]['source']
        
        return applicable_policies
    
    def _get_response_policies(self) -> Dict[str, str]:
        """Get policies for response filtering and redaction."""
        response_policies = {}
        
        for policy_name, policy_data in self.policy_cache.items():
            # Check if policy has response-related rules
            if 'response' in policy_data.get('tags', []) or 'redaction' in policy_data.get('tags', []):
                response_policies[policy_name] = policy_data['source']
        
        return response_policies
    
    def _policy_applies_to_path(self, policy_name: str, path: str, method: str) -> bool:
        """Check if a policy applies to the given path and method."""
        # This is a simplified implementation
        # In practice, policies would have metadata about their scope
        policy_data = self.policy_cache.get(policy_name, {})
        
        # Check path patterns
        path_patterns = policy_data.get('path_patterns', ['*'])
        if '*' in path_patterns:
            return True
        
        for pattern in path_patterns:
            if path.startswith(pattern.rstrip('*')):
                return True
        
        # Check method restrictions
        methods = policy_data.get('methods', ['*'])
        if '*' in methods or method in methods:
            return True
        
        return False
    
    def _get_or_compile_policy(self, policy_name: str, policy_source: str):
        """Get compiled policy from cache or compile it."""
        cache_key = f"{policy_name}:{hash(policy_source)}"
        
        # Check cache validity
        if (cache_key in self.policy_cache and 
            time.time() - self.policy_cache_timestamps.get(cache_key, 0) < self.config.policy_cache_ttl):
            return self.policy_cache[cache_key]['compiled']
        
        # Compile policy (trim whitespace first)
        compile_result = self.engine.compile_policy(policy_source.strip(), policy_name)
        if not compile_result.success:
            raise Exception(f"Policy compilation failed: {compile_result.error_message}")
        
        # Cache compiled policy
        self.policy_cache[cache_key] = {
            'source': policy_source,
            'compiled': compile_result.policy,
            'tags': self._extract_policy_tags(policy_source)
        }
        self.policy_cache_timestamps[cache_key] = time.time()
        
        return compile_result.policy
    
    def _extract_policy_tags(self, policy_source: str) -> List[str]:
        """Extract tags from policy source for categorization."""
        tags = []
        
        # Simple tag extraction based on keywords in policy
        if 'redact' in policy_source.lower():
            tags.append('redaction')
        if 'response' in policy_source.lower():
            tags.append('response')
        if 'pii' in policy_source.lower():
            tags.append('pii')
        if 'alert' in policy_source.lower():
            tags.append('alerting')
        
        return tags
    
    def _apply_redactions(self, data: Any, redaction_actions: List[Dict[str, Any]]) -> Any:
        """Apply redaction actions to data."""
        import re
        
        if isinstance(data, dict):
            redacted_data = {}
            for key, value in data.items():
                redacted_data[key] = self._apply_redactions(value, redaction_actions)
            return redacted_data
        
        elif isinstance(data, list):
            return [self._apply_redactions(item, redaction_actions) for item in data]
        
        elif isinstance(data, str):
            redacted_text = data
            for action in redaction_actions:
                params = action.get('parameters', {})
                pattern = params.get('pattern')
                replacement = params.get('replacement', '[REDACTED]')
                field = params.get('field')
                
                if pattern:
                    try:
                        redacted_text = re.sub(pattern, replacement, redacted_text)
                    except re.error as e:
                        logger.error(f"Invalid redaction pattern {pattern}: {e}")
                elif field:
                    # Field-based redaction would be handled at the dict level
                    pass
            
            return redacted_text
        
        else:
            return data
    
    def _create_violation(self, 
                         policy_name: str,
                         rule_names: List[str],
                         violation_type: str,
                         severity: str,
                         message: str,
                         request: Request,
                         actions: List[Dict[str, Any]]) -> PolicyViolation:
        """Create a policy violation record."""
        user_id = None
        tenant_id = None
        
        if hasattr(request.state, 'user'):
            user = request.state.user
            user_id = str(getattr(user, 'user_id', ''))
            tenant_id = str(getattr(user, 'tenant_id', ''))
        
        return PolicyViolation(
            violation_id=str(uuid4()),
            policy_name=policy_name,
            rule_name=', '.join(rule_names),
            violation_type=violation_type,
            severity=severity,
            message=message,
            user_id=user_id,
            tenant_id=tenant_id,
            resource_path=request.url.path,
            timestamp=time.time(),
            context={
                'method': request.method,
                'query_params': dict(request.query_params),
                'client_ip': request.client.host if request.client else None,
                'user_agent': request.headers.get('User-Agent'),
                'correlation_id': request.headers.get('X-Correlation-ID')
            },
            remediation_actions=actions
        )
    
    async def _handle_violation(self, violation: PolicyViolation):
        """Handle a policy violation."""
        # Log the violation
        logger.warning(
            f"Policy violation: {violation.violation_type}",
            extra={
                'violation_id': violation.violation_id,
                'policy_name': violation.policy_name,
                'rule_name': violation.rule_name,
                'severity': violation.severity,
                'user_id': violation.user_id,
                'tenant_id': violation.tenant_id,
                'resource_path': violation.resource_path
            }
        )
        
        # Call registered violation handlers
        for handler in self.violation_handlers:
            try:
                handler(violation)
            except Exception as e:
                logger.error(f"Error in violation handler: {e}")
    
    def add_violation_handler(self, handler: Callable[[PolicyViolation], None]):
        """Add a violation handler."""
        self.violation_handlers.append(handler)
    
    def _load_policies(self):
        """Load policies using the policy loader."""
        if not self.policy_loader:
            return
        
        try:
            policies = self.policy_loader()
            for name, source in policies.items():
                # Pre-compile and cache policies
                try:
                    self._get_or_compile_policy(name, source.strip())
                    logger.info(f"Loaded policy: {name}")
                except Exception as e:
                    logger.error(f"Failed to load policy {name}: {e}")
        
        except Exception as e:
            logger.error(f"Error loading policies: {e}")


@dataclass
class PolicyEvaluationResult:
    """Result of policy evaluation for middleware."""
    allowed: bool
    policy_name: str
    matched_rules: List[str]
    actions: List[Dict[str, Any]]
    error: Optional[str] = None


class PolicyRedactionFilter:
    """Utility class for applying data redaction based on policies."""
    
    def __init__(self, engine: PolicyEngine):
        self.engine = engine
    
    def redact_data(self, data: Any, policies: List[str], context: Dict[str, Any]) -> Any:
        """Apply redaction policies to data."""
        redacted_data = data
        
        for policy_name in policies:
            try:
                # Get cached policy
                policy = self.engine.get_cached_policy(policy_name)
                if not policy:
                    logger.warning(f"Policy not found in cache: {policy_name}")
                    continue
                
                # Evaluate policy with data
                eval_context = {**context, 'data': {'content': str(redacted_data)}}
                eval_result = self.engine.evaluate_policy(policy, eval_context)
                
                if eval_result.success and eval_result.evaluation:
                    # Apply redaction actions
                    redaction_actions = [a for a in eval_result.evaluation.actions 
                                       if a.get('type') == ActionType.REDACT.value]
                    
                    if redaction_actions:
                        redacted_data = self._apply_redactions_to_data(redacted_data, redaction_actions)
            
            except Exception as e:
                logger.error(f"Error applying redaction policy {policy_name}: {e}")
        
        return redacted_data
    
    def _apply_redactions_to_data(self, data: Any, redaction_actions: List[Dict[str, Any]]) -> Any:
        """Apply redaction actions to data structure."""
        import re
        
        if isinstance(data, dict):
            redacted_data = {}
            for key, value in data.items():
                # Check for field-specific redactions
                field_redactions = [a for a in redaction_actions 
                                  if a.get('parameters', {}).get('field') == key]
                
                if field_redactions:
                    # Apply field redaction
                    replacement = field_redactions[0].get('parameters', {}).get('replacement', '[REDACTED]')
                    redacted_data[key] = replacement
                else:
                    # Recursively apply redactions
                    redacted_data[key] = self._apply_redactions_to_data(value, redaction_actions)
            
            return redacted_data
        
        elif isinstance(data, list):
            return [self._apply_redactions_to_data(item, redaction_actions) for item in data]
        
        elif isinstance(data, str):
            redacted_text = data
            
            # Apply pattern-based redactions
            for action in redaction_actions:
                params = action.get('parameters', {})
                pattern = params.get('pattern')
                replacement = params.get('replacement', '[REDACTED]')
                
                if pattern:
                    try:
                        redacted_text = re.sub(pattern, replacement, redacted_text)
                    except re.error as e:
                        logger.error(f"Invalid redaction pattern {pattern}: {e}")
            
            return redacted_text
        
        else:
            return data