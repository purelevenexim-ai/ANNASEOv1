import os, re, json, logging, hashlib
from collections import defaultdict
from typing import List, Dict, Optional
import requests
from engines.ruflo_strategy_dev_engine import AI
from engines.ruflo_20phase_engine import Cfg
from collections import OrderedDict
import os

log = logging.getLogger("seo.keyword.pipeline")

# Global LLM cache to avoid contaminate across seeds — bounded LRU
LLM_CACHE_MAX = int(os.getenv("LLM_CACHE_MAX", "1024"))
LLM_CACHE: "OrderedDict[str, dict]" = OrderedDict()


def _llm_cache_get(key: str):
    """Get from LRU cache, moving accessed key to end (most-recently-used)."""
    if key in LLM_CACHE:
        LLM_CACHE.move_to_end(key)
        return LLM_CACHE[key]
    return None


def _llm_cache_set(key: str, value):
    """Set in LRU cache, evicting oldest entry if at capacity."""
    LLM_CACHE[key] = value
    LLM_CACHE.move_to_end(key)
    while len(LLM_CACHE) > LLM_CACHE_MAX:
        LLM_CACHE.popitem(last=False)

# -----------------------------------------
# P4: Entity Cleaning & Normalization
# -----------------------------------------
JUNK_PATTERNS = [
    "emoji", "drawing", "meaning", "photos", "kids", "q", "live",
    "bogus", "random", "nonsense", "experiment", "diagram"
]

def is_valid_keyword(keyword: str) -> bool:
    kw = keyword.strip().lower()
    if not kw or len(kw.split()) < 2:
        return False
    if any(j in kw for j in JUNK_PATTERNS):
        return False
    if kw.startswith(("can ", "how do i ", "what does ", "is it ", "can i ")):
        return False
    if re.search(r"[^a-z0-9\s\-]", kw):
        return False
    return True


def reset_pipeline():
    """Reset non-persistent state to avoid cross-seed carry-over."""
    global LLM_CACHE
    LLM_CACHE = {}


def enforce_seed_on_keywords(keywords: List[str], seed: str) -> List[str]:
    if not seed:
        return keywords
    seed_normalized = seed.strip().lower()
    valid = [kw for kw in keywords if seed_normalized in kw.lower()]
    invalid = [kw for kw in keywords if seed_normalized not in kw.lower()]
    if invalid:
        log.warning(f"[SeedGuard] Removed {len(invalid)} cross-seed terms: {invalid[:5]}")
    return valid


def normalize_keyword_text(kw: str) -> Optional[str]:
    kw = kw.strip().lower()
    kw = re.sub(r"[^a-z0-9\s-]", "", kw)
    kw = re.sub(r"\s+", " ", kw).strip()
    if not kw or len(kw.split()) < 2:
        return None
    # simple keyword-orient normalization
    kw = re.sub(r"\b(the|a|an|of|in|for|and|or|to|is|are|was|were)\b", "", kw)
    kw = re.sub(r"\s+", " ", kw).strip()
    return kw if len(kw.split()) >= 2 else None


def canonicalize_keyword(kw: str) -> str:
    base = kw.strip().lower()
    modifiers = ["buy", "best", "cheap", "online", "india", "wholesale", "per", "price", "kg", "kilo", "meter"]
    for mod in modifiers:
        base = re.sub(rf"\b{re.escape(mod)}\b", "", base)
    base = re.sub(r"\s+", " ", base).strip()
    return base or kw


def normalize_keywords(raw_keywords: List[str], seed: str) -> Dict[str, List[dict]]:
    # P3: group variants while preserving full list (no removal due to grouping)
    base_list = []
    groups = defaultdict(lambda: {"canonical": "", "variants": []})

    for kw in raw_keywords:
        normalized = normalize_keyword_text(kw)
        if not normalized:
            continue
        if seed and seed.lower() not in normalized:
            continue

        base_list.append(normalized)
        canonical = canonicalize_keyword(normalized)
        if not groups[canonical]["canonical"]:
            groups[canonical]["canonical"] = canonical

        if normalized not in groups[canonical]["variants"]:
            groups[canonical]["variants"].append(normalized)

    normalized_groups = []
    for canon, bucket in groups.items():
        variants = bucket["variants"]
        if not variants:
            continue
        primary = sorted(variants, key=lambda x: (-len(x), x))[0]
        normalized_groups.append({
            "canonical": primary,
            "variants": variants
        })

    log.info(f"[P3] normalized {len(raw_keywords)} → {len(base_list)} keywords, {len(normalized_groups)} groups")
    return {
        "keywords": base_list,
        "groups": normalized_groups,
        # backward compatibility: some callers expect 'normalization' key
        "normalization": normalized_groups
    }


