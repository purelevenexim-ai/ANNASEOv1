"""
================================================================================
ANNASEO — INTELLIGENT CRAWL & KEYWORD ENGINE (intelligent_crawl_engine.py)
================================================================================
Replaces the basic n-gram extraction approach with a multi-pass AI-powered
keyword discovery system.

IMPROVEMENTS OVER EXISTING SYSTEM:
  1. DEEP SITE CRAWL — Crawls homepage, product pages, about page, blogs
     separately with page-type classification (not just "any page").
  2. AI BUSINESS UNDERSTANDING — Uses LLM to understand what the business
     actually sells, its USP, target audience, and key product categories.
  3. AI KEYWORD EXTRACTION — LLM extracts real keyword candidates from
     page content rather than relying on n-gram frequency counting.
  4. AI KEYWORD CLASSIFICATION — Classifies each keyword as good/bad with
     purchase intent scoring (transactional vs informational) and relevance.
  5. SMART COMPETITOR ANALYSIS — Only crawls competitor homepage + blogs
     matching our pillars + product pages matching our pillars (not all pages).
  6. SUPPORTING KEYWORD SCORING — Each supporting keyword scored for:
     purchase intent, search volume signal, relevance to pillar, ranking
     feasibility, and customer intent (purchase vs information).

WORKFLOW:
  Phase 1: User provides seed pillars + URL
  Phase 2: Crawl customer site → extract ALL keywords AI finds relevant
  Phase 3: AI analyses business → confirms/adds pillar keywords
  Phase 4: User confirms pillars → "Next" triggers competitor crawl
  Phase 5: Competitor crawl (focused: homepage + pillar-matching pages only)
  Phase 6: AI scores & ranks supporting keywords (top 5 per pillar)

AI ROUTING:
  Groq (primary, free) → Gemini (fallback) → Ollama/DeepSeek (offline)

================================================================================
"""

from __future__ import annotations

import os, re, json, hashlib, time, logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from urllib.parse import urlparse, urljoin

import requests as _req
from bs4 import BeautifulSoup

log = logging.getLogger("annaseo.intelligent_crawl")

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"  # kept for reference
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent"

CRAWL_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; AnnaSEO/2.0; +https://annaseo.com/bot)",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Rate limits
CRAWL_DELAY = 0.3  # seconds between page fetches
AI_RATE_LIMIT = 3.0  # seconds between AI calls (Groq free: 30 RPM)


# ─────────────────────────────────────────────────────────────────────────────
# DATA MODELS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CrawledPage:
    url: str
    page_type: str  # "homepage" | "product" | "about" | "blog" | "category" | "other"
    title: str = ""
    meta_description: str = ""
    headings: List[str] = field(default_factory=list)
    body_text: str = ""
    products_found: List[str] = field(default_factory=list)
    internal_links: List[str] = field(default_factory=list)
    word_count: int = 0
    crawled_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class BusinessProfile:
    """AI-extracted understanding of the business."""
    business_name: str = ""
    business_type: str = ""  # ecommerce, service, blog, saas
    primary_products: List[str] = field(default_factory=list)
    product_categories: List[str] = field(default_factory=list)
    target_audience: str = ""
    usp: str = ""
    geographic_focus: List[str] = field(default_factory=list)
    content_themes: List[str] = field(default_factory=list)
    brand_tone: str = ""


@dataclass
class ScoredKeyword:
    """A keyword with full scoring breakdown."""
    keyword: str
    pillar: str
    source: str  # "site_crawl" | "competitor" | "ai_generated" | "google_suggest"
    keyword_type: str  # "pillar" | "supporting"
    intent: str  # "purchase" | "research" | "informational" | "comparison" | "local"

    # Scoring (each 0-100)
    purchase_intent_score: float = 0.0
    relevance_score: float = 0.0
    search_volume_signal: float = 0.0
    ranking_feasibility: float = 0.0
    business_fit_score: float = 0.0
    final_score: float = 0.0

    # Metadata
    page_url: str = ""
    page_type: str = ""
    ai_reasoning: str = ""
    is_good: bool = True
    # Pillar tier: "product" (score 100) | "thematic" (score 50) | "" (supporting)
    pillar_tier: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1 — AI CALLER (delegates to central AIRouter)
# ─────────────────────────────────────────────────────────────────────────────

try:
    import sys as _sys
    _sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'core'))
    from ai_config import AIRouter as _AIRouter
    _ai_router_available = True
except ImportError:
    _ai_router_available = False
    log.warning("[IntelCrawl] Could not import AIRouter — falling back to inline calls")


class AICaller:
    """Thin wrapper around the central AIRouter. All AI goes through one place."""

    @staticmethod
    def call(prompt: str, system: str = "You are an expert SEO analyst.",
             temperature: float = 0.2) -> str:
        if _ai_router_available:
            return _AIRouter.call(prompt, system, temperature)
        return ""

    @staticmethod
    def extract_json(text: str):
        if _ai_router_available:
            return _AIRouter.extract_json(text)
        if not text:
            return None
        try:
            return json.loads(text)
        except Exception:
            pass
        for start, end in [('{', '}'), ('[', ']')]:
            idx_s = text.find(start)
            idx_e = text.rfind(end)
            if idx_s >= 0 and idx_e > idx_s:
                try:
                    return json.loads(text[idx_s:idx_e + 1])
                except Exception:
                    pass
        return None


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2 — INTELLIGENT SITE CRAWLER
# ─────────────────────────────────────────────────────────────────────────────

