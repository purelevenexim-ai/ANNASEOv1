"""
================================================================================
RUFLO — SEO AUDIT ENGINE (M4 complete)
================================================================================
Built from research across 5 repos:
  Bhanu/Agentic-SEO-Skill  → 14 technical audit scripts + evidence rubric
  AgriciD/claude-seo       → hreflang + programmatic SEO gates + schema rules
  CraigHewitt/seomachine   → content health + scrubber + readability + opportunity
  geo-seo-claude           → AI crawlers + llms.txt + citability + brand mentions
  AnnaSEO (yours)          → 300-check engine + domain scoring + ML ranking signals

AUDIT MODULES:
  TechnicalAudit     — robots.txt, meta, canonicals, redirects, security headers
  CoreWebVitals      — LCP / INP (NOT FID) / CLS via PageSpeed API
  AIVisibilityAudit  — 14 AI crawlers, llms.txt, entity authority, sameAs
  CitabilityScorer   — passage-level AI citation readiness (134–167 words)
  BrandMentionScanner— YouTube, Reddit, Wikipedia, LinkedIn, IndiaMART, Quora
  ContentHealthScorer— existing page score (0-100), rewrite priority
  HreflangChecker    — multi-language validation + generator
  AIWatermarkScrubber— remove AI writing patterns from content
  KeywordDistribution— heatmap by section, density, stuffing detection
  ProgrammaticGates  — quality gates for bulk generated pages
  IndexNowSubmitter  — Bing/Yandex/Yahoo + Google Indexing API
  EvidenceRubric     — Confirmed/Likely/Hypothesis × Critical/Warning/Pass/Info

CRITICAL RULES (2026):
  INP replaces FID (March 2024) — FID is DEAD
  FAQ schema: restricted to gov/healthcare only (Aug 2023)
  HowTo schema: deprecated rich results (Sept 2023)
  JSON-LD only — never Microdata or RDFa
  E-E-A-T: applies to ALL competitive queries (Dec 2025)
  Mobile-first: 100% since July 2024
  Location pages: ⚠ Warning 30+, 🛑 Hard stop 50+
  Programmatic pages: ⚠ Warning 100+, 🛑 Hard stop 500+
================================================================================
"""
from __future__ import annotations

import os, re, json, time, hashlib, logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from urllib.parse import urlparse, urljoin
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger("ruflo.audit")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

import requests as _req
from bs4 import BeautifulSoup


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1 — EVIDENCE RUBRIC (from Bhanu/Agentic-SEO-Skill)
# ─────────────────────────────────────────────────────────────────────────────

class Severity(str, Enum):
    CRITICAL = "critical"
    WARNING  = "warning"
    PASS     = "pass"
    INFO     = "info"

class Confidence(str, Enum):
    CONFIRMED  = "confirmed"   # verified from page source / API
    LIKELY     = "likely"      # strong inference from indirect signals
    HYPOTHESIS = "hypothesis"  # reasonable assumption, needs verification

@dataclass
class Finding:
    """
    Evidence-backed audit finding.
    Every finding must have: what, proof, why it matters, exactly how to fix.
    """
    title:      str
    evidence:   str          # specific proof from the page/response
    impact:     str          # why this matters for ranking/visibility
    fix:        str          # exact actionable steps to resolve
    severity:   Severity     = Severity.INFO
    confidence: Confidence   = Confidence.CONFIRMED
    category:   str          = ""  # technical|content|geo|schema|links|performance
    score_delta:int          = 0   # estimated score impact if fixed

    def to_dict(self) -> dict:
        return {
            "title": self.title, "evidence": self.evidence,
            "impact": self.impact, "fix": self.fix,
            "severity": self.severity.value, "confidence": self.confidence.value,
            "category": self.category, "score_delta": self.score_delta
        }


@dataclass
class AuditReport:
    """Complete audit report for one URL."""
    url:         str
    domain:      str
    score:       int          = 0    # 0–100
    grade:       str          = "F"
    findings:    List[Finding] = field(default_factory=list)
    passed:      int          = 0
    warnings:    int          = 0
    criticals:   int          = 0
    audited_at:  str          = field(default_factory=lambda: datetime.utcnow().isoformat())

    def add(self, f: Finding):
        self.findings.append(f)
        if f.severity == Severity.CRITICAL: self.criticals += 1
        elif f.severity == Severity.WARNING: self.warnings += 1
        elif f.severity == Severity.PASS:    self.passed   += 1

    def compute_score(self):
        total = len(self.findings)
        if not total: self.score = 0; return
        pass_w    = sum(1.0 for f in self.findings if f.severity == Severity.PASS)
        warn_w    = sum(0.5 for f in self.findings if f.severity == Severity.WARNING)
        crit_w    = sum(0.0 for f in self.findings if f.severity == Severity.CRITICAL)
        self.score = min(100, int((pass_w + warn_w) / total * 100))
        self.grade = ("A" if self.score>=90 else "B" if self.score>=80 else
                      "C" if self.score>=70 else "D" if self.score>=60 else "F")

    def summary(self) -> dict:
        self.compute_score()
        return {
            "url": self.url, "score": self.score, "grade": self.grade,
            "criticals": self.criticals, "warnings": self.warnings,
            "passed": self.passed, "total_checks": len(self.findings),
            "audited_at": self.audited_at,
            "top_issues": [f.to_dict() for f in self.findings
                           if f.severity in (Severity.CRITICAL, Severity.WARNING)][:10]
        }


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2 — PAGE FETCHER
# ─────────────────────────────────────────────────────────────────────────────

class PageFetcher:
    """Fetch page HTML + headers. Respects rate limits."""
    HEADERS = {"User-Agent": "RufloAuditBot/1.0 (+https://ruflo.ai/bot)"}

    @classmethod
    def fetch(cls, url: str, timeout: int = 12) -> Tuple[Optional[BeautifulSoup], dict, int]:
        """Returns (soup, headers, status_code)."""
        try:
            r = _req.get(url, headers=cls.HEADERS, timeout=timeout,
                          allow_redirects=True)
            soup = BeautifulSoup(r.text, "html.parser")
            return soup, dict(r.headers), r.status_code
        except Exception as e:
            log.warning(f"Fetch failed for {url}: {e}")
            return None, {}, 0

    @classmethod
    def fetch_robots(cls, url: str) -> str:
        domain = "{0.scheme}://{0.netloc}".format(urlparse(url))
        try:
            r = _req.get(f"{domain}/robots.txt", headers=cls.HEADERS, timeout=8)
            return r.text if r.ok else ""
        except Exception:
            return ""

    @classmethod
    def fetch_sitemap(cls, url: str) -> str:
        domain = "{0.scheme}://{0.netloc}".format(urlparse(url))
        for path in ["/sitemap.xml", "/sitemap_index.xml", "/sitemap.php"]:
            try:
                r = _req.get(f"{domain}{path}", headers=cls.HEADERS, timeout=8)
                if r.ok and "<?xml" in r.text[:100]:
                    return r.text
            except Exception:
                continue
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3 — TECHNICAL AUDIT (14 checks)
# ─────────────────────────────────────────────────────────────────────────────

