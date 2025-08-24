#!/bin/bash

# 🎯 PRODUCTION DEMO SCRIPT - WeMakeDevs AgentHack 2025
# Real Razorpay MCP + Portia SDK Integration

echo "🚀 PRODUCTION ORCHESTRATOR API - Starting with REAL Razorpay MCP"
echo "📦 Components: FastAPI + Portia v0.7.2 + Razorpay Remote MCP + Moonshot Kimi"
echo ""

# Start the service
echo "🔄 Starting service..."
cd /Users/aaryanguglani/anumate/services/orchestrator
python run_service.py &
SERVICE_PID=$!

echo "⏳ Waiting for service initialization (30s)..."
sleep 30

echo ""
echo "🎯 JUDGE DEMO - Copy/Paste Ready Commands:"
echo "==========================================="
echo ""

echo "1️⃣ Service Readiness Check:"
echo "curl -s localhost:8090/readyz | jq ."
echo ""

echo "2️⃣ Create Payment Link (₹100.00):"
echo "curl -sS -X POST http://localhost:8090/v1/execute/portia \\"
echo "  -H 'Content-Type: application/json' \\"
echo "  -d '{"
echo "    \"plan_hash\": \"judge-demo-payment\","
echo "    \"engine\": \"razorpay_mcp_payment_link\","
echo "    \"require_approval\": false,"
echo "    \"razorpay\": {"
echo "      \"amount\": 10000,"
echo "      \"currency\": \"INR\","
echo "      \"description\": \"Judge Demo Payment\","
echo "      \"customer\": {"
echo "        \"name\": \"WeMakeDevs Judge\","
echo "        \"email\": \"judge@wemakedevs.org\""
echo "      }"
echo "    }"
echo "  }' | jq ."
echo ""

echo "3️⃣ Idempotency Test:"
echo "IDK=key-\$(date +%s)"
echo "# First call:"
echo "curl -sS -X POST http://localhost:8090/v1/execute/portia \\"
echo "  -H 'Content-Type: application/json' \\"
echo "  -H \"Idempotency-Key: \$IDK\" \\"
echo "  -d '{"
echo "    \"plan_hash\": \"idem-test\","
echo "    \"engine\": \"razorpay_mcp_payment_link\","
echo "    \"require_approval\": false,"
echo "    \"razorpay\": {\"amount\": 1500, \"currency\": \"INR\", \"description\": \"Idempotency demo\"}"
echo "  }' | jq ."
echo ""
echo "# Second call (same key) - should return identical result:"
echo "curl -sS -X POST http://localhost:8090/v1/execute/portia \\"
echo "  -H 'Content-Type: application/json' \\"
echo "  -H \"Idempotency-Key: \$IDK\" \\"
echo "  -d '{"
echo "    \"plan_hash\": \"idem-test\","
echo "    \"engine\": \"razorpay_mcp_payment_link\","
echo "    \"require_approval\": false,"
echo "    \"razorpay\": {\"amount\": 1500, \"currency\": \"INR\", \"description\": \"Idempotency demo\"}"
echo "  }' | jq ."
echo ""

echo "🏆 SUCCESS CRITERIA:"
echo "✅ HTTP 200 responses"
echo "✅ plan_run_id and receipt_id generated"  
echo "✅ MCP protocol negotiated (v2025-03-26)"
echo "✅ Razorpay Remote MCP integration working"
echo "✅ Idempotency preventing duplicate operations"
echo "✅ Live execution with fallback safety"
echo ""

echo "📋 Service is running (PID: $SERVICE_PID)"
echo "🌐 Service URL: http://localhost:8090"
echo "📖 API docs: http://localhost:8090/docs"
echo ""

echo "🛑 To stop: kill $SERVICE_PID"
echo ""

# Keep script running
echo "✨ PRODUCTION DEMO READY - Service running in background"
wait $SERVICE_PID
