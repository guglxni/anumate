"""Demo script showing Approvals service and ClarificationsBridge integration."""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from uuid import uuid4, UUID
from typing import Dict, Any, List

"""Demo script showing Approvals service and ClarificationsBridge integration."""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from uuid import uuid4, UUID
from typing import Dict, Any, List

# For demo purposes, we'll use simplified versions to avoid dependency issues
from src.models import (
    ApprovalCreate,
    ApprovalDetail, 
    ApprovalResponse,
    ApprovalStatus,
    ApprovalPriority,
    NotificationChannel,
)

# Create minimal versions to avoid import issues
class MockApprovalService:
    """Mock approval service for demo."""
    
    def __init__(self):
        self.approvals = {}
        self.clarification_map = {}
        self.events = []
    
    async def create_approval_request(self, tenant_id: UUID, approval_data: ApprovalCreate, approver_contacts=None):
        approval_id = uuid4()
        now = datetime.now(timezone.utc)
        
        approval = ApprovalDetail(
            approval_id=approval_id,
            tenant_id=tenant_id,
            clarification_id=approval_data.clarification_id,
            run_id=approval_data.run_id,
            title=approval_data.title,
            description=approval_data.description,
            priority=approval_data.priority,
            required_approvers=approval_data.required_approvers,
            approval_rules=[],
            requires_all_approvers=approval_data.requires_all_approvers,
            status=ApprovalStatus.PENDING,
            requested_at=now,
            expires_at=approval_data.expires_at or (now + timedelta(hours=24)),
            completed_at=None,
            plan_context=approval_data.plan_context,
            request_metadata=approval_data.request_metadata,
            approved_by=[],
            rejected_by=None,
            approval_reason=None,
            rejection_reason=None,
            created_at=now,
            updated_at=now,
        )
        
        self.approvals[approval_id] = approval
        self.clarification_map[approval_data.clarification_id] = approval_id
        
        # Mock notification sending
        if approver_contacts:
            print(f"📧 Sending approval notifications to {len(approval_data.required_approvers)} approvers")
            for approver in approval_data.required_approvers:
                contacts = approver_contacts.get(approver, [])
                for contact in contacts:
                    print(f"   📨 {contact['channel']} to {contact['address']}")
        
        # Mock event publishing
        self.events.append({
            "event_type": "approval.requested",
            "data": {
                "approval_id": str(approval_id),
                "clarification_id": approval_data.clarification_id,
                "tenant_id": str(tenant_id),
            },
            "timestamp": datetime.utcnow().isoformat(),
        })
        print(f"📤 Event published: approval.requested")
        
        return approval
    
    async def get_approval_by_clarification(self, clarification_id: str, tenant_id: UUID):
        approval_id = self.clarification_map.get(clarification_id)
        if approval_id:
            return self.approvals.get(approval_id)
        return None
    
    async def approve_request(self, approval_id: UUID, tenant_id: UUID, response: ApprovalResponse, requester_contacts=None):
        approval = self.approvals.get(approval_id)
        if approval and approval.status == ApprovalStatus.PENDING:
            if response.approved:
                approval.approved_by = approval.approved_by + [response.approver_id]
                approval.approval_reason = response.reason
                approval.completed_at = datetime.now(timezone.utc)
                
                # Check if approval is complete
                if not approval.requires_all_approvers or set(approval.approved_by) == set(approval.required_approvers):
                    approval.status = ApprovalStatus.APPROVED
                
                # Mock notification
                print(f"📧 Sending approved notification to requester")
                
                # Mock event
                self.events.append({
                    "event_type": "approval.granted", 
                    "data": {
                        "approval_id": str(approval_id),
                        "approved_by": approval.approved_by,
                    },
                    "timestamp": datetime.utcnow().isoformat(),
                })
                print(f"📤 Event published: approval.granted")
            else:
                approval.status = ApprovalStatus.REJECTED
                approval.rejected_by = response.approver_id
                approval.rejection_reason = response.reason
                approval.completed_at = datetime.now(timezone.utc)
                
                # Mock event
                self.events.append({
                    "event_type": "approval.rejected",
                    "data": {
                        "approval_id": str(approval_id),
                        "rejected_by": response.approver_id,
                    },
                    "timestamp": datetime.utcnow().isoformat(),
                })
                print(f"📤 Event published: approval.rejected")
        
        return approval
    
    async def cleanup_expired_approvals(self):
        return 0  # Mock cleanup

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MockClarificationsBridge:
    """Mock ClarificationsBridge to demonstrate integration."""
    
    def __init__(self, approvals_service: MockApprovalService, approvals_base_url: str = "http://localhost:8004"):
        self.approvals_service = approvals_service
        self.approvals_base_url = approvals_base_url
    
    async def create_approval_request(
        self,
        clarification_id: str,
        run_id: str,
        tenant_id: UUID,
        plan_context: Dict[str, Any],
    ) -> str:
        """Create approval request from Portia Clarification."""
        print(f"🔗 ClarificationsBridge: Creating approval for clarification {clarification_id}")
        
        # Extract approval details from plan context
        title = plan_context.get("title", f"Approval required for run {run_id}")
        description = plan_context.get("description", "Manual approval required for plan execution")
        priority = ApprovalPriority(plan_context.get("priority", "medium"))
        required_approvers = plan_context.get("required_approvers", ["default-approver"])
        
        approval_data = ApprovalCreate(
            clarification_id=clarification_id,
            run_id=run_id,
            title=title,
            description=description,
            priority=priority,
            required_approvers=required_approvers,
            requires_all_approvers=plan_context.get("requires_all_approvers", False),
            plan_context=plan_context,
            request_metadata={"source": "clarifications_bridge"},
        )
        
        # Mock approver contacts
        approver_contacts = {
            approver: [{"channel": "email", "address": f"{approver}@example.com"}]
            for approver in required_approvers
        }
        
        approval = await self.approvals_service.create_approval_request(
            tenant_id=tenant_id,
            approval_data=approval_data,
            approver_contacts=approver_contacts,
        )
        
        print(f"✅ Approval request created: {approval.approval_id}")
        return str(approval.approval_id)
    
    async def poll_approval_status(
        self,
        clarification_id: str,
        tenant_id: UUID,
    ) -> Dict[str, Any]:
        """Poll approval status."""
        print(f"🔍 ClarificationsBridge: Polling status for clarification {clarification_id}")
        
        approval = await self.approvals_service.get_approval_by_clarification(
            clarification_id=clarification_id,
            tenant_id=tenant_id,
        )
        
        if not approval:
            return {"status": "not_found"}
        
        status_map = {
            ApprovalStatus.PENDING: "pending",
            ApprovalStatus.APPROVED: "approved", 
            ApprovalStatus.REJECTED: "rejected",
            ApprovalStatus.CANCELLED: "cancelled",
            ApprovalStatus.EXPIRED: "expired",
        }
        
        result = {
            "status": status_map[approval.status],
            "approval_id": str(approval.approval_id),
            "approved_by": approval.approved_by,
            "rejected_by": approval.rejected_by,
            "reason": approval.approval_reason or approval.rejection_reason,
        }
        
        print(f"📊 Status: {result['status']}")
        return result