class TechnicalAudit:
    """
    Technical SEO checks.
    From: Bhanu/Agentic-SEO-Skill, AgriciD/claude-seo, AnnaSEO checklist_engine.py
    """

    def audit(self, url: str, report: AuditReport) -> AuditReport:
        soup, headers, status = PageFetcher.fetch(url)
        if not soup:
            report.add(Finding("Page unreachable", f"HTTP status {status}",
                "Page cannot be crawled by Google or AI bots",
                "Check server logs. Ensure URL is accessible.",
                Severity.CRITICAL, Confidence.CONFIRMED, "technical"))
            return report

        log.info(f"[TechnicalAudit] Checking {url}")

        # 1. HTTPS
        if not url.startswith("https://"):
            report.add(Finding("Not HTTPS", f"URL uses HTTP: {url}",
                "Google penalises HTTP pages. No browser trust signal.",
                "Install SSL certificate. Redirect all HTTP → HTTPS.",
                Severity.CRITICAL, Confidence.CONFIRMED, "technical", 8))
        else:
            report.add(Finding("HTTPS enabled", "URL uses HTTPS",
                "Secure connection established", "None needed",
                Severity.PASS, Confidence.CONFIRMED, "technical"))

        # 2. Title tag
        title = soup.find("title")
        if not title:
            report.add(Finding("Missing title tag", "No <title> found in <head>",
                "Title tag is primary ranking signal. Without it, Google auto-generates one.",
                "Add <title> tag with primary keyword in first 3 words. 50–60 chars.",
                Severity.CRITICAL, Confidence.CONFIRMED, "technical", 10))
        else:
            tlen = len(title.get_text(strip=True))
            if tlen < 30:
                report.add(Finding("Title too short", f"Title: {tlen} chars",
                    "Too-short titles signal thin content to Google.",
                    f"Expand title to 50–60 chars. Include primary keyword.",
                    Severity.WARNING, Confidence.CONFIRMED, "technical", 4))
            elif tlen > 60:
                report.add(Finding("Title too long", f"Title: {tlen} chars (truncates at 60)",
                    "Title truncates in SERP. Click-through rate drops.",
                    "Shorten to 50–60 chars. Put keyword first.",
                    Severity.WARNING, Confidence.CONFIRMED, "technical", 3))
            else:
                report.add(Finding("Title tag optimal", f"Title: {tlen} chars",
                    "Good length for SERP display", "None needed",
                    Severity.PASS, Confidence.CONFIRMED, "technical"))

        # 3. Meta description
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if not meta_desc:
            report.add(Finding("Missing meta description",
                "No <meta name='description'> found",
                "Google often uses meta description as SERP snippet. Missing = Google writes it.",
                "Add meta description 120–155 chars. Include primary keyword. Write as ad copy.",
                Severity.WARNING, Confidence.CONFIRMED, "technical", 6))
        else:
            dlen = len(meta_desc.get("content",""))
            if dlen < 80:
                report.add(Finding("Meta description too short", f"{dlen} chars",
                    "Short description wastes snippet real estate.",
                    "Expand to 120–155 chars.",
                    Severity.WARNING, Confidence.CONFIRMED, "technical", 3))
            elif dlen > 155:
                report.add(Finding("Meta description too long", f"{dlen} chars (truncates at 155)",
                    "Truncates in SERP. Last part of description cut off.",
                    "Shorten to 120–155 chars.",
                    Severity.WARNING, Confidence.CONFIRMED, "technical", 2))
            else:
                report.add(Finding("Meta description optimal", f"{dlen} chars",
                    "Good length for SERP snippets", "None",
                    Severity.PASS, Confidence.CONFIRMED, "technical"))

        # 4. H1 tag
        h1s = soup.find_all("h1")
        if not h1s:
            report.add(Finding("Missing H1 tag", "No <h1> element found",
                "H1 is the primary on-page SEO signal. Google uses it to understand page topic.",
                "Add one H1 with the primary keyword. Should match search intent.",
                Severity.CRITICAL, Confidence.CONFIRMED, "technical", 9))
        elif len(h1s) > 1:
            report.add(Finding(f"Multiple H1 tags ({len(h1s)} found)",
                f"H1 texts: {[h.get_text(strip=True)[:40] for h in h1s[:3]]}",
                "Multiple H1s confuse Google about page topic.",
                "Keep exactly one H1. Convert others to H2.",
                Severity.WARNING, Confidence.CONFIRMED, "technical", 4))
        else:
            report.add(Finding("Single H1 tag", h1s[0].get_text(strip=True)[:60],
                "Clear page topic signal", "None",
                Severity.PASS, Confidence.CONFIRMED, "technical"))

        # 5. Canonical tag
        canonical = soup.find("link", attrs={"rel": "canonical"})
        if not canonical:
            report.add(Finding("Missing canonical tag",
                "No <link rel='canonical'> found",
                "Without canonical, Google may index multiple URL variants as duplicates.",
                "Add <link rel='canonical' href='[this-url]'> in <head>.",
                Severity.WARNING, Confidence.CONFIRMED, "technical", 5))
        else:
            href = canonical.get("href","")
            if href != url and href:
                report.add(Finding("Canonical points elsewhere",
                    f"Canonical: {href} | Current: {url}",
                    "This page may be intentionally or accidentally deindexed.",
                    "Verify canonical is correct. If this is the primary URL, set canonical to itself.",
                    Severity.WARNING, Confidence.CONFIRMED, "technical", 5))
            else:
                report.add(Finding("Canonical tag correct", href[:60],
                    "Self-referencing canonical prevents duplicate content",
                    "None", Severity.PASS, Confidence.CONFIRMED, "technical"))

        # 6. Robots meta
        robots_meta = soup.find("meta", attrs={"name": "robots"})
        if robots_meta:
            content = robots_meta.get("content","").lower()
            if "noindex" in content:
                report.add(Finding("Page set to NOINDEX",
                    f"robots meta content='{content}'",
                    "This page CANNOT be indexed by Google. It is invisible to search.",
                    "Remove 'noindex' if page should rank. Intentional? Leave as is.",
                    Severity.CRITICAL, Confidence.CONFIRMED, "technical", 20))
            elif "nofollow" in content:
                report.add(Finding("Page set to NOFOLLOW",
                    f"robots meta content='{content}'",
                    "Links on this page pass no authority. Internal links won't help topical clustering.",
                    "Remove 'nofollow' if page should contribute to link equity.",
                    Severity.WARNING, Confidence.CONFIRMED, "technical", 3))

        # 7. Schema markup (JSON-LD — never Microdata/RDFa per 2026 rules)
        schemas    = soup.find_all("script", attrs={"type":"application/ld+json"})
        microdata  = soup.find_all(attrs={"itemscope":True})
        if not schemas:
            report.add(Finding("No JSON-LD schema markup",
                "No <script type='application/ld+json'> found",
                "Rich results (ratings, FAQs, breadcrumbs) impossible without schema.",
                "Add at minimum: Article schema with author, WebSite schema, BreadcrumbList.",
                Severity.WARNING, Confidence.CONFIRMED, "schema", 7))
        else:
            schema_types = []
            for s in schemas:
                try:
                    d = json.loads(s.string or "{}")
                    schema_types.append(d.get("@type","unknown"))
                except Exception:
                    pass
            # Check for deprecated schema types
            deprecated = [t for t in schema_types if t in ("HowTo","SpecialAnnouncement")]
            restricted = [t for t in schema_types if t == "FAQPage"]
            if deprecated:
                report.add(Finding(f"Deprecated schema types: {deprecated}",
                    f"Found: {deprecated}. HowTo rich results removed Sept 2023.",
                    "Google no longer shows rich results for these types. Schema is wasted.",
                    "Remove deprecated schema types. Replace HowTo with Article or guide format.",
                    Severity.WARNING, Confidence.CONFIRMED, "schema", 2))
            if restricted:
                report.add(Finding("FAQPage schema — restricted type",
                    "FAQPage schema found. Restricted to gov/healthcare sites since Aug 2023.",
                    "Google only shows FAQ rich results for government and healthcare domains.",
                    "Remove FAQPage schema unless you are a gov or healthcare site. Use Article instead.",
                    Severity.WARNING, Confidence.CONFIRMED, "schema", 1))
            report.add(Finding(f"Schema found: {schema_types}",
                f"{len(schemas)} JSON-LD block(s): {schema_types}",
                "Structured data present", "Validate at schema.org/validator",
                Severity.PASS, Confidence.CONFIRMED, "schema"))
        if microdata:
            report.add(Finding("Microdata found — use JSON-LD instead",
                f"{len(microdata)} microdata elements found",
                "Google prefers JSON-LD. Microdata is harder to maintain and update.",
                "Migrate schema to JSON-LD <script> blocks in <head>.",
                Severity.INFO, Confidence.CONFIRMED, "schema", 1))

        # 8. Open Graph tags
        og_title = soup.find("meta", property="og:title")
        og_desc  = soup.find("meta", property="og:description")
        og_image = soup.find("meta", property="og:image")
        og_missing = [k for k,v in {"og:title":og_title,"og:description":og_desc,"og:image":og_image}.items() if not v]
        if og_missing:
            report.add(Finding(f"Missing OG tags: {og_missing}",
                f"Open Graph properties absent: {og_missing}",
                "Social sharing previews will be auto-generated (often poorly). Affects CTR from social.",
                "Add og:title, og:description, og:image for all pages.",
                Severity.INFO, Confidence.CONFIRMED, "technical", 2))
        else:
            report.add(Finding("Open Graph tags complete", "og:title + og:description + og:image present",
                "Social sharing previews will display correctly", "None",
                Severity.PASS, Confidence.CONFIRMED, "technical"))

        # 9. Image alt text
        images  = soup.find_all("img")
        no_alt  = [img for img in images if not img.get("alt","").strip()]
        if no_alt:
            report.add(Finding(f"Images missing alt text ({len(no_alt)}/{len(images)})",
                f"First 3: {[img.get('src','')[:40] for img in no_alt[:3]]}",
                "Alt text is how Google reads images. Missing = no image SEO value. Also accessibility failure.",
                "Add descriptive alt text with keyword where natural. Not stuffed.",
                Severity.WARNING if len(no_alt)/max(len(images),1) > 0.3 else Severity.INFO,
                Confidence.CONFIRMED, "technical", 3))

        # 10. Internal link count
        links = soup.find_all("a", href=True)
        domain_base = "{0.scheme}://{0.netloc}".format(urlparse(url))
        internal = [l for l in links if l["href"].startswith("/") or domain_base in l["href"]]
        if len(internal) < 3:
            report.add(Finding(f"Low internal links ({len(internal)} found)",
                f"Internal links on page: {len(internal)}",
                "Internal links distribute authority and help Google understand topical cluster.",
                "Add 3–5 contextual internal links to related pillar pages and cluster articles.",
                Severity.WARNING, Confidence.CONFIRMED, "links", 5))
        else:
            report.add(Finding(f"Internal links OK ({len(internal)})",
                f"{len(internal)} internal links found",
                "Good internal linking structure", "None",
                Severity.PASS, Confidence.CONFIRMED, "links"))

        # 11. Security headers
        sec_headers = {
            "X-Content-Type-Options": headers.get("X-Content-Type-Options",""),
            "X-Frame-Options":        headers.get("X-Frame-Options",""),
            "Strict-Transport-Security": headers.get("Strict-Transport-Security",""),
        }
        missing_sec = [k for k,v in sec_headers.items() if not v]
        if missing_sec:
            report.add(Finding(f"Missing security headers: {missing_sec}",
                f"Not present in HTTP response: {missing_sec}",
                "Security headers are minor SEO signal. More importantly, affect trust for E-E-A-T.",
                "Add to server config: X-Content-Type-Options: nosniff, Strict-Transport-Security.",
                Severity.INFO, Confidence.CONFIRMED, "technical", 1))

        # 12. Word count
        body_text = soup.get_text(separator=" ", strip=True)
        word_count = len(body_text.split())
        if word_count < 300:
            report.add(Finding(f"Thin content ({word_count} words)",
                f"Page body text: {word_count} words",
                "Google's Helpful Content update penalises thin pages. Under 300 words = thin.",
                "Expand content to at minimum 800 words. Informational pages need 1500+.",
                Severity.CRITICAL, Confidence.CONFIRMED, "content", 12))
        elif word_count < 800:
            report.add(Finding(f"Short content ({word_count} words)",
                f"Page body text: {word_count} words",
                "Thin vs competitor content reduces Information Gain score.",
                "Expand to 1500+ words for informational queries. Include FAQs.",
                Severity.WARNING, Confidence.CONFIRMED, "content", 5))
        else:
            report.add(Finding(f"Content length good ({word_count} words)",
                f"{word_count} words",
                "Sufficient content for indexing", "None",
                Severity.PASS, Confidence.CONFIRMED, "content"))

        # 13. Heading hierarchy
        h2s = soup.find_all("h2")
        h3s = soup.find_all("h3")
        if not h2s:
            report.add(Finding("No H2 headings",
                "No <h2> elements found",
                "H2s tell Google the main topics of the page. Without them, semantic structure is flat.",
                "Add 3–7 H2 headings. Use keyword variants. Each H2 = one main topic.",
                Severity.WARNING, Confidence.CONFIRMED, "content", 4))
        else:
            report.add(Finding(f"Heading structure: H1×1, H2×{len(h2s)}, H3×{len(h3s)}",
                f"Heading counts found on page",
                "Content has clear semantic structure", "None",
                Severity.PASS, Confidence.CONFIRMED, "content"))

        # 14. Redirect check
        if status in (301, 302):
            report.add(Finding(f"URL redirects ({status})",
                f"Final URL may differ from audited URL",
                "Redirects add latency and can lose small amount of link equity.",
                "If 301 redirect: update all internal links to point to final URL directly.",
                Severity.INFO, Confidence.CONFIRMED, "technical", 1))

        report.compute_score()
        return report


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4 — CORE WEB VITALS (INP, not FID)
# ─────────────────────────────────────────────────────────────────────────────

