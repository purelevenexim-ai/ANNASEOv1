"""
================================================================================
MULTI-PLATFORM RESEARCH ENGINE
================================================================================
Phase 2 — Research topics across platforms (Backlinko Step 2, Semrush Step 1).

Implements:
- Google Autocomplete suggestions
- YouTube search suggestions
- Reddit topic mining
- AI/LLM topic exploration
- Customer insight collection
- Competitor keyword stealing (delegates to competitor_gap engine)

Reference: Backlinko "Research Topics Across Platforms"
           "Search Everywhere Optimization — understanding how searchers explore
            a topic across different platforms"
================================================================================
"""

from __future__ import annotations
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

import requests

log = logging.getLogger("annaseo.multi_platform_research")

_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0",
    "Accept": "application/json, text/html, */*",
})

REQUEST_TIMEOUT = 10


# ─────────────────────────────────────────────────────────────────────────────
# GOOGLE AUTOCOMPLETE
# ─────────────────────────────────────────────────────────────────────────────

def google_autocomplete(seed: str, language: str = "en", region: str = "us") -> List[str]:
    """
    Fetch Google Autocomplete suggestions for a seed keyword.
    These come directly from Google's data — people are actively searching for them.
    Long-tail keywords that are less competitive and easier to rank for.
    """
    suggestions = []
    try:
        url = "https://suggestqueries.google.com/complete/search"
        params = {"client": "firefox", "q": seed, "hl": language, "gl": region}
        resp = _SESSION.get(url, params=params, timeout=REQUEST_TIMEOUT)
        if resp.ok:
            data = resp.json()
            if isinstance(data, list) and len(data) > 1:
                suggestions = [s for s in data[1] if isinstance(s, str) and s != seed]
    except Exception as e:
        log.warning("[Research] Google autocomplete error for '%s': %s", seed, e)

    # Also try prefix/suffix variations
    for prefix in ["best ", "how to ", "why ", "what is "]:
        try:
            params["q"] = prefix + seed
            resp = _SESSION.get(url, params=params, timeout=REQUEST_TIMEOUT)
            if resp.ok:
                data = resp.json()
                if isinstance(data, list) and len(data) > 1:
                    suggestions.extend([s for s in data[1] if isinstance(s, str)])
            time.sleep(0.3)
        except Exception:
            pass

    # Alphabet soup method (a, b, c, ... appended)
    for letter in "abcdefghij":
        try:
            params["q"] = f"{seed} {letter}"
            resp = _SESSION.get(url, params=params, timeout=REQUEST_TIMEOUT)
            if resp.ok:
                data = resp.json()
                if isinstance(data, list) and len(data) > 1:
                    suggestions.extend([s for s in data[1] if isinstance(s, str)])
            time.sleep(0.2)
        except Exception:
            pass

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for s in suggestions:
        s_clean = s.strip().lower()
        if s_clean and s_clean not in seen:
            seen.add(s_clean)
            unique.append(s.strip())

    log.info("[Research] Google autocomplete for '%s': %d suggestions", seed, len(unique))
    return unique


# ─────────────────────────────────────────────────────────────────────────────
# YOUTUBE SEARCH SUGGESTIONS
# ─────────────────────────────────────────────────────────────────────────────

def youtube_suggestions(seed: str) -> List[Dict[str, str]]:
    """
    Get YouTube search suggestions. YouTube is the second-largest search engine.
    People search differently there than on Google.

    Reference: Backlinko "Check YouTube"
    """
    results = []
    try:
        url = "https://suggestqueries.google.com/complete/search"
        params = {"client": "youtube", "ds": "yt", "q": seed}
        resp = _SESSION.get(url, params=params, timeout=REQUEST_TIMEOUT)
        if resp.ok:
            # YouTube returns JSONP-like format
            text = resp.text
            # Extract JSON array
            match = re.search(r'\[.*\]', text, re.DOTALL)
            if match:
                data = json.loads(match.group())
                if isinstance(data, list) and len(data) > 1:
                    for item in data[1]:
                        if isinstance(item, list) and item:
                            results.append({
                                "suggestion": item[0],
                                "platform": "youtube",
                            })
    except Exception as e:
        log.warning("[Research] YouTube suggestions error for '%s': %s", seed, e)

    log.info("[Research] YouTube suggestions for '%s': %d results", seed, len(results))
    return results


