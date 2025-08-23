"""
Main Policy DSL Engine.

This module provides the high-level interface for the Policy DSL system,
integrating parsing, validation, evaluation, and testing.
"""

from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass
import json
try:
    from .parser import parse_policy, ParseError
    from .lexer import LexerError
    from .ast_nodes import PolicyNode
    from .evaluator import PolicyEvaluator, EvaluationResult, EvaluationError
    from .validator import PolicyValidator, ValidationResult
    from .test_framework import PolicyTester, TestSuite, TestCase, TestReport
except ImportError:
    from parser import parse_policy, ParseError
    from lexer import LexerError
    from ast_nodes import PolicyNode
    from evaluator import PolicyEvaluator, EvaluationResult, EvaluationError
    from validator import PolicyValidator, ValidationResult
    from test_framework import PolicyTester, TestSuite, TestCase, TestReport


@dataclass
class PolicyEngineResult:
    """Result from policy engine operations."""
    success: bool
    policy: Optional[PolicyNode] = None
    evaluation: Optional[EvaluationResult] = None
    validation: Optional[ValidationResult] = None
    test_report: Optional[TestReport] = None
    error_message: Optional[str] = None


class PolicyEngine:
    """Main interface for the Policy DSL system."""
    
    def __init__(self):
        self.evaluator = PolicyEvaluator()
        self.validator = PolicyValidator()
        self.tester = PolicyTester()
        self._compiled_policies: Dict[str, PolicyNode] = {}
    
    def compile_policy(self, source_code: str, policy_name: Optional[str] = None) -> PolicyEngineResult:
        """
        Compile Policy DSL source code into an AST.
        
        Args:
            source_code: The Policy DSL source code
            policy_name: Optional name to cache the compiled policy
            
        Returns:
            PolicyEngineResult with compilation status and policy AST
        """
        try:
            policy = parse_policy(source_code)
            
            # Cache the compiled policy if name provided
            if policy_name:
                self._compiled_policies[policy_name] = policy
            
            return PolicyEngineResult(
                success=True,
                policy=policy
            )
        
        except (LexerError, ParseError) as e:
            return PolicyEngineResult(
                success=False,
                error_message=f"Compilation error: {str(e)}"
            )
        except Exception as e:
            return PolicyEngineResult(
                success=False,
                error_message=f"Unexpected error during compilation: {str(e)}"
            )
    
    def validate_policy(self, policy: Union[PolicyNode, str], 
                       policy_name: Optional[str] = None) -> PolicyEngineResult:
        """
        Validate a policy for syntax, semantics, and best practices.
        
        Args:
            policy: Either a PolicyNode or source code string
            policy_name: Optional name for caching
            
        Returns:
            PolicyEngineResult with validation status and issues
        """
        try:
            # Compile if source code provided
            if isinstance(policy, str):
                compile_result = self.compile_policy(policy, policy_name)
                if not compile_result.success:
                    return compile_result
                policy = compile_result.policy
            
            # Validate the policy
            validation_result = self.validator.validate(policy)
            
            return PolicyEngineResult(
                success=validation_result.is_valid,
                policy=policy,
                validation=validation_result,
                error_message=None if validation_result.is_valid else "Policy has validation errors"
            )
        
        except Exception as e:
            return PolicyEngineResult(
                success=False,
                error_message=f"Validation error: {str(e)}"
            )
    
    def evaluate_policy(self, policy: Union[PolicyNode, str], 
                       data: Dict[str, Any],
                       context: Optional[Dict[str, Any]] = None,
                       policy_name: Optional[str] = None) -> PolicyEngineResult:
        """
        Evaluate a policy against input data.
        
        Args:
            policy: Either a PolicyNode or source code string
            data: Input data to evaluate against
            context: Optional evaluation context
            policy_name: Optional name for caching
            
        Returns:
            PolicyEngineResult with evaluation results
        """
        try:
            # Compile if source code provided
            if isinstance(policy, str):
                compile_result = self.compile_policy(policy, policy_name)
                if not compile_result.success:
                    return compile_result
                policy = compile_result.policy
            
            # Evaluate the policy
            evaluation_result = self.evaluator.evaluate_policy(policy, data, context)
            
            return PolicyEngineResult(
                success=True,
                policy=policy,
                evaluation=evaluation_result
            )
        
        except EvaluationError as e:
            return PolicyEngineResult(
                success=False,
                error_message=f"Evaluation error: {str(e)}"
            )
        except Exception as e:
            return PolicyEngineResult(
                success=False,
                error_message=f"Unexpected error during evaluation: {str(e)}"
            )
    
    def test_policy(self, policy: Union[PolicyNode, str],
                   test_cases: List[TestCase],
                   suite_name: str = "Policy Test Suite",
                   policy_name: Optional[str] = None) -> PolicyEngineResult:
        """
        Test a policy with provided test cases.
        
        Args:
            policy: Either a PolicyNode or source code string
            test_cases: List of test cases to run
            suite_name: Name for the test suite
            policy_name: Optional name for caching
            
        Returns:
            PolicyEngineResult with test report
        """
        try:
            # Compile if source code provided
            if isinstance(policy, str):
                compile_result = self.compile_policy(policy, policy_name)
                if not compile_result.success:
                    return compile_result
                policy = compile_result.policy
            
            # Create test suite and run tests
            test_suite = TestSuite(
                name=suite_name,
                description=f"Test suite for policy '{policy.name}'",
                policy=policy,
                test_cases=test_cases
            )
            
            test_report = self.tester.run_test_suite(test_suite)
            
            return PolicyEngineResult(
                success=test_report.is_passing,
                policy=policy,
                test_report=test_report,
                error_message=None if test_report.is_passing else "Some tests failed"
            )
        
        except Exception as e:
            return PolicyEngineResult(
                success=False,
                error_message=f"Testing error: {str(e)}"
            )
    
    def get_cached_policy(self, policy_name: str) -> Optional[PolicyNode]:
        """Get a cached compiled policy by name."""
        return self._compiled_policies.get(policy_name)
    
    def clear_cache(self):
        """Clear all cached policies."""
        self._compiled_policies.clear()
    
    def list_cached_policies(self) -> List[str]:
        """List names of all cached policies."""
        return list(self._compiled_policies.keys())
    
    def export_policy_ast(self, policy: PolicyNode) -> Dict[str, Any]:
        """Export policy AST as a dictionary for serialization."""
        return self._ast_to_dict(policy)
    
    def _ast_to_dict(self, node) -> Dict[str, Any]:
        """Convert AST node to dictionary representation."""
        if hasattr(node, '__dict__'):
            result = {'node_type': node.node_type.value if hasattr(node.node_type, 'value') else str(node.node_type)}
            
            for key, value in node.__dict__.items():
                if key == 'node_type':
                    continue
                elif isinstance(value, list):
                    result[key] = [self._ast_to_dict(item) for item in value]
                elif hasattr(value, '__dict__'):
                    result[key] = self._ast_to_dict(value)
                elif hasattr(value, 'value'):  # Enum
                    result[key] = value.value
                else:
                    result[key] = value
            
            return result
        else:
            return value


