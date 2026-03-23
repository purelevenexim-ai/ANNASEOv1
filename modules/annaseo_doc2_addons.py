"""
================================================================================
ANNASEO — ADDITIONS FROM SECOND PROJECT DOCUMENT
================================================================================
5 genuine additions. Everything else in the document was already built.

1. ClusterTypeTaxonomy    — Pillar/Subtopic/Support/Conversion classification
2. KeywordStatusLifecycle — Not Used → Planned → In Content → Published → Ranking → Optimized
3. PromptVersioning       — DB-backed prompt store with A/B + performance tracking
4. MemorySystem           — Project/Learning/Interaction memory (Brand voice already exists)
5. CompetitorAttackPlan   — Synthesises gap analysis into prioritised attack sequence

Integration points (all additive, no existing code changes):
  ClusterTypeTaxonomy → Add to P9_ClusterFormation output, add cluster_type to DB
  KeywordStatusLifecycle → Add keyword_status column to keywords table
  PromptVersioning → New table prompt_versions, wrapper around all AI calls
  MemorySystem → New table ai_memory, inject into prompts dynamically
  CompetitorAttackPlan → New Claude call at end of M1 Business Intelligence Engine
================================================================================
"""

from __future__ import annotations

import os, json, hashlib, logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger("annaseo.doc2_addons")


# ─────────────────────────────────────────────────────────────────────────────
# 1. CLUSTER TYPE TAXONOMY
# Add cluster_type field to P9_ClusterFormation output and clusters DB table
# ─────────────────────────────────────────────────────────────────────────────

class ClusterType(str, Enum):
    PILLAR     = "pillar"      # Broad, high-volume anchor page (3000+ words)
    SUBTOPIC   = "subtopic"    # Focused, detailed, medium-volume (1500-2000 words)
    SUPPORT    = "support"     # FAQs, comparisons, tips (800-1500 words)
    CONVERSION = "conversion"  # Buying intent, commercial (landing page format)


class ClusterTypeClassifier:
    """
    Classify clusters into 4 functional types after P9 formation.
    Uses DeepSeek (local, free) — fast rule-based classification.

    Why this matters:
    - Pillar clusters → generate pillar pages (3000+ words, anchor for cluster)
    - Subtopic clusters → generate detailed blogs (1500-2000 words)
    - Support clusters → generate FAQs, comparison pages (800-1500 words)
    - Conversion clusters → generate landing/product pages (conversion-optimised)

    The type changes everything: word count, format, schema type, CTA type.

    Add to P9_ClusterFormation.run():
        classifier = ClusterTypeClassifier()
        for cluster_name, topics in clusters.items():
            cluster_type = classifier.classify(cluster_name, topics, seed_keyword)
            # Store with cluster data
    """

    # Conversion signals — these words in cluster name = conversion type
    CONVERSION_SIGNALS = [
        "buy","price","shop","order","purchase","cost","discount","deal",
        "wholesale","online","delivery","near me","where to","best brand",
        "cheap","affordable","sale","offer","store","checkout"
    ]

    # Support signals — FAQs, comparisons, tips
    SUPPORT_SIGNALS = [
        "vs","versus","compare","difference","which is better","what is",
        "how to","tips","guide","faq","frequently asked","pros and cons",
        "review","benefits","side effects","safe","dosage","storage","history"
    ]

    def classify(self, cluster_name: str, topics: List[str],
                  seed_keyword: str) -> ClusterType:
        """Classify one cluster into its functional type."""
        name_lower = cluster_name.lower()
        all_text   = name_lower + " " + " ".join(t.lower() for t in topics[:5])

        # Conversion check first (highest business value)
        if any(signal in all_text for signal in self.CONVERSION_SIGNALS):
            return ClusterType.CONVERSION

        # Support check
        if any(signal in all_text for signal in self.SUPPORT_SIGNALS):
            return ClusterType.SUPPORT

        # Pillar check: if cluster name is very close to seed keyword = pillar
        seed_words  = set(seed_keyword.lower().split())
        cluster_words = set(name_lower.split())
        overlap = len(seed_words & cluster_words) / max(len(seed_words), 1)
        if overlap >= 0.5 or len(topics) >= 10:
            return ClusterType.PILLAR

        # Default: subtopic
        return ClusterType.SUBTOPIC

    def classify_batch(self, clusters: Dict[str, List[str]],
                        seed_keyword: str) -> Dict[str, str]:
        """Return {cluster_name: cluster_type} for all clusters."""
        return {
            name: self.classify(name, topics, seed_keyword).value
            for name, topics in clusters.items()
        }

    @staticmethod
    def content_spec(cluster_type: ClusterType) -> dict:
        """
        Return recommended content specification for each cluster type.
        Used by P15_ContentBrief to set correct format.
        """
        specs = {
            ClusterType.PILLAR: {
                "word_count":   3000,
                "format":       "pillar_page",
                "schema_type":  "Article",
                "cta":          "Explore related topics",
                "internal_links": 8,
            },
            ClusterType.SUBTOPIC: {
                "word_count":   1800,
                "format":       "long_form_blog",
                "schema_type":  "Article",
                "cta":          "Read the full guide",
                "internal_links": 4,
            },
            ClusterType.SUPPORT: {
                "word_count":   1000,
                "format":       "faq_page",
                "schema_type":  "FAQPage",
                "cta":          "See all questions",
                "internal_links": 3,
            },
            ClusterType.CONVERSION: {
                "word_count":   800,
                "format":       "landing_page",
                "schema_type":  "Product",
                "cta":          "Buy now",
                "internal_links": 2,
            },
        }
        return specs.get(cluster_type, specs[ClusterType.SUBTOPIC])


