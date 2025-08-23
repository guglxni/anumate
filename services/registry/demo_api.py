#!/usr/bin/env python3
"""
Demo script for Capsule Registry API endpoints.

This script demonstrates the implemented API endpoints:
- POST /v1/capsules - Create new Capsule
- GET /v1/capsules - List Capsules with filtering
- GET /v1/capsules/{id} - Get specific Capsule version
- PUT /v1/capsules/{id} - Update Capsule (creates new version)
- DELETE /v1/capsules/{id} - Soft delete Capsule
"""

import json
from uuid import uuid4

from fastapi.testclient import TestClient
from api.main import create_app

# Sample Capsule YAML for demonstration
SAMPLE_CAPSULE_YAML = """
name: demo-capsule
version: 1.0.0
description: Demo capsule for API testing
metadata:
  author: demo-user
  created: 2024-01-01
automation:
  steps:
    - name: greeting
      action: echo
      parameters:
        message: "Hello from Anumate!"
    - name: list-files
      action: ls
      parameters:
        path: "."
tools:
  - echo
  - ls
  - cat
policies:
  - demo-policy
  - security-policy
"""

UPDATED_CAPSULE_YAML = """
name: demo-capsule
version: 1.1.0
description: Updated demo capsule for API testing
metadata:
  author: demo-user
  created: 2024-01-01
  updated: 2024-01-15
automation:
  steps:
    - name: greeting
      action: echo
      parameters:
        message: "Hello from Anumate v1.1!"
    - name: list-files
      action: ls
      parameters:
        path: "."
    - name: show-version
      action: echo
      parameters:
        message: "Version 1.1.0"
tools:
  - echo
  - ls
  - cat
policies:
  - demo-policy
  - security-policy
  - audit-policy
"""