class IntelligentSiteCrawler:
    """
    Crawls a website with page-type awareness:
    - Homepage: extract business overview, main products
    - Product pages: extract product names, descriptions, features
    - About page: extract USP, brand story, target audience
    - Blog pages: extract content themes, topic keywords
    - Category pages: extract product categories
    """

    # URL patterns for page type classification
    PRODUCT_PATTERNS = re.compile(
        r'/(product|shop|store|item|buy|p/)|(\.html|\.php)\?.*id=',
        re.I
    )
    BLOG_PATTERNS = re.compile(
        r'/(blog|article|post|news|guide|learn|resources|tips|recipe)',
        re.I
    )
    ABOUT_PATTERNS = re.compile(
        r'/(about|who-we-are|our-story|company|team|mission)',
        re.I
    )
    CATEGORY_PATTERNS = re.compile(
        r'/(category|categories|collection|collections|catalog|department)',
        re.I
    )
    SKIP_PATTERNS = re.compile(
        r'/(cart|checkout|account|login|signup|register|privacy|terms|'
        r'cookie|faq|contact|sitemap|feed|wp-json|wp-admin|cdn-cgi|'
        r'policies|refund|return|shipping-policy|terms-of-service|'
        r'\.pdf|\.jpg|\.png|\.gif|\.css|\.js)',
        re.I
    )

    def crawl_site(self, url: str, max_pages: int = 30) -> List[CrawledPage]:
        """
        Intelligently crawl a site, prioritizing key page types.
        Returns pages grouped by type for downstream AI analysis.
        """
        if not url.startswith("http"):
            url = f"https://{url}"
        domain = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
        log.info(f"[IntelCrawl] Starting intelligent crawl of {domain}")

        # Phase 1: Discover all URLs
        all_urls = self._discover_urls(url, domain)
        log.info(f"[IntelCrawl] Discovered {len(all_urls)} URLs")

        # Phase 2: Classify URLs by page type
        classified = self._classify_urls(all_urls, domain)

        # Phase 3: Prioritize crawl order (homepage first, then products, about, blogs)
        crawl_order = self._prioritize_crawl(classified, url, max_pages)
        log.info(f"[IntelCrawl] Crawling {len(crawl_order)} prioritized pages")

        # Phase 4: Crawl each page
        pages = []
        for page_url, page_type in crawl_order:
            page = self._crawl_page(page_url, page_type)
            if page:
                pages.append(page)
            time.sleep(CRAWL_DELAY)

        log.info(f"[IntelCrawl] Successfully crawled {len(pages)} pages "
                 f"(product={sum(1 for p in pages if p.page_type=='product')}, "
                 f"blog={sum(1 for p in pages if p.page_type=='blog')}, "
                 f"about={sum(1 for p in pages if p.page_type=='about')})")
        return pages

    def _discover_urls(self, start_url: str, domain: str) -> List[str]:
        """Discover URLs via sitemap + homepage link extraction."""
        urls = set()
        urls.add(start_url)

        # Try sitemap
        for path in ["/sitemap.xml", "/sitemap_index.xml"]:
            try:
                r = _req.get(f"{domain}{path}", headers=CRAWL_HEADERS, timeout=8)
                if r.ok and "xml" in r.headers.get("content-type", ""):
                    soup = BeautifulSoup(r.text, "xml")
                    # Handle sitemap index (nested sitemaps)
                    for sitemap_loc in soup.find_all("loc"):
                        loc_text = sitemap_loc.get_text().strip()
                        if "sitemap" in loc_text.lower() and loc_text.endswith(".xml"):
                            try:
                                sub_r = _req.get(loc_text, headers=CRAWL_HEADERS, timeout=8)
                                if sub_r.ok:
                                    sub_soup = BeautifulSoup(sub_r.text, "xml")
                                    for sub_loc in sub_soup.find_all("loc"):
                                        u = sub_loc.get_text().strip()
                                        if u.startswith(domain):
                                            urls.add(u)
                            except Exception:
                                pass
                        elif loc_text.startswith(domain):
                            urls.add(loc_text)
                    if len(urls) > 5:
                        break
            except Exception:
                pass

        # Also extract links from homepage
        try:
            r = _req.get(start_url, headers=CRAWL_HEADERS, timeout=10)
            if r.ok:
                soup = BeautifulSoup(r.text, "html.parser")
                for a in soup.find_all("a", href=True):
                    href = urljoin(start_url, a["href"])
                    parsed = urlparse(href)
                    # Same domain, no fragments, no query params (usually)
                    clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                    if clean_url.startswith(domain) and not self.SKIP_PATTERNS.search(parsed.path):
                        urls.add(clean_url.rstrip("/"))
        except Exception as e:
            log.debug(f"[IntelCrawl] Homepage link extraction failed: {e}")

        return list(urls)[:200]  # cap at 200 URLs for discovery

    def _classify_urls(self, urls: List[str], domain: str) -> Dict[str, List[str]]:
        """Classify URLs into page types based on URL patterns."""
        classified = {
            "homepage": [],
            "product": [],
            "blog": [],
            "about": [],
            "category": [],
            "other": [],
        }

        homepage_netloc = urlparse(domain).netloc
        for url in urls:
            parsed = urlparse(url)
            path = parsed.path.rstrip("/")

            # Homepage: root path or very short path
            if not path or path == "/":
                classified["homepage"].append(url)
            elif self.PRODUCT_PATTERNS.search(path):
                classified["product"].append(url)
            elif self.BLOG_PATTERNS.search(path):
                classified["blog"].append(url)
            elif self.ABOUT_PATTERNS.search(path):
                classified["about"].append(url)
            elif self.CATEGORY_PATTERNS.search(path):
                classified["category"].append(url)
            else:
                # Short paths with 1-2 segments are likely product or category pages
                segments = [s for s in path.split("/") if s]
                if len(segments) <= 2:
                    classified["product"].append(url)
                else:
                    classified["other"].append(url)

        return classified

    def _prioritize_crawl(self, classified: Dict[str, List[str]],
                          start_url: str, max_pages: int) -> List[Tuple[str, str]]:
        """Build prioritized crawl list."""
        order = []

        # 1. Homepage (always first)
        for url in classified.get("homepage", [start_url])[:1]:
            order.append((url, "homepage"))

        # 2. About page (understand business)
        for url in classified.get("about", [])[:2]:
            order.append((url, "about"))

        # 3. Product pages (core keywords)
        for url in classified.get("product", [])[:12]:
            order.append((url, "product"))

        # 4. Category pages (keyword clusters)
        for url in classified.get("category", [])[:5]:
            order.append((url, "category"))

        # 5. Blog pages (content themes)
        for url in classified.get("blog", [])[:8]:
            order.append((url, "blog"))

        # 6. Other pages (fill remaining slots)
        remaining = max_pages - len(order)
        if remaining > 0:
            for url in classified.get("other", [])[:remaining]:
                order.append((url, "other"))

        return order[:max_pages]

    def _crawl_page(self, url: str, page_type: str) -> Optional[CrawledPage]:
        """Crawl a single page and extract structured content."""
        try:
            r = _req.get(url, headers=CRAWL_HEADERS, timeout=12)
            if not r.ok or "text/html" not in r.headers.get("content-type", ""):
                return None

            soup = BeautifulSoup(r.text, "html.parser")

            # Title
            title = soup.title.get_text(strip=True) if soup.title else ""

            # Meta description
            meta = soup.find("meta", attrs={"name": re.compile("description", re.I)})
            meta_desc = meta.get("content", "").strip() if meta else ""

            # Headings
            headings = []
            for tag in soup.find_all(["h1", "h2", "h3"])[:30]:
                text = tag.get_text(strip=True)
                if text and len(text) > 2:
                    headings.append(text)

            # Clean body text
            for tag in soup(["script", "style", "nav", "footer", "header",
                            "aside", "form", "iframe", "noscript"]):
                tag.decompose()

            body_text = " ".join(soup.get_text().split())
            # Trim to manageable size for AI (first 3000 words)
            words = body_text.split()
            body_text_trimmed = " ".join(words[:3000])

            # Extract product names from schema.org markup
            products_found = []
            for item in soup.find_all(attrs={"itemtype": re.compile("schema.org/Product", re.I)}):
                name_el = item.find(attrs={"itemprop": "name"})
                if name_el:
                    products_found.append(name_el.get_text(strip=True))

            # Also check JSON-LD structured data
            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    ld = json.loads(script.string or "")
                    if isinstance(ld, dict):
                        ld = [ld]
                    for item in ld if isinstance(ld, list) else []:
                        if item.get("@type") == "Product" and item.get("name"):
                            products_found.append(item["name"])
                        elif item.get("@type") == "ItemList":
                            for elem in item.get("itemListElement", []):
                                if isinstance(elem, dict) and elem.get("name"):
                                    products_found.append(elem["name"])
                except (json.JSONDecodeError, TypeError):
                    pass

            # Extract product names from title for ecommerce sites
            # e.g. "Kerala Cardamom 8mm - 200gm – Organic Pure Leven"
            if page_type == "product" and title:
                # Remove brand/site suffix after — or – or |
                clean_title = re.split(r'\s*[—–|]\s*', title)[0].strip()
                if clean_title and len(clean_title) > 5:
                    products_found.append(clean_title)

            # Internal links
            internal_links = []
            domain = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
            for a in soup.find_all("a", href=True):
                href = urljoin(url, a["href"])
                if href.startswith(domain) and not self.SKIP_PATTERNS.search(href):
                    internal_links.append(href)

            return CrawledPage(
                url=url,
                page_type=page_type,
                title=title,
                meta_description=meta_desc,
                headings=headings,
                body_text=body_text_trimmed,
                products_found=list(dict.fromkeys(products_found)),
                internal_links=list(dict.fromkeys(internal_links))[:30],
                word_count=len(words),
            )
        except Exception as e:
            log.debug(f"[IntelCrawl] Failed to crawl {url}: {e}")
            return None


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3 — AI BUSINESS ANALYZER
# ─────────────────────────────────────────────────────────────────────────────

class AIBusinessAnalyzer:
    """
    Uses AI to deeply understand the business from crawled pages.
    Extracts: products, services, USP, target market, content themes.
    """

    def analyze(self, pages: List[CrawledPage], user_pillars: List[str] = None) -> BusinessProfile:
        """
        Analyze all crawled pages to build a business profile.
        This helps identify pillar keywords the user may have missed.
        """
        # Build context from crawled pages
        context = self._build_context(pages)
        user_pillars = user_pillars or []

        prompt = f"""Analyze this website content and extract a business profile.

WEBSITE CONTENT:
---
Homepage Title: {context['homepage_title']}
Homepage Description: {context['homepage_meta']}
All Page Titles: {json.dumps(context['all_titles'][:20])}
All Headings (H1-H3): {json.dumps(context['all_headings'][:40])}
Products Found: {json.dumps(context['products_found'][:30])}
Blog Topics: {json.dumps(context['blog_titles'][:15])}
Page Types Found: {json.dumps(context['page_type_counts'])}

User's Existing Pillars: {json.dumps(user_pillars)}
---

Return a JSON object with:
{{
  "business_name": "detected business name",
  "business_type": "ecommerce|service|blog|saas|marketplace",
  "primary_products": ["list of main products/services - these are pillar keyword candidates"],
  "product_categories": ["broader categories these products belong to"],
  "target_audience": "who buys these products",
  "usp": "what makes this business unique (1-2 sentences)",
  "geographic_focus": ["countries/regions they serve"],
  "content_themes": ["blog/content topics they cover"],
  "brand_tone": "professional|casual|luxury|budget-friendly|technical|...",
  "missing_pillars": ["products/services found on site but NOT in user's existing pillars"]
}}

Focus on identifying ALL products and services. These become pillar keywords.
Be thorough - check headings, product names, blog topics for product mentions.
Return ONLY valid JSON."""

        result = AICaller.call(prompt)
        parsed = AICaller.extract_json(result)

        if not parsed or not isinstance(parsed, dict):
            log.warning("[BizAnalyzer] AI returned unparseable response, using fallback")
            return self._fallback_profile(pages, context)

        return BusinessProfile(
            business_name=parsed.get("business_name", ""),
            business_type=parsed.get("business_type", ""),
            primary_products=parsed.get("primary_products", []),
            product_categories=parsed.get("product_categories", []),
            target_audience=parsed.get("target_audience", ""),
            usp=parsed.get("usp", ""),
            geographic_focus=parsed.get("geographic_focus", []),
            content_themes=parsed.get("content_themes", []),
            brand_tone=parsed.get("brand_tone", ""),
        )

    def _build_context(self, pages: List[CrawledPage]) -> dict:
        """Build structured context from crawled pages for AI analysis."""
        homepage = next((p for p in pages if p.page_type == "homepage"), None)
        return {
            "homepage_title": homepage.title if homepage else "",
            "homepage_meta": homepage.meta_description if homepage else "",
            "all_titles": [p.title for p in pages if p.title],
            "all_headings": [h for p in pages for h in p.headings],
            "products_found": list(dict.fromkeys(
                prod for p in pages for prod in p.products_found
            )),
            "blog_titles": [p.title for p in pages if p.page_type == "blog"],
            "page_type_counts": {
                pt: sum(1 for p in pages if p.page_type == pt)
                for pt in ["homepage", "product", "blog", "about", "category", "other"]
            },
        }

    # Noise text patterns common on ecommerce sites (Shopify, WooCommerce, etc.)
    NOISE_PATTERNS = [
        "item added to your cart", "add to cart", "added to cart",
        "shopping cart", "your cart", "view cart", "checkout",
        "free shipping", "shipping policy", "refund policy",
        "terms of service", "privacy policy", "cookie policy",
        "subscribe", "newsletter", "sign up", "log in",
        "sold out", "out of stock", "coming soon",
        "skip to content", "menu", "navigation", "search",
        "footer", "header", "sidebar", "copyright",
    ]

    def _is_noise(self, text: str) -> bool:
        """Check if text is website noise (not a real product)."""
        tl = text.lower().strip()
        if len(tl) < 4:
            return True
        return any(noise in tl for noise in self.NOISE_PATTERNS)

    def _fallback_profile(self, pages: List[CrawledPage], context: dict) -> BusinessProfile:
        """Rule-based fallback when AI is unavailable."""
        products = [p for p in context["products_found"] if not self._is_noise(p)]
        # Use H1s from product pages as products
        for p in pages:
            if p.page_type == "product" and p.headings:
                h1 = p.headings[0]
                if not self._is_noise(h1):
                    products.append(h1)
            # Also extract from page titles for ecommerce
            if p.page_type == "product" and p.title:
                clean_title = re.split(r'\s*[—–|]\s*', p.title)[0].strip()
                if clean_title and not self._is_noise(clean_title) and len(clean_title) > 5:
                    products.append(clean_title)
        # Detect business name from homepage title
        homepage = next((p for p in pages if p.page_type == "homepage"), None)
        biz_name = ""
        if homepage and homepage.title:
            biz_name = homepage.title.strip()
        return BusinessProfile(
            business_name=biz_name,
            primary_products=list(dict.fromkeys(products))[:20],
            content_themes=[p.title for p in pages if p.page_type == "blog"][:10],
        )


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4 — AI KEYWORD EXTRACTOR
# ─────────────────────────────────────────────────────────────────────────────