# ─────────────────────────────────────────────────────────────────────────────
# 2. KEYWORD STATUS LIFECYCLE
# Add keyword_status column to keywords table
# Separate from content status (draft/frozen/published) — this is keyword-level
# ─────────────────────────────────────────────────────────────────────────────

class KeywordStatus(str, Enum):
    NOT_USED   = "not_used"   # In keyword tree, no content planned
    PLANNED    = "planned"    # In content calendar, not yet written
    IN_CONTENT = "in_content" # Article written/drafted, not published
    PUBLISHED  = "published"  # Live on site
    RANKING    = "ranking"    # In top 20 for this keyword
    OPTIMIZED  = "optimized"  # In top 5, performing well


class KeywordStatusTracker:
    """
    Track keyword-level status lifecycle.
    Different from content status — a keyword can be "not_used" even if
    articles exist that mention it (it's about deliberate targeting).

    Critical dashboard query this enables:
      "Show all keywords that are In Content but not yet ranking"
      "Show all keywords planned but not yet written"
      "Show all published keywords dropping out of ranking"

    DB change: ALTER TABLE keywords ADD COLUMN status VARCHAR(20) DEFAULT 'not_used';

    Usage:
        tracker = KeywordStatusTracker()
        # When article is scheduled:
        tracker.advance(keyword_id, KeywordStatus.PLANNED)
        # When article is written:
        tracker.advance(keyword_id, KeywordStatus.IN_CONTENT)
        # When published:
        tracker.advance(keyword_id, KeywordStatus.PUBLISHED)
        # When GSC shows rank < 20:
        tracker.advance(keyword_id, KeywordStatus.RANKING)
        # When rank reaches top 5:
        tracker.advance(keyword_id, KeywordStatus.OPTIMIZED)
    """

    # Valid status transitions — can't skip stages
    TRANSITIONS = {
        KeywordStatus.NOT_USED:   [KeywordStatus.PLANNED],
        KeywordStatus.PLANNED:    [KeywordStatus.IN_CONTENT, KeywordStatus.NOT_USED],
        KeywordStatus.IN_CONTENT: [KeywordStatus.PUBLISHED, KeywordStatus.PLANNED],
        KeywordStatus.PUBLISHED:  [KeywordStatus.RANKING, KeywordStatus.IN_CONTENT],
        KeywordStatus.RANKING:    [KeywordStatus.OPTIMIZED, KeywordStatus.PUBLISHED],
        KeywordStatus.OPTIMIZED:  [KeywordStatus.RANKING],  # can regress
    }

    def can_advance(self, current: KeywordStatus,
                     target: KeywordStatus) -> bool:
        return target in self.TRANSITIONS.get(current, [])

    def dashboard_counts(self, keywords: List[dict]) -> dict:
        """Return status counts for dashboard display."""
        counts = {s.value: 0 for s in KeywordStatus}
        for kw in keywords:
            status = kw.get("status", KeywordStatus.NOT_USED.value)
            counts[status] = counts.get(status, 0) + 1
        return {
            "not_used":   counts["not_used"],
            "planned":    counts["planned"],
            "in_content": counts["in_content"],
            "published":  counts["published"],
            "ranking":    counts["ranking"],
            "optimized":  counts["optimized"],
            "total":      len(keywords),
            "utilization_pct": round(
                (len(keywords) - counts["not_used"]) / max(len(keywords), 1) * 100, 1
            )
        }

    @staticmethod
    def sql_migration() -> str:
        """SQL to add keyword status to existing keywords table."""
        return """
-- Add keyword status lifecycle column
ALTER TABLE keywords ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'not_used';
ALTER TABLE keywords ADD COLUMN IF NOT EXISTS status_updated_at TIMESTAMP;

-- Index for dashboard queries
CREATE INDEX IF NOT EXISTS idx_keyword_status ON keywords(status);

-- Keyword status history (optional but useful)
CREATE TABLE IF NOT EXISTS keyword_status_history (
    id           SERIAL PRIMARY KEY,
    keyword_id   INTEGER REFERENCES keywords(id),
    old_status   VARCHAR(20),
    new_status   VARCHAR(20),
    changed_at   TIMESTAMP DEFAULT NOW(),
    changed_by   VARCHAR(50) DEFAULT 'system'
);
"""