def validate_keywords_by_seed(keywords: List[str], seed: str) -> List[str]:
    return enforce_seed_on_keywords(keywords, seed)

# -----------------------------------------
# LLM adapter
# -----------------------------------------
def llm_call(prompt: str, data: dict, seed: str = "") -> dict:
    """Try Groq first, then DeepSeek fallback (seed-aware cache)."""
    cache_key = f"{seed.lower()}#{hashlib.md5((prompt + json.dumps(data, sort_keys=True)).encode()).hexdigest()}"
    cached = _llm_cache_get(cache_key)
    if cached is not None:
        log.debug(f"[LLMCache] hit for seed={seed}")
        return cached

    payload_text = prompt + "\n\nINPUT:\n" + json.dumps(data, sort_keys=True)
    groq_key = os.getenv("GROQ_API_KEY") or getattr(Cfg, "GROQ_KEY", "")
    rsp: dict = {}

    if groq_key:
        try:
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                json={
                    "model": os.getenv("GROQ_MODEL", "llama-3.3-70b-instruct"),
                    "messages": [
                        {"role": "system", "content": f"You are an authoritative SEO keyword assistant focused on '{seed}'."},
                        {"role": "user", "content": payload_text}
                    ],
                    "temperature": 0.2,
                    "max_tokens": 1200
                },
                timeout=30
            )
            r.raise_for_status()
            rsp = r.json()
        except Exception as e:
            log.warning(f"Groq call failed: {e}")

    if not rsp:
        try:
            d = AI.deepseek(payload_text, system=f"You are an SEO strategist constrained to '{seed}'.")
            rsp = {"content": d}
        except Exception as e:
            log.error(f"DeepSeek fallback failed: {e}")
            rsp = {"error": str(e)}

    _llm_cache_set(cache_key, rsp)
    return rsp

# -----------------------------------------
# P5: Intent + business intent
# -----------------------------------------
def classify_intent_llm(keywords: List[str], business_type: str, industry: str, seed: str) -> List[dict]:
    prompt = (
        "You are a revenue-focused SEO intent classifier."
        "\nContext: business_type={business_type}, industry={industry}, seed={seed}."
        "\nSTRICT RULE: only classify keywords clearly related to seed '{seed}'; if not, return intent='junk'."
        "\nFor each keyword, decide: intent (transactional/commercial/informational/navigational)," 
        " sub_intent (problem_solving/comparison/buying/local/educational)," 
        " business_score(0-10), conversion_score(0-10)." 
        "\nOutput JSON array."
    ).format(business_type=business_type, industry=industry, seed=seed)

    payload = {"keywords": keywords, "seed": seed}
    rsp = llm_call(prompt, payload, seed=seed)

    # parse from LLM text if possible
    if "choices" in rsp and rsp["choices"]:
        txt = rsp["choices"][0].get("message", {}).get("content", "")
    else:
        txt = rsp.get("content", "")

    try:
        parsed = json.loads(re.search(r"(\[.*\])", txt, re.DOTALL).group(1))
        return parsed
    except Exception:
        # fallback simple rules
        out = []
        for kw in keywords:
            intent = "informational"
            if any(x in kw for x in ["buy", "price", "wholesale", "supplier", "order"]):
                intent = "transactional"
            elif any(x in kw for x in ["best", "compare", "vs", "review"]):
                intent = "commercial"
            sub_intent = "buying" if intent == "transactional" else "educational"
            out.append({
                "keyword": kw,
                "intent": intent,
                "sub_intent": sub_intent,
                "business_score": 7,
                "conversion_score": 7
            })
        return out

