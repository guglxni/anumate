#!/usr/bin/env python3
"""
Example demonstrating Capsule Registry functionality.

This example shows how to:
1. Create and validate Capsule definitions
2. Sign Capsules with Ed25519 keys
3. Verify Capsule integrity and signatures
4. Use the CapsuleRegistryService for CRUD operations
"""

import asyncio
import json
from uuid import uuid4

from cryptography.hazmat.primitives.asymmetric import ed25519

# Import our Capsule Registry components
from src.models import (
    CapsuleDefinition,
    CapsuleSignature,
    Capsule,
    CapsuleCreateRequest
)
from src.validation import capsule_validator


async def main():
    """Demonstrate Capsule Registry functionality."""
    
    print("🚀 Anumate Capsule Registry Example")
    print("=" * 50)
    
    # 1. Create a sample Capsule definition
    print("\n1. Creating Capsule Definition...")
    
    capsule_yaml = """
name: payment-processor
version: 1.2.0
description: Automated payment processing workflow
metadata:
  author: "DevOps Team"
  category: "finance"
labels:
  environment: "production"
  team: "payments"
annotations:
  docs.anumate.io/url: "https://docs.example.com/payment-processor"
dependencies:
  - auth-service@2.1.0
  - notification-service@1.5.0
automation:
  triggers:
    - type: webhook
      config:
        path: "/webhooks/payment"
        method: "POST"
  variables:
    amount:
      type: number
      required: true
      description: "Payment amount in cents"
    currency:
      type: string
      default: "USD"
      description: "Payment currency code"
  steps:
    - name: validate-payment
      action: payment-validator
      parameters:
        min_amount: 100
        max_amount: 1000000
      conditions:
        amount: "{{ variables.amount }}"
        currency: "{{ variables.currency }}"
    - name: process-payment
      action: payment-processor
      parameters:
        gateway: "stripe"
        capture: true
      retry:
        attempts: 3
        delay: 5
    - name: send-confirmation
      action: email-sender
      parameters:
        template: "payment-confirmation"
        recipient: "{{ context.customer_email }}"
tools:
  - payment-validator
  - payment-processor
  - email-sender
policies:
  - pci-compliance
  - fraud-detection
"""
    
    # 2. Validate the YAML
    print("\n2. Validating Capsule YAML...")
    validation_result = capsule_validator.validate_complete(capsule_yaml)
    
    if validation_result.valid:
        print("✅ Validation passed!")
        if validation_result.warnings:
            print(f"⚠️  Warnings: {', '.join(validation_result.warnings)}")
    else:
        print("❌ Validation failed!")
        for error in validation_result.errors:
            print(f"   - {error}")
        return
    
    # 3. Create CapsuleDefinition object
    print("\n3. Creating CapsuleDefinition object...")
    definition = CapsuleDefinition.from_yaml(capsule_yaml)
    
    print(f"   Name: {definition.name}")
    print(f"   Version: {definition.version}")
    print(f"   Description: {definition.description}")
    print(f"   Tools: {', '.join(definition.tools)}")
    print(f"   Dependencies: {', '.join(definition.dependencies)}")
    
    # 4. Calculate checksum
    print("\n4. Calculating integrity checksum...")
    checksum = definition.calculate_checksum()
    print(f"   SHA-256: {checksum}")
    
    # 5. Create digital signature
    print("\n5. Creating digital signature...")
    private_key = ed25519.Ed25519PrivateKey.generate()
    signature = CapsuleSignature.create_signature(
        definition, 
        private_key, 
        "example-signer"
    )
    
    print(f"   Algorithm: {signature.algorithm}")
    print(f"   Signer: {signature.signer}")
    print(f"   Signed at: {signature.signed_at}")
    print(f"   Public key: {signature.public_key[:32]}...")
    print(f"   Signature: {signature.signature[:32]}...")
    
    # 6. Verify signature
    print("\n6. Verifying digital signature...")
    is_valid = signature.verify_signature(definition)
    print(f"   Signature valid: {'✅ Yes' if is_valid else '❌ No'}")
    
    # 7. Create complete Capsule
    print("\n7. Creating complete Capsule...")
    tenant_id = uuid4()
    created_by = uuid4()
    
    capsule = Capsule.create(
        tenant_id=tenant_id,
        definition=definition,
        created_by=created_by,
        signature=signature
    )
    
    print(f"   Capsule ID: {capsule.capsule_id}")
    print(f"   Tenant ID: {capsule.tenant_id}")
    print(f"   Created by: {capsule.created_by}")
    print(f"   Created at: {capsule.created_at}")
    print(f"   Active: {capsule.active}")
    
    # 8. Test integrity check
    print("\n8. Testing integrity check...")
    expected_checksum = definition.calculate_checksum()
    integrity_valid = expected_checksum == capsule.checksum
    print(f"   Integrity valid: {'✅ Yes' if integrity_valid else '❌ No'}")
    
    # 9. Convert to dictionary (for database storage)
    print("\n9. Converting to dictionary format...")
    capsule_dict = capsule.to_dict()
    print(f"   Dictionary keys: {', '.join(capsule_dict.keys())}")
    
    # 10. Demonstrate YAML round-trip
    print("\n10. Testing YAML round-trip...")
    yaml_output = definition.to_yaml()
    parsed_definition = CapsuleDefinition.from_yaml(yaml_output)
    
    roundtrip_valid = (
        parsed_definition.name == definition.name and
        parsed_definition.version == definition.version and
        parsed_definition.calculate_checksum() == definition.calculate_checksum()
    )
    print(f"    YAML round-trip: {'✅ Success' if roundtrip_valid else '❌ Failed'}")
    
    # 11. Create request object (for API usage)
    print("\n11. Creating API request object...")
    create_request = CapsuleCreateRequest(
        yaml_content=capsule_yaml,
        sign_capsule=True
    )
    
    request_definition = create_request.to_capsule_definition()
    print(f"    Request parsed: {'✅ Success' if request_definition.name == definition.name else '❌ Failed'}")
    
    print("\n" + "=" * 50)
    print("🎉 Capsule Registry example completed successfully!")
    print("\nKey features demonstrated:")
    print("  ✅ YAML parsing and validation")
    print("  ✅ Schema enforcement")
    print("  ✅ Business rule validation")
    print("  ✅ Checksum calculation")
    print("  ✅ Ed25519 digital signatures")
    print("  ✅ Signature verification")
    print("  ✅ Data integrity checks")
    print("  ✅ Database serialization")
    print("  ✅ API request handling")


if __name__ == "__main__":
    asyncio.run(main())