class AIKeywordExtractor:
    """
    Extracts keywords from crawled pages using AI rather than n-gram counting.
    Much higher quality than frequency-based extraction.
    """

    # Words that should NEVER be keywords on their own
    JUNK_WORDS = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been",
        "have", "has", "had", "do", "does", "did", "will", "would",
        "can", "could", "may", "might", "shall", "should",
        "i", "me", "my", "we", "our", "you", "your", "he", "she", "it",
        "they", "them", "this", "that", "these", "those",
        "what", "which", "who", "whom", "where", "when", "why", "how",
        "all", "each", "every", "both", "few", "more", "most", "some",
        "any", "no", "not", "only", "very", "just", "but", "and", "or",
        "if", "so", "than", "too", "also", "about", "up", "out", "on",
        "off", "over", "under", "again", "then", "here", "there",
        # Navigation / site chrome words
        "shop", "buy", "cart", "add", "menu", "home", "login", "sign",
        "search", "next", "prev", "page", "click", "view", "close",
        "us", "us?", "contact", "with", "from", "for", "info",
        # Size/quantity fragments
        "gm", "gms", "kg", "ml", "mm", "cm", "oz", "lbs", "pcs",
        "pack", "qty", "set",
        # Generic
        "new", "sale", "offer", "free", "best", "top", "good",
        "get", "now", "see", "day", "way", "use",
    }

    def _is_junk_keyword(self, keyword: str, pillars: List[str]) -> bool:
        """Return True if keyword is junk and should be rejected."""
        kw = keyword.lower().strip()
        # Too short
        if len(kw) < 3:
            return True
        # Pure number or size like "100gm", "8mm"
        if re.match(r'^[\d.]+\s*(mm|cm|g|gm|grams?|kg|ml|l|oz|lbs?|pcs?)?$', kw, re.I):
            return True
        # Single word that's a junk/stop word
        words = kw.split()
        if len(words) == 1 and kw in self.JUNK_WORDS:
            return True
        # Contains URL-like patterns
        if '://' in kw or '.com' in kw or '.in' in kw:
            return True
        # All words are junk
        if all(w in self.JUNK_WORDS or len(w) < 2 for w in words):
            return True
        return False

    def _is_valid_supporting(self, keyword: str, pillars: List[str]) -> bool:
        """A supporting keyword must be a real search phrase, not a fragment."""
        kw = keyword.lower().strip()
        words = kw.split()
        # Must be at least 2 words
        if len(words) < 2:
            return False
        # Must relate to at least one pillar (contain a pillar word)
        pillar_lower = [p.lower() for p in pillars]
        has_pillar = any(p in kw for p in pillar_lower)
        if not has_pillar:
            # Check if any pillar word is a substring of any keyword word
            has_pillar = any(
                p in w or w in p
                for p in pillar_lower for w in words
                if len(w) > 2
            )
        return has_pillar

    def extract_from_pages(self, pages: List[CrawledPage],
                           pillars: List[str],
                           business_profile: BusinessProfile = None) -> List[ScoredKeyword]:
        """Extract keywords from all pages using rule-based NLP (no AI).

        AI is NOT used during crawl — only in Stage 4 (AI Validate) to review.
        """
        all_keywords = []

        # Group pages by type for batch processing
        page_groups = {}
        for page in pages:
            page_groups.setdefault(page.page_type, []).append(page)

        # Process each page group with rule-based extraction
        for page_type, group_pages in page_groups.items():
            kws = self._rule_based_extract(group_pages, pillars, page_type, business_profile)
            all_keywords.extend(kws)

        # Deduplicate keeping best score
        deduped = self._deduplicate(all_keywords)

        # Quality gate: remove junk keywords
        clean = []
        for kw in deduped:
            if self._is_junk_keyword(kw.keyword, pillars):
                continue
            if kw.keyword_type == "supporting" and not self._is_valid_supporting(kw.keyword, pillars):
                continue
            clean.append(kw)

        log.info(f"[RuleExtract] Extracted {len(clean)} quality keywords "
                 f"(filtered {len(deduped) - len(clean)} junk) from {len(pages)} pages")
        return clean

    def _extract_group(self, pages: List[CrawledPage], page_type: str,
                       pillars: List[str],
                       profile: BusinessProfile = None) -> List[ScoredKeyword]:
        """Extract keywords from a group of same-type pages using AI.

        Two-tier pillar scoring:
        - Tier 1 (product pages) → core product names → score 100
        - Tier 2 (homepage/about/blog/category) → thematic category keywords → score 50
        - Supporting → long-tail phrases that contain a pillar word → scored by classifier
        """
        # Build content summary for AI
        content_parts = []
        for p in pages[:6]:
            content_parts.append(
                f"URL: {p.url}\n"
                f"Title: {p.title}\n"
                f"Headings: {', '.join(p.headings[:8])}\n"
                f"Products: {', '.join(p.products_found[:8])}\n"
                f"Content preview: {p.body_text[:300]}\n"
            )
        content_text = "\n---\n".join(content_parts)

        # ── PRODUCT PAGES: Tier 1 pillar extraction ─────────────────────────
        if page_type == "product":
            return self._extract_tier1_pillars(pages, page_type, pillars, content_text, profile)

        # ── HOMEPAGE / ABOUT / CATEGORY / BLOG: Tier 2 thematic extraction ──
        if page_type in ("homepage", "about", "category"):
            return self._extract_tier2_thematic(pages, page_type, pillars, content_text, profile)

        # ── BLOG pages: both thematic pillars AND supporting keywords ────────
        if page_type == "blog":
            tier2 = self._extract_tier2_thematic(pages, page_type, pillars, content_text, profile)
            supporting = self._extract_supporting_only(pages, page_type, pillars, content_text, profile)
            return tier2 + supporting

        # ── OTHER pages: supporting keywords only ────────────────────────────
        return self._extract_supporting_only(pages, page_type, pillars, content_text, profile)

    def _extract_tier1_pillars(self, pages: List[CrawledPage], page_type: str,
                               pillars: List[str], content_text: str,
                               profile: BusinessProfile = None) -> List[ScoredKeyword]:
        """
        TIER 1 — Product pages → core product names (score 100).
        These are the EXACT products/services the business sells.
        """
        products_context = ""
        if profile and profile.primary_products:
            products_context = f"\nKnown products: {', '.join(profile.primary_products[:20])}"

        prompt = f"""Extract the CORE PRODUCT NAMES being sold on these product pages.
These become TIER 1 PILLAR keywords (score: 100) — the business's main products.

CONFIRMED PILLAR WORDS (from user): {json.dumps(pillars)}
{products_context}

PRODUCT PAGE CONTENT:
{content_text}

RULES FOR TIER 1 PILLAR EXTRACTION:
- Extract the CORE product name only — not the full title
- Remove geographic qualifiers: "Kerala Cardamom" → "cardamom"
- Remove size/weight: "Black Pepper 500g" → "black pepper"
- Remove quality adjectives: "Pure Organic Turmeric Powder" → "turmeric" or "turmeric powder"
- Maximum 2 words per pillar keyword
- DO NOT include: brand names, sizes (100g), "pack", "bundle", "combo"
- If the same product appears in many variants, list it ONCE

Also extract 2-4 word long-tail supporting keywords for each pillar:
examples: "buy cardamom online", "organic cardamom price", "cardamom 100g pack"

Return ONLY valid JSON:
{{
  "tier1_pillars": [
    {{"keyword": "cardamom", "confidence": 0.95}},
    {{"keyword": "black pepper", "confidence": 0.9}}
  ],
  "supporting_keywords": [
    {{
      "keyword": "buy cardamom online",
      "pillar": "cardamom",
      "intent": "purchase",
      "why_good": "transactional search"
    }}
  ]
}}"""

        result = AICaller.call(prompt)
        parsed = AICaller.extract_json(result)
        keywords = []

        if parsed and isinstance(parsed, dict):
            for pk in parsed.get("tier1_pillars", []):
                kw_text = pk.get("keyword", "").strip().lower()
                if kw_text and len(kw_text) > 2:
                    keywords.append(ScoredKeyword(
                        keyword=kw_text,
                        pillar=kw_text,
                        source="site_crawl",
                        keyword_type="pillar",
                        pillar_tier="product",
                        intent="purchase",
                        page_url=pages[0].url if pages else "",
                        page_type=page_type,
                        relevance_score=100.0,
                        business_fit_score=100.0,
                        purchase_intent_score=100.0,
                        final_score=100.0,
                        is_good=True,
                        ai_reasoning=f"Confirmed product (confidence {pk.get('confidence', 0.9):.0%})",
                    ))
            for sk in parsed.get("supporting_keywords", []):
                kw_text = sk.get("keyword", "").strip().lower()
                if kw_text and len(kw_text) > 3:
                    keywords.append(ScoredKeyword(
                        keyword=kw_text,
                        pillar=sk.get("pillar", "").lower(),
                        source="site_crawl",
                        keyword_type="supporting",
                        pillar_tier="",
                        intent=sk.get("intent", "purchase"),
                        page_url=pages[0].url if pages else "",
                        page_type=page_type,
                        ai_reasoning=sk.get("why_good", ""),
                    ))
        else:
            keywords.extend(self._rule_based_extract(pages, pillars, page_type))

        return keywords

    def _extract_tier2_thematic(self, pages: List[CrawledPage], page_type: str,
                                pillars: List[str], content_text: str,
                                profile: BusinessProfile = None) -> List[ScoredKeyword]:
        """
        TIER 2 — Homepage/about/blog/category → thematic category keywords (score 50).
        These describe WHAT the business is, not specific products.

        Examples for a spice shop:
          "organic spices online", "Kerala spices", "Indian spices",
          "buy spices online india", "pure natural spices"
        """
        known_products = []
        if profile and profile.primary_products:
            known_products = profile.primary_products[:10]

        prompt = f"""Analyze these {page_type} pages to find THEMATIC CATEGORY KEYWORDS.
These are TIER 2 PILLAR keywords (score: 50) — what the business CATEGORY is, not specific products.

EXISTING PRODUCT PILLARS (already discovered, DON'T repeat these): {json.dumps(pillars)}
KNOWN PRODUCTS (for context only): {json.dumps(known_products)}

PAGE CONTENT:
{content_text}

YOUR GOAL: Find 2-5 word search phrases that describe the BUSINESS CATEGORY.
These are what someone searches to FIND this type of business — not to find a specific product.

GOOD EXAMPLES (for a spice ecommerce site):
  ✓ "organic spices online" — category + channel
  ✓ "kerala spices" — geographic brand niche
  ✓ "indian spices online" — category + audience
  ✓ "buy spices online india" — transactional category
  ✓ "authentic south indian spices" — quality positioning
  ✓ "spices wholesale india" — B2B category

BAD EXAMPLES (these are product names, NOT thematic pillars):
  ✗ "cardamom" — specific product (already a Tier 1 pillar)
  ✗ "turmeric powder" — specific product variant
  ✗ "black pepper 500g" — product with size

RULES:
- 2-4 words per keyword
- Must be real Google search queries
- Must reflect this business's category/niche/positioning
- NOT specific product names (those are Tier 1)
- Extract from: headlines, meta descriptions, about text, homepage H1/H2, blog category names
- Include geographic qualifiers if the business has a regional identity
- Include buying channel terms: "online", "wholesale", "bulk"
- Include quality/origin qualifiers: "organic", "pure", "authentic", "natural"

Return ONLY valid JSON:
{{
  "thematic_pillars": [
    {{
      "keyword": "organic spices online",
      "found_in": "homepage H1",
      "why_pillar": "core business category keyword"
    }}
  ]
}}"""

        result = AICaller.call(prompt)
        parsed = AICaller.extract_json(result)
        keywords = []

        if parsed and isinstance(parsed, dict):
            for tp in parsed.get("thematic_pillars", []):
                kw_text = tp.get("keyword", "").strip().lower()
                # Must be 2+ words and not already a pillar
                words = kw_text.split()
                if kw_text and len(words) >= 2 and kw_text not in (p.lower() for p in pillars):
                    keywords.append(ScoredKeyword(
                        keyword=kw_text,
                        pillar=self._match_pillar(kw_text, pillars) or kw_text,
                        source="site_crawl",
                        keyword_type="pillar",
                        pillar_tier="thematic",
                        intent="purchase" if any(w in kw_text for w in ["buy", "online", "wholesale", "price"]) else "research",
                        page_url=pages[0].url if pages else "",
                        page_type=page_type,
                        relevance_score=50.0,
                        business_fit_score=80.0,
                        purchase_intent_score=60.0,
                        final_score=50.0,
                        is_good=True,
                        ai_reasoning=tp.get("why_pillar", "") or f"Found in {tp.get('found_in', page_type)}",
                    ))
        # No rule-based fallback for thematic — better to return empty than junk

        return keywords

    def _extract_supporting_only(self, pages: List[CrawledPage], page_type: str,
                                 pillars: List[str], content_text: str,
                                 profile: BusinessProfile = None) -> List[ScoredKeyword]:
        """Extract supporting long-tail keywords from pages."""
        products_context = ""
        if profile and profile.primary_products:
            products_context = f"\nBusiness products: {', '.join(profile.primary_products[:10])}"

        prompt = f"""Extract SEO supporting keywords from these {page_type} pages.

PILLAR KEYWORDS: {json.dumps(pillars)}
{products_context}

PAGE CONTENT:
{content_text}

Extract SUPPORTING keywords only — long-tail phrases that:
- Are 2-4 words
- Contain or closely relate to a pillar keyword
- Are real phrases people search on Google
- Examples: "buy cardamom online", "organic turmeric benefits", "black pepper price per kg"

Types to find:
- Geographic: "Kerala cardamom", "Indian black pepper"
- Intent: "buy X online", "X price", "X wholesale"
- Informational: "X benefits", "how to use X", "X recipes"
- Comparison: "best X brand"

Return ONLY valid JSON:
{{
  "supporting_keywords": [
    {{
      "keyword": "...",
      "pillar": "which pillar relates to",
      "intent": "purchase|research|informational|comparison|local",
      "why_good": "brief reason"
    }}
  ]
}}"""

        result = AICaller.call(prompt)
        parsed = AICaller.extract_json(result)
        keywords = []

        if parsed and isinstance(parsed, dict):
            for sk in parsed.get("supporting_keywords", []):
                kw_text = sk.get("keyword", "").strip().lower()
                if kw_text and len(kw_text) > 3:
                    keywords.append(ScoredKeyword(
                        keyword=kw_text,
                        pillar=sk.get("pillar", "").lower(),
                        source="site_crawl",
                        keyword_type="supporting",
                        pillar_tier="",
                        intent=sk.get("intent", "informational"),
                        page_url=pages[0].url if pages else "",
                        page_type=page_type,
                        ai_reasoning=sk.get("why_good", ""),
                    ))
        else:
            keywords.extend(self._rule_based_extract(pages, pillars, page_type))

        return keywords

    def _rule_based_extract(self, pages: List[CrawledPage],
                            pillars: List[str],
                            page_type: str,
                            profile: BusinessProfile = None) -> List[ScoredKeyword]:
        """Comprehensive rule-based keyword extraction — NO AI needed.

        Extracts from: page titles, headings, product names, meta descriptions,
        body text n-grams.  Assigns tier based on page_type:
          - product pages  → Tier 1 pillars (score 100)
          - homepage/about/category → Tier 2 thematic pillars (score 50)
          - blog/other → supporting keywords
        """
        keywords = []
        pillar_lower = [p.lower().strip() for p in pillars if p.strip()]

        for page in pages:
            url = page.url

            # ── 1. PRODUCT NAMES → Tier 1 pillar keywords ──────────────────
            for prod in page.products_found:
                prod_stripped = prod.strip()
                if len(prod_stripped) < 4 or self._is_noise_text(prod_stripped):
                    continue
                core_info = _extract_core_pillar(prod_stripped, pillars)
                core = core_info["core_pillar"]
                if core and len(core) > 2:
                    keywords.append(ScoredKeyword(
                        keyword=core.lower(),
                        pillar=self._match_pillar(core.lower(), pillar_lower) or core.lower(),
                        source="site_crawl",
                        keyword_type="pillar",
                        pillar_tier="product",
                        intent="purchase",
                        page_url=url,
                        page_type=page_type,
                        relevance_score=100.0,
                        business_fit_score=100.0,
                        purchase_intent_score=100.0,
                        final_score=100.0,
                        is_good=True,
                        ai_reasoning="Core product extracted from product listing",
                    ))
                    # Also generate supporting from full product name
                    full_clean = re.sub(r'[^a-z0-9\s]', ' ', prod_stripped.lower()).strip()
                    full_clean = re.sub(r'\s+', ' ', full_clean)
                    if full_clean != core.lower() and 2 <= len(full_clean.split()) <= 6:
                        keywords.append(ScoredKeyword(
                            keyword=full_clean,
                            pillar=core.lower(),
                            source="site_crawl",
                            keyword_type="supporting",
                            intent="purchase",
                            page_url=url,
                            page_type=page_type,
                            ai_reasoning="Product name variant",
                        ))

            # ── 2. PAGE TITLE → pillar or thematic keywords ─────────────────
            if page.title:
                title_parts = re.split(r'\s*[—–|·:]\s*', page.title)
                for part in title_parts:
                    clean = re.sub(r'[^a-z0-9\s]', ' ', part.lower()).strip()
                    clean = re.sub(r'\s+', ' ', clean)
                    words = clean.split()
                    if len(clean) < 4 or len(words) > 8:
                        continue
                    if self._is_noise_text(clean):
                        continue
                    # Check if it relates to a pillar
                    matched_pillar = self._match_pillar(clean, pillar_lower)
                    if matched_pillar and 2 <= len(words) <= 6:
                        kw_type = "pillar" if page_type in ("homepage", "about", "category") else "supporting"
                        tier = "thematic" if kw_type == "pillar" else ""
                        score = 50.0 if kw_type == "pillar" else 0.0
                        keywords.append(ScoredKeyword(
                            keyword=clean,
                            pillar=matched_pillar,
                            source="site_crawl",
                            keyword_type=kw_type,
                            pillar_tier=tier,
                            intent="purchase" if any(w in clean for w in ["buy", "online", "price", "shop"]) else "research",
                            page_url=url,
                            page_type=page_type,
                            relevance_score=score,
                            final_score=score,
                            is_good=kw_type == "pillar",
                            ai_reasoning=f"Extracted from page title",
                        ))

            # ── 3. HEADINGS (H1-H6) → keywords ─────────────────────────────
            for heading in page.headings:
                h_clean = re.sub(r'[^a-z0-9\s]', ' ', heading.lower()).strip()
                h_clean = re.sub(r'\s+', ' ', h_clean)
                words = h_clean.split()
                if len(h_clean) < 4 or not (2 <= len(words) <= 7):
                    continue
                if self._is_noise_text(h_clean):
                    continue
                matched_pillar = self._match_pillar(h_clean, pillar_lower)
                if matched_pillar:
                    keywords.append(ScoredKeyword(
                        keyword=h_clean,
                        pillar=matched_pillar,
                        source="site_crawl",
                        keyword_type="supporting",
                        intent="informational",
                        page_url=url,
                        page_type=page_type,
                        ai_reasoning="Extracted from heading",
                    ))
                elif page_type in ("product", "category") and len(words) <= 3:
                    # Short headings on product/category pages may be new pillars
                    if not all(w in self.JUNK_WORDS for w in words):
                        keywords.append(ScoredKeyword(
                            keyword=h_clean,
                            pillar=h_clean,
                            source="site_crawl",
                            keyword_type="pillar",
                            pillar_tier="thematic",
                            intent="research",
                            page_url=url,
                            page_type=page_type,
                            relevance_score=30.0,
                            final_score=30.0,
                            ai_reasoning="Short heading on product/category page",
                        ))

            # ── 4. META DESCRIPTION → supporting keywords ──────────────────
            if page.meta_description:
                meta_clean = re.sub(r'[^a-z0-9\s]', ' ', page.meta_description.lower()).strip()
                meta_clean = re.sub(r'\s+', ' ', meta_clean)
                # Extract 2-4 word n-grams containing pillars
                meta_words = meta_clean.split()
                for n in range(2, 5):
                    for i in range(len(meta_words) - n + 1):
                        ngram = " ".join(meta_words[i:i + n])
                        matched_pillar = self._match_pillar(ngram, pillar_lower)
                        if matched_pillar and not self._is_noise_text(ngram):
                            keywords.append(ScoredKeyword(
                                keyword=ngram,
                                pillar=matched_pillar,
                                source="site_crawl",
                                keyword_type="supporting",
                                intent="informational",
                                page_url=url,
                                page_type=page_type,
                                ai_reasoning="Extracted from meta description",
                            ))

            # ── 5. BODY TEXT N-GRAMS → supporting keywords ──────────────────
            if page.body_text:
                body_clean = re.sub(r'[^a-z0-9\s]', ' ', page.body_text[:2000].lower())
                body_clean = re.sub(r'\s+', ' ', body_clean).strip()
                body_words = body_clean.split()
                seen_ngrams = set()
                for n in range(2, 5):
                    for i in range(len(body_words) - n + 1):
                        ngram = " ".join(body_words[i:i + n])
                        if ngram in seen_ngrams:
                            continue
                        matched_pillar = self._match_pillar(ngram, pillar_lower)
                        if matched_pillar and not self._is_noise_text(ngram):
                            seen_ngrams.add(ngram)
                            keywords.append(ScoredKeyword(
                                keyword=ngram,
                                pillar=matched_pillar,
                                source="site_crawl",
                                keyword_type="supporting",
                                intent="informational",
                                page_url=url,
                                page_type=page_type,
                                ai_reasoning="Extracted from body text",
                            ))

            # ── 6. GENERATE COMMON LONG-TAIL PATTERNS ───────────────────────
            intent_templates = [
                ("buy {p} online", "purchase"),
                ("{p} price", "purchase"),
                ("best {p}", "research"),
                ("{p} benefits", "informational"),
                ("organic {p}", "purchase"),
            ]
            for pillar in pillar_lower:
                for template, intent in intent_templates:
                    kw = template.format(p=pillar)
                    keywords.append(ScoredKeyword(
                        keyword=kw,
                        pillar=pillar,
                        source="site_crawl",
                        keyword_type="supporting",
                        intent=intent,
                        page_url=url,
                        page_type=page_type,
                        ai_reasoning="Generated long-tail pattern",
                    ))

        # ── 7. PROFILE-BASED pillar generation ──────────────────────────────
        if profile and profile.primary_products:
            for prod in profile.primary_products[:20]:
                core_info = _extract_core_pillar(prod, pillars)
                core = core_info["core_pillar"]
                if core and len(core) > 2 and core.lower() not in pillar_lower:
                    keywords.append(ScoredKeyword(
                        keyword=core.lower(),
                        pillar=core.lower(),
                        source="site_crawl",
                        keyword_type="pillar",
                        pillar_tier="product",
                        intent="purchase",
                        page_url=pages[0].url if pages else "",
                        page_type=page_type,
                        relevance_score=80.0,
                        business_fit_score=80.0,
                        final_score=80.0,
                        is_good=True,
                        ai_reasoning="Discovered from business profile products",
                    ))

        return keywords

    # Navigation / site chrome patterns for noise detection
    _NOISE_PHRASES = {
        "add to cart", "shopping cart", "view cart", "checkout",
        "free shipping", "shipping policy", "refund policy",
        "terms of service", "privacy policy", "cookie policy",
        "subscribe", "newsletter", "sign up", "log in", "login",
        "sold out", "out of stock", "coming soon",
        "skip to content", "menu", "navigation", "search",
        "footer", "header", "sidebar", "copyright",
        "powered by", "all rights reserved",
    }

    def _is_noise_text(self, text: str) -> bool:
        """Check if text is website chrome / noise."""
        tl = text.lower().strip()
        if len(tl) < 4:
            return True
        return any(noise in tl for noise in self._NOISE_PHRASES)

    def _match_pillar(self, keyword: str, pillars: List[str]) -> str:
        """Find which pillar a keyword belongs to."""
        kl = keyword.lower()
        for p in pillars:
            if p.lower() in kl:
                return p.lower()
        return ""

    def _deduplicate(self, keywords: List[ScoredKeyword]) -> List[ScoredKeyword]:
        """Deduplicate keywords, keeping the one with highest relevance.
        For pillar keywords, also dedup by core term so 'Kerala Cardamom 8mm'
        and 'cardamom' don't both appear as separate pillars."""
        best: Dict[str, ScoredKeyword] = {}
        for kw in keywords:
            key = re.sub(r'\s+', ' ', kw.keyword.lower().strip())
            if not key:
                continue
            if key not in best or kw.relevance_score > best[key].relevance_score:
                best[key] = kw

        # Second pass: collapse pillar keywords to their core terms
        # e.g. "kerala cardamom 8mm fruit" and "cardamom" → keep "cardamom"
        pillar_keys = [k for k, v in best.items() if v.keyword_type == "pillar"]
        cores_seen: Dict[str, str] = {}  # core_term → best_key
        to_remove = []
        for key in pillar_keys:
            core_info = _extract_core_pillar(key, pillar_keys)
            core = core_info["core_pillar"].lower().strip()
            if core in cores_seen:
                existing_key = cores_seen[core]
                # Keep the shorter / cleaner one
                if len(key) <= len(existing_key):
                    to_remove.append(existing_key)
                    cores_seen[core] = key
                else:
                    to_remove.append(key)
            else:
                cores_seen[core] = key
        for k in to_remove:
            best.pop(k, None)

        return list(best.values())


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5 — AI KEYWORD CLASSIFIER & SCORER
# ─────────────────────────────────────────────────────────────────────────────

