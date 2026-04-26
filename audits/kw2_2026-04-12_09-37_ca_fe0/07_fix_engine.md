# Fix Engine

Original Code:
```python
def analyze(self, project_id: str, url: str | None = None, manual_input: dict | None = None, competitor_urls: list[str] | None = None, ai_provider: str = "auto", force: bool = False) -> dict:
    """Full Phase 1 analysis pipeline. Returns a business profile dict with confidence score. Uses cache if available and not expired (unless force=True)."""
    
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
        pages = self._crawl(url)
        log.info(f"[Phase1] Crawled {len(pages)} pages from {url}")

    # 3. Segment content
    segmented = segment_content(pages) if pages else {
        "products": "", "categories": "", "about": "", "found_products": []
    }

    # 4. Extract entities
    combined_text = f"{segmented['products']} {segmented['categories']}"
    entities, topics = extract_entities(combined_text)

    # 5. Competitor insights
    competitor_insights = get_competitor_insights(competitor_urls)

    # 6. AI analysis
    confidence_score = compute_confidence(entities, topics, competitor_insights)

    # 7. Consistency check
    consistency_check = check_consistency(pages, segmented, entities, topics, competitor_insights)

    # 8. Pillar extractor
    pillar_extractor = PillarExtractor()
    pillars = pillar_extractor.extract(pages)

    # 9. Modifier extractor
    modifier_extractor = ModifierExtractor(DEFAULT_MODIFIERS)
    modified_texts = modifier_extractor.modify(combined_text)

    # 10. Persist
    profile = {
        "project_id": project_id,
        "url": url,
        "manual_input": manual_input,
        "competitor_urls": competitor_urls,
        "ai_provider": ai_provider,
        "force