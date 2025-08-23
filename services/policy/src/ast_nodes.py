"""
Abstract Syntax Tree (AST) nodes for the Policy DSL.

This module defines the AST node types used to represent parsed Policy DSL expressions.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union
from enum import Enum


class NodeType(Enum):
    """Types of AST nodes in the Policy DSL."""
    POLICY = "policy"
    RULE = "rule"
    CONDITION = "condition"
    ACTION = "action"
    EXPRESSION = "expression"
    LITERAL = "literal"
    IDENTIFIER = "identifier"
    OPERATOR = "operator"


class Operator(Enum):
    """Supported operators in Policy DSL expressions."""
    # Comparison operators
    EQUALS = "=="
    NOT_EQUALS = "!="
    GREATER_THAN = ">"
    LESS_THAN = "<"
    GREATER_EQUAL = ">="
    LESS_EQUAL = "<="
    
    # Logical operators
    AND = "and"
    OR = "or"
    NOT = "not"
    
    # String operators
    CONTAINS = "contains"
    MATCHES = "matches"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    
    # Collection operators
    IN = "in"
    NOT_IN = "not_in"


class ActionType(Enum):
    """Types of actions that can be taken by policies."""
    ALLOW = "allow"
    DENY = "deny"
    REDACT = "redact"
    LOG = "log"
    ALERT = "alert"
    REQUIRE_APPROVAL = "require_approval"


class ASTNode(ABC):
    """Base class for all AST nodes."""
    
    def __init__(self, node_type: NodeType = None, line: int = 0, column: int = 0):
        self.node_type = node_type
        self.line = line
        self.column = column
    
    @abstractmethod
    def accept(self, visitor):
        """Accept a visitor for the visitor pattern."""
        pass


@dataclass
class PolicyNode(ASTNode):
    """Root node representing a complete policy."""
    name: str
    description: Optional[str] = None
    rules: List['RuleNode'] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        super().__init__(NodeType.POLICY)
        if self.rules is None:
            self.rules = []
        if self.metadata is None:
            self.metadata = {}
    
    def accept(self, visitor):
        return visitor.visit_policy(self)


@dataclass
class RuleNode(ASTNode):
    """Node representing a policy rule."""
    name: str
    condition: 'ConditionNode' = None
    actions: List['ActionNode'] = None
    priority: int = 0
    enabled: bool = True
    
    def __post_init__(self):
        super().__init__(NodeType.RULE)
        if self.actions is None:
            self.actions = []
    
    def accept(self, visitor):
        return visitor.visit_rule(self)


@dataclass
class ConditionNode(ASTNode):
    """Node representing a condition expression."""
    expression: 'ExpressionNode' = None
    
    def __post_init__(self):
        super().__init__(NodeType.CONDITION)
    
    def accept(self, visitor):
        return visitor.visit_condition(self)


@dataclass
class ActionNode(ASTNode):
    """Node representing an action to be taken."""
    action_type: ActionType = None
    parameters: Dict[str, Any] = None
    
    def __post_init__(self):
        super().__init__(NodeType.ACTION)
        if self.parameters is None:
            self.parameters = {}
    
    def accept(self, visitor):
        return visitor.visit_action(self)


@dataclass
class ExpressionNode(ASTNode):
    """Base class for expression nodes."""
    
    def __post_init__(self):
        super().__init__(NodeType.EXPRESSION)
    
    def accept(self, visitor):
        return visitor.visit_expression(self)


@dataclass
class BinaryExpressionNode(ExpressionNode):
    """Node representing a binary expression (left operator right)."""
    left: ExpressionNode = None
    operator: Operator = None
    right: ExpressionNode = None
    
    def accept(self, visitor):
        return visitor.visit_binary_expression(self)


@dataclass
class UnaryExpressionNode(ExpressionNode):
    """Node representing a unary expression (operator operand)."""
    operator: Operator = None
    operand: ExpressionNode = None
    
    def accept(self, visitor):
        return visitor.visit_unary_expression(self)


@dataclass
class LiteralNode(ASTNode):
    """Node representing a literal value."""
    value: Union[str, int, float, bool, None] = None
    data_type: str = "unknown"
    
    def __post_init__(self):
        super().__init__(NodeType.LITERAL)
    
    def accept(self, visitor):
        return visitor.visit_literal(self)


@dataclass
class IdentifierNode(ASTNode):
    """Node representing an identifier (variable, field name, etc.)."""
    name: str = ""
    path: Optional[List[str]] = None  # For nested field access like user.email
    
    def __post_init__(self):
        super().__init__(NodeType.IDENTIFIER)
    
    def accept(self, visitor):
        return visitor.visit_identifier(self)


@dataclass
class FunctionCallNode(ExpressionNode):
    """Node representing a function call."""
    function_name: str = ""
    arguments: List[ExpressionNode] = None
    
    def __post_init__(self):
        super().__post_init__()
        if self.arguments is None:
            self.arguments = []
    
    def accept(self, visitor):
        return visitor.visit_function_call(self)


@dataclass
class ListNode(ExpressionNode):
    """Node representing a list literal."""
    elements: List[ExpressionNode] = None
    
    def __post_init__(self):
        super().__post_init__()
        if self.elements is None:
            self.elements = []
    
    def accept(self, visitor):
        return visitor.visit_list(self)


@dataclass
class DictNode(ExpressionNode):
    """Node representing a dictionary literal."""
    pairs: List[tuple[ExpressionNode, ExpressionNode]] = None
    
    def __post_init__(self):
        super().__post_init__()
        if self.pairs is None:
            self.pairs = []
    
    def accept(self, visitor):
        return visitor.visit_dict(self)