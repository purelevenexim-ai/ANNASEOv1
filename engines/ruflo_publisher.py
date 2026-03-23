"""
================================================================================
RUFLO — PUBLISHING ENGINE
================================================================================
Publishes frozen articles to WordPress and/or Shopify — one at a time,
at their scheduled datetime. Never in bulk. Never in parallel.

Philosophy:
  - One article goes out. System waits. Confirms live. Moves to next.
  - If publish fails → retry up to 3 times → mark failed → skip to next.
  - Console output for every step (mirrors keyword module style).
  - Scheduler runs as background loop — checks every 60 seconds.
  - Each article can target WordPress, Shopify, or both.

WordPress integration:
  - WP REST API (/wp-json/wp/v2/posts)
  - App password auth (no plugin needed)
  - Injects JSON-LD schema into post head via custom field
  - Sets Yoast/RankMath meta via REST API
  - Pings Google Indexing API after publish

Shopify integration:
  - Shopify Admin REST API (/admin/api/2024-01/blogs/{blog_id}/articles)
  - API token auth
  - Maps article to correct blog (by pillar)
  - Injects metafields for SEO title + description
  - Sets published_at for scheduled visibility

Queue:
  - SQLite-backed queue (no Redis needed)
  - Reads from content_blogs table where status='scheduled' AND scheduled_date <= now
  - Processes in order: earliest scheduled_date first
  - One-at-a-time: next article only after previous confirmed live
  - Configurable delay between publishes (default: 30 seconds)
================================================================================
"""

from __future__ import annotations

import os, json, re, time, sqlite3, hashlib, logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger("ruflo.publisher")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(name)s] %(message)s")

import requests as _req


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1 — CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

class Cfg:
    # WordPress
    WP_URL          = os.getenv("WP_URL", "")           # https://yoursite.com
    WP_USERNAME     = os.getenv("WP_USERNAME", "")
    WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD", "")  # Settings → App Passwords

    # Shopify
    SHOPIFY_STORE   = os.getenv("SHOPIFY_STORE", "")    # yourstore.myshopify.com
    SHOPIFY_TOKEN   = os.getenv("SHOPIFY_TOKEN", "")    # Admin API access token
    SHOPIFY_BLOG_ID = os.getenv("SHOPIFY_BLOG_ID", "")  # default blog ID

    # Queue behaviour
    DELAY_BETWEEN   = int(os.getenv("PUBLISH_DELAY_SEC", "30"))  # seconds between publishes
    MAX_RETRIES     = int(os.getenv("PUBLISH_MAX_RETRIES", "3"))
    RETRY_DELAY     = int(os.getenv("PUBLISH_RETRY_DELAY_SEC", "60"))
    SCHEDULER_TICK  = int(os.getenv("SCHEDULER_TICK_SEC", "60"))  # how often to check queue

    # DB
    DB_PATH         = Path(os.getenv("RUFLO_DB", "./ruflo_data/ruflo.db"))
    ARTICLE_DIR     = Path(os.getenv("RUFLO_DIR", "./ruflo_data")) / "articles"

    @classmethod
    def wp_configured(cls) -> bool:
        return bool(cls.WP_URL and cls.WP_USERNAME and cls.WP_APP_PASSWORD)

    @classmethod
    def shopify_configured(cls) -> bool:
        return bool(cls.SHOPIFY_STORE and cls.SHOPIFY_TOKEN)


class Platform(str, Enum):
    WORDPRESS = "wordpress"
    SHOPIFY   = "shopify"
    BOTH      = "both"


class PublishStatus(str, Enum):
    SCHEDULED  = "scheduled"
    PUBLISHING = "publishing"
    LIVE       = "live"
    FAILED     = "failed"
    RETRYING   = "retrying"
    SKIPPED    = "skipped"


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2 — DATA MODELS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ArticlePayload:
    """One article ready to publish."""
    article_id:       str
    title:            str
    slug:             str
    body:             str          # HTML or markdown
    meta_title:       str
    meta_description: str
    schema_json:      str          # JSON-LD Article schema
    faq_schema_json:  str          # JSON-LD FAQPage schema (may be empty)
    keyword:          str
    pillar:           str
    language:         str
    scheduled_date:   str          # ISO datetime
    platform:         Platform
    wp_category_id:   Optional[int] = None
    wp_tag_ids:       List[int]    = field(default_factory=list)
    shopify_blog_id:  str          = ""
    shopify_tags:     List[str]    = field(default_factory=list)
    featured_image_url: str        = ""


@dataclass
class PublishResult:
    article_id:    str
    platform:      Platform
    status:        PublishStatus
    live_url:      str          = ""
    platform_id:   str          = ""  # WP post ID or Shopify article ID
    error:         str          = ""
    attempt:       int          = 1
    published_at:  str          = ""


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3 — CONSOLE LOGGER (mirrors keyword module style)
# ─────────────────────────────────────────────────────────────────────────────

class Console:
    COLORS = {
        "success": "\033[92m",  # green
        "info":    "\033[94m",  # blue
        "data":    "\033[95m",  # magenta
        "warning": "\033[93m",  # amber
        "error":   "\033[91m",  # red
        "sep":     "\033[90m",  # gray
        "hand":    "\033[37m",  # light gray
    }
    RESET = "\033[0m"

    @classmethod
    def log(cls, engine: str, level: str, msg: str, data: dict = None):
        ts      = datetime.utcnow().strftime("%H:%M:%S")
        col     = cls.COLORS.get(level, "")
        icon    = {"success":"✓","info":"→","data":"·","warning":"⚠",
                   "error":"✗","sep":"─","hand":"⟶"}.get(level, "·")
        tag     = f"[{engine:<14}]"
        line    = f"  {ts} {col}{tag} {icon} {msg}{cls.RESET}"
        print(line)
        if data:
            for k, v in list(data.items())[:4]:
                print(f"  {'':>10} {cls.COLORS['data']}  · {k}: {v}{cls.RESET}")


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4 — DATABASE QUEUE
# ─────────────────────────────────────────────────────────────────────────────