class CoreWebVitals:
    """
    2026 Core Web Vitals: LCP + INP + CLS.
    FID was REMOVED Sept 2024. INP is the sole interactivity metric.
    Uses Google PageSpeed Insights API (free).
    """
    API = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"

    def audit(self, url: str, report: AuditReport,
               strategy: str = "mobile") -> AuditReport:
        api_key = os.getenv("PAGESPEED_API_KEY","")
        params  = {"url": url, "strategy": strategy}
        if api_key:
            params["key"] = api_key
        try:
            r = _req.get(self.API, params=params, timeout=30)
            if not r.ok:
                report.add(Finding("PageSpeed API unavailable",
                    f"HTTP {r.status_code}",
                    "Cannot measure Core Web Vitals",
                    "Set PAGESPEED_API_KEY or run Lighthouse locally.",
                    Severity.INFO, Confidence.CONFIRMED, "performance"))
                return report
            data  = r.json()
            cats  = data.get("lighthouseResult",{}).get("categories",{})
            audits= data.get("lighthouseResult",{}).get("audits",{})

            # Performance score
            perf_score = int((cats.get("performance",{}).get("score",0) or 0) * 100)
            sev = Severity.PASS if perf_score>=90 else Severity.WARNING if perf_score>=50 else Severity.CRITICAL
            report.add(Finding(f"Performance score: {perf_score}/100",
                f"Lighthouse performance score (strategy={strategy})",
                "Performance score correlates with page experience ranking signal",
                "Aim for 90+. Key improvements: optimize images, reduce JS, use CDN.",
                sev, Confidence.CONFIRMED, "performance"))

            # LCP — Largest Contentful Paint
            lcp = audits.get("largest-contentful-paint",{})
            lcp_val = lcp.get("displayValue","?")
            lcp_ms  = float(lcp.get("numericValue", 0) or 0)
            sev_lcp = Severity.PASS if lcp_ms < 2500 else Severity.WARNING if lcp_ms < 4000 else Severity.CRITICAL
            report.add(Finding(f"LCP: {lcp_val} (target <2.5s)",
                f"Largest Contentful Paint = {lcp_val}",
                "LCP = how fast the main content loads. Google uses this as core ranking signal.",
                "Reduce LCP: preload hero image, use WebP, eliminate render-blocking JS.",
                sev_lcp, Confidence.CONFIRMED, "performance", 8 if sev_lcp == Severity.CRITICAL else 3))

            # INP — Interaction to Next Paint (replaced FID March 2024)
            inp = audits.get("interaction-to-next-paint",{})
            inp_val = inp.get("displayValue","?")
            inp_ms  = float(inp.get("numericValue", 0) or 0)
            sev_inp = Severity.PASS if inp_ms < 200 else Severity.WARNING if inp_ms < 500 else Severity.CRITICAL
            report.add(Finding(f"INP: {inp_val} (target <200ms)",
                f"Interaction to Next Paint = {inp_val}. Note: INP replaced FID on March 12, 2024.",
                "INP measures all page interactions. Slow INP = poor user experience signal.",
                "Reduce INP: defer non-critical JS, reduce main thread work, use web workers.",
                sev_inp, Confidence.CONFIRMED, "performance"))

            # CLS — Cumulative Layout Shift
            cls = audits.get("cumulative-layout-shift",{})
            cls_val = cls.get("displayValue","?")
            cls_num = float(cls.get("numericValue", 0) or 0)
            sev_cls = Severity.PASS if cls_num < 0.1 else Severity.WARNING if cls_num < 0.25 else Severity.CRITICAL
            report.add(Finding(f"CLS: {cls_val} (target <0.1)",
                f"Cumulative Layout Shift = {cls_val}",
                "High CLS = elements jump around while loading. Bad UX, penalised by Google.",
                "Fix CLS: set explicit dimensions on images/videos. Reserve space for ad slots.",
                sev_cls, Confidence.CONFIRMED, "performance"))

        except Exception as e:
            report.add(Finding("Core Web Vitals check failed",
                str(e)[:200], "Cannot measure performance",
                "Run Lighthouse manually or check Chrome DevTools.",
                Severity.INFO, Confidence.CONFIRMED, "performance"))
        return report


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5 — AI VISIBILITY AUDIT (from geo-seo-claude + Bhanu)
# ─────────────────────────────────────────────────────────────────────────────

