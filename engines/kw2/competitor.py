"""
kw2 Phase 1 helper — gather competitor insights via crawl.
"""
import logging

from engines.kw2.content_segmenter import segment_content

log = logging.getLogger("kw2.competitor")

MAX_COMPETITOR_CHARS = 2000


def get_competitor_insights(competitor_urls: list[str], pillars: list[str]) -> str:
    """
    Crawl competitor sites and return combined product/category text.

    Args:
        competitor_urls: list of competitor website URLs
        pillars: current pillar keywords (for context filtering)

    Returns:
        Combined text string from competitor sites (capped at 2000 chars).
        Returns "" on any error.
    """
    if not competitor_urls:
        return ""

    try:
        from engines.intelligent_crawl_engine import IntelligentSiteCrawler
    except ImportError:
        log.warning("IntelligentSiteCrawler not available")
        return ""

    crawler = IntelligentSiteCrawler()
    parts = []
    chars_per_url = MAX_COMPETITOR_CHARS // max(len(competitor_urls), 1)

    for url in competitor_urls[:4]:  # max 4 competitors
        try:
            pages = crawler.crawl_site(url, max_pages=10)
            if not pages:
                continue
            seg = segment_content(pages)
            text = f"{seg['products']} {seg['categories']}".strip()
            if text:
                parts.append(text[:chars_per_url])
        except Exception as e:
            log.warning(f"Competitor crawl failed for {url}: {e}")
            continue

    return " ".join(parts)[:MAX_COMPETITOR_CHARS]
