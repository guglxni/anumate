# Anumate Plan Hash

This package provides deterministic plan hash generation for the Anumate platform.

## Usage

To use this package, you can generate a hash for a plan dictionary:

```python
from anumate_planhash import generate_plan_hash

plan = {
    "steps": [
        {"tool": "tool-a", "args": {"arg1": "value1"}},
        {"tool": "tool-b", "args": {"arg2": "value2"}},
    ]
}

plan_hash = generate_plan_hash(plan)
```

The hash is generated based on a canonical representation of the plan, ensuring that semantically equivalent plans have the same hash.
