"""
Negative Review Research Engine
================================
Researches common complaints, negative reviews, and issues reported by customers
for a given product/service keyword. For each complaint, generates a solution
positioning our product/service as the answer.

Integration:
  - Called from SEOContentPipeline._step1_research() after standard research
  - Results stored in self._complaint_signals = [{"complaint", "frequency", "solution", "cta_line"}]
  - Injected into blueprint prompts in _step2_structure() / _step6_draft()

Standalone usage:
  import asyncio
  from engines.negative_review_engine import NegativeReviewEngine
  engine = NegativeReviewEngine(keyword="kerala cardamom", business_context="organic spice farm")
  results = asyncio.run(engine.research())
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

CRAWL_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; AnnaSEO/2.0; +https://annaseo.pureleven.com)",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}
CRAWL_TIMEOUT = 12


@dataclass
class ComplaintSignal:
    """A single customer complaint and our solution positioning."""
    complaint: str             # The complaint e.g. "cardamom too small and pale"
    frequency: str             # "very common" | "common" | "occasional"
    source_hint: str           # Where this complaint was identified
    solution: str              # How our product solves it e.g. "we hand-select 8mm+ green pods"
    cta_line: str              # Short article hook sentence


@dataclass
class NegativeReviewResult:
    keyword: str
    signals: List[ComplaintSignal] = field(default_factory=list)
    raw_complaints: List[str] = field(default_factory=list)
    content_hooks: List[str] = field(default_factory=list)   # Ready-to-use sentences for article
    credibility_section: str = ""                            # Full HTML paragraph/block for article


class NegativeReviewEngine:
    """
    Researches customer complaints for a keyword and generates solution content.

    Usage inside SEOContentPipeline: inject via inject_into_pipeline()
    Usage standalone: NegativeReviewEngine(keyword, business_context, or_key).research()
    """

    # Review/complaint search patterns used to find relevant content
    _REVIEW_QUERIES = [
        "{keyword} problems complaints reviews",
        "{keyword} issues quality negative",
        "{keyword} customer complaints bad reviews",
        "{keyword} common problems amazon reddit",
    ]

    # Sites that commonly have genuine customer reviews
    _REVIEW_SITE_PATTERNS = [
        "amazon.in", "amazon.com", "flipkart.com", "reddit.com",
        "trustpilot.com", "consumerreports.org", "quora.com",
        "tripadvisor.com", "yelp.com", "google.com/maps",
    ]

    def __init__(
        self,
        keyword: str,
        business_context: str = "",
        or_key: str = "",
        or_model: str = "openai/gpt-oss-120b:free",   # free model by default (or_qwen)
        max_complaints: int = 8,
    ):
        self.keyword = keyword
        self.business_context = business_context
        self.or_key = or_key or os.getenv("OPENROUTER_API_KEY", "")
        self.or_model = or_model
        self.max_complaints = max_complaints

    # ──────────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────────

    async def research(self) -> NegativeReviewResult:
        """Full pipeline: crawl reviews → extract complaints → generate solutions."""
        result = NegativeReviewResult(keyword=self.keyword)

        # Step A: crawl review pages
        review_texts = await self._crawl_review_texts()

        # Step B: AI extract complaints from crawled text
        raw_complaints = await self._extract_complaints(review_texts)
        result.raw_complaints = raw_complaints

        if not raw_complaints:
            log.warning(f"[NegativeReview] No complaints found for '{self.keyword}', using AI-only")
            raw_complaints = await self._ai_only_complaints()
            result.raw_complaints = raw_complaints

        # Step C: Generate solutions for each complaint
        signals = await self._generate_solutions(raw_complaints[:self.max_complaints])
        result.signals = signals

        # Step D: Build ready-to-use content hooks
        result.content_hooks = self._build_hooks(signals)

        # Step E: Build a credibility paragraph for article injection
        result.credibility_section = self._build_credibility_section(signals)

        return result

    # ──────────────────────────────────────────────────────────────────────────
    # Crawl
    # ──────────────────────────────────────────────────────────────────────────

    async def _crawl_review_texts(self) -> str:
        """Crawl DDG search results for review/complaint content."""
        all_text_parts = []
        loop = asyncio.get_event_loop()

        query = self._REVIEW_QUERIES[0].format(keyword=self.keyword)
        urls = await loop.run_in_executor(None, self._ddg_search, query, 6)

        for url in urls[:5]:
            try:
                text = await loop.run_in_executor(None, self._crawl_page_text, url)
                if text and len(text) > 200:
                    all_text_parts.append(f"SOURCE: {url}\n{text[:1200]}")
            except Exception as e:
                log.debug(f"[NegativeReview] crawl failed {url}: {e}")
            await asyncio.sleep(0.3)

        return "\n\n---\n\n".join(all_text_parts)

    def _ddg_search(self, query: str, n: int = 6) -> List[str]:
        """DuckDuckGo HTML search — no API key required."""
        try:
            encoded = urllib.parse.quote_plus(query)
            url = f"https://html.duckduckgo.com/html/?q={encoded}"
            resp = requests.get(url, headers=CRAWL_HEADERS, timeout=CRAWL_TIMEOUT)
            soup = BeautifulSoup(resp.text, "html.parser")
            links = []
            for a in soup.select(".result__a")[:n * 2]:
                href = a.get("href", "")
                if href.startswith("http") and "duckduckgo.com" not in href:
                    links.append(href)
                    if len(links) >= n:
                        break
            return links
        except Exception as e:
            log.warning(f"[NegativeReview] DDG search failed: {e}")
            return []

    def _crawl_page_text(self, url: str) -> str:
        """Crawl a single page and extract relevant complaint text."""
        try:
            resp = requests.get(url, headers=CRAWL_HEADERS, timeout=CRAWL_TIMEOUT,
                                allow_redirects=True)
            if resp.status_code != 200:
                return ""
            soup = BeautifulSoup(resp.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()
            # Focus on review/comment sections
            review_containers = soup.find_all(
                lambda t: t.name in ("div", "section", "article") and
                any(cls in " ".join(t.get("class", [])).lower()
                    for cls in ("review", "comment", "rating", "feedback", "testimonial"))
            )
            if review_containers:
                text = " ".join(c.get_text(" ", strip=True) for c in review_containers[:10])
            else:
                # Fallback: all paragraphs
                paras = [p.get_text(strip=True) for p in soup.find_all("p")
                         if len(p.get_text(strip=True)) > 50]
                text = " ".join(paras[:20])
            return text[:2000]
        except Exception:
            return ""

    # ──────────────────────────────────────────────────────────────────────────
    # AI calls
    # ──────────────────────────────────────────────────────────────────────────

    async def _extract_complaints(self, crawled_text: str) -> List[str]:
        """Use AI to extract list of distinct customer complaints from crawled text."""
        if not crawled_text.strip():
            return []

        prompt = f"""You are analyzing customer reviews and complaints about "{self.keyword}".

