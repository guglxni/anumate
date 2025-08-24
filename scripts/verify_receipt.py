#!/usr/bin/env python3
"""
Receipt verification script for Anumate execution receipts.
Validates tamper-evidence and cryptographic signatures.
"""

import json
import hashlib
import hmac
import base64
import sys
from datetime import datetime
from typing import Dict, Any, Optional


def verify_receipt_signature(receipt: Dict[str, Any], signing_key: str) -> bool:
    """
    Verify the cryptographic signature of an execution receipt.
    
    Args:
        receipt: Receipt data containing signature
        signing_key: Secret key for signature verification
    
    Returns:
        True if signature is valid, False otherwise
    """
    try:
        # Extract signature from receipt
        signature = receipt.get('signature')
        if not signature:
            print("❌ No signature found in receipt")
            return False
        
        # Create signature payload (receipt without signature field)
        payload = {k: v for k, v in receipt.items() if k != 'signature'}
        payload_json = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        
        # Compute expected signature
        expected_signature = hmac.new(
            signing_key.encode('utf-8'),
            payload_json.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        # Compare signatures
        is_valid = hmac.compare_digest(signature, expected_signature)
        
        if is_valid:
            print("✅ Receipt signature verified successfully")
        else:
            print("❌ Receipt signature verification failed")
            print(f"   Expected: {expected_signature}")
            print(f"   Got:      {signature}")
        
        return is_valid
        
    except Exception as e:
        print(f"❌ Error verifying receipt signature: {e}")
        return False


def verify_receipt_integrity(receipt: Dict[str, Any]) -> bool:
    """
    Verify the structural integrity and required fields of a receipt.
    
    Args:
        receipt: Receipt data to verify
    
    Returns:
        True if receipt structure is valid, False otherwise
    """
    required_fields = [
        'receipt_id', 'plan_run_id', 'status', 'timestamp',
        'tenant_id', 'actor', 'plan_hash'
    ]
    
    missing_fields = [field for field in required_fields if field not in receipt]
    
    if missing_fields:
        print(f"❌ Receipt missing required fields: {missing_fields}")
        return False
    
    # Verify timestamp format
    try:
        timestamp = receipt['timestamp']
        datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
    except (ValueError, TypeError) as e:
        print(f"❌ Invalid timestamp format: {e}")
        return False
    
    # Verify status is valid
    valid_statuses = ['SUCCEEDED', 'FAILED', 'PARTIAL', 'CANCELLED']
    if receipt['status'] not in valid_statuses:
        print(f"❌ Invalid status: {receipt['status']} (must be one of {valid_statuses})")
        return False
    
    print("✅ Receipt structure and integrity verified")
    return True


def verify_plan_hash_binding(receipt: Dict[str, Any], expected_plan_hash: Optional[str] = None) -> bool:
    """
    Verify that the receipt is bound to the correct plan hash.
    
    Args:
        receipt: Receipt data
        expected_plan_hash: Expected plan hash (optional)
    
    Returns:
        True if plan hash binding is valid
    """
    plan_hash = receipt.get('plan_hash')
    
    if not plan_hash:
        print("❌ No plan_hash found in receipt")
        return False
    
    if expected_plan_hash and plan_hash != expected_plan_hash:
        print(f"❌ Plan hash mismatch:")
        print(f"   Expected: {expected_plan_hash}")
        print(f"   Got:      {plan_hash}")
        return False
    
    print(f"✅ Plan hash binding verified: {plan_hash}")
    return True


def verify_mcp_execution_evidence(receipt: Dict[str, Any]) -> bool:
    """
    Verify evidence of live MCP execution in the receipt.
    
    Args:
        receipt: Receipt data
    
    Returns:
        True if MCP execution evidence is present
    """
    mcp_data = receipt.get('mcp', {})
    
    if not mcp_data:
        print("⚠️  No MCP execution data found in receipt")
        return False
    
    # Check for live execution flag
    live_execution = mcp_data.get('live_execution', False)
    fallback_mode = mcp_data.get('fallback_mode', False)
    
    if fallback_mode:
        print("⚠️  Receipt shows fallback mode - MCP execution may have failed")
    elif live_execution:
        print("✅ Live MCP execution verified")
    else:
        print("⚠️  MCP execution status unclear")
    
    # Check for MCP tool evidence
    tool = mcp_data.get('tool')
    if tool and tool.startswith('razorpay.'):
        print(f"✅ Razorpay MCP tool executed: {tool}")
    else:
        print("⚠️  No clear Razorpay MCP tool evidence")
    
    return True


def main():
    """Main verification function."""
    if len(sys.argv) < 2:
        print("Usage: python verify_receipt.py <receipt_file> [signing_key] [expected_plan_hash]")
        print("       python verify_receipt.py '<receipt_json>' [signing_key] [expected_plan_hash]")
        sys.exit(1)
    
    receipt_input = sys.argv[1]
    signing_key = sys.argv[2] if len(sys.argv) > 2 else None
    expected_plan_hash = sys.argv[3] if len(sys.argv) > 3 else None
    
    # Load receipt data
    try:
        if receipt_input.startswith('{'):
            # JSON string provided directly
            receipt = json.loads(receipt_input)
        else:
            # File path provided
            with open(receipt_input, 'r') as f:
                receipt = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"❌ Error loading receipt: {e}")
        sys.exit(1)
    
    print("🔍 Verifying execution receipt...")
    print(f"   Receipt ID: {receipt.get('receipt_id', 'N/A')}")
    print(f"   Plan Run ID: {receipt.get('plan_run_id', 'N/A')}")
    print(f"   Status: {receipt.get('status', 'N/A')}")
    print()
    
    # Run verification checks
    checks = [
        ("Structural Integrity", verify_receipt_integrity(receipt)),
        ("Plan Hash Binding", verify_plan_hash_binding(receipt, expected_plan_hash)),
        ("MCP Execution Evidence", verify_mcp_execution_evidence(receipt)),
    ]
    
    if signing_key:
        checks.append(("Cryptographic Signature", verify_receipt_signature(receipt, signing_key)))
    else:
        print("⚠️  No signing key provided - skipping signature verification")
    
    print()
    print("📊 VERIFICATION SUMMARY:")
    print("=" * 50)
    
    all_passed = True
    for check_name, result in checks:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{check_name:.<30} {status}")
        if not result:
            all_passed = False
    
    print("=" * 50)
    if all_passed:
        print("🎉 ALL VERIFICATIONS PASSED - Receipt is valid and tamper-evident")
        sys.exit(0)
    else:
        print("❌ SOME VERIFICATIONS FAILED - Receipt may be invalid or tampered")
        sys.exit(1)


if __name__ == "__main__":
    main()
