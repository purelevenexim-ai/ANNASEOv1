from services.error_logger import save_error


def process_error_log(payload: dict):
    # Sanitize PII in metadata
    metadata = payload.get("metadata") or {}
    safe_metadata = {}
    for k, v in (metadata or {}).items():
        if any(term in k.lower() for term in ["password", "token", "authorization", "api_key"]):
            safe_metadata[k] = "[REDACTED]"
        else:
            safe_metadata[k] = v

    payload["metadata"] = safe_metadata
    save_error(payload)
