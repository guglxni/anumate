"""Simple demo of Orchestrator service components."""

import asyncio
import json
from datetime import datetime, timezone
from uuid import uuid4

# Simple demo without external dependencies
def demo_plan_transformation():
    """Demonstrate ExecutablePlan to Portia transformation."""
    print("🚀 Anumate Orchestrator - Plan Transformation Demo")
    print("=" * 50)
    
    # Sample ExecutablePlan
    executable_plan = {
        "plan_id": str(uuid4()),
        "plan_hash": "demo123abc456def",
        "tenant_id": str(uuid4()),
        "name": "Demo Automation Plan",
        "version": "1.0.0",
        "description": "Demo plan for Portia integration testing",
        "flows": [
            {
                "flow_id": "main_flow",
                "name": "Main Automation Flow",
                "steps": [
                    {
                        "step_id": "validate_input",
                        "name": "Validate Input Data",
                        "step_type": "action",
                        "action": "validate_data",
                        "tool": "data_validator",
                        "parameters": {
                            "schema": "user_registration",
                            "strict": True
                        },
                        "timeout": 30
                    },
                    {
                        "step_id": "send_welcome_email",
                        "name": "Send Welcome Email",
                        "step_type": "action",
                        "action": "send_email",
                        "tool": "email_connector",
                        "depends_on": ["validate_input"],
                        "conditions": ["validate_input.success == true"]
                    }
                ]
            }
        ],
        "main_flow": "main_flow",
        "security_context": {
            "allowed_tools": ["data_validator", "email_connector"],
            "required_capabilities": ["execute_plan", "send_notification"]
        },
        "variables": {
            "environment": "demo",
            "debug_mode": True
        },
        "configuration": {
            "timeout": 300,
            "retry_policy": {
                "max_attempts": 3,
                "initial_delay": 2.0
            }
        }
    }
    
    print(f"📋 ExecutablePlan: {executable_plan['name']}")
    print(f"   Plan Hash: {executable_plan['plan_hash']}")
    print(f"   Flows: {len(executable_plan['flows'])}")
    print(f"   Steps: {len(executable_plan['flows'][0]['steps'])}")
    print()
    
    # Demonstrate plan transformation logic
    print("🔄 Transforming to Portia format...")
    
    # Extract basic plan information
    plan_id = f"anumate-{executable_plan['plan_hash'][:8]}"
    name = executable_plan.get('name', 'Unnamed Plan')
    
    # Transform steps
    main_flow = executable_plan['flows'][0]
    portia_steps = []
    
    for step in main_flow['steps']:
        portia_step = {
            'id': step['step_id'],
            'name': step['name'],
            'type': step['step_type'],
        }
        
        if step.get('action'):
            portia_step['action'] = step['action']
        if step.get('tool'):
            portia_step['tool'] = step['tool']
        if step.get('parameters'):
            portia_step['parameters'] = step['parameters']
        if step.get('depends_on'):
            portia_step['depends_on'] = step['depends_on']
        if step.get('conditions'):
            portia_step['conditions'] = step['conditions']
        if step.get('timeout'):
            portia_step['timeout'] = step['timeout']
        
        portia_steps.append(portia_step)
    
    # Create Portia plan structure
    portia_plan = {
        'plan_id': plan_id,
        'name': name,
        'description': executable_plan.get('description'),
        'steps': portia_steps,
        'variables': {
            **executable_plan.get('variables', {}),
            'tenant_id': executable_plan['tenant_id'],
            'plan_hash': executable_plan['plan_hash'],
        },
        'timeout': executable_plan.get('configuration', {}).get('timeout'),
        'created_by': 'demo-user',
        'created_at': datetime.now(timezone.utc).isoformat()
    }
    
    print(f"✅ Portia Plan Created:")
    print(f"   Plan ID: {portia_plan['plan_id']}")
    print(f"   Name: {portia_plan['name']}")
    print(f"   Steps: {len(portia_plan['steps'])}")
    print(f"   Variables: {len(portia_plan['variables'])}")
    print()
    
    print("📝 Portia Steps:")
    for i, step in enumerate(portia_plan['steps'], 1):
        print(f"   {i}. {step['name']} ({step['type']})")
        if step.get('action'):
            print(f"      Action: {step['action']}")
        if step.get('tool'):
            print(f"      Tool: {step['tool']}")
        if step.get('depends_on'):
            print(f"      Depends on: {step['depends_on']}")
    print()
    
    # Demonstrate capability validation
    print("🔒 Capability Validation:")
    security_context = executable_plan.get('security_context', {})
    required_capabilities = security_context.get('required_capabilities', [])
    allowed_tools = security_context.get('allowed_tools', [])
    
    print(f"   Required Capabilities: {required_capabilities}")
    print(f"   Allowed Tools: {allowed_tools}")
    
    # Mock validation
    for step in portia_plan['steps']:
        tool = step.get('tool')
        if tool:
            is_allowed = tool in allowed_tools
            status = "✅ ALLOWED" if is_allowed else "❌ DENIED"
            print(f"   Tool '{tool}': {status}")
    print()
    
    # Demonstrate retry policy
    print("🔄 Retry Policy:")
    retry_config = executable_plan.get('configuration', {}).get('retry_policy', {})
    if retry_config:
        print(f"   Max Attempts: {retry_config.get('max_attempts', 3)}")
        print(f"   Initial Delay: {retry_config.get('initial_delay', 1.0)}s")
        print(f"   Exponential Base: {retry_config.get('exponential_base', 2.0)}")
    else:
        print("   Using default retry policy")
    print()
    
    # Demonstrate idempotency key generation
    print("🔑 Idempotency Key Generation:")
    request_data = {
        'plan_hash': executable_plan['plan_hash'],
        'tenant_id': executable_plan['tenant_id'],
        'parameters': {'user_email': 'demo@example.com'},
        'variables': {'custom_greeting': 'Welcome!'}
    }
    
    # Simple hash generation (mock)
    import hashlib
    json_str = json.dumps(request_data, sort_keys=True)
    request_hash = hashlib.sha256(json_str.encode()).hexdigest()
    idempotency_key = f"idempotency:{executable_plan['tenant_id']}:{request_hash}"
    
    print(f"   Request Hash: {request_hash[:16]}...")
    print(f"   Idempotency Key: {idempotency_key[:50]}...")
    print()
    
    print("🎉 Transformation demo completed!")
    print()
    print("Key Features Demonstrated:")
    print("✅ ExecutablePlan → Portia Plan transformation")
    print("✅ Step dependency mapping")
    print("✅ Security context validation")
    print("✅ Tool allowlist checking")
    print("✅ Retry policy configuration")
    print("✅ Idempotency key generation")
    print("✅ Variable and parameter handling")


if __name__ == "__main__":
    demo_plan_transformation()