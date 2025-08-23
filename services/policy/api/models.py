"""Pydantic models for Policy Service API."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class PolicyCreateRequest(BaseModel):
    """Request model for creating a new policy."""
    name: str = Field(..., description="Policy name")
    description: Optional[str] = Field(None, description="Policy description")
    source_code: str = Field(..., description="Policy DSL source code")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Policy metadata")
    enabled: bool = Field(True, description="Whether the policy is enabled")


class PolicyUpdateRequest(BaseModel):
    """Request model for updating a policy."""
    name: Optional[str] = Field(None, description="Policy name")
    description: Optional[str] = Field(None, description="Policy description")
    source_code: Optional[str] = Field(None, description="Policy DSL source code")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Policy metadata")
    enabled: Optional[bool] = Field(None, description="Whether the policy is enabled")


class PolicyEvaluateRequest(BaseModel):
    """Request model for evaluating a policy."""
    data: Dict[str, Any] = Field(..., description="Data to evaluate against the policy")
    context: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Evaluation context")


class PolicyTestRequest(BaseModel):
    """Request model for testing a policy."""
    test_cases: List[Dict[str, Any]] = Field(..., description="Test cases to run")
    suite_name: Optional[str] = Field("Policy Test Suite", description="Test suite name")


class PolicyTestCase(BaseModel):
    """Individual test case for policy testing."""
    name: str = Field(..., description="Test case name")
    description: Optional[str] = Field(None, description="Test case description")
    input_data: Dict[str, Any] = Field(..., description="Input data for the test")
    expected_result: bool = Field(..., description="Expected evaluation result (allow/deny)")
    context: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Test context")


class PolicyValidationIssue(BaseModel):
    """Policy validation issue."""
    level: str = Field(..., description="Issue level (error, warning, info)")
    message: str = Field(..., description="Issue message")
    line: Optional[int] = Field(None, description="Line number where issue occurs")
    column: Optional[int] = Field(None, description="Column number where issue occurs")


class PolicyValidationResult(BaseModel):
    """Policy validation result."""
    is_valid: bool = Field(..., description="Whether the policy is valid")
    issues: List[PolicyValidationIssue] = Field(default_factory=list, description="Validation issues")


class PolicyEvaluationResult(BaseModel):
    """Policy evaluation result."""
    policy_name: str = Field(..., description="Name of the evaluated policy")
    matched_rules: List[str] = Field(default_factory=list, description="Names of matched rules")
    actions: List[Dict[str, Any]] = Field(default_factory=list, description="Actions to be taken")
    allowed: bool = Field(..., description="Whether the request is allowed")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Policy metadata")
    evaluation_time_ms: Optional[float] = Field(None, description="Evaluation time in milliseconds")


class PolicyTestResult(BaseModel):
    """Individual policy test result."""
    test_name: str = Field(..., description="Test case name")
    passed: bool = Field(..., description="Whether the test passed")
    expected: bool = Field(..., description="Expected result")
    actual: bool = Field(..., description="Actual result")
    error_message: Optional[str] = Field(None, description="Error message if test failed")


class PolicyTestReport(BaseModel):
    """Policy test report."""
    suite_name: str = Field(..., description="Test suite name")
    policy_name: str = Field(..., description="Policy name")
    total_tests: int = Field(..., description="Total number of tests")
    passed_tests: int = Field(..., description="Number of passed tests")
    failed_tests: int = Field(..., description="Number of failed tests")
    is_passing: bool = Field(..., description="Whether all tests passed")
    test_results: List[PolicyTestResult] = Field(default_factory=list, description="Individual test results")
    execution_time_ms: Optional[float] = Field(None, description="Total execution time in milliseconds")


class Policy(BaseModel):
    """Policy model."""
    policy_id: UUID = Field(..., description="Policy unique identifier")
    tenant_id: UUID = Field(..., description="Tenant identifier")
    name: str = Field(..., description="Policy name")
    description: Optional[str] = Field(None, description="Policy description")
    source_code: str = Field(..., description="Policy DSL source code")
    compiled_ast: Optional[Dict[str, Any]] = Field(None, description="Compiled AST representation")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Policy metadata")
    enabled: bool = Field(..., description="Whether the policy is enabled")
    version: int = Field(..., description="Policy version")
    created_by: UUID = Field(..., description="User who created the policy")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    last_evaluated_at: Optional[datetime] = Field(None, description="Last evaluation timestamp")
    evaluation_count: int = Field(0, description="Number of times policy has been evaluated")


class PolicyListResponse(BaseModel):
    """Response model for listing policies."""
    policies: List[Policy] = Field(..., description="List of policies")
    total: int = Field(..., description="Total number of policies")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Page size")


class PolicyCompilationResult(BaseModel):
    """Policy compilation result."""
    success: bool = Field(..., description="Whether compilation was successful")
    compiled_ast: Optional[Dict[str, Any]] = Field(None, description="Compiled AST if successful")
    validation_result: Optional[PolicyValidationResult] = Field(None, description="Validation result")
    error_message: Optional[str] = Field(None, description="Error message if compilation failed")