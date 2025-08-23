"""
Lexical analyzer (tokenizer) for the Policy DSL.

This module breaks down Policy DSL source code into tokens for parsing.
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Iterator, List, Optional, Union


class TokenType(Enum):
    """Types of tokens in the Policy DSL."""
    # Literals
    STRING = "STRING"
    NUMBER = "NUMBER"
    BOOLEAN = "BOOLEAN"
    NULL = "NULL"
    
    # Identifiers and keywords
    IDENTIFIER = "IDENTIFIER"
    KEYWORD = "KEYWORD"
    
    # Operators
    EQUALS = "=="
    ASSIGN = "="
    NOT_EQUALS = "!="
    GREATER_THAN = ">"
    LESS_THAN = "<"
    GREATER_EQUAL = ">="
    LESS_EQUAL = "<="
    AND = "AND"
    OR = "OR"
    NOT = "NOT"
    CONTAINS = "CONTAINS"
    MATCHES = "MATCHES"
    STARTS_WITH = "STARTS_WITH"
    ENDS_WITH = "ENDS_WITH"
    IN = "IN"
    NOT_IN = "NOT_IN"
    
    # Punctuation
    LPAREN = "("
    RPAREN = ")"
    LBRACE = "{"
    RBRACE = "}"
    LBRACKET = "["
    RBRACKET = "]"
    COMMA = ","
    DOT = "."
    COLON = ":"
    SEMICOLON = ";"
    
    # Special
    NEWLINE = "NEWLINE"
    EOF = "EOF"
    WHITESPACE = "WHITESPACE"
    COMMENT = "COMMENT"


@dataclass
class Token:
    """Represents a token in the Policy DSL."""
    type: TokenType
    value: str
    line: int
    column: int
    
    def __str__(self):
        return f"Token({self.type.value}, '{self.value}', {self.line}:{self.column})"


class LexerError(Exception):
    """Exception raised by the lexer for invalid tokens."""
    
    def __init__(self, message: str, line: int, column: int):
        self.message = message
        self.line = line
        self.column = column
        super().__init__(f"Lexer error at {line}:{column}: {message}")


class Lexer:
    """Lexical analyzer for the Policy DSL."""
    
    # Keywords in the Policy DSL
    KEYWORDS = {
        'policy', 'rule', 'when', 'then', 'allow', 'deny', 'redact', 'log', 'alert',
        'require_approval', 'and', 'or', 'not', 'true', 'false', 'null', 'contains',
        'matches', 'starts_with', 'ends_with', 'in', 'not_in', 'if', 'else', 'endif'
    }
    
    # Token patterns (order matters for precedence)
    TOKEN_PATTERNS = [
        # Comments
        (r'#.*', TokenType.COMMENT),
        
        # Multi-character operators (must come before single-character ones)
        (r'==', TokenType.EQUALS),
        (r'!=', TokenType.NOT_EQUALS),
        (r'>=', TokenType.GREATER_EQUAL),
        (r'<=', TokenType.LESS_EQUAL),
        (r'not_in\b', TokenType.NOT_IN),
        (r'starts_with\b', TokenType.STARTS_WITH),
        (r'ends_with\b', TokenType.ENDS_WITH),
        
        # Single-character operators
        (r'>', TokenType.GREATER_THAN),
        (r'<', TokenType.LESS_THAN),
        (r'=', TokenType.ASSIGN),  # Single = for assignments
        
        # String literals (support both single and double quotes)
        (r'"(?:[^"\\]|\\.)*"', TokenType.STRING),
        (r"'(?:[^'\\]|\\.)*'", TokenType.STRING),
        
        # Numbers (integers and floats)
        (r'\d+\.\d+', TokenType.NUMBER),
        (r'\d+', TokenType.NUMBER),
        
        # Identifiers and keywords
        (r'[a-zA-Z_][a-zA-Z0-9_]*', TokenType.IDENTIFIER),
        
        # Punctuation
        (r'\(', TokenType.LPAREN),
        (r'\)', TokenType.RPAREN),
        (r'\{', TokenType.LBRACE),
        (r'\}', TokenType.RBRACE),
        (r'\[', TokenType.LBRACKET),
        (r'\]', TokenType.RBRACKET),
        (r',', TokenType.COMMA),
        (r'\.', TokenType.DOT),
        (r':', TokenType.COLON),
        (r';', TokenType.SEMICOLON),
        
        # Whitespace and newlines
        (r'\n', TokenType.NEWLINE),
        (r'[ \t]+', TokenType.WHITESPACE),
    ]
    
    def __init__(self, text: str):
        self.text = text
        self.position = 0
        self.line = 1
        self.column = 1
        self.tokens: List[Token] = []
        
        # Compile regex patterns for efficiency
        self.compiled_patterns = [
            (re.compile(pattern), token_type)
            for pattern, token_type in self.TOKEN_PATTERNS
        ]
    
    def tokenize(self) -> List[Token]:
        """Tokenize the input text and return a list of tokens."""
        self.tokens = []
        
        while self.position < len(self.text):
            if not self._match_token():
                char = self.text[self.position]
                raise LexerError(f"Unexpected character: '{char}'", self.line, self.column)
        
        # Add EOF token
        self.tokens.append(Token(TokenType.EOF, "", self.line, self.column))
        
        # Filter out whitespace and comments for easier parsing
        return [token for token in self.tokens 
                if token.type not in (TokenType.WHITESPACE, TokenType.COMMENT)]
    
    def _match_token(self) -> bool:
        """Try to match a token at the current position."""
        for pattern, token_type in self.compiled_patterns:
            match = pattern.match(self.text, self.position)
            if match:
                value = match.group(0)
                
                # Handle special token types
                if token_type == TokenType.IDENTIFIER:
                    # Check if it's a keyword
                    if value.lower() in self.KEYWORDS:
                        token_type = self._get_keyword_token_type(value.lower())
                
                elif token_type == TokenType.STRING:
                    # Remove quotes from string literals
                    value = value[1:-1]  # Remove surrounding quotes
                    # Unescape common escape sequences
                    value = value.replace('\\"', '"').replace("\\'", "'").replace('\\\\', '\\')
                
                elif token_type == TokenType.NUMBER:
                    # Keep the original string representation for now
                    pass
                
                # Create token
                token = Token(token_type, value, self.line, self.column)
                self.tokens.append(token)
                
                # Update position
                self._advance_position(len(match.group(0)))
                return True
        
        return False
    
    def _get_keyword_token_type(self, keyword: str) -> TokenType:
        """Get the appropriate token type for a keyword."""
        keyword_map = {
            'and': TokenType.AND,
            'or': TokenType.OR,
            'not': TokenType.NOT,
            'contains': TokenType.CONTAINS,
            'matches': TokenType.MATCHES,
            'starts_with': TokenType.STARTS_WITH,
            'ends_with': TokenType.ENDS_WITH,
            'in': TokenType.IN,
            'not_in': TokenType.NOT_IN,
            'true': TokenType.BOOLEAN,
            'false': TokenType.BOOLEAN,
            'null': TokenType.NULL,
        }
        
        return keyword_map.get(keyword, TokenType.KEYWORD)
    
    def _advance_position(self, count: int):
        """Advance the position and update line/column tracking."""
        for _ in range(count):
            if self.position < len(self.text) and self.text[self.position] == '\n':
                self.line += 1
                self.column = 1
            else:
                self.column += 1
            self.position += 1