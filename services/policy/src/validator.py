"""
Policy validation framework for the Policy DSL.

This module provides validation for Policy DSL syntax, semantics, and best practices.
"""

from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass
from enum import Enum
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


class ValidationLevel(Enum):
    """Levels of validation severity."""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class ValidationIssue:
    """Represents a validation issue found in a policy."""
    level: ValidationLevel
    message: str
    node: Optional[ASTNode] = None
    line: int = 0
    column: int = 0
    rule_name: Optional[str] = None
    
    def __str__(self):
        location = f"{self.line}:{self.column}" if self.line > 0 else "unknown"
        rule_info = f" in rule '{self.rule_name}'" if self.rule_name else ""
        return f"{self.level.value.upper()} at {location}{rule_info}: {self.message}"


@dataclass
class ValidationResult:
    """Result of policy validation."""
    is_valid: bool
    issues: List[ValidationIssue]
    
    @property
    def errors(self) -> List[ValidationIssue]:
        """Get only error-level issues."""
        return [issue for issue in self.issues if issue.level == ValidationLevel.ERROR]
    
    @property
    def warnings(self) -> List[ValidationIssue]:
        """Get only warning-level issues."""
        return [issue for issue in self.issues if issue.level == ValidationLevel.WARNING]
    
    @property
    def infos(self) -> List[ValidationIssue]:
        """Get only info-level issues."""
        return [issue for issue in self.issues if issue.level == ValidationLevel.INFO]