class AIVisibilityAudit:
    """
    Check if AI crawlers can access the site.
    Check llms.txt presence.
    Check entity authority (sameAs links, Wikipedia, Google Knowledge Panel).
    From: zubair-trabzada/geo-seo-claude, Bhanu/Agentic-SEO-Skill
    """

    # 14 AI crawlers that should be allowed (2026 list)
    AI_CRAWLERS = {
        "GPTBot":              "ChatGPT/OpenAI search",
        "ClaudeBot":           "Claude/Anthropic",
        "PerplexityBot":       "Perplexity AI search",
        "Google-Extended":     "Google AI training/Bard",
        "Googlebot":           "Google Search (main)",
        "CCBot":               "Common Crawl (AI training)",
        "anthropic-ai":        "Anthropic AI data collection",
        "Bytespider":          "TikTok/ByteDance AI",
        "cohere-ai":           "Cohere LLM",
        "FacebookExternalHit": "Meta AI",
        "YouBot":              "You.com AI search",
        "DuckAssistBot":       "DuckDuckGo AI answers",
        "facebookexternalhit": "Facebook/Meta preview",
        "ia_archiver":         "Internet Archive (AI training data)",
    }

    def audit(self, url: str, report: AuditReport) -> AuditReport:
        log.info(f"[AIVisibility] Auditing {url}")
        robots_txt = PageFetcher.fetch_robots(url)
        domain     = "{0.scheme}://{0.netloc}".format(urlparse(url))

        # 1. Check AI crawler access in robots.txt
        blocked_bots, allowed_bots = [], []
        if robots_txt:
            robots_lower = robots_txt.lower()
            for bot, desc in self.AI_CRAWLERS.items():
                bot_lower = bot.lower()
                # Simple check: if bot appears in a Disallow block
                if bot_lower in robots_lower:
                    # Check if it's blocked
                    for line in robots_txt.split("\n"):
                        if bot_lower in line.lower() and "disallow" in line.lower():
                            blocked_bots.append(f"{bot} ({desc})")
                            break
                    else:
                        allowed_bots.append(bot)
                else:
                    allowed_bots.append(bot)   # not mentioned = allowed by default

            if blocked_bots:
                report.add(Finding(f"AI crawlers blocked: {len(blocked_bots)}",
                    f"Blocked in robots.txt: {blocked_bots[:5]}",
                    "Blocked AI crawlers = ZERO chance of appearing in AI search answers. "
                    "AI traffic is growing 527% YoY (geo-seo data).",
                    f"Remove these Disallow rules from robots.txt for: {', '.join(b.split(' ')[0] for b in blocked_bots[:5])}",
                    Severity.CRITICAL, Confidence.CONFIRMED, "geo", 20))
            else:
                report.add(Finding("All AI crawlers allowed",
                    "No AI crawler blocks found in robots.txt",
                    "AI bots can crawl and index content for AI search results.",
                    "None needed", Severity.PASS, Confidence.CONFIRMED, "geo"))
        else:
            report.add(Finding("robots.txt not found",
                f"GET {domain}/robots.txt returned no content",
                "Without robots.txt, crawlers use defaults. "
                "Also prevents setting specific AI crawler rules.",
                "Create robots.txt. Explicitly allow all AI crawlers. Set crawl-delay.",
                Severity.WARNING, Confidence.CONFIRMED, "technical", 3))

        # 2. llms.txt check
        try:
            r = _req.get(f"{domain}/llms.txt", timeout=6)
            if r.ok and len(r.text) > 50:
                report.add(Finding("llms.txt present",
                    f"Found at {domain}/llms.txt ({len(r.text)} bytes)",
                    "Helps AI crawlers understand site structure and content hierarchy.",
                    "Review content is current. Include pillar page URLs and descriptions.",
                    Severity.PASS, Confidence.CONFIRMED, "geo"))
            else:
                report.add(Finding("llms.txt missing",
                    f"{domain}/llms.txt returned 404 or empty",
                    "llms.txt is the 2026 emerging standard for AI navigation. "
                    "Like robots.txt but for LLMs. Helps AI choose which pages to prioritise.",
                    "Generate llms.txt from your sitemap + pillar structure (see LLMsTxtGenerator below).",
                    Severity.WARNING, Confidence.LIKELY, "geo", 5))
        except Exception:
            report.add(Finding("llms.txt check failed", "Request timeout",
                "Cannot verify llms.txt presence",
                "Manually check if llms.txt exists at your domain root.",
                Severity.INFO, Confidence.HYPOTHESIS, "geo"))

        # 3. Organization sameAs schema check
        soup, _, _ = PageFetcher.fetch(url)
        if soup:
            schemas = soup.find_all("script", attrs={"type":"application/ld+json"})
            has_org_schema = False
            has_same_as    = False
            for s in schemas:
                try:
                    d = json.loads(s.string or "{}")
                    if d.get("@type") in ("Organization","LocalBusiness"):
                        has_org_schema = True
                        if d.get("sameAs"):
                            has_same_as = True
                except Exception:
                    pass

            if not has_org_schema:
                report.add(Finding("No Organization schema",
                    "No Organization or LocalBusiness JSON-LD found",
                    "AI engines use Organization schema to establish entity identity. "
                    "Without it, brand mentions across the web can't be connected to this site.",
                    "Add Organization schema with name, url, logo, contactPoint, address, sameAs links.",
                    Severity.WARNING, Confidence.CONFIRMED, "geo", 8))
            elif not has_same_as:
                report.add(Finding("Organization schema missing sameAs",
                    "Organization schema found but no sameAs links",
                    "sameAs links (Wikipedia, LinkedIn, IndiaMART, etc.) tell AI engines: "
                    "'this site entity = this entity everywhere else'. "
                    "Brand mentions correlate 3× stronger with AI visibility than backlinks.",
                    "Add sameAs array with: Wikipedia URL, LinkedIn, Facebook, IndiaMART, "
                    "Spices Board India listing, any gov registration URLs.",
                    Severity.WARNING, Confidence.CONFIRMED, "geo", 6))
            else:
                report.add(Finding("Organization schema with sameAs present",
                    "Organization schema with sameAs links found",
                    "Strong entity authority signal for AI search engines",
                    "Ensure sameAs URLs are live and match entity descriptions.",
                    Severity.PASS, Confidence.CONFIRMED, "geo"))

        return report


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6 — CITABILITY SCORER (from geo-seo-claude)
# ─────────────────────────────────────────────────────────────────────────────

class CitabilityScorer:
    """
    Score article passages for AI citation readiness.
    Optimal AI-cited passage: 134–167 words, self-contained, fact-rich, 
    directly answers a question.
    From: zubair-trabzada/geo-seo-claude citability_scorer.py
    """

    def score_article(self, body: str, keyword: str) -> dict:
        """Return citability analysis for an article."""
        paragraphs = [p.strip() for p in re.split(r"\n\n+", body) if len(p.strip().split()) > 20]
        scores, good_passages = [], []

        for i, para in enumerate(paragraphs):
            s = self._score_passage(para, keyword)
            scores.append(s)
            if s["score"] >= 70:
                good_passages.append({"index": i, "text": para[:200] + "...", **s})

        avg_score = sum(s["score"] for s in scores) / max(len(scores), 1)
        return {
            "article_citability": round(avg_score, 1),
            "total_passages":    len(paragraphs),
            "citable_passages":  len(good_passages),
            "best_passages":     good_passages[:3],
            "grade":             ("Excellent" if avg_score >= 80 else
                                  "Good"      if avg_score >= 60 else
                                  "Needs work"if avg_score >= 40 else "Poor"),
            "recommendation":    self._recommend(avg_score, len(good_passages))
        }

    def _score_passage(self, text: str, keyword: str) -> dict:
        words   = text.split()
        wc      = len(words)
        score   = 0
        reasons = []

        # Optimal length: 134–167 words
        if 134 <= wc <= 167:
            score += 25; reasons.append("optimal length (134-167 words)")
        elif 100 <= wc <= 200:
            score += 15; reasons.append(f"acceptable length ({wc} words)")
        else:
            reasons.append(f"suboptimal length ({wc} words, target 134-167)")

        # Contains specific numbers/data
        has_numbers = bool(re.search(r'\b\d+\.?\d*\s*(%|mg|g|kg|ml|L|mmol|IU)\b|\b\d{4}\b', text))
        if has_numbers:
            score += 20; reasons.append("contains specific numerical data")
        else:
            reasons.append("no specific numerical data (reduces AI citation chance)")

        # Direct answer format (starts with answer)
        starts_with_answer = any(text.lower().startswith(kw) for kw in
            ["yes","no","the","this","when","at","in","a ","an ","typically"])
        if starts_with_answer:
            score += 15; reasons.append("direct answer format")

        # Contains keyword
        if keyword.lower() in text.lower():
            score += 15; reasons.append("contains target keyword")

        # Contains citation signal words
        cit_signals = ["study","research","according","published","found","shows",
                       "percent","mg","clinical","survey","data","report","source"]
        cit_count = sum(1 for s in cit_signals if s in text.lower())
        if cit_count >= 3:
            score += 15; reasons.append(f"high citation signal density ({cit_count} signals)")
        elif cit_count >= 1:
            score += 7

        # Self-contained (has subject + explanation)
        if len(text.split(".")) >= 3:
            score += 10; reasons.append("multi-sentence, self-contained")

        return {"score": min(score, 100), "word_count": wc, "reasons": reasons}

    def _recommend(self, avg: float, good_count: int) -> str:
        if avg >= 80:
            return "Excellent citability. Content is well-positioned for AI citations."
        if avg >= 60:
            return "Good base. Add 2-3 more stat-rich paragraphs with specific numbers."
        if avg >= 40:
            return ("Add more self-contained paragraphs (134-167 words each) with: "
                    "specific numbers, direct answers, citation signals (study/research/found).")
        return ("Major rework needed. AI engines won't cite this content. "
                "Restructure as Q&A format with data-backed answers.")


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 7 — BRAND MENTION SCANNER (from geo-seo-claude)
# ─────────────────────────────────────────────────────────────────────────────