# ─────────────────────────────────────────────────────────────────────────────
# 3. PROMPT VERSIONING SYSTEM
# Completely missing — all prompts currently hardcoded in Python files
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PromptVersion:
    prompt_id:       str    # e.g. "clustering_v1", "scoring_v2"
    agent:           str    # "clustering" | "scoring" | "content_mapping" | "strategy"
    version:         int    = 1
    system_prompt:   str    = ""
    user_template:   str    = ""
    status:          str    = "active"   # active | testing | deprecated
    accuracy_score:  float  = 0.0
    success_rate:    float  = 0.0
    avg_response_ms: int    = 0
    total_runs:      int    = 0
    created_at:      str    = field(default_factory=lambda: datetime.utcnow().isoformat())
    notes:           str    = ""


class PromptVersioning:
    """
    DB-backed prompt versioning with A/B testing and performance tracking.

    Why this matters:
    - When clustering produces bad results, you can roll back to v1
    - You can test v2 on 50% of jobs and compare quality scores
    - Performance data tells you which prompts work best per business type
    - Prompts become a maintained asset, not scattered Python strings

    DB table: prompt_versions (see sql_schema below)

    Usage:
        pv = PromptVersioning()
        # Get active prompt for clustering:
        prompt = pv.get_active("clustering")
        # Record outcome:
        pv.record_run("clustering_v2", success=True, response_ms=1200, quality_score=88)
        # A/B test: get prompt for this run (50/50 split):
        prompt = pv.get_ab_prompt("clustering")
    """

    def __init__(self, db_path: str = None):
        """In production, swap with SQLAlchemy session."""
        self._store: Dict[str, PromptVersion] = {}
        self._load_defaults()

    def _load_defaults(self):
        """Load the default prompts we've been using — now versioned."""
        defaults = [
            PromptVersion(
                prompt_id="clustering_v1", agent="clustering", version=1,
                system_prompt=(
                    "You are an SEO Keyword Clustering Engine. "
                    "Group keywords into meaningful clusters based on: "
                    "1. Semantic similarity 2. Search intent 3. SERP similarity. "
                    "Rules: each cluster = ONE clear topic. "
                    "Classify each as: pillar/subtopic/support/conversion. "
                    "Return ONLY valid JSON."
                ),
                user_template=(
                    "Business: {business_name}\n"
                    "Industry: {industry}\n"
                    "Seed: {seed_keyword}\n"
                    "Keywords:\n{keyword_list}\n\n"
                    "Return JSON: {{\"clusters\": [{{\"name\":...,\"type\":...,\"keywords\":[...]}}]}}"
                ),
                status="active", notes="Default clustering prompt"
            ),
            PromptVersion(
                prompt_id="scoring_v1", agent="scoring", version=1,
                system_prompt=(
                    "You are an SEO Keyword Scoring Engine. "
                    "Score each keyword 0-100 based on: search volume, competition, "
                    "business relevance, intent (transactional=highest, informational=medium). "
                    "Return ONLY valid JSON."
                ),
                user_template=(
                    "Business: {business_name}\n"
                    "Keyword data:\n{keyword_data}\n\n"
                    "Return JSON: {{\"keywords\": [{{\"keyword\":...,\"score\":0-100,\"reason\":...}}]}}"
                ),
                status="active", notes="Default scoring prompt"
            ),
            PromptVersion(
                prompt_id="content_mapping_v1", agent="content_mapping", version=1,
                system_prompt=(
                    "You are an SEO Content Strategy Engine. "
                    "Convert keyword clusters into a content plan. "
                    "Rules: 1 pillar cluster = 1 pillar page. "
                    "Strong internal linking: all supporting content links to pillar. "
                    "Match type with intent: informational=blog, transactional=landing page. "
                    "Return ONLY valid JSON."
                ),
                user_template=(
                    "Business: {business_name}\n"
                    "Clusters:\n{clusters_json}\n\n"
                    "Generate content mapping JSON with pillar_page + supporting_content array."
                ),
                status="active", notes="Default content mapping prompt"
            ),
            PromptVersion(
                prompt_id="attack_plan_v1", agent="competitor_attack", version=1,
                system_prompt=(
                    "You are an SEO competitive intelligence strategist. "
                    "Given our keyword clusters and competitor gaps, produce an attack plan. "
                    "Be aggressive but realistic. Prioritise quick wins first, then authority builders. "
                    "Return ONLY valid JSON."
                ),
                user_template=(
                    "Business: {business_name}\n"
                    "Our clusters:\n{our_clusters}\n\n"
                    "Competitor gaps (keywords they rank for, we don't):\n{competitor_gaps}\n\n"
                    "Return JSON with: quick_wins[], content_priority[], strategy_summary string."
                ),
                status="active", notes="Competitor attack plan prompt"
            ),
        ]
        for p in defaults:
            self._store[p.prompt_id] = p

    def get_active(self, agent: str) -> Optional[PromptVersion]:
        """Get the current active prompt for an agent."""
        active = [p for p in self._store.values()
                  if p.agent == agent and p.status == "active"]
        if not active:
            return None
        return sorted(active, key=lambda p: p.version, reverse=True)[0]

    def get_ab_prompt(self, agent: str, run_id: str = "") -> PromptVersion:
        """
        A/B test: return active or testing prompt based on run_id hash.
        50% of runs get active, 50% get testing (if testing version exists).
        """
        testing = [p for p in self._store.values()
                   if p.agent == agent and p.status == "testing"]
        if not testing:
            return self.get_active(agent)
        # Deterministic split based on run_id
        use_testing = int(hashlib.md5(run_id.encode()).hexdigest()[:4], 16) % 2 == 0
        return testing[0] if use_testing else self.get_active(agent)

    def record_run(self, prompt_id: str, success: bool,
                    response_ms: int, quality_score: float = 0.0):
        """Update performance stats for a prompt version."""
        if prompt_id not in self._store:
            return
        p = self._store[prompt_id]
        p.total_runs += 1
        # Running average
        n = p.total_runs
        p.avg_response_ms  = int((p.avg_response_ms * (n-1) + response_ms) / n)
        p.success_rate     = round((p.success_rate * (n-1) + (1.0 if success else 0.0)) / n, 3)
        if quality_score > 0:
            p.accuracy_score = round((p.accuracy_score * (n-1) + quality_score) / n, 2)

    def add_version(self, agent: str, system_prompt: str,
                     user_template: str, notes: str = "") -> PromptVersion:
        """Add a new testing version for an agent."""
        existing = [p for p in self._store.values() if p.agent == agent]
        new_v    = max((p.version for p in existing), default=0) + 1
        pid      = f"{agent}_v{new_v}"
        pv = PromptVersion(
            prompt_id=pid, agent=agent, version=new_v,
            system_prompt=system_prompt, user_template=user_template,
            status="testing", notes=notes
        )
        self._store[pid] = pv
        log.info(f"[PromptVersioning] New version: {pid} (status=testing)")
        return pv

    def promote(self, prompt_id: str):
        """Promote a testing prompt to active (deprecates old active)."""
        if prompt_id not in self._store:
            return
        p = self._store[prompt_id]
        # Deprecate old active
        for existing in self._store.values():
            if existing.agent == p.agent and existing.status == "active":
                existing.status = "deprecated"
        p.status = "active"
        log.info(f"[PromptVersioning] Promoted: {prompt_id} → active")

    def performance_report(self) -> List[dict]:
        """Summary of all prompt versions for admin dashboard."""
        return [
            {
                "prompt_id":     p.prompt_id,
                "agent":         p.agent,
                "version":       p.version,
                "status":        p.status,
                "success_rate":  f"{p.success_rate:.0%}",
                "accuracy":      p.accuracy_score,
                "avg_ms":        p.avg_response_ms,
                "total_runs":    p.total_runs,
            }
            for p in sorted(self._store.values(), key=lambda x: (x.agent, x.version))
        ]

    @staticmethod
    def sql_schema() -> str:
        return """
CREATE TABLE IF NOT EXISTS prompt_versions (
    id               SERIAL PRIMARY KEY,
    prompt_id        VARCHAR(100) UNIQUE NOT NULL,
    agent            VARCHAR(50) NOT NULL,
    version          INTEGER DEFAULT 1,
    system_prompt    TEXT NOT NULL,
    user_template    TEXT NOT NULL,
    status           VARCHAR(20) DEFAULT 'active',
    accuracy_score   DECIMAL(5,2) DEFAULT 0,
    success_rate     DECIMAL(5,4) DEFAULT 0,
    avg_response_ms  INTEGER DEFAULT 0,
    total_runs       INTEGER DEFAULT 0,
    notes            TEXT DEFAULT '',
    created_at       TIMESTAMP DEFAULT NOW(),
    updated_at       TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_prompt_agent_status ON prompt_versions(agent, status);
"""