# -----------------------------------------
# P6: SERP intelligence
# -----------------------------------------
def serp_analysis(keywords: List[str]) -> Dict[str, dict]:
    results = {}
    for kw in keywords:
        serp = serp_crawl_connector(kw)
        results[kw] = {
            "competition_score": serp.get("competition", 50),
            "content_gap": serp.get("content_gap", False),
            "weak_domains": serp.get("weak_domains", False),
            "ugc_presence": serp.get("ugc_presence", False),
            "video_presence": serp.get("video_presence", False),
            "domain_authority": serp.get("domain_authority", 50),
            "serp_source": serp.get("source", "unknown")
        }
    return results


def serp_crawl_connector(keyword: str, location: str = "india") -> dict:
    """Sample external strategy to fetch SERP data from a provider (Ahrefs-style)."""
    api_key = os.getenv("SERP_API_KEY", "")
    if not api_key:
        return {
            "source": "local_stub",
            "domain_authority": 50,
            "competition": 50,
            "unordered_results": 0,
            "notes": "No API key configured."
        }

    try:
        r = requests.get(
            "https://api.ahrefs.com/v3/serp",
            params={
                "token": api_key,
                "target": keyword,
                "country": location,
                "depth": 10
            },
            timeout=30
        )
        r.raise_for_status()
        data = r.json()
        # parse provider-specific fields as standard
        return {
            "source": "ahrefs",
            "domain_authority": data.get("domain_rating", 50),
            "competition": data.get("competition", 50),
            "content_gap": data.get("content_gap", False),
            "weak_domains": data.get("weak_domains", False),
            "ugc_presence": data.get("ugc", False),
            "video_presence": data.get("video", False),
        }
    except Exception as e:
        log.warning(f"SERP crawl connector failed for {keyword}: {e}")
        return {
            "source": "local_fallback",
            "domain_authority": 50,
            "competition": 50,
            "content_gap": False,
            "weak_domains": False,
            "ugc_presence": False,
            "video_presence": False
        }

# -----------------------------------------
# P7: Opportunity scoring
# -----------------------------------------
INTENT_WEIGHT = {"transactional": 1.0, "commercial": 0.8, "informational": 0.6, "navigational": 0.3}

def score_keyword(item: Dict, entity: str) -> float:
    intent_score = item.get("business_score", 5) * 10
    conversion_score = item.get("conversion_score", 5) * 10
    serp = item.get("serp", {})
    competition_score = serp.get("competition_score", 50)
    content_gap = 1 if serp.get("content_gap") else 0
    weak_domains = 1 if serp.get("weak_domains") else 0
    intent = item.get("intent", "informational")

    score = (
        intent_score * 0.25 +
        conversion_score * 0.20 +
        (100 - competition_score) * 0.20 +
        content_gap * 15 +
        weak_domains * 10 +
        INTENT_WEIGHT.get(intent, 0.5) * 10
    )

    # relevance to entity
    if entity and entity.lower() in item.get("keyword", "").lower():
        score += 10
    return min(100.0, max(0.0, round(score, 2)))


def _select_top100_for_pillar(enriched_keywords: List[Dict]) -> List[Dict]:
    if not enriched_keywords:
        return []

    intent_buckets = defaultdict(list)
    for kw in enriched_keywords:
        intent = kw.get("intent", "informational")
        intent_buckets[intent].append(kw)

    for intent in intent_buckets:
        intent_buckets[intent] = sorted(intent_buckets[intent], key=lambda x: x.get("score", 0), reverse=True)

    quotas = {
        "transactional": 25,
        "commercial": 30,
        "informational": 40,
        "comparison": 3,
        "navigational": 2
    }

    selected, used = [], set()
    for intent, quota in quotas.items():
        for kw in intent_buckets.get(intent, [])[:quota]:
            if kw["keyword"] not in used:
                selected.append(kw)
                used.add(kw["keyword"])

    remainder = [kw for kw in sorted(enriched_keywords, key=lambda x: x.get("score", 0), reverse=True)
                 if kw["keyword"] not in used]
    for kw in remainder:
        if len(selected) >= 100:
            break
        selected.append(kw)
        used.add(kw["keyword"])

    return selected[:100]


