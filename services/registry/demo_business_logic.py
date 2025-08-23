"""Demo of Capsule Registry business logic features."""

import asyncio
import json
from uuid import uuid4
from datetime import datetime, timezone

from src.models import (
    CapsuleDefinition, Capsule, DependencySpec, 
    CapsuleCreateRequest, ApprovalStatus
)
from src.dependency_resolver import DependencyResolver
from src.composition import CapsuleComposer
from src.diff_tracker import CapsuleDiffTracker
from src.approval_workflow import ApprovalWorkflowManager


class MockRepository:
    """Mock repository for demo purposes."""
    
    def __init__(self):
        self.capsules = {}
        self.capsules_by_name = {}
    
    async def get_by_id(self, capsule_id):
        return self.capsules.get(capsule_id)
    
    async def get_by_name_version(self, name, version):
        return self.capsules_by_name.get(f"{name}@{version}")
    
    async def list_by_name(self, name):
        return [c for c in self.capsules.values() if c.name == name]
    
    async def get_latest_version(self, name):
        versions = await self.list_by_name(name)
        if not versions:
            return None
        return max(versions, key=lambda c: c.created_at)
    
    def add_capsule(self, capsule):
        self.capsules[capsule.capsule_id] = capsule
        self.capsules_by_name[f"{capsule.name}@{capsule.version}"] = capsule


class MockDatabase:
    """Mock database for demo purposes."""
    
    def __init__(self):
        self.approvals = {}
        self.next_approval_id = 1
    
    async def fetchval(self, query, *args):
        if "INSERT INTO capsule_approvals" in query:
            approval_id = uuid4()
            self.approvals[approval_id] = {
                "capsule_id": args[0],
                "requester_id": args[1],
                "status": args[2],
                "metadata": args[3],
                "created_at": args[4]
            }
            return approval_id
        return None
    
    async def fetchrow(self, query, *args):
        if "SELECT" in query and "capsule_approvals" in query:
            for approval_id, data in self.approvals.items():
                if data["capsule_id"] == args[0]:
                    return {
                        "status": data["status"],
                        "approver_id": data.get("approver_id"),
                        "approved_at": data.get("approved_at"),
                        "rejection_reason": data.get("rejection_reason"),
                        "approval_metadata": data["metadata"]
                    }
        return None
    
    async def execute(self, query, *args):
        if "UPDATE capsule_approvals" in query:
            for approval_id, data in self.approvals.items():
                if data["capsule_id"] == args[1]:  # capsule_id is second arg
                    data["status"] = "approved"
                    data["approver_id"] = args[1]
                    data["approved_at"] = args[2]
                    return approval_id
        return "UPDATE 1"


async def demo_dependency_resolution():
    """Demo dependency resolution functionality."""
    print("\n=== Dependency Resolution Demo ===")
    
    repository = MockRepository()
    resolver = DependencyResolver(repository)
    
    # Create some mock capsules with dependencies
    base_lib_def = CapsuleDefinition(
        name="base-lib",
        version="1.0.0",
        automation={"steps": [{"name": "base-step", "action": "echo 'base'"}]}
    )
    base_lib = Capsule.create(
        tenant_id=uuid4(),
        definition=base_lib_def,
        created_by=uuid4()
    )
    repository.add_capsule(base_lib)
    
    # Create a capsule that depends on base-lib
    app_def = CapsuleDefinition(
        name="my-app",
        version="1.0.0",
        dependencies=["base-lib@>=1.0.0"],
        automation={"steps": [{"name": "app-step", "action": "echo 'app'"}]}
    )
    app = Capsule.create(
        tenant_id=uuid4(),
        definition=app_def,
        created_by=uuid4()
    )
    repository.add_capsule(app)
    
    # Test dependency resolution
    print(f"Resolving dependencies for {app.name}@{app.version}")
    result = await resolver.resolve_dependencies(app.definition.dependencies)
    
    print(f"Resolution successful: {result.success}")
    print(f"Resolved dependencies: {len(result.resolved)}")
    for dep in result.resolved:
        print(f"  - {dep.name}@{dep.version}")
    
    if result.unresolved:
        print(f"Unresolved dependencies: {result.unresolved}")
    
    # Test dependency tree
    print(f"\nDependency tree for {app.name}:")
    tree = await resolver.get_dependency_tree(app)
    print(json.dumps(tree, indent=2, default=str))


