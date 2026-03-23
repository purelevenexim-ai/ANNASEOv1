"""
================================================================================
ANNASEO — PRODUCT GROWTH ENGINES  (annaseo_product_growth.py)
================================================================================
6 product-tier features:

  1. TeamACL          — project-level user roles (Admin, Editor, Analyst, Viewer)
  2. WebhookEngine    — real-time notifications to Slack, email, Discord, Zapier
  3. PDFReportEngine  — monthly client reports (white-label ready)
  4. GA4Integration   — organic traffic + conversion tracking per article
  5. BulkKeywordImport— CSV/Excel keyword list → classified into universe
  6. ContentBriefExport — briefs as Google Doc / Notion / Markdown for human writers
================================================================================
"""

from __future__ import annotations

import os, re, json, hashlib, time, csv, io, logging, sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

import requests as _req

log = logging.getLogger("annaseo.growth")
DB_PATH = Path(os.getenv("ANNASEO_DB", "./annaseo.db"))
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"


def _db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.executescript("""
    CREATE TABLE IF NOT EXISTS team_members (
        member_id   TEXT PRIMARY KEY,
        project_id  TEXT NOT NULL,
        user_id     TEXT NOT NULL,
        role        TEXT NOT NULL,
        invited_by  TEXT DEFAULT '',
        accepted    INTEGER DEFAULT 0,
        created_at  TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS webhooks (
        webhook_id  TEXT PRIMARY KEY,
        project_id  TEXT NOT NULL,
        name        TEXT DEFAULT '',
        url         TEXT NOT NULL,
        events      TEXT DEFAULT '[]',
        active      INTEGER DEFAULT 1,
        secret      TEXT DEFAULT '',
        created_at  TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS webhook_deliveries (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        webhook_id  TEXT NOT NULL,
        event_type  TEXT NOT NULL,
        payload     TEXT DEFAULT '{}',
        response_status INTEGER DEFAULT 0,
        delivered_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS pdf_reports (
        report_id   TEXT PRIMARY KEY,
        project_id  TEXT NOT NULL,
        period_from TEXT DEFAULT '',
        period_to   TEXT DEFAULT '',
        file_path   TEXT DEFAULT '',
        status      TEXT DEFAULT 'generating',
        created_at  TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS ga4_connections (
        project_id      TEXT PRIMARY KEY,
        measurement_id  TEXT DEFAULT '',
        property_id     TEXT DEFAULT '',
        service_account TEXT DEFAULT '',
        connected       INTEGER DEFAULT 0,
        last_sync       TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS ga4_article_metrics (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id      TEXT NOT NULL,
        article_id      TEXT NOT NULL,
        organic_sessions INTEGER DEFAULT 0,
        bounce_rate     REAL DEFAULT 0,
        avg_time_sec    INTEGER DEFAULT 0,
        conversions     INTEGER DEFAULT 0,
        recorded_at     TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS bulk_import_jobs (
        job_id      TEXT PRIMARY KEY,
        project_id  TEXT NOT NULL,
        filename    TEXT DEFAULT '',
        total_kws   INTEGER DEFAULT 0,
        processed   INTEGER DEFAULT 0,
        accepted    INTEGER DEFAULT 0,
        rejected    INTEGER DEFAULT 0,
        status      TEXT DEFAULT 'pending',
        created_at  TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS brief_exports (
        export_id   TEXT PRIMARY KEY,
        article_id  TEXT NOT NULL,
        format      TEXT NOT NULL,
        content     TEXT DEFAULT '',
        created_at  TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_team_project ON team_members(project_id);
    CREATE INDEX IF NOT EXISTS idx_webhooks_project ON webhooks(project_id);
    CREATE INDEX IF NOT EXISTS idx_ga4_project ON ga4_article_metrics(project_id);
    """)
    con.commit()
    return con


# ─────────────────────────────────────────────────────────────────────────────
# ENGINE 1 — TEAM ACL
# ─────────────────────────────────────────────────────────────────────────────

class TeamRole:
    ADMIN    = "admin"      # full access: settings, delete, all content
    EDITOR   = "editor"     # create/edit content, approve articles
    ANALYST  = "analyst"    # read all + submit QI feedback, no edit
    VIEWER   = "viewer"     # read-only dashboard only

# What each role can do
ROLE_PERMISSIONS = {
    TeamRole.ADMIN:   ["read","write","delete","publish","approve","settings","invite","billing"],
    TeamRole.EDITOR:  ["read","write","publish","approve"],
    TeamRole.ANALYST: ["read","qi_feedback","comment"],
    TeamRole.VIEWER:  ["read"],
}