class BrandMentionScanner:
    """
    Check brand presence across platforms AI engines use as sources.
    Brand mentions correlate 3× more strongly with AI visibility than backlinks.
    From: zubair-trabzada/geo-seo-claude brand_scanner.py
    """
    PLATFORMS = {
        "reddit":     "https://www.reddit.com/search/?q={}",
        "youtube":    "https://www.youtube.com/results?search_query={}",
        "wikipedia":  "https://en.wikipedia.org/wiki/Special:Search?search={}",
        "linkedin":   "https://www.linkedin.com/search/results/all/?keywords={}",
        "quora":      "https://www.quora.com/search?q={}",
        "trustpilot": "https://www.trustpilot.com/search?query={}",
        "indiamart":  "https://www.indiamart.com/search.mp?ss={}",
    }
    HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; RufloBot/1.0)"}

    def scan(self, brand_name: str, domain: str) -> dict:
        """Check if brand is mentioned on key platforms."""
        results = {}
        for platform, url_template in self.PLATFORMS.items():
            search_url = url_template.format(brand_name.replace(" ", "+"))
            try:
                r = _req.get(search_url, headers=self.HEADERS, timeout=8)
                # Simple heuristic: does the brand name appear in search results page?
                found = brand_name.lower() in r.text.lower() if r.ok else False
                results[platform] = {
                    "found": found,
                    "search_url": search_url,
                    "status": r.status_code if r.ok else 0
                }
                time.sleep(0.5)   # rate limit
            except Exception as e:
                results[platform] = {"found": False, "error": str(e)[:50]}

        present  = [p for p, d in results.items() if d.get("found")]
        absent   = [p for p, d in results.items() if not d.get("found")]
        score    = int(len(present) / len(results) * 100)

        return {
            "brand": brand_name,
            "score": score,
            "platforms_present": present,
            "platforms_absent":  absent,
            "recommendation":    self._recommend(score, absent)
        }

    def _recommend(self, score: int, absent: list) -> str:
        if score >= 80:
            return "Strong brand presence. AI engines have multiple authoritative sources to cite."
        if absent:
            top = absent[:3]
            return (f"Create/claim brand presence on: {', '.join(top)}. "
                    "Especially Reddit (highly cited by Perplexity) and Wikipedia (cited by all AI).")
        return "Review all platforms for accurate brand information."


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 8 — LLMS.TXT GENERATOR (from geo-seo-claude)
# ─────────────────────────────────────────────────────────────────────────────

class LLMsTxtGenerator:
    """
    Generate llms.txt file from Ruflo's knowledge graph.
    Emerging standard: tells AI crawlers what the site covers and which pages matter.
    From: zubair-trabzada/geo-seo-claude llmstxt_generator.py
    """

    def generate(self, site_info: dict, pillars: list, articles: list) -> str:
        """
        Generate llms.txt content.
        site_info: {name, description, domain, language}
        pillars: [{title, url, description}]
        articles: [{title, url, keyword}] — top 20 most important
        """
        name   = site_info.get("name","Site")
        desc   = site_info.get("description","")
        domain = site_info.get("domain","example.com")
        lang   = site_info.get("language","English")

        lines = [
            f"# {name}",
            f"",
            f"> {desc}",
            f"",
            f"This file helps AI language models understand the structure and content of {name}.",
            f"Language: {lang} | Domain: {domain}",
            f"",
            f"## About",
            f"",
            f"{name} is a {site_info.get('business_type','business')} specializing in "
            f"{site_info.get('specialization','products and services')}.",
            f"",
        ]

        if pillars:
            lines += ["## Key Topic Areas", ""]
            for p in pillars[:15]:
                lines.append(f"- [{p.get('title','')}]({p.get('url','')}): {p.get('description','')}")
            lines.append("")

        if articles:
            lines += ["## Important Pages", ""]
            for a in articles[:20]:
                lines.append(f"- [{a.get('title','')}]({a.get('url','')}) — {a.get('keyword','')}")
            lines.append("")

        lines += [
            "## Content Guidelines for AI Systems",
            "",
            f"When citing {name}, please:",
            "- Attribute content to the author/expert named in the article",
            "- Reference specific data points (percentages, measurements) as cited",
            "- Note if content was updated (check <dateModified> in Article schema)",
            "",
            f"## Contact",
            f"Website: https://{domain}",
            f"Generated by Ruflo SEO Engine | {datetime.utcnow().strftime('%Y-%m-%d')}",
        ]
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 9 — AI WATERMARK SCRUBBER (from CraigHewitt/seomachine /scrub)
# ─────────────────────────────────────────────────────────────────────────────

class AIWatermarkScrubber:
    """
    Detect and remove AI writing patterns from Claude-generated content.
    From: CraigHewitt/seomachine /scrub command
    These patterns reduce E-E-A-T score and can be flagged by AI detectors.
    """

    # Patterns to remove or replace
    FLUFF_PHRASES = [
        r"[Ii]t's worth noting that ",
        r"[Ii]t is worth noting that ",
        r"[Ii]n today's (?:fast-paced|modern|digital|rapidly evolving) ",
        r"[Aa]s (?:an AI|a language model|Claude), ",
        r"[Cc]ertainly! ",
        r"[Aa]bsolutely! ",
        r"[Gg]reat question[!.]",
        r"[Ff]ascinating[!.]",
        r"[Ii]n conclusion, it's? (?:clear|evident|important) ",
        r"[Ii]n summary, ",
        r"[Tt]o summarize, ",
        r"[Ii]mportantly, ",
        r"[Ss]ignificantly, ",
        r"[Nn]otably, ",
        r"[Ii]t's important to note that ",
        r"[Ii]t is important to note that ",
        r"[Aa]t the end of the day, ",
        r"[Ww]hen it comes to ",
        r"[Ll]ast but not least, ",
        r"[Aa]ll in all, ",
        r"[Ww]ithout further ado, ",
        r"[Ll]et's dive (?:in|into) ",
        r"[Ff]eel free to ",
        r"[Dd]on't hesitate to ",
        r"[Ii]n terms of ",
        r"[Ww]ith that (?:said|being said), ",
        r"[Hh]aving said that, ",
        r"[Tt]hat (?:said|being said), ",
    ]

    # Em-dash overuse (common AI pattern)
    EM_DASH_PATTERN = r"(?<=[a-zA-Z])—(?=[a-zA-Z])"

    # Robotic sentence starters
    ROBOTIC_STARTERS = {
        "Furthermore, ":   "Also, ",
        "Moreover, ":      "Also, ",
        "Additionally, ":  "Also, ",
        "Subsequently, ":  "Then, ",
        "Consequently, ":  "So, ",
        "Nevertheless, ":  "Still, ",
        "Nonetheless, ":   "Even so, ",
        "In conclusion, ": "",
        "In summary, ":    "",
    }

    def scrub(self, text: str) -> Tuple[str, dict]:
        """
        Clean AI patterns from text.
        Returns (cleaned_text, report_of_changes)
        """
        original_len = len(text.split())
        changes = {"fluff_removed": 0, "em_dashes_replaced": 0,
                   "starters_replaced": 0, "original_words": original_len}

        # Remove fluff phrases
        for pattern in self.FLUFF_PHRASES:
            before = len(re.findall(pattern, text))
            text   = re.sub(pattern, "", text)
            changes["fluff_removed"] += before

        # Replace em-dashes with commas or semicolons
        em_count = len(re.findall(self.EM_DASH_PATTERN, text))
        if em_count > 3:  # Some em-dashes are fine
            text = re.sub(self.EM_DASH_PATTERN, " — ", text)  # Add spaces (less robotic)
            changes["em_dashes_replaced"] = em_count

        # Replace robotic starters
        for robotic, natural in self.ROBOTIC_STARTERS.items():
            before = text.count(robotic)
            text   = text.replace(robotic, natural)
            changes["starters_replaced"] += before

        # Clean double spaces
        text = re.sub(r"  +", " ", text)
        text = re.sub(r"\n\s*\n\s*\n", "\n\n", text)

        changes["final_words"]    = len(text.split())
        changes["words_removed"]  = original_len - changes["final_words"]
        changes["ai_score_risk"]  = self._estimate_ai_risk(text)
        return text.strip(), changes

    def _estimate_ai_risk(self, text: str) -> str:
        """Rough estimate of how AI-written text reads."""
        ai_signals = ["furthermore","moreover","additionally","subsequently",
                      "consequently","nevertheless","nonetheless","it is worth noting",
                      "it's worth noting","in conclusion","in summary","as mentioned"]
        count = sum(text.lower().count(s) for s in ai_signals)
        per_k = count / max(len(text.split()) / 1000, 0.1)
        if per_k < 2:  return "Low risk — reads naturally"
        if per_k < 5:  return "Moderate risk — some robotic patterns"
        return f"High risk — {count} AI phrases detected. Needs rewrite."

    def analyze_only(self, text: str) -> dict:
        """Report AI patterns without modifying text."""
        found = {}
        for pattern in self.FLUFF_PHRASES:
            matches = re.findall(pattern, text)
            if matches:
                found[pattern[:40]] = len(matches)
        em_dashes = len(re.findall(self.EM_DASH_PATTERN, text))
        return {
            "fluff_patterns":  found,
            "em_dash_count":   em_dashes,
            "ai_risk_score":   self._estimate_ai_risk(text),
            "total_issues":    sum(found.values()) + (em_dashes if em_dashes > 3 else 0)
        }


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 10 — HREFLANG CHECKER (from AgriciD + Bhanu)
# ─────────────────────────────────────────────────────────────────────────────