def demo_api_endpoints():
    """Demonstrate all the implemented API endpoints."""
    print("🚀 Anumate Capsule Registry API Demo")
    print("=" * 50)
    
    # Create test client
    app = create_app()
    client = TestClient(app)
    
    # Mock authentication by patching the dependencies
    from unittest.mock import patch
    
    tenant_id = uuid4()
    user_id = uuid4()
    
    with patch('api.dependencies.get_current_tenant', return_value=tenant_id):
        with patch('api.dependencies.get_current_user', return_value=user_id):
            with patch('api.dependencies.get_capsule_service') as mock_service:
                
                # Mock the service responses
                from src.models import Capsule, CapsuleDefinition
                
                # Create sample capsule for responses
                definition = CapsuleDefinition.from_yaml(SAMPLE_CAPSULE_YAML)
                sample_capsule = Capsule.create(
                    tenant_id=tenant_id,
                    definition=definition,
                    created_by=user_id
                )
                
                mock_service_instance = mock_service.return_value
                mock_service_instance.create_capsule.return_value = sample_capsule
                mock_service_instance.list_capsules.return_value = ([sample_capsule], 1)
                mock_service_instance.get_capsule.return_value = sample_capsule
                mock_service_instance.update_capsule.return_value = sample_capsule
                mock_service_instance.delete_capsule.return_value = True
                
                # 1. Test POST /v1/capsules - Create new Capsule
                print("\n1️⃣  POST /v1/capsules - Create new Capsule")
                print("-" * 40)
                
                create_request = {
                    "yaml_content": SAMPLE_CAPSULE_YAML,
                    "sign_capsule": False
                }
                
                response = client.post("/v1/capsules", json=create_request)
                print(f"Status Code: {response.status_code}")
                if response.status_code == 201:
                    data = response.json()
                    print(f"Created Capsule: {data['name']} v{data['version']}")
                    print(f"Capsule ID: {data['capsule_id']}")
                    capsule_id = data['capsule_id']
                else:
                    print(f"Error: {response.json()}")
                    return
                
                # 2. Test GET /v1/capsules - List Capsules
                print("\n2️⃣  GET /v1/capsules - List Capsules")
                print("-" * 40)
                
                response = client.get("/v1/capsules")
                print(f"Status Code: {response.status_code}")
                if response.status_code == 200:
                    data = response.json()
                    print(f"Total Capsules: {data['total']}")
                    print(f"Page: {data['page']}, Page Size: {data['page_size']}")
                    for capsule in data['capsules']:
                        print(f"  - {capsule['name']} v{capsule['version']}")
                
                # 3. Test GET /v1/capsules with filtering
                print("\n3️⃣  GET /v1/capsules?name=demo - List with filter")
                print("-" * 40)
                
                response = client.get("/v1/capsules?name=demo&page=1&page_size=10")
                print(f"Status Code: {response.status_code}")
                if response.status_code == 200:
                    data = response.json()
                    print(f"Filtered Results: {data['total']} capsules")
                
                # 4. Test GET /v1/capsules/{id} - Get specific Capsule
                print(f"\n4️⃣  GET /v1/capsules/{capsule_id} - Get specific Capsule")
                print("-" * 40)
                
                response = client.get(f"/v1/capsules/{capsule_id}")
                print(f"Status Code: {response.status_code}")
                if response.status_code == 200:
                    data = response.json()
                    print(f"Retrieved: {data['name']} v{data['version']}")
                    print(f"Description: {data['definition']['description']}")
                    print(f"Tools: {', '.join(data['definition']['tools'])}")
                
                # 5. Test PUT /v1/capsules/{id} - Update Capsule
                print(f"\n5️⃣  PUT /v1/capsules/{capsule_id} - Update Capsule")
                print("-" * 40)
                
                update_request = {
                    "yaml_content": UPDATED_CAPSULE_YAML,
                    "sign_capsule": False
                }
                
                response = client.put(f"/v1/capsules/{capsule_id}", json=update_request)
                print(f"Status Code: {response.status_code}")
                if response.status_code == 200:
                    data = response.json()
                    print(f"Updated: {data['name']} v{data['version']}")
                
                # 6. Test DELETE /v1/capsules/{id} - Soft delete Capsule
                print(f"\n6️⃣  DELETE /v1/capsules/{capsule_id} - Delete Capsule")
                print("-" * 40)
                
                response = client.delete(f"/v1/capsules/{capsule_id}")
                print(f"Status Code: {response.status_code}")
                if response.status_code == 204:
                    print("✅ Capsule deleted successfully")
                
                # 7. Test additional endpoints
                print("\n7️⃣  Additional Endpoints")
                print("-" * 40)
                
                # Test validation endpoint
                response = client.post("/v1/capsules/validate", json=SAMPLE_CAPSULE_YAML)
                print(f"Validation endpoint status: {response.status_code}")
                
                # Test get versions by name
                response = client.get("/v1/capsules/by-name/demo-capsule")
                print(f"Get versions by name status: {response.status_code}")
                
                # Test get latest version
                response = client.get("/v1/capsules/by-name/demo-capsule/latest")
                print(f"Get latest version status: {response.status_code}")
    
    print("\n✨ API Demo Complete!")
    print("\n📋 Summary of Implemented Endpoints:")
    print("   ✅ POST /v1/capsules - Create new Capsule")
    print("   ✅ GET /v1/capsules - List Capsules with filtering")
    print("   ✅ GET /v1/capsules/{id} - Get specific Capsule version")
    print("   ✅ PUT /v1/capsules/{id} - Update Capsule (creates new version)")
    print("   ✅ DELETE /v1/capsules/{id} - Soft delete Capsule")
    print("   ✅ Additional utility endpoints for validation and versioning")


def show_openapi_spec():
    """Show the OpenAPI specification for the API."""
    print("\n📖 OpenAPI Specification")
    print("=" * 50)
    
    app = create_app()
    openapi_spec = app.openapi()
    
    print(f"Title: {openapi_spec['info']['title']}")
    print(f"Version: {openapi_spec['info']['version']}")
    print(f"Description: {openapi_spec['info']['description']}")
    
    print("\n🛣️  Available Endpoints:")
    for path, methods in openapi_spec['paths'].items():
        for method, details in methods.items():
            print(f"  {method.upper()} {path} - {details.get('summary', 'No summary')}")


if __name__ == "__main__":
    demo_api_endpoints()
    show_openapi_spec()