class AIKeywordClassifier:
    """
    Uses AI to classify keywords as good vs bad, and score them
    for purchase intent and ranking potential.

    Mission: Rank top 5 supporting keywords per pillar.
    Each scored on: purchase intent, search volume, relevance, feasibility.
    """

    # Intent weights for final scoring
    INTENT_WEIGHTS = {
        "purchase": 100,
        "research": 75,  # "best cardamom brand" - researching before buying
        "comparison": 70,
        "local": 65,
        "informational": 40,
    }

    def classify_and_score(self, keywords: List[ScoredKeyword],
                           pillars: List[str],
                           business_profile: BusinessProfile = None,
                           batch_size: int = 30) -> List[ScoredKeyword]:
        """
        Classify all keywords using AI:
        1. Good vs Bad (is this a real searchable keyword?)
        2. Intent classification (purchase/research/informational/comparison/local)
        3. Scoring on 5 dimensions
        
        Each batch has a 60s timeout — if AI fails or hangs, uses rule-based fallback.
        """
        import concurrent.futures
        scored = []

        # Process in batches to manage AI token limits
        total_batches = (len(keywords) + batch_size - 1) // batch_size
        for batch_idx, i in enumerate(range(0, len(keywords), batch_size)):
            batch = keywords[i:i + batch_size]
            batch_num = batch_idx + 1
            log.info(f"[AIClassify] Scoring batch {batch_num}/{total_batches} ({len(batch)} keywords)")
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(self._score_batch, batch, pillars, business_profile)
                    batch_scored = future.result(timeout=60)
                scored.extend(batch_scored)
            except concurrent.futures.TimeoutError:
                log.warning(f"[AIClassify] Batch {batch_num}/{total_batches} timed out after 60s — using rule-based fallback")
                for kw in batch:
                    kw = self._rule_based_score(kw, pillars)
                    kw.final_score = self._compute_final_score(kw)
                    kw.ai_reasoning = "rule-based (AI timeout)"
                    scored.append(kw)
            except Exception as e:
                log.warning(f"[AIClassify] Batch {batch_num}/{total_batches} failed: {e} — using rule-based fallback")
                for kw in batch:
                    kw = self._rule_based_score(kw, pillars)
                    kw.final_score = self._compute_final_score(kw)
                    kw.ai_reasoning = f"rule-based ({type(e).__name__})"
                    scored.append(kw)
            if i + batch_size < len(keywords):
                time.sleep(AI_RATE_LIMIT)

        # Sort by final score
        scored.sort(key=lambda k: k.final_score, reverse=True)

        good_count = sum(1 for k in scored if k.is_good)
        log.info(f"[AIClassify] Scored {len(scored)} keywords, "
                 f"{good_count} good, {len(scored) - good_count} bad")
        return scored

    def _score_batch(self, keywords: List[ScoredKeyword],
                     pillars: List[str],
                     profile: BusinessProfile = None) -> List[ScoredKeyword]:
        """Score a batch of keywords using AI."""
        kw_list = [
            {"keyword": kw.keyword, "pillar": kw.pillar, "current_intent": kw.intent}
            for kw in keywords
        ]

        business_context = ""
        if profile:
            business_context = (
                f"Business: {profile.business_name} ({profile.business_type})\n"
                f"Products: {', '.join(profile.primary_products[:10])}\n"
                f"Target Market: {profile.target_audience}\n"
                f"USP: {profile.usp}\n"
            )

        prompt = f"""Score these SEO keywords for an ecommerce business.

{business_context}
PILLAR KEYWORDS: {json.dumps(pillars)}

KEYWORDS TO SCORE:
{json.dumps(kw_list, indent=1)}

For EACH keyword, evaluate:

1. is_good (true/false): Is this a real keyword someone would search? 
   BAD examples: "the cardamom", "cardamom cardamom", random phrases, navigation text
   GOOD examples: "buy cardamom online", "cardamom price per kg", "organic cardamom benefits"

2. intent: "purchase" | "research" | "informational" | "comparison" | "local"
   - purchase: "buy X", "X price", "X online", "X wholesale" (ready to buy)
   - research: "best X", "X reviews", "top X brand" (comparing before buying)
   - comparison: "X vs Y", "X or Y"
   - local: "X near me", "X in Kerala"
   - informational: "X benefits", "how to use X", "what is X" (just learning)

3. purchase_intent (0-100): How likely is the searcher to buy?
   100 = "buy cardamom 1kg online" (immediate purchase)
   75 = "best cardamom brand India" (researching to buy)
   40 = "cardamom health benefits" (informational, may buy later)
   10 = "what is cardamom" (pure information)

4. relevance (0-100): How relevant to the business products?

5. ranking_feasibility (0-100): How easy to rank for?
   Long-tail (4+ words) = easier = higher score
   Short (1-2 words) = harder = lower score
   Very competitive head terms = low score

6. business_fit (0-100): Does this keyword match the business USP/products?

Return JSON array:
[
  {{
    "keyword": "...",
    "is_good": true,
    "intent": "purchase",
    "purchase_intent": 85,
    "relevance": 90,
    "ranking_feasibility": 70,
    "business_fit": 95,
    "reason": "brief reason"
  }}
]

Return ONLY valid JSON array."""

        result = AICaller.call(prompt, temperature=0.1)
        parsed = AICaller.extract_json(result)

        if parsed and isinstance(parsed, list):
            scored_map = {item["keyword"].lower(): item for item in parsed if "keyword" in item}
        else:
            scored_map = {}
            log.warning("[AIClassify] AI scoring returned unparseable result, using rule-based")

        scored_keywords = []
        for kw in keywords:
            # ── Pillar tier scores are fixed — do NOT let classifier override them ──
            if kw.keyword_type == "pillar" and kw.pillar_tier == "product":
                # Tier 1: confirmed product from product page → score locked at 100
                kw.final_score = 100.0
                kw.is_good = True
                scored_keywords.append(kw)
                continue
            if kw.keyword_type == "pillar" and kw.pillar_tier == "thematic":
                # Tier 2: thematic category keyword → score locked at 50
                kw.final_score = 50.0
                kw.is_good = True
                scored_keywords.append(kw)
                continue

            ai_data = scored_map.get(kw.keyword.lower(), {})

            if ai_data:
                kw.is_good = ai_data.get("is_good", True)
                kw.intent = ai_data.get("intent", kw.intent)
                kw.purchase_intent_score = float(ai_data.get("purchase_intent", 50))
                kw.relevance_score = float(ai_data.get("relevance", 60))
                kw.ranking_feasibility = float(ai_data.get("ranking_feasibility", 50))
                kw.business_fit_score = float(ai_data.get("business_fit", 60))
                kw.ai_reasoning = ai_data.get("reason", "")
            else:
                # Rule-based fallback scoring
                kw = self._rule_based_score(kw, pillars)

            # Calculate final score
            kw.final_score = self._compute_final_score(kw)
            scored_keywords.append(kw)

        return scored_keywords

    def _rule_based_score(self, kw: ScoredKeyword, pillars: List[str]) -> ScoredKeyword:
        """Fallback scoring when AI is unavailable."""
        keyword = kw.keyword.lower()

        # Purchase intent
        PURCHASE_SIGNALS = ["buy", "price", "cost", "order", "shop", "online",
                            "wholesale", "bulk", "supplier", "delivery", "near me"]
        RESEARCH_SIGNALS = ["best", "top", "review", "compare", "vs", "brand"]
        INFO_SIGNALS = ["benefit", "use", "how", "what", "why", "recipe",
                        "health", "property", "nutrition"]

        if any(s in keyword for s in PURCHASE_SIGNALS):
            kw.purchase_intent_score = 85
            kw.intent = "purchase"
        elif any(s in keyword for s in RESEARCH_SIGNALS):
            kw.purchase_intent_score = 65
            kw.intent = "research"
        elif any(s in keyword for s in INFO_SIGNALS):
            kw.purchase_intent_score = 30
            kw.intent = "informational"
        else:
            kw.purchase_intent_score = 50
            kw.intent = "research"

        # Relevance: does it contain a pillar?
        has_pillar = any(p.lower() in keyword for p in pillars)
        kw.relevance_score = 90 if has_pillar else 40

        # Ranking feasibility: longer = easier
        word_count = len(keyword.split())
        if word_count >= 4:
            kw.ranking_feasibility = 80
        elif word_count == 3:
            kw.ranking_feasibility = 65
        elif word_count == 2:
            kw.ranking_feasibility = 50
        else:
            kw.ranking_feasibility = 30

        # Business fit
        kw.business_fit_score = 80 if has_pillar else 40

        kw.is_good = has_pillar and word_count >= 2
        return kw

    def _compute_final_score(self, kw: ScoredKeyword) -> float:
        """
        Weighted final score.
        Mission: Top 5 per pillar should be best to rank + highest purchase intent.
        """
        score = (
            kw.purchase_intent_score * 0.30 +
            kw.relevance_score * 0.25 +
            kw.business_fit_score * 0.20 +
            kw.ranking_feasibility * 0.15 +
            kw.search_volume_signal * 0.10
        )
        return round(min(100, max(0, score)), 2)

    def get_top_supporting(self, scored_keywords: List[ScoredKeyword],
                           per_pillar: int = 5) -> Dict[str, List[ScoredKeyword]]:
        """
        Get top N supporting keywords per pillar.
        These are the BEST keywords to target for ranking.
        """
        # Filter to good supporting keywords only
        supporting = [kw for kw in scored_keywords
                      if kw.is_good and kw.keyword_type == "supporting"]

        # Group by pillar
        by_pillar: Dict[str, List[ScoredKeyword]] = {}
        for kw in supporting:
            if kw.pillar:
                by_pillar.setdefault(kw.pillar, []).append(kw)

        # Sort each pillar group and take top N
        top = {}
        for pillar, kws in by_pillar.items():
            kws.sort(key=lambda k: k.final_score, reverse=True)
            top[pillar] = kws[:per_pillar]

        return top


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6 — SMART COMPETITOR ANALYZER
# ─────────────────────────────────────────────────────────────────────────────