class PublishQueue:
    """
    SQLite-backed publish queue.
    Reads content_blogs and publish_log tables.
    Safe for single-process use — no concurrent access issues.
    """

    def __init__(self):
        Cfg.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(Cfg.DB_PATH), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self):
        self._db.executescript("""
        CREATE TABLE IF NOT EXISTS content_blogs (
            id            TEXT PRIMARY KEY,
            project_id    TEXT,
            title         TEXT,
            slug          TEXT,
            body          TEXT,
            meta_title    TEXT,
            meta_desc     TEXT,
            schema_json   TEXT DEFAULT '',
            faq_schema    TEXT DEFAULT '',
            keyword       TEXT,
            pillar        TEXT DEFAULT '',
            language      TEXT DEFAULT 'english',
            platform      TEXT DEFAULT 'wordpress',
            scheduled_date TEXT,
            status        TEXT DEFAULT 'scheduled',
            frozen        INTEGER DEFAULT 0,
            published_url TEXT DEFAULT '',
            wp_category_id INTEGER,
            shopify_blog_id TEXT DEFAULT '',
            retry_count   INTEGER DEFAULT 0,
            last_error    TEXT DEFAULT '',
            created_at    TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS publish_log (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id    TEXT,
            platform      TEXT,
            attempt       INTEGER DEFAULT 1,
            status        TEXT,
            live_url      TEXT DEFAULT '',
            platform_id   TEXT DEFAULT '',
            error_msg     TEXT DEFAULT '',
            published_at  TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """)
        self._db.commit()

    def next_due(self) -> Optional[sqlite3.Row]:
        """
        Return the single next article due for publishing.
        Conditions: status=scheduled AND frozen=1 AND scheduled_date <= now
        Ordered by scheduled_date ASC — earliest first.
        """
        now = datetime.utcnow().isoformat()
        return self._db.execute("""
            SELECT * FROM content_blogs
            WHERE status = 'scheduled'
              AND frozen = 1
              AND scheduled_date <= ?
            ORDER BY scheduled_date ASC
            LIMIT 1
        """, (now,)).fetchone()

    def mark_publishing(self, article_id: str):
        self._db.execute(
            "UPDATE content_blogs SET status=? WHERE id=?",
            (PublishStatus.PUBLISHING.value, article_id)
        )
        self._db.commit()

    def mark_live(self, article_id: str, url: str):
        self._db.execute(
            "UPDATE content_blogs SET status=?, published_url=? WHERE id=?",
            (PublishStatus.LIVE.value, url, article_id)
        )
        self._db.commit()

    def mark_failed(self, article_id: str, error: str, retry_count: int):
        status = (PublishStatus.RETRYING.value
                  if retry_count < Cfg.MAX_RETRIES
                  else PublishStatus.FAILED.value)
        self._db.execute("""
            UPDATE content_blogs
            SET status=?, retry_count=?, last_error=?
            WHERE id=?
        """, (status, retry_count, error[:500], article_id))
        self._db.commit()

    def mark_retry_ready(self, article_id: str):
        """Reset retrying → scheduled so scheduler picks it up again."""
        self._db.execute(
            "UPDATE content_blogs SET status='scheduled' WHERE id=? AND status='retrying'",
            (article_id,)
        )
        self._db.commit()

    def log_result(self, result: PublishResult):
        self._db.execute("""
            INSERT INTO publish_log
            (article_id, platform, attempt, status, live_url, platform_id, error_msg, published_at)
            VALUES (?,?,?,?,?,?,?,?)
        """, (
            result.article_id, result.platform.value, result.attempt,
            result.status.value, result.live_url, result.platform_id,
            result.error, result.published_at or datetime.utcnow().isoformat()
        ))
        self._db.commit()

    def pending_count(self) -> int:
        now = datetime.utcnow().isoformat()
        row = self._db.execute(
            "SELECT COUNT(*) FROM content_blogs WHERE status='scheduled' AND frozen=1 AND scheduled_date<=?",
            (now,)
        ).fetchone()
        return row[0] if row else 0

    def add_article(self, article: ArticlePayload):
        """Insert or replace article in queue."""
        self._db.execute("""
            INSERT OR REPLACE INTO content_blogs
            (id, title, slug, body, meta_title, meta_desc, schema_json, faq_schema,
             keyword, pillar, language, platform, scheduled_date, status, frozen,
             wp_category_id, shopify_blog_id)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            article.article_id, article.title, article.slug, article.body,
            article.meta_title, article.meta_description,
            article.schema_json, article.faq_schema_json,
            article.keyword, article.pillar, article.language,
            article.platform.value, article.scheduled_date,
            PublishStatus.SCHEDULED.value, 1,
            article.wp_category_id, article.shopify_blog_id
        ))
        self._db.commit()

    def to_payload(self, row: sqlite3.Row) -> ArticlePayload:
        return ArticlePayload(
            article_id=row["id"], title=row["title"], slug=row["slug"],
            body=row["body"], meta_title=row["meta_title"],
            meta_description=row["meta_desc"],
            schema_json=row["schema_json"] or "",
            faq_schema_json=row["faq_schema"] or "",
            keyword=row["keyword"], pillar=row["pillar"] or "",
            language=row["language"] or "english",
            platform=Platform(row["platform"] or "wordpress"),
            scheduled_date=row["scheduled_date"],
            wp_category_id=row["wp_category_id"],
            shopify_blog_id=row["shopify_blog_id"] or Cfg.SHOPIFY_BLOG_ID,
        )


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5 — WORDPRESS PUBLISHER
# ─────────────────────────────────────────────────────────────────────────────

class WordPressPublisher:
    """
    Publishes one article to WordPress via REST API.
    Auth: Application Password (Settings → Users → Application Passwords).
    No plugin required.
    """

    def __init__(self):
        self.base    = Cfg.WP_URL.rstrip("/")
        self.session = _req.Session()
        import base64
        cred = base64.b64encode(
            f"{Cfg.WP_USERNAME}:{Cfg.WP_APP_PASSWORD}".encode()
        ).decode()
        self.session.headers.update({
            "Authorization": f"Basic {cred}",
            "Content-Type":  "application/json",
            "User-Agent":    "RufloPublisher/1.0",
        })

    def publish(self, article: ArticlePayload,
                attempt: int = 1) -> PublishResult:
        """Publish one article. Returns PublishResult."""
        Console.log("WordPress", "info",
                    f"Publishing: '{article.title[:55]}'  (attempt {attempt})")

        # Build HTML body with schema injected
        body_html = self._build_html(article)

        # Map language to WP locale if multi-language plugin active
        lang_tag = article.language if article.language != "english" else ""

        payload: Dict[str, Any] = {
            "title":       article.meta_title or article.title,
            "content":     body_html,
            "status":      "publish",
            "slug":        article.slug or self._slugify(article.title),
            "categories":  [article.wp_category_id] if article.wp_category_id else [],
            "tags":        article.wp_tag_ids or [],
            "meta": {
                # Yoast SEO fields
                "_yoast_wpseo_title":       article.meta_title,
                "_yoast_wpseo_metadesc":    article.meta_description,
                "_yoast_wpseo_focuskw":     article.keyword,
                # RankMath fields (also set, in case RankMath is active)
                "rank_math_title":          article.meta_title,
                "rank_math_description":    article.meta_description,
                "rank_math_focus_keyword":  article.keyword,
                # Canonical
                "_yoast_wpseo_canonical":   self._build_canonical(article),
            }
        }

        if lang_tag:
            payload["lang"] = lang_tag

        try:
            r = self.session.post(
                f"{self.base}/wp-json/wp/v2/posts",
                json=payload, timeout=30
            )
            r.raise_for_status()
            data     = r.json()
            post_id  = str(data.get("id", ""))
            live_url = data.get("link", "")

            Console.log("WordPress", "success",
                        f"Published · ID: {post_id} · {live_url}")

            # Ping Google Indexing API (fire and forget)
            self._ping_indexing(live_url)

            return PublishResult(
                article_id=article.article_id, platform=Platform.WORDPRESS,
                status=PublishStatus.LIVE, live_url=live_url,
                platform_id=post_id, attempt=attempt,
                published_at=datetime.utcnow().isoformat()
            )

        except _req.HTTPError as e:
            err = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
            Console.log("WordPress", "error", f"Failed: {err}")
            return PublishResult(
                article_id=article.article_id, platform=Platform.WORDPRESS,
                status=PublishStatus.FAILED, error=err, attempt=attempt
            )
        except Exception as e:
            Console.log("WordPress", "error", f"Exception: {e}")
            return PublishResult(
                article_id=article.article_id, platform=Platform.WORDPRESS,
                status=PublishStatus.FAILED, error=str(e), attempt=attempt
            )

    def _build_html(self, article: ArticlePayload) -> str:
        """Inject JSON-LD schemas into body as <script> tags at bottom."""
        schemas = []
        if article.schema_json:
            schemas.append(article.schema_json)
        if article.faq_schema_json:
            schemas.append(article.faq_schema_json)

        schema_html = "\n".join(
            f'<script type="application/ld+json">{s}</script>'
            for s in schemas if s
        )

        # Convert markdown to basic HTML if body contains markdown headers
        body = self._md_to_html(article.body)
        return body + ("\n" + schema_html if schema_html else "")

    def _md_to_html(self, text: str) -> str:
        """Minimal markdown → HTML conversion."""
        lines, out = text.split("\n"), []
        for line in lines:
            if line.startswith("### "):
                out.append(f"<h3>{line[4:]}</h3>")
            elif line.startswith("## "):
                out.append(f"<h2>{line[3:]}</h2>")
            elif line.startswith("# "):
                out.append(f"<h1>{line[2:]}</h1>")
            elif re.match(r"^\|.+\|$", line):
                out.append(line)  # preserve markdown tables for WP renderer
            else:
                out.append(line)
        html = "\n".join(out)
        # Bold and italic
        html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
        html = re.sub(r"\*(.+?)\*",     r"<em>\1</em>",         html)
        # Inline links
        html = re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2">\1</a>', html)
        # Wrap paragraphs
        paras = re.split(r"\n\n+", html)
        result = []
        for p in paras:
            p = p.strip()
            if not p:
                continue
            if p.startswith("<h") or p.startswith("<ul") or p.startswith("<ol") or p.startswith("<script"):
                result.append(p)
            else:
                result.append(f"<p>{p}</p>")
        return "\n".join(result)

    def _slugify(self, title: str) -> str:
        slug = re.sub(r"[^\w\s-]","",title.lower())
        return re.sub(r"[-\s]+","-",slug).strip("-")[:80]

    def _build_canonical(self, article: ArticlePayload) -> str:
        if Cfg.WP_URL:
            return f"{Cfg.WP_URL.rstrip('/')}/{self._slugify(article.title)}/"
        return ""

    def _ping_indexing(self, url: str):
        """Fire-and-forget Google Indexing API ping."""
        try:
            _req.post(
                "https://indexing.googleapis.com/v3/urlNotifications:publish",
                json={"url": url, "type": "URL_UPDATED"},
                timeout=5
            )
        except Exception:
            pass  # non-critical


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6 — SHOPIFY PUBLISHER
# ─────────────────────────────────────────────────────────────────────────────

class ShopifyPublisher:
    """
    Publishes one article to Shopify via Admin REST API.
    Auth: Private app API token (Admin API access token).
    Target: Shopify Blogs → Articles endpoint.

    Endpoint: POST /admin/api/2024-01/blogs/{blog_id}/articles.json
    """

    API_VERSION = "2024-01"

    def __init__(self):
        self.store   = Cfg.SHOPIFY_STORE.replace("https://","").rstrip("/")
        self.token   = Cfg.SHOPIFY_TOKEN
        self.session = _req.Session()
        self.session.headers.update({
            "X-Shopify-Access-Token": self.token,
            "Content-Type":           "application/json",
            "User-Agent":             "RufloPublisher/1.0",
        })

    def _base(self, blog_id: str) -> str:
        return (f"https://{self.store}/admin/api/{self.API_VERSION}"
                f"/blogs/{blog_id}/articles.json")

    def publish(self, article: ArticlePayload,
                attempt: int = 1) -> PublishResult:
        """Publish one article to Shopify blog."""
        blog_id = article.shopify_blog_id or Cfg.SHOPIFY_BLOG_ID
        if not blog_id:
            return PublishResult(
                article_id=article.article_id, platform=Platform.SHOPIFY,
                status=PublishStatus.FAILED,
                error="SHOPIFY_BLOG_ID not set — set env var or pass shopify_blog_id",
                attempt=attempt
            )

        Console.log("Shopify", "info",
                    f"Publishing: '{article.title[:55]}'  (attempt {attempt})")

        # Build body HTML with schema
        body_html = self._build_html(article)

        # Shopify article payload
        payload = {
            "article": {
                "title":       article.title,
                "body_html":   body_html,
                "summary_html":article.meta_description,
                "tags":        ", ".join(article.shopify_tags or [article.keyword, article.pillar]),
                "published":   True,
                "published_at": article.scheduled_date + "Z"
                                if not article.scheduled_date.endswith("Z")
                                else article.scheduled_date,
                "metafields": [
                    {
                        "namespace": "seo",
                        "key":       "title",
                        "value":     article.meta_title or article.title,
                        "type":      "single_line_text_field"
                    },
                    {
                        "namespace": "seo",
                        "key":       "description",
                        "value":     article.meta_description,
                        "type":      "multi_line_text_field"
                    },
                    {
                        "namespace": "ruflo",
                        "key":       "keyword",
                        "value":     article.keyword,
                        "type":      "single_line_text_field"
                    },
                    {
                        "namespace": "ruflo",
                        "key":       "pillar",
                        "value":     article.pillar,
                        "type":      "single_line_text_field"
                    },
                ]
            }
        }

        # Add featured image if provided
        if article.featured_image_url:
            payload["article"]["image"] = {"src": article.featured_image_url}

        try:
            r = self.session.post(
                self._base(blog_id), json=payload, timeout=30
            )
            r.raise_for_status()
            data       = r.json().get("article", {})
            article_id = str(data.get("id",""))
            handle     = data.get("handle","")
            live_url   = (f"https://{self.store}/blogs/"
                          f"{data.get('blog_id',blog_id)}/{handle}")

            Console.log("Shopify", "success",
                        f"Published · ID: {article_id} · {live_url}")

            return PublishResult(
                article_id=article.article_id, platform=Platform.SHOPIFY,
                status=PublishStatus.LIVE, live_url=live_url,
                platform_id=article_id, attempt=attempt,
                published_at=datetime.utcnow().isoformat()
            )

        except _req.HTTPError as e:
            err = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
            Console.log("Shopify", "error", f"Failed: {err}")
            return PublishResult(
                article_id=article.article_id, platform=Platform.SHOPIFY,
                status=PublishStatus.FAILED, error=err, attempt=attempt
            )
        except Exception as e:
            Console.log("Shopify", "error", f"Exception: {e}")
            return PublishResult(
                article_id=article.article_id, platform=Platform.SHOPIFY,
                status=PublishStatus.FAILED, error=str(e), attempt=attempt
            )

    def _build_html(self, article: ArticlePayload) -> str:
        """Build HTML body with schema tags for Shopify."""
        body = self._md_to_html(article.body)
        schemas = [s for s in [article.schema_json, article.faq_schema_json] if s]
        schema_html = "\n".join(
            f'<script type="application/ld+json">{s}</script>'
            for s in schemas
        )
        return body + ("\n" + schema_html if schema_html else "")

    def _md_to_html(self, text: str) -> str:
        """Same minimal markdown converter as WordPress."""
        lines, out = text.split("\n"), []
        for line in lines:
            if line.startswith("### "):   out.append(f"<h3>{line[4:]}</h3>")
            elif line.startswith("## "): out.append(f"<h2>{line[3:]}</h2>")
            elif line.startswith("# "):  out.append(f"<h1>{line[2:]}</h1>")
            else: out.append(line)
        html = "\n".join(out)
        html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
        html = re.sub(r"\*(.+?)\*",     r"<em>\1</em>", html)
        html = re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2">\1</a>', html)
        paras, result = re.split(r"\n\n+", html), []
        for p in paras:
            p = p.strip()
            if not p: continue
            if p.startswith("<h") or p.startswith("<script"): result.append(p)
            else: result.append(f"<p>{p}</p>")
        return "\n".join(result)

    def get_blogs(self) -> List[dict]:
        """List available blogs on this Shopify store."""
        try:
            r = self.session.get(
                f"https://{self.store}/admin/api/{self.API_VERSION}/blogs.json",
                timeout=10
            )
            r.raise_for_status()
            return r.json().get("blogs", [])
        except Exception as e:
            Console.log("Shopify", "error", f"Could not list blogs: {e}")
            return []


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 7 — PUBLISH SCHEDULER (one at a time)
# ─────────────────────────────────────────────────────────────────────────────

class PublishScheduler:
    """
    Main scheduler loop.
    Checks queue every SCHEDULER_TICK seconds.
    Processes ONE article at a time — waits for confirmation before next.
    Never publishes two articles simultaneously.

    Usage:
        scheduler = PublishScheduler()
        scheduler.run()          # blocking loop (run in thread/process)
        scheduler.run_once()     # process one article from queue (for testing)
    """

    def __init__(self):
        self.queue   = PublishQueue()
        self.wp      = WordPressPublisher() if Cfg.wp_configured() else None
        self.shopify = ShopifyPublisher()   if Cfg.shopify_configured() else None
        self._running= False

    def run(self):
        """Blocking scheduler loop. Call in a background thread."""
        self._running = True
        Console.log("Scheduler", "info",
                    f"Started · tick={Cfg.SCHEDULER_TICK}s · "
                    f"delay={Cfg.DELAY_BETWEEN}s between articles")
        Console.log("Scheduler", "data",
                    f"Platforms: WordPress={'✓' if self.wp else '✗ not configured'} · "
                    f"Shopify={'✓' if self.shopify else '✗ not configured'}")

        while self._running:
            try:
                self._tick()
            except Exception as e:
                Console.log("Scheduler", "error", f"Tick error: {e}")
            time.sleep(Cfg.SCHEDULER_TICK)

    def stop(self):
        self._running = False
        Console.log("Scheduler", "info", "Stopping after current article completes...")

    def _tick(self):
        """One scheduler tick — process one due article if available."""
        # Reset any retrying articles whose retry delay has passed
        self._check_retries()

        pending = self.queue.pending_count()
        if pending == 0:
            return

        Console.log("Scheduler", "info",
                    f"{pending} article(s) due — processing next...")
        self.run_once()

    def run_once(self) -> Optional[PublishResult]:
        """
        Process the single next due article.
        Returns the final PublishResult (or None if queue is empty).
        """
        row = self.queue.next_due()
        if not row:
            Console.log("Scheduler", "sep",
                        "Queue empty — nothing due right now.")
            return None

        article = self.queue.to_payload(row)
        retry   = row["retry_count"] or 0

        Console.log("Scheduler", "info",
                    f"Next: '{article.title[:60]}' | "
                    f"Platform: {article.platform.value} | "
                    f"Scheduled: {article.scheduled_date}")
        Console.log("Scheduler", "hand",
                    f"→→→ Starting publish sequence")

        self.queue.mark_publishing(article.article_id)

        result = self._publish_to_platforms(article, attempt=retry + 1)

        if result.status == PublishStatus.LIVE:
            self.queue.mark_live(article.article_id, result.live_url)
            self.queue.log_result(result)
            Console.log("Scheduler", "success",
                        f"✓ Live: {result.live_url}")
            Console.log("Scheduler", "sep",
                        f"Waiting {Cfg.DELAY_BETWEEN}s before next article...")
            time.sleep(Cfg.DELAY_BETWEEN)
        else:
            new_retry = retry + 1
            self.queue.mark_failed(article.article_id, result.error, new_retry)
            self.queue.log_result(result)
            if new_retry < Cfg.MAX_RETRIES:
                Console.log("Scheduler", "warning",
                            f"Attempt {new_retry}/{Cfg.MAX_RETRIES} failed. "
                            f"Will retry in {Cfg.RETRY_DELAY}s. Error: {result.error[:80]}")
                time.sleep(Cfg.RETRY_DELAY)
                self.queue.mark_retry_ready(article.article_id)
            else:
                Console.log("Scheduler", "error",
                            f"All {Cfg.MAX_RETRIES} attempts failed. "
                            f"Article marked FAILED — skipping to next.")
                self.queue.log_result(PublishResult(
                    article_id=article.article_id,
                    platform=article.platform,
                    status=PublishStatus.SKIPPED,
                    error=f"Skipped after {Cfg.MAX_RETRIES} failed attempts"
                ))

        return result

    def _publish_to_platforms(self, article: ArticlePayload,
                               attempt: int) -> PublishResult:
        """
        Route to the correct publisher(s) based on article.platform.
        For Platform.BOTH: publishes to WordPress first, then Shopify.
        If either fails on BOTH, returns the failed result.
        """
        Console.log("Scheduler", "sep",
                    "─────────────────────────────────────────────────")

        if article.platform == Platform.WORDPRESS:
            if not self.wp:
                return PublishResult(
                    article_id=article.article_id, platform=Platform.WORDPRESS,
                    status=PublishStatus.FAILED, attempt=attempt,
                    error="WordPress not configured. Set WP_URL, WP_USERNAME, WP_APP_PASSWORD."
                )
            return self.wp.publish(article, attempt)

        elif article.platform == Platform.SHOPIFY:
            if not self.shopify:
                return PublishResult(
                    article_id=article.article_id, platform=Platform.SHOPIFY,
                    status=PublishStatus.FAILED, attempt=attempt,
                    error="Shopify not configured. Set SHOPIFY_STORE, SHOPIFY_TOKEN."
                )
            return self.shopify.publish(article, attempt)

        elif article.platform == Platform.BOTH:
            # WordPress first
            wp_result = None
            if self.wp:
                Console.log("Scheduler", "info", "Platform: BOTH → WordPress first...")
                wp_result = self.wp.publish(article, attempt)
                if wp_result.status != PublishStatus.LIVE:
                    Console.log("Scheduler", "warning",
                                "WordPress failed — skipping Shopify for this attempt")
                    return wp_result
                Console.log("Scheduler", "info",
                            f"WordPress done. Waiting 5s before Shopify...")
                time.sleep(5)

            # Shopify second
            sh_result = None
            if self.shopify:
                Console.log("Scheduler", "info", "Publishing to Shopify...")
                sh_result = self.shopify.publish(article, attempt)

            # Return based on results
            if wp_result and sh_result:
                if sh_result.status == PublishStatus.LIVE:
                    combined_url = f"WP: {wp_result.live_url} | Shopify: {sh_result.live_url}"
                    return PublishResult(
                        article_id=article.article_id, platform=Platform.BOTH,
                        status=PublishStatus.LIVE, live_url=combined_url,
                        platform_id=f"wp:{wp_result.platform_id}|sh:{sh_result.platform_id}",
                        attempt=attempt,
                        published_at=datetime.utcnow().isoformat()
                    )
                return sh_result
            return wp_result or sh_result or PublishResult(
                article_id=article.article_id, platform=Platform.BOTH,
                status=PublishStatus.FAILED, attempt=attempt,
                error="No platform configured for BOTH mode"
            )

        return PublishResult(
            article_id=article.article_id, platform=article.platform,
            status=PublishStatus.FAILED, attempt=attempt,
            error=f"Unknown platform: {article.platform}"
        )

    def _check_retries(self):
        """Mark retrying articles as scheduled again after delay."""
        self.queue._db.execute("""
            UPDATE content_blogs
            SET status = 'scheduled'
            WHERE status = 'retrying'
              AND retry_count < ?
        """, (Cfg.MAX_RETRIES,))
        self.queue._db.commit()

    def status_report(self) -> dict:
        """Return live queue status summary."""
        db   = self.queue._db
        rows = db.execute("""
            SELECT status, COUNT(*) as cnt
            FROM content_blogs
            GROUP BY status
        """).fetchall()
        counts = {r["status"]: r["cnt"] for r in rows}

        recent = db.execute("""
            SELECT l.*, b.title
            FROM publish_log l
            JOIN content_blogs b ON l.article_id = b.id
            ORDER BY l.published_at DESC
            LIMIT 10
        """).fetchall()

        return {
            "queue_counts": counts,
            "recent_publishes": [dict(r) for r in recent],
            "wp_configured":      Cfg.wp_configured(),
            "shopify_configured": Cfg.shopify_configured(),
        }


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 8 — FASTAPI ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

try:
    from fastapi import FastAPI, BackgroundTasks, HTTPException
    from pydantic import BaseModel as PM
    import threading

    app = FastAPI(title="Ruflo Publisher", version="1.0.0",
                  description="WordPress + Shopify publish scheduler — one at a time")

    _scheduler: Optional[PublishScheduler] = None
    _sched_thread: Optional[threading.Thread] = None

    class ArticleIn(PM):
        article_id:       str
        title:            str
        slug:             str = ""
        body:             str
        meta_title:       str = ""
        meta_description: str = ""
        schema_json:      str = ""
        faq_schema_json:  str = ""
        keyword:          str = ""
        pillar:           str = ""
        language:         str = "english"
        platform:         str = "wordpress"    # wordpress | shopify | both
        scheduled_date:   str = ""             # ISO datetime, e.g. 2026-04-15T09:00:00
        wp_category_id:   int = None
        shopify_blog_id:  str = ""

    @app.on_event("startup")
    def start_scheduler():
        global _scheduler, _sched_thread
        _scheduler = PublishScheduler()
        _sched_thread = threading.Thread(target=_scheduler.run, daemon=True)
        _sched_thread.start()
        Console.log("API", "success", "Scheduler started as background thread")

    @app.on_event("shutdown")
    def stop_scheduler():
        if _scheduler:
            _scheduler.stop()

    @app.post("/api/publish/queue", tags=["Publisher"])
    def queue_article(art: ArticleIn):
        """Add an article to the publish queue. Scheduler picks it up at scheduled_date."""
        if not art.scheduled_date:
            art.scheduled_date = datetime.utcnow().isoformat()
        payload = ArticlePayload(
            article_id=art.article_id, title=art.title,
            slug=art.slug or re.sub(r"\s+","-",art.title.lower())[:80],
            body=art.body, meta_title=art.meta_title or art.title,
            meta_description=art.meta_description,
            schema_json=art.schema_json, faq_schema_json=art.faq_schema_json,
            keyword=art.keyword, pillar=art.pillar, language=art.language,
            platform=Platform(art.platform),
            scheduled_date=art.scheduled_date,
            wp_category_id=art.wp_category_id,
            shopify_blog_id=art.shopify_blog_id,
        )
        sched = _scheduler or PublishScheduler()
        sched.queue.add_article(payload)
        return {"queued": True, "article_id": art.article_id,
                "scheduled_date": art.scheduled_date, "platform": art.platform}

    @app.post("/api/publish/now/{article_id}", tags=["Publisher"])
    def publish_now(article_id: str, bg: BackgroundTasks):
        """Force-publish one article immediately (bypasses schedule)."""
        sched = _scheduler or PublishScheduler()
        row   = sched.queue._db.execute(
            "SELECT * FROM content_blogs WHERE id=?", (article_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, f"Article {article_id} not found in queue")

        def _run():
            article = sched.queue.to_payload(row)
            result  = sched._publish_to_platforms(article, attempt=1)
            if result.status == PublishStatus.LIVE:
                sched.queue.mark_live(article_id, result.live_url)
            else:
                sched.queue.mark_failed(article_id, result.error, 1)
            sched.queue.log_result(result)

        bg.add_task(_run)
        return {"publishing": True, "article_id": article_id}

    @app.get("/api/publish/status", tags=["Publisher"])
    def get_status():
        """Live queue status and recent publish log."""
        sched = _scheduler or PublishScheduler()
        return sched.status_report()

    @app.get("/api/publish/queue", tags=["Publisher"])
    def list_queue(limit: int = 20, status: str = None):
        """List articles in the publish queue."""
        sched = _scheduler or PublishScheduler()
        q     = "SELECT id,title,platform,scheduled_date,status,retry_count FROM content_blogs"
        if status:
            q += f" WHERE status='{status}'"
        q += f" ORDER BY scheduled_date ASC LIMIT {limit}"
        rows = sched.queue._db.execute(q).fetchall()
        return [dict(r) for r in rows]

    @app.delete("/api/publish/queue/{article_id}", tags=["Publisher"])
    def remove_from_queue(article_id: str):
        """Remove an article from the queue (only if not yet published)."""
        sched = _scheduler or PublishScheduler()
        sched.queue._db.execute(
            "DELETE FROM content_blogs WHERE id=? AND status NOT IN ('live','publishing')",
            (article_id,)
        )
        sched.queue._db.commit()
        return {"removed": True, "article_id": article_id}

    @app.get("/api/publish/shopify/blogs", tags=["Publisher"])
    def list_shopify_blogs():
        """List available Shopify blogs to map pillars to blog IDs."""
        if not Cfg.shopify_configured():
            raise HTTPException(400, "Shopify not configured")
        sched = _scheduler or PublishScheduler()
        return sched.shopify.get_blogs()

    @app.get("/api/health", tags=["System"])
    def health():
        return {
            "status": "ok",
            "wordpress":  Cfg.wp_configured(),
            "shopify":    Cfg.shopify_configured(),
            "scheduler":  _sched_thread.is_alive() if _sched_thread else False,
        }

except ImportError:
    pass  # FastAPI not installed — CLI mode only


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 8b — PUBLISHER ADAPTER (used by main.py)
# ─────────────────────────────────────────────────────────────────────────────

class Publisher:
    """
    Simple adapter for WordPressPublisher that accepts per-project credentials.
    Used by main.py: Publisher(wp_url=..., wp_user=..., wp_app_password=...)
    """
    def __init__(self, wp_url: str = "", wp_user: str = "", wp_app_password: str = ""):
        import base64, requests as _rq
        self._base = wp_url.rstrip("/")
        cred = base64.b64encode(f"{wp_user}:{wp_app_password}".encode()).decode()
        self._session = _rq.Session()
        self._session.headers.update({
            "Authorization": f"Basic {cred}",
            "Content-Type": "application/json",
            "User-Agent": "AnnaSEOPublisher/1.0",
        })
        self._configured = bool(wp_url and wp_user and wp_app_password)

    def publish(self, article: ArticlePayload) -> dict:
        """Publish to WordPress. Returns dict with 'url' key."""
        if not self._configured:
            return {"url": "", "error": "WordPress not configured", "status": "skipped"}
        try:
            payload = {
                "title":   article.meta_title or article.title,
                "content": article.body,
                "status":  "publish",
                "slug":    article.slug if article.slug else article.title.lower().replace(" ", "-"),
                "meta": {
                    "_yoast_wpseo_title":    article.meta_title or article.title,
                    "_yoast_wpseo_metadesc": article.meta_description or "",
                }
            }
            r = self._session.post(f"{self._base}/wp-json/wp/v2/posts", json=payload, timeout=60)
            if r.ok:
                data = r.json()
                return {"url": data.get("link", ""), "id": data.get("id", ""), "status": "published"}
            return {"url": "", "error": r.text[:200], "status": "failed"}
        except Exception as e:
            return {"url": "", "error": str(e)[:200], "status": "error"}


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 9 — TESTS
# ─────────────────────────────────────────────────────────────────────────────

class Tests:
    """
    Run:
      python ruflo_publisher.py test queue         # queue + dequeue logic
      python ruflo_publisher.py test schedule      # scheduler tick
      python ruflo_publisher.py test wp            # WordPress publish (needs creds)
      python ruflo_publisher.py test shopify       # Shopify publish (needs creds)
      python ruflo_publisher.py test both          # publish to both platforms
      python ruflo_publisher.py demo               # add 3 articles, run scheduler
    """

    SAMPLE_ARTICLE = ArticlePayload(
        article_id="art_test_001",
        title="Does Black Pepper Lower Blood Sugar? The 2026 Evidence",
        slug="black-pepper-blood-sugar-evidence",
        body="""# Does Black Pepper Lower Blood Sugar? The 2026 Evidence

Black pepper can help regulate blood sugar. Piperine, the active compound in
Malabar black pepper, activates insulin receptors and improves glucose metabolism.

**Key takeaway: Wayanad-grown black pepper contains 7.2% piperine — higher than
the national average of 4.8%.**

## What is Piperine?

What is piperine? Piperine (C₁₇H₁₉NO₃) is the alkaloid that gives black pepper
its pungency and accounts for 5–10% of dry weight in premium Malabar grades.

## How Piperine Affects Blood Sugar

According to a 2025 study in the Journal of Nutrition, 500mg piperine daily
reduced fasting blood glucose by 18% in type-2 diabetic patients over 12 weeks.

| Metric | Before | After 12 weeks |
|--------|--------|----------------|
| Fasting glucose | 142 mg/dL | 116 mg/dL |
| HbA1c | 7.8% | 6.9% |
| Insulin sensitivity | baseline | +24% |

## Our Farm Observation

In our Wayanad farm, the 2026 harvest showed exceptionally high piperine
due to 2,400mm of rainfall this monsoon — the highest in 8 years.

## Frequently Asked Questions

### How much black pepper helps with blood sugar?
Studies use 500mg piperine daily — roughly 1/4 teaspoon of ground black pepper.
Consult your doctor before using as a supplement.

### Is Malabar black pepper better than other varieties?
Yes — Tellicherry and Malabar Grade A contain 20–30% more piperine than commodity pepper.
""",
        meta_title="Black Pepper & Blood Sugar: Piperine Evidence 2026",
        meta_description="Piperine in Malabar black pepper reduces fasting blood glucose by 18% in 12 weeks. Learn the science and our 2026 farm findings from Wayanad.",
        schema_json=json.dumps({
            "@context":"https://schema.org",
            "@type":"Article",
            "headline":"Does Black Pepper Lower Blood Sugar?",
            "author":{"@type":"Person","name":"Rajiv Kumar"}
        }),
        faq_schema_json=json.dumps({
            "@context":"https://schema.org",
            "@type":"FAQPage",
            "mainEntity":[
                {"@type":"Question","name":"How much black pepper helps with blood sugar?",
                 "acceptedAnswer":{"@type":"Answer","text":"Studies use 500mg piperine daily."}}
            ]
        }),
        keyword="black pepper blood sugar",
        pillar="Black Pepper Health Benefits",
        language="english",
        platform=Platform.BOTH,
        scheduled_date=datetime.utcnow().isoformat(),
        shopify_blog_id=Cfg.SHOPIFY_BLOG_ID or "123456789",
    )

    def _h(self, n): print(f"\n{'─'*55}\n  TEST: {n}\n{'─'*55}")
    def _ok(self, m): print(f"  ✓ {m}")

    def test_queue(self):
        self._h("Queue — add, retrieve, mark live")
        q = PublishQueue()
        art = self.SAMPLE_ARTICLE
        art.scheduled_date = datetime.utcnow().isoformat()
        q.add_article(art)
        self._ok(f"Article queued: {art.article_id}")
        due = q.next_due()
        assert due is not None, "Should have one due article"
        self._ok(f"Next due: {due['title'][:40]}")
        q.mark_live(art.article_id, "https://test.com/article-1")
        due_after = q.next_due()
        self._ok(f"Queue after marking live: {'empty ✓' if due_after is None else 'still has items'}")

    def test_schedule(self):
        self._h("Scheduler — run_once with mock publishers")
        q = PublishQueue()
        art = self.SAMPLE_ARTICLE
        art.article_id  = "art_test_schedule"
        art.platform    = Platform.WORDPRESS
        art.scheduled_date = datetime.utcnow().isoformat()
        q.add_article(art)

        sched = PublishScheduler()
        sched.wp      = None   # no real WP credentials in test
        sched.shopify = None   # no real Shopify credentials in test

        # Override publisher with mock
        class MockWP:
            def publish(self, article, attempt=1):
                Console.log("MockWP", "success", f"Mock published: {article.title[:40]}")
                return PublishResult(
                    article_id=article.article_id, platform=Platform.WORDPRESS,
                    status=PublishStatus.LIVE,
                    live_url="https://mock-site.com/mock-article",
                    platform_id="9999", attempt=attempt,
                    published_at=datetime.utcnow().isoformat()
                )
        sched.wp = MockWP()
        result = sched.run_once()
        self._ok(f"Scheduler result: {result.status.value} · {result.live_url}")

    def test_wp(self):
        self._h("WordPress publish (needs credentials in .env)")
        if not Cfg.wp_configured():
            print("  ⚠ WP_URL / WP_USERNAME / WP_APP_PASSWORD not set — skipping")
            return
        wp  = WordPressPublisher()
        art = self.SAMPLE_ARTICLE
        art.platform = Platform.WORDPRESS
        result = wp.publish(art, attempt=1)
        self._ok(f"Status: {result.status.value}")
        self._ok(f"URL: {result.live_url}")
        self._ok(f"ID: {result.platform_id}")

    def test_shopify(self):
        self._h("Shopify publish (needs credentials in .env)")
        if not Cfg.shopify_configured():
            print("  ⚠ SHOPIFY_STORE / SHOPIFY_TOKEN not set — skipping")
            return
        sh  = ShopifyPublisher()
        art = self.SAMPLE_ARTICLE
        art.platform = Platform.SHOPIFY
        result = sh.publish(art, attempt=1)
        self._ok(f"Status: {result.status.value}")
        self._ok(f"URL: {result.live_url}")
        self._ok(f"ID: {result.platform_id}")

    def test_both(self):
        self._h("Publish to BOTH platforms (needs both sets of credentials)")
        if not Cfg.wp_configured() or not Cfg.shopify_configured():
            print("  ⚠ Both WP and Shopify credentials needed — skipping")
            return
        art = self.SAMPLE_ARTICLE
        art.platform = Platform.BOTH
        sched = PublishScheduler()
        result = sched._publish_to_platforms(art, attempt=1)
        self._ok(f"Combined status: {result.status.value}")
        self._ok(f"URLs: {result.live_url}")

    def demo(self):
        self._h("DEMO — 3 articles queued, scheduler processes one by one")
        q = PublishQueue()
        articles = [
            ("art_demo_001", "Black Pepper Health Benefits: Complete Guide",
             "black pepper health benefits", Platform.WORDPRESS, 0),
            ("art_demo_002", "Organic Cardamom: Why Wayanad Grade is Different",
             "organic cardamom Wayanad", Platform.SHOPIFY, 30),
            ("art_demo_003", "Malabar Black Pepper vs Vietnamese Pepper",
             "Malabar vs Vietnamese pepper", Platform.BOTH, 60),
        ]
        print(f"\n  Queueing {len(articles)} articles:")
        for aid, title, kw, plat, offset in articles:
            art = ArticlePayload(
                article_id=aid, title=title, slug=aid,
                body=f"# {title}\n\nSample body for {kw}...",
                meta_title=title[:60], meta_description=f"About {kw}",
                schema_json="", faq_schema_json="",
                keyword=kw, pillar="Black Pepper", language="english",
                platform=plat,
                scheduled_date=(datetime.utcnow() + timedelta(seconds=offset)).isoformat(),
                shopify_blog_id=Cfg.SHOPIFY_BLOG_ID or "demo_blog",
            )
            q.add_article(art)
            print(f"  + [{plat.value:12}] {title[:50]} · T+{offset}s")

        print(f"\n  Queue has {q.pending_count()} articles due now (offset=0 is immediate)")
        print(f"  Scheduler tick = {Cfg.SCHEDULER_TICK}s · delay between articles = {Cfg.DELAY_BETWEEN}s")
        print(f"\n  Running scheduler for 3 ticks (mock mode)...")

        sched = PublishScheduler()
        class MockPub:
            def __init__(self, name): self.name = name
            def publish(self, art, attempt=1):
                Console.log(f"Mock{self.name}", "success",
                            f"Published to {self.name}: {art.title[:40]}")
                return PublishResult(
                    article_id=art.article_id, platform=Platform(self.name.lower()),
                    status=PublishStatus.LIVE,
                    live_url=f"https://mock-{self.name.lower()}.com/{art.slug}",
                    platform_id=str(hash(art.article_id))[:6], attempt=attempt,
                    published_at=datetime.utcnow().isoformat()
                )
        sched.wp      = MockPub("WordPress")
        sched.shopify = MockPub("Shopify")

        for i in range(3):
            print(f"\n  ── Tick {i+1} ──")
            result = sched.run_once()
            if result:
                print(f"  Result: {result.status.value} · {result.live_url}")
            else:
                print("  Nothing due yet.")

    def run_all(self):
        print("\n"+"═"*55)
        print("  PUBLISHER ENGINE — TESTS")
        print("═"*55)
        tests = [("queue",self.test_queue),("schedule",self.test_schedule)]
        p=f=0
        for name,fn in tests:
            try: fn(); p+=1
            except Exception as e: print(f"  ✗ {name}: {e}"); f+=1
        print(f"\n  {p} passed / {f} failed\n"+"═"*55)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 10 — CLI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    HELP = """
Ruflo — Publishing Engine
────────────────────────────────────────────────────────────
WordPress + Shopify · Scheduled one by one · Retry logic · Console output

Usage:
  python ruflo_publisher.py test                # all unit tests
  python ruflo_publisher.py test <stage>        # one test (queue|schedule|wp|shopify|both)
  python ruflo_publisher.py demo                # queue 3 articles, mock-publish one by one
  python ruflo_publisher.py scheduler           # start live scheduler (blocking)
  python ruflo_publisher.py api                 # start FastAPI server on :8003
  python ruflo_publisher.py status              # show queue status

Environment (.env):
  WP_URL=https://yoursite.com
  WP_USERNAME=your_username
  WP_APP_PASSWORD=xxxx xxxx xxxx xxxx xxxx xxxx   (Settings → Users → App Passwords)

  SHOPIFY_STORE=yourstore.myshopify.com
  SHOPIFY_TOKEN=shpat_xxxxxxxxxxxxxxxxxxxx
  SHOPIFY_BLOG_ID=12345678

  PUBLISH_DELAY_SEC=30      seconds between publishes (default 30)
  PUBLISH_MAX_RETRIES=3     attempts before marking failed
  SCHEDULER_TICK_SEC=60     how often scheduler checks queue

Platform options per article:  wordpress | shopify | both
"""
    if len(sys.argv) < 2:
        print(HELP); exit(0)
    cmd = sys.argv[1]

    if cmd == "test":
        t = Tests()
        if len(sys.argv) == 3:
            fn = getattr(t, f"test_{sys.argv[2]}", None)
            if fn: fn()
            else: print(f"Unknown stage: {sys.argv[2]}")
        else: t.run_all()

    elif cmd == "demo":
        Tests().demo()

    elif cmd == "scheduler":
        Console.log("Ruflo", "info", "Starting live scheduler...")
        sched = PublishScheduler()
        sched.run()   # blocking

    elif cmd == "status":
        sched = PublishScheduler()
        report = sched.status_report()
        print(f"\n  Queue status: {report['queue_counts']}")
        print(f"  WordPress:    {'✓' if report['wp_configured'] else '✗ not configured'}")
        print(f"  Shopify:      {'✓' if report['shopify_configured'] else '✗ not configured'}")
        print(f"\n  Recent publishes:")
        for r in report['recent_publishes'][:5]:
            print(f"    [{r['status']:12}] {r.get('title','?')[:40]} → {r.get('live_url','?')[:50]}")

    elif cmd == "api":
        try:
            import uvicorn
            Console.log("Ruflo", "info", "Publisher API at http://localhost:8003")
            Console.log("Ruflo", "info", "Docs at http://localhost:8003/docs")
            uvicorn.run("ruflo_publisher:app", host="0.0.0.0", port=8003, reload=True)
        except ImportError:
            print("pip install uvicorn")
    else:
        print(f"Unknown: {cmd}\n{HELP}")