class PolicyValidator:
    """Validates Policy DSL for syntax, semantics, and best practices."""
    
    def __init__(self):
        self.issues: List[ValidationIssue] = []
        self.current_rule: Optional[str] = None
        self.declared_identifiers: Set[str] = set()
        self.used_identifiers: Set[str] = set()
        self.built_in_functions = {
            'len', 'lower', 'upper', 'strip', 'split', 'join', 'type',
            'str', 'int', 'float', 'bool', 'abs', 'min', 'max', 'sum',
            'any', 'all', 'sorted', 'reversed', 'is_email', 'is_phone',
            'is_ssn', 'is_credit_card', 'contains_pii', 'now', 'today', 'uuid'
        }
    
    def validate(self, policy: PolicyNode) -> ValidationResult:
        """Validate a complete policy."""
        self.issues = []
        self.current_rule = None
        self.declared_identifiers = set()
        self.used_identifiers = set()
        
        self._validate_policy(policy)
        
        # Check for unused identifiers
        unused = self.declared_identifiers - self.used_identifiers
        for identifier in unused:
            self.issues.append(ValidationIssue(
                level=ValidationLevel.WARNING,
                message=f"Identifier '{identifier}' is declared but never used"
            ))
        
        # Determine if policy is valid (no errors)
        has_errors = any(issue.level == ValidationLevel.ERROR for issue in self.issues)
        
        return ValidationResult(
            is_valid=not has_errors,
            issues=self.issues
        )
    
    def _validate_policy(self, policy: PolicyNode):
        """Validate a policy node."""
        # Check policy name
        if not policy.name or not policy.name.strip():
            self._add_error("Policy must have a non-empty name", policy)
        
        # Check for duplicate rule names
        rule_names = [rule.name for rule in policy.rules]
        duplicates = set([name for name in rule_names if rule_names.count(name) > 1])
        for duplicate in duplicates:
            self._add_error(f"Duplicate rule name: '{duplicate}'", policy)
        
        # Validate each rule
        for rule in policy.rules:
            self._validate_rule(rule)
        
        # Check for at least one rule
        if not policy.rules:
            self._add_warning("Policy has no rules", policy)
        
        # Validate metadata
        self._validate_metadata(policy.metadata, policy)
    
    def _validate_rule(self, rule: RuleNode):
        """Validate a rule node."""
        self.current_rule = rule.name
        
        # Check rule name
        if not rule.name or not rule.name.strip():
            self._add_error("Rule must have a non-empty name", rule)
        
        # Validate condition
        if rule.condition:
            self._validate_condition(rule.condition)
        else:
            self._add_error("Rule must have a condition", rule)
        
        # Validate actions
        if not rule.actions:
            self._add_error("Rule must have at least one action", rule)
        else:
            for action in rule.actions:
                self._validate_action(action)
        
        # Check priority range
        if rule.priority < 0 or rule.priority > 1000:
            self._add_warning(f"Rule priority {rule.priority} is outside recommended range (0-1000)", rule)
        
        self.current_rule = None
    
    def _validate_condition(self, condition: ConditionNode):
        """Validate a condition node."""
        if condition.expression:
            self._validate_expression(condition.expression)
        else:
            self._add_error("Condition must have an expression", condition)
    
    def _validate_action(self, action: ActionNode):
        """Validate an action node."""
        # Validate action-specific parameters
        if action.action_type == ActionType.REDACT:
            self._validate_redact_action(action)
        elif action.action_type == ActionType.LOG:
            self._validate_log_action(action)
        elif action.action_type == ActionType.ALERT:
            self._validate_alert_action(action)
        elif action.action_type == ActionType.REQUIRE_APPROVAL:
            self._validate_approval_action(action)
    
    def _validate_redact_action(self, action: ActionNode):
        """Validate redact action parameters."""
        params = action.parameters
        
        # Check for required parameters
        if 'field' not in params and 'pattern' not in params:
            self._add_error("Redact action must specify either 'field' or 'pattern'", action)
        
        # Validate replacement parameter
        if 'replacement' in params:
            replacement = params['replacement']
            if not isinstance(replacement, str):
                self._add_error("Redact replacement must be a string", action)
    
    def _validate_log_action(self, action: ActionNode):
        """Validate log action parameters."""
        params = action.parameters
        
        # Check log level
        if 'level' in params:
            level = params['level']
            valid_levels = {'debug', 'info', 'warning', 'error', 'critical'}
            if level not in valid_levels:
                self._add_error(f"Invalid log level '{level}'. Must be one of: {valid_levels}", action)
    
    def _validate_alert_action(self, action: ActionNode):
        """Validate alert action parameters."""
        params = action.parameters
        
        # Check for required message
        if 'message' not in params:
            self._add_error("Alert action must have a 'message' parameter", action)
        
        # Validate severity
        if 'severity' in params:
            severity = params['severity']
            valid_severities = {'low', 'medium', 'high', 'critical'}
            if severity not in valid_severities:
                self._add_error(f"Invalid alert severity '{severity}'. Must be one of: {valid_severities}", action)
    
    def _validate_approval_action(self, action: ActionNode):
        """Validate approval action parameters."""
        params = action.parameters
        
        # Check for required approvers
        if 'approvers' not in params:
            self._add_error("Approval action must specify 'approvers'", action)
        else:
            approvers = params['approvers']
            if not isinstance(approvers, list) or not approvers:
                self._add_error("Approvers must be a non-empty list", action)
    
    def _validate_expression(self, expr: ExpressionNode):
        """Validate an expression node."""
        if isinstance(expr, BinaryExpressionNode):
            self._validate_binary_expression(expr)
        elif isinstance(expr, UnaryExpressionNode):
            self._validate_unary_expression(expr)
        elif isinstance(expr, IdentifierNode):
            self._validate_identifier(expr)
        elif isinstance(expr, FunctionCallNode):
            self._validate_function_call(expr)
        elif isinstance(expr, ListNode):
            self._validate_list(expr)
        elif isinstance(expr, DictNode):
            self._validate_dict(expr)
        elif isinstance(expr, LiteralNode):
            self._validate_literal(expr)
    
    def _validate_binary_expression(self, expr: BinaryExpressionNode):
        """Validate a binary expression."""
        self._validate_expression(expr.left)
        self._validate_expression(expr.right)
        
        # Type compatibility checks
        self._check_operator_compatibility(expr.operator, expr)
    
    def _validate_unary_expression(self, expr: UnaryExpressionNode):
        """Validate a unary expression."""
        self._validate_expression(expr.operand)
        
        # Check operator compatibility
        if expr.operator == Operator.NOT:
            # NOT operator can be applied to any expression
            pass
        else:
            self._add_error(f"Unknown unary operator: {expr.operator}", expr)
    
    def _validate_identifier(self, identifier: IdentifierNode):
        """Validate an identifier."""
        self.used_identifiers.add(identifier.name)
        
        # Check for common field names that might indicate PII
        pii_fields = {'email', 'phone', 'ssn', 'social_security_number', 'credit_card', 'password'}
        if identifier.name.lower() in pii_fields:
            self._add_info(f"Identifier '{identifier.name}' may contain PII - consider redaction policies", identifier)
        
        # Check for path access on potentially null values
        if identifier.path and len(identifier.path) > 3:
            self._add_warning(f"Deep field access '{identifier.name}.{'.'.join(identifier.path)}' may be fragile", identifier)
    
    def _validate_function_call(self, func_call: FunctionCallNode):
        """Validate a function call."""
        function_name = func_call.function_name
        
        # Check if function exists
        if function_name not in self.built_in_functions:
            self._add_error(f"Unknown function: '{function_name}'", func_call)
        
        # Validate arguments
        for arg in func_call.arguments:
            self._validate_expression(arg)
        
        # Function-specific validation
        self._validate_function_arguments(func_call)
    
    def _validate_function_arguments(self, func_call: FunctionCallNode):
        """Validate function-specific argument requirements."""
        function_name = func_call.function_name
        arg_count = len(func_call.arguments)
        
        # Define expected argument counts for built-in functions
        function_args = {
            'len': 1,
            'lower': 1,
            'upper': 1,
            'strip': 1,
            'type': 1,
            'str': 1,
            'int': 1,
            'float': 1,
            'bool': 1,
            'abs': 1,
            'is_email': 1,
            'is_phone': 1,
            'is_ssn': 1,
            'is_credit_card': 1,
            'contains_pii': 1,
            'now': 0,
            'today': 0,
            'uuid': 0,
        }
        
        if function_name in function_args:
            expected = function_args[function_name]
            if arg_count != expected:
                self._add_error(f"Function '{function_name}' expects {expected} arguments, got {arg_count}", func_call)
    
    def _validate_list(self, list_node: ListNode):
        """Validate a list literal."""
        for element in list_node.elements:
            self._validate_expression(element)
        
        # Check for very large lists
        if len(list_node.elements) > 100:
            self._add_warning(f"Large list with {len(list_node.elements)} elements may impact performance", list_node)
    
    def _validate_dict(self, dict_node: DictNode):
        """Validate a dictionary literal."""
        keys = []
        for key_expr, value_expr in dict_node.pairs:
            self._validate_expression(key_expr)
            self._validate_expression(value_expr)
            
            # Check for duplicate keys (if they're literals)
            if isinstance(key_expr, LiteralNode):
                if key_expr.value in keys:
                    self._add_error(f"Duplicate key in dictionary: {key_expr.value}", dict_node)
                keys.append(key_expr.value)
    
    def _validate_literal(self, literal: LiteralNode):
        """Validate a literal value."""
        # Check for potential PII in string literals
        if literal.data_type == "string" and isinstance(literal.value, str):
            if self._looks_like_pii(literal.value):
                self._add_warning(f"String literal may contain PII: '{literal.value[:20]}...'", literal)
    
    def _validate_metadata(self, metadata: Dict[str, Any], node: ASTNode):
        """Validate policy metadata."""
        # Check for recommended metadata fields
        recommended_fields = {'version', 'author', 'description', 'tags'}
        missing_fields = recommended_fields - set(metadata.keys())
        
        if missing_fields:
            self._add_info(f"Consider adding metadata fields: {missing_fields}", node)
        
        # Validate specific metadata values
        if 'version' in metadata:
            version = metadata['version']
            if not isinstance(version, str) or not version.strip():
                self._add_warning("Version should be a non-empty string", node)
    
    def _check_operator_compatibility(self, operator: Operator, expr: BinaryExpressionNode):
        """Check if operator is compatible with operand types."""
        # This is a simplified check - in a real implementation, you'd want
        # more sophisticated type inference
        
        if operator in (Operator.CONTAINS, Operator.MATCHES, Operator.STARTS_WITH, Operator.ENDS_WITH):
            # String operations should warn if used with non-string literals
            if isinstance(expr.left, LiteralNode) and expr.left.data_type != "string":
                self._add_warning(f"String operator '{operator.value}' used with non-string operand", expr)
        
        elif operator in (Operator.GREATER_THAN, Operator.LESS_THAN, Operator.GREATER_EQUAL, Operator.LESS_EQUAL):
            # Numeric comparisons should warn about type mismatches
            if (isinstance(expr.left, LiteralNode) and isinstance(expr.right, LiteralNode) and
                expr.left.data_type in ("int", "float") and expr.right.data_type == "string"):
                self._add_warning("Comparing number with string may not work as expected", expr)
    
    def _looks_like_pii(self, text: str) -> bool:
        """Check if a string looks like it might contain PII."""
        import re
        
        # Simple PII patterns
        patterns = [
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',  # Email
            r'\b\d{3}-\d{3}-\d{4}\b',  # Phone
            r'\b\d{3}-\d{2}-\d{4}\b',  # SSN
            r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b',  # Credit card
        ]
        
        return any(re.search(pattern, text) for pattern in patterns)
    
    def _add_error(self, message: str, node: Optional[ASTNode] = None):
        """Add an error-level validation issue."""
        self.issues.append(ValidationIssue(
            level=ValidationLevel.ERROR,
            message=message,
            node=node,
            line=node.line if node else 0,
            column=node.column if node else 0,
            rule_name=self.current_rule
        ))
    
    def _add_warning(self, message: str, node: Optional[ASTNode] = None):
        """Add a warning-level validation issue."""
        self.issues.append(ValidationIssue(
            level=ValidationLevel.WARNING,
            message=message,
            node=node,
            line=node.line if node else 0,
            column=node.column if node else 0,
            rule_name=self.current_rule
        ))
    
    def _add_info(self, message: str, node: Optional[ASTNode] = None):
        """Add an info-level validation issue."""
        self.issues.append(ValidationIssue(
            level=ValidationLevel.INFO,
            message=message,
            node=node,
            line=node.line if node else 0,
            column=node.column if node else 0,
            rule_name=self.current_rule
        ))