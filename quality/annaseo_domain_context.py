"""
================================================================================
ANNASEO — DOMAIN CONTEXT ENGINE  (annaseo_domain_context.py)
================================================================================
Solves the core problem
────────────────────────
"Cinnamon tour" means different things to different businesses:

  Project A — Spice Exporter (industry: FOOD_SPICES)
    "cinnamon tour"    → BAD  (tourism is off-topic for a spice seller)
    "cinnamon health benefits" → GOOD

  Project B — Sri Lanka Travel Agency (industry: TOURISM)
    "ceylon cinnamon tour"  → GOOD  (cinnamon is a tourism attraction)
    "cinnamon grows in sri lanka" → GOOD  (geographic/cultural context)
    "cinnamon price per kg" → BAD   (e-commerce, not tourism)

Same keyword. Same seed. Opposite verdict.
The verdict depends on BUSINESS DOMAIN, not the keyword itself.

Architecture
─────────────
  ProjectDomainProfile
    ├── industry (FOOD_SPICES / TOURISM / ECOMMERCE / etc.)
    ├── domain_keywords (what THIS business cares about)
    ├── anti_keywords (what this business explicitly rejects)
    ├── cross_domain_signals (words that flip meaning by industry)
    └── tuning_history (per-project tuning log)

  DomainContextEngine
    ├── classify(keyword, project_id) → ACCEPT / REJECT / AMBIGUOUS + reason
    ├── cross_domain_check(keyword, project_id) → is this a cross-domain term?
    └── score_for_domain(keyword, project_id) → 0-100 domain relevance score

  GlobalTuningRegistry
    ├── core code quality rules (apply to ALL projects)
    ├── engine health thresholds (global)
    └── algorithm bugs (not domain-specific — actual code issues)

  ProjectTuningRegistry
    ├── per-project kill words
    ├── per-project accept overrides
    ├── per-project prompt adjustments
    └── domain-specific scoring rules

Tuning separation (Industry standard: configuration as data)
──────────────────────────────────────────────────────────────
  GLOBAL tuning  → touches engine code, thresholds, prompt structure
  PROJECT tuning → touches per-project config, kill lists, accept lists

  This means:
    - Fixing "tour" in a spice project DOES NOT affect the travel project
    - Fixing a code bug in P8_TopicDetection fixes ALL projects
    - A spice project's kill list is never inherited by a travel project

Where this engine sits in the pipeline
────────────────────────────────────────
  BEFORE P2_KeywordExpansion  → sets domain context for the run
  AFTER  P2_KeywordExpansion  → first pass domain filter (replaces global OffTopicFilter for cross-domain cases)
  AFTER  P8_TopicDetection    → cluster names validated against domain
  AFTER  P10_PillarIdentification → pillars validated against domain
  IN     P15_ContentBrief     → content angles validated against domain
================================================================================
"""

from __future__ import annotations

import os, json, hashlib, sqlite3, logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

import requests as _req

log = logging.getLogger("annaseo.domain_context")
DB_PATH = Path(os.getenv("ANNASEO_DB", "./annaseo.db"))


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1 — INDUSTRY DOMAIN MAP
# What each industry ACCEPTS and what it REJECTS
# Cross-domain terms are words that are valid in some industries, invalid in others
# ─────────────────────────────────────────────────────────────────────────────

class Industry(str, Enum):
    FOOD_SPICES  = "food_spices"
    TOURISM      = "tourism"
    ECOMMERCE    = "ecommerce"
    HEALTHCARE   = "healthcare"
    AGRICULTURE  = "agriculture"
    EDUCATION    = "education"
    REAL_ESTATE  = "real_estate"
    TECH_SAAS    = "tech_saas"
    WELLNESS     = "wellness"
    RESTAURANT   = "restaurant"
    FASHION      = "fashion"
    GENERAL      = "general"


