"""
Issue classifier — maps detected issues to recovery action categories.
"""
from typing import Dict, List


def classify_issues(issues: List[Dict], recovery_rules: Dict) -> List[Dict]:
    """Map detected issues to recovery actions from recovery_rules.

    Each issue gets an "action" key with the corresponding fix instruction
    from recovery_rules["issue_actions"].

    Returns enriched issues with action/instruction fields.
    """
    actions = recovery_rules.get("issue_actions", {})
    classified = []

    for issue in issues:
        issue_type = issue.get("type", "")
        action_def = actions.get(issue_type, {})

        classified.append({
            **issue,
            "action": issue_type,  # e.g., "low_depth", "ai_tone"
            "instruction": action_def.get("instruction", f"Fix the {issue_type} issue"),
        })

    # Sort by severity: high > medium > low
    severity_order = {"high": 0, "medium": 1, "low": 2}
    classified.sort(key=lambda x: severity_order.get(x.get("severity", "low"), 3))

    return classified
