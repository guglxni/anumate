"""
Policy evaluation engine for the Policy DSL.

This module evaluates parsed Policy AST against input data to determine
policy outcomes and actions.
"""

import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union, Callable
from dataclasses import dataclass
try:
    from .ast_nodes import (
        ASTNode, PolicyNode, RuleNode, ConditionNode, ActionNode, ExpressionNode,
        BinaryExpressionNode, UnaryExpressionNode, LiteralNode, IdentifierNode,
        FunctionCallNode, ListNode, DictNode, Operator, ActionType
    )
except ImportError:
    from ast_nodes import (
        ASTNode, PolicyNode, RuleNode, ConditionNode, ActionNode, ExpressionNode,
        BinaryExpressionNode, UnaryExpressionNode, LiteralNode, IdentifierNode,
        FunctionCallNode, ListNode, DictNode, Operator, ActionType
    )


@dataclass
class EvaluationResult:
    """Result of policy evaluation."""
    policy_name: str
    matched_rules: List[str]
    actions: List[Dict[str, Any]]
    allowed: bool
    metadata: Dict[str, Any]


@dataclass
class RuleResult:
    """Result of evaluating a single rule."""
    rule_name: str
    matched: bool
    actions: List[Dict[str, Any]]
    evaluation_time_ms: float


class EvaluationError(Exception):
    """Exception raised during policy evaluation."""
    pass