class SmartCompetitorAnalyzer:
    """
    Focused competitor analysis:
    - DO NOT crawl all competitor product pages (they may have products we don't sell)
    - DO crawl: homepage, blogs with our pillar keywords, product pages matching our pillars
    - Focus: what content do they have for OUR pillar keywords that we don't?
    """

    def analyze_competitor(self, competitor_url: str,
                           our_pillars: List[str],
                           max_pages: int = 20) -> List[ScoredKeyword]:
        """
        Crawl competitor with pillar-focused filtering.
        Only extracts keywords relevant to OUR business pillars.
        """
        if not competitor_url.startswith("http"):
            competitor_url = f"https://{competitor_url}"

        crawler = IntelligentSiteCrawler()
        domain = f"{urlparse(competitor_url).scheme}://{urlparse(competitor_url).netloc}"
        log.info(f"[CompAnalyze] Analyzing {domain} for pillars: {our_pillars}")

        # Phase 1: Discover URLs
        all_urls = crawler._discover_urls(competitor_url, domain)

        # Phase 2: Filter URLs to only relevant ones
        relevant_urls = self._filter_relevant_urls(all_urls, our_pillars, domain,
                                                    competitor_url)
        log.info(f"[CompAnalyze] {len(relevant_urls)} relevant URLs "
                 f"(from {len(all_urls)} total)")

        # Phase 3: Crawl relevant pages only
        pages = []
        for url, page_type in relevant_urls[:max_pages]:
            page = crawler._crawl_page(url, page_type)
            if page:
                pages.append(page)
            time.sleep(CRAWL_DELAY)

        if not pages:
            log.warning(f"[CompAnalyze] No pages crawled from {domain}")
            return []

        # Phase 4: AI extraction focused on our pillars
        extractor = AIKeywordExtractor()
        keywords = extractor.extract_from_pages(pages, our_pillars)

        # Tag source as competitor
        for kw in keywords:
            kw.source = f"competitor:{urlparse(competitor_url).netloc}"

        log.info(f"[CompAnalyze] Extracted {len(keywords)} keywords from {domain}")
        return keywords

    def _filter_relevant_urls(self, urls: List[str], pillars: List[str],
                              domain: str, homepage: str) -> List[Tuple[str, str]]:
        """
        Filter competitor URLs to only those relevant to our pillars.
        Always include: homepage, about page
        Include if matches pillar: product pages, blog pages, category pages
        Skip: pages about products we don't sell
        """
        relevant = []
        crawler = IntelligentSiteCrawler()
        pillar_lower = [p.lower() for p in pillars]

        for url in urls:
            parsed = urlparse(url)
            path = parsed.path.lower()
            path_words = re.sub(r'[^a-z0-9\s]', ' ', path).split()

            # Always include homepage
            if not parsed.path or parsed.path == "/":
                relevant.append((url, "homepage"))
                continue

            # Always include about page
            if crawler.ABOUT_PATTERNS.search(path):
                relevant.append((url, "about"))
                continue

            # Blog pages: include if URL or path contains any pillar word
            if crawler.BLOG_PATTERNS.search(path):
                if any(p in path for p in pillar_lower):
                    relevant.append((url, "blog"))
                elif len(relevant) < 5:
                    # Include a few generic blogs for content strategy intel
                    relevant.append((url, "blog"))
                continue

            # Product/category pages: include ONLY if URL contains pillar word
            if (crawler.PRODUCT_PATTERNS.search(path) or
                    crawler.CATEGORY_PATTERNS.search(path)):
                if any(p in path for p in pillar_lower):
                    relevant.append((url, "product"))
                continue

            # Other short-path pages: check for pillar words
            if any(p in " ".join(path_words) for p in pillar_lower):
                relevant.append((url, "other"))

        return relevant


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 7 — GOOGLE SUGGEST KEYWORD ENRICHER
# ─────────────────────────────────────────────────────────────────────────────

