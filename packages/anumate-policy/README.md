# Anumate Policy

This package provides a policy DSL evaluation engine for the Anumate platform.

## Usage

To use this package, you can define policies as dictionaries and evaluate them against data:

```python
from anumate_policy import evaluate_policy

policy = {
    "rules": [
        {"type": "threshold", "field": "amount", "max": 100},
        {"type": "two_person_rule"},
    ]
}

data = {"amount": 50, "approvers": ["user1", "user2"]}

if evaluate_policy(policy, data):
    print("Policy passed")
else:
    print("Policy failed")
```
