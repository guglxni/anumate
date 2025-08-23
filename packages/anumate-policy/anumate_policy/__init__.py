from typing import Any, Dict, List


def evaluate_policy(policy: Dict[str, Any], data: Dict[str, Any]) -> bool:
    for rule in policy.get("rules", []):
        if not evaluate_rule(rule, data):
            return False
    return True


def evaluate_rule(rule: Dict[str, Any], data: Dict[str, Any]) -> bool:
    rule_type = rule.get("type")
    if rule_type == "threshold":
        return evaluate_threshold_rule(rule, data)
    elif rule_type == "two_person_rule":
        return evaluate_two_person_rule(rule, data)
    elif rule_type == "dlp":
        return evaluate_dlp_rule(rule, data)
    elif rule_type == "drift":
        return evaluate_drift_rule(rule, data)
    return False


def evaluate_threshold_rule(rule: Dict[str, Any], data: Dict[str, Any]) -> bool:
    field = rule.get("field")
    max_value = rule.get("max")
    if field and max_value and field in data:
        return data[field] <= max_value
    return False


def evaluate_two_person_rule(rule: Dict[str, Any], data: Dict[str, Any]) -> bool:
    approvers = data.get("approvers", [])
    return len(approvers) >= 2


def evaluate_dlp_rule(rule: Dict[str, Any], data: Dict[str, Any]) -> bool:
    # This is a mock implementation. A real implementation would use a DLP scanner.
    return True


def evaluate_drift_rule(rule: Dict[str, Any], data: Dict[str, Any]) -> bool:
    # This is a mock implementation. A real implementation would compare against a baseline.
    return True
