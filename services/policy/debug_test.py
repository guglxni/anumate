#!/usr/bin/env python3
"""
Debug test for Policy DSL components.
"""

import sys
import os

# Add the policy service to the path
policy_path = os.path.join(os.path.dirname(__file__), 'src')
sys.path.insert(0, policy_path)

def test_lexer():
    """Test the lexer component."""
    print("Testing Lexer...")
    
    from lexer import Lexer, TokenType
    
    source = 'policy "test" { }'
    lexer = Lexer(source)
    
    try:
        tokens = lexer.tokenize()
        print(f"✅ Lexer success! Generated {len(tokens)} tokens:")
        for token in tokens:
            print(f"  {token}")
        return True
    except Exception as e:
        print(f"❌ Lexer failed: {e}")
        return False

def test_parser():
    """Test the parser component."""
    print("\nTesting Parser...")
    
    from parser import parse_policy
    
    source = '''policy "Simple Policy" {
    rule "Test Rule" {
        when true
        then allow()
    }
}'''
    
    try:
        policy = parse_policy(source)
        print(f"✅ Parser success! Policy: {policy.name}")
        print(f"  Rules: {len(policy.rules)}")
        if policy.rules:
            print(f"  First rule: {policy.rules[0].name}")
        return True
    except Exception as e:
        print(f"❌ Parser failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_evaluator():
    """Test the evaluator component."""
    print("\nTesting Evaluator...")
    
    from parser import parse_policy
    from evaluator import PolicyEvaluator
    
    source = '''policy "Simple Policy" {
    rule "Test Rule" {
        when true
        then allow()
    }
}'''
    
    try:
        policy = parse_policy(source)
        evaluator = PolicyEvaluator()
        
        data = {"user": {"role": "test"}}
        result = evaluator.evaluate_policy(policy, data)
        
        print(f"✅ Evaluator success!")
        print(f"  Decision: {'ALLOWED' if result.allowed else 'DENIED'}")
        print(f"  Matched rules: {result.matched_rules}")
        return True
    except Exception as e:
        print(f"❌ Evaluator failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🔍 Policy DSL Debug Test")
    print("=" * 30)
    
    success1 = test_lexer()
    success2 = test_parser() if success1 else False
    success3 = test_evaluator() if success2 else False
    
    if success1 and success2 and success3:
        print("\n🎉 All components working!")
    else:
        print("\n❌ Some components failed!")
        sys.exit(1)