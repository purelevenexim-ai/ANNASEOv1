import json
import re


def extract_json(text: str) -> str:
    if not isinstance(text, str):
        return text
    # finds first top-level JSON object or array
    match = re.search(r"(\{(?:.|\n)*\}|\[(?:.|\n)*\])", text, re.DOTALL)
    return match.group(0) if match else text


def sanitize_llm_output(text: str) -> str:
    if not isinstance(text, str):
        return text
    t = text.strip()
    # remove code fences
    t = re.sub(r"```(?:json)?", "", t, flags=re.IGNORECASE)
    t = t.strip()

    # Extract first JSON object or array
    if "{" in t or "[" in t:
        candidates = []
        idx_curly = t.find("{")
        idx_sq = t.find("[")
        if idx_curly != -1:
            candidates.append(idx_curly)
        if idx_sq != -1:
            candidates.append(idx_sq)
        if candidates:
            first_brace = min(candidates)
            last_brace = max(t.rfind("}"), t.rfind("]"))
            if last_brace > first_brace:
                t = t[first_brace:last_brace + 1]

    t = t.strip()
    return t


def parse_llm_json(raw_text: str):
    if raw_text is None:
        return None, "raw_text is None"

    text = extract_json(raw_text)
    try:
        return json.loads(text), None
    except Exception as e:
        # Try sanitized version
        cleaned = sanitize_llm_output(raw_text)
        try:
            return json.loads(cleaned), None
        except Exception as e2:
            return None, f"first_error={e}; sanitize_error={e2}"