async def demo_composition_inheritance():
    """Demo composition and inheritance functionality."""
    print("\n=== Composition and Inheritance Demo ===")
    
    repository = MockRepository()
    composer = CapsuleComposer(repository)
    
    # Create a base capsule
    base_def = CapsuleDefinition(
        name="base-capsule",
        version="1.0.0",
        metadata={"type": "base"},
        tools=["curl", "jq"],
        automation={"steps": [{"name": "base-step", "action": "echo 'base'"}]}
    )
    base = Capsule.create(
        tenant_id=uuid4(),
        definition=base_def,
        created_by=uuid4()
    )
    repository.add_capsule(base)
    
    # Create a capsule that inherits from base
    child_def = CapsuleDefinition(
        name="child-capsule",
        version="1.0.0",
        inherits_from="base-capsule@1.0.0",
        metadata={"type": "child", "environment": "production"},
        tools=["kubectl"],  # Additional tools
        automation={"steps": [{"name": "child-step", "action": "echo 'child'"}]}
    )
    child = Capsule.create(
        tenant_id=uuid4(),
        definition=child_def,
        created_by=uuid4()
    )
    repository.add_capsule(child)
    
    # Test composition
    print(f"Composing {child.name}@{child.version}")
    composed = await composer.compose_capsule(child)
    
    print(f"Inheritance chain: {composed.inheritance_chain}")
    print(f"Composition chain: {composed.composition_chain}")
    print(f"Final tools: {composed.composed_definition.tools}")
    print(f"Final metadata: {composed.composed_definition.metadata}")
    
    # Test validation
    print(f"\nValidating composition for {child.name}")
    errors = await composer.validate_composition(child)
    if errors:
        print(f"Validation errors: {errors}")
    else:
        print("Composition is valid!")


async def demo_diff_tracking():
    """Demo diff and change tracking functionality."""
    print("\n=== Diff and Change Tracking Demo ===")
    
    repository = MockRepository()
    diff_tracker = CapsuleDiffTracker(repository)
    
    # Create original version
    original_def = CapsuleDefinition(
        name="evolving-capsule",
        version="1.0.0",
        description="Original version",
        tools=["curl"],
        automation={"steps": [{"name": "step1", "action": "echo 'v1'"}]}
    )
    original = Capsule.create(
        tenant_id=uuid4(),
        definition=original_def,
        created_by=uuid4()
    )
    repository.add_capsule(original)
    
    # Create updated version
    updated_def = CapsuleDefinition(
        name="evolving-capsule",
        version="1.1.0",
        description="Updated version with new features",
        tools=["curl", "jq"],  # Added jq
        automation={"steps": [
            {"name": "step1", "action": "echo 'v1.1'"},  # Modified
            {"name": "step2", "action": "echo 'new step'"}  # Added
        ]}
    )
    updated = Capsule.create(
        tenant_id=uuid4(),
        definition=updated_def,
        created_by=uuid4()
    )
    repository.add_capsule(updated)
    
    # Generate diff
    print(f"Generating diff between {original.version} and {updated.version}")
    diff = diff_tracker.generate_diff(original, updated)
    
    print(f"Changes detected: {len(diff.changes)}")
    for change in diff.changes:
        print(f"  - {change.change_type}: {change.field_path}")
        if change.change_type == "modified":
            print(f"    Old: {change.old_value}")
            print(f"    New: {change.new_value}")
        elif change.change_type == "added":
            print(f"    Added: {change.new_value}")
        elif change.change_type == "removed":
            print(f"    Removed: {change.old_value}")
    
    # Test change summary
    summary = diff_tracker.get_change_summary(diff)
    print(f"\nChange summary: {summary}")


async def demo_approval_workflow():
    """Demo approval workflow functionality."""
    print("\n=== Approval Workflow Demo ===")
    
    mock_db = MockDatabase()
    approval_manager = ApprovalWorkflowManager(mock_db)
    
    # Create a capsule that requires approval
    sensitive_def = CapsuleDefinition(
        name="sensitive-capsule",
        version="1.0.0",
        description="Capsule with sensitive tools",
        tools=["kubectl", "terraform"],  # Sensitive tools
        policies=["production"],  # Production policy
        automation={"steps": [{"name": "deploy", "action": "kubectl apply"}]}
    )
    sensitive = Capsule.create(
        tenant_id=uuid4(),
        definition=sensitive_def,
        created_by=uuid4()
    )
    
    requester_id = uuid4()
    approver_id = uuid4()
    
    # Check if approval is required
    print(f"Checking if approval required for {sensitive.name}")
    requires_approval = await approval_manager.check_approval_required(sensitive)
    print(f"Approval required: {requires_approval}")
    
    if requires_approval:
        # Create approval request
        print(f"\nCreating approval request for {sensitive.name}")
        approval = await approval_manager.create_approval_request(
            sensitive, 
            requester_id,
            {"priority": "high", "reason": "Production deployment"}
        )
        print(f"Approval request created with status: {approval.status}")
        
        # Approve the capsule
        print(f"\nApproving capsule {sensitive.name}")
        approved = await approval_manager.approve_capsule(
            sensitive.capsule_id,
            approver_id,
            "Reviewed and approved for production deployment"
        )
        print(f"Approval successful: {approved}")
        
        # Check final status
        final_status = await approval_manager.get_approval_status(sensitive.capsule_id)
        if final_status:
            print(f"Final approval status: {final_status.status}")


async def main():
    """Run all demos."""
    print("Capsule Registry Business Logic Demo")
    print("=" * 50)
    
    await demo_dependency_resolution()
    await demo_composition_inheritance()
    await demo_diff_tracking()
    await demo_approval_workflow()
    
    print("\n" + "=" * 50)
    print("Demo completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())