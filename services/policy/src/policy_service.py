"""Policy Service for managing and evaluating policies."""

import json
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

import structlog
from anumate_infrastructure.database import DatabaseManager
from anumate_infrastructure.tenant_context import get_current_tenant_id

from .engine import PolicyEngine, PolicyEngineResult
from .test_framework import TestCase, TestReport

logger = structlog.get_logger(__name__)


class PolicyService:
    """Service for managing and evaluating policies."""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.engine = PolicyEngine()
    
    async def create_policy(
        self,
        name: str,
        source_code: str,
        created_by: UUID,
        description: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        enabled: bool = True
    ) -> Dict[str, Any]:
        """Create a new policy."""
        tenant_id = get_current_tenant_id()
        if not tenant_id:
            raise ValueError("Tenant context required")
        
        # Compile and validate the policy
        compile_result = self.engine.compile_policy(source_code, name)
        if not compile_result.success:
            raise ValueError(f"Policy compilation failed: {compile_result.error_message}")
        
        # Validate the policy
        validate_result = self.engine.validate_policy(compile_result.policy)
        if not validate_result.success:
            raise ValueError(f"Policy validation failed: {validate_result.error_message}")
        
        # Check if policy name already exists for this tenant
        existing = await self._get_policy_by_name(name, tenant_id)
        if existing:
            raise ValueError(f"Policy with name '{name}' already exists")
        
        policy_id = uuid4()
        compiled_ast = self.engine.export_policy_ast(compile_result.policy)
        
        async with self.db_manager.get_connection() as conn:
            await conn.execute("""
                INSERT INTO policies (
                    policy_id, tenant_id, name, description, source_code, 
                    compiled_ast, metadata, enabled, version, created_by, 
                    created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            """, 
                policy_id, tenant_id, name, description, source_code,
                json.dumps(compiled_ast), json.dumps(metadata or {}), enabled, 1, 
                created_by, datetime.utcnow(), datetime.utcnow()
            )
        
        logger.info("Policy created", 
                   policy_id=str(policy_id), 
                   name=name, 
                   tenant_id=str(tenant_id))
        
        return await self.get_policy(policy_id)
    
    async def get_policy(self, policy_id: UUID) -> Optional[Dict[str, Any]]:
        """Get a policy by ID."""
        tenant_id = get_current_tenant_id()
        if not tenant_id:
            raise ValueError("Tenant context required")
        
        async with self.db_manager.get_connection() as conn:
            row = await conn.fetchrow("""
                SELECT policy_id, tenant_id, name, description, source_code, 
                       compiled_ast, metadata, enabled, version, created_by, 
                       created_at, updated_at, last_evaluated_at, evaluation_count
                FROM policies 
                WHERE policy_id = $1 AND tenant_id = $2 AND active = true
            """, policy_id, tenant_id)
        
        if not row:
            return None
        
        return self._row_to_policy(row)
    
    async def list_policies(
        self, 
        page: int = 1, 
        page_size: int = 50,
        name_filter: Optional[str] = None,
        enabled_only: bool = False
    ) -> Tuple[List[Dict[str, Any]], int]:
        """List policies with pagination and filtering."""
        tenant_id = get_current_tenant_id()
        if not tenant_id:
            raise ValueError("Tenant context required")
        
        offset = (page - 1) * page_size
        
        # Build query conditions
        conditions = ["tenant_id = $1", "active = true"]
        params = [tenant_id]
        param_count = 1
        
        if name_filter:
            param_count += 1
            conditions.append(f"name ILIKE ${param_count}")
            params.append(f"%{name_filter}%")
        
        if enabled_only:
            conditions.append("enabled = true")
        
        where_clause = " AND ".join(conditions)
        
        async with self.db_manager.get_connection() as conn:
            # Get total count
            count_query = f"SELECT COUNT(*) FROM policies WHERE {where_clause}"
            total = await conn.fetchval(count_query, *params)
            
            # Get policies
            query = f"""
                SELECT policy_id, tenant_id, name, description, source_code, 
                       compiled_ast, metadata, enabled, version, created_by, 
                       created_at, updated_at, last_evaluated_at, evaluation_count
                FROM policies 
                WHERE {where_clause}
                ORDER BY created_at DESC
                LIMIT ${param_count + 1} OFFSET ${param_count + 2}
            """
            params.extend([page_size, offset])
            
            rows = await conn.fetch(query, *params)
        
        policies = [self._row_to_policy(row) for row in rows]
        
        return policies, total
    
    async def update_policy(
        self,
        policy_id: UUID,
        name: Optional[str] = None,
        description: Optional[str] = None,
        source_code: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        enabled: Optional[bool] = None
    ) -> Dict[str, Any]:
        """Update an existing policy."""
        tenant_id = get_current_tenant_id()
        if not tenant_id:
            raise ValueError("Tenant context required")
        
        # Get existing policy
        existing = await self.get_policy(policy_id)
        if not existing:
            raise ValueError(f"Policy {policy_id} not found")
        
        # Prepare update data
        updates = {}
        if name is not None:
            # Check if new name conflicts with existing policies
            if name != existing["name"]:
                existing_with_name = await self._get_policy_by_name(name, tenant_id)
                if existing_with_name and existing_with_name["policy_id"] != policy_id:
                    raise ValueError(f"Policy with name '{name}' already exists")
            updates["name"] = name
        
        if description is not None:
            updates["description"] = description
        
        if source_code is not None:
            # Compile and validate new source code
            compile_result = self.engine.compile_policy(source_code, name or existing["name"])
            if not compile_result.success:
                raise ValueError(f"Policy compilation failed: {compile_result.error_message}")
            
            validate_result = self.engine.validate_policy(compile_result.policy)
            if not validate_result.success:
                raise ValueError(f"Policy validation failed: {validate_result.error_message}")
            
            updates["source_code"] = source_code
            updates["compiled_ast"] = json.dumps(self.engine.export_policy_ast(compile_result.policy))
            updates["version"] = existing["version"] + 1
        
        if metadata is not None:
            updates["metadata"] = json.dumps(metadata)
        
        if enabled is not None:
            updates["enabled"] = enabled
        
        if not updates:
            return existing
        
        # Build update query
        set_clauses = []
        params = []
        param_count = 0
        
        for field, value in updates.items():
            param_count += 1
            set_clauses.append(f"{field} = ${param_count}")
            params.append(value)
        
        # Add updated_at
        param_count += 1
        set_clauses.append(f"updated_at = ${param_count}")
        params.append(datetime.utcnow())
        
        # Add WHERE conditions
        param_count += 1
        params.append(policy_id)
        param_count += 1
        params.append(tenant_id)
        
        query = f"""
            UPDATE policies 
            SET {', '.join(set_clauses)}
            WHERE policy_id = ${param_count - 1} AND tenant_id = ${param_count}
        """
        
        async with self.db_manager.get_connection() as conn:
            await conn.execute(query, *params)
        
        logger.info("Policy updated", 
                   policy_id=str(policy_id), 
                   tenant_id=str(tenant_id))
        
        return await self.get_policy(policy_id)
    
    async def delete_policy(self, policy_id: UUID) -> bool:
        """Soft delete a policy."""
        tenant_id = get_current_tenant_id()
        if not tenant_id:
            raise ValueError("Tenant context required")
        
        async with self.db_manager.get_connection() as conn:
            result = await conn.execute("""
                UPDATE policies 
                SET active = false, updated_at = $1
                WHERE policy_id = $2 AND tenant_id = $3 AND active = true
            """, datetime.utcnow(), policy_id, tenant_id)
        
        success = result.split()[-1] == "1"  # Check if one row was updated
        
        if success:
            logger.info("Policy deleted", 
                       policy_id=str(policy_id), 
                       tenant_id=str(tenant_id))
        
        return success
    
    async def evaluate_policy(
        self, 
        policy_id: UUID, 
        data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Evaluate a policy against input data."""
        tenant_id = get_current_tenant_id()
        if not tenant_id:
            raise ValueError("Tenant context required")
        
        # Get the policy
        policy_data = await self.get_policy(policy_id)
        if not policy_data:
            raise ValueError(f"Policy {policy_id} not found")
        
        if not policy_data["enabled"]:
            raise ValueError(f"Policy {policy_id} is disabled")
        
        start_time = time.time()
        
        # Evaluate the policy
        result = self.engine.evaluate_policy(policy_data["source_code"], data, context)
        
        end_time = time.time()
        evaluation_time_ms = (end_time - start_time) * 1000
        
        if not result.success:
            raise ValueError(f"Policy evaluation failed: {result.error_message}")
        
        # Update evaluation statistics
        await self._update_evaluation_stats(policy_id)
        
        logger.info("Policy evaluated", 
                   policy_id=str(policy_id),
                   allowed=result.evaluation.allowed,
                   evaluation_time_ms=evaluation_time_ms)
        
        return {
            "policy_name": result.evaluation.policy_name,
            "matched_rules": result.evaluation.matched_rules,
            "actions": result.evaluation.actions,
            "allowed": result.evaluation.allowed,
            "metadata": result.evaluation.metadata,
            "evaluation_time_ms": evaluation_time_ms
        }
    
    async def test_policy(
        self, 
        policy_id: UUID, 
        test_cases: List[Dict[str, Any]],
        suite_name: str = "Policy Test Suite"
    ) -> Dict[str, Any]:
        """Test a policy with provided test cases."""
        tenant_id = get_current_tenant_id()
        if not tenant_id:
            raise ValueError("Tenant context required")
        
        # Get the policy
        policy_data = await self.get_policy(policy_id)
        if not policy_data:
            raise ValueError(f"Policy {policy_id} not found")
        
        # Convert test cases to TestCase objects
        test_case_objects = []
        for i, tc in enumerate(test_cases):
            test_case_objects.append(TestCase(
                name=tc.get("name", f"Test Case {i + 1}"),
                description=tc.get("description", ""),
                input_data=tc["input_data"],
                expected_result=tc["expected_result"],
                context=tc.get("context", {})
            ))
        
        # Run the tests
        result = self.engine.test_policy(
            policy_data["source_code"], 
            test_case_objects, 
            suite_name,
            policy_data["name"]
        )
        
        if not result.success:
            raise ValueError(f"Policy testing failed: {result.error_message}")
        
        logger.info("Policy tested", 
                   policy_id=str(policy_id),
                   total_tests=result.test_report.total_tests,
                   passed_tests=result.test_report.passed_tests)
        
        # Convert test report to dict
        return {
            "suite_name": result.test_report.suite_name,
            "policy_name": result.test_report.policy_name,
            "total_tests": result.test_report.total_tests,
            "passed_tests": result.test_report.passed_tests,
            "failed_tests": result.test_report.failed_tests,
            "is_passing": result.test_report.is_passing,
            "test_results": [
                {
                    "test_name": tr.test_name,
                    "passed": tr.passed,
                    "expected": tr.expected,
                    "actual": tr.actual,
                    "error_message": tr.error_message
                }
                for tr in result.test_report.test_results
            ],
            "execution_time_ms": result.test_report.execution_time_ms
        }
    
    async def validate_policy_source(self, source_code: str) -> Dict[str, Any]:
        """Validate policy source code without creating a policy."""
        # Compile the policy
        compile_result = self.engine.compile_policy(source_code)
        if not compile_result.success:
            return {
                "is_valid": False,
                "issues": [{
                    "level": "error",
                    "message": compile_result.error_message,
                    "line": None,
                    "column": None
                }]
            }
        
        # Validate the policy
        validate_result = self.engine.validate_policy(compile_result.policy)
        
        issues = []
        if validate_result.validation:
            for issue in validate_result.validation.issues:
                issues.append({
                    "level": issue.level.value.lower(),
                    "message": issue.message,
                    "line": getattr(issue, 'line', None),
                    "column": getattr(issue, 'column', None)
                })
        
        return {
            "is_valid": validate_result.success,
            "issues": issues
        }
    
    async def _get_policy_by_name(self, name: str, tenant_id: UUID) -> Optional[Dict[str, Any]]:
        """Get a policy by name and tenant."""
        async with self.db_manager.get_connection() as conn:
            row = await conn.fetchrow("""
                SELECT policy_id, tenant_id, name, description, source_code, 
                       compiled_ast, metadata, enabled, version, created_by, 
                       created_at, updated_at, last_evaluated_at, evaluation_count
                FROM policies 
                WHERE name = $1 AND tenant_id = $2 AND active = true
            """, name, tenant_id)
        
        if not row:
            return None
        
        return self._row_to_policy(row)
    
    async def _update_evaluation_stats(self, policy_id: UUID):
        """Update policy evaluation statistics."""
        async with self.db_manager.get_connection() as conn:
            await conn.execute("""
                UPDATE policies 
                SET last_evaluated_at = $1, evaluation_count = evaluation_count + 1
                WHERE policy_id = $2
            """, datetime.utcnow(), policy_id)
    
    def _row_to_policy(self, row) -> Dict[str, Any]:
        """Convert database row to policy dictionary."""
        return {
            "policy_id": row["policy_id"],
            "tenant_id": row["tenant_id"],
            "name": row["name"],
            "description": row["description"],
            "source_code": row["source_code"],
            "compiled_ast": json.loads(row["compiled_ast"]) if row["compiled_ast"] else None,
            "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
            "enabled": row["enabled"],
            "version": row["version"],
            "created_by": row["created_by"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "last_evaluated_at": row["last_evaluated_at"],
            "evaluation_count": row["evaluation_count"]
        }