Review text from multiple sources:
{crawled_text[:3000]}

Extract the TOP {self.max_complaints} most common customer complaints or negative issues mentioned.
Focus on specific, actionable complaints (size, quality, freshness, color, taste, smell, delivery, packaging, etc.)
Be specific — don't say "poor quality", say "uneven cardamom pod size" or "pale green color".

Return ONLY a JSON array of complaint strings:
["complaint 1", "complaint 2", ...]"""

        result = await self._call_or(prompt)
        if isinstance(result, list):
            return [str(c) for c in result if c]
        return []

    async def _ai_only_complaints(self) -> List[str]:
        """When crawl fails, use AI knowledge about typical complaints."""
        prompt = f"""Based on your knowledge of customer reviews and complaints about "{self.keyword}", 
list the {self.max_complaints} most commonly reported problems or negative experiences customers face.

{f'Business context: {self.business_context}' if self.business_context else ''}

Be very specific and realistic (e.g. for cardamom: "pods are smaller than expected", "color too pale/yellow", 
"no strong aroma", "high moisture content causes clumping", "chicory added without disclosure").

Return ONLY a JSON array:
["specific complaint 1", "specific complaint 2", ...]"""

        result = await self._call_or(prompt)
        if isinstance(result, list):
            return [str(c) for c in result if c]
        # Fallback generic
        return [
            f"Inconsistent quality in {self.keyword}",
            f"Freshness issues with {self.keyword}",
            f"Poor packaging for {self.keyword}",
            f"Size and color variation in {self.keyword}",
        ]

    async def _generate_solutions(self, complaints: List[str]) -> List[ComplaintSignal]:
        """For each complaint, generate a solution positioning our product as the answer."""
        if not complaints:
            return []

        complaints_text = "\n".join(f"{i+1}. {c}" for i, c in enumerate(complaints))
        context = f"Business context: {self.business_context}\n" if self.business_context else ""

        prompt = f"""You are writing content for a genuine, high-quality {self.keyword} seller.
{context}
Below are the most common customer complaints about {self.keyword} products in general.
For EACH complaint, write:
1. A brief explanation of WHY this problem occurs with typical sellers
2. A specific, credible solution our product offers (what we actually do differently)
3. A short CTA hook sentence that could appear in a blog article

Be specific and honest — not marketing fluff. Example:
- Complaint: "cardamom pods look pale yellow"  
- Why: "mass producers harvest early to maximize volume, leaving pods under-ripe"
- Solution: "we harvest only when pods reach 7.5–8mm with full green color, verified by hand"
- Hook: "Unlike most brands that harvest early, our cardamom pods are held until full 7.5–8mm ripeness."

Customer complaints to address:
{complaints_text}

