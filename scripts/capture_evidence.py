#!/usr/bin/env python3
"""
Evidence capture script for WeMakeDevs AgentHack 2025 submission.
Captures and validates live MCP execution evidence.
"""

import json
import subprocess
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List
import requests


def capture_service_status() -> Dict[str, Any]:
    """Capture current service status and health."""
    evidence = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "check_type": "service_status"
    }
    
    try:
        # Check service readiness
        response = requests.get("http://localhost:8090/readyz", timeout=5)
        evidence["readiness_check"] = {
            "status_code": response.status_code,
            "response": response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text
        }
    except Exception as e:
        evidence["readiness_check"] = {"error": str(e)}
    
    try:
        # Check service health
        response = requests.get("http://localhost:8090/health", timeout=5)
        evidence["health_check"] = {
            "status_code": response.status_code,
            "response": response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text
        }
    except Exception as e:
        evidence["health_check"] = {"error": str(e)}
    
    return evidence


def capture_mcp_execution(plan_hash: str, amount: int = 10000) -> Dict[str, Any]:
    """Capture a live MCP execution for evidence."""
    evidence = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "check_type": "mcp_execution",
        "plan_hash": plan_hash,
        "amount_paise": amount
    }
    
    payload = {
        "plan_hash": plan_hash,
        "engine": "razorpay_mcp_payment_link",
        "require_approval": False,
        "razorpay": {
            "amount": amount,
            "currency": "INR",
            "description": f"Evidence capture - {plan_hash}",
            "customer": {
                "name": "Evidence Capture Bot",
                "email": "evidence@wemakedevs.org"
            }
        }
    }
    
    try:
        start_time = time.time()
        response = requests.post(
            "http://localhost:8090/v1/execute/portia",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=60
        )
        execution_time = time.time() - start_time
        
        evidence["execution"] = {
            "status_code": response.status_code,
            "execution_time_seconds": round(execution_time, 3),
            "response": response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text
        }
        
        # Analyze MCP evidence in response
        if response.status_code == 200:
            result = response.json()
            evidence["mcp_analysis"] = analyze_mcp_evidence(result)
        
    except Exception as e:
        evidence["execution"] = {"error": str(e)}
    
    return evidence


def capture_idempotency_evidence() -> Dict[str, Any]:
    """Capture evidence of idempotency behavior."""
    evidence = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "check_type": "idempotency_test"
    }
    
    # Generate unique idempotency key
    idem_key = f"evidence_{int(time.time())}_{str(uuid.uuid4())[:8]}"
    plan_hash = f"idem_evidence_{int(time.time())}"
    
    payload = {
        "plan_hash": plan_hash,
        "engine": "razorpay_mcp_payment_link",
        "require_approval": False,
        "razorpay": {
            "amount": 1500,
            "currency": "INR",
            "description": "Idempotency evidence test"
        }
    }
    
    headers = {
        "Content-Type": "application/json",
        "Idempotency-Key": idem_key
    }
    
    try:
        # First execution
        start_time = time.time()
        response1 = requests.post(
            "http://localhost:8090/v1/execute/portia",
            json=payload,
            headers=headers,
            timeout=30
        )
        first_exec_time = time.time() - start_time
        
        # Second execution with same idempotency key
        start_time = time.time()
        response2 = requests.post(
            "http://localhost:8090/v1/execute/portia",
            json=payload,
            headers=headers,
            timeout=30
        )
        second_exec_time = time.time() - start_time
        
        evidence["first_execution"] = {
            "status_code": response1.status_code,
            "execution_time_seconds": round(first_exec_time, 3),
            "response": response1.json() if response1.headers.get('content-type', '').startswith('application/json') else response1.text
        }
        
        evidence["second_execution"] = {
            "status_code": response2.status_code,
            "execution_time_seconds": round(second_exec_time, 3),
            "response": response2.json() if response2.headers.get('content-type', '').startswith('application/json') else response2.text
        }
        
        # Analyze idempotency
        if response1.status_code == 200 and response2.status_code == 200:
            result1 = response1.json()
            result2 = response2.json()
            
            evidence["idempotency_analysis"] = {
                "receipt_id_match": result1.get("receipt_id") == result2.get("receipt_id"),
                "plan_run_id_match": result1.get("plan_run_id") == result2.get("plan_run_id"),
                "mcp_id_match": result1.get("mcp", {}).get("id") == result2.get("mcp", {}).get("id"),
                "second_execution_faster": second_exec_time < first_exec_time,
                "first_receipt_id": result1.get("receipt_id"),
                "second_receipt_id": result2.get("receipt_id")
            }
        
    except Exception as e:
        evidence["error"] = str(e)
    
    return evidence