def _token_signature(keyword: str) -> str:
    t = keyword.lower()
    t = re.sub(r"[^a-z0-9\s]", "", t)
    t = re.sub(r"\b(buy|best|cheap|online|india|wholesale|price|per|kg|kilo|order)\b", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t or keyword.lower()


# -----------------------------------------
# P8: Topic detection (pillars)
# -----------------------------------------

def detect_topics_llm(keywords: List[str], seed: str) -> Dict[str, List[str]]:
    prompt = (
        "Group these keywords into 6-8 strong SEO pillars (topic names)."
        "\nFocus strictly on seed: {seed}. Reject keywords unrelated to {seed}."
        "\nEach pillar: high business impact, clusterable, not overlapping."
        "\nReturn JSON object map: {{\"pillar\": [keywords]}}."
    ).format(seed=seed)
    rsp = llm_call(prompt, {"keywords": keywords, "seed": seed}, seed=seed)
    try:
        txt = rsp.get("choices", [{}])[0].get("message", {}).get("content", "") if "choices" in rsp else rsp.get("content", "")
        parsed = json.loads(re.search(r"(\{.*\})", txt, re.DOTALL).group(1))
        return parsed
    except Exception:
        # fallback simple keyword bucket by major tokens
        topics = {"turmeric benefits": [], "turmeric uses": [], "turmeric products": []}
        for kw in keywords:
            k = kw.lower()
            if "benefit" in k or "health" in k:
                topics["turmeric benefits"].append(kw)
            elif "drink" in k or "water" in k or "milk" in k:
                topics["turmeric uses"].append(kw)
            else:
                topics["turmeric products"].append(kw)
        return topics

# -----------------------------------------
# P9: Clustering
# -----------------------------------------

def create_clusters(topic_keywords: List[str], keyword_intents: Optional[Dict[str,str]] = None) -> List[Dict]:
    clusters = []
    if not topic_keywords:
        return clusters

    keyword_intents = keyword_intents or {}
    intent_buckets = defaultdict(list)

    for kw in topic_keywords:
        raw_intent = keyword_intents.get(kw, "informational")
        if isinstance(raw_intent, dict):
            intent = raw_intent.get("intent", "informational")
        else:
            intent = raw_intent
        intent_buckets[intent].append(kw)

    for intent, kws in intent_buckets.items():
        semantic_groups = defaultdict(list)
        for kw in kws:
            sig = _token_signature(kw)
            semantic_groups[sig].append(kw)

        for sig, kw_list in semantic_groups.items():
            kw_list = sorted(set(kw_list), key=lambda x: (len(x), x))
            primary = kw_list[0]
            supporting = [k for k in kw_list if k != primary]
            clusters.append({
                "cluster_name": sig.title(),
                "primary_keyword": primary,
                "intent": intent,
                "keywords": supporting
            })

    # Optional LLM refinement for cluster summary (no intent mixing, minimal risk)
    try:
        prompt = (
            "You are an SEO cluster engine. Group these keywords into clusters without mixing intent." 
            "Return JSON array with cluster_name, primary_keyword, intent, keywords."
            "\nKeywords: " + json.dumps(topic_keywords)
        )
        rsp = llm_call(prompt, {"keywords": topic_keywords}, seed="")
        if rsp and "choices" in rsp and rsp["choices"]:
            txt = rsp["choices"][0].get("message", {}).get("content", "")
            parsed = json.loads(re.search(r"(\[.*\])", txt, re.DOTALL).group(1))
            if isinstance(parsed, list) and parsed:
                return parsed
    except Exception:
        pass

    weak_warnings = validate_clusters(clusters)
    if weak_warnings:
        for w in weak_warnings:
            log.warning(f"[P6] {w}")

    return clusters


def validate_clusters(clusters: List[Dict]) -> List[str]:
    warnings = []
    for c in clusters:
        kw_count = len(c.get("keywords", [])) + (1 if c.get("primary_keyword") else 0)
        if kw_count < 3:
            warnings.append(f"Cluster '{c.get('cluster_name', 'unknown')}' has only {kw_count} keywords")
        if c.get("intent") not in {"transactional", "commercial", "informational", "comparison", "navigational"}:
            warnings.append(f"Cluster '{c.get('cluster_name', 'unknown')}' has unusual intent '{c.get('intent')}'")
    return warnings


# -----------------------------------------
# P10: Pillar build
# -----------------------------------------

def build_pillar(topic: str, keywords: List[str], enriched_keywords: List[Dict], intent_map: Dict[str,str]) -> Dict:
    sub_enriched = [item for item in enriched_keywords if item["keyword"] in set(keywords)]
    top100_entities = _select_top100_for_pillar(sub_enriched)
    top100_keywords = [item["keyword"] for item in top100_entities]

    clusters = create_clusters(top100_keywords, keyword_intents=intent_map)

    covered = set()
    for c in clusters:
        covered.update(c.get("keywords", []))
        covered.add(c.get("primary_keyword"))

    missing = [kw for kw in top100_keywords if kw not in covered]
    for m in missing:
        intent = intent_map.get(m, "informational")
        assigned = False
        for c in clusters:
            if c.get("intent") == intent:
                c.setdefault("keywords", []).append(m)
                assigned = True
                break
        if not assigned:
            clusters.append({
                "cluster_name": _token_signature(m).title(),
                "primary_keyword": m,
                "intent": intent,
                "keywords": []
            })

    return {
        "pillar_title": topic.title(),
        "primary_keyword": topic,
        "top_keywords": top100_keywords,
        "clusters": clusters,
        "normalized_groups": []
    }


# -----------------------------------------
# API assembly
# -----------------------------------------

def run_full_pipeline(input_data: Dict) -> Dict:
    project_id = input_data.get("project_id")
    session_id = input_data.get("session_id")
    pillar = input_data.get("pillar", "turmeric")
    seed = input_data.get("seed", pillar)
    usp = input_data.get("usp", "premium turmeric exporter")
    raw_keywords = input_data.get("keywords", [])

    cleaned = [kw for kw in raw_keywords if is_valid_keyword(kw)]
    if seed:
        cleaned = [kw for kw in cleaned if seed.lower() in kw.lower()]

    normalized_data = normalize_keywords(cleaned, seed)
    normalized_list = normalized_data.get("keywords", [])
    normalized_groups = normalized_data.get("groups", [])

    # Intent + business intent
    intent_data = classify_intent_llm(normalized_list, input_data.get("business_type", "ecommerce"), input_data.get("industry", "food_spices"), seed)
    intent_map = {x["keyword"]: x for x in intent_data}

    # SERP signals
    serp_map = serp_analysis(normalized_list)

    enriched = []
    for kw in normalized_list:
        if seed and seed.lower() not in kw.lower():
            log.warning(f"Seed contamination filtered out: {kw}")
            continue

        itm = {
            "keyword": kw,
            "intent": intent_map.get(kw, {}).get("intent", "informational"),
            "sub_intent": intent_map.get(kw, {}).get("sub_intent", "educational"),
            "business_score": intent_map.get(kw, {}).get("business_score", 5),
            "conversion_score": intent_map.get(kw, {}).get("conversion_score", 5),
            "serp": serp_map.get(kw, {}),
            "score": 0,
        }
        itm["score"] = score_keyword(itm, pillar)
        enriched.append(itm)

    enriched = sorted(enriched, key=lambda x: x["score"], reverse=True)
    keyword_sorted = [k["keyword"] for k in enriched]

    topics = detect_topics_llm(keyword_sorted, seed)

    pillars = {}
    for topic, kws in topics.items():
        if not kws:
            continue
        pillars[topic] = build_pillar(topic, kws, enriched, intent_map)

    # Compute distribution by competition
    bucketed = {"low": 0, "medium": 0, "high": 0}
    for kw in enriched:
        comp = kw.get("serp", {}).get("competition_score", 50)
        if comp <= 40:
            bucketed["low"] += 1
        elif comp <= 70:
            bucketed["medium"] += 1
        else:
            bucketed["high"] += 1

    return {
        "seed": seed,
        "total_keywords": len(cleaned),
        "normalized_keywords": normalized_list,
        "normalization": normalized_groups,
        "pillars": pillars,
        "enriched": enriched[:500],
        "raw": raw_keywords,
        "competition_distribution": bucketed,
    }