Return JSON array:
[
  {{
    "complaint": "exact complaint text",
    "why_it_happens": "brief explanation",
    "our_solution": "what we do specifically",
    "frequency": "very common|common|occasional",
    "cta_line": "one sentence for blog article"
  }},
  ...
]"""

        result = await self._call_or(prompt, expect_list=True)
        signals = []
        if isinstance(result, list):
            for item in result:
                if not isinstance(item, dict):
                    continue
                signals.append(ComplaintSignal(
                    complaint=item.get("complaint", ""),
                    frequency=item.get("frequency", "common"),
                    source_hint="research",
                    solution=item.get("our_solution", ""),
                    cta_line=item.get("cta_line", ""),
                ))
        return signals

    async def _call_or(self, prompt: str, expect_list: bool = False) -> Any:
        """Call OpenRouter with clean JSON parsing. Tries multiple free models."""
        if not self.or_key:
            log.warning("[NegativeReview] No OpenRouter key — skipping AI call")
            return [] if expect_list else {}

        system = "You are a product research analyst. Return only valid JSON. No markdown code blocks."
        # Try multiple free models in order
        models_to_try = [
            self.or_model,
            "openai/gpt-oss-120b:free",
            "qwen/qwq-32b:free",
            "mistralai/mistral-small-3.2-24b-instruct:free",
        ]
        # Deduplicate
        seen = set()
        models_to_try = [m for m in models_to_try if not (m in seen or seen.add(m))]

        for model in models_to_try:
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
                "max_tokens": 2000,
            }

            try:
                loop = asyncio.get_event_loop()
                resp = await loop.run_in_executor(None, lambda m=model: requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.or_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://annaseo.pureleven.com",
                        "X-Title": "AnnaSEO",
                    },
                    json={**payload, "model": m},
                    timeout=45,
                ))
                if resp.status_code == 429:
                    log.debug(f"[NegativeReview] model {model} rate-limited, trying next")
                    continue
                if resp.status_code != 200:
                    log.warning(f"[NegativeReview] OR API error {resp.status_code} for {model}: {resp.text[:200]}")
                    continue

                data = resp.json()
                text = data.get("choices", [{}])[0].get("message", {}).get("content", "")

                # Strip markdown code fences
                text = re.sub(r"```(?:json)?\s*", "", text)
                text = re.sub(r"```\s*", "", text)
                text = text.strip()

                # Strip <think> blocks (DeepSeek, etc.)
                text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

                # Parse JSON
                parsed = json.loads(text)
                return parsed
            except json.JSONDecodeError as e:
                log.warning(f"[NegativeReview] JSON parse error from {model}: {e}")
                continue
            except Exception as e:
                log.warning(f"[NegativeReview] OR call failed for {model}: {e}")
                continue

        log.warning("[NegativeReview] All free models failed or rate-limited")
        return [] if expect_list else {}

    # ──────────────────────────────────────────────────────────────────────────
    # Content generation helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _build_hooks(self, signals: List[ComplaintSignal]) -> List[str]:
        """Build ready-to-use article sentences from signals."""
        hooks = []
        for s in signals:
            if s.cta_line:
                hooks.append(s.cta_line)
        return hooks

    def _build_credibility_section(self, signals: List[ComplaintSignal]) -> str:
        """
        Build a full HTML section (2–4 paragraphs) addressing common complaints.
        This can be injected directly into the article body.
        """
        if not signals:
            return ""

        items_html = ""
        for s in signals[:5]:
            if s.complaint and s.solution:
                items_html += f"""
  <li>
    <strong>{s.complaint.capitalize()}:</strong> {s.solution}
  </li>"""

        return f"""
<section class="quality-assurance">
  <h2>What Other {self.keyword.title()} Buyers Get Wrong (And How We Fixed It)</h2>
  <p>Most customer complaints about {self.keyword} come down to the same recurring issues. 
  We researched hundreds of reviews so you don't have to — and built our sourcing process around solving each problem.</p>
  <ul>{items_html}
  </ul>
  <p>Every decision we make — from harvest timing to packaging — is a direct response to the problems buyers 
  commonly face. You don't need to guess; the differences are traceable.</p>
</section>"""

    def to_blueprint_hint(self, result: NegativeReviewResult) -> str:
        """
        Format the research result as a compact hint text for the content blueprint prompt.
        Used by SEOContentPipeline to inject into Step 2/6 prompts.
        """
        if not result.signals:
            return ""

        parts = ["COMPETITIVE DIFFERENTIATION — Common customer complaints and our solutions:"]
        for i, s in enumerate(result.signals[:6], 1):
            parts.append(f"{i}. Complaint: {s.complaint}")
            if s.solution:
                parts.append(f"   Solution: {s.solution}")
        parts.append("")
        parts.append("Include a section addressing these complaints with our solutions to boost credibility and conversions.")
        parts.append("Use conversational, genuine tone — not marketing speak.")
        return "\n".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# Integrate into SEOContentPipeline
# ─────────────────────────────────────────────────────────────────────────────

async def run_complaint_research(
    keyword: str,
    business_context: str = "",
    or_key: str = "",
) -> NegativeReviewResult:
    """Convenience async entry point."""
    engine = NegativeReviewEngine(keyword=keyword, business_context=business_context, or_key=or_key)
    return await engine.research()
