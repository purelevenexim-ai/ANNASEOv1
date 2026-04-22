"""
kw2 Prompt Manager — Phase 12.

DB-backed prompt registry. Every AI prompt used by the kw2 system is:
- Visible and editable by the user
- Versioned (with rollback)
- Seeded from engines/kw2/prompts.py on first run

Usage:
    pm = PromptManager()
    template = pm.get_prompt("strategy_2a")  # returns template string
"""
import json
import logging
import uuid
from datetime import datetime, timezone

from engines.kw2 import db

log = logging.getLogger("kw2.prompt_manager")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uid(prefix: str = "") -> str:
    short = uuid.uuid4().hex[:12]
    return f"{prefix}{short}" if prefix else short


# ── Prompt seed definitions ───────────────────────────────────────────────────
# Each entry: (prompt_key, phase, display_name, description, is_system)
# Templates are seeded from prompts.py values at startup.

PROMPT_REGISTRY = [
    ("strategy_v2_system",     2, "Strategy System Prompt",    "System role for all strategy sub-modules", 1),
    ("strategy_2a",            2, "Module 2A — Business Analysis", "Analyse business profile and intel", 0),
    ("strategy_2b",            2, "Module 2B — Keyword Intelligence", "Analyse full keyword dataset", 0),
    ("strategy_2c",            2, "Module 2C — Strategy Builder", "Build full strategy from 2A + 2B", 0),
    ("strategy_2d",            2, "Module 2D — Action Mapping", "Map strategy to execution actions", 0),
    ("question_module_system", 3, "Question Module System",     "System role for all Q1-Q7 modules", 1),
    ("question_module",        3, "Question Module Prompt",     "Generic prompt for Q1-Q7 modules", 0),
    ("enrichment_system",      5, "Enrichment System Prompt",   "System role for enrichment phase", 1),
    ("enrichment",             5, "Enrichment Prompt",          "Add intent/funnel/geo metadata to questions", 0),
    ("title_system",           9, "Title Generation System",    "System role for content title generation", 1),
    ("title_generation",       9, "Title Generation Prompt",    "Convert questions to SEO titles", 0),
]

# Map prompt_key → attribute name in prompts.py module
_PROMPTS_PY_MAP = {
    "strategy_v2_system":     "STRATEGY_V2_SYSTEM",
    "strategy_2a":            "STRATEGY_2A_USER",
    "strategy_2b":            "STRATEGY_2B_USER",
    "strategy_2c":            "STRATEGY_2C_USER",
    "strategy_2d":            "STRATEGY_2D_USER",
    "question_module_system": "QUESTION_MODULE_SYSTEM",
    "question_module":        "QUESTION_MODULE_USER",
    "enrichment_system":      "ENRICHMENT_SYSTEM",
    "enrichment":             "ENRICHMENT_USER",
    "title_system":           "TITLE_SYSTEM",
    "title_generation":       "TITLE_PROMPT",
}