# ─────────────────────────────────────────────────────────────────────────────
# REDDIT TOPIC MINING
# ─────────────────────────────────────────────────────────────────────────────

def reddit_topics(seed: str, limit: int = 25) -> List[Dict[str, Any]]:
    """
    Mine Reddit for topics and questions about a subject.
    Reddit discussions often reveal questions and problems that don't show up
    in traditional keyword research.

    Reference: Backlinko "Explore Reddit"
    Focus on: common questions, pain points, recommended tools/solutions
    """
    results = []
    try:
        url = f"https://www.reddit.com/search.json"
        params = {"q": seed, "sort": "relevance", "limit": limit, "t": "year"}
        headers = {"User-Agent": "AnnaSEO-Research/1.0"}
        resp = _SESSION.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)

        if resp.ok:
            data = resp.json()
            posts = data.get("data", {}).get("children", [])
            for post in posts:
                pdata = post.get("data", {})
                title = pdata.get("title", "")
                subreddit = pdata.get("subreddit", "")
                score = pdata.get("score", 0)
                num_comments = pdata.get("num_comments", 0)
                selftext = (pdata.get("selftext", "") or "")[:300]

                if title and score > 1:
                    # Extract question patterns
                    is_question = any(title.lower().startswith(q) for q in
                                      ["how", "what", "why", "is ", "can ", "should", "best ", "which"])
                    results.append({
                        "title": title,
                        "subreddit": subreddit,
                        "score": score,
                        "comments": num_comments,
                        "engagement": score + num_comments,
                        "is_question": is_question,
                        "snippet": selftext,
                        "platform": "reddit",
                    })
    except Exception as e:
        log.warning("[Research] Reddit search error for '%s': %s", seed, e)

    # Sort by engagement
    results.sort(key=lambda x: x["engagement"], reverse=True)
    log.info("[Research] Reddit topics for '%s': %d results", seed, len(results))
    return results


# ─────────────────────────────────────────────────────────────────────────────
# AI/LLM TOPIC EXPLORATION
# ─────────────────────────────────────────────────────────────────────────────

def ai_topic_exploration(seed: str, business_context: str = "", ollama_url: str = "http://172.235.16.165:11434") -> List[Dict[str, str]]:
    """
    Use local LLM to explore topic variations and discover keyword opportunities.

    Reference: Backlinko "Ask AI" — query AI with context for natural language
    keyword discovery and topic categorization.
    """
    results = []

    prompt = f"""You are an SEO research assistant. Given the topic "{seed}" and business context: "{business_context}",
generate 20 keyword/topic opportunities across these categories:

1. Question patterns (how people naturally phrase problems)
2. Comparison queries (X vs Y)
3. Commercial intent keywords (best, review, buy, price)
4. Informational long-tail keywords
5. Conversational/natural language queries (as people ask AI tools)

Return as JSON array: [{{"keyword": "...", "category": "...", "intent": "informational|commercial|transactional|navigational", "search_potential": "high|medium|low"}}]

Only return the JSON array, no other text."""

    try:
        resp = requests.post(
            f"{ollama_url}/api/generate",
            json={"model": "deepseek-r1:8b", "prompt": prompt, "stream": False},
            timeout=60,
        )
        if resp.ok:
            text = resp.json().get("response", "")
            # Strip <think> blocks if present
            text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
            # Extract JSON
            match = re.search(r'\[.*\]', text, re.DOTALL)
            if match:
                results = json.loads(match.group())
    except Exception as e:
        log.warning("[Research] AI topic exploration error: %s", e)

    log.info("[Research] AI topics for '%s': %d results", seed, len(results))
    return results