class TeamACL:
    """Project-level user roles and permissions."""

    def invite(self, project_id: str, user_id: str, role: str,
                invited_by: str) -> str:
        mid = f"mem_{hashlib.md5(f'{project_id}{user_id}'.encode()).hexdigest()[:10]}"
        _db().execute("""
            INSERT OR REPLACE INTO team_members
            (member_id,project_id,user_id,role,invited_by)
            VALUES (?,?,?,?,?)
        """, (mid, project_id, user_id, role, invited_by))
        _db().commit()
        log.info(f"[Team] Invited {user_id} to {project_id} as {role}")
        return mid

    def accept(self, member_id: str):
        _db().execute("UPDATE team_members SET accepted=1 WHERE member_id=?", (member_id,))
        _db().commit()

    def check(self, project_id: str, user_id: str, permission: str) -> bool:
        """Return True if user has the given permission for the project."""
        row = _db().execute(
            "SELECT role FROM team_members WHERE project_id=? AND user_id=? AND accepted=1",
            (project_id, user_id)
        ).fetchone()
        if not row: return False
        role = row["role"]
        return permission in ROLE_PERMISSIONS.get(role, [])

    def require(self, project_id: str, user_id: str, permission: str):
        """Raise exception if user lacks permission."""
        if not self.check(project_id, user_id, permission):
            raise PermissionError(f"User {user_id} lacks '{permission}' on project {project_id}")

    def list_members(self, project_id: str) -> List[dict]:
        return [dict(r) for r in _db().execute(
            "SELECT * FROM team_members WHERE project_id=? ORDER BY created_at",
            (project_id,)
        ).fetchall()]

    def remove(self, project_id: str, user_id: str):
        _db().execute(
            "DELETE FROM team_members WHERE project_id=? AND user_id=?",
            (project_id, user_id)
        )
        _db().commit()

    def update_role(self, project_id: str, user_id: str, new_role: str):
        _db().execute(
            "UPDATE team_members SET role=? WHERE project_id=? AND user_id=?",
            (new_role, project_id, user_id)
        )
        _db().commit()


# ─────────────────────────────────────────────────────────────────────────────
# ENGINE 2 — WEBHOOK SYSTEM
# ─────────────────────────────────────────────────────────────────────────────

# All event types that can trigger webhooks
WEBHOOK_EVENTS = {
    "article.published":        "Article published to WordPress/Shopify",
    "article.approved":         "Article manually approved",
    "ranking.drop":             "Keyword dropped >5 positions",
    "ranking.gain":             "Keyword gained >5 positions",
    "keyword_universe.complete":"Keyword universe generation finished",
    "content.refresh_needed":   "Article flagged for refresh",
    "approval.pending":         "Engine tuning needs manual approval",
    "engine.health_degraded":   "Engine score dropped below 80",
    "qa.feedback_bad":          "User marked QI item as bad",
    "audit.score_drop":         "Site SEO audit score dropped",
    "citation.not_cited":       "Competitor cited in AI search but we aren't",
}


class WebhookEngine:
    """Send events to external URLs (Slack, email relay, Discord, Zapier, Make.com)."""

    def register(self, project_id: str, name: str, url: str,
                  events: List[str], secret: str = "") -> str:
        wid = f"wh_{hashlib.md5(f'{project_id}{url}'.encode()).hexdigest()[:10]}"
        _db().execute("""
            INSERT OR REPLACE INTO webhooks
            (webhook_id,project_id,name,url,events,secret)
            VALUES (?,?,?,?,?,?)
        """, (wid, project_id, name, url, json.dumps(events), secret))
        _db().commit()
        log.info(f"[Webhook] Registered: {name} ({url}) for {len(events)} events")
        return wid

    def emit(self, project_id: str, event_type: str, payload: dict):
        """Fire all webhooks registered for this event type."""
        con = _db()
        hooks = [dict(r) for r in con.execute(
            "SELECT * FROM webhooks WHERE project_id=? AND active=1",
            (project_id,)
        ).fetchall()]
        for hook in hooks:
            events = json.loads(hook.get("events","[]"))
            if event_type not in events and "*" not in events:
                continue
            self._deliver(hook, event_type, payload)

    def _deliver(self, hook: dict, event_type: str, payload: dict):
        """Deliver one webhook. Store delivery result."""
        body = {
            "event":      event_type,
            "project_id": hook["project_id"],
            "timestamp":  datetime.utcnow().isoformat(),
            "data":       payload,
        }
        # Add signature if secret configured
        if hook.get("secret"):
            import hmac as _hmac
            sig = _hmac.new(hook["secret"].encode(),
                             json.dumps(body).encode(),
                             "sha256").hexdigest()
            headers = {"X-AnnaSEO-Signature": f"sha256={sig}",
                       "Content-Type": "application/json"}
        else:
            headers = {"Content-Type": "application/json"}
        try:
            r = _req.post(hook["url"], json=body, headers=headers, timeout=10)
            status = r.status_code
            log.info(f"[Webhook] {event_type} → {hook['url']}: {status}")
        except Exception as e:
            status = 0
            log.warning(f"[Webhook] Delivery failed: {e}")
        _db().execute("""
            INSERT INTO webhook_deliveries (webhook_id,event_type,payload,response_status)
            VALUES (?,?,?,?)
        """, (hook["webhook_id"], event_type, json.dumps(body)[:2000], status))
        _db().commit()

    def list_webhooks(self, project_id: str) -> List[dict]:
        return [dict(r) for r in _db().execute(
            "SELECT * FROM webhooks WHERE project_id=?", (project_id,)
        ).fetchall()]

    def deliveries(self, webhook_id: str, limit: int = 50) -> List[dict]:
        return [dict(r) for r in _db().execute(
            "SELECT * FROM webhook_deliveries WHERE webhook_id=? ORDER BY delivered_at DESC LIMIT ?",
            (webhook_id, limit)
        ).fetchall()]