class PolicyEvaluator:
    """Evaluates Policy DSL against input data."""
    
    def __init__(self):
        self.built_in_functions = self._register_built_in_functions()
        self.context_stack: List[Dict[str, Any]] = []
    
    def evaluate_policy(self, policy: PolicyNode, data: Dict[str, Any], 
                       context: Optional[Dict[str, Any]] = None) -> EvaluationResult:
        """Evaluate a policy against input data."""
        if context is None:
            context = {}
        
        # Set up evaluation context
        self.context_stack = [data, context]
        
        matched_rules = []
        all_actions = []
        allowed = True  # Default to allow unless explicitly denied
        
        # Sort rules by priority (higher priority first)
        sorted_rules = sorted(policy.rules, key=lambda r: r.priority, reverse=True)
        
        for rule in sorted_rules:
            if not rule.enabled:
                continue
            
            try:
                rule_result = self._evaluate_rule(rule)
                if rule_result.matched:
                    matched_rules.append(rule_result.rule_name)
                    all_actions.extend(rule_result.actions)
                    
                    # Check for deny actions (they override allow)
                    for action in rule_result.actions:
                        if action.get('type') == ActionType.DENY.value:
                            allowed = False
            
            except Exception as e:
                raise EvaluationError(f"Error evaluating rule '{rule.name}': {str(e)}")
        
        return EvaluationResult(
            policy_name=policy.name,
            matched_rules=matched_rules,
            actions=all_actions,
            allowed=allowed,
            metadata=policy.metadata
        )
    
    def _evaluate_rule(self, rule: RuleNode) -> RuleResult:
        """Evaluate a single rule."""
        import time
        start_time = time.time()
        
        # Evaluate the condition
        condition_result = self._evaluate_condition(rule.condition)
        
        actions = []
        if condition_result:
            # Execute actions
            for action_node in rule.actions:
                action_result = self._evaluate_action(action_node)
                actions.append(action_result)
        
        end_time = time.time()
        evaluation_time_ms = (end_time - start_time) * 1000
        
        return RuleResult(
            rule_name=rule.name,
            matched=condition_result,
            actions=actions,
            evaluation_time_ms=evaluation_time_ms
        )
    
    def _evaluate_condition(self, condition: ConditionNode) -> bool:
        """Evaluate a condition and return boolean result."""
        result = self._evaluate_expression(condition.expression)
        
        # Convert result to boolean
        if isinstance(result, bool):
            return result
        elif result is None:
            return False
        elif isinstance(result, (int, float)):
            return result != 0
        elif isinstance(result, str):
            return len(result) > 0
        elif isinstance(result, (list, dict)):
            return len(result) > 0
        else:
            return bool(result)
    
    def _evaluate_action(self, action: ActionNode) -> Dict[str, Any]:
        """Evaluate an action and return action details."""
        return {
            'type': action.action_type.value,
            'parameters': action.parameters,
            'line': action.line,
            'column': action.column
        }
    
    def _evaluate_expression(self, expr: ExpressionNode) -> Any:
        """Evaluate an expression and return the result."""
        if isinstance(expr, LiteralNode):
            return expr.value
        
        elif isinstance(expr, IdentifierNode):
            return self._resolve_identifier(expr)
        
        elif isinstance(expr, BinaryExpressionNode):
            return self._evaluate_binary_expression(expr)
        
        elif isinstance(expr, UnaryExpressionNode):
            return self._evaluate_unary_expression(expr)
        
        elif isinstance(expr, FunctionCallNode):
            return self._evaluate_function_call(expr)
        
        elif isinstance(expr, ListNode):
            return [self._evaluate_expression(elem) for elem in expr.elements]
        
        elif isinstance(expr, DictNode):
            result = {}
            for key_expr, value_expr in expr.pairs:
                key = self._evaluate_expression(key_expr)
                value = self._evaluate_expression(value_expr)
                result[key] = value
            return result
        
        else:
            raise EvaluationError(f"Unknown expression type: {type(expr)}")
    
    def _evaluate_binary_expression(self, expr: BinaryExpressionNode) -> Any:
        """Evaluate a binary expression."""
        left = self._evaluate_expression(expr.left)
        
        # Short-circuit evaluation for logical operators
        if expr.operator == Operator.AND:
            if not self._to_boolean(left):
                return False
            right = self._evaluate_expression(expr.right)
            return self._to_boolean(right)
        
        elif expr.operator == Operator.OR:
            if self._to_boolean(left):
                return True
            right = self._evaluate_expression(expr.right)
            return self._to_boolean(right)
        
        # Evaluate right side for other operators
        right = self._evaluate_expression(expr.right)
        
        # Comparison operators
        if expr.operator == Operator.EQUALS:
            return left == right
        elif expr.operator == Operator.NOT_EQUALS:
            return left != right
        elif expr.operator == Operator.GREATER_THAN:
            return left > right
        elif expr.operator == Operator.LESS_THAN:
            return left < right
        elif expr.operator == Operator.GREATER_EQUAL:
            return left >= right
        elif expr.operator == Operator.LESS_EQUAL:
            return left <= right
        
        # String operators
        elif expr.operator == Operator.CONTAINS:
            return self._string_contains(left, right)
        elif expr.operator == Operator.MATCHES:
            return self._string_matches(left, right)
        elif expr.operator == Operator.STARTS_WITH:
            return self._string_starts_with(left, right)
        elif expr.operator == Operator.ENDS_WITH:
            return self._string_ends_with(left, right)
        
        # Collection operators
        elif expr.operator == Operator.IN:
            return left in right
        elif expr.operator == Operator.NOT_IN:
            return left not in right
        
        else:
            raise EvaluationError(f"Unknown binary operator: {expr.operator}")
    
    def _evaluate_unary_expression(self, expr: UnaryExpressionNode) -> Any:
        """Evaluate a unary expression."""
        operand = self._evaluate_expression(expr.operand)
        
        if expr.operator == Operator.NOT:
            return not self._to_boolean(operand)
        else:
            raise EvaluationError(f"Unknown unary operator: {expr.operator}")
    
    def _evaluate_function_call(self, expr: FunctionCallNode) -> Any:
        """Evaluate a function call."""
        function_name = expr.function_name
        
        if function_name not in self.built_in_functions:
            raise EvaluationError(f"Unknown function: {function_name}")
        
        # Evaluate arguments
        args = [self._evaluate_expression(arg) for arg in expr.arguments]
        
        # Call the function
        function = self.built_in_functions[function_name]
        return function(*args)
    
    def _resolve_identifier(self, identifier: IdentifierNode) -> Any:
        """Resolve an identifier to its value in the current context."""
        name = identifier.name
        path = identifier.path or []
        
        # Search through context stack (most recent first)
        for context in reversed(self.context_stack):
            if name in context:
                value = context[name]
                
                # Navigate through path if specified
                for field in path:
                    if isinstance(value, dict) and field in value:
                        value = value[field]
                    elif hasattr(value, field):
                        value = getattr(value, field)
                    else:
                        raise EvaluationError(f"Field '{field}' not found in {name}")
                
                return value
        
        raise EvaluationError(f"Identifier '{name}' not found in context")
    
    def _to_boolean(self, value: Any) -> bool:
        """Convert a value to boolean."""
        if isinstance(value, bool):
            return value
        elif value is None:
            return False
        elif isinstance(value, (int, float)):
            return value != 0
        elif isinstance(value, str):
            return len(value) > 0
        elif isinstance(value, (list, dict)):
            return len(value) > 0
        else:
            return bool(value)
    
    def _string_contains(self, haystack: Any, needle: Any) -> bool:
        """Check if haystack contains needle."""
        if not isinstance(haystack, str) or not isinstance(needle, str):
            return False
        return needle in haystack
    
    def _string_matches(self, text: Any, pattern: Any) -> bool:
        """Check if text matches regex pattern."""
        if not isinstance(text, str) or not isinstance(pattern, str):
            return False
        try:
            return bool(re.search(pattern, text))
        except re.error:
            raise EvaluationError(f"Invalid regex pattern: {pattern}")
    
    def _string_starts_with(self, text: Any, prefix: Any) -> bool:
        """Check if text starts with prefix."""
        if not isinstance(text, str) or not isinstance(prefix, str):
            return False
        return text.startswith(prefix)
    
    def _string_ends_with(self, text: Any, suffix: Any) -> bool:
        """Check if text ends with suffix."""
        if not isinstance(text, str) or not isinstance(suffix, str):
            return False
        return text.endswith(suffix)
    
    def _register_built_in_functions(self) -> Dict[str, Callable]:
        """Register built-in functions available in Policy DSL."""
        return {
            'len': len,
            'lower': lambda s: s.lower() if isinstance(s, str) else s,
            'upper': lambda s: s.upper() if isinstance(s, str) else s,
            'strip': lambda s: s.strip() if isinstance(s, str) else s,
            'split': lambda s, sep=' ': s.split(sep) if isinstance(s, str) else [],
            'join': lambda lst, sep='': sep.join(str(x) for x in lst) if isinstance(lst, list) else '',
            'type': lambda x: type(x).__name__,
            'str': str,
            'int': int,
            'float': float,
            'bool': bool,
            'abs': abs,
            'min': min,
            'max': max,
            'sum': sum,
            'any': any,
            'all': all,
            'sorted': sorted,
            'reversed': lambda x: list(reversed(x)) if hasattr(x, '__reversed__') else x,
            
            # PII detection functions
            'is_email': self._is_email,
            'is_phone': self._is_phone,
            'is_ssn': self._is_ssn,
            'is_credit_card': self._is_credit_card,
            'contains_pii': self._contains_pii,
            
            # Utility functions
            'now': self._now,
            'today': self._today,
            'uuid': self._generate_uuid,
        }
    
    def _is_email(self, text: str) -> bool:
        """Check if text looks like an email address."""
        if not isinstance(text, str):
            return False
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        return bool(re.search(email_pattern, text))
    
    def _is_phone(self, text: str) -> bool:
        """Check if text looks like a phone number."""
        if not isinstance(text, str):
            return False
        # Various phone number patterns
        patterns = [
            r'\b\d{3}-\d{3}-\d{4}\b',  # 123-456-7890
            r'\b\(\d{3}\)\s*\d{3}-\d{4}\b',  # (123) 456-7890
            r'\b\d{10}\b',  # 1234567890
            r'\b\+1\s*\d{3}\s*\d{3}\s*\d{4}\b',  # +1 123 456 7890
        ]
        return any(re.search(pattern, text) for pattern in patterns)
    
    def _is_ssn(self, text: str) -> bool:
        """Check if text looks like a Social Security Number."""
        if not isinstance(text, str):
            return False
        ssn_pattern = r'\b\d{3}-\d{2}-\d{4}\b'
        return bool(re.search(ssn_pattern, text))
    
    def _is_credit_card(self, text: str) -> bool:
        """Check if text looks like a credit card number."""
        if not isinstance(text, str):
            return False
        # Credit card patterns (with or without spaces/dashes)
        cc_pattern = r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b'
        return bool(re.search(cc_pattern, text))
    
    def _contains_pii(self, text: str) -> bool:
        """Check if text contains any PII."""
        if not isinstance(text, str):
            return False
        return (self._is_email(text) or self._is_phone(text) or 
                self._is_ssn(text) or self._is_credit_card(text))
    
    def _now(self) -> float:
        """Get current timestamp."""
        import time
        return time.time()
    
    def _today(self) -> str:
        """Get today's date as ISO string."""
        from datetime import date
        return date.today().isoformat()
    
    def _generate_uuid(self) -> str:
        """Generate a UUID."""
        import uuid
        return str(uuid.uuid4())