async def demo_approvals_clarifications_integration():
    """Demonstrate the Approvals service integration with ClarificationsBridge."""
    
    print("🚀 Starting Approvals & ClarificationsBridge Integration Demo")
    print("=" * 60)
    
    # Setup mock services
    approval_service = MockApprovalService()
    
    # Create ClarificationsBridge mock
    clarifications_bridge = MockClarificationsBridge(approval_service)
    
    # Demo scenario
    tenant_id = uuid4()
    clarification_id = f"clarification-{uuid4()}"
    run_id = f"run-{uuid4()}"
    
    print(f"\n📋 Demo Scenario:")
    print(f"   Tenant ID: {tenant_id}")
    print(f"   Clarification ID: {clarification_id}")
    print(f"   Run ID: {run_id}")
    print()
    
    # Step 1: Portia creates clarification, bridge creates approval
    print("1️⃣ Step 1: Create Approval from Portia Clarification")
    plan_context = {
        "title": "High-Risk User Account Creation",
        "description": "Creating privileged user account with admin permissions",
        "priority": "high",
        "required_approvers": ["security-team", "compliance-officer"],
        "requires_all_approvers": False,
        "action": "create_user",
        "user_email": "admin@example.com",
        "permissions": ["admin", "write", "delete"],
        "risk_level": "high",
    }
    
    approval_id = await clarifications_bridge.create_approval_request(
        clarification_id=clarification_id,
        run_id=run_id,
        tenant_id=tenant_id,
        plan_context=plan_context,
    )
    print()
    
    # Step 2: Bridge polls for status (initially pending)
    print("2️⃣ Step 2: Poll Initial Approval Status")
    status = await clarifications_bridge.poll_approval_status(
        clarification_id=clarification_id,
        tenant_id=tenant_id,
    )
    print(f"   Initial status: {status}")
    print()
    
    # Step 3: Simulate approver response
    print("3️⃣ Step 3: Security Team Approves Request")
    response = ApprovalResponse(
        approved=True,
        approver_id="security-team",
        reason="Security review completed - account creation approved with monitoring",
        metadata={"review_id": "SEC-2024-001", "monitoring_enabled": True},
    )
    
    approval_uuid = UUID(approval_id)
    approved_approval = await approval_service.approve_request(
        approval_id=approval_uuid,
        tenant_id=tenant_id,
        response=response,
        requester_contacts=[{"channel": "email", "address": "requester@example.com"}],
    )
    
    print(f"   ✅ Approval granted by {response.approver_id}")
    print(f"   📝 Reason: {response.reason}")
    print()
    
    # Step 4: Bridge polls for final status
    print("4️⃣ Step 4: Poll Final Approval Status")
    final_status = await clarifications_bridge.poll_approval_status(
        clarification_id=clarification_id,
        tenant_id=tenant_id,
    )
    print(f"   Final status: {final_status}")
    print()
    
    # Step 5: Show event history
    print("5️⃣ Step 5: Event History")
    print("   Events published:")
    for i, event in enumerate(approval_service.events, 1):
        print(f"   {i}. {event['event_type']} at {event['timestamp']}")
    print()
    
    # Summary
    print("📊 Demo Summary:")
    print(f"   ✅ Created approval request from clarification")
    print(f"   ✅ Sent notifications to {len(plan_context['required_approvers'])} approvers")
    print(f"   ✅ Processed approval decision")
    print(f"   ✅ Published {len(approval_service.events)} events")
    print(f"   ✅ Final status: {final_status['status']}")
    print()
    
    print("🎉 Integration Demo Completed Successfully!")
    print("\n📋 Key Integration Points Demonstrated:")
    print("   • ClarificationsBridge → Approvals service API calls")
    print("   • Approval creation from clarification context")
    print("   • Status polling for clarification updates")  
    print("   • Event publishing for approval lifecycle")
    print("   • Notification system integration")
    print("   • Multi-approver workflow support")