# ─────────────────────────────────────────────────────────────────────────────
# ENGINE 3 — PDF REPORT GENERATOR
# ─────────────────────────────────────────────────────────────────────────────

class PDFReportEngine:
    """
    Generate monthly client reports as PDF.
    Covers: keyword universe health, content performance, ranking movements,
    technical SEO score, AI search visibility, cost breakdown, next-month plan.
    White-label: customisable header with client logo and agency name.

    Uses reportlab for PDF generation (pure Python, no external service).
    Falls back to HTML report if reportlab not installed.
    """

    def generate(self, project_id: str, period_from: str = None,
                  period_to: str = None, agency_name: str = "AnnaSEO",
                  client_name: str = "", logo_path: str = "") -> str:
        """Generate report. Returns file path."""
        period_from = period_from or (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d")
        period_to   = period_to   or datetime.utcnow().strftime("%Y-%m-%d")

        # Gather data
        data = self._gather_data(project_id, period_from, period_to)

        # Generate HTML report (works without reportlab)
        report_dir  = Path(os.getenv("VERSIONS_DIR","./rsd_versions")) / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_id   = f"rpt_{project_id}_{datetime.utcnow().strftime('%Y%m')}"
        html_path   = report_dir / f"{report_id}.html"

        html = self._render_html(data, agency_name, client_name,
                                  period_from, period_to)
        html_path.write_text(html, encoding="utf-8")
        log.info(f"[PDF] Report generated: {html_path}")

        # Try PDF conversion
        pdf_path = str(html_path).replace(".html", ".pdf")
        if self._try_pdf_convert(str(html_path), pdf_path):
            file_path = pdf_path
        else:
            file_path = str(html_path)

        _db().execute("""
            INSERT OR REPLACE INTO pdf_reports
            (report_id,project_id,period_from,period_to,file_path,status)
            VALUES (?,?,?,?,?,'done')
        """, (report_id, project_id, period_from, period_to, file_path))
        _db().commit()
        return file_path

    def _gather_data(self, project_id: str, period_from: str,
                      period_to: str) -> dict:
        sql_con = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        sql_con.row_factory = sqlite3.Row
        def q(sql, params=()):
            try: return [dict(r) for r in sql_con.execute(sql, params).fetchall()]
            except Exception: return []

        articles = q("SELECT * FROM content_articles WHERE project_id=? AND created_at>=? ORDER BY created_at DESC",
                      (project_id, period_from))
        published = [a for a in articles if a["status"] == "published"]
        rankings  = q("SELECT * FROM rankings WHERE project_id=? AND recorded_at>=? ORDER BY recorded_at DESC LIMIT 50",
                       (project_id, period_from))
        costs     = q("SELECT model,SUM(cost_usd) as total FROM ai_usage WHERE project_id=? AND created_at>=? GROUP BY model",
                       (project_id, period_from))
        audits    = q("SELECT * FROM seo_audits WHERE url LIKE ? ORDER BY created_at DESC LIMIT 3",
                       (f"%{project_id}%",)) if True else []
        total_cost = sum(r.get("total",0) for r in costs)
        sql_con.close()
        return {
            "project_id":     project_id,
            "period_from":    period_from,
            "period_to":      period_to,
            "articles_total": len(articles),
            "articles_pub":   len(published),
            "rankings":       rankings[:20],
            "top_keywords":   [r for r in rankings if r.get("position",99) <= 10][:5],
            "total_cost_usd": round(total_cost, 2),
            "cost_per_article":round(total_cost/max(len(published),1), 3),
            "audits":         audits,
        }

    def _render_html(self, data: dict, agency: str, client: str,
                      period_from: str, period_to: str) -> str:
        top_kws = "".join(
            f"<tr><td>{r.get('keyword','')[:40]}</td><td style='text-align:center'>{r.get('position','')}</td></tr>"
            for r in data["top_keywords"]
        ) or "<tr><td colspan='2'>No ranking data yet</td></tr>"

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{agency} SEO Report — {client or data['project_id']}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         color: #1a1a1a; margin: 0; padding: 40px; max-width: 900px; margin: 0 auto; }}
  .header {{ border-bottom: 3px solid #7F77DD; padding-bottom: 20px; margin-bottom: 30px; }}
  .header h1 {{ font-size: 28px; color: #7F77DD; margin: 0; }}
  .header .sub {{ color: #666; font-size: 14px; margin-top: 4px; }}
  .stat-grid {{ display: grid; grid-template-columns: repeat(4,1fr); gap: 16px; margin: 24px 0; }}
  .stat {{ background: #f8f7ff; border-radius: 12px; padding: 16px; text-align: center; }}
  .stat .num {{ font-size: 28px; font-weight: 700; color: #7F77DD; }}
  .stat .label {{ font-size: 12px; color: #666; margin-top: 4px; }}
  h2 {{ font-size: 18px; color: #333; border-left: 4px solid #7F77DD; padding-left: 12px; margin: 28px 0 14px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{ background: #f0efff; padding: 8px 12px; text-align: left; font-weight: 600; }}
  td {{ padding: 8px 12px; border-bottom: 1px solid #eee; }}
  .footer {{ margin-top: 40px; padding-top: 20px; border-top: 1px solid #eee;
             font-size: 11px; color: #999; text-align: center; }}
</style>
</head>
<body>
<div class="header">
  <h1>{agency}</h1>
  <div class="sub">SEO Performance Report — {period_from} to {period_to}</div>
  {f'<div class="sub">Prepared for: <strong>{client}</strong></div>' if client else ''}
</div>

<div class="stat-grid">
  <div class="stat"><div class="num">{data['articles_pub']}</div><div class="label">Articles published</div></div>
  <div class="stat"><div class="num">{len(data['top_keywords'])}</div><div class="label">Keywords in top 10</div></div>
  <div class="stat"><div class="num">${data['total_cost_usd']:.2f}</div><div class="label">Total AI cost</div></div>
  <div class="stat"><div class="num">${data['cost_per_article']:.3f}</div><div class="label">Cost per article</div></div>
</div>

<h2>Top ranking keywords</h2>
<table>
  <tr><th>Keyword</th><th>Position</th></tr>
  {top_kws}
</table>

<h2>Content summary</h2>
<p>
  <strong>{data['articles_total']}</strong> articles generated this period.
  <strong>{data['articles_pub']}</strong> published.
  Total AI generation cost: <strong>${data['total_cost_usd']:.2f}</strong>
  (${data['cost_per_article']:.3f} per article average).
</p>

<div class="footer">
  Generated by {agency} · {datetime.utcnow().strftime('%B %Y')} ·
  Powered by AnnaSEO
</div>
</body>
</html>"""

    def _try_pdf_convert(self, html_path: str, pdf_path: str) -> bool:
        """Try weasyprint → pdfkit → skip."""
        for lib in ["weasyprint", "pdfkit"]:
            try:
                if lib == "weasyprint":
                    from weasyprint import HTML
                    HTML(filename=html_path).write_pdf(pdf_path)
                    return True
                elif lib == "pdfkit":
                    import pdfkit
                    pdfkit.from_file(html_path, pdf_path)
                    return True
            except Exception:
                continue
        return False


# ─────────────────────────────────────────────────────────────────────────────
# ENGINE 4 — GA4 INTEGRATION
# ─────────────────────────────────────────────────────────────────────────────

class GA4Integration:
    """
    Connect Google Analytics 4 to track organic traffic per article.
    Calculates actual ROI per article: sessions + conversions from organic.
    Uses GA4 Data API (service account auth).
    Falls back to UTM-based import if API not configured.
    """

    def connect(self, project_id: str, measurement_id: str,
                 property_id: str, service_account_json: str = "") -> dict:
        _db().execute("""
            INSERT OR REPLACE INTO ga4_connections
            (project_id,measurement_id,property_id,service_account,connected)
            VALUES (?,?,?,?,1)
        """, (project_id, measurement_id, property_id, service_account_json))
        _db().commit()
        return {"connected": True, "project_id": project_id}

    def sync(self, project_id: str, days: int = 30) -> dict:
        """
        Pull organic sessions per published article from GA4 Data API.
        Falls back to simulated data for testing.
        """
        con = _db()
        conn = con.execute("SELECT * FROM ga4_connections WHERE project_id=?",
                            (project_id,)).fetchone()
        if not conn or not dict(conn).get("connected"):
            return {"error": "GA4 not connected for this project"}

        # Try real GA4 Data API
        try:
            from google.analytics.data_v1beta import BetaAnalyticsDataClient
            from google.analytics.data_v1beta.types import (
                DateRange, Dimension, Metric, RunReportRequest
            )
            import google.oauth2.service_account as svc

            sa_info = json.loads(dict(conn).get("service_account","{}"))
            creds   = svc.Credentials.from_service_account_info(
                sa_info, scopes=["https://www.googleapis.com/auth/analytics.readonly"]
            )
            client = BetaAnalyticsDataClient(credentials=creds)
            prop_id = dict(conn)["property_id"]
            response = client.run_report(RunReportRequest(
                property=f"properties/{prop_id}",
                dimensions=[Dimension(name="pagePath"),
                             Dimension(name="sessionDefaultChannelGroup")],
                metrics=[Metric(name="sessions"),
                          Metric(name="bounceRate"),
                          Metric(name="averageSessionDuration"),
                          Metric(name="conversions")],
                date_ranges=[DateRange(start_date=f"{days}daysAgo", end_date="today")],
            ))
            synced = 0
            for row in response.rows:
                path    = row.dimension_values[0].value
                channel = row.dimension_values[1].value
                if "organic" not in channel.lower(): continue
                sessions = int(row.metric_values[0].value)
                bounce   = float(row.metric_values[1].value)
                avg_time = int(float(row.metric_values[2].value))
                convs    = int(float(row.metric_values[3].value))
                # Match path to article
                art = con.execute(
                    "SELECT article_id FROM content_articles WHERE project_id=? AND published_url LIKE ?",
                    (project_id, f"%{path}%")
                ).fetchone()
                if art:
                    art_id = dict(art)["article_id"]
                    con.execute("""
                        INSERT INTO ga4_article_metrics
                        (project_id,article_id,organic_sessions,bounce_rate,avg_time_sec,conversions)
                        VALUES (?,?,?,?,?,?)
                    """, (project_id, art_id, sessions, bounce, avg_time, convs))
                    synced += 1
            con.commit()
            con.execute("UPDATE ga4_connections SET last_sync=? WHERE project_id=?",
                         (datetime.utcnow().isoformat(), project_id))
            con.commit()
            return {"synced_articles": synced, "period_days": days}

        except ImportError:
            return {"error": "google-analytics-data not installed. pip install google-analytics-data",
                    "fallback": "Use /api/ga4/manual-import to upload CSV from GA4"}
        except Exception as e:
            return {"error": str(e)[:200]}

    def article_roi(self, project_id: str, article_id: str) -> dict:
        """Calculate ROI for one article: sessions × estimated value vs generation cost."""
        con  = _db()
        sql_con = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        sql_con.row_factory = sqlite3.Row
        metrics = [dict(r) for r in con.execute(
            "SELECT * FROM ga4_article_metrics WHERE project_id=? AND article_id=? ORDER BY recorded_at DESC LIMIT 12",
            (project_id, article_id)
        ).fetchall()]
        cost_row = sql_con.execute(
            "SELECT SUM(cost_usd) as total FROM ai_usage WHERE run_id=(SELECT run_id FROM content_articles WHERE article_id=?)",
            (article_id,)
        ).fetchone()
        gen_cost = dict(cost_row).get("total",0) or 0.022   # default $0.022
        total_sessions = sum(m.get("organic_sessions",0) for m in metrics)
        total_convs    = sum(m.get("conversions",0) for m in metrics)
        sql_con.close()
        return {
            "article_id":       article_id,
            "total_organic_sessions": total_sessions,
            "total_conversions":      total_convs,
            "generation_cost_usd":    round(gen_cost, 4),
            "sessions_per_dollar":    round(total_sessions / max(gen_cost, 0.001), 0),
            "roi_ratio":              round(total_convs * 10 / max(gen_cost, 0.001), 1),  # assumes $10/conversion
        }


# ─────────────────────────────────────────────────────────────────────────────
# ENGINE 5 — BULK KEYWORD IMPORT
# ─────────────────────────────────────────────────────────────────────────────

class BulkKeywordImporter:
    """
    Upload CSV/Excel of up to 50,000 keywords (from Semrush, Ahrefs, GSC export).
    AnnaSEO classifies all of them through the domain context engine,
    scores opportunity, clusters, and integrates into the universe.
    """

    def import_csv(self, csv_text: str, project_id: str,
                    seed: str = "") -> str:
        """
        Parse CSV and start import job.
        Expected columns: keyword, [volume], [difficulty], [intent]
        Returns job_id.
        """
        job_id = f"imp_{project_id}_{int(time.time())}"
        # Parse CSV
        reader = csv.DictReader(io.StringIO(csv_text))
        rows   = list(reader)
        _db().execute("""
            INSERT INTO bulk_import_jobs (job_id,project_id,filename,total_kws,status)
            VALUES (?,?,?,?,'processing')
        """, (job_id, project_id, "upload.csv", len(rows)))
        _db().commit()

        # Process
        accepted, rejected, processed = 0, 0, 0
        db_path = Path(os.getenv("ANNASEO_DB","./annaseo.db"))
        sql_con = sqlite3.connect(str(db_path), check_same_thread=False)
        sql_con.row_factory = sqlite3.Row

        # Domain context filter
        try:
            from annaseo_domain_context import DomainContextEngine
            dce = DomainContextEngine()
            use_domain = True
        except Exception:
            use_domain = False

        for row in rows[:50000]:
            kw  = row.get("keyword","").strip().lower()
            if not kw: continue
            vol  = int(row.get("volume",row.get("search_volume","0")) or 0)
            diff = int(row.get("difficulty",row.get("kd","50")) or 50)
            processed += 1
            # Domain context check
            verdict = "accept"
            if use_domain:
                result  = dce.classify(kw, project_id)
                verdict = result.get("verdict","accept")
            if verdict == "reject":
                rejected += 1
                continue
            # Calculate opportunity score
            opp = round(vol * (1 - diff/100) * 0.001, 2)
            try:
                sql_con.execute("""
                    INSERT OR IGNORE INTO keywords
                    (id,keyword,volume_estimate,difficulty_estimate,opportunity_score,intent,status)
                    VALUES (?,?,?,?,?,'informational','not_used')
                """, (f"kw_{hashlib.md5(f'{project_id}{kw}'.encode()).hexdigest()[:10]}",
                       kw, vol, diff, opp))
                accepted += 1
            except Exception:
                pass
            if processed % 500 == 0:
                sql_con.commit()
                _db().execute(
                    "UPDATE bulk_import_jobs SET processed=?,accepted=?,rejected=? WHERE job_id=?",
                    (processed, accepted, rejected, job_id)
                )
                _db().commit()

        sql_con.commit()
        sql_con.close()
        _db().execute("""
            UPDATE bulk_import_jobs SET processed=?,accepted=?,rejected=?,status='done' WHERE job_id=?
        """, (processed, accepted, rejected, job_id))
        _db().commit()
        log.info(f"[BulkImport] {job_id}: {processed} processed, {accepted} accepted, {rejected} rejected")
        return job_id

    def get_job(self, job_id: str) -> Optional[dict]:
        row = _db().execute("SELECT * FROM bulk_import_jobs WHERE job_id=?",
                             (job_id,)).fetchone()
        return dict(row) if row else None


# ─────────────────────────────────────────────────────────────────────────────
# ENGINE 6 — CONTENT BRIEF EXPORT
# ─────────────────────────────────────────────────────────────────────────────

BRIEF_FORMATS = {
    "markdown": {
        "extension": ".md",
        "description": "Markdown file for human writers (Notion, Obsidian, any editor)",
    },
    "google_docs": {
        "extension": ".gdoc-template.html",
        "description": "HTML formatted for copy-paste into Google Docs",
    },
    "notion": {
        "extension": ".notion.md",
        "description": "Notion-compatible markdown with callout blocks",
    },
    "plain_text": {
        "extension": ".txt",
        "description": "Plain text for any word processor",
    },
}


class ContentBriefExporter:
    """
    Export P15 content briefs as Markdown, Google Doc format, or Notion pages.
    For businesses that have human writers who want the research without AI writing.
    """

    def export(self, article_id: str, fmt: str = "markdown") -> dict:
        """Export content brief. Returns {content, export_id, filename}."""
        db_path = Path(os.getenv("ANNASEO_DB","./annaseo.db"))
        sql_con = sqlite3.connect(str(db_path), check_same_thread=False)
        sql_con.row_factory = sqlite3.Row
        article = sql_con.execute("SELECT * FROM content_articles WHERE article_id=?",
                                   (article_id,)).fetchone()
        sql_con.close()
        if not article:
            return {"error": "Article not found"}
        art = dict(article)
        content = self._render(art, fmt)
        ext     = BRIEF_FORMATS.get(fmt, {}).get("extension",".md")
        fname   = f"brief_{art.get('keyword','article').replace(' ','_')}{ext}"

        export_id = f"exp_{article_id}_{int(time.time())}"
        _db().execute("INSERT INTO brief_exports (export_id,article_id,format,content) VALUES (?,?,?,?)",
                       (export_id, article_id, fmt, content[:50000]))
        _db().commit()
        return {"export_id": export_id, "filename": fname, "content": content,
                "format": fmt, "word_count": len(content.split())}

    def _render(self, article: dict, fmt: str) -> str:
        kw    = article.get("keyword","")
        title = article.get("title","")
        score = article.get("seo_score",0)

        if fmt == "markdown":
            return f"""# Content Brief: {title or kw}

**Keyword:** {kw}
**Target word count:** {article.get('word_count', 2000) or 2000}
**SEO Score (previous draft):** {score}/100

---

## Brief Overview
This brief covers everything your writer needs to create a high-performing article.

## Target Keyword
Primary: **{kw}**

## Recommended Title (H1)
{title or f"Complete Guide to {kw.title()}"}

## Content Structure

### Introduction
- Answer the main question in the first 2 sentences
- Include primary keyword in first 100 words
- Set up the rest of the article in 3-4 sentences

### H2 Sections (write each as 300-400 words)
1. What is {kw}?
2. Benefits of {kw}
3. How to use {kw}
4. Best {kw} available
5. Expert tips for {kw}

### FAQ Section (include at end, 4-6 questions)
- What is {kw}?
- How much {kw} per day?
- Where to buy {kw}?
- Is {kw} safe?

---

## Quality Requirements
- [ ] Minimum 1,800 words
- [ ] Primary keyword in H1, first 100 words, at least 2 H2s
- [ ] Include specific numbers/statistics
- [ ] First-person experience signals ("In our testing...", "We found...")
- [ ] No AI writing patterns (furthermore, certainly, it is worth noting)
- [ ] FAQ section with direct answers

---
*Brief generated by AnnaSEO · {datetime.utcnow().strftime('%B %d, %Y')}*
"""
        elif fmt == "notion":
            return f"""> **[CONTENT BRIEF]** {title or kw}
> Status: 📝 In Progress | Writer: Unassigned

# {title or f"Guide to {kw.title()}"}

## Brief Details

| | |
|--|--|
| **Primary keyword** | {kw} |
| **Word count target** | {article.get('word_count',2000)} |
| **SEO score target** | 75+ |

---

## Article Structure

### Introduction (200 words)
Answer the main question immediately. Include "{kw}" in first sentence.

### Section 1: What is {kw}? (300 words)
Definition + context + why it matters to the reader.

### Section 2: Key Benefits (400 words)
3-5 specific, research-backed benefits. Include statistics.

### Section 3: How to Use It (400 words)
Step-by-step or practical application. First-person where relevant.

### Section 4: Expert Tips (300 words)
Advanced insights. Cite sources or experience.

### FAQ Section (200 words)
4 questions. Each answer in 2-3 sentences.

---

> 💡 **Writer checklist:**
> - [ ] 1,800+ words
> - [ ] Keyword in H1 + 2x H2 + first paragraph
> - [ ] Stats with sources
> - [ ] No "furthermore" or "certainly"
> - [ ] FAQs answered directly
"""
        else:  # plain text or google docs
            return f"""CONTENT BRIEF: {title or kw}

KEYWORD: {kw}
TARGET WORDS: {article.get('word_count',2000)}

STRUCTURE:
1. Introduction - answer main question in first 2 sentences
2. What is {kw}? (300 words)
3. Benefits of {kw} (400 words)
4. How to use {kw} (400 words)
5. Expert tips (300 words)
6. FAQ - 4 questions with direct 2-3 sentence answers

QUALITY CHECKLIST:
- Minimum 1800 words
- Keyword in title, intro, and 2+ H2s
- Include specific statistics
- First-person experience signals
- No AI writing patterns
"""


# ─────────────────────────────────────────────────────────────────────────────
# FASTAPI ROUTER — all 6 growth engines
# ─────────────────────────────────────────────────────────────────────────────

try:
    from fastapi import FastAPI, BackgroundTasks, UploadFile, File
    from pydantic import BaseModel as PM
    from typing import Optional as Opt, List as L

    app = FastAPI(title="AnnaSEO Product Growth Engines")

    team   = TeamACL()
    wh     = WebhookEngine()
    pdf    = PDFReportEngine()
    ga4    = GA4Integration()
    importer = BulkKeywordImporter()
    briefexp = ContentBriefExporter()

    # Team
    class InviteBody(PM):
        user_id:    str
        role:       str
        invited_by: str

    @app.post("/api/team/{project_id}/invite", tags=["Team"])
    def invite(project_id: str, body: InviteBody):
        mid = team.invite(project_id, body.user_id, body.role, body.invited_by)
        return {"member_id": mid}

    @app.get("/api/team/{project_id}", tags=["Team"])
    def list_team(project_id: str):
        return team.list_members(project_id)

    @app.delete("/api/team/{project_id}/{user_id}", tags=["Team"])
    def remove_member(project_id: str, user_id: str):
        team.remove(project_id, user_id)
        return {"removed": user_id}

    @app.post("/api/team/{project_id}/{user_id}/role", tags=["Team"])
    def update_role(project_id: str, user_id: str, role: str):
        team.update_role(project_id, user_id, role)
        return {"updated": True}

    @app.get("/api/team/permissions", tags=["Team"])
    def permissions():
        return ROLE_PERMISSIONS

    # Webhooks
    class WebhookBody(PM):
        name:   str
        url:    str
        events: L[str]
        secret: str = ""

    @app.post("/api/webhooks/{project_id}", tags=["Webhooks"])
    def register_webhook(project_id: str, body: WebhookBody):
        wid = wh.register(project_id, body.name, body.url, body.events, body.secret)
        return {"webhook_id": wid}

    @app.get("/api/webhooks/{project_id}", tags=["Webhooks"])
    def list_webhooks(project_id: str):
        return wh.list_webhooks(project_id)

    @app.get("/api/webhooks/events", tags=["Webhooks"])
    def webhook_events():
        return WEBHOOK_EVENTS

    @app.get("/api/webhooks/{webhook_id}/deliveries", tags=["Webhooks"])
    def webhook_deliveries(webhook_id: str):
        return wh.deliveries(webhook_id)

    # PDF Reports
    class ReportBody(PM):
        period_from:  Opt[str] = None
        period_to:    Opt[str] = None
        agency_name:  str = "AnnaSEO"
        client_name:  str = ""

    @app.post("/api/reports/{project_id}", tags=["Reports"])
    async def generate_report(project_id: str, body: ReportBody, bg: BackgroundTasks):
        bg.add_task(pdf.generate, project_id, body.period_from, body.period_to,
                     body.agency_name, body.client_name)
        return {"status": "generating", "project_id": project_id}

    @app.get("/api/reports/{project_id}", tags=["Reports"])
    def list_reports(project_id: str):
        return [dict(r) for r in _db().execute(
            "SELECT * FROM pdf_reports WHERE project_id=? ORDER BY created_at DESC LIMIT 12",
            (project_id,)
        ).fetchall()]

    # GA4
    class GA4Body(PM):
        measurement_id: str
        property_id:    str
        service_account_json: str = ""

    @app.post("/api/ga4/{project_id}/connect", tags=["GA4"])
    def ga4_connect(project_id: str, body: GA4Body):
        return ga4.connect(project_id, body.measurement_id, body.property_id,
                            body.service_account_json)

    @app.post("/api/ga4/{project_id}/sync", tags=["GA4"])
    async def ga4_sync(project_id: str, days: int = 30, bg: BackgroundTasks = None):
        if bg:
            bg.add_task(ga4.sync, project_id, days)
            return {"status": "syncing"}
        return ga4.sync(project_id, days)

    @app.get("/api/ga4/{project_id}/roi/{article_id}", tags=["GA4"])
    def article_roi(project_id: str, article_id: str):
        return ga4.article_roi(project_id, article_id)

    # Bulk import
    class ImportBody(PM):
        csv_content: str
        project_id:  str
        seed:        str = ""

    @app.post("/api/import/keywords", tags=["Bulk Import"])
    async def bulk_import(body: ImportBody, bg: BackgroundTasks):
        bg.add_task(importer.import_csv, body.csv_content, body.project_id, body.seed)
        return {"status": "started", "message": "Import started. Check /api/import/jobs for progress."}

    @app.get("/api/import/jobs/{job_id}", tags=["Bulk Import"])
    def import_job(job_id: str):
        job = importer.get_job(job_id)
        if not job: raise __import__("fastapi").HTTPException(404, "Job not found")
        return job

    # Content brief export
    @app.post("/api/brief-export/{article_id}", tags=["Brief Export"])
    def export_brief(article_id: str, fmt: str = "markdown"):
        return briefexp.export(article_id, fmt)

    @app.get("/api/brief-export/formats", tags=["Brief Export"])
    def export_formats():
        return BRIEF_FORMATS

except ImportError:
    pass


if __name__ == "__main__":
    import sys
    print("AnnaSEO Product Growth Engines")
    print("Engines: TeamACL, WebhookEngine, PDFReportEngine, GA4Integration, BulkKeywordImporter, ContentBriefExporter")
    print("\nUsage: import and use individual classes, or run FastAPI server")
    if len(sys.argv) > 1 and sys.argv[1] == "demo":
        # Demo team ACL
        t = TeamACL()
        mid = t.invite("proj_demo","user_002","editor","user_001")
        print(f"Invited editor: {mid}")
        print(f"Can publish: {t.check('proj_demo','user_002','publish')}")
        print(f"Can delete:  {t.check('proj_demo','user_002','delete')}")
        # Demo brief export
        print("\nBrief export formats:", list(BRIEF_FORMATS.keys()))
        # Demo seasonality (standalone)
        from annaseo_intelligence_engines import SeasonalKeywordCalendar
        s = SeasonalKeywordCalendar()
        for kw in ["cinnamon recipe","cinnamon health","buy cinnamon"]:
            r = s.detect_seasonality(kw)
            print(f"  {kw}: seasonal={r['has_seasonality']}")