class GoogleSuggestEnricher:
    """
    Enrich keywords using Google Autocomplete suggestions.
    Better signal than raw volume for finding real search queries.
    """

    def enrich(self, pillars: List[str],
               existing_keywords: List[str] = None) -> List[ScoredKeyword]:
        """
        For each pillar, query Google Suggest with various prefixes
        to discover real search queries people type.
        """
        existing = set((kw.lower() for kw in existing_keywords) if existing_keywords else [])
        new_keywords = []

        for pillar in pillars:
            suggestions = self._get_all_suggestions(pillar)
            for suggestion in suggestions:
                if suggestion.lower() not in existing:
                    existing.add(suggestion.lower())
                    new_keywords.append(ScoredKeyword(
                        keyword=suggestion.lower(),
                        pillar=pillar.lower(),
                        source="google_suggest",
                        keyword_type="supporting",
                        intent=self._infer_intent(suggestion),
                        search_volume_signal=70,  # appears in suggest = has volume
                    ))
            time.sleep(0.2)  # rate limit

        log.info(f"[GSuggest] Found {len(new_keywords)} new suggestions for {len(pillars)} pillars")
        return new_keywords

    def _get_all_suggestions(self, pillar: str) -> List[str]:
        """Get suggestions with various query patterns."""
        suggestions = set()

        # Direct query
        suggestions.update(self._query(pillar))

        # With common prefixes
        for prefix in ["buy ", "best ", "organic ", "price of ", "how to use "]:
            suggestions.update(self._query(f"{prefix}{pillar}"))

        # With alphabet expansion (a-h after pillar — trimmed for speed)
        for letter in "abcdefgh":
            results = self._query(f"{pillar} {letter}")
            suggestions.update(results)
            if not results:
                break  # stop if no results for this prefix pattern
            time.sleep(0.1)

        return list(suggestions)

    def _query(self, query: str) -> List[str]:
        """Query Google Autocomplete API."""
        try:
            r = _req.get(
                "https://suggestqueries.google.com/complete/search",
                params={"client": "firefox", "q": query},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=5,
            )
            if r.ok:
                data = r.json()
                if len(data) > 1 and isinstance(data[1], list):
                    return [s for s in data[1] if isinstance(s, str)]
        except Exception:
            pass
        return []

    def _infer_intent(self, keyword: str) -> str:
        kl = keyword.lower()
        if any(s in kl for s in ["buy", "price", "cost", "order", "shop", "online",
                                  "wholesale", "bulk", "delivery", "near me"]):
            return "purchase"
        if any(s in kl for s in ["best", "top", "review", "vs", "compare"]):
            return "research"
        if any(s in kl for s in ["benefit", "use", "how", "what", "why", "recipe",
                                  "health"]):
            return "informational"
        return "research"


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 8 — PRODUCT NAME → CORE PILLAR NORMALIZER
# ─────────────────────────────────────────────────────────────────────────────

