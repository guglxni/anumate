from typing import Any, Dict

from anumate_crypto import canonical_json_serialize, sha256_hash


def generate_plan_hash(plan: Dict[str, Any]) -> str:
    normalized_plan = _normalize_plan(plan)
    serialized_plan = canonical_json_serialize(normalized_plan)
    return sha256_hash(serialized_plan).hex()


def _normalize_plan(plan: Dict[str, Any]) -> Dict[str, Any]:
    # In a real implementation, this would be more sophisticated,
    # handling different number types and string formats.
    return plan
