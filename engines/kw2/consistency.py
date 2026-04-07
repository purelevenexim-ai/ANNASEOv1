"""
kw2 Phase 1 helper — AI consistency check for business profile.
"""
import json
import logging

from engines.kw2.ai_caller import kw2_ai_call, kw2_extract_json
from engines.kw2.prompts import CONSISTENCY_CHECK_SYSTEM, CONSISTENCY_CHECK_USER

log = logging.getLogger("kw2.consistency")


def check_consistency(profile: dict, ai_provider: str = "auto") -> bool:
    """
    Ask AI to validate that a business profile is internally consistent.

    Returns True if valid (or on any error — fail-open to avoid blocking pipeline).
    If False, issues are logged for debugging.
    """
    try:
        profile_json = json.dumps(profile, indent=2, default=str)
        prompt = CONSISTENCY_CHECK_USER.format(profile_json=profile_json)
        response = kw2_ai_call(prompt, CONSISTENCY_CHECK_SYSTEM, provider=ai_provider)

        result = kw2_extract_json(response)
        if not result or not isinstance(result, dict):
            log.debug("Consistency check returned unparseable response — assuming valid")
            return True

        valid = result.get("valid", True)
        if not valid:
            issues = result.get("issues", [])
            log.warning(f"Business profile consistency issues: {issues}")

        return bool(valid)

    except Exception as e:
        log.warning(f"Consistency check failed (proceeding anyway): {e}")
        return True
