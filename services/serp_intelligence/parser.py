import requests
from bs4 import BeautifulSoup
import logging
from urllib.parse import urlparse

log = logging.getLogger("serp.parser")


def parse_page(url):
    if not url:
        return None
    try:
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")

        headings = [h.get_text(strip=True) for h in soup.find_all(["h1", "h2", "h3"]) if h.get_text(strip=True)]
        paragraphs = [p.get_text(strip=True) for p in soup.find_all("p") if p.get_text(strip=True)]
        word_count = sum(len(p.split()) for p in paragraphs)

        is_schema = bool(soup.find_all(lambda tag: tag.name == 'script' and tag.get('type') == 'application/ld+json'))

        schema_age = None
        last_updated = None
        og_updated = soup.find('meta', {'property': 'article:modified_time'})
        if og_updated and og_updated.get('content'):
            last_updated = og_updated['content']

        return {
            "url": url,
            "headings": headings,
            "word_count": word_count,
            "num_sections": len(headings),
            "has_schema": is_schema,
            "last_updated": last_updated,
            "content_type": _infer_content_type(headings),
        }
    except Exception as e:
        log.warning("Failed parse_page(%s): %s", url, e)
        return None


def _infer_content_type(headings):
    body = " ".join(headings).lower()
    if "review" in body or "best" in body or "top" in body:
        return "listicle"
    if "how to" in body or "guide" in body or "step" in body:
        return "how-to"
    if "vs" in body or "compare" in body:
        return "comparison"
    return "article"
