"""
Parser for the Policy DSL.

This module converts tokens from the lexer into an Abstract Syntax Tree (AST).
"""

from typing import List, Optional, Dict, Any
try:
    from .lexer import Token, TokenType, Lexer
    from .ast_nodes import (
        PolicyNode, RuleNode, ConditionNode, ActionNode, ExpressionNode,
        BinaryExpressionNode, UnaryExpressionNode, LiteralNode, IdentifierNode,
        FunctionCallNode, ListNode, DictNode, Operator, ActionType
    )
except ImportError:
    from lexer import Token, TokenType, Lexer
    from ast_nodes import (
        PolicyNode, RuleNode, ConditionNode, ActionNode, ExpressionNode,
        BinaryExpressionNode, UnaryExpressionNode, LiteralNode, IdentifierNode,
        FunctionCallNode, ListNode, DictNode, Operator, ActionType
    )


class ParseError(Exception):
    """Exception raised by the parser for syntax errors."""
    
    def __init__(self, message: str, token: Optional[Token] = None):
        self.message = message
        self.token = token
        if token:
            super().__init__(f"Parse error at {token.line}:{token.column}: {message}")
        else:
            super().__init__(f"Parse error: {message}")


class Parser:
    """Parser for the Policy DSL."""
    
    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.position = 0
        self.current_token = tokens[0] if tokens else None
    
    def parse(self) -> PolicyNode:
        """Parse tokens into a Policy AST."""
        return self.parse_policy()
    
    def parse_policy(self) -> PolicyNode:
        """Parse a complete policy definition."""
        # Expect: policy "name" { ... }
        self.expect_keyword("policy")
        
        # Policy name (string literal)
        name_token = self.expect(TokenType.STRING)
        name = name_token.value
        
        self.expect(TokenType.LBRACE)
        
        # Parse policy metadata and rules
        description = None
        rules = []
        metadata = {}
        
        while not self.check(TokenType.RBRACE) and not self.is_at_end():
            if self.check_keyword("description"):
                self.advance()  # consume 'description'
                self.expect(TokenType.COLON)
                desc_token = self.expect(TokenType.STRING)
                description = desc_token.value
            elif self.check_keyword("rule"):
                rules.append(self.parse_rule())
            elif self.check(TokenType.IDENTIFIER):
                # Parse metadata key-value pairs
                key_token = self.expect(TokenType.IDENTIFIER)
                self.expect(TokenType.COLON)
                value = self.parse_literal_value()
                metadata[key_token.value] = value
            else:
                # Skip unexpected tokens (like newlines)
                self.advance()
        
        self.expect(TokenType.RBRACE)
        
        node = PolicyNode(
            name=name,
            description=description,
            rules=rules,
            metadata=metadata
        )
        node.line = name_token.line
        node.column = name_token.column
        return node
    
    def parse_rule(self) -> RuleNode:
        """Parse a rule definition."""
        # Expect: rule "name" { when ... then ... }
        rule_token = self.expect_keyword("rule")
        
        name_token = self.expect(TokenType.STRING)
        name = name_token.value
        
        self.expect(TokenType.LBRACE)
        
        # Parse rule body
        condition = None
        actions = []
        priority = 0
        enabled = True
        
        while not self.check(TokenType.RBRACE) and not self.is_at_end():
            if self.check_keyword("when"):
                condition = self.parse_condition()
            elif self.check_keyword("then"):
                actions.extend(self.parse_actions())
            elif self.check_keyword("priority"):
                self.advance()
                self.expect(TokenType.COLON)
                priority_token = self.expect(TokenType.NUMBER)
                priority = int(priority_token.value)
            elif self.check_keyword("enabled"):
                self.advance()
                self.expect(TokenType.COLON)
                enabled_token = self.expect(TokenType.BOOLEAN)
                enabled = enabled_token.value.lower() == "true"
            else:
                # Skip unexpected tokens (like newlines)
                self.advance()
        
        self.expect(TokenType.RBRACE)
        
        if condition is None:
            self.error("Rule must have a 'when' condition")
        
        if not actions:
            self.error("Rule must have at least one 'then' action")
        
        node = RuleNode(
            name=name,
            condition=condition,
            actions=actions,
            priority=priority,
            enabled=enabled
        )
        node.line = rule_token.line
        node.column = rule_token.column
        return node
    
    def parse_condition(self) -> ConditionNode:
        """Parse a condition (when clause)."""
        when_token = self.expect_keyword("when")
        expression = self.parse_expression()
        
        node = ConditionNode(expression=expression)
        node.line = when_token.line
        node.column = when_token.column
        return node
    
    def parse_actions(self) -> List[ActionNode]:
        """Parse actions (then clause)."""
        self.expect_keyword("then")
        actions = []
        
        # Actions can be a single action or a block of actions
        if self.check(TokenType.LBRACE):
            self.advance()  # consume '{'
            while not self.check(TokenType.RBRACE) and not self.is_at_end():
                if self.check_keyword("log") or self.check_keyword("alert") or self.check_keyword("allow") or \
                   self.check_keyword("deny") or self.check_keyword("redact") or self.check_keyword("require_approval"):
                    actions.append(self.parse_action())
                else:
                    # Skip unexpected tokens (like newlines)
                    self.advance()
            self.expect(TokenType.RBRACE)
        else:
            actions.append(self.parse_action())
        
        return actions
    
    def parse_action(self) -> ActionNode:
        """Parse a single action."""
        action_token = self.current_token
        
        # Parse action type
        if self.check_keyword("allow"):
            action_type = ActionType.ALLOW
            self.advance()
        elif self.check_keyword("deny"):
            action_type = ActionType.DENY
            self.advance()
        elif self.check_keyword("redact"):
            action_type = ActionType.REDACT
            self.advance()
        elif self.check_keyword("log"):
            action_type = ActionType.LOG
            self.advance()
        elif self.check_keyword("alert"):
            action_type = ActionType.ALERT
            self.advance()
        elif self.check_keyword("require_approval"):
            action_type = ActionType.REQUIRE_APPROVAL
            self.advance()
        else:
            self.error(f"Expected action type, got: {self.current_token.value}")
        
        # Parse action parameters
        parameters = {}
        if self.check(TokenType.LPAREN):
            parameters = self.parse_action_parameters()
        
        node = ActionNode(
            action_type=action_type,
            parameters=parameters
        )
        node.line = action_token.line
        node.column = action_token.column
        return node
    
    def parse_action_parameters(self) -> Dict[str, Any]:
        """Parse action parameters in parentheses."""
        self.expect(TokenType.LPAREN)
        parameters = {}
        
        while not self.check(TokenType.RPAREN) and not self.is_at_end():
            # Parse key=value pairs
            key_token = self.expect(TokenType.IDENTIFIER)
            self.expect(TokenType.ASSIGN)
            value = self.parse_literal_value()
            parameters[key_token.value] = value
            
            if self.check(TokenType.COMMA):
                self.advance()
        
        self.expect(TokenType.RPAREN)
        return parameters
    
    def parse_expression(self) -> ExpressionNode:
        """Parse an expression with operator precedence."""
        return self.parse_or_expression()
    
    def parse_or_expression(self) -> ExpressionNode:
        """Parse OR expressions (lowest precedence)."""
        expr = self.parse_and_expression()
        
        while self.check(TokenType.OR):
            operator_token = self.advance()
            right = self.parse_and_expression()
            node = BinaryExpressionNode(
                left=expr,
                operator=Operator.OR,
                right=right
            )
            node.line = operator_token.line
            node.column = operator_token.column
            expr = node
        
        return expr
    
    def parse_and_expression(self) -> ExpressionNode:
        """Parse AND expressions."""
        expr = self.parse_equality_expression()
        
        while self.check(TokenType.AND):
            operator_token = self.advance()
            right = self.parse_equality_expression()
            node = BinaryExpressionNode(
                left=expr,
                operator=Operator.AND,
                right=right
            )
            node.line = operator_token.line
            node.column = operator_token.column
            expr = node
        
        return expr
    
    def parse_equality_expression(self) -> ExpressionNode:
        """Parse equality expressions (==, !=)."""
        expr = self.parse_comparison_expression()
        
        while self.check(TokenType.EQUALS) or self.check(TokenType.NOT_EQUALS):
            operator_token = self.advance()
            right = self.parse_comparison_expression()
            
            operator = Operator.EQUALS if operator_token.type == TokenType.EQUALS else Operator.NOT_EQUALS
            node = BinaryExpressionNode(
                left=expr,
                operator=operator,
                right=right
            )
            node.line = operator_token.line
            node.column = operator_token.column
            expr = node
        
        return expr
    
    def parse_comparison_expression(self) -> ExpressionNode:
        """Parse comparison expressions (<, >, <=, >=)."""
        expr = self.parse_string_expression()
        
        while (self.check(TokenType.GREATER_THAN) or self.check(TokenType.LESS_THAN) or
               self.check(TokenType.GREATER_EQUAL) or self.check(TokenType.LESS_EQUAL)):
            operator_token = self.advance()
            right = self.parse_string_expression()
            
            operator_map = {
                TokenType.GREATER_THAN: Operator.GREATER_THAN,
                TokenType.LESS_THAN: Operator.LESS_THAN,
                TokenType.GREATER_EQUAL: Operator.GREATER_EQUAL,
                TokenType.LESS_EQUAL: Operator.LESS_EQUAL,
            }
            
            node = BinaryExpressionNode(
                left=expr,
                operator=operator_map[operator_token.type],
                right=right
            )
            node.line = operator_token.line
            node.column = operator_token.column
            expr = node
        
        return expr
    
    def parse_string_expression(self) -> ExpressionNode:
        """Parse string operations (contains, matches, etc.)."""
        expr = self.parse_membership_expression()
        
        while (self.check(TokenType.CONTAINS) or self.check(TokenType.MATCHES) or
               self.check(TokenType.STARTS_WITH) or self.check(TokenType.ENDS_WITH)):
            operator_token = self.advance()
            right = self.parse_membership_expression()
            
            operator_map = {
                TokenType.CONTAINS: Operator.CONTAINS,
                TokenType.MATCHES: Operator.MATCHES,
                TokenType.STARTS_WITH: Operator.STARTS_WITH,
                TokenType.ENDS_WITH: Operator.ENDS_WITH,
            }
            
            node = BinaryExpressionNode(
                left=expr,
                operator=operator_map[operator_token.type],
                right=right
            )
            node.line = operator_token.line
            node.column = operator_token.column
            expr = node
        
        return expr
    
    def parse_membership_expression(self) -> ExpressionNode:
        """Parse membership expressions (in, not_in)."""
        expr = self.parse_unary_expression()
        
        while self.check(TokenType.IN) or self.check(TokenType.NOT_IN):
            operator_token = self.advance()
            right = self.parse_unary_expression()
            
            operator = Operator.IN if operator_token.type == TokenType.IN else Operator.NOT_IN
            node = BinaryExpressionNode(
                left=expr,
                operator=operator,
                right=right
            )
            node.line = operator_token.line
            node.column = operator_token.column
            expr = node
        
        return expr
    
    def parse_unary_expression(self) -> ExpressionNode:
        """Parse unary expressions (not)."""
        if self.check(TokenType.NOT):
            operator_token = self.advance()
            operand = self.parse_unary_expression()
            node = UnaryExpressionNode(
                operator=Operator.NOT,
                operand=operand
            )
            node.line = operator_token.line
            node.column = operator_token.column
            return node
        
        return self.parse_primary_expression()
    
    def parse_primary_expression(self) -> ExpressionNode:
        """Parse primary expressions (literals, identifiers, function calls, etc.)."""
        if self.check(TokenType.STRING) or self.check(TokenType.NUMBER) or self.check(TokenType.BOOLEAN) or self.check(TokenType.NULL):
            return self.parse_literal()
        
        if self.check(TokenType.IDENTIFIER):
            return self.parse_identifier_or_function_call()
        
        if self.check(TokenType.LBRACKET):
            return self.parse_list()
        
        if self.check(TokenType.LBRACE):
            return self.parse_dict()
        
        if self.check(TokenType.LPAREN):
            self.advance()  # consume '('
            expr = self.parse_expression()
            self.expect(TokenType.RPAREN)
            return expr
        
        self.error(f"Unexpected token: {self.current_token.value}")
    
    def parse_literal(self) -> LiteralNode:
        """Parse a literal value."""
        token = self.advance()
        
        if token.type == TokenType.STRING:
            node = LiteralNode(value=token.value, data_type="string")
            node.line = token.line
            node.column = token.column
            return node
        elif token.type == TokenType.NUMBER:
            # Determine if it's an integer or float
            if '.' in token.value:
                value = float(token.value)
                data_type = "float"
            else:
                value = int(token.value)
                data_type = "int"
            node = LiteralNode(value=value, data_type=data_type)
            node.line = token.line
            node.column = token.column
            return node
        elif token.type == TokenType.BOOLEAN:
            value = token.value.lower() == "true"
            node = LiteralNode(value=value, data_type="boolean")
            node.line = token.line
            node.column = token.column
            return node
        elif token.type == TokenType.NULL:
            node = LiteralNode(value=None, data_type="null")
            node.line = token.line
            node.column = token.column
            return node
        
        self.error(f"Invalid literal: {token.value}")
    
    def parse_identifier_or_function_call(self) -> ExpressionNode:
        """Parse an identifier or function call."""
        name_token = self.expect(TokenType.IDENTIFIER)
        
        # Check for function call
        if self.check(TokenType.LPAREN):
            return self.parse_function_call(name_token.value, name_token)
        
        # Check for field access (dot notation)
        path = [name_token.value]
        while self.check(TokenType.DOT):
            self.advance()  # consume '.'
            field_token = self.expect(TokenType.IDENTIFIER)
            path.append(field_token.value)
        
        node = IdentifierNode(
            name=path[0],
            path=path[1:] if len(path) > 1 else None
        )
        node.line = name_token.line
        node.column = name_token.column
        return node
    
    def parse_function_call(self, function_name: str, name_token: Token) -> FunctionCallNode:
        """Parse a function call."""
        self.expect(TokenType.LPAREN)
        
        arguments = []
        while not self.check(TokenType.RPAREN) and not self.is_at_end():
            arguments.append(self.parse_expression())
            if self.check(TokenType.COMMA):
                self.advance()
        
        self.expect(TokenType.RPAREN)
        
        node = FunctionCallNode(
            function_name=function_name,
            arguments=arguments
        )
        node.line = name_token.line
        node.column = name_token.column
        return node
    
    def parse_list(self) -> ListNode:
        """Parse a list literal."""
        bracket_token = self.expect(TokenType.LBRACKET)
        
        elements = []
        while not self.check(TokenType.RBRACKET) and not self.is_at_end():
            elements.append(self.parse_expression())
            if self.check(TokenType.COMMA):
                self.advance()
        
        self.expect(TokenType.RBRACKET)
        
        node = ListNode(elements=elements)
        node.line = bracket_token.line
        node.column = bracket_token.column
        return node
    
    def parse_dict(self) -> DictNode:
        """Parse a dictionary literal."""
        brace_token = self.expect(TokenType.LBRACE)
        
        pairs = []
        while not self.check(TokenType.RBRACE) and not self.is_at_end():
            key = self.parse_expression()
            self.expect(TokenType.COLON)
            value = self.parse_expression()
            pairs.append((key, value))
            
            if self.check(TokenType.COMMA):
                self.advance()
        
        self.expect(TokenType.RBRACE)
        
        node = DictNode(pairs=pairs)
        node.line = brace_token.line
        node.column = brace_token.column
        return node
    
    def parse_literal_value(self) -> Any:
        """Parse a literal value and return its Python representation."""
        if self.check(TokenType.STRING):
            return self.advance().value
        elif self.check(TokenType.NUMBER):
            token = self.advance()
            return float(token.value) if '.' in token.value else int(token.value)
        elif self.check(TokenType.BOOLEAN):
            return self.advance().value.lower() == "true"
        elif self.check(TokenType.NULL):
            self.advance()
            return None
        elif self.check(TokenType.LBRACKET):
            # Parse list literal
            list_node = self.parse_list()
            return [self._evaluate_literal_expression(elem) for elem in list_node.elements]
        else:
            self.error(f"Expected literal value, got: {self.current_token.value}")
    
    def _evaluate_literal_expression(self, expr) -> Any:
        """Evaluate a literal expression to get its value."""
        if isinstance(expr, LiteralNode):
            return expr.value
        elif isinstance(expr, ListNode):
            return [self._evaluate_literal_expression(elem) for elem in expr.elements]
        else:
            # For now, just return the string representation
            return str(expr)
    
    # Helper methods
    
    def advance(self) -> Token:
        """Consume and return the current token."""
        if not self.is_at_end():
            self.position += 1
            if self.position < len(self.tokens):
                self.current_token = self.tokens[self.position]
        return self.tokens[self.position - 1]
    
    def check(self, token_type: TokenType) -> bool:
        """Check if the current token is of the given type."""
        if self.is_at_end():
            return False
        return self.current_token.type == token_type
    
    def check_keyword(self, keyword: str) -> bool:
        """Check if the current token is a specific keyword."""
        return (self.check(TokenType.KEYWORD) and 
                self.current_token.value.lower() == keyword.lower())
    
    def expect(self, token_type: TokenType) -> Token:
        """Expect a token of the given type and consume it."""
        if self.check(token_type):
            return self.advance()
        
        expected = token_type.value
        actual = self.current_token.type.value if self.current_token else "EOF"
        self.error(f"Expected {expected}, got {actual}")
    
    def expect_keyword(self, keyword: str) -> Token:
        """Expect a specific keyword and consume it."""
        if self.check_keyword(keyword):
            return self.advance()
        
        actual = self.current_token.value if self.current_token else "EOF"
        self.error(f"Expected keyword '{keyword}', got '{actual}'")
    
    def is_at_end(self) -> bool:
        """Check if we've reached the end of tokens."""
        return (self.position >= len(self.tokens) or 
                self.current_token.type == TokenType.EOF)
    
    def error(self, message: str):
        """Raise a parse error."""
        raise ParseError(message, self.current_token)


def parse_policy(source_code: str) -> PolicyNode:
    """Parse Policy DSL source code into an AST."""
    lexer = Lexer(source_code)
    tokens = lexer.tokenize()
    parser = Parser(tokens)
    return parser.parse()