async def demo_approval_workflow_scenarios():
    """Demonstrate various approval workflow scenarios."""
    
    print("\n" + "=" * 60)
    print("🔀 Additional Approval Workflow Scenarios")
    print("=" * 60)
    
    # Setup
    approval_service = MockApprovalService()
    
    tenant_id = uuid4()
    
    print("\n🚫 Scenario: Approval Rejection")
    
    # Create approval
    approval_data = ApprovalCreate(
        clarification_id="clarification-reject-demo",
        run_id="run-reject-demo",
        title="Suspicious Account Modification",
        description="Attempting to modify security-sensitive account settings",
        priority=ApprovalPriority.URGENT,
        required_approvers=["security-team"],
        plan_context={
            "action": "modify_account",
            "target_user": "admin@example.com",
            "changes": ["password_reset", "permissions_escalation"],
            "risk_score": 9.5,
        },
    )
    
    approval = await approval_service.create_approval_request(
        tenant_id=tenant_id,
        approval_data=approval_data,
        approver_contacts={
            "security-team": [{"channel": "slack", "address": "#security-urgent"}]
        },
    )
    
    # Reject the approval
    rejection_response = ApprovalResponse(
        approved=False,
        approver_id="security-team",
        reason="High risk score and unusual modification pattern detected. Requires additional verification.",
        metadata={"risk_score": 9.5, "additional_verification_required": True},
    )
    
    await approval_service.approve_request(
        approval_id=approval.approval_id,
        tenant_id=tenant_id,
        response=rejection_response,
    )
    
    print(f"   ❌ Approval rejected: {rejection_response.reason}")
    
    print("\n⏰ Scenario: Approval Expiration")
    print("   (In production, expired approvals would be cleaned up by background tasks)")
    
    expired_count = await approval_service.cleanup_expired_approvals()
    print(f"   🧹 Cleaned up {expired_count} expired approvals")
    
    print("\n✅ All scenarios completed successfully!")


if __name__ == "__main__":
    asyncio.run(demo_approvals_clarifications_integration())
    asyncio.run(demo_approval_workflow_scenarios())
