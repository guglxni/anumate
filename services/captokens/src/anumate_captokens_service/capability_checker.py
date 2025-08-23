"""
Capability Checker Service
==========================

Core service for validating capabilities against tool access patterns.
Implements strict tool allow-lists and capability enforcement.
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from .models import ToolAllowList

logger = logging.getLogger(__name__)


class PatternType(Enum):
    """Pattern matching types for tool allow-lists."""
    EXACT = "exact"
    REGEX = "regex" 
    GLOB = "glob"


class RuleType(Enum):
    """Rule types for access control."""
    ALLOW = "allow"
    DENY = "deny"


@dataclass
class CapabilityCheckRequest:
    """Request for capability checking."""
    capabilities: List[str]
    tool: str
    action: Optional[str] = None
    tenant_id: str = ""
    metadata: Optional[Dict[str, Any]] = None


@dataclass 
class CapabilityCheckResult:
    """Result of capability checking."""
    allowed: bool
    matched_rules: List[Dict[str, Any]]
    violation_reason: Optional[str] = None
    required_capabilities: List[str] = None


class CapabilityChecker:
    """
    Service for checking capabilities against tool access patterns.
    
    Features:
    - Pattern-based tool access control
    - Hierarchical capability matching
    - Priority-based rule evaluation
    - Caching for performance
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self._rule_cache: Dict[str, List[ToolAllowList]] = {}
        self._cache_timeout = 300  # 5 minutes
    
    async def check_capability(self, request: CapabilityCheckRequest) -> CapabilityCheckResult:
        """
        Check if provided capabilities allow access to a tool/action.
        
        Args:
            request: Capability check request
            
        Returns:
            Result indicating if access is allowed
        """
        try:
            # Get active rules for this tenant
            rules = await self._get_active_rules(request.tenant_id)
            
            if not rules:
                logger.warning(f"No capability rules found for tenant {request.tenant_id}")
                return CapabilityCheckResult(
                    allowed=False,
                    matched_rules=[],
                    violation_reason="No capability rules configured",
                    required_capabilities=[]
                )
            
            # Evaluate rules in priority order
            matched_rules = []
            allow_decision = None
            
            for rule in sorted(rules, key=lambda r: r.priority):
                if await self._rule_matches(rule, request):
                    matched_rules.append(self._rule_to_dict(rule))
                    
                    # First matching rule determines the decision
                    if allow_decision is None:
                        allow_decision = rule.rule_type == RuleType.ALLOW.value
                    
                    # DENY rules override ALLOW rules
                    if rule.rule_type == RuleType.DENY.value:
                        allow_decision = False
                        break
            
            # Default deny if no rules match
            if allow_decision is None:
                allow_decision = False
                violation_reason = f"No matching capability rules for tool '{request.tool}'"
            else:
                violation_reason = None if allow_decision else "Access denied by capability rules"
            
            # Determine required capabilities if access denied
            required_capabilities = []
            if not allow_decision:
                required_capabilities = await self._get_required_capabilities(
                    request.tool, request.action, request.tenant_id
                )
            
            logger.info(
                f"Capability check: tool='{request.tool}', capabilities={request.capabilities}, "
                f"allowed={allow_decision}, matched_rules={len(matched_rules)}"
            )
            
            return CapabilityCheckResult(
                allowed=allow_decision,
                matched_rules=matched_rules,
                violation_reason=violation_reason,
                required_capabilities=required_capabilities
            )
            
        except Exception as e:
            logger.error(f"Capability check failed: {e}", exc_info=True)
            return CapabilityCheckResult(
                allowed=False,
                matched_rules=[],
                violation_reason=f"Internal error during capability check: {str(e)}",
                required_capabilities=[]
            )
    
    async def _get_active_rules(self, tenant_id: str) -> List[ToolAllowList]:
        """Get active capability rules for a tenant."""
        try:
            # Check cache first
            cache_key = f"rules:{tenant_id}"
            if cache_key in self._rule_cache:
                return self._rule_cache[cache_key]
            
            # Query database
            query = select(ToolAllowList).where(
                and_(
                    ToolAllowList.tenant_id == tenant_id,
                    ToolAllowList.is_active == True
                )
            )
            
            result = await self.db.execute(query)
            rules = result.scalars().all()
            
            # Cache results
            self._rule_cache[cache_key] = list(rules)
            
            return rules
            
        except Exception as e:
            logger.error(f"Failed to get capability rules: {e}")
            return []
    
    async def _rule_matches(self, rule: ToolAllowList, request: CapabilityCheckRequest) -> bool:
        """Check if a rule matches the request."""
        try:
            # Check if any provided capability matches the rule's capability
            capability_matches = False
            for capability in request.capabilities:
                if self._capability_matches(capability, rule.capability_name):
                    capability_matches = True
                    break
            
            if not capability_matches:
                return False
            
            # Check tool pattern
            if not self._pattern_matches(request.tool, rule.tool_pattern, rule.pattern_type):
                return False
            
            # Check action pattern if specified
            if rule.action_pattern and request.action:
                if not self._pattern_matches(request.action, rule.action_pattern, rule.pattern_type):
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Rule matching failed: {e}")
            return False
    
    def _capability_matches(self, provided: str, required: str) -> bool:
        """
        Check if a provided capability matches a required capability.
        
        Supports hierarchical matching (e.g., 'admin' matches 'admin.*')
        """
        # Exact match
        if provided == required:
            return True
        
        # Hierarchical matching (dot notation)
        if "." in required:
            # 'admin.read' matches 'admin.*' or 'admin'
            required_parts = required.split(".")
            provided_parts = provided.split(".")
            
            if len(provided_parts) >= len(required_parts):
                for i, req_part in enumerate(required_parts):
                    if req_part == "*":
                        return True
                    if i >= len(provided_parts) or provided_parts[i] != req_part:
                        return False
                return True
        
        # Admin-level capabilities
        if provided == "admin" and not required.startswith("admin."):
            return True
            
        return False
    
    def _pattern_matches(self, value: str, pattern: str, pattern_type: str) -> bool:
        """Check if a value matches a pattern based on pattern type."""
        try:
            if pattern_type == PatternType.EXACT.value:
                return value == pattern
            
            elif pattern_type == PatternType.REGEX.value:
                return bool(re.match(pattern, value))
            
            elif pattern_type == PatternType.GLOB.value:
                # Convert glob pattern to regex
                regex_pattern = pattern.replace("*", ".*").replace("?", ".")
                return bool(re.match(f"^{regex_pattern}$", value))
            
            else:
                logger.warning(f"Unknown pattern type: {pattern_type}")
                return False
                
        except Exception as e:
            logger.error(f"Pattern matching failed: {e}")
            return False
    
    async def _get_required_capabilities(self, tool: str, action: Optional[str], tenant_id: str) -> List[str]:
        """Get the capabilities required to access a tool/action."""
        try:
            query = select(ToolAllowList.capability_name).where(
                and_(
                    ToolAllowList.tenant_id == tenant_id,
                    ToolAllowList.is_active == True,
                    ToolAllowList.rule_type == RuleType.ALLOW.value
                )
            )
            
            result = await self.db.execute(query)
            capabilities = [row[0] for row in result.fetchall()]
            
            return capabilities
            
        except Exception as e:
            logger.error(f"Failed to get required capabilities: {e}")
            return []
    
    def _rule_to_dict(self, rule: ToolAllowList) -> Dict[str, Any]:
        """Convert a ToolAllowList rule to dictionary."""
        return {
            "rule_id": str(rule.rule_id),
            "capability_name": rule.capability_name,
            "tool_pattern": rule.tool_pattern,
            "action_pattern": rule.action_pattern,
            "rule_type": rule.rule_type,
            "pattern_type": rule.pattern_type,
            "priority": rule.priority,
            "description": rule.description
        }
    
    async def add_default_rules(self, tenant_id: str) -> None:
        """Add default capability rules for a new tenant."""
        try:
            default_rules = [
                # Admin capabilities
                {
                    "capability_name": "admin",
                    "tool_pattern": "*",
                    "rule_type": "allow",
                    "pattern_type": "glob",
                    "priority": 1,
                    "description": "Admin access to all tools"
                },
                
                # Basic read capabilities
                {
                    "capability_name": "read",
                    "tool_pattern": "*.read",
                    "rule_type": "allow", 
                    "pattern_type": "glob",
                    "priority": 10,
                    "description": "Read access to all tools"
                },
                
                # Basic write capabilities  
                {
                    "capability_name": "write",
                    "tool_pattern": "*.write",
                    "rule_type": "allow",
                    "pattern_type": "glob", 
                    "priority": 10,
                    "description": "Write access to all tools"
                },
                
                # Database access
                {
                    "capability_name": "database.read",
                    "tool_pattern": "postgres.*",
                    "rule_type": "allow",
                    "pattern_type": "glob",
                    "priority": 20,
                    "description": "Database read access"
                },
                
                # Execution capabilities
                {
                    "capability_name": "execute",
                    "tool_pattern": "orchestrator.*",
                    "rule_type": "allow",
                    "pattern_type": "glob",
                    "priority": 15,
                    "description": "Plan execution access"
                }
            ]
            
            for rule_data in default_rules:
                rule = ToolAllowList(
                    tenant_id=tenant_id,
                    **rule_data
                )
                self.db.add(rule)
            
            await self.db.commit()
            logger.info(f"Added {len(default_rules)} default capability rules for tenant {tenant_id}")
            
        except Exception as e:
            logger.error(f"Failed to add default capability rules: {e}")
            await self.db.rollback()
            raise
    
    def clear_cache(self, tenant_id: Optional[str] = None) -> None:
        """Clear the rule cache."""
        if tenant_id:
            cache_key = f"rules:{tenant_id}"
            self._rule_cache.pop(cache_key, None)
        else:
            self._rule_cache.clear()