# Cross-domain vocabulary:
# Words that are VALID for some industries and INVALID for others
# Format: word → {industry: "accept" or "reject"}
CROSS_DOMAIN_VOCABULARY: Dict[str, Dict[str, str]] = {

    # ── Tourism / travel words ────────────────────────────────────────────────
    "tour":       {Industry.TOURISM: "accept",    Industry.FOOD_SPICES: "reject",
                   Industry.ECOMMERCE: "reject",  Industry.HEALTHCARE: "reject"},
    "travel":     {Industry.TOURISM: "accept",    Industry.FOOD_SPICES: "reject",
                   Industry.ECOMMERCE: "reject"},
    "trip":       {Industry.TOURISM: "accept",    Industry.FOOD_SPICES: "reject"},
    "holiday":    {Industry.TOURISM: "accept",    Industry.FOOD_SPICES: "reject",
                   Industry.ECOMMERCE: "conditional"},  # "holiday sale" = ok for ecommerce
    "destination":{Industry.TOURISM: "accept",    Industry.FOOD_SPICES: "reject"},
    "hotel":      {Industry.TOURISM: "accept",    Industry.FOOD_SPICES: "reject"},
    "resort":     {Industry.TOURISM: "accept",    Industry.FOOD_SPICES: "reject",
                   Industry.WELLNESS: "accept"},   # "wellness resort" is valid
    "visit":      {Industry.TOURISM: "accept",    Industry.FOOD_SPICES: "reject"},
    "itinerary":  {Industry.TOURISM: "accept",    Industry.FOOD_SPICES: "reject"},
    "flight":     {Industry.TOURISM: "accept",    Industry.FOOD_SPICES: "reject"},
    "booking":    {Industry.TOURISM: "accept",    Industry.ECOMMERCE: "accept",
                   Industry.FOOD_SPICES: "reject"},

    # ── Geographic / cultural words (valid for tourism, not always for products) ─
    "sri lanka":  {Industry.TOURISM: "accept",    Industry.FOOD_SPICES: "accept",
                   Industry.AGRICULTURE: "accept"},   # "sri lanka cinnamon" = valid for spices
    "ceylon":     {Industry.TOURISM: "accept",    Industry.FOOD_SPICES: "accept",
                   Industry.AGRICULTURE: "accept"},   # "ceylon cinnamon" = product name
    "plantation": {Industry.TOURISM: "accept",    Industry.FOOD_SPICES: "accept",
                   Industry.AGRICULTURE: "accept"},   # both valid
    "origin":     {Industry.TOURISM: "accept",    Industry.FOOD_SPICES: "accept",
                   Industry.AGRICULTURE: "accept"},   # "spice origin" = valid
    "kerala":     {Industry.TOURISM: "accept",    Industry.FOOD_SPICES: "accept",
                   Industry.AGRICULTURE: "accept"},

    # ── E-commerce / product words ────────────────────────────────────────────
    "buy":        {Industry.ECOMMERCE: "accept",  Industry.FOOD_SPICES: "accept",
                   Industry.TOURISM: "reject",     Industry.EDUCATION: "reject"},
    "price":      {Industry.ECOMMERCE: "accept",  Industry.FOOD_SPICES: "accept",
                   Industry.TOURISM: "conditional",  # "tour price" = ok
                   Industry.HEALTHCARE: "conditional"},  # "medicine price" = ok
    "wholesale":  {Industry.FOOD_SPICES: "accept", Industry.ECOMMERCE: "accept",
                   Industry.TOURISM: "reject"},
    "bulk":       {Industry.FOOD_SPICES: "accept", Industry.ECOMMERCE: "accept",
                   Industry.TOURISM: "reject"},
    "kg":         {Industry.FOOD_SPICES: "accept", Industry.AGRICULTURE: "accept",
                   Industry.ECOMMERCE: "accept",   Industry.TOURISM: "reject"},
    "organic":    {Industry.FOOD_SPICES: "accept", Industry.AGRICULTURE: "accept",
                   Industry.WELLNESS: "accept",    Industry.TOURISM: "conditional"},

    # ── Health / medical words ────────────────────────────────────────────────
    "benefits":   {Industry.FOOD_SPICES: "accept", Industry.WELLNESS: "accept",
                   Industry.HEALTHCARE: "accept",  Industry.TOURISM: "conditional"},
    "treatment":  {Industry.HEALTHCARE: "accept",  Industry.WELLNESS: "accept",
                   Industry.FOOD_SPICES: "reject",  Industry.TOURISM: "reject"},
    "dosage":     {Industry.HEALTHCARE: "accept",  Industry.WELLNESS: "accept",
                   Industry.FOOD_SPICES: "reject"},
    "ayurveda":   {Industry.HEALTHCARE: "accept",  Industry.WELLNESS: "accept",
                   Industry.FOOD_SPICES: "accept",  Industry.TOURISM: "accept"},  # Kerala Ayurveda tourism

    # ── DIY / craft / social media ────────────────────────────────────────────
    "challenge":  {Industry.TOURISM: "reject",    Industry.FOOD_SPICES: "reject",
                   Industry.ECOMMERCE: "reject",  Industry.HEALTHCARE: "reject"},
    "meme":       {"__all__": "reject"},
    "viral":      {"__all__": "reject"},
    "tiktok":     {"__all__": "reject"},
    "instagram":  {"__all__": "reject"},
    "twitter":    {"__all__": "reject"},
    "facebook":   {"__all__": "reject"},
}