class PromptManager:
    """Manage AI prompts: seed, read, edit, version."""

    def seed_all(self, force: bool = False) -> int:
        """
        Seed all prompts from prompts.py into kw2_prompts.
        Called once at startup. Skips if already seeded (unless force=True).
        Returns count of prompts seeded or updated.
        """
        import engines.kw2.prompts as prompts_module
        # Also import title prompt from content_title_engine.py inline
        try:
            from engines.kw2.content_title_engine import TITLE_SYSTEM, TITLE_PROMPT
        except ImportError:
            TITLE_SYSTEM = ""
            TITLE_PROMPT = ""

        extra = {"title_system": TITLE_SYSTEM, "title_generation": TITLE_PROMPT}

        count = 0
        for entry in PROMPT_REGISTRY:
            prompt_key, phase, display_name, description, is_system = entry
            template = ""

            attr_name = _PROMPTS_PY_MAP.get(prompt_key)
            if attr_name:
                template = getattr(prompts_module, attr_name, "") or ""
            if not template and prompt_key in extra:
                template = extra[prompt_key] or ""

            if not template:
                log.debug("No template found for prompt key %s — skipping seed", prompt_key)
                continue

            existing = self._get_by_key(prompt_key)
            if existing and not force:
                # Update if template has changed in prompts.py
                if existing.get("template", "").strip() != template.strip():
                    self._update_template(existing["id"], prompt_key, template)
                    count += 1
                continue

            if existing:
                # Update template if force=True
                self._update_template(existing["id"], prompt_key, template)
            else:
                self._create_prompt(
                    prompt_key, phase, display_name, description,
                    template, is_system,
                )
            count += 1

        log.info("[PromptManager] Seeded %d prompts", count)
        return count

    def get_prompt(self, prompt_key: str) -> str:
        """
        Get the current template for a prompt key.
        Falls back to prompts.py if not in DB.
        """
        row = self._get_by_key(prompt_key)
        if row and row.get("template"):
            return row["template"]

        # Fallback to prompts.py
        import engines.kw2.prompts as prompts_module
        attr_name = _PROMPTS_PY_MAP.get(prompt_key)
        if attr_name:
            return getattr(prompts_module, attr_name, "") or ""
        return ""

    def list_prompts(self, phase: int | None = None) -> list[dict]:
        conn = db.get_conn()
        try:
            if phase is not None:
                rows = conn.execute(
                    "SELECT id, prompt_key, phase, display_name, description, version, is_system, updated_at "
                    "FROM kw2_prompts WHERE phase=? ORDER BY phase, prompt_key",
                    (phase,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, prompt_key, phase, display_name, description, version, is_system, updated_at "
                    "FROM kw2_prompts ORDER BY phase, prompt_key"
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_prompt_detail(self, prompt_key: str) -> dict | None:
        """Get full prompt with template and variables."""
        row = self._get_by_key(prompt_key)
        if not row:
            return None
        d = dict(row)
        raw_vars = d.get("variables", "[]")
        try:
            d["variables"] = json.loads(raw_vars) if raw_vars else []
        except Exception:
            d["variables"] = []
        return d

    def update_template(self, prompt_key: str, new_template: str, note: str = "") -> bool:
        """Update a prompt template and save previous version."""
        row = self._get_by_key(prompt_key)
        if not row:
            return False
        if row.get("is_system"):
            raise ValueError("System prompts cannot be edited.")
        return self._update_template(row["id"], prompt_key, new_template, note)

    def list_versions(self, prompt_key: str) -> list[dict]:
        row = self._get_by_key(prompt_key)
        if not row:
            return []
        conn = db.get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM kw2_prompt_versions WHERE prompt_id=? ORDER BY version DESC",
                (row["id"],),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def restore_version(self, prompt_key: str, version_number: int) -> bool:
        """Restore a specific version as the active template."""
        row = self._get_by_key(prompt_key)
        if not row:
            return False
        conn = db.get_conn()
        try:
            ver = conn.execute(
                "SELECT template FROM kw2_prompt_versions WHERE prompt_id=? AND version=?",
                (row["id"], version_number),
            ).fetchone()
            if not ver:
                return False
        finally:
            conn.close()
        return self._update_template(row["id"], prompt_key, ver["template"], f"Restored v{version_number}")

    # ── Internal ─────────────────────────────────────────────────────────────

    def _get_by_key(self, prompt_key: str) -> dict | None:
        conn = db.get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM kw2_prompts WHERE prompt_key=?", (prompt_key,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def _create_prompt(
        self,
        prompt_key: str,
        phase: int,
        display_name: str,
        description: str,
        template: str,
        is_system: int = 0,
    ) -> str:
        pid = _uid("p_")
        now = _now()
        conn = db.get_conn()
        try:
            conn.execute(
                """INSERT OR IGNORE INTO kw2_prompts
                   (id, prompt_key, phase, display_name, description, template,
                    variables, is_system, version, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,1,?,?)""",
                (pid, prompt_key, phase, display_name, description,
                 template, "[]", is_system, now, now),
            )
            conn.commit()
        finally:
            conn.close()
        return pid

    def _update_template(
        self, prompt_id: str, prompt_key: str, new_template: str, note: str = ""
    ) -> bool:
        conn = db.get_conn()
        try:
            row = conn.execute(
                "SELECT version, template FROM kw2_prompts WHERE id=?", (prompt_id,)
            ).fetchone()
            if not row:
                return False
            old_version = row["version"] or 1
            old_template = row["template"] or ""

            # Save current version to history
            conn.execute(
                """INSERT INTO kw2_prompt_versions
                   (id, prompt_id, template, version, changed_by, change_note, created_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (_uid("pv_"), prompt_id, old_template, old_version, "user", note, _now()),
            )

            # Update prompt
            conn.execute(
                "UPDATE kw2_prompts SET template=?, version=?, updated_at=? WHERE id=?",
                (new_template, old_version + 1, _now(), prompt_id),
            )
            conn.commit()
            return True
        finally:
            conn.close()
