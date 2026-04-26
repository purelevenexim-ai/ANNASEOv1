from __future__ import annotations

import json
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import requests

from .config import QAConfig, TestScenario


class UIFlowRunner:
    def __init__(self, cfg: QAConfig):
        self.cfg = cfg

    def _login_token(self) -> str:
        if self.cfg.token:
            return self.cfg.token

        attempts = [
            (self.cfg.username, self.cfg.password),
            ("anna@gmail.com", "admin"),
            ("test_api@test.com", "test123"),
        ]
        last_err = None
        for user, pw in attempts:
            try:
                res = requests.post(
                    f"{self.cfg.api_url}/api/auth/login",
                    data={"username": user, "password": pw},
                    timeout=20,
                )
                if res.status_code == 200:
                    return res.json()["access_token"]
                last_err = RuntimeError(f"login failed for {user}: {res.status_code}")
            except Exception as exc:
                last_err = exc

        # Final fallback: create a throwaway QA user and use returned token.
        try:
            email = f"qa_auto_{uuid.uuid4().hex[:8]}@example.com"
            reg = requests.post(
                f"{self.cfg.api_url}/api/auth/register",
                json={"email": email, "name": "QA Auto", "password": "qa_auto_pass_123"},
                timeout=20,
            )
            if reg.status_code == 200:
                body = reg.json()
                token = body.get("access_token")
                if token:
                    return token
            last_err = RuntimeError(f"register fallback failed: {reg.status_code} {reg.text[:200]}")
        except Exception as exc:
            last_err = exc

        raise RuntimeError(
            "Unable to obtain auth token. Set QA_TOKEN or valid QA_USERNAME/QA_PASSWORD."
        ) from last_err

    def _playwright(self):
        try:
            from playwright.sync_api import sync_playwright  # type: ignore
        except Exception as exc:
            raise RuntimeError(
                "playwright is not installed. Run: pip install playwright && python3 -m playwright install chromium"
            ) from exc
        return sync_playwright

    def _api_get(self, token: str, path: str) -> Any:
        r = requests.get(
            f"{self.cfg.api_url}{path}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()

    def _api_post(self, token: str, path: str, body: Dict[str, Any]) -> Any:
        r = requests.post(
            f"{self.cfg.api_url}{path}",
            headers={"Authorization": f"Bearer {token}"},
            json=body,
            timeout=40,
        )
        r.raise_for_status()
        return r.json()

    def _find_session_id_from_name(self, token: str, session_name: str) -> Optional[str]:
        rows = self._api_get(token, f"/api/kw2/{self.cfg.project_id}/sessions/list")
        sessions = rows.get("sessions", []) if isinstance(rows, dict) else rows
        for s in sessions:
            if (s.get("name") or "") == session_name:
                return s.get("id")
        if sessions:
            sessions = sorted(sessions, key=lambda s: s.get("updated_at", ""), reverse=True)
            return sessions[0].get("id")
        return None

    def _safe_fill_and_enter(self, page: Any, placeholder: str, value: str) -> bool:
        try:
            loc = page.get_by_placeholder(placeholder).first
            loc.click(timeout=8000)
            loc.fill(value)
            loc.press("Enter")
            return True
        except Exception:
            return False

    def run(self, scenario: TestScenario) -> Dict[str, Any]:
        from typing import TYPE_CHECKING

        if TYPE_CHECKING:
            from playwright.sync_api import Browser, Page  # pragma: no cover

        started = datetime.now(timezone.utc)
        token = self._login_token()

        console_errors: list[str] = []
        network_log: list[dict[str, Any]] = []
        session_name = f"qa-auto-{scenario.name}-{int(time.time())}"
        session_id = None

        # Create session via API first to avoid brittle UI prompt interactions.
        try:
            created = self._api_post(
                token,
                f"/api/kw2/{self.cfg.project_id}/sessions",
                {"provider": "auto", "mode": "brand", "name": session_name, "seed_keywords": []},
            )
            session_id = created.get("session", {}).get("id") or created.get("id")
        except Exception:
            session_id = None

        sync_playwright = self._playwright()

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=self.cfg.headless,
                slow_mo=self.cfg.slow_mo_ms,
            )
            context = browser.new_context()
            script_lines = [
                f"window.localStorage.setItem('annaseo_token', {json.dumps(token)});",
                f"window.localStorage.setItem('annaseo_project', {json.dumps(self.cfg.project_id)});",
            ]
            if session_id:
                script_lines.append(f"window.localStorage.setItem('kw3:activeSession', {json.dumps(session_id)});")
                script_lines.append("window.localStorage.setItem('kw3:activeTab', 'business');")
            context.add_init_script(script="\n".join(script_lines))
            page = context.new_page()

            page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)

            def on_response(resp):
                url = resp.url
                if "/api/" in url:
                    try:
                        network_log.append({"url": url, "status": resp.status})
                    except Exception:
                        pass

            page.on("response", on_response)

            page.goto(self.cfg.frontend_url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(1500)

            # Enter Keywords V3 area.
            try:
                page.get_by_role("button", name=re.compile(r"Keywords V3", re.I)).first.click(timeout=15000)
            except Exception:
                page.get_by_text("Keywords V3", exact=False).first.click(timeout=15000)
            page.wait_for_timeout(1000)

            # Ensure page is actually on kw3 view.
            if page.get_by_text("1. Business Analysis", exact=False).count() == 0:
                try:
                    page.get_by_role("button", name=re.compile(r"Keywords V3", re.I)).first.click(timeout=8000)
                    page.wait_for_timeout(1200)
                except Exception:
                    pass

            # If pre-created session did not work, fall back to UI-based creation.
            if not session_id:
                def _dialog_handler(dialog):
                    try:
                        dialog.accept(session_name)
                    except Exception:
                        pass

                page.once("dialog", _dialog_handler)
                page.get_by_text("+ New session", exact=False).first.click(timeout=10000)
                page.wait_for_timeout(2000)
                session_id = self._find_session_id_from_name(token, session_name)

            # Step 1: Business Analysis.
            page.get_by_text("1. Business Analysis", exact=False).first.click(timeout=15000)
            page.wait_for_timeout(600)

            domain_ok = self._safe_fill_and_enter(page, "https://example.com", scenario.domain)
            comp_ok = self._safe_fill_and_enter(page, "https://competitor.com", scenario.competitor)
            pillar_ok = self._safe_fill_and_enter(page, "Type a pillar and press Enter", scenario.pillar)
            mod_ok = True
            for m in scenario.modifiers:
                mod_ok = mod_ok and self._safe_fill_and_enter(page, "organic, wholesale, bulk", m)

            page.get_by_text("Analyze Business", exact=False).first.click(timeout=10000)
            page.wait_for_timeout(5000)

            business_saved = bool(page.get_by_text("Continue to Generate", exact=False).count())
            if business_saved:
                page.get_by_text("Continue to Generate", exact=False).first.click(timeout=10000)
            else:
                page.get_by_text("2. Generate", exact=False).first.click(timeout=10000)

            # Step 2: Generate keywords.
            if scenario.pillar:
                self._safe_fill_and_enter(
                    page,
                    "Add pillars (comma-separated) e.g. organic spices, whole spices",
                    scenario.pillar,
                )
            for m in scenario.modifiers:
                self._safe_fill_and_enter(page, "organic, bulk, buy, best...", m)

            page.get_by_text("Generate keywords", exact=False).first.click(timeout=10000)
            # Wait until either continue appears or timeout.
            try:
                page.get_by_text("Continue", exact=False).first.wait_for(timeout=self.cfg.timeout_sec * 1000)
            except Exception:
                pass

            if page.get_by_text("Continue", exact=False).count() > 0:
                page.get_by_text("Continue", exact=False).first.click(timeout=10000)
            else:
                page.get_by_text("3. Score & Validate", exact=False).first.click(timeout=10000)

            # Step 3: Validate & score.
            if page.get_by_text("Batch Validate & Score", exact=False).count() > 0:
                page.get_by_text("Batch Validate & Score", exact=False).first.click(timeout=10000)
                # Wait for scoring to finish on live environments.
                page.wait_for_timeout(12000)
            elif page.get_by_text("Run Scoring", exact=False).count() > 0:
                page.get_by_text("Run Scoring", exact=False).first.click(timeout=10000)
                page.wait_for_timeout(12000)

            # If approval gate appears, approve all and continue.
            if page.get_by_text("✓ Approve all", exact=False).count() > 0:
                try:
                    page.get_by_text("✓ Approve all", exact=False).first.click(timeout=5000)
                    page.wait_for_timeout(500)
                except Exception:
                    pass
            if page.get_by_text("Continue with", exact=False).count() > 0:
                try:
                    page.get_by_text("Continue with", exact=False).first.click(timeout=7000)
                    page.wait_for_timeout(1500)
                except Exception:
                    pass

            page.get_by_text("4. Strategy & Plan", exact=False).first.click(timeout=10000)

            # Step 4: Strategy generation.
            if page.get_by_text("Continue from where left off", exact=False).count() > 0:
                page.get_by_text("Continue from where left off", exact=False).first.click(timeout=10000)
            elif page.get_by_text("Generate strategy", exact=False).count() > 0:
                btn = page.get_by_text("Generate strategy", exact=False).first
                if btn.is_enabled():
                    btn.click(timeout=10000)

            page.wait_for_timeout(12000)

            # Gather strategy tab text.
            ui_text = page.inner_text("body")
            phase9_failed = "Phase 9" in ui_text and "failed" in ui_text.lower()

            # Discover session id from API after UI run.
            session_id = self._find_session_id_from_name(token, session_name)

            phase9_api_fallback_triggered = False
            phase9_api_fallback_error = ""
            # If UI flow does not complete strategy generation, attempt a direct API trigger.
            # This keeps QA deterministic when UI buttons are disabled due timing/state drift.
            if session_id:
                try:
                    sess_resp = self._api_get(token, f"/api/kw2/{self.cfg.project_id}/sessions/{session_id}")
                    sess_obj = sess_resp.get("session", sess_resp) if isinstance(sess_resp, dict) else {}
                    phase9_done = bool((sess_obj or {}).get("phase9_done"))
                    if not phase9_done:
                        phase9_api_fallback_triggered = True
                        self._api_post(
                            token,
                            f"/api/kw2/{self.cfg.project_id}/sessions/{session_id}/phase9",
                            {},
                        )
                        page.wait_for_timeout(3000)
                except Exception as exc:
                    phase9_api_fallback_error = str(exc)

            browser.close()

        capture = {
            "scenario": {
                "name": scenario.name,
                "domain": scenario.domain,
                "competitor": scenario.competitor,
                "pillar": scenario.pillar,
                "modifiers": scenario.modifiers,
            },
            "ui": {
                "domain_input_ok": domain_ok,
                "competitor_input_ok": comp_ok,
                "pillar_input_ok": pillar_ok,
                "modifier_input_ok": mod_ok,
                "business_saved": business_saved,
                "phase9_failed_banner": phase9_failed,
                "console_errors": console_errors,
                "network_log": network_log,
            },
            "run_meta": {
                "session_name": session_name,
                "session_id": session_id,
                "phase9_api_fallback_triggered": phase9_api_fallback_triggered,
                "phase9_api_fallback_error": phase9_api_fallback_error,
                "started_at": started.isoformat(),
                "finished_at": datetime.now(timezone.utc).isoformat(),
            },
        }

        # API capture for deeper evaluation.
        if session_id:
            session = self._api_get(token, f"/api/kw2/{self.cfg.project_id}/sessions/{session_id}")
            profile = self._api_get(token, f"/api/kw2/{self.cfg.project_id}/profile")

            validated = self._api_get(token, f"/api/kw2/{self.cfg.project_id}/sessions/{session_id}/validated")
            validated_items = validated.get("items", []) if isinstance(validated, dict) else []
            validated_keywords = [it.get("keyword", "") for it in validated_items if isinstance(it, dict)]

            strategy_text = ""
            try:
                strategy = self._api_get(token, f"/api/kw2/{self.cfg.project_id}/sessions/{session_id}/strategy")
                strategy_obj = strategy.get("strategy") if isinstance(strategy, dict) else None
                strategy_text = json.dumps(strategy_obj or strategy, ensure_ascii=True)
            except Exception:
                strategy_text = ""

            clusters = 0
            try:
                import sqlite3
                conn = sqlite3.connect(self.cfg.db_path)
                row = conn.execute(
                    "SELECT COUNT(1) FROM kw2_content_clusters WHERE session_id=?",
                    (session_id,),
                ).fetchone()
                clusters = int((row[0] if row else 0) or 0)
                conn.close()
            except Exception:
                clusters = 0

            capture["api"] = {
                "session": session,
                "profile": profile,
                "validated_keywords": validated_keywords,
                "validated_count": len(validated_keywords),
                "strategy_text": strategy_text,
                "clusters": clusters,
            }
        else:
            capture["api"] = {
                "session": {},
                "profile": {},
                "validated_keywords": [],
                "validated_count": 0,
                "strategy_text": "",
                "clusters": 0,
            }

        return capture
