"""
GSC Engine — OAuth2 + Google Search Console API Client
Handles: auth URL generation, token exchange, token refresh, query fetching.
Phase 3 Upgrade: API key validation for Gemini AI features.
"""
import os
import json
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
import logging

from . import gsc_db

log = logging.getLogger(__name__)

# ─── Config ──────────────────────────────────────────────────────────────────

SCOPES = "https://www.googleapis.com/auth/webmasters.readonly"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
GSC_API_BASE = "https://www.googleapis.com/webmasters/v3"
GEMINI_MODELS_URL = "https://generativelanguage.googleapis.com/v1beta/models"
GEMINI_GENERATE_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"


# ─── API Key Validation (Phase 3) ────────────────────────────────────────────

def validate_gemini_key(api_key: str) -> dict:
    """
    Validate a Gemini API key by listing models. Returns validation result.
    Tries: list models endpoint, then a simple generate call.
    """
    if not api_key or len(api_key) < 10:
        return {"valid": False, "error": "Invalid key format"}

    # Try listing models
    url = f"{GEMINI_MODELS_URL}?key={api_key}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            models = [m["name"] for m in data.get("models", [])[:5]]
            return {
                "valid": True,
                "provider": "gemini",
                "models": models,
                "model_count": len(data.get("models", [])),
            }
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:500]
        if e.code == 403 and "Generative Language API" in body:
            return {
                "valid": False,
                "error": "Generative Language API not enabled for this project",
                "hint": "Enable at: https://console.developers.google.com/apis/api/generativelanguage.googleapis.com",
                "key_recognized": True,
            }
        return {"valid": False, "error": f"HTTP {e.code}: {body[:200]}"}
    except Exception as e:
        return {"valid": False, "error": str(e)}


def get_best_gemini_key() -> str | None:
    """
    Return the best available Gemini API key.
    Priority: GCP_API_KEY → GEMINI_PAID_API_KEY → GEMINI_API_KEY
    Validates each before returning.
    """
    for env_var in ("GCP_API_KEY", "GEMINI_PAID_API_KEY", "GEMINI_API_KEY"):
        key = os.getenv(env_var, "")
        if key and len(key) > 10:
            result = validate_gemini_key(key)
            if result.get("valid"):
                log.info(f"[GSC] Using Gemini key from {env_var}")
                return key
    return None


def _client_id() -> str:
    v = os.getenv("GOOGLE_CLIENT_ID", "")
    if not v:
        raise ValueError("GOOGLE_CLIENT_ID not set in environment")
    return v


def _client_secret() -> str:
    v = os.getenv("GOOGLE_CLIENT_SECRET", "")
    if not v:
        raise ValueError("GOOGLE_CLIENT_SECRET not set in environment")
    return v


def _redirect_uri() -> str:
    return os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/api/gsc/auth/callback")


# ─── OAuth ───────────────────────────────────────────────────────────────────

def get_auth_url(project_id: str) -> str:
    """Generate Google OAuth URL. state param encodes project_id."""
    params = {
        "client_id": _client_id(),
        "redirect_uri": _redirect_uri(),
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "offline",
        "prompt": "consent",          # force showing consent to get refresh_token
        "state": project_id,
    }
    return f"{AUTH_URL}?{urllib.parse.urlencode(params)}"