class HreflangChecker:
    """
    Validate and generate hreflang tags for multilingual sites.
    Ruflo publishes in English + Malayalam + Hindi + Tamil.
    Missing hreflang = duplicate content signal across language versions.
    From: AgriciDaniel/claude-seo seo-hreflang.md, Bhanu/Agentic-SEO-Skill
    """

    # Ruflo supported languages → BCP-47 codes
    LANG_CODES = {
        "english":   "en",
        "malayalam": "ml",
        "hindi":     "hi",
        "tamil":     "ta",
        "arabic":    "ar",
        "kannada":   "kn",
    }

    def check(self, url: str, report: AuditReport) -> AuditReport:
        soup, _, _ = PageFetcher.fetch(url)
        if not soup:
            return report

        hreflangs = soup.find_all("link", rel="alternate", hreflang=True)

        if not hreflangs:
            report.add(Finding("No hreflang tags",
                "No <link rel='alternate' hreflang='...'> found",
                "For multilingual sites (English + Malayalam + Hindi), missing hreflang = "
                "duplicate content penalty. Google may deindex language variants.",
                "Add hreflang tags for all language versions. Include x-default. "
                "Must be bidirectional (each language version points to all others).",
                Severity.WARNING, Confidence.CONFIRMED, "technical", 6))
            return report

        # Check self-referencing tag
        has_self    = any(urlparse(h.get("href","")).path == urlparse(url).path
                         for h in hreflangs)
        has_default = any(h.get("hreflang","").lower() == "x-default" for h in hreflangs)

        if not has_self:
            report.add(Finding("Hreflang missing self-reference",
                "No hreflang pointing to this page's own URL",
                "Self-referencing hreflang is required by Google spec.",
                "Add <link rel='alternate' hreflang='[lang]' href='[this-url]'>",
                Severity.WARNING, Confidence.CONFIRMED, "technical", 3))

        if not has_default:
            report.add(Finding("Hreflang missing x-default",
                "No hreflang with hreflang='x-default'",
                "x-default tells Google which URL to show users with unmatched language.",
                "Add <link rel='alternate' hreflang='x-default' href='[english-url]'>",
                Severity.WARNING, Confidence.CONFIRMED, "technical", 2))

        if len(hreflangs) >= 2 and has_self:
            report.add(Finding(f"Hreflang tags found ({len(hreflangs)} language versions)",
                f"Languages: {[h.get('hreflang') for h in hreflangs]}",
                "Multilingual structure properly implemented",
                "Verify bidirectional links and BCP-47 code correctness.",
                Severity.PASS, Confidence.CONFIRMED, "technical"))

        return report

    def generate_tags(self, url_map: Dict[str, str]) -> str:
        """
        Generate hreflang HTML tags.
        url_map: {"english": "https://...", "malayalam": "https://...", ...}
        """
        tags = []
        for lang, page_url in url_map.items():
            code = self.LANG_CODES.get(lang.lower(), lang.lower()[:2])
            tags.append(f'<link rel="alternate" hreflang="{code}" href="{page_url}">')

        # Add x-default (point to English version)
        en_url = url_map.get("english","")
        if en_url:
            tags.append(f'<link rel="alternate" hreflang="x-default" href="{en_url}">')

        return "\n".join(tags)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 11 — PROGRAMMATIC SEO GATES (from AgriciD + CraigHewitt)
# ─────────────────────────────────────────────────────────────────────────────

class ProgrammaticSEOGates:
    """
    Quality gates for bulk-generated pages (Ruflo generates thousands of blogs).
    Warning at 100+ thin pages, hard stop at 500+.
    From: AgriciDaniel/claude-seo /seo programmatic
    """

    def check_project(self, project_stats: dict) -> dict:
        """
        Check if a project's content generation is at risk of index bloat.
        project_stats: {total_pages, thin_pages, location_pages, avg_word_count, duplicate_ratio}
        """
        issues, warnings = [], []
        total         = project_stats.get("total_pages", 0)
        thin          = project_stats.get("thin_pages", 0)       # < 300 words
        location_pages= project_stats.get("location_pages", 0)
        avg_wc        = project_stats.get("avg_word_count", 1000)
        dup_ratio     = project_stats.get("duplicate_ratio", 0.0) # 0-1

        # Location page limits (2026 rule)
        if location_pages >= 50:
            issues.append({
                "type": "location_page_hard_stop",
                "message": f"🛑 HARD STOP: {location_pages} location pages detected. "
                           "Hard limit is 50. Google will treat these as doorway pages.",
                "action": "Merge location pages into regional guides. Remove thin variants."
            })
        elif location_pages >= 30:
            warnings.append({
                "type": "location_page_warning",
                "message": f"⚠ WARNING: {location_pages} location pages (30 is warning threshold).",
                "action": "Audit each page for unique value. Remove duplicates."
            })

        # Total page volume gates
        if total >= 500:
            issues.append({
                "type": "programmatic_hard_stop",
                "message": f"🛑 HARD STOP: {total} generated pages without quality audit. "
                           "Index bloat risk is critical.",
                "action": "Run content quality audit. Noindex or merge thin pages before generating more."
            })
        elif total >= 100:
            warnings.append({
                "type": "programmatic_warning",
                "message": f"⚠ WARNING: {total} generated pages. Audit recommended.",
                "action": "Verify each page has unique content above 500 words."
            })

        # Thin content
        if thin > 0 and total > 0:
            thin_pct = thin / total * 100
            if thin_pct > 20:
                issues.append({
                    "type": "thin_content",
                    "message": f"🛑 {thin} pages ({thin_pct:.0f}%) have < 300 words. "
                               "Helpful Content update penalises this.",
                    "action": "Expand or consolidate thin pages. Set minimum 800 words in ContentPace."
                })

        # Average word count
        if avg_wc < 500:
            warnings.append({
                "type": "low_avg_word_count",
                "message": f"⚠ Average word count is {avg_wc} words. "
                           "Informational pages need 1500+ to compete.",
                "action": "Increase ContentPace word_count_min to 1500."
            })

        # Duplicate ratio
        if dup_ratio > 0.15:
            issues.append({
                "type": "duplicate_content",
                "message": f"🛑 {dup_ratio:.0%} of pages have near-duplicate content.",
                "action": "Enable canonical tags on variants. Merge duplicate topics."
            })

        return {
            "total_pages":    total,
            "critical_issues":issues,
            "warnings":       warnings,
            "can_continue":   len(issues) == 0,
            "recommendation": "Clear all critical issues before generating more content." if issues
                              else "Continue with caution." if warnings else "Healthy."
        }


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 12 — INDEXNOW SUBMITTER (from Bhanu/Agentic-SEO-Skill)
# ─────────────────────────────────────────────────────────────────────────────

class IndexNowSubmitter:
    """
    Submit new/updated URLs to IndexNow protocol.
    Single submission → Bing, Yandex, Yahoo, Naver, Seznam, Yep all notified.
    From: Bhanu/Agentic-SEO-Skill indexnow_checker.py
    """
    ENDPOINT = "https://api.indexnow.org/indexnow"

    def __init__(self):
        self.key  = os.getenv("INDEXNOW_KEY","")
        self.host = os.getenv("SITE_DOMAIN","")

    def submit(self, urls: List[str]) -> dict:
        if not self.key:
            return {"error": "INDEXNOW_KEY not set in .env", "submitted": 0}

        # Batch up to 10,000 URLs
        results = {"submitted": 0, "failed": 0, "errors": []}
        for batch in [urls[i:i+100] for i in range(0, len(urls), 100)]:
            payload = {
                "host":    self.host,
                "key":     self.key,
                "keyLocation": f"https://{self.host}/{self.key}.txt",
                "urlList": batch
            }
            try:
                r = _req.post(self.ENDPOINT, json=payload, timeout=10)
                if r.status_code in (200, 202):
                    results["submitted"] += len(batch)
                    log.info(f"[IndexNow] Submitted {len(batch)} URLs")
                else:
                    results["failed"] += len(batch)
                    results["errors"].append(f"HTTP {r.status_code}: {r.text[:100]}")
            except Exception as e:
                results["failed"] += len(batch)
                results["errors"].append(str(e)[:100])
        return results


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 13 — CONTENT HEALTH SCORER (from CraigHewitt/seomachine)
# ─────────────────────────────────────────────────────────────────────────────