# Words that are modifiers, not core product names
_GEO_WORDS = {
    "kerala", "india", "indian", "srilanka", "sri", "lanka", "karnataka",
    "tamilnadu", "assam", "darjeeling", "nilgiri", "wayanad", "idukki",
    "coorg", "ooty", "mysore", "malabar", "adimali", "south", "north",
}
_QUALITY_WORDS = {
    "organic", "pure", "natural", "fresh", "best", "top", "finest",
    "authentic", "raw", "whole", "ground", "powder", "paste", "extract",
    "oil", "seeds", "leaves", "bark", "dried", "handpicked", "selected",
    "premium", "wild", "cold", "pressed", "certified", "aromatic",
    "fruit", "bulb", "root", "flower", "pod", "herb", "spice", "grade",
    "bold", "extra", "medium", "small", "large", "true",
}
_SIZE_PAT = re.compile(
    r'^\d+\s*(mm|cm|g|gm|grams?|kg|ml|l|oz|lbs?|pcs?|pieces?|units?)$', re.I
)
_NOISE_WORDS = {
    "free", "delivery", "offer", "sale", "pack", "combo", "set", "kit",
    "copy", "new", "special", "limited", "edition", "in", "of", "the",
    "and", "for", "with", "from", "per", "a", "an",
    "gm", "gms", "g", "kg", "ml", "mm", "cm", "oz", "lbs",
}


def _extract_core_pillar(product_name: str, known_pillars: List[str] = None) -> dict:
    """
    Extract the core pillar keyword from a full product name.
    "Kerala Cardamom 8mm Fruit - 100gm" → {"core_pillar": "cardamom", "modifiers": ["kerala","8mm","fruit","100gm"]}
    "Aromatic True Cinnamon (Ceylon) — 100g" → {"core_pillar": "cinnamon", "modifiers": ["aromatic","true","ceylon","100g"]}
    """
    known_pillars = known_pillars or []
    name_lower = product_name.lower().strip()

    # Step 1: Check if any known pillar is in the name
    for bp in sorted(known_pillars, key=len, reverse=True):
        if bp.lower() in name_lower:
            return {
                "core_pillar": bp.lower(),
                "modifiers": _get_modifiers(product_name, bp.lower()),
                "original": product_name,
            }

    # Step 2: Tokenize and find the core noun
    tokens = [t.strip().lower() for t in re.split(r'[\s\-/|,&()—–]+', product_name)
              if t.strip() and len(t.strip()) > 1]

    core = None
    modifiers = []
    for t in tokens:
        if (t in _GEO_WORDS or t in _QUALITY_WORDS or t in _NOISE_WORDS or
                _SIZE_PAT.match(t) or t.isdigit()):
            modifiers.append(t)
        elif core is None:
            core = t
        else:
            # Could be part of compound name: "black pepper" → keep both
            if not core:
                core = t
            else:
                # Check if this extends the core (e.g., "black pepper")
                compound = f"{core} {t}"
                if t not in _GEO_WORDS and t not in _QUALITY_WORDS and not _SIZE_PAT.match(t):
                    core = compound
                else:
                    modifiers.append(t)

    return {
        "core_pillar": core or name_lower,
        "modifiers": modifiers,
        "original": product_name,
    }