# ─────────────────────────────────────────────────────────────────────────────
# 4. 4-LAYER MEMORY SYSTEM
# Brand voice already exists as Layer 1. Adding Layers 2, 3, 4.
# ─────────────────────────────────────────────────────────────────────────────

class MemoryLayer(str, Enum):
    BUSINESS     = "business"     # Layer 1: brand voice (already in BrandVoice dataclass)
    PROJECT      = "project"      # Layer 2: current run state (clusters, keywords, in-progress)
    LEARNING     = "learning"     # Layer 3: what worked (rankings, performance, success patterns)
    INTERACTION  = "interaction"  # Layer 4: user approvals/rejections/manual edits


@dataclass
class MemoryEntry:
    layer:       str
    key:         str          # descriptive key, e.g. "cluster_black_pepper_health"
    value:       Any
    project_id:  str          = ""
    relevance:   float        = 1.0   # 0-1, higher = more relevant to inject
    created_at:  str          = field(default_factory=lambda: datetime.utcnow().isoformat())
    expires_at:  str          = ""    # empty = permanent


class MemorySystem:
    """
    4-layer memory injected dynamically into prompts.
    Layer 1 (Business/Brand voice) already exists in BrandVoice dataclass.
    This adds Layers 2, 3, 4.

    Layer 2 — Project Memory:
      Stores the current universe state so Claude doesn't re-suggest
      clusters that were already approved or rejected this session.
      "We already have a cluster for Black Pepper Health Benefits —
       don't create a duplicate."

    Layer 3 — Learning Memory:
      Stores what has worked historically.
      "Articles targeting 'piperine benefits' ranked top 5 within 6 weeks.
       Recipe format articles have 3× higher CTR than list articles."
      → Feeds scoring and content type decisions.

    Layer 4 — Interaction Memory:
      Stores user manual overrides.
      "User rejected 'comparison cluster' twice → avoid suggesting it."
      "User always changes tone to 'informal' → default to informal."
      → Aligns AI with user preferences over time.

    Usage:
        memory = MemorySystem(project_id="proj_001")
        # Store a learning signal:
        memory.learn("keyword_black_pepper_ranked", {
            "keyword": "black pepper blood sugar",
            "rank_achieved": 3,
            "weeks_to_rank": 6,
            "content_type": "long_form_blog"
        })
        # Store user rejection:
        memory.record_interaction("rejected_cluster", {
            "cluster": "Comparison Clusters",
            "reason": "User rejected"
        })
        # Build memory context for prompt:
        context = memory.build_prompt_context()
    """

    def __init__(self, project_id: str = ""):
        self.project_id = project_id
        self._entries: List[MemoryEntry] = []

    # ── Layer 2: Project Memory ──────────────────────────────────────────────

    def remember_cluster(self, cluster_name: str, cluster_type: str,
                          status: str = "approved"):
        """Remember an approved/rejected cluster to avoid duplicates."""
        self._entries.append(MemoryEntry(
            layer=MemoryLayer.PROJECT,
            key=f"cluster_{hashlib.md5(cluster_name.encode()).hexdigest()[:8]}",
            value={"cluster": cluster_name, "type": cluster_type, "status": status},
            project_id=self.project_id
        ))

    def remember_keywords_in_use(self, keywords: List[str]):
        """Remember keywords already in the universe."""
        self._entries.append(MemoryEntry(
            layer=MemoryLayer.PROJECT,
            key="keywords_in_use",
            value={"count": len(keywords), "sample": keywords[:10]},
            project_id=self.project_id
        ))

    # ── Layer 3: Learning Memory ─────────────────────────────────────────────

    def learn(self, signal_type: str, data: dict):
        """
        Store a learning signal.
        signal_type examples:
          "keyword_ranked" — keyword achieved top 20
          "content_success" — article high CTR/traffic
          "cluster_pattern" — cluster type that worked well
        """
        self._entries.append(MemoryEntry(
            layer=MemoryLayer.LEARNING,
            key=f"{signal_type}_{datetime.utcnow().strftime('%Y%m%d')}",
            value=data,
            project_id=self.project_id,
            relevance=0.9
        ))

    def get_learning_signals(self, limit: int = 5) -> List[dict]:
        """Get recent learning signals sorted by relevance."""
        learning = [e for e in self._entries if e.layer == MemoryLayer.LEARNING]
        return [e.value for e in sorted(learning, key=lambda x: x.relevance, reverse=True)[:limit]]

    # ── Layer 4: Interaction Memory ──────────────────────────────────────────

    def record_interaction(self, action: str, data: dict):
        """
        Record user actions.
        action examples:
          "approved_cluster", "rejected_cluster", "edited_keyword",
          "changed_tone", "manual_content_override"
        """
        self._entries.append(MemoryEntry(
            layer=MemoryLayer.INTERACTION,
            key=f"{action}_{datetime.utcnow().timestamp():.0f}",
            value={"action": action, **data},
            project_id=self.project_id,
            relevance=0.8
        ))

    def get_user_preferences(self) -> dict:
        """Infer user preferences from interaction history."""
        interactions = [e.value for e in self._entries
                        if e.layer == MemoryLayer.INTERACTION]
        rejections  = [i for i in interactions if "rejected" in i.get("action","")]
        approvals   = [i for i in interactions if "approved" in i.get("action","")]
        return {
            "rejected_types":  list({r.get("cluster_type","") for r in rejections if r.get("cluster_type")}),
            "approval_rate":   len(approvals) / max(len(interactions), 1),
            "total_interactions": len(interactions),
        }

    # ── Prompt Context Builder ───────────────────────────────────────────────

    def build_prompt_context(self) -> str:
        """
        Build the memory context string injected into prompts.
        This is what replaces {{project_memory}}, {{learning_signals}},
        {{user_preferences}} placeholders.
        """
        sections = []

        # Project memory — what's already in the universe
        project = [e for e in self._entries if e.layer == MemoryLayer.PROJECT]
        if project:
            cluster_entries = [e for e in project if "cluster" in e.key]
            if cluster_entries:
                approved = [e.value["cluster"] for e in cluster_entries
                            if e.value.get("status") == "approved"]
                rejected = [e.value["cluster"] for e in cluster_entries
                            if e.value.get("status") == "rejected"]
                if approved:
                    sections.append(f"EXISTING CLUSTERS (do not recreate): {approved[:10]}")
                if rejected:
                    sections.append(f"REJECTED CLUSTERS (do not suggest): {rejected[:5]}")

        # Learning memory — what works
        learning = self.get_learning_signals(limit=3)
        if learning:
            signals = []
            for s in learning:
                if s.get("rank_achieved"):
                    signals.append(f"'{s.get('keyword','')}' ranked #{s['rank_achieved']} "
                                   f"in {s.get('weeks_to_rank','?')} weeks as {s.get('content_type','blog')}")
            if signals:
                sections.append(f"WHAT HAS WORKED (use as reference): {'; '.join(signals)}")

        # Interaction memory — user preferences
        prefs = self.get_user_preferences()
        if prefs["rejected_types"]:
            sections.append(f"USER PREFERENCE — avoid these cluster types: {prefs['rejected_types']}")

        return "\n".join(sections) if sections else ""

    @staticmethod
    def sql_schema() -> str:
        return """
CREATE TABLE IF NOT EXISTS ai_memory (
    id           SERIAL PRIMARY KEY,
    layer        VARCHAR(20) NOT NULL,
    key          VARCHAR(200) NOT NULL,
    value        JSONB NOT NULL,
    project_id   VARCHAR(50) DEFAULT '',
    relevance    DECIMAL(3,2) DEFAULT 1.0,
    expires_at   TIMESTAMP,
    created_at   TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_memory_layer_project ON ai_memory(layer, project_id);
CREATE INDEX IF NOT EXISTS idx_memory_key ON ai_memory(key);
"""


