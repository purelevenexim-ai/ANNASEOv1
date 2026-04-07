"""
kw2 Phase 2 — Keyword Universe Generator.

5-layer generation pipeline:
  Layer 1: Seeds (pillar × modifier combos)
  Layer 2: Rule expand (transactional templates per seed)
  Layer 3: Google Suggest (autosuggest per pillar)
  Layer 4: Competitor crawl (keywords from competitor sites)
  Layer 5: AI expand (30 buyer-intent keywords per pillar)

Then: negative filter → normalize → dedup → bulk insert.
"""
import json
import logging
import re

from engines.kw2.constants import (
    NEGATIVE_PATTERNS, TRANSACTIONAL_TEMPLATES, COMMERCIAL_TEMPLATES,
    LOCAL_TEMPLATES, GARBAGE_WORDS,
)
from engines.kw2.prompts import UNIVERSE_EXPAND_SYSTEM, UNIVERSE_EXPAND_USER
from engines.kw2.ai_caller import kw2_ai_call
from engines.kw2 import db

log = logging.getLogger("kw2.generator")


class KeywordUniverseGenerator:
    """Phase 2: Generate a keyword universe from business profile data."""

    def generate(
        self,
        project_id: str,
        session_id: str,
        competitor_urls: list[str] | None = None,
        ai_provider: str = "auto",
    ) -> dict:
        """
        Full synchronous generation — returns summary stats.
        """
        profile = db.load_business_profile(project_id)
        if not profile:
            raise ValueError(f"No business profile found for project {project_id}. Run Phase 1 first.")

        pillars = profile.get("pillars", [])
        modifiers = profile.get("modifiers", [])
        negative_scope = profile.get("negative_scope", [])
        universe = profile.get("universe", "")
        geo = profile.get("geo_scope", "")

        all_keywords = []
        stats = {"seeds": 0, "rules": 0, "suggest": 0, "competitor": 0, "ai_expand": 0}

        # Layer 1: Seeds
        seeds = self._build_seeds(pillars, modifiers)
        all_keywords.extend(seeds)
        stats["seeds"] = len(seeds)

        # Layer 2: Rule expand
        rule_kws = self._rule_expand(pillars, modifiers, geo)
        all_keywords.extend(rule_kws)
        stats["rules"] = len(rule_kws)

        # Layer 3: Google Suggest
        suggest_kws = self._google_suggest(pillars)
        all_keywords.extend(suggest_kws)
        stats["suggest"] = len(suggest_kws)

        # Layer 4: Competitor
        if competitor_urls:
            comp_kws = self._competitor_keywords(competitor_urls, pillars)
            all_keywords.extend(comp_kws)
            stats["competitor"] = len(comp_kws)

        # Layer 5: AI expand
        ai_kws = self._ai_expand(pillars, modifiers, universe, ai_provider)
        all_keywords.extend(ai_kws)
        stats["ai_expand"] = len(ai_kws)

        # Filter + dedup
        passed, rejected = self._negative_filter(all_keywords, negative_scope)
        unique = self._normalize_dedup(passed)

        # Bulk insert
        db.bulk_insert_universe(session_id, project_id, unique)

        # Also insert rejected items for audit trail
        for r in rejected:
            r["status"] = "rejected"
        db.bulk_insert_universe(session_id, project_id, rejected)

        # Update session
        db.update_session(session_id, phase2_done=1, universe_count=len(unique))

        result = {
            "session_id": session_id,
            "total": len(unique),
            "rejected": len(rejected),
            "sources": stats,
        }
        log.info(f"[Phase2] Generated {len(unique)} keywords ({len(rejected)} rejected) for {project_id}")
        return result

    def generate_stream(
        self,
        project_id: str,
        session_id: str,
        competitor_urls: list[str] | None = None,
        ai_provider: str = "auto",
    ):
        """
        SSE generator — yields progress events per layer.
        """
        profile = db.load_business_profile(project_id)
        if not profile:
            yield f'data: {json.dumps({"type": "error", "msg": "No business profile. Run Phase 1 first."})}\n\n'
            return

        pillars = profile.get("pillars", [])
        modifiers = profile.get("modifiers", [])
        negative_scope = profile.get("negative_scope", [])
        universe = profile.get("universe", "")
        geo = profile.get("geo_scope", "")

        all_keywords = []

        # Layer 1: Seeds
        seeds = self._build_seeds(pillars, modifiers)
        all_keywords.extend(seeds)
        yield f'data: {json.dumps({"type": "progress", "source": "seeds", "count": len(seeds)})}\n\n'

        # Layer 2: Rules
        rule_kws = self._rule_expand(pillars, modifiers, geo)
        all_keywords.extend(rule_kws)
        yield f'data: {json.dumps({"type": "progress", "source": "rules", "count": len(rule_kws)})}\n\n'

        # Layer 3: Google Suggest (one event per pillar)
        for pillar in pillars:
            suggest_kws = self._google_suggest([pillar])
            all_keywords.extend(suggest_kws)
            yield f'data: {json.dumps({"type": "progress", "source": "suggest", "pillar": pillar, "count": len(suggest_kws)})}\n\n'

        # Layer 4: Competitor (one event per URL)
        if competitor_urls:
            for url in competitor_urls[:4]:
                comp_kws = self._competitor_keywords([url], pillars)
                all_keywords.extend(comp_kws)
                yield f'data: {json.dumps({"type": "progress", "source": "competitor", "url": url, "count": len(comp_kws)})}\n\n'

        # Layer 5: AI expand (one event per pillar)
        for pillar in pillars:
            ai_kws = self._ai_expand([pillar], modifiers, universe, ai_provider)
            all_keywords.extend(ai_kws)
            yield f'data: {json.dumps({"type": "progress", "source": "ai_expand", "pillar": pillar, "count": len(ai_kws)})}\n\n'

        # Filter + dedup + persist
        passed, rejected = self._negative_filter(all_keywords, negative_scope)
        unique = self._normalize_dedup(passed)

        db.bulk_insert_universe(session_id, project_id, unique)
        for r in rejected:
            r["status"] = "rejected"
        db.bulk_insert_universe(session_id, project_id, rejected)
        db.update_session(session_id, phase2_done=1, universe_count=len(unique))

        yield f'data: {json.dumps({"type": "complete", "total": len(unique), "rejected": len(rejected)})}\n\n'

    # ── Layer generators ─────────────────────────────────────────────────

    def _build_seeds(self, pillars: list[str], modifiers: list[str]) -> list[dict]:
        """Layer 1: pillar × modifier forward/reverse combos."""
        seeds = []
        for p in pillars:
            seeds.append({"keyword": p, "source": "seeds", "pillar": p, "raw_score": 80.0})
            for m in modifiers:
                seeds.append({"keyword": f"{m} {p}", "source": "seeds", "pillar": p, "raw_score": 70.0})
                seeds.append({"keyword": f"{p} {m}", "source": "seeds", "pillar": p, "raw_score": 70.0})
        return seeds

    def _rule_expand(self, pillars: list[str], modifiers: list[str], geo: str) -> list[dict]:
        """Layer 2: apply transactional/commercial/local templates."""
        results = []
        for p in pillars:
            for tmpl in TRANSACTIONAL_TEMPLATES:
                kw = tmpl.replace("{k}", p)
                results.append({"keyword": kw, "source": "rules", "pillar": p, "raw_score": 65.0})

            for tmpl in COMMERCIAL_TEMPLATES:
                if "{alt}" in tmpl:
                    # Pair with other pillars
                    for other in pillars:
                        if other != p:
                            kw = tmpl.replace("{k}", p).replace("{alt}", other)
                            results.append({"keyword": kw, "source": "rules", "pillar": p, "raw_score": 55.0})
                else:
                    kw = tmpl.replace("{k}", p)
                    results.append({"keyword": kw, "source": "rules", "pillar": p, "raw_score": 60.0})

            # Local templates
            locations = [geo] if geo else []
            for loc in locations:
                for tmpl in LOCAL_TEMPLATES:
                    kw = tmpl.replace("{k}", p).replace("{loc}", loc)
                    results.append({"keyword": kw, "source": "rules", "pillar": p, "raw_score": 55.0})

        return results

    def _google_suggest(self, pillars: list[str]) -> list[dict]:
        """Layer 3: Google Autosuggest via reusable engine."""
        try:
            from engines.intelligent_crawl_engine import GoogleSuggestEnricher
            enricher = GoogleSuggestEnricher()
            scored = enricher.enrich(pillars)
            results = []
            for sk in scored:
                kw = getattr(sk, "keyword", str(sk))
                pillar = self._detect_pillar(kw, pillars)
                results.append({"keyword": kw, "source": "suggest", "pillar": pillar, "raw_score": 60.0})
            return results
        except Exception as e:
            log.warning(f"Google Suggest failed: {e}")
            return []

    def _competitor_keywords(self, urls: list[str], pillars: list[str]) -> list[dict]:
        """Layer 4: keywords from competitor site crawl."""
        try:
            from engines.intelligent_crawl_engine import SmartCompetitorAnalyzer
            analyzer = SmartCompetitorAnalyzer()
            results = []
            for url in urls[:4]:
                try:
                    scored = analyzer.analyze_competitor(url, pillars, max_pages=15)
                    for sk in scored:
                        kw = getattr(sk, "keyword", str(sk))
                        pillar = self._detect_pillar(kw, pillars)
                        results.append({"keyword": kw, "source": "competitor", "pillar": pillar, "raw_score": 55.0})
                except Exception as e:
                    log.warning(f"Competitor crawl failed for {url}: {e}")
            return results
        except ImportError:
            log.warning("SmartCompetitorAnalyzer not available")
            return []

    def _ai_expand(self, pillars: list[str], modifiers: list[str], universe: str, provider: str) -> list[dict]:
        """Layer 5: AI-generated buyer-intent keywords."""
        results = []
        for pillar in pillars:
            try:
                prompt = UNIVERSE_EXPAND_USER.format(
                    universe=universe, pillar=pillar,
                    modifiers=", ".join(modifiers[:10]),
                )
                response = kw2_ai_call(prompt, UNIVERSE_EXPAND_SYSTEM, provider=provider)
                if not response:
                    continue
                lines = [l.strip() for l in response.strip().split("\n") if l.strip()]
                for line in lines[:30]:
                    # Clean numbering/bullets
                    clean = re.sub(r'^[\d\.\-\*\)\]]+\s*', '', line).strip()
                    if clean and len(clean) > 3:
                        results.append({"keyword": clean, "source": "ai_expand", "pillar": pillar, "raw_score": 50.0})
            except Exception as e:
                log.warning(f"AI expand failed for pillar {pillar}: {e}")
        return results

    # ── Filters ──────────────────────────────────────────────────────────

    def _negative_filter(self, keywords: list[dict], negative_scope: list[str]) -> tuple[list[dict], list[dict]]:
        """Hard-reject keywords matching negative patterns."""
        neg_patterns = set(p.lower() for p in (negative_scope or []))
        neg_patterns.update(p.lower() for p in NEGATIVE_PATTERNS)

        passed = []
        rejected = []
        for kw_dict in keywords:
            kw_lower = kw_dict["keyword"].lower()
            hit = False
            for neg in neg_patterns:
                if neg in kw_lower:
                    kw_dict["reject_reason"] = f"negative_pattern:{neg}"
                    rejected.append(kw_dict)
                    hit = True
                    break
            if not hit:
                passed.append(kw_dict)
        return passed, rejected

    def _normalize_dedup(self, keywords: list[dict]) -> list[dict]:
        """Normalize text + exact-match dedup. Keeps first occurrence (highest raw_score first)."""
        # Sort by score desc so dedup keeps highest
        keywords.sort(key=lambda x: x.get("raw_score", 0), reverse=True)

        seen = set()
        unique = []
        for kw_dict in keywords:
            normalized = self._normalize(kw_dict["keyword"])
            if not normalized or len(normalized) < 4:
                continue
            if normalized not in seen:
                seen.add(normalized)
                kw_dict["keyword"] = normalized
                unique.append(kw_dict)
        return unique

    def _normalize(self, text: str) -> str:
        """Lowercase, strip, collapse whitespace, remove non-alphanumeric except spaces."""
        text = text.lower().strip()
        text = re.sub(r'[^a-z0-9\s]', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def _detect_pillar(self, keyword: str, pillars: list[str]) -> str:
        """Detect which pillar a keyword belongs to."""
        kw_lower = keyword.lower()
        for p in pillars:
            if p.lower() in kw_lower:
                return p
        return pillars[0] if pillars else "general"