# Convenience functions for common operations

def compile_policy_from_file(file_path: str) -> PolicyEngineResult:
    """Compile a policy from a file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            source_code = f.read()
        
        engine = PolicyEngine()
        return engine.compile_policy(source_code)
    
    except FileNotFoundError:
        return PolicyEngineResult(
            success=False,
            error_message=f"Policy file not found: {file_path}"
        )
    except Exception as e:
        return PolicyEngineResult(
            success=False,
            error_message=f"Error reading policy file: {str(e)}"
        )


def evaluate_policy_simple(source_code: str, data: Dict[str, Any]) -> bool:
    """
    Simple policy evaluation that returns just the allow/deny decision.
    
    Args:
        source_code: Policy DSL source code
        data: Input data to evaluate
        
    Returns:
        True if allowed, False if denied or error
    """
    engine = PolicyEngine()
    result = engine.evaluate_policy(source_code, data)
    
    if result.success and result.evaluation:
        return result.evaluation.allowed
    else:
        return False


def validate_policy_file(file_path: str) -> ValidationResult:
    """
    Validate a policy file and return validation results.
    
    Args:
        file_path: Path to the policy file
        
    Returns:
        ValidationResult with validation status and issues
    """
    compile_result = compile_policy_from_file(file_path)
    
    if not compile_result.success:
        # Return a validation result with the compilation error
        from .validator import ValidationResult, ValidationIssue, ValidationLevel
        
        issue = ValidationIssue(
            level=ValidationLevel.ERROR,
            message=compile_result.error_message or "Compilation failed"
        )
        
        return ValidationResult(
            is_valid=False,
            issues=[issue]
        )
    
    engine = PolicyEngine()
    validate_result = engine.validate_policy(compile_result.policy)
    
    return validate_result.validation