# ─────────────────────────────────────────────────────────────────────────────
# 5. COMPETITOR ATTACK PLAN
# One Claude call at end of M1 Business Intelligence Engine
# Synthesises gap analysis into prioritised attack sequence
# ─────────────────────────────────────────────────────────────────────────────

class CompetitorAttackPlan:
    """
    Generate a prioritised attack plan from competitor gap analysis.
    Called at end of M1 Business Intelligence Engine after gap analysis completes.

    Input: our keyword clusters + competitor gaps
    Output: quick_wins, content_priority, strategy_summary

    Uses the versioned prompt "attack_plan_v1" from PromptVersioning.

    Integration:
        # At end of M1 Business Intelligence Engine run:
        plan = CompetitorAttackPlan()
        attack = plan.generate(
            business_name="Pureleven Organics",
            our_clusters=confirmed_clusters,
            competitor_gaps=gap_analysis_results
        )
        job.log("AttackPlan", "claude", f"Strategy: {attack['strategy_summary']}")
        # Feed into Gate 4 (blog suggestions) as priority ordering input
    """

    SYSTEM_PROMPT = """You are an SEO competitive intelligence strategist for a product business.
Given keyword clusters and competitor gaps, produce an actionable attack plan.

Rules:
- Quick wins = high commercial intent + low competition + competitor weakness
- Prioritise transactional keywords first (direct revenue impact)
- Then informational content that builds topical authority
- Be specific — name exact keywords and content types, not generic advice
- Maximum 10 quick wins, 5 content priorities

Return ONLY valid JSON."""

    USER_TEMPLATE = """Business: {business_name}
Industry: {industry}

Our confirmed keyword clusters:
{our_clusters}

Competitor gaps (keywords they rank for but we don't target):
{competitor_gaps}

Competitor weaknesses identified:
{competitor_weaknesses}

Generate attack plan JSON:
{{
  "quick_wins": [
    {{"keyword": "...", "why": "...", "content_type": "blog|landing|comparison"}}
  ],
  "content_priority": [
    {{"theme": "...", "rationale": "..."}}
  ],
  "strategy_summary": "one sentence core strategy",
  "dominate_first": "which intent/cluster to own first and why"
}}"""

    def generate(self, business_name: str, industry: str,
                  our_clusters: List[str], competitor_gaps: List[dict],
                  competitor_weaknesses: List[str] = None) -> dict:
        """Generate attack plan. Returns parsed dict or error fallback."""
        import requests as _req, re, json as _json

        anthropic_key = os.getenv("ANTHROPIC_API_KEY","")
        if not anthropic_key:
            return self._fallback_plan(our_clusters, competitor_gaps)

        prompt = self.USER_TEMPLATE.format(
            business_name=business_name,
            industry=industry,
            our_clusters="\n".join(f"- {c}" for c in our_clusters[:15]),
            competitor_gaps="\n".join(
                f"- {g.get('keyword','')} (they rank #{g.get('rank','?')})"
                for g in competitor_gaps[:20]
            ),
            competitor_weaknesses="\n".join(
                f"- {w}" for w in (competitor_weaknesses or ["None identified"])[:5]
            )
        )

        try:
            import anthropic
            client = anthropic.Anthropic(api_key=anthropic_key)
            r = client.messages.create(
                model=os.getenv("CLAUDE_MODEL","claude-sonnet-4-6"),
                max_tokens=1500,
                system=self.SYSTEM_PROMPT,
                messages=[{"role":"user","content":prompt}]
            )
            text = r.content[0].text.strip()
            # Parse JSON
            text = re.sub(r"```(?:json)?","",text).strip().rstrip("`").strip()
            m = re.search(r'\{.*\}', text, re.DOTALL)
            if m:
                return _json.loads(m.group(0))
        except Exception as e:
            log.warning(f"[AttackPlan] Claude call failed: {e}")

        return self._fallback_plan(our_clusters, competitor_gaps)

    def _fallback_plan(self, clusters: List[str],
                        gaps: List[dict]) -> dict:
        """Rule-based fallback when Claude is unavailable."""
        # Find transactional gaps (highest commercial value)
        transactional = [g for g in gaps
                         if any(w in g.get("keyword","").lower()
                                for w in ["buy","price","online","order","shop"])]
        informational = [g for g in gaps if g not in transactional]

        return {
            "quick_wins": [
                {"keyword": g["keyword"], "why": "competitor gap + commercial intent",
                 "content_type": "landing"}
                for g in transactional[:5]
            ],
            "content_priority": [
                {"theme": c, "rationale": "build topical authority"}
                for c in clusters[:5]
            ],
            "strategy_summary": (
                f"Target {len(transactional)} transactional gaps immediately, "
                f"then build authority across {len(clusters)} topic clusters."
            ),
            "dominate_first": "Transactional keywords — direct revenue impact"
        }