# Industry-specific ACCEPT signals (keywords that are clearly on-domain)
INDUSTRY_ACCEPT_SIGNALS: Dict[str, List[str]] = {
    Industry.FOOD_SPICES: [
        "spice","spices","herb","herbs","flavour","flavor","aroma","seasoning",
        "cinnamon","turmeric","cardamom","pepper","clove","ginger","nutmeg",
        "piperine","curcumin","capsaicin","oleoresin","allicin",
        "organic","natural","pure","ceylon","malabar","wayanad",
        "benefits","health","recipe","cooking","culinary","wholesale","bulk",
        "buy","price","kg","gram","export","import","supplier","manufacturer",
    ],
    Industry.TOURISM: [
        "tour","travel","trip","visit","tourist","tourism","destination",
        "hotel","resort","flight","booking","itinerary","package",
        "wildlife","heritage","beach","mountain","backwater",
        "guide","experience","adventure","culture","history",
        "sri lanka","kerala","india","wayanad","munnar","alleppey",
    ],
    Industry.HEALTHCARE: [
        "health","medical","doctor","hospital","clinic","treatment","therapy",
        "medicine","drug","symptoms","diagnosis","patient","care","wellness",
        "ayurveda","yoga","meditation","nutrition","supplement",
    ],
    Industry.ECOMMERCE: [
        "buy","shop","store","product","price","order","delivery","shipping",
        "discount","offer","sale","review","rating","compare","brand",
    ],
    Industry.AGRICULTURE: [
        "farm","farming","crop","harvest","cultivation","plantation","soil",
        "seeds","yield","organic","fertilizer","irrigation","export","agri",
        "spice","herb","ceylon","malabar","wayanad",
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2 — PROJECT DOMAIN PROFILE
# Per-project configuration. Stored in DB. Editable by user.
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ProjectDomainProfile:
    project_id:         str
    project_name:       str
    industry:           str           # Industry enum value
    seed_keywords:      List[str]     # the universe seeds
    domain_description: str           # one-paragraph description of the business
    accept_overrides:   List[str]     # words explicitly ACCEPTED despite global rules
    reject_overrides:   List[str]     # words explicitly REJECTED for this project only
    cross_domain_rules: Dict[str,str] # word → "accept"|"reject" for this project
    content_angles:     List[str]     # what content should focus on
    avoid_angles:       List[str]     # what content should NOT cover
    created_at:         str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at:         str = field(default_factory=lambda: datetime.utcnow().isoformat())


# Pre-built profiles that auto-apply based on Industry selection
DEFAULT_DOMAIN_PROFILES: Dict[str, dict] = {

    Industry.FOOD_SPICES: {
        "accept_overrides":  ["ceylon cinnamon","ceylon","sri lanka spice","plantation","origin"],
        "reject_overrides":  ["tour","travel","trip","holiday","hotel","resort","visit","itinerary"],
        "cross_domain_rules":{"ceylon": "accept", "plantation": "accept", "tour": "reject"},
        "content_angles":    ["health benefits","cooking and recipes","sourcing and quality",
                              "buying guide","wholesale","organic certification","ayurveda"],
        "avoid_angles":      ["travel itineraries","tourist spots","hotel reviews"],
    },

    Industry.TOURISM: {
        "accept_overrides":  ["ceylon cinnamon tour","spice plantation tour","ayurveda tourism",
                              "culinary tour","spice route","spice history"],
        "reject_overrides":  ["buy spice online","wholesale price","kg price","bulk order"],
        "cross_domain_rules":{"cinnamon": "accept", "spice": "accept",
                              "plantation": "accept", "ceylon": "accept",
                              "tour": "accept", "travel": "accept"},
        "content_angles":    ["tourist experiences","travel guides","destination highlights",
                              "cultural heritage","culinary tourism","spice route history"],
        "avoid_angles":      ["product pricing","wholesale buying","cultivation methods"],
    },

    Industry.HEALTHCARE: {
        "accept_overrides":  ["cinnamon medicine","spice therapy","ayurvedic cinnamon"],
        "reject_overrides":  ["tour","travel","wholesale","bulk order"],
        "cross_domain_rules":{"cinnamon": "accept", "benefits": "accept", "tour": "reject"},
        "content_angles":    ["medical research","health benefits","dosage guidelines",
                              "drug interactions","ayurvedic use","clinical studies"],
        "avoid_angles":      ["travel","cooking recipes","wholesale prices"],
    },

    Industry.ECOMMERCE: {
        "accept_overrides":  ["holiday sale","christmas offer","gift set"],
        "reject_overrides":  ["tour","travel","trip"],
        "cross_domain_rules":{"holiday": "accept", "gift": "accept", "tour": "reject"},
        "content_angles":    ["product reviews","buying guides","comparison","pricing",
                              "quality certification","delivery","customer reviews"],
        "avoid_angles":      ["travel itineraries","medical claims without evidence"],
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3 — DOMAIN CONTEXT DATABASE
# ─────────────────────────────────────────────────────────────────────────────

class DomainContextDB:
    def __init__(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._init()

    def _init(self):
        self._db.executescript("""
        CREATE TABLE IF NOT EXISTS dc_project_profiles (
            project_id          TEXT PRIMARY KEY,
            project_name        TEXT,
            industry            TEXT NOT NULL,
            seed_keywords       TEXT DEFAULT '[]',
            domain_description  TEXT DEFAULT '',
            accept_overrides    TEXT DEFAULT '[]',
            reject_overrides    TEXT DEFAULT '[]',
            cross_domain_rules  TEXT DEFAULT '{}',
            content_angles      TEXT DEFAULT '[]',
            avoid_angles        TEXT DEFAULT '[]',
            created_at          TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at          TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS dc_project_tunings (
            tuning_id           TEXT PRIMARY KEY,
            project_id          TEXT NOT NULL,
            tuning_scope        TEXT NOT NULL,   -- "project" | "global"
            tuning_type         TEXT NOT NULL,   -- "filter"|"prompt_edit"|"parameter"|"scoring_rule"
            engine_file         TEXT NOT NULL,
            fn_target           TEXT NOT NULL,
            problem             TEXT NOT NULL,
            fix                 TEXT NOT NULL,
            before_value        TEXT DEFAULT '',
            after_value         TEXT DEFAULT '',
            status              TEXT DEFAULT 'pending',
            approved_by         TEXT DEFAULT '',
            approved_at         TEXT DEFAULT '',
            rollback_snap       TEXT DEFAULT '',
            evidence            TEXT DEFAULT '[]',
            created_at          TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS dc_classification_log (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id          TEXT NOT NULL,
            keyword             TEXT NOT NULL,
            verdict             TEXT NOT NULL,   -- "accept"|"reject"|"ambiguous"
            reason              TEXT DEFAULT '',
            score               REAL DEFAULT 0,
            industry            TEXT DEFAULT '',
            created_at          TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS dc_global_tunings (
            tuning_id           TEXT PRIMARY KEY,
            tuning_type         TEXT NOT NULL,
            engine_file         TEXT NOT NULL,
            fn_target           TEXT NOT NULL,
            problem             TEXT NOT NULL,
            fix                 TEXT NOT NULL,
            before_value        TEXT DEFAULT '',
            after_value         TEXT DEFAULT '',
            status              TEXT DEFAULT 'pending',
            approved_by         TEXT DEFAULT '',
            approved_at         TEXT DEFAULT '',
            rollback_snap       TEXT DEFAULT '',
            scope_note          TEXT DEFAULT 'affects all projects',
            created_at          TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_dc_profiles   ON dc_project_profiles(project_id);
        CREATE INDEX IF NOT EXISTS idx_dc_tunings_proj ON dc_project_tunings(project_id);
        CREATE INDEX IF NOT EXISTS idx_dc_tunings_scope ON dc_project_tunings(tuning_scope);
        CREATE INDEX IF NOT EXISTS idx_dc_clf_project ON dc_classification_log(project_id);
        """)
        self._db.commit()

    def save_profile(self, p: ProjectDomainProfile):
        self._db.execute("""
            INSERT OR REPLACE INTO dc_project_profiles
            (project_id, project_name, industry, seed_keywords, domain_description,
             accept_overrides, reject_overrides, cross_domain_rules,
             content_angles, avoid_angles, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (p.project_id, p.project_name, p.industry,
              json.dumps(p.seed_keywords), p.domain_description,
              json.dumps(p.accept_overrides), json.dumps(p.reject_overrides),
              json.dumps(p.cross_domain_rules),
              json.dumps(p.content_angles), json.dumps(p.avoid_angles),
              datetime.utcnow().isoformat()))
        self._db.commit()

    def get_profile(self, project_id: str) -> Optional[dict]:
        row = self._db.execute(
            "SELECT * FROM dc_project_profiles WHERE project_id=?", (project_id,)
        ).fetchone()
        return dict(row) if row else None

    def log_classification(self, project_id: str, keyword: str, verdict: str,
                            reason: str, score: float, industry: str):
        self._db.execute("""
            INSERT INTO dc_classification_log (project_id,keyword,verdict,reason,score,industry)
            VALUES (?,?,?,?,?,?)
        """, (project_id, keyword, verdict, reason, score, industry))
        self._db.commit()

    def save_project_tuning(self, tuning: dict):
        self._db.execute("""
            INSERT OR REPLACE INTO dc_project_tunings
            (tuning_id,project_id,tuning_scope,tuning_type,engine_file,fn_target,
             problem,fix,before_value,after_value,status,evidence)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (tuning["tuning_id"], tuning.get("project_id",""),
              tuning.get("tuning_scope","project"),
              tuning["tuning_type"], tuning["engine_file"],
              tuning["fn_target"], tuning["problem"], tuning["fix"],
              tuning.get("before_value",""), tuning.get("after_value",""),
              "pending", json.dumps(tuning.get("evidence",[]))))
        self._db.commit()

    def save_global_tuning(self, tuning: dict):
        self._db.execute("""
            INSERT OR REPLACE INTO dc_global_tunings
            (tuning_id,tuning_type,engine_file,fn_target,problem,fix,
             before_value,after_value,scope_note)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (tuning["tuning_id"], tuning["tuning_type"],
              tuning["engine_file"], tuning["fn_target"],
              tuning["problem"], tuning["fix"],
              tuning.get("before_value",""), tuning.get("after_value",""),
              tuning.get("scope_note","affects all projects")))
        self._db.commit()

    def get_project_tunings(self, project_id: str,
                             status: str = None) -> List[dict]:
        q = "SELECT * FROM dc_project_tunings WHERE project_id=?"
        p = [project_id]
        if status: q += " AND status=?"; p.append(status)
        return [dict(r) for r in self._db.execute(q, p).fetchall()]

    def get_global_tunings(self, status: str = None) -> List[dict]:
        q = "SELECT * FROM dc_global_tunings"
        p = []
        if status: q += " WHERE status=?"; p.append(status)
        return [dict(r) for r in self._db.execute(q, p).fetchall()]


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4 — DOMAIN CONTEXT ENGINE (classification + scoring)
# ─────────────────────────────────────────────────────────────────────────────

class DomainContextEngine:
    """
    Core engine. Call this:
    1. Before passing keywords to OffTopicFilter — domain-aware pre-filter
    2. After P10 produces pillars — validate each pillar against domain
    3. In content briefs — validate content angles against domain

    Project-isolated: each project has its own verdict.
    "cinnamon tour" → REJECT for spice project, ACCEPT for travel project.
    """

    def __init__(self):
        self._db = DomainContextDB()

    # ── Project setup ──────────────────────────────────────────────────────────

    def setup_project(self, project_id: str, project_name: str,
                       industry: str, seeds: List[str],
                       description: str = "",
                       custom_accepts: List[str] = None,
                       custom_rejects: List[str] = None) -> ProjectDomainProfile:
        """
        Create or update a project's domain profile.
        Auto-populates from DEFAULT_DOMAIN_PROFILES for the industry.
        Custom accepts/rejects extend (not replace) the defaults.
        """
        defaults = DEFAULT_DOMAIN_PROFILES.get(industry, {})
        profile  = ProjectDomainProfile(
            project_id=project_id,
            project_name=project_name,
            industry=industry,
            seed_keywords=seeds,
            domain_description=description,
            accept_overrides=(defaults.get("accept_overrides",[]) +
                               (custom_accepts or [])),
            reject_overrides=(defaults.get("reject_overrides",[]) +
                               (custom_rejects or [])),
            cross_domain_rules=defaults.get("cross_domain_rules", {}),
            content_angles=defaults.get("content_angles", []),
            avoid_angles=defaults.get("avoid_angles", []),
        )
        self._db.save_profile(profile)
        log.info(f"[DomainContext] Project setup: {project_id} ({industry})")
        return profile

    # ── Classification ─────────────────────────────────────────────────────────

    def classify(self, keyword: str, project_id: str) -> dict:
        """
        Classify a keyword as ACCEPT, REJECT, or AMBIGUOUS for this project.
        Project-isolated: same keyword can have different verdicts per project.

        Returns:
          {verdict, score, reason, industry, is_cross_domain, suggested_action}
        """
        profile = self._db.get_profile(project_id)
        if not profile:
            return {"verdict": "accept", "score": 50.0,
                    "reason": "No domain profile found — allowing by default",
                    "industry": "unknown", "is_cross_domain": False}

        industry      = profile["industry"]
        kw_lower      = keyword.lower()
        words         = set(kw_lower.split())
        accept_list   = json.loads(profile.get("accept_overrides","[]"))
        reject_list   = json.loads(profile.get("reject_overrides","[]"))
        cross_rules   = json.loads(profile.get("cross_domain_rules","{}"))

        # ── GATE 0: Universal noise — __all__: reject — no project rule can override ──
        # Must run first so meme/viral/tiktok/instagram always reject regardless of
        # project cross-domain rules (e.g. tourism project accepting "cinnamon").
        for word in words:
            vocab = CROSS_DOMAIN_VOCABULARY.get(word, {})
            if vocab.get("__all__") == "reject":
                return self._result("reject", 0,
                    f"Universal noise word: '{word}'",
                    industry, project_id, keyword, True)

        # ── GATE 1: Project explicit reject overrides ─────────────────────────────────
        for phrase in reject_list:
            if phrase.lower() in kw_lower:
                return self._result("reject", 5, f"Project reject override: '{phrase}'",
                                     industry, project_id, keyword, True)

        # ── GATE 2: Cross-domain vocabulary industry-specific rejects ─────────────────
        # Scan ALL words before any accept rule fires — prevents a project cross-domain
        # accept rule (e.g. "cinnamon" → accept for tourism) from rescuing a keyword
        # that also contains a hard industry-reject word (e.g. "buy", "kg" for tourism).
        is_cross_domain = False
        for word in words:
            vocab = CROSS_DOMAIN_VOCABULARY.get(word, {})
            if not vocab:
                continue
            is_cross_domain = True
            if vocab.get(industry) == "reject":
                return self._result("reject", 5,
                    f"Cross-domain word '{word}' = rejected for {industry}",
                    industry, project_id, keyword, True)

        # ── GATE 3: Project explicit accept overrides ─────────────────────────────────
        for phrase in accept_list:
            if phrase.lower() in kw_lower:
                return self._result("accept", 95, f"Explicit accept override: '{phrase}'",
                                     industry, project_id, keyword, True)

        # ── GATE 4: Project cross-domain rules ────────────────────────────────────────
        for word, verdict in cross_rules.items():
            if word.lower() in kw_lower:
                if verdict == "accept":
                    return self._result("accept", 85,
                        f"Project cross-domain rule: '{word}' = accept for {industry}",
                        industry, project_id, keyword, True)
                elif verdict == "reject":
                    return self._result("reject", 5,
                        f"Project cross-domain rule: '{word}' = reject for {industry}",
                        industry, project_id, keyword, True)

        # ── GATE 5: Cross-domain vocabulary industry-specific accepts ─────────────────
        for word in words:
            vocab = CROSS_DOMAIN_VOCABULARY.get(word, {})
            verdict = vocab.get(industry)
            if verdict == "accept":
                score = self._domain_score(kw_lower, industry)
                return self._result("accept", max(score, 70),
                    f"Cross-domain word '{word}' = accepted for {industry}",
                    industry, project_id, keyword, True)
            # conditional falls through to domain scoring

        # ── GATE 6: Domain scoring — how many accept signals does this keyword have? ──
        score = self._domain_score(kw_lower, industry)
        if score >= 65:
            return self._result("accept", score,
                f"Domain relevance score {score:.0f}/100 — accepted",
                industry, project_id, keyword, is_cross_domain)
        if score >= 35:
            return self._result("ambiguous", score,
                f"Domain relevance score {score:.0f}/100 — needs human review",
                industry, project_id, keyword, is_cross_domain)
        return self._result("reject", score,
            f"Domain relevance score {score:.0f}/100 — below threshold for {industry}",
            industry, project_id, keyword, is_cross_domain)

    def classify_batch(self, keywords: List[str],
                        project_id: str) -> Tuple[List[str], List[str], List[dict]]:
        """
        Classify a batch. Returns (accepted, rejected, ambiguous_with_details).
        Drop-in for OffTopicFilter at the project level.
        """
        accepted, rejected, ambiguous = [], [], []
        for kw in keywords:
            result = self.classify(kw, project_id)
            if result["verdict"] == "accept":
                accepted.append(kw)
            elif result["verdict"] == "reject":
                rejected.append(kw)
            else:
                ambiguous.append({**result, "keyword": kw})
        return accepted, rejected, ambiguous

    def validate_pillars(self, pillars: dict,
                          project_id: str) -> Tuple[dict, List[dict]]:
        """
        Validate P10's pillar outputs against the domain profile.
        Returns (valid_pillars, rejected_pillars_with_reasons).
        """
        valid, rejected = {}, []
        for cluster_name, pillar_data in pillars.items():
            kw     = pillar_data.get("pillar_keyword", cluster_name)
            result = self.classify(kw, project_id)
            if result["verdict"] == "reject":
                rejected.append({
                    "pillar_keyword":  kw,
                    "cluster":         cluster_name,
                    "reason":          result["reason"],
                    "industry":        result["industry"],
                })
                log.info(f"[DomainContext] Pillar rejected: '{kw}' — {result['reason']}")
            else:
                valid[cluster_name] = pillar_data
        return valid, rejected

    def validate_content_brief(self, brief: dict,
                                 project_id: str) -> dict:
        """
        Check content brief angles against domain profile.
        Returns brief with flagged off-domain angles removed/replaced.
        """
        profile = self._db.get_profile(project_id)
        if not profile:
            return brief

        avoid   = json.loads(profile.get("avoid_angles","[]"))
        angles  = brief.get("content_angles", [])
        h2s     = brief.get("h2_headings", [])

        # Flag any heading that overlaps with avoid_angles
        flagged_h2s = []
        clean_h2s   = []
        for h2 in h2s:
            if any(a.lower() in h2.lower() for a in avoid):
                flagged_h2s.append(h2)
            else:
                clean_h2s.append(h2)

        if flagged_h2s:
            brief["h2_headings"]     = clean_h2s
            brief["removed_angles"]  = flagged_h2s
            brief["domain_warning"]  = f"Removed {len(flagged_h2s)} off-domain H2s: {flagged_h2s}"
            log.info(f"[DomainContext] Brief: removed {len(flagged_h2s)} off-domain headings")

        return brief

    # ── Scoring ───────────────────────────────────────────────────────────────

    def _domain_score(self, keyword: str, industry: str) -> float:
        """Score how relevant a keyword is to the given industry (0-100)."""
        signals  = INDUSTRY_ACCEPT_SIGNALS.get(industry, [])
        words    = set(keyword.lower().split())
        matches  = sum(1 for s in signals if s.lower() in keyword.lower())
        if matches >= 3: return 95.0
        if matches == 2: return 80.0
        if matches == 1: return 65.0
        # No direct signal — check if any word is a seed keyword in common domains
        if len(words) >= 2: return 45.0   # multi-word = more specific = more likely valid
        return 25.0   # single unmatched word

    def _result(self, verdict: str, score: float, reason: str,
                 industry: str, project_id: str, keyword: str,
                 is_cross_domain: bool) -> dict:
        self._db.log_classification(project_id, keyword, verdict, reason, score, industry)
        return {
            "verdict":          verdict,
            "score":            round(score, 1),
            "reason":           reason,
            "industry":         industry,
            "is_cross_domain":  is_cross_domain,
            "suggested_action": (
                "Accept — domain relevant"   if verdict == "accept" else
                "Reject — off domain"        if verdict == "reject" else
                "Ask user — unclear domain fit"
            )
        }


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5 — TUNING REGISTRY (project-level vs global separation)
# ─────────────────────────────────────────────────────────────────────────────

class TuningRegistry:
    """
    Manages the separation between:
    - PROJECT tunings: kill words, accept overrides, prompt edits for ONE project
    - GLOBAL tunings:  engine code fixes, threshold changes, algorithm bugs

    Rule: User feedback on a keyword → PROJECT tuning
          Code bug / scoring algorithm issue → GLOBAL tuning
          User feedback on content quality → PROJECT tuning (prompt layer 2/3)
          Content engine structural fix → GLOBAL tuning (prompt layer 1)
    """

    def __init__(self):
        self._db = DomainContextDB()

    def submit_feedback(self, project_id: str, keyword: str,
                         verdict: str, reason: str,
                         industry: str) -> dict:
        """
        User marks keyword as wrong for their project.
        Determine whether this needs a project tuning or global tuning.
        """
        kw_lower = keyword.lower()
        words    = set(kw_lower.split())

        CROSS_WORDS = set(CROSS_DOMAIN_VOCABULARY.keys())

        if words & CROSS_WORDS:
            # It's a cross-domain word — this is a PROJECT tuning
            # The word might be valid in another project's industry
            bad_words = list(words & CROSS_WORDS)
            tuning_id = f"pt_{hashlib.md5(f'{project_id}{keyword}'.encode()).hexdigest()[:10]}"
            self._db.save_project_tuning({
                "tuning_id":     tuning_id,
                "project_id":    project_id,
                "tuning_scope":  "project",
                "tuning_type":   "filter",
                "engine_file":   "annaseo_domain_context.py",
                "fn_target":     "ProjectDomainProfile.reject_overrides",
                "problem":       f"'{keyword}' is off-domain for {industry}: {reason}",
                "fix":           f"Add '{keyword}' to project reject_overrides",
                "before_value":  f"reject_overrides for project {project_id}",
                "after_value":   f"Add: {bad_words}",
                "evidence":      [f"User marked '{keyword}' bad: {reason}"],
            })
            scope = "project"
            note  = f"Cross-domain word found. Affects this project only — won't affect other projects with different industry."
        else:
            # Not a cross-domain word — could be an actual OffTopicFilter gap
            # This is a GLOBAL tuning (affects all projects)
            tuning_id = f"gt_{hashlib.md5(f'{keyword}{reason}'.encode()).hexdigest()[:10]}"
            self._db.save_global_tuning({
                "tuning_id":    tuning_id,
                "tuning_type":  "filter",
                "engine_file":  "annaseo_addons.py",
                "fn_target":    "OffTopicFilter.GLOBAL_KILL",
                "problem":      f"'{keyword}' not in GLOBAL_KILL — universal noise word",
                "fix":          f"Add '{keyword}' to GLOBAL_KILL (affects all projects)",
                "before_value": "GLOBAL_KILL missing this word",
                "after_value":  f'"{keyword}",  # universal noise',
                "scope_note":   "Universal noise — rejected in ALL projects regardless of industry",
            })
            scope = "global"
            note  = f"Universal noise word. Added to GLOBAL kill list — applies to all projects."

        return {
            "tuning_id": tuning_id,
            "scope":     scope,
            "note":      note,
        }

    def get_project_kill_list(self, project_id: str) -> List[str]:
        """Get the merged kill list for a specific project."""
        profile = self._db.get_profile(project_id)
        if not profile:
            return []
        return json.loads(profile.get("reject_overrides","[]"))

    def get_project_accept_list(self, project_id: str) -> List[str]:
        """Get the explicit accept list for a specific project."""
        profile = self._db.get_profile(project_id)
        if not profile:
            return []
        return json.loads(profile.get("accept_overrides","[]"))


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6 — RSD SCOPE DEFINER (Global vs Project RSD)
# ─────────────────────────────────────────────────────────────────────────────

"""
RESEARCH & SELF DEVELOPMENT — TWO SCOPES

GLOBAL RSD (applies to ALL projects)
  Focus:  Engine code quality, algorithm correctness, code bugs
  What:   Monitors engine health scores across all projects
          Watches for systematic failures (same error in all projects)
          Keeps engine code, prompts (Layer 1), thresholds current
          Tracks industry news and new SEO signals
  Tuning: Touches engine .py files directly
  Gate:   Same manual approval + rollback
  Who:    Ruflo system admin

PROJECT RSD (applies to one project only)
  Focus:  Content quality for THIS business/industry
          Keyword relevance for THIS seed/domain
          Content angle accuracy for THIS audience
  What:   Reviews live keyword results per project run
          Scores content for domain fit (not just SEO signals)
          Catches domain-specific errors the global filter missed
          Tracks project-specific ranking performance
  Tuning: Touches ProjectDomainProfile (reject_overrides, cross_domain_rules)
          Touches Layer 2 (brand) and Layer 3 (article) prompts
          NEVER touches Layer 1 system prompt (that is global)
  Gate:   Same manual approval (per project)
  Who:    Project owner / SEO manager

Decision table:
  "cinnamon tour" bad for spice project  → PROJECT tuning
  "cinnamon tour" good for travel project → project accept override
  P8 topic naming uses wrong prompt       → GLOBAL tuning
  Article lacks E-E-A-T overall          → GLOBAL tuning (Layer 1)
  Article wrong angle for this business  → PROJECT tuning (Layer 2/3)
  OffTopicFilter missing "meme"           → GLOBAL tuning (universal noise)
  OffTopicFilter missing "tour" for spices→ PROJECT tuning (domain-specific)
"""

SCOPE_DECISION_RULES = [
    {
        "condition":   "keyword is in CROSS_DOMAIN_VOCABULARY",
        "scope":       "project",
        "reason":      "Cross-domain words have different meaning per industry",
        "tuning_file": "dc_project_profiles (reject_overrides or accept_overrides)",
    },
    {
        "condition":   "keyword is pure noise (meme, viral, tiktok)",
        "scope":       "global",
        "reason":      "Universal noise — no industry would want this",
        "tuning_file": "annaseo_addons.py → OffTopicFilter.GLOBAL_KILL",
    },
    {
        "condition":   "content lacks E-E-A-T structure globally",
        "scope":       "global",
        "reason":      "Structural content issue — Layer 1 system prompt",
        "tuning_file": "ruflo_content_engine.py → Layer1_system_prompt",
    },
    {
        "condition":   "content wrong angle for this business",
        "scope":       "project",
        "reason":      "Domain/audience specific — Layer 2 or 3 prompt",
        "tuning_file": "project brand config (Layer 2) or article brief (Layer 3)",
    },
    {
        "condition":   "engine code bug (wrong phase output, crash, logic error)",
        "scope":       "global",
        "reason":      "Code error affects all projects",
        "tuning_file": "relevant engine .py file",
    },
    {
        "condition":   "threshold too loose/tight (score 75→80, dedup 0.85→0.80)",
        "scope":       "global",
        "reason":      "Algorithm parameter — affects all projects",
        "tuning_file": "relevant engine .py file → Cfg class or constant",
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 7 — FASTAPI ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

try:
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel as PM
    from typing import Optional as Opt, List as L

    app = FastAPI(title="AnnaSEO Domain Context Engine",
                  description="Per-project domain classification, cross-domain vocabulary, tuning scope separation")

    dce = DomainContextEngine()
    tr  = TuningRegistry()

    class ProjectSetupBody(PM):
        project_name:     str
        industry:         str
        seed_keywords:    L[str] = []
        description:      str = ""
        custom_accepts:   L[str] = []
        custom_rejects:   L[str] = []

    class ClassifyBody(PM):
        keywords:   L[str]
        project_id: str

    class FeedbackBody(PM):
        project_id: str
        keyword:    str
        verdict:    str
        reason:     str
        industry:   str

    @app.post("/api/dc/projects/{project_id}/setup")
    def setup_project(project_id: str, body: ProjectSetupBody):
        p = dce.setup_project(project_id, body.project_name, body.industry,
                               body.seed_keywords, body.description,
                               body.custom_accepts, body.custom_rejects)
        return {"project_id": p.project_id, "industry": p.industry,
                "accept_overrides": p.accept_overrides,
                "reject_overrides": p.reject_overrides}

    @app.get("/api/dc/projects/{project_id}")
    def get_project(project_id: str):
        profile = DomainContextDB().get_profile(project_id)
        if not profile: raise HTTPException(404, "Project not found")
        return profile

    @app.post("/api/dc/classify")
    def classify(body: ClassifyBody):
        results = {}
        for kw in body.keywords[:200]:
            results[kw] = dce.classify(kw, body.project_id)
        return results

    @app.post("/api/dc/validate-pillars/{project_id}")
    def validate_pillars(project_id: str, pillars: dict):
        valid, rejected = dce.validate_pillars(pillars, project_id)
        return {"valid_pillars": valid, "rejected": rejected}

    @app.post("/api/dc/feedback")
    def feedback(body: FeedbackBody):
        return tr.submit_feedback(body.project_id, body.keyword,
                                   body.verdict, body.reason, body.industry)

    @app.get("/api/dc/tunings/project/{project_id}")
    def project_tunings(project_id: str, status: Opt[str] = None):
        return DomainContextDB().get_project_tunings(project_id, status)

    @app.get("/api/dc/tunings/global")
    def global_tunings(status: Opt[str] = None):
        return DomainContextDB().get_global_tunings(status)

    @app.get("/api/dc/scope-rules")
    def scope_rules():
        return SCOPE_DECISION_RULES

    @app.get("/api/dc/cross-domain-vocabulary")
    def cross_domain_vocab():
        return CROSS_DOMAIN_VOCABULARY

except ImportError:
    pass


# ─────────────────────────────────────────────────────────────────────────────
# CLI DEMO
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    print("\n  DOMAIN CONTEXT ENGINE DEMO")
    print("  " + "─"*52)

    dce = DomainContextEngine()

    # Setup spice project
    dce.setup_project(
        project_id="proj_spice_001",
        project_name="Ceylon Spice Exports",
        industry=Industry.FOOD_SPICES,
        seeds=["cinnamon","turmeric","cardamom"],
        description="B2B and B2C organic spice exporter based in Kerala, India"
    )

    # Setup tourism project
    dce.setup_project(
        project_id="proj_tour_001",
        project_name="Sri Lanka Spice Tours",
        industry=Industry.TOURISM,
        seeds=["sri lanka tour","ceylon cinnamon","spice route"],
        description="Tourism operator offering spice plantation tours in Sri Lanka"
    )

    test_keywords = [
        "cinnamon tour",
        "ceylon cinnamon tour",
        "cinnamon benefits",
        "buy cinnamon online",
        "cinnamon travel guide",
        "ceylon cinnamon grows in sri lanka",
        "cinnamon price per kg",
        "spice plantation visit",
        "organic cinnamon",
        "cinnamon meme",
        "cinnamon viral tiktok",
    ]

    print("\n  KEYWORD → SPICE PROJECT (food_spices)")
    print("  " + "─"*52)
    for kw in test_keywords:
        r = dce.classify(kw, "proj_spice_001")
        icon = "✓" if r["verdict"]=="accept" else "✗" if r["verdict"]=="reject" else "?"
        cross = " [cross-domain]" if r["is_cross_domain"] else ""
        print(f"  {icon} {kw:<38} {r['score']:5.0f}  {r['reason'][:50]}{cross}")

    print("\n  KEYWORD → TOURISM PROJECT (tourism)")
    print("  " + "─"*52)
    for kw in test_keywords:
        r = dce.classify(kw, "proj_tour_001")
        icon = "✓" if r["verdict"]=="accept" else "✗" if r["verdict"]=="reject" else "?"
        cross = " [cross-domain]" if r["is_cross_domain"] else ""
        print(f"  {icon} {kw:<38} {r['score']:5.0f}  {r['reason'][:50]}{cross}")

    print("\n  SCOPE DECISION RULES")
    print("  " + "─"*52)
    for rule in SCOPE_DECISION_RULES:
        print(f"  [{rule['scope'].upper():7}] {rule['condition'][:55]}")
        print(f"           → {rule['tuning_file'][:60]}")
