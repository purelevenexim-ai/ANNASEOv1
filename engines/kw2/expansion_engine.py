"""
kw2 Expansion Engine — Phase 4.

Takes seed questions from kw2_intelligence_questions and expands them
recursively across discovered dimensions (geo, audience, use-case, etc.)

Strategy:
1. Discover dimensions from business context via AI (no hardcoding)
2. For each seed question × each dimension value → generate N variations
3. Save expanded questions at expansion_depth+1
4. (Optional) recurse up to max_depth
"""
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

from engines.kw2.ai_caller import kw2_ai_call, kw2_extract_json
from engines.kw2 import db
from engines.kw2.prompts import (
    MULTI_DIM_EXPAND_SYSTEM, MULTI_DIM_EXPAND_USER,
    VALIDATE_QUESTIONS_SYSTEM, VALIDATE_QUESTIONS_USER,
)

log = logging.getLogger("kw2.expansion_engine")

EXPANSION_SYSTEM = (
    "You are a content strategy specialist. "
    "Output ONLY valid JSON with no markdown fences."
)

DISCOVER_DIMENSIONS_PROMPT = """BUSINESS: {universe} | TYPE: {btype}
BRAND: {brand_name}
PILLARS: {pillars}
TARGET LOCATIONS: {target_locations}
LANGUAGES: {languages}
CULTURAL CONTEXT: {cultural_context}
PRODUCTS: {products}

Discover the expansion dimensions relevant to this specific business.

Return the dimensions that create meaningful question variations:
{{
  "dimensions": [
    {{
      "name": "geo",
      "values": ["Kerala", "Mumbai", "Delhi", "Export markets"]
    }},
    {{
      "name": "audience",
      "values": ["home cooks", "restaurants", "spice traders"]
    }},
    {{
      "name": "use_case",
      "values": ["cooking", "gifting", "medicinal use"]
        }},
        {{
            "name": "brand_name",
            "values": ["{brand_name_example}"]
    }}
  ]
}}

Include only dimensions that genuinely create different content opportunities.
If the business has a real store or product brand, include a brand_name dimension.
Use the target locations to create a comprehensive geo dimension.
Use the cultural context to create a cultural/seasonal dimension if relevant.
Use the products list to create product-variant dimensions if they have distinct attributes.
Maximum 7 dimensions. Each dimension should have 3-8 specific values."""