# ─────────────────────────────────────────────────────────────────────────────
# CUSTOMER INSIGHT COLLECTOR
# ─────────────────────────────────────────────────────────────────────────────
# From Backlinko: "Before you open a single keyword tool, you have access to
# intelligence that your competitors don't: direct customer insights."

INSIGHT_TEMPLATES = {
    "ecommerce": {
        "sources": ["product_reviews", "support_tickets", "return_reasons"],
        "example_queries": ["Why does X break after Y months?", "X vs Y comparison"],
    },
    "local": {
        "sources": ["walk_in_questions", "phone_inquiries", "seasonal_patterns"],
        "example_queries": ["Best X near me", "X open on Sunday", "Emergency X service"],
    },
    "saas": {
        "sources": ["sales_calls", "demo_questions", "cancellation_feedback"],
        "example_queries": ["X integration with Y", "How to migrate from X to Y"],
    },
    "content": {
        "sources": ["comments", "dms", "audience_polls"],
        "example_queries": ["Behind the scenes X", "X tutorial for beginners"],
    },
    "consultant": {
        "sources": ["client_briefs", "proposals", "discovery_calls"],
        "example_queries": ["How to choose X consultant", "X pricing guide"],
    },
}


def get_insight_template(business_type: str) -> Dict[str, Any]:
    """Get customer insight collection template for business type."""
    btype = business_type.lower().replace(" ", "_")
    for key in INSIGHT_TEMPLATES:
        if btype in key or key in btype:
            return INSIGHT_TEMPLATES[key]
    return INSIGHT_TEMPLATES["content"]


# ─────────────────────────────────────────────────────────────────────────────
# MASTER RESEARCH ORCHESTRATOR
# ─────────────────────────────────────────────────────────────────────────────

def run_multi_platform_research(
    seed_keywords: List[str],
    business_type: str = "",
    business_context: str = "",
    platforms: List[str] = None,
) -> Dict[str, Any]:
    """
    Run research across all platforms for seed keywords.

    Args:
        seed_keywords: list of seed keywords to research
        business_type: type of business
        business_context: additional context for AI research
        platforms: which platforms to research (default: all)
    """
    if platforms is None:
        platforms = ["google", "youtube", "reddit", "ai"]

    results = {
        "google_suggestions": [],
        "youtube_topics": [],
        "reddit_topics": [],
        "ai_topics": [],
        "all_keywords": [],
        "keyword_count": 0,
        "platforms_searched": platforms,
    }

    all_keywords = set()

    for seed in seed_keywords[:10]:  # Limit seeds to prevent excessive API calls
        if "google" in platforms:
            suggestions = google_autocomplete(seed)
            results["google_suggestions"].extend(
                [{"keyword": s, "source": "google_autocomplete", "seed": seed} for s in suggestions]
            )
            all_keywords.update(suggestions)
            time.sleep(0.5)

        if "youtube" in platforms:
            yt = youtube_suggestions(seed)
            results["youtube_topics"].extend(yt)
            all_keywords.update(t["suggestion"] for t in yt)
            time.sleep(0.5)

        if "reddit" in platforms:
            rd = reddit_topics(seed)
            results["reddit_topics"].extend(rd)
            # Extract potential keywords from Reddit titles
            for post in rd:
                title_words = post["title"].lower()
                if len(title_words.split()) <= 8:
                    all_keywords.add(post["title"].lower().strip("?!."))
            time.sleep(0.5)

        if "ai" in platforms:
            ai = ai_topic_exploration(seed, business_context)
            results["ai_topics"].extend(ai)
            all_keywords.update(t.get("keyword", "") for t in ai if t.get("keyword"))

    results["all_keywords"] = sorted(list(all_keywords))
    results["keyword_count"] = len(all_keywords)

    log.info("[Research] Multi-platform research complete: %d total keywords from %d seeds",
             len(all_keywords), len(seed_keywords))
    return results