def analyze_mcp_evidence(execution_result: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze execution result for MCP evidence."""
    analysis = {
        "has_mcp_data": "mcp" in execution_result,
        "live_execution": False,
        "fallback_mode": False,
        "razorpay_tool_used": False,
        "tool_name": None
    }
    
    mcp_data = execution_result.get("mcp", {})
    if mcp_data:
        analysis["live_execution"] = mcp_data.get("live_execution", False)
        analysis["fallback_mode"] = mcp_data.get("fallback_mode", False)
        
        tool_name = mcp_data.get("tool", "")
        analysis["tool_name"] = tool_name
        analysis["razorpay_tool_used"] = tool_name.startswith("razorpay.")
        
        # Check for MCP-specific response fields
        analysis["has_mcp_id"] = "id" in mcp_data
        analysis["has_short_url"] = "short_url" in mcp_data
        analysis["has_status"] = "status" in mcp_data
    
    return analysis


def capture_service_logs() -> Dict[str, Any]:
    """Capture recent service logs for evidence."""
    evidence = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "check_type": "service_logs"
    }
    
    try:
        # Try to get logs from common locations
        log_sources = [
            "orchestrator.log",
            "/var/log/orchestrator.log",
            "logs/orchestrator.log"
        ]
        
        logs_found = []
        for log_file in log_sources:
            try:
                with open(log_file, 'r') as f:
                    # Get last 50 lines
                    lines = f.readlines()[-50:]
                    logs_found.append({
                        "source": log_file,
                        "lines_count": len(lines),
                        "recent_lines": [line.strip() for line in lines if line.strip()]
                    })
            except FileNotFoundError:
                continue
        
        evidence["logs"] = logs_found
        
        if not logs_found:
            evidence["note"] = "No log files found at standard locations"
    
    except Exception as e:
        evidence["error"] = str(e)
    
    return evidence


def generate_evidence_report() -> Dict[str, Any]:
    """Generate complete evidence report."""
    report = {
        "report_metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "submission": "WeMakeDevs AgentHack 2025",
            "component": "Razorpay MCP + Portia Integration",
            "version": "1.0.0"
        },
        "evidence": []
    }
    
    print("🔍 Capturing evidence for judge evaluation...")
    
    # Service status
    print("📊 Capturing service status...")
    report["evidence"].append(capture_service_status())
    
    # Live MCP execution
    print("🚀 Capturing live MCP execution...")
    plan_hash = f"evidence_{int(time.time())}"
    report["evidence"].append(capture_mcp_execution(plan_hash))
    
    # Idempotency test
    print("🔄 Capturing idempotency evidence...")
    report["evidence"].append(capture_idempotency_evidence())
    
    # Service logs
    print("📝 Capturing service logs...")
    report["evidence"].append(capture_service_logs())
    
    return report


def main():
    """Main evidence capture function."""
    print("🎯 WeMakeDevs AgentHack 2025 - Evidence Capture")
    print("=" * 60)
    
    evidence_report = generate_evidence_report()
    
    # Save evidence report
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"evidence_report_{timestamp}.json"
    
    with open(filename, 'w') as f:
        json.dump(evidence_report, f, indent=2)
    
    print(f"\n✅ Evidence report saved: {filename}")
    
    # Summary analysis
    print("\n📋 EVIDENCE SUMMARY:")
    print("=" * 40)
    
    for evidence in evidence_report["evidence"]:
        check_type = evidence["check_type"]
        timestamp = evidence["timestamp"]
        
        print(f"\n🔍 {check_type.replace('_', ' ').title()}")
        print(f"   Timestamp: {timestamp}")
        
        if check_type == "service_status":
            readiness = evidence.get("readiness_check", {})
            health = evidence.get("health_check", {})
            print(f"   Readiness: {readiness.get('status_code', 'ERROR')}")
            print(f"   Health: {health.get('status_code', 'ERROR')}")
        
        elif check_type == "mcp_execution":
            execution = evidence.get("execution", {})
            analysis = evidence.get("mcp_analysis", {})
            print(f"   Status: {execution.get('status_code', 'ERROR')}")
            print(f"   Time: {execution.get('execution_time_seconds', 'N/A')}s")
            print(f"   Live MCP: {analysis.get('live_execution', False)}")
            print(f"   Razorpay Tool: {analysis.get('razorpay_tool_used', False)}")
        
        elif check_type == "idempotency_test":
            analysis = evidence.get("idempotency_analysis", {})
            if analysis:
                print(f"   Receipt ID Match: {analysis.get('receipt_id_match', False)}")
                print(f"   Plan Run ID Match: {analysis.get('plan_run_id_match', False)}")
                print(f"   Cached Response: {analysis.get('second_execution_faster', False)}")
    
    print(f"\n🎉 Evidence capture complete! Report: {filename}")


if __name__ == "__main__":
    main()