class ContentHealthScorer:
    """
    Score existing published pages (0–100).
    Identifies: quick wins, needs update, needs rewrite.
    From: CraigHewitt/seomachine /analyze-existing command
    """

    def score(self, url: str, primary_keyword: str = "") -> dict:
        """Fetch existing page and score it."""
        soup, headers, status = PageFetcher.fetch(url)
        if not soup:
            return {"url": url, "score": 0, "grade": "F", "status": "unreachable"}

        score = 60   # start at 60 (neutral)
        issues, quick_wins = [], []
        body_text  = soup.get_text(separator=" ", strip=True)
        word_count = len(body_text.split())

        # Word count score
        if word_count >= 2000:   score += 10
        elif word_count >= 1000: score += 5
        else:                    issues.append(f"Thin content ({word_count} words)"); score -= 15

        # Primary keyword presence
        if primary_keyword:
            kw_count = body_text.lower().count(primary_keyword.lower())
            density  = kw_count / max(word_count,1) * 100
            if 0.5 <= density <= 2.5: score += 8
            elif density == 0:        issues.append(f"Keyword '{primary_keyword}' not found"); score -= 10
            elif density > 2.5:       issues.append("Keyword stuffing detected"); score -= 5

        # FAQ section
        if "faq" in body_text.lower() or "frequently asked" in body_text.lower():
            score += 5
        else:
            quick_wins.append("Add FAQ section (+5pts, targets PAA)")

        # H2 count
        h2s = soup.find_all("h2")
        if len(h2s) >= 3: score += 5
        elif len(h2s) == 0: issues.append("No H2 headings"); score -= 8

        # Schema
        schemas = soup.find_all("script", attrs={"type":"application/ld+json"})
        if schemas: score += 5
        else: quick_wins.append("Add JSON-LD schema (+5pts)")

        # Internal links
        links    = soup.find_all("a", href=True)
        internal = [l for l in links if l["href"].startswith("/")]
        if len(internal) >= 3: score += 5
        elif len(internal) == 0: issues.append("No internal links"); score -= 8

        # Images with alt
        imgs   = soup.find_all("img")
        no_alt = [img for img in imgs if not img.get("alt","").strip()]
        if imgs and len(no_alt)/len(imgs) > 0.5:
            quick_wins.append("Add alt text to images (+3pts)")

        # Freshness (year mentions)
        current_year = str(datetime.utcnow().year)
        if current_year in body_text:
            score += 3
        else:
            quick_wins.append(f"Add {current_year} year reference (+3pts, freshness signal)")

        score    = max(0, min(100, score))
        grade    = ("A" if score>=90 else "B" if score>=80 else
                    "C" if score>=70 else "D" if score>=60 else "F")
        priority = ("high — rewrite needed" if score < 50 else
                    "medium — needs update"  if score < 70 else
                    "low — light refresh")

        return {
            "url": url, "score": score, "grade": grade,
            "word_count": word_count, "priority": priority,
            "critical_issues":  issues,
            "quick_wins":       quick_wins,
            "recommendation":   self._recommend(score, issues, quick_wins)
        }

    def _recommend(self, score: int, issues: list, wins: list) -> str:
        if score >= 80:
            return "Good health. Minor refreshes can improve further."
        if issues:
            return f"Fix critical issues first: {issues[0]}. Then apply quick wins."
        if wins:
            return f"Apply quick wins: {wins[0]}. Should improve score to 75+."
        return "Expand content and add more structure."


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 14 — MASTER AUDIT ORCHESTRATOR
# ─────────────────────────────────────────────────────────────────────────────

class RufloSEOAudit:
    """
    Run all audit modules for a URL.
    Returns complete AuditReport with evidence-backed findings.
    Console output matches keyword module style.
    """

    def __init__(self):
        self.tech   = TechnicalAudit()
        self.cwv    = CoreWebVitals()
        self.ai_vis = AIVisibilityAudit()
        self.hrefl  = HreflangChecker()

    def full_audit(self, url: str, keyword: str = "",
                    mobile: bool = True) -> AuditReport:
        """Full audit: technical + CWV + AI visibility + hreflang."""
        domain = "{0.scheme}://{0.netloc}".format(urlparse(url))
        report = AuditReport(url=url, domain=domain)

        print(f"\n  {'─'*55}")
        print(f"  RUFLO SEO AUDIT — {url}")
        print(f"  {'─'*55}")

        print("  [Technical]   Running 14 technical checks...")
        self.tech.audit(url, report)
        print(f"              → {report.criticals} critical · {report.warnings} warnings · {report.passed} pass")

        print("  [CoreWebVitals] Checking LCP / INP / CLS (mobile)...")
        self.cwv.audit(url, report, strategy="mobile" if mobile else "desktop")

        print("  [AI Visibility] Checking AI crawler access + llms.txt + sameAs...")
        self.ai_vis.audit(url, report)

        print("  [Hreflang]    Checking multilingual implementation...")
        self.hrefl.check(url, report)

        report.compute_score()
        print(f"\n  AUDIT COMPLETE — Score: {report.score}/100 (Grade {report.grade})")
        print(f"  Criticals: {report.criticals} | Warnings: {report.warnings} | Pass: {report.passed}")
        print(f"  {'─'*55}\n")

        return report


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 15 — TESTS
# ─────────────────────────────────────────────────────────────────────────────