EXPAND_QUESTION_PROMPT = """BUSINESS: {business_context}

BASE QUESTION:
{base_question}

EXPANSION DIMENSION: {dimension_name}
VALUES TO EXPAND ACROSS: {dimension_values}

Generate {target_count} UNIQUE question variations inspired by the dimension values.

CRITICAL RULES:
- Each question must sound like something a REAL person would type into Google
- DO NOT just append a city/value to the base question (e.g. "X in Mumbai" is BAD)
- Each variation must have a DIFFERENT intent, angle, or topic focus
- Think: what would someone in that geo/audience/context ACTUALLY search for?
- Vary sentence structure — mix "how to", "best", "why", "where", comparisons, lists
- Questions must be self-contained (readable without the base question)
- Skip a dimension value if it doesn't produce a meaningfully different question

BAD examples (template substitutions — NEVER do this):
- "Kerala spices for cooking in Mumbai" (just appended city)
- "Benefits of spices for home cooks" / "Benefits of spices for restaurants" (same template)
- "How to store spices in 100gm" / "How to store spices in 200gm" (trivial swap)

GOOD examples (genuinely different questions):
- "Which Kerala spices are used in traditional Ayurvedic remedies?"
- "Bulk spice suppliers in Mumbai with direct Kerala sourcing"
- "Restaurant-grade whole spices vs pre-ground: flavor comparison"

Return ONLY this JSON:
{{
  "expanded_questions": [
    {{
      "question": "",
      "dimension_applied": "{dimension_name}",
      "dimension_value": ""
    }}
  ]
}}"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uid(prefix: str = "") -> str:
    short = uuid.uuid4().hex[:12]
    return f"{prefix}{short}" if prefix else short


def _safe_json(obj) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return "{}"


def _unique_strings(values, limit: int = 8) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        text = " ".join(str(value or "").split()).strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def _normalize_dimensions(raw) -> dict[str, list[str]]:
    dims: dict[str, list[str]] = {}
    if isinstance(raw, list):
        for dim in raw:
            if not isinstance(dim, dict) or not dim.get("name"):
                continue
            name = str(dim.get("name", "")).strip()
            values = _unique_strings(dim.get("values", []))
            if name and values:
                dims[name] = values
        return dims

    if not isinstance(raw, dict):
        return dims

    for name, values in raw.items():
        flat_values: list[str] = []
        if isinstance(values, list):
            flat_values = values
        elif isinstance(values, dict):
            nested = values.get("values")
            if isinstance(nested, dict):
                for sub_values in nested.values():
                    if isinstance(sub_values, list):
                        flat_values.extend(sub_values)
            elif isinstance(nested, list):
                flat_values.extend(nested)
            for sub_values in values.values():
                if isinstance(sub_values, list):
                    flat_values.extend(sub_values)
        elif values:
            flat_values = [values]

        cleaned = _unique_strings(flat_values)
        if cleaned:
            dims[str(name).strip()] = cleaned
    return dims


def _clean_brand_candidate(value: str | None) -> str:
    text = " ".join(str(value or "").split()).strip(" -_|:/")
    if not text:
        return ""
    if len(text) > 60:
        text = text[:60].strip()
    lowered = text.casefold()
    if lowered in {"brand", "business", "store", "shop"}:
        return ""
    return text


def _brand_from_domain(domain: str | None) -> str:
    raw = str(domain or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    host = (parsed.netloc or parsed.path or "").strip().lower()
    if not host:
        return ""
    host = host.split("@")[-1].split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    label = host.split(".")[0]
    label = re.sub(r"[^a-z0-9]+", " ", label).strip()
    if not label or label in {"shop", "store", "site", "app"}:
        return ""
    return " ".join(part.capitalize() for part in label.split())


def _extract_brand_name(profile: dict) -> str:
    manual = profile.get("manual_input") if isinstance(profile.get("manual_input"), dict) else {}
    raw_ai = profile.get("raw_ai_json") if isinstance(profile.get("raw_ai_json"), dict) else {}
    biz_identity = raw_ai.get("business_identity") if isinstance(raw_ai.get("business_identity"), dict) else {}

    candidates = [
        manual.get("brand_name"),
        manual.get("business_name"),
        manual.get("name"),
        profile.get("brand_name"),
        profile.get("name"),
        raw_ai.get("brand_name"),
        raw_ai.get("name"),
        biz_identity.get("name"),
    ]
    for candidate in candidates:
        brand = _clean_brand_candidate(candidate)
        if brand:
            return brand

    return _brand_from_domain(manual.get("domain") or profile.get("domain"))


def _fallback_dimensions(profile: dict) -> dict[str, list[str]]:
    dimensions: dict[str, list[str]] = {}

    brand_name = _extract_brand_name(profile)
    if brand_name:
        dimensions["brand_name"] = [brand_name]

    # Geo: combine geo_scope + target_locations + business_locations
    geo_values = []
    geo_scope = str(profile.get("geo_scope", "") or "")
    if geo_scope:
        geo_values.extend(re.split(r"[|,/]+", geo_scope))
    mi = profile.get("manual_input") if isinstance(profile.get("manual_input"), dict) else {}
    for loc in (profile.get("target_locations") or mi.get("target_locations", [])):
        t = str(loc).strip()
        if t and t.lower() not in {v.strip().lower() for v in geo_values}:
            geo_values.append(t)
    for loc in (profile.get("business_locations") or mi.get("business_locations", [])):
        t = str(loc).strip()
        if t and t.lower() not in {v.strip().lower() for v in geo_values}:
            geo_values.append(t)
    geo_values = _unique_strings(geo_values, limit=8)
    if geo_values:
        dimensions["geo"] = geo_values

    audience_values = _unique_strings(profile.get("audience", []), limit=6)
    if audience_values:
        dimensions["audience"] = audience_values

    product_values = _unique_strings(profile.get("pillars", []), limit=6)
    # Supplement with product_catalog items (specific products as extra dimension values)
    catalog = profile.get("product_catalog", [])
    if catalog:
        catalog_values = _unique_strings(catalog, limit=6)
        if catalog_values:
            dimensions["product_variant"] = catalog_values
    if product_values:
        dimensions["product"] = product_values

    # Cultural context → new dimension for cultural/seasonal expansion
    cultural = profile.get("cultural_context") or mi.get("cultural_context", [])
    cultural_values = _unique_strings(cultural, limit=6)
    if cultural_values:
        dimensions["cultural"] = cultural_values

    # Languages → new dimension for multilingual expansion
    languages = profile.get("languages") or mi.get("languages", [])
    lang_values = _unique_strings(languages, limit=5)
    if lang_values:
        dimensions["language"] = lang_values

    return dimensions


def _merge_dimensions(primary: dict[str, list[str]], fallback: dict[str, list[str]]) -> dict[str, list[str]]:
    merged = {name: _unique_strings(values) for name, values in (primary or {}).items() if values}
    for name, values in (fallback or {}).items():
        merged[name] = _unique_strings((merged.get(name) or []) + list(values), limit=8)
    return {name: values for name, values in merged.items() if values}


class ExpansionEngine:
    """Phase 4: Expand seed questions across discovered dimensions."""

    def discover_dimensions(
        self, project_id: str, session_id: str, ai_provider: str = "auto",
    ) -> dict:
        """
        Ask AI to discover which dimensions are relevant for this business.
        Saves config to kw2_expansion_config.
        """
        profile = db.load_business_profile(project_id)
        if not profile:
            raise ValueError("No business profile.")

        brand_name = _extract_brand_name(profile)
        pillars = ", ".join(str(p) for p in profile.get("pillars", []))
        mi = profile.get("manual_input") if isinstance(profile.get("manual_input"), dict) else {}
        target_locs = profile.get("target_locations") or mi.get("target_locations", [])
        languages = profile.get("languages") or mi.get("languages", [])
        cultural = profile.get("cultural_context") or mi.get("cultural_context", [])
        products = profile.get("product_catalog", [])
        prompt = DISCOVER_DIMENSIONS_PROMPT.format(
            universe=profile.get("universe", "Business"),
            btype=profile.get("business_type", "unknown"),
            pillars=pillars,
            brand_name=brand_name or "(not available)",
            brand_name_example=brand_name or "Example Brand",
            target_locations=", ".join(str(l) for l in target_locs[:8]) or "(not specified)",
            languages=", ".join(str(l) for l in languages[:5]) or "(not specified)",
            cultural_context=", ".join(str(c) for c in cultural[:5]) or "(not specified)",
            products=", ".join(str(p) for p in products[:10]) or "(not specified)",
        )
        resp = kw2_ai_call(
            prompt, EXPANSION_SYSTEM, provider=ai_provider, temperature=0.4,
            session_id=session_id, project_id=project_id,
            task="expansion_discover",
        )
        result = kw2_extract_json(resp)
        ai_dimensions = {}
        if isinstance(result, dict):
            ai_dimensions = _normalize_dimensions(result.get("dimensions", {}))

        fallback_dimensions = _fallback_dimensions(profile)
        dimensions = _merge_dimensions(ai_dimensions, fallback_dimensions)
        if fallback_dimensions.get("brand_name"):
            dimensions["brand_name"] = fallback_dimensions["brand_name"]
        else:
            dimensions.pop("brand_name", None)
        if not dimensions:
            raise ValueError("No expansion dimensions available for this business.")

        # Save to config table
        self._save_config(session_id, dimensions)
        log.info("[ExpansionEngine] Discovered %d dimensions (brand=%s)", len(dimensions), brand_name or "none")
        return {"dimensions": dimensions, "brand_name": brand_name}

    def run(
        self,
        project_id: str,
        session_id: str,
        ai_provider: str = "auto",
        max_depth: int = 2,
        max_per_node: int = 5,
        max_total: int = 5000,
    ) -> dict:
        """
        Recursively expand questions using stored dimensions.
        Depth 0 = original Q1-Q7 seeds.
        Depth 1 = expansions of seeds.
        Depth 2 = expansions of depth-1 (optional, controlled by max_depth).
        """
        profile = db.load_business_profile(project_id)
        business_context = (profile.get("universe", "") if profile else "") or "Business"
        brand_name = _extract_brand_name(profile or {})
        if brand_name:
            business_context = f"{business_context} | Brand: {brand_name}"
        # Add business type and key context for richer expansion prompts
        if profile:
            btype = profile.get("business_type", "")
            if btype:
                business_context = f"{business_context} | Type: {btype}"
            mi = profile.get("manual_input") if isinstance(profile.get("manual_input"), dict) else {}
            usp = profile.get("usp") or mi.get("usp", "")
            if usp:
                business_context = f"{business_context} | USP: {usp[:100]}"

        config = self._load_config(session_id)
        dimensions = config.get("discovered_dimensions", {})
        if isinstance(dimensions, str):
            try:
                dimensions = json.loads(dimensions)
            except Exception:
                dimensions = {}

        if not dimensions:
            discovered = self.discover_dimensions(project_id, session_id, ai_provider)
            dimensions = discovered.get("dimensions", {})
        if not dimensions:
            raise ValueError("No dimensions discovered yet. Run discover-dimensions first.")

        log.info("[ExpansionEngine] Running recursive expansion to depth=%d, max=%d", max_depth, max_total)

        total_created = 0
        seeds_per_depth: dict[int, int] = {}
        dim_items = list(dimensions.items())

        # Recursive loop: expand depth 0, then 1, then up to max_depth-1
        for current_depth in range(max_depth):
            if total_created >= max_total:
                break

            seeds = self._load_seeds_at_depth(session_id, current_depth)
            if not seeds:
                log.info("[ExpansionEngine] No seeds at depth=%d, stopping", current_depth)
                break

            seeds_per_depth[current_depth] = len(seeds)
            log.info("[ExpansionEngine] Depth %d: %d seeds × %d dimensions",
                     current_depth, len(seeds), len(dim_items))

            for seed in seeds:
                if total_created >= max_total:
                    break
                for dim_name, dim_values in dim_items:
                    if total_created >= max_total or not dim_values:
                        break
                    count = self._expand_question(
                        seed, dim_name, dim_values, business_context,
                        max_per_node, ai_provider, session_id, project_id,
                    )
                    total_created += count

        return {
            "seeds_per_depth": seeds_per_depth,
            "questions_created": total_created,
            "max_depth_reached": max(seeds_per_depth.keys(), default=0),
        }

    def get_config(self, session_id: str) -> dict:
        """Get expansion config for a session."""
        return self._load_config(session_id)

    def update_config(self, session_id: str, **kwargs) -> bool:
        """Update expansion config fields."""
        conn = db.get_conn()
        try:
            existing = conn.execute(
                "SELECT id FROM kw2_expansion_config WHERE session_id=?",
                (session_id,),
            ).fetchone()
            if not existing:
                return False
            allowed = {"max_depth", "max_per_node", "dedup_threshold", "max_total",
                       "expand_audience", "expand_use_cases"}
            for key, val in kwargs.items():
                if key in allowed:
                    conn.execute(
                        f"UPDATE kw2_expansion_config SET {key}=? WHERE session_id=?",
                        (val, session_id),
                    )
            conn.commit()
            return True
        finally:
            conn.close()

    def _expand_question(
        self, seed: dict, dim_name: str, dim_values: list,
        business_context: str, max_per_node: int,
        provider: str, session_id: str, project_id: str,
    ) -> int:
        target = min(max_per_node * len(dim_values), max_per_node * 5)
        prompt = EXPAND_QUESTION_PROMPT.format(
            business_context=(business_context or "")[:600],
            base_question=seed.get("question", ""),
            dimension_name=dim_name,
            dimension_values=", ".join(str(v) for v in dim_values[:8]),
            target_count=target,
        )
        resp = kw2_ai_call(
            prompt, EXPANSION_SYSTEM, provider=provider, temperature=0.3,
            session_id=session_id, project_id=project_id,
            task="expansion_expand",
        )
        result = kw2_extract_json(resp)
        if not isinstance(result, dict):
            return 0

        expanded = result.get("expanded_questions", [])
        if not isinstance(expanded, list):
            return 0

        to_insert = []
        now = _now()
        parent_id = seed.get("id", "")
        module_code = seed.get("module_code", "EXP")
        depth = (seed.get("expansion_depth") or 0) + 1

        for item in expanded:
            if not isinstance(item, dict) or not item.get("question"):
                continue
            dimension_name = str(item.get("dimension_applied", dim_name))[:100]
            dimension_value = str(item.get("dimension_value", ""))[:160]
            to_insert.append((
                _uid("qi_"),
                session_id,
                project_id,
                module_code,
                str(item.get("question", ""))[:2000],
                dimension_name,
                depth,
                parent_id,
                "pending",
                dimension_name,
                dimension_value,
                "ai_expansion",
                now,
            ))

        if not to_insert:
            return 0

        conn = db.get_conn()
        try:
            conn.executemany(
                """INSERT INTO kw2_intelligence_questions
                   (id, session_id, project_id, module_code, question,
                    content_type, expansion_depth, parent_question_id,
                    status, expansion_dimension_name, expansion_dimension_value,
                    data_source, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                to_insert,
            )
            conn.commit()
        finally:
            conn.close()
        return len(to_insert)

    def _load_seeds_at_depth(self, session_id: str, depth: int) -> list[dict]:
        """Load questions at a specific expansion depth for recursive expansion."""
        conn = db.get_conn()
        try:
            rows = conn.execute(
                """SELECT id, question, module_code, expansion_depth
                   FROM kw2_intelligence_questions
                   WHERE session_id=? AND expansion_depth=?
                   AND is_duplicate=0
                   ORDER BY business_relevance DESC, final_score DESC""",
                (session_id, depth),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def all_seeds_for_expansion(self, session_id: str) -> list[dict]:
        """Return all depth-0 seed questions (for frontend-driven per-seed expansion)."""
        seeds = self._load_seeds_at_depth(session_id, 0)
        return [{"id": s["id"], "question": s["question"]} for s in seeds]

    def expand_seed(
        self,
        session_id: str,
        project_id: str,
        seed_id: str,
        ai_provider: str = "auto",
        max_per_node: int = 3,
        max_total_remaining: int = 99999,
    ) -> dict:
        """Expand a single seed question across ALL discovered dimensions in ONE AI call.

        Previously called _expand_question() once per dimension (6 calls per seed).
        Now combines all dimensions into a single prompt — 6× faster per seed.

        Returns {questions_created, seed_id}.
        """
        profile = db.load_business_profile(project_id)
        business_context = (profile.get("universe", "") if profile else "") or "Business"
        brand_name = _extract_brand_name(profile or {})
        if brand_name:
            business_context = f"{business_context} | Brand: {brand_name}"

        config = self._load_config(session_id)
        dimensions = config.get("discovered_dimensions", {})
        if isinstance(dimensions, str):
            try:
                dimensions = json.loads(dimensions)
            except Exception:
                dimensions = {}

        if not dimensions:
            return {"questions_created": 0, "seed_id": seed_id, "error": "No dimensions discovered"}

        conn = db.get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM kw2_intelligence_questions WHERE id=? AND session_id=?",
                (seed_id, session_id),
            ).fetchone()
        finally:
            conn.close()

        if not row:
            return {"questions_created": 0, "seed_id": seed_id, "error": "Seed not found"}

        seed = dict(row)

        # Build the dimensions block for the unified prompt
        dim_lines = []
        for dim_name, dim_values in dimensions.items():
            if not dim_values:
                continue
            vals = ", ".join(str(v) for v in dim_values[:8])
            dim_lines.append(f"- {dim_name}: {vals}")
        if not dim_lines:
            return {"questions_created": 0, "seed_id": seed_id}

        dimensions_block = "\n".join(dim_lines)

        prompt = MULTI_DIM_EXPAND_USER.format(
            business_context=(business_context or "")[:600],
            base_question=seed.get("question", ""),
            dimensions_block=dimensions_block,
            per_dim=max_per_node,
        )
        resp = kw2_ai_call(
            prompt, MULTI_DIM_EXPAND_SYSTEM, provider=ai_provider, temperature=0.3,
            session_id=session_id, project_id=project_id,
            task="expansion_expand",
        )
        result = kw2_extract_json(resp)
        if not isinstance(result, dict):
            return {"questions_created": 0, "seed_id": seed_id}

        expanded = result.get("expanded_questions", [])
        if not isinstance(expanded, list):
            return {"questions_created": 0, "seed_id": seed_id}

        to_insert = []
        now = _now()
        parent_id = seed.get("id", "")
        module_code = seed.get("module_code", "EXP")
        depth = (seed.get("expansion_depth") or 0) + 1
        total_allowed = min(len(expanded), max_total_remaining)

        for item in expanded[:total_allowed]:
            if not isinstance(item, dict) or not item.get("question"):
                continue
            dimension_name = str(item.get("dimension_applied", ""))[:100]
            dimension_value = str(item.get("dimension_value", ""))[:160]
            to_insert.append((
                _uid("qi_"),
                session_id,
                project_id,
                module_code,
                str(item.get("question", ""))[:2000],
                dimension_name,
                depth,
                parent_id,
                "pending",
                dimension_name,
                dimension_value,
                "ai_expansion",
                now,
            ))

        if not to_insert:
            return {"questions_created": 0, "seed_id": seed_id}

        conn = db.get_conn()
        try:
            conn.executemany(
                """INSERT INTO kw2_intelligence_questions
                   (id, session_id, project_id, module_code, question,
                    content_type, expansion_depth, parent_question_id,
                    status, expansion_dimension_name, expansion_dimension_value,
                    data_source, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                to_insert,
            )
            conn.commit()
        finally:
            conn.close()

        # ── AI validation pass: reject template/low-quality questions ──
        inserted_ids = [row[0] for row in to_insert]  # id is first element
        rejected_count = self._validate_questions(
            inserted_ids, session_id, business_context, ai_provider, project_id,
        )
        final_count = len(to_insert) - rejected_count
        log.info("[ExpansionEngine] seed=%s created=%d rejected=%d kept=%d",
                 seed_id, len(to_insert), rejected_count, final_count)

        return {"questions_created": final_count, "seed_id": seed_id, "rejected": rejected_count}

    def _validate_questions(
        self,
        question_ids: list[str],
        session_id: str,
        business_context: str,
        ai_provider: str,
        project_id: str,
        batch_size: int = 40,
    ) -> int:
        """AI validation pass: reject template substitutions and low-quality questions.

        Returns the number of questions rejected (marked is_duplicate=1).
        """
        if not question_ids:
            return 0

        conn = db.get_conn()
        try:
            placeholders = ",".join("?" for _ in question_ids)
            rows = conn.execute(
                f"""SELECT id, question FROM kw2_intelligence_questions
                    WHERE id IN ({placeholders}) AND session_id=?""",
                (*question_ids, session_id),
            ).fetchall()
        finally:
            conn.close()

        questions = [dict(r) for r in rows]
        if not questions:
            return 0

        total_rejected = 0

        # Process in batches to stay within token limits
        for i in range(0, len(questions), batch_size):
            batch = questions[i : i + batch_size]
            questions_json = json.dumps(
                [{"id": q["id"], "question": q["question"]} for q in batch],
                ensure_ascii=False,
            )
            prompt = VALIDATE_QUESTIONS_USER.format(
                business_context=(business_context or "")[:600],
                questions_json=questions_json[:6000],
            )
            try:
                resp = kw2_ai_call(
                    prompt, VALIDATE_QUESTIONS_SYSTEM,
                    provider=ai_provider, temperature=0.1,
                    session_id=session_id, project_id=project_id,
                    task="expansion_validate",
                )
                result = kw2_extract_json(resp)
                if not isinstance(result, dict):
                    continue

                verdicts = result.get("results", [])
                if not isinstance(verdicts, list):
                    continue

                reject_ids = []
                for v in verdicts:
                    if not isinstance(v, dict):
                        continue
                    if str(v.get("verdict", "")).upper() == "REJECT":
                        reject_ids.append(v.get("id"))

                if reject_ids:
                    conn = db.get_conn()
                    try:
                        for rid in reject_ids:
                            conn.execute(
                                """UPDATE kw2_intelligence_questions
                                   SET is_duplicate=1, duplicate_of='ai_validation_reject'
                                   WHERE id=? AND session_id=?""",
                                (rid, session_id),
                            )
                        conn.commit()
                        total_rejected += len(reject_ids)
                    finally:
                        conn.close()

            except Exception as exc:
                log.warning("[ExpansionEngine] Validation batch failed: %s", exc)
                continue

        return total_rejected

    def _load_seeds(self, session_id: str) -> list[dict]:
        conn = db.get_conn()
        try:
            rows = conn.execute(
                """SELECT id, question, module_code, expansion_depth
                   FROM kw2_intelligence_questions
                   WHERE session_id=? AND expansion_depth=0
                   AND is_duplicate=0
                   ORDER BY business_relevance DESC, final_score DESC""",
                (session_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def _save_config(self, session_id: str, dimensions: dict) -> None:
        conn = db.get_conn()
        try:
            existing = conn.execute(
                "SELECT id FROM kw2_expansion_config WHERE session_id=?",
                (session_id,),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE kw2_expansion_config SET discovered_dimensions=? WHERE session_id=?",
                    (_safe_json(dimensions), session_id),
                )
            else:
                conn.execute(
                    """INSERT INTO kw2_expansion_config
                       (id, session_id, discovered_dimensions, created_at)
                       VALUES (?,?,?,?)""",
                    (_uid("ec_"), session_id, _safe_json(dimensions), _now()),
                )
            conn.commit()
        finally:
            conn.close()

    def _load_config(self, session_id: str) -> dict:
        conn = db.get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM kw2_expansion_config WHERE session_id=?",
                (session_id,),
            ).fetchone()
            if not row:
                return {}
            d = dict(row)
            raw = d.get("discovered_dimensions", "{}")
            try:
                d["discovered_dimensions"] = json.loads(raw) if raw else {}
            except Exception:
                d["discovered_dimensions"] = {}
            return d
        finally:
            conn.close()
