# Fix Engine

Original Code:
```python
def analyze(self, project_id: str, url: str | None = None, manual_input: dict | None = None, competitor_urls: list[str] | None = None, ai_provider: str = "auto", force: bool = False) -> dict:
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
    ai_analysis = kw2_ai_call(project_id, entities, topics, competitor_insights, ai_provider)

    # 7. Consistency check
    consistency = check_consistency(ai_analysis)

    # 8. Confidence score
    confidence = compute_confidence(entities, topics, consistency)

    # 9. Persist
    db.save_business_profile(project_id, entities, topics, competitor_insights, ai_analysis, consistency, confidence)

    return {
        "entities": entities,
        "topics": topics,
        "competitor_insights": competitor_insights,
        "ai_analysis": ai_analysis,
        "consistency": consistency,
        "confidence": confidence,
        "cached": False,
    }
```
Improved Code:
```python
def analyze(self, project_id