def exchange_code(code: str, project_id: str) -> dict:
    """Exchange authorization code for access + refresh tokens. Saves to DB."""
    data = urllib.parse.urlencode({
        "code": code,
        "client_id": _client_id(),
        "client_secret": _client_secret(),
        "redirect_uri": _redirect_uri(),
        "grant_type": "authorization_code",
    }).encode()

    req = urllib.request.Request(TOKEN_URL, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    with urllib.request.urlopen(req, timeout=15) as resp:
        tokens = json.loads(resp.read())

    if "error" in tokens:
        raise ValueError(f"Token exchange error: {tokens['error']} — {tokens.get('error_description')}")

    expiry = (datetime.utcnow() + timedelta(seconds=tokens.get("expires_in", 3600))).isoformat()
    gsc_db.upsert_integration(
        project_id,
        access_token=tokens["access_token"],
        refresh_token=tokens.get("refresh_token"),
        token_expiry=expiry,
        status="connected",
    )
    log.info(f"[GSC] Tokens stored for project {project_id}")
    return tokens


def _refresh_access_token(project_id: str) -> str:
    """Use refresh_token to get a new access_token. Returns new access_token."""
    integration = gsc_db.get_integration(project_id)
    if not integration or not integration.get("refresh_token"):
        raise ValueError("No refresh token stored — user must re-authenticate")

    data = urllib.parse.urlencode({
        "client_id": _client_id(),
        "client_secret": _client_secret(),
        "refresh_token": integration["refresh_token"],
        "grant_type": "refresh_token",
    }).encode()

    req = urllib.request.Request(TOKEN_URL, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    with urllib.request.urlopen(req, timeout=15) as resp:
        tokens = json.loads(resp.read())

    if "error" in tokens:
        gsc_db.set_integration_status(project_id, "error")
        raise ValueError(f"Token refresh error: {tokens['error']}")

    expiry = (datetime.utcnow() + timedelta(seconds=tokens.get("expires_in", 3600))).isoformat()
    gsc_db.upsert_integration(
        project_id,
        access_token=tokens["access_token"],
        token_expiry=expiry,
        status="connected",
    )
    return tokens["access_token"]


def _get_valid_token(project_id: str) -> str:
    """Return a valid access token, refreshing if expired."""
    integration = gsc_db.get_integration(project_id)
    if not integration or integration.get("status") != "connected":
        raise ValueError("GSC not connected for this project")

    expiry_str = integration.get("token_expiry")
    if expiry_str:
        expiry = datetime.fromisoformat(expiry_str)
        if datetime.utcnow() >= expiry - timedelta(minutes=5):
            log.info(f"[GSC] Token expired for {project_id}, refreshing...")
            return _refresh_access_token(project_id)

    return integration["access_token"]


# ─── GSC API Calls ───────────────────────────────────────────────────────────

def _api_get(project_id: str, path: str) -> dict:
    """Authenticated GET to GSC API."""
    token = _get_valid_token(project_id)
    url = f"{GSC_API_BASE}{path}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def _api_post(project_id: str, path: str, body: dict) -> dict:
    """Authenticated POST to GSC API."""
    token = _get_valid_token(project_id)
    url = f"{GSC_API_BASE}{path}"
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def list_sites(project_id: str) -> list[dict]:
    """List all verified sites in the user's GSC account."""
    result = _api_get(project_id, "/sites")
    sites = result.get("siteEntry", [])
    return [{"url": s["siteUrl"], "permission": s.get("permissionLevel")} for s in sites]


def fetch_queries(
    project_id: str,
    site_url: str,
    days: int = 90,
    row_limit: int = 25000,
) -> list[dict]:
    """
    Fetch all queries from GSC for the given site and date range.
    Returns list of: {keys:[query], clicks, impressions, ctr, position}
    Uses pagination to get up to row_limit rows in a single call (GSC max per page = 25000).
    """
    end_date = datetime.utcnow().date()
    start_date = end_date - timedelta(days=days)
    date_start = start_date.isoformat()
    date_end = end_date.isoformat()

    encoded_site = urllib.parse.quote(site_url, safe="")
    path = f"/sites/{encoded_site}/searchAnalytics/query"

    all_rows = []
    start_row = 0

    while True:
        body = {
            "startDate": date_start,
            "endDate": date_end,
            "dimensions": ["query"],
            "rowLimit": min(row_limit, 25000),
            "startRow": start_row,
        }
        result = _api_post(project_id, path, body)
        rows = result.get("rows", [])
        if not rows:
            break

        all_rows.extend(rows)
        log.info(f"[GSC] Fetched {len(rows)} rows (total: {len(all_rows)})")

        if len(rows) < 25000 or len(all_rows) >= row_limit:
            break

        start_row += len(rows)

    log.info(f"[GSC] Total queries fetched: {len(all_rows)} for {site_url}")

    # Store raw data to DB
    gsc_db.upsert_raw_keywords(project_id, all_rows, date_start, date_end)

    return all_rows


def search_keyword(
    project_id: str,
    site_url: str,
    query_filter: str,
    days: int = 90,
    row_limit: int = 1000,
) -> list[dict]:
    """
    Search GSC for queries containing the given keyword filter.
    Uses dimensionFilterGroups to narrow results server-side.
    Returns list of: {keyword, clicks, impressions, ctr, position}
    Sorted by impressions desc — effectively top traffic keywords containing that term.
    """
    end_date = datetime.utcnow().date()
    start_date = (end_date - timedelta(days=days))
    encoded_site = urllib.parse.quote(site_url, safe="")
    path = f"/sites/{encoded_site}/searchAnalytics/query"

    all_rows = []
    start_row = 0

    while True:
        body = {
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
            "dimensions": ["query"],
            "dimensionFilterGroups": [{
                "filters": [{
                    "dimension": "query",
                    "operator": "contains",
                    "expression": query_filter.lower(),
                }]
            }],
            "rowLimit": min(row_limit, 25000),
            "startRow": start_row,
            "orderBy": [{"fieldName": "impressions", "sortOrder": "descending"}],
        }
        result = _api_post(project_id, path, body)
        rows = result.get("rows", [])
        if not rows:
            break

        all_rows.extend(rows)
        if len(rows) < 25000 or len(all_rows) >= row_limit:
            break
        start_row += len(rows)

    # Normalise row format: {keyword, clicks, impressions, ctr, position}
    return [
        {
            "keyword":     r["keys"][0],
            "clicks":      r.get("clicks", 0),
            "impressions": r.get("impressions", 0),
            "ctr":         round(r.get("ctr", 0), 4),
            "position":    round(r.get("position", 0), 1),
        }
        for r in all_rows
    ]

