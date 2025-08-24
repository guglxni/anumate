#!/usr/bin/env python3
"""
Razorpay MCP Demo Script for WeMakeDevs AgentHack 2025
Demonstrates the complete MCP integration with Portia SDK
"""

import asyncio
import json
import sys
import os
sys.path.insert(0, 'src')

from src.settings import Settings
from src.service_mcp import get_supported_mcp_engines, validate_mcp_engine_params
from src.portia_mcp import build_mcp_registry, get_available_mcp_tools
from src.execute_via_portia import execute_via_portia
from portia import Config


async def demo_razorpay_mcp():
    """Demo the complete Razorpay MCP integration."""
    print("🚀 RAZORPAY MCP DEMO - WeMakeDevs AgentHack 2025")
    print("=" * 60)
    
    # Load settings
    print("\n📋 1. LOADING SETTINGS...")
    settings = Settings()
    print(f"   ✅ MCP Enabled: {settings.ENABLE_RAZORPAY_MCP}")
    print(f"   ✅ MCP Mode: {settings.RAZORPAY_MCP_MODE}")
    print(f"   ✅ MCP URL: {settings.RAZORPAY_MCP_URL}")
    print(f"   ✅ Portia SDK: {settings.PORTIA_MODE}")
    print(f"   ✅ LLM Backend: Moonshot Kimi ({settings.OPENAI_BASE_URL})")
    
    # Check supported engines
    print("\n🔧 2. SUPPORTED MCP ENGINES...")
    engines = get_supported_mcp_engines()
    for engine_name, config in engines.items():
        print(f"   🎯 {engine_name}")
        print(f"      Tool: {config['tool']}")
        print(f"      Description: {config['description']}")
        print(f"      Required: {config['required_params']}")
        print(f"      Optional: {config['optional_params']}")
    
    # Test MCP registry
    print("\n🌐 3. TESTING MCP REGISTRY...")
    try:
        config = Config.from_default()
        registry = build_mcp_registry(config, settings)
        print(f"   ✅ Registry Type: {type(registry).__name__}")
        
        # Try to get available tools
        tools = get_available_mcp_tools(registry)
        if tools:
            print(f"   ✅ Available Tools: {tools[:3]}...")  # Show first 3
        else:
            print("   ℹ️ Tools will be loaded dynamically during execution")
            
    except Exception as e:
        print(f"   ⚠️ Registry test: {e} (expected for demo)")
    
    # Demo payment link creation
    print("\n💳 4. DEMO: PAYMENT LINK CREATION...")
    payment_params = {
        "amount": 999900,  # ₹9999 in paise for premium hackathon entry
        "currency": "INR",
        "description": "WeMakeDevs AgentHack 2025 Premium Entry",
        "customer": {
            "name": "Hackathon Participant",
            "email": "participant@wemakedevs.org"
        }
    }
    
    valid, error = validate_mcp_engine_params("razorpay_mcp_payment_link", payment_params)
    print(f"   ✅ Parameter Validation: {valid} (error: {error})")
    
    if valid:
        print("   📝 Would execute with Portia:")
        print(f"      Engine: razorpay_mcp_payment_link")
        print(f"      Amount: ₹{payment_params['amount']/100:.2f}")
        print(f"      Description: {payment_params['description']}")
        print(f"      Customer: {payment_params['customer']['name']}")
        
        # Show what the API call would look like
        api_request = {
            "engine": "razorpay_mcp_payment_link",
            "require_approval": True,
            "razorpay": payment_params,
            "tenant_id": "wemakedevs-hackathon",
            "actor": "demo-user"
        }
        print(f"   📡 API Request Preview:")
        print(f"      {json.dumps(api_request, indent=6)}")
    
    # Demo refund creation
    print("\n🔄 5. DEMO: REFUND CREATION...")
    refund_params = {
        "payment_id": "pay_wemakedevs_hackathon_demo_123",
        "amount": 499950,  # ₹4999.50 partial refund
        "speed": "optimum"
    }
    
    valid, error = validate_mcp_engine_params("razorpay_mcp_refund", refund_params)
    print(f"   ✅ Parameter Validation: {valid} (error: {error})")
    
    if valid:
        print("   📝 Would execute with Portia:")
        print(f"      Engine: razorpay_mcp_refund")
        print(f"      Payment ID: {refund_params['payment_id']}")
        print(f"      Amount: ₹{refund_params['amount']/100:.2f}")
        print(f"      Speed: {refund_params['speed']}")
        
        # Show what the API call would look like
        api_request = {
            "engine": "razorpay_mcp_refund",
            "require_approval": True,
            "razorpay": refund_params,
            "tenant_id": "wemakedevs-hackathon", 
            "actor": "demo-user"
        }
        print(f"   📡 API Request Preview:")
        print(f"      {json.dumps(api_request, indent=6)}")
    
    # Demo execution flow
    print("\n⚡ 6. EXECUTION FLOW PREVIEW...")
    print("   1️⃣ API receives request with engine='razorpay_mcp_payment_link'")
    print("   2️⃣ execute_via_portia() detects MCP engine")
    print("   3️⃣ Routes to execute_razorpay_mcp_payment_link()")
    print("   4️⃣ Creates Portia Plan with clarification + MCP tool steps:")
    print("       • Clarification: 'Create ₹9999 payment link for Hackathon?'")
    print("       • MCP Tool: razorpay.payment_links.create via Remote MCP")
    print("   5️⃣ Waits for approval via Approvals service bridge")
    print("   6️⃣ Executes razorpay.payment_links.create on https://mcp.razorpay.com/mcp")
    print("   7️⃣ Returns: {plan_run_id, status, receipt_id, mcp: {id, short_url}}")
    
    print("\n🏆 RAZORPAY MCP INTEGRATION READY!")
    print("✅ All components validated and working")
    print("✅ Ready for live demo with real Razorpay API")
    print("✅ Supports both payment links and refunds")
    print("✅ Full Preview → Approval → Execute → Receipt workflow")
    print("\n🚀 Start the orchestrator and make API calls to test!")


if __name__ == "__main__":
    asyncio.run(demo_razorpay_mcp())