def _get_modifiers(product_name: str, pillar: str) -> List[str]:
    """Extract modifier words (everything that's not the pillar word)."""
    tokens = [t.strip().lower() for t in re.split(r'[\s\-/|,&()—–]+', product_name)
              if t.strip() and len(t.strip()) > 1]
    return [t for t in tokens if t != pillar and t not in {"and", "the", "for"}]


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 9 — MAIN ORCHESTRATOR
# ─────────────────────────────────────────────────────────────────────────────

class IntelligentKeywordDiscovery:
    """
    Main orchestrator for the improved keyword discovery workflow.

    FLOW:
    1. crawl_customer_site() → deep crawl + AI business analysis + keyword extraction
    2. User confirms pillars
    3. crawl_competitors() → focused competitor analysis for confirmed pillars
    4. score_all_keywords() → AI classification + scoring
    5. get_top_keywords() → top 5 per pillar for ranking
    """

    def __init__(self):
        self.crawler = IntelligentSiteCrawler()
        self.analyzer = AIBusinessAnalyzer()
        self.extractor = AIKeywordExtractor()
        self.classifier = AIKeywordClassifier()
        self.competitor_analyzer = SmartCompetitorAnalyzer()
        self.suggest_enricher = GoogleSuggestEnricher()

    def crawl_customer_site(self, url: str,
                            user_pillars: List[str] = None,
                            max_pages: int = 30) -> dict:
        """
        Phase 1: Crawl customer site, analyze business, extract keywords.

        Returns:
        {
            "business_profile": BusinessProfile,
            "pillar_keywords": [ScoredKeyword],
            "supporting_keywords": [ScoredKeyword],
            "pages_crawled": int,
            "page_breakdown": {type: count},
            "suggested_new_pillars": [str],
        }
        """
        user_pillars = user_pillars or []
        log.info(f"[Discovery] Phase 1: Crawling {url} with pillars={user_pillars}")

        # Step 1: Intelligent crawl
        pages = self.crawler.crawl_site(url, max_pages=max_pages)
        if not pages:
            return {"error": "Could not crawl site", "pages_crawled": 0}

        # Step 2: Rule-based business analysis (no AI during crawl)
        context = self.analyzer._build_context(pages)
        profile = self.analyzer._fallback_profile(pages, context)
        log.info(f"[Discovery] Business: {profile.business_name}, "
                 f"Products: {profile.primary_products[:5]}")

        # Step 3: Normalize product names → core pillar keywords
        # "Kerala Cardamom 8mm Fruit - 100gm" → pillar="cardamom"
        core_pillars = set(p.lower() for p in user_pillars)
        suggested_new_pillars = []
        for product in profile.primary_products:
            cls = _extract_core_pillar(product, user_pillars)
            core = cls["core_pillar"]
            if core and core not in core_pillars:
                core_pillars.add(core)
                suggested_new_pillars.append(core)
            # Add modifiers as supporting keyword candidates
            for mod in cls["modifiers"]:
                if mod not in core_pillars and len(mod) > 2:
                    pass  # modifiers feed into supporting keywords via extraction

        all_pillars_for_extraction = list(core_pillars)

        # Step 4: AI keyword extraction from all pages
        keywords = self.extractor.extract_from_pages(
            pages, all_pillars_for_extraction, profile
        )

        # NOTE: Google Suggest enrichment moved to Stage 3 (Discover Keywords)
        # NOTE: Scoring moved to Stage 4/5 (AI Validate / Rank)

        # Split into pillar and supporting
        pillar_kws = [kw for kw in keywords if kw.keyword_type == "pillar"]
        supporting_kws = [kw for kw in keywords if kw.keyword_type == "supporting"]

        page_breakdown = {}
        for p in pages:
            page_breakdown[p.page_type] = page_breakdown.get(p.page_type, 0) + 1

        return {
            "business_profile": profile,
            "pillar_keywords": pillar_kws,
            "supporting_keywords": supporting_kws,
            "pages_crawled": len(pages),
            "page_breakdown": page_breakdown,
            "suggested_new_pillars": suggested_new_pillars,
            "all_keywords": keywords,
        }

    def crawl_competitors(self, competitor_urls: List[str],
                          confirmed_pillars: List[str],
                          max_pages_per: int = 15) -> dict:
        """
        Phase 2: Focused competitor crawl using confirmed pillars.

        Only crawls competitor pages relevant to our pillars:
        - Homepage (always)
        - Blog posts containing our pillar words
        - Product pages matching our pillar words
        - Skips competitor products we don't sell
        """
        log.info(f"[Discovery] Phase 2: Analyzing {len(competitor_urls)} competitors "
                 f"for pillars={confirmed_pillars}")

        all_comp_keywords = []
        competitor_insights = []

        for comp_url in competitor_urls[:5]:
            try:
                kws = self.competitor_analyzer.analyze_competitor(
                    comp_url, confirmed_pillars, max_pages_per
                )
                all_comp_keywords.extend(kws)
                competitor_insights.append({
                    "url": comp_url,
                    "keywords_found": len(kws),
                    "pillar_coverage": list(set(kw.pillar for kw in kws if kw.pillar)),
                })
            except Exception as e:
                log.warning(f"[Discovery] Competitor {comp_url} failed: {e}")
                competitor_insights.append({
                    "url": comp_url,
                    "keywords_found": 0,
                    "error": str(e)[:100],
                })

        return {
            "competitor_keywords": all_comp_keywords,
            "competitor_insights": competitor_insights,
            "total_keywords": len(all_comp_keywords),
        }

    def score_all_keywords(self, all_keywords: List[ScoredKeyword],
                           pillars: List[str],
                           business_profile: BusinessProfile = None) -> List[ScoredKeyword]:
        """
        Phase 3: AI classification and scoring of all keywords.
        Classifies good vs bad, scores for purchase intent and ranking potential.
        """
        log.info(f"[Discovery] Phase 3: Scoring {len(all_keywords)} keywords")
        return self.classifier.classify_and_score(
            all_keywords, pillars, business_profile
        )

    def get_top_keywords(self, scored_keywords: List[ScoredKeyword],
                         per_pillar: int = 5) -> Dict[str, List[dict]]:
        """
        Phase 4: Get top N supporting keywords per pillar, formatted for frontend.

        Each keyword scored on:
        - Purchase intent (0-100)
        - Relevance to pillar (0-100)
        - Ranking feasibility (0-100)
        - Business fit (0-100)
        - Final composite score (0-100)
        """
        top_per_pillar = self.classifier.get_top_supporting(scored_keywords, per_pillar)

        # Format for API response
        result = {}
        for pillar, kws in top_per_pillar.items():
            result[pillar] = [{
                "keyword": kw.keyword,
                "intent": kw.intent,
                "purchase_intent_score": kw.purchase_intent_score,
                "relevance_score": kw.relevance_score,
                "ranking_feasibility": kw.ranking_feasibility,
                "business_fit_score": kw.business_fit_score,
                "final_score": kw.final_score,
                "source": kw.source,
                "ai_reasoning": kw.ai_reasoning,
            } for kw in kws]

        return result

    def full_discovery(self, customer_url: str,
                       competitor_urls: List[str],
                       user_pillars: List[str]) -> dict:
        """
        Run the complete discovery pipeline end-to-end.
        Useful for testing and batch processing.
        """
        # Phase 1: Customer site
        site_result = self.crawl_customer_site(customer_url, user_pillars)
        if "error" in site_result:
            return site_result

        # Combine user pillars with discovered ones
        all_pillars = list(set(
            user_pillars +
            [kw.keyword for kw in site_result["pillar_keywords"]] +
            site_result.get("suggested_new_pillars", [])
        ))

        # Phase 2: Competitors
        comp_result = self.crawl_competitors(competitor_urls, all_pillars)

        # Merge all keywords
        all_keywords = (
            site_result.get("all_keywords", []) +
            comp_result.get("competitor_keywords", [])
        )

        # Phase 3: Score
        scored = self.score_all_keywords(
            all_keywords, all_pillars, site_result.get("business_profile")
        )

        # Phase 4: Top keywords
        top = self.get_top_keywords(scored)

        return {
            "business_profile": site_result["business_profile"],
            "pages_crawled": site_result["pages_crawled"],
            "page_breakdown": site_result["page_breakdown"],
            "suggested_new_pillars": site_result["suggested_new_pillars"],
            "competitor_insights": comp_result["competitor_insights"],
            "total_keywords": len(scored),
            "good_keywords": sum(1 for k in scored if k.is_good),
            "bad_keywords": sum(1 for k in scored if not k.is_good),
            "top_keywords_per_pillar": top,
            "all_scored_keywords": scored,
        }
