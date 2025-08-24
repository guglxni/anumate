"""
Plan transformer for converting capsule YAML to Portia plans.
"""

import hashlib
import json
import logging
from typing import Dict, Any

import yaml

logger = logging.getLogger(__name__)


def to_portia_plan(capsule_yaml: str, capsule_id: str = None, plan_hash: str = None, inject_approval_gates: bool = False, require_approval: bool = None) -> Dict[str, Any]:
    """
    Transform capsule YAML to Portia plan format.
    
    Args:
        capsule_yaml: YAML content defining the capsule
        capsule_id: The capsule identifier  
        plan_hash: The plan hash
        inject_approval_gates: Whether to inject approval steps
        require_approval: Whether to inject approval step (backward compatibility)
        
    Returns:
        Portia plan dictionary with deterministic structure
    """
    
    print(f"DEBUG: to_portia_plan called with capsule_id={capsule_id}, plan_hash={plan_hash}")
    
    # Handle backward compatibility
    if require_approval is not None:
        inject_approval_gates = require_approval
    logger.info(f"Transforming capsule to Portia plan, inject_approval_gates={inject_approval_gates}")
    
    try:
        # Parse YAML
        capsule_data = yaml.safe_load(capsule_yaml)
    except yaml.YAMLError as e:
        logger.error(f"Invalid YAML: {e}")
        raise ValueError(f"Invalid capsule YAML: {e}")
    
    # Extract capsule metadata
    name = capsule_data.get("name", "orchestrator-plan")
    steps = capsule_data.get("steps", [])
    
    # Build Portia plan steps
    portia_steps = []
    
    # 1. Inject approval step if required
    if inject_approval_gates:
        approval_step = {
            "id": "approval_gate",
            "type": "clarification", 
            "prompt": "Approve execution?",
            "clarification_type": "approval",
            "metadata": {
                "required": True,
                "source": "orchestrator"
            }
        }
        portia_steps.append(approval_step)
    
    # 2. Transform capsule steps to Portia steps
    for i, step in enumerate(steps):
        # For now, create echo/no-op tool steps 
        # (will be swapped to Stripe later per requirements)
        portia_step = {
            "id": f"step_{i}",
            "type": "tool",
            "tool": step.get("tool", "echo"),
            "parameters": step.get("parameters", {}),
            "metadata": {
                "original_step": step,
                "step_index": i
            }
        }
        portia_steps.append(portia_step)
    
    # If no steps provided, add a default no-op
    if not portia_steps or (len(portia_steps) == 1 and inject_approval_gates):
        noop_step = {
            "id": "noop",
            "type": "tool", 
            "tool": "echo",
            "parameters": {"message": "Plan execution complete"},
            "metadata": {"default_step": True}
        }
        portia_steps.append(noop_step)
    
    # Build deterministic plan structure
    plan = {
        "name": name,
        "steps": portia_steps,
        "metadata": {
            "source": "anumate-orchestrator",
            "capsule_name": name,
            "require_approval": inject_approval_gates,
            "step_count": len(portia_steps),
            "original_capsule": capsule_data
        }
    }
    
    # Add plan hash for deterministic identification
    plan_json = json.dumps(plan, sort_keys=True)
    plan_hash = hashlib.sha256(plan_json.encode()).hexdigest()[:16]
    plan["metadata"]["plan_hash"] = plan_hash
    
    logger.info(f"Created Portia plan: {name}, steps={len(portia_steps)}, hash={plan_hash}")
    
    return plan
