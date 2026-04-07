"""
kw2 Phase 1 helper — segment crawled pages into product/category/about buckets.
"""
import logging

log = logging.getLogger("kw2.segmenter")

MAX_PRODUCTS_CHARS = 2000
MAX_CATEGORIES_CHARS = 1500
MAX_ABOUT_CHARS = 500


def segment_content(pages: list) -> dict:
    """
    Segment CrawledPage objects into product, category, and about text buckets.

    Args:
        pages: List of CrawledPage (from IntelligentSiteCrawler.crawl_site)
               Each has: page_type, title, headings, body_text, products_found

    Returns:
        {"products": str, "categories": str, "about": str, "found_products": list}
    """
    products_parts = []
    categories_parts = []
    about_parts = []
    found_products = []

    for p in pages:
        ptype = getattr(p, "page_type", "").lower()
        title = getattr(p, "title", "") or ""
        headings = getattr(p, "headings", []) or []
        body = getattr(p, "body_text", "") or ""
        prods = getattr(p, "products_found", []) or []

        text = f"{title} {' '.join(headings)} {body}"

        if ptype == "product":
            products_parts.append(text)
            found_products.extend(prods)
        elif ptype in ("category", "homepage"):
            categories_parts.append(text)
            found_products.extend(prods)
        elif ptype == "about":
            about_parts.append(text)

    # Deduplicate found products
    seen = set()
    unique_products = []
    for p in found_products:
        pl = str(p).strip().lower()
        if pl and pl not in seen:
            seen.add(pl)
            unique_products.append(str(p).strip())

    return {
        "products": _cap(" ".join(products_parts), MAX_PRODUCTS_CHARS),
        "categories": _cap(" ".join(categories_parts), MAX_CATEGORIES_CHARS),
        "about": _cap(" ".join(about_parts), MAX_ABOUT_CHARS),
        "found_products": unique_products,
    }


def _cap(text: str, limit: int) -> str:
    """Truncate text to limit chars at word boundary."""
    if len(text) <= limit:
        return text.strip()
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut.strip()