# ─────────────────────────────────────────────────────────────────────────────
# TESTS
# ─────────────────────────────────────────────────────────────────────────────

class Tests:

    def _h(self, n): print(f"\n{'─'*55}\n  TEST: {n}\n{'─'*55}")
    def _ok(self, m): print(f"  ✓ {m}")

    def test_cluster_types(self):
        self._h("ClusterTypeClassifier — 4 types")
        c = ClusterTypeClassifier()
        cases = [
            ("Black Pepper Health Benefits", ["piperine benefits","blood sugar"], "black pepper"),
            ("Buy Black Pepper Online",      ["buy pepper","price","order"],      "black pepper"),
            ("Ceylon vs Cassia Cinnamon",    ["vs","comparison","which better"],  "cinnamon"),
            ("Cinnamon Tea Recipe",          ["recipe","how to make","cinnamon tea"],"cinnamon"),
        ]
        for name, topics, seed in cases:
            ctype = c.classify(name, topics, seed)
            spec  = ClusterTypeClassifier.content_spec(ctype)
            self._ok(f"{name[:35]:35} → {ctype.value:12} ({spec['word_count']} words, {spec['format']})")

    def test_keyword_status(self):
        self._h("KeywordStatusLifecycle")
        tracker = KeywordStatusTracker()
        keywords = [
            {"keyword": "black pepper health", "status": "ranking"},
            {"keyword": "buy black pepper",    "status": "published"},
            {"keyword": "piperine benefits",   "status": "in_content"},
            {"keyword": "cinnamon tea",        "status": "planned"},
            {"keyword": "turmeric origin",     "status": "not_used"},
        ]
        counts = tracker.dashboard_counts(keywords)
        self._ok(f"Dashboard: {counts}")
        self._ok(f"Utilization: {counts['utilization_pct']}%")
        valid = tracker.can_advance(KeywordStatus.PLANNED, KeywordStatus.IN_CONTENT)
        self._ok(f"Can advance PLANNED→IN_CONTENT: {valid}")

    def test_prompt_versioning(self):
        self._h("PromptVersioning — A/B + performance tracking")
        pv = PromptVersioning()
        # Get active prompt
        p = pv.get_active("clustering")
        self._ok(f"Active clustering prompt: {p.prompt_id} v{p.version}")
        # Record some runs
        pv.record_run(p.prompt_id, success=True, response_ms=1200, quality_score=82)
        pv.record_run(p.prompt_id, success=True, response_ms=980,  quality_score=88)
        pv.record_run(p.prompt_id, success=False,response_ms=4000, quality_score=0)
        # Report
        report = pv.performance_report()
        for r in report[:2]:
            self._ok(f"{r['prompt_id']:25} success={r['success_rate']} avg={r['avg_ms']}ms")
        # Add new version
        new_p = pv.add_version("clustering",
                                "Improved clustering system prompt v2...",
                                "Improved user template v2...",
                                notes="Testing semantic intent grouping improvement")
        self._ok(f"New version added: {new_p.prompt_id} (status={new_p.status})")

    def test_memory(self):
        self._h("MemorySystem — 4 layers")
        mem = MemorySystem(project_id="proj_spices_001")
        # Layer 2: project
        mem.remember_cluster("Black Pepper Health", "pillar", "approved")
        mem.remember_cluster("Comparison Clusters", "support", "rejected")
        # Layer 3: learning
        mem.learn("keyword_ranked", {
            "keyword": "black pepper blood sugar",
            "rank_achieved": 3, "weeks_to_rank": 6,
            "content_type": "long_form_blog"
        })
        # Layer 4: interaction
        mem.record_interaction("rejected_cluster", {"cluster": "Comparison Clusters", "cluster_type": "support"})
        # Build context
        context = mem.build_prompt_context()
        self._ok("Memory context built:")
        for line in context.split("\n"):
            self._ok(f"  {line[:70]}")
        prefs = mem.get_user_preferences()
        self._ok(f"Inferred preferences: {prefs}")

    def test_attack_plan_fallback(self):
        self._h("CompetitorAttackPlan — fallback (no Claude key needed)")
        plan = CompetitorAttackPlan()
        clusters = ["Black Pepper Health", "Cinnamon Recipes", "Buy Spices Online"]
        gaps = [
            {"keyword": "buy organic black pepper India", "rank": 4},
            {"keyword": "cinnamon diabetes PubMed",       "rank": 7},
            {"keyword": "black pepper price per kg",      "rank": 3},
        ]
        result = plan._fallback_plan(clusters, gaps)
        self._ok(f"Quick wins: {len(result['quick_wins'])}")
        self._ok(f"Strategy:   {result['strategy_summary']}")
        self._ok(f"Dominate:   {result['dominate_first']}")

    def run_all(self):
        print("\n"+"═"*55+"\n  ANNASEO DOC2 ADDONS — TESTS\n"+"═"*55)
        tests = [
            ("cluster_types",       self.test_cluster_types),
            ("keyword_status",      self.test_keyword_status),
            ("prompt_versioning",   self.test_prompt_versioning),
            ("memory",              self.test_memory),
            ("attack_plan",         self.test_attack_plan_fallback),
        ]
        p=f=0
        for name,fn in tests:
            try: fn(); p+=1
            except Exception as e: print(f"  ✗ {name}: {e}"); f+=1
        print(f"\n  {p} passed / {f} failed\n"+"═"*55)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        if len(sys.argv) > 2:
            fn = getattr(Tests(), f"test_{sys.argv[2]}", None)
            if fn: fn()
            else: print(f"Unknown: {sys.argv[2]}")
        else:
            Tests().run_all()
    else:
        print("Usage: python annaseo_doc2_addons.py test [cluster_types|keyword_status|prompt_versioning|memory|attack_plan]")
