# Fix Engine

```python
# ═══ FILE: engines/kw2/business_analyzer.py ════
"""
kw2 Phase 1 — Business Intelligence Engine.

Orchestrates: crawl → segment → extract entities → competitor insights → AI analysis
→ consistency check → confidence score → persist.
"""
import json
import logging
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

from engines.kw2.constants import NEGATIVE_PATTERNS, CRAWL_MAX_PAGES, PROFILE_CACHE_DAYS
from engines.kw2.prompts import BUSINESS_ANALYSIS_SYSTEM, BUSINESS_ANALYSIS_USER
from engines.kw2.ai_caller import kw2_ai_call, kw2_extract_json
from engines.kw2.content_segmenter import segment_content
from engines.kw2.entity_extractor import extract_entities
from engines.kw2.competitor import get_competitor_insights
from engines.kw2.confidence import compute_confidence
from engines.kw2.consistency import check_consistency
from engines.kw2.pillar_extractor import PillarExtractor
from engines.kw2.modifier_extractor import ModifierExtractor, DEFAULT_MODIFIERS
from engines.kw2 import db

log = logging.getLogger("kw2.business")


class BusinessIntelligenceEngine:
    """Phase 1: Analyze a business website and produce a structured profile."""

    def analyze(
        self,
        project_id: str,
        url: str | None = None,
        manual_input: dict | None = None,
        competitor_urls: list[str] | None = None,
        ai_provider: str = "auto",
        force: bool = False,
    ) -> dict:
        """
        Full Phase 1 analysis pipeline.

        Returns a business profile dict with confidence score.
        Uses cache if available and not expired (unless force=True).
        """
        # 1. Cache check
        if not force:
            cached = db.load_business_profile(project_id)
            if cached and self._is_fresh(cached):
                log.info(f"[Phase1] Using cached profile for {project_id}")
                cached["cached"] = True
                return cached

        # 2. Crawl customer site
        pages = []
        if url:
            pages = self._crawl