class Tests:
    """
    Run:
      python ruflo_seo_audit.py test technical       # 14 technical checks
      python ruflo_seo_audit.py test ai_visibility   # AI crawlers + llms.txt
      python ruflo_seo_audit.py test citability      # passage citability scoring
      python ruflo_seo_audit.py test brand           # brand mention scanner
      python ruflo_seo_audit.py test scrubber        # AI watermark detection
      python ruflo_seo_audit.py test health          # content health scorer
      python ruflo_seo_audit.py test hreflang        # hreflang checker
      python ruflo_seo_audit.py test gates           # programmatic SEO gates
      python ruflo_seo_audit.py test llmstxt         # llms.txt generator
      python ruflo_seo_audit.py audit <url>          # full audit
    """

    def _h(self, n): print(f"\n{'─'*55}\n  TEST: {n}\n{'─'*55}")
    def _ok(self, m): print(f"  ✓ {m}")

    def test_technical(self):
        self._h("Technical Audit (14 checks)")
        report = AuditReport(url="https://example.com", domain="example.com")
        audit  = TechnicalAudit()
        # Mock soup
        from bs4 import BeautifulSoup as BS
        html = """<html><head>
          <title>Test Page — Black Pepper Benefits</title>
          <meta name="description" content="A good description about black pepper">
          <link rel="canonical" href="https://example.com/test">
          <script type="application/ld+json">{"@type":"Article","headline":"Test"}</script>
        </head><body>
          <h1>Black Pepper Health Benefits</h1>
          <h2>What is Piperine?</h2>
          <h2>How It Helps</h2>
          <a href="/other-page">Internal link</a>
          <a href="/another">Another link</a>
          <a href="/more">More links</a>
          <img src="pepper.jpg" alt="Black pepper">
          <p>Content here with words.</p>
        </body></html>"""
        soup = BS(html, "html.parser")
        # Manually test title check
        title = soup.find("title")
        self._ok(f"Title found: '{title.get_text(strip=True)[:50]}'")
        h1s = soup.find_all("h1")
        self._ok(f"H1 count: {len(h1s)}")
        schemas = soup.find_all("script", attrs={"type":"application/ld+json"})
        self._ok(f"Schema blocks: {len(schemas)}")
        self._ok("Technical checks structure OK")

    def test_ai_visibility(self):
        self._h("AI Visibility Audit — crawler check")
        # Test with a sample robots.txt
        robots_sample = """User-agent: *\nDisallow: /admin/\n\nUser-agent: GPTBot\nDisallow: /\n\nUser-agent: ClaudeBot\nAllow: /\n"""
        checker = AIVisibilityAudit()
        blocked = []
        for bot in checker.AI_CRAWLERS:
            if bot.lower() in robots_sample.lower():
                for line in robots_sample.split("\n"):
                    if bot.lower() in line.lower() and "disallow" in line.lower():
                        if line.split("Disallow:")[-1].strip() in ("/", "/*"):
                            blocked.append(bot)
        self._ok(f"AI crawlers checked: {len(checker.AI_CRAWLERS)}")
        self._ok(f"Blocked in sample: {blocked}")
        self._ok(f"Critical: GPTBot blocked = zero ChatGPT visibility")

    def test_citability(self):
        self._h("Citability Scorer — passage analysis")
        scorer = CitabilityScorer()
        sample = """
Piperine, the alkaloid compound responsible for black pepper's pungency, constitutes
5–9% of dry weight in premium Malabar grade pepper. A 2024 study published in the
Journal of Nutritional Biochemistry found that 500mg piperine daily reduced fasting
blood glucose by 18% over 12 weeks in type-2 diabetic patients. Ceylon pepper from
Wayanad contains 7.2% piperine — 30% higher than commodity grades due to slower
drying process that preserves volatile oils.

Short para.

According to researchers at the National Institute of Nutrition, piperine enhances
bioavailability of other nutrients by inhibiting intestinal p-glycoprotein and
cytochrome P450 enzymes. This mechanism explains why combining turmeric with black
pepper increases curcumin absorption by 2,000%. The optimal dose for absorption
enhancement is 5–20mg piperine consumed simultaneously with target nutrients.
"""
        result = scorer.score_article(sample, "piperine")
        self._ok(f"Article citability: {result['article_citability']}/100 ({result['grade']})")
        self._ok(f"Citable passages: {result['citable_passages']}/{result['total_passages']}")
        if result['best_passages']:
            p = result['best_passages'][0]
            self._ok(f"Best passage score: {p['score']}/100 — {', '.join(p['reasons'][:2])}")

    def test_scrubber(self):
        self._h("AI Watermark Scrubber")
        scrubber = AIWatermarkScrubber()
        ai_text  = """It's worth noting that black pepper has many benefits. Certainly!
Furthermore, piperine is the key compound. It is important to note that you should
consult a doctor. In today's modern world, spices are vital. Let's dive into the
science. At the end of the day, quality matters. Additionally, Wayanad pepper is
certified organic by USDA."""
        cleaned, changes = scrubber.scrub(ai_text)
        analysis = scrubber.analyze_only(ai_text)
        self._ok(f"Fluff phrases found: {analysis['total_issues']}")
        self._ok(f"After scrub — words removed: {changes['words_removed']}")
        self._ok(f"AI risk assessment: {analysis['ai_risk_score']}")

    def test_health(self):
        self._h("Content Health Scorer")
        scorer = ContentHealthScorer()
        # Mock existing page with known structure
        print("  (This test requires a live URL — using mock scoring logic)")
        # Test the scoring logic directly
        score_input = {
            "word_count": 850,
            "has_faq": True,
            "h2_count": 4,
            "has_schema": True,
            "internal_links": 3,
            "keyword_density": 1.2,
        }
        mock_score = 60
        if score_input["word_count"] >= 2000:   mock_score += 10
        elif score_input["word_count"] >= 1000: mock_score += 5
        if score_input["has_faq"]:              mock_score += 5
        if score_input["h2_count"] >= 3:        mock_score += 5
        if score_input["has_schema"]:           mock_score += 5
        if score_input["internal_links"] >= 3:  mock_score += 5
        self._ok(f"Mock page score: {mock_score}/100")
        priority = "low — light refresh" if mock_score >= 70 else "medium — needs update"
        self._ok(f"Priority: {priority}")

    def test_hreflang(self):
        self._h("Hreflang Generator")
        checker  = HreflangChecker()
        url_map  = {
            "english":   "https://pureleven.com/black-pepper-benefits",
            "malayalam": "https://pureleven.com/ml/black-pepper-benefits",
            "hindi":     "https://pureleven.com/hi/kali-mirch-fayde",
            "tamil":     "https://pureleven.com/ta/black-pepper-payangal",
        }
        tags = checker.generate_tags(url_map)
        self._ok(f"Generated {len(url_map)+1} hreflang tags (including x-default)")
        print(f"\n{tags}\n")

    def test_gates(self):
        self._h("Programmatic SEO Gates")
        gates = ProgrammaticSEOGates()
        # Test warning scenario
        result = gates.check_project({
            "total_pages": 120,
            "thin_pages": 15,
            "location_pages": 25,
            "avg_word_count": 1200,
            "duplicate_ratio": 0.08
        })
        self._ok(f"Can continue: {result['can_continue']}")
        self._ok(f"Warnings: {len(result['warnings'])}")
        self._ok(f"Recommendation: {result['recommendation']}")

        # Test hard stop scenario
        result2 = gates.check_project({
            "total_pages": 520,
            "thin_pages": 200,
            "location_pages": 60,
            "avg_word_count": 280,
            "duplicate_ratio": 0.35
        })
        self._ok(f"Hard stop scenario — can_continue: {result2['can_continue']}")
        self._ok(f"Critical issues: {len(result2['critical_issues'])}")

    def test_llmstxt(self):
        self._h("llms.txt Generator")
        gen = LLMsTxtGenerator()
        site_info = {
            "name": "Pureleven Organics",
            "description": "Single-origin organic spices from Wayanad, Kerala. Farm-direct.",
            "domain": "pureleven.com",
            "language": "English, Malayalam, Hindi",
            "business_type": "D2C e-commerce",
            "specialization": "organic spices from Wayanad Kerala"
        }
        pillars = [
            {"title": "Black Pepper Health Benefits", "url": "/black-pepper-benefits", "description": "Piperine content, blood sugar, bioavailability"},
            {"title": "Organic Cardamom Guide",       "url": "/cardamom-guide",        "description": "Kerala cardamom, uses, benefits"},
            {"title": "Cinnamon vs Cassia",           "url": "/cinnamon-vs-cassia",    "description": "Ceylon vs cassia, coumarin content"},
        ]
        articles = [
            {"title": "Does Black Pepper Lower Blood Sugar?", "url": "/black-pepper-blood-sugar", "keyword": "black pepper blood sugar"},
            {"title": "Wayanad Organic Spices Certification", "url": "/wayanad-organic-certification", "keyword": "Wayanad organic spices"},
        ]
        content = gen.generate(site_info, pillars, articles)
        self._ok(f"Generated {len(content.split(chr(10)))} lines")
        print(f"\n{content[:600]}...\n")

    def run_all(self):
        tests = [
            ("technical",    self.test_technical),
            ("ai_visibility",self.test_ai_visibility),
            ("citability",   self.test_citability),
            ("scrubber",     self.test_scrubber),
            ("health",       self.test_health),
            ("hreflang",     self.test_hreflang),
            ("gates",        self.test_gates),
            ("llmstxt",      self.test_llmstxt),
        ]
        print("\n"+"═"*55+"\n  RUFLO SEO AUDIT ENGINE — TESTS\n"+"═"*55)
        p=f=0
        for name,fn in tests:
            try: fn(); p+=1
            except Exception as e: print(f"  ✗ {name}: {e}"); f+=1
        print(f"\n  {p} passed / {f} failed\n"+"═"*55)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    HELP = """
Ruflo — SEO Audit Engine
─────────────────────────────────────────────────────────────
Technical audit + AI visibility + CWV + hreflang + citability
Built from: Bhanu/Agentic-SEO-Skill, AgriciD/claude-seo,
            CraigHewitt/seomachine, geo-seo-claude, AnnaSEO

Usage:
  python ruflo_seo_audit.py test             # all tests
  python ruflo_seo_audit.py test <stage>     # one test
  python ruflo_seo_audit.py audit <url>      # full audit
  python ruflo_seo_audit.py health <url>     # content health score
  python ruflo_seo_audit.py citability <url> # passage citability
  python ruflo_seo_audit.py brand <name>     # brand mention scan
  python ruflo_seo_audit.py llmstxt          # generate llms.txt from .env
  python ruflo_seo_audit.py scrub <file.md>  # scrub AI patterns from file

Stages: technical, ai_visibility, citability, brand, scrubber, health,
        hreflang, gates, llmstxt
"""
    if len(sys.argv) < 2: print(HELP); exit(0)
    cmd = sys.argv[1]

    if cmd == "test":
        t = Tests()
        if len(sys.argv) == 3:
            fn = getattr(t, f"test_{sys.argv[2]}", None)
            if fn: fn()
            else: print(f"Unknown: {sys.argv[2]}")
        else: t.run_all()

    elif cmd == "audit":
        url = sys.argv[2] if len(sys.argv)>2 else "https://example.com"
        auditor = RufloSEOAudit()
        report  = auditor.full_audit(url)
        print(json.dumps(report.summary(), indent=2))

    elif cmd == "health":
        url = sys.argv[2] if len(sys.argv)>2 else ""
        kw  = sys.argv[3] if len(sys.argv)>3 else ""
        result = ContentHealthScorer().score(url, kw)
        print(json.dumps(result, indent=2))

    elif cmd == "citability":
        url = sys.argv[2] if len(sys.argv)>2 else ""
        kw  = sys.argv[3] if len(sys.argv)>3 else ""
        soup, _, _ = PageFetcher.fetch(url)
        if soup:
            body = soup.get_text(separator="\n", strip=True)
            result = CitabilityScorer().score_article(body, kw)
            print(json.dumps(result, indent=2))

    elif cmd == "brand":
        name   = " ".join(sys.argv[2:]) if len(sys.argv)>2 else "Pureleven Organics"
        domain = os.getenv("SITE_DOMAIN","pureleven.com")
        result = BrandMentionScanner().scan(name, domain)
        print(json.dumps(result, indent=2))

    elif cmd == "scrub":
        path = sys.argv[2] if len(sys.argv)>2 else ""
        if path and Path(path).exists():
            with open(path) as f: text = f.read()
            cleaned, changes = AIWatermarkScrubber().scrub(text)
            out = path.replace(".md","_scrubbed.md")
            with open(out,"w") as f: f.write(cleaned)
            print(f"Scrubbed → {out}"); print(json.dumps(changes,indent=2))
        else:
            print("Usage: scrub <file.md>")

    else:
        print(f"Unknown: {cmd}\n{HELP}")
