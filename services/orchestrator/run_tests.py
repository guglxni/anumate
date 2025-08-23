#!/usr/bin/env python3
"""Test runner for orchestrator service with proper path setup."""

import sys
import os
import subprocess
from pathlib import Path

def setup_python_path():
    """Setup Python path to include all necessary packages."""
    # Get the current directory (services/orchestrator)
    current_dir = Path(__file__).parent.absolute()
    
    # Add paths to sys.path
    paths_to_add = [
        str(current_dir),  # services/orchestrator
        str(current_dir / "../../packages/anumate-infrastructure"),
        str(current_dir / "../../packages/anumate-tracing"), 
        str(current_dir / "../../packages/anumate-events"),
        str(current_dir / "../../packages/anumate-logging"),
        str(current_dir / "../../packages/anumate-core-config"),
        str(current_dir / "../../packages/anumate-errors"),
        str(current_dir / "../../packages/anumate-oidc"),
    ]
    
    for path in paths_to_add:
        if path not in sys.path:
            sys.path.insert(0, path)
    
    # Set PYTHONPATH environment variable
    current_pythonpath = os.environ.get('PYTHONPATH', '')
    new_pythonpath = ':'.join(paths_to_add)
    if current_pythonpath:
        new_pythonpath = f"{new_pythonpath}:{current_pythonpath}"
    
    os.environ['PYTHONPATH'] = new_pythonpath

def run_tests():
    """Run the tests with proper setup."""
    setup_python_path()
    
    # Change to orchestrator directory
    os.chdir(Path(__file__).parent)
    
    print("🧪 Running Orchestrator Tests")
    print("=" * 40)
    
    # Test cases to run
    test_commands = [
        # Simple standalone tests that work
        ["python", "test_api_simple.py"],
        ["python", "test_execution_monitor_simple.py"],
        
        # Try pytest with proper path setup
        ["python", "-m", "pytest", "tests/test_api.py", "-v", "--tb=short"],
        ["python", "-m", "pytest", "tests/test_execution_monitor.py", "-v", "--tb=short"],
    ]
    
    results = []
    
    for i, cmd in enumerate(test_commands, 1):
        print(f"\n📋 Test {i}: {' '.join(cmd)}")
        print("-" * 30)
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                print("✅ PASSED")
                results.append(("PASSED", cmd))
                if result.stdout:
                    print(result.stdout)
            else:
                print("❌ FAILED")
                results.append(("FAILED", cmd))
                if result.stderr:
                    print("STDERR:", result.stderr)
                if result.stdout:
                    print("STDOUT:", result.stdout)
                    
        except subprocess.TimeoutExpired:
            print("⏰ TIMEOUT")
            results.append(("TIMEOUT", cmd))
        except Exception as e:
            print(f"💥 ERROR: {e}")
            results.append(("ERROR", cmd))
    
    # Summary
    print("\n" + "=" * 40)
    print("📊 Test Results Summary")
    print("=" * 40)
    
    passed = sum(1 for status, _ in results if status == "PASSED")
    total = len(results)
    
    for status, cmd in results:
        status_icon = {
            "PASSED": "✅",
            "FAILED": "❌", 
            "TIMEOUT": "⏰",
            "ERROR": "💥"
        }.get(status, "❓")
        
        print(f"{status_icon} {status}: {' '.join(cmd)}")
    
    print(f"\n🎯 Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed!")
        return 0
    else:
        print("⚠️  Some tests failed")
        return 1

if __name__ == "__main__":
    exit_code = run_tests()
    sys.exit(exit_code)