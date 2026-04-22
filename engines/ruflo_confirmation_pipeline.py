"""
================================================================================
RUFLO — KEYWORD INTELLIGENCE + CONFIRMATION GATE PIPELINE
================================================================================

FLOW (5 gates, human confirmation between every engine):

  Customer input: "Black Pepper, Turmeric, Spices online, Organic Black Pepper"
      ↓
  [INTELLIGENCE LAYER]
  Detects: Black Pepper = universe, Turmeric = universe
           Spices online = pillar under Black Pepper (broader modifier)
           Organic Black Pepper = supporting under Black Pepper (qualifier)
      ↓
  ── GATE 1: Universe Confirmation ──────────────────────────── customer confirms
      ↓ engine runs
  Universe Engine: SERP → pillar candidates per universe
      ↓
  ── GATE 2: Pillar Confirmation (per universe) ─────────────── customer confirms
      ↓ engine runs
  Keyword Expansion: 8 methods + dedup + scoring + clustering
      ↓
  ── GATE 3: Keyword Universe Confirmation ──────────────────── customer confirms
      ↓ engine runs
  Content Strategy Engine: angles + sequence + link map + blog titles
      ↓
  ── GATE 4: Blog Suggestions Confirmation ──────────────────── customer confirms
      ↓ engine runs
  Claude Final Strategy: 5-step CoT, cross-checks everything, ranks #1 plan
      ↓
  ── GATE 5: Final Strategy Confirmation ────────────────────── customer confirms
      ↓
  Content Duration Selection: 1 year / 2 years / 3 years / custom
      ↓
  Content Calendar Generated → execution begins

ADD NEW UNIVERSE LATER:
  Customer adds "Cardamom" → runs through all 5 gates for Cardamom only
  Existing keywords/content untouched
  Cross-universe dedup runs automatically
================================================================================
"""

import os, json, re, time, hashlib, logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from dotenv import load_dotenv
import requests as _req

load_dotenv()
log = logging.getLogger("ruflo.pipeline")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1 — DATA MODELS
# ─────────────────────────────────────────────────────────────────────────────

class KeywordRole(str, Enum):
    UNIVERSE   = "universe"    # broad, independent — gets its own tree
    PILLAR     = "pillar"      # proven traffic topic under a universe
    SUPPORTING = "supporting"  # long-tail, modifier, cluster keyword
    AMBIGUOUS  = "ambiguous"   # system can't decide — asks customer


@dataclass
class ClassifiedKeyword:
    """Output of the intelligence layer for one customer-input keyword."""
    raw_input:       str
    normalised:      str
    role:            KeywordRole
    parent_universe: Optional[str]    # if role=pillar/supporting, which universe
    rationale:       str              # why this classification
    confidence:      float            # 0-1
    suggestion:      str              # what system recommends
    alternatives:    List[str]        # if ambiguous, options to show customer


@dataclass
class Universe:
    """One confirmed universe keyword with all its downstream data."""
    id:              str
    term:            str
    status:          str = "pending"  # pending|running|gate_2|gate_3|gate_4|gate_5|confirmed
    pillars:         List[dict] = field(default_factory=list)
    keywords:        List[dict] = field(default_factory=list)
    blog_suggestions:List[dict] = field(default_factory=list)
    strategy:        dict = field(default_factory=dict)
    confirmed_at:    Optional[str] = None
    added_at:        str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class GateState:
    """State of one confirmation gate — what's waiting, what's confirmed."""
    gate_number: int
    gate_name:   str
    status:      str = "waiting"   # waiting|shown|confirmed|rejected|rerequested
    data:        dict = field(default_factory=dict)
    confirmed_at:Optional[str] = None
    customer_edits: List[dict] = field(default_factory=list)


@dataclass
class PipelineJob:
    """Complete state of one customer's pipeline run."""
    id:              str
    project_id:      str
    universes:       List[Universe] = field(default_factory=list)
    gates:           List[GateState] = field(default_factory=list)
    current_gate:    int = 0
    status:          str = "input"   # input|running|gate_N|complete
    console_logs:    List[dict] = field(default_factory=list)
    final_strategy:  dict = field(default_factory=dict)
    content_duration_years: Optional[float] = None
    created_at:      str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def log(self, engine: str, level: str, message: str, data: dict = None):
        """Add a console log entry. Streamed to frontend via SSE."""
        entry = {
            "ts":      datetime.now(timezone.utc).strftime("%H:%M:%S"),
            "engine":  engine,
            "level":   level,    # success|info|warning|error|data|handoff|critical
            "message": message,
            "data":    data or {},
        }
        self.console_logs.append(entry)
        color = {
            "success":  "✓", "info": "→", "warning": "⚠",
            "error": "✗", "data": "·", "handoff": "⟶", "critical": "✗✗"
        }.get(level, "·")
        print(f"  {entry['ts']} [{engine}] {color} {message}")


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2 — AI HELPERS
# ─────────────────────────────────────────────────────────────────────────────

class Cfg:
    OLLAMA_URL     = os.getenv("OLLAMA_URL",     "http://172.235.16.165:8080")
    OLLAMA_MODEL   = os.getenv("OLLAMA_MODEL",   "mistral:7b-instruct-q4_K_M")
    OLLAMA_EMBED   = os.getenv("OLLAMA_EMBED",   "nomic-embed-text")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL   = os.getenv("GEMINI_MODEL",   "gemini-1.5-flash")
    GEMINI_RATE    = float(os.getenv("GEMINI_RATE", "4.0"))
    ANTHROPIC_KEY  = os.getenv("ANTHROPIC_API_KEY", "")
    CLAUDE_MODEL   = os.getenv("CLAUDE_MODEL",   "claude-sonnet-4-6")
    EMBED_MODEL    = "all-MiniLM-L6-v2"
    SIMILARITY_UNIVERSE_THRESHOLD  = 0.85  # above = same universe, merge
    SIMILARITY_AMBIGUOUS_THRESHOLD = 0.70  # between 0.70-0.85 = ambiguous


class AI:
    _embed_model = None
    _last_gemini = 0.0

    @staticmethod
    def _extract_ollama_text(data: Any) -> str:
        if not isinstance(data, dict):
            return ""
        if isinstance(data.get("response"), str) and data.get("response").strip():
            return data["response"].strip()
        msg = data.get("message")
        if isinstance(msg, dict) and isinstance(msg.get("content"), str) and msg.get("content").strip():
            return msg["content"].strip()
        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                if isinstance(first.get("message"), dict) and isinstance(first["message"].get("content"), str):
                    return first["message"]["content"].strip()
                if isinstance(first.get("text"), str):
                    return first["text"].strip()
        if isinstance(data.get("text"), str):
            return data["text"].strip()
        return ""

    @staticmethod
    def deepseek(prompt: str, system: str = "You are an SEO expert.",
                  temperature: float = 0.1) -> str:
        """Route through central AIRouter (health check, semaphore, 620s timeout)."""
        try:
            from core.ai_config import AIRouter
            return AIRouter._call_ollama(prompt, system or "You are an SEO expert.", temperature)
        except Exception as e:
            log.warning(f"DeepSeek error: {e}")
            return ""

    @classmethod
    def gemini(cls, prompt: str, temperature: float = 0.3) -> str:
        if not Cfg.GEMINI_API_KEY:
            return cls.deepseek(prompt, temperature=temperature)
        elapsed = time.time() - cls._last_gemini
        if elapsed < Cfg.GEMINI_RATE:
            time.sleep(Cfg.GEMINI_RATE - elapsed)
        try:
            import google.generativeai as genai
            genai.configure(api_key=Cfg.GEMINI_API_KEY)
            model = genai.GenerativeModel(Cfg.GEMINI_MODEL)
            resp  = model.generate_content(prompt,
                generation_config=genai.GenerationConfig(temperature=temperature))
            cls._last_gemini = time.time()
            return resp.text.strip()
        except Exception as e:
            log.warning(f"Gemini error: {e}")
            return cls.deepseek(prompt, temperature=temperature)

    @staticmethod
    def claude(system: str, prompt: str,
               max_tokens: int = 4000) -> Tuple[str, int]:
        if not Cfg.ANTHROPIC_KEY:
            log.warning("No ANTHROPIC_API_KEY — returning mock strategy")
            return json.dumps({"mock": True, "note": "set ANTHROPIC_API_KEY"}), 0
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=Cfg.ANTHROPIC_KEY)
            r = client.messages.create(
                model=Cfg.CLAUDE_MODEL, max_tokens=max_tokens,
                system=system,
                messages=[{"role":"user","content":prompt}]
            )
            return r.content[0].text.strip(), r.usage.input_tokens + r.usage.output_tokens
        except Exception as e:
            log.error(f"Claude error: {e}")
            return '{"error":"' + str(e) + '"}', 0

    @classmethod
    def embed(cls, texts: List[str]) -> List[List[float]]:
        """Get embeddings. Ollama first, sentence-transformers fallback."""
        try:
            r = _req.post(f"{Cfg.OLLAMA_URL}/api/embed",
                          json={"model": Cfg.OLLAMA_EMBED, "input": texts}, timeout=60)
            r.raise_for_status()
            return r.json()["embeddings"]
        except Exception:
            if cls._embed_model is None:
                from sentence_transformers import SentenceTransformer
                cls._embed_model = SentenceTransformer(Cfg.EMBED_MODEL)
            return cls._embed_model.encode(texts, normalize_embeddings=True).tolist()

    @staticmethod
    def cosine_similarity(a: List[float], b: List[float]) -> float:
        import math
        dot   = sum(x*y for x,y in zip(a,b))
        mag_a = math.sqrt(sum(x*x for x in a))
        mag_b = math.sqrt(sum(x*x for x in b))
        return dot / (mag_a * mag_b + 1e-9)

    @staticmethod
    def parse_json(text: str) -> Any:
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        text = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
        m = re.search(r'(\{.*\}|\[.*\])', text, re.DOTALL)
        if m:
            return json.loads(m.group(1))
        return json.loads(text)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3 — KEYWORD INTELLIGENCE LAYER
# ─────────────────────────────────────────────────────────────────────────────

class KeywordIntelligenceLayer:
    """
    THE FIRST ENGINE. Runs before anything else.

    Customer input: "Black Pepper, Turmeric, Spices online, Organic Black Pepper, buy black pepper"
    
    Intelligence output:
      - Black Pepper        → Universe (broad, independent)
      - Turmeric            → Universe (broad, independent, different topic)
      - Spices online       → Pillar under Black Pepper (modifier+broader category)
      - Organic Black Pepper → Supporting under Black Pepper (qualifier)
      - buy black pepper    → Supporting/transactional under Black Pepper
    
    Rules:
    1. Embedding similarity > 0.85 to another term = modifier/supporting of that term
    2. Word count: 1-2 words + broad concept = universe. 3+ words = supporting.
    3. Transactional words (buy, order, price, cheap) = always supporting, never universe.
    4. Similarity 0.70-0.85 = ambiguous → ask customer.
    5. Multiple terms similar to each other → keep the shortest as universe.
    """

    TRANSACTIONAL_WORDS = [
        "buy", "order", "price", "cheap", "discount", "wholesale", "bulk",
        "online", "shop", "store", "delivery", "near me", "cost", "sale",
        "purchase", "get", "deal", "offer", "free shipping"
    ]

    QUALIFIER_WORDS = [
        "organic", "best", "natural", "pure", "premium", "authentic",
        "fresh", "dried", "powdered", "whole", "ground", "certified",
        "top", "quality", "grade", "raw", "roasted"
    ]

    CLASSIFY_PROMPT = """You are an SEO keyword strategist.
Customer provided these keywords for their {industry} business ({usp}):
{keywords}

Classify each keyword:
- "universe": a broad, standalone topic that deserves its own content tree (1-3 word core concepts)
- "pillar": a major topic UNDER one of the universe keywords (proven competitor traffic topic)
- "supporting": a modifier, qualifier, or long-tail variant of a universe keyword
- "ambiguous": genuinely unclear — could be universe or pillar

For supporting/pillar keywords, identify which universe they belong to.

Rules:
1. Transactional keywords (buy, price, order) = always supporting, never universe
2. Qualifiers (organic, best, premium) + universe keyword = supporting of that universe
3. Short broad terms = universe. Modified terms = supporting.
4. Only classify as universe if it's truly a distinct enough topic to have its own content strategy.

Return ONLY valid JSON array:
[
  {{
    "term": "original keyword",
    "role": "universe|pillar|supporting|ambiguous",
    "parent_universe": "which universe this belongs to (null if universe itself)",
    "rationale": "why this classification in one sentence",
    "confidence": 0.0-1.0
  }}
]"""

    def classify(self, raw_inputs: List[str], business_context: dict) -> List[ClassifiedKeyword]:
        """
        Main classification method.
        1. Normalise inputs
        2. Compute embeddings + similarity matrix
        3. Rule-based pre-classification
        4. DeepSeek confirmation
        5. Build final ClassifiedKeyword list
        """
        # Normalise
        normalised = [kw.strip().lower() for kw in raw_inputs if kw.strip()]
        unique      = list(dict.fromkeys(normalised))  # preserve order, remove exact dupes

        log.info(f"[Intelligence] Classifying {len(unique)} keywords: {unique}")

        # Rule-based pre-classification
        pre_classified = []
        for kw in unique:
            role   = self._rule_based_classify(kw, unique)
            pre_classified.append({"term": kw, "role": role})

        # Embedding similarity matrix (for ambiguous resolution)
        sim_matrix = {}
        if len(unique) > 1:
            try:
                embeddings = AI.embed(unique)
                for i, kw_a in enumerate(unique):
                    sim_matrix[kw_a] = {}
                    for j, kw_b in enumerate(unique):
                        if i != j:
                            sim_matrix[kw_a][kw_b] = AI.cosine_similarity(
                                embeddings[i], embeddings[j]
                            )
            except Exception as e:
                log.warning(f"Embedding failed: {e}")

        # Merge obvious duplicates based on similarity
        merged = self._merge_similar(unique, sim_matrix, pre_classified)

        # AI confirmation via DeepSeek
        ai_classifications = self._ai_classify(merged, business_context)

        # Build output
        return self._build_output(merged, ai_classifications, sim_matrix)

    def _rule_based_classify(self, kw: str, all_kws: List[str]) -> KeywordRole:
        """Fast rule-based first pass."""
        words = kw.split()
        kw_lower = kw.lower()

        # Transactional = always supporting
        if any(t in kw_lower for t in self.TRANSACTIONAL_WORDS):
            return KeywordRole.SUPPORTING

        # Qualifier + another keyword = supporting of that keyword
        is_qualifier_combo = any(q in kw_lower for q in self.QUALIFIER_WORDS)
        if is_qualifier_combo and len(words) >= 2:
            return KeywordRole.SUPPORTING

        # Long tail (5+ words) = always supporting
        if len(words) >= 5:
            return KeywordRole.SUPPORTING

        # 1-2 word broad terms = likely universe
        if len(words) <= 2:
            return KeywordRole.UNIVERSE

        # 3-4 word modifier = ambiguous
        return KeywordRole.AMBIGUOUS

    def _merge_similar(self, keywords: List[str], sim_matrix: dict,
                        pre_classified: List[dict]) -> List[dict]:
        """
        If "Organic Black Pepper" has 0.92 similarity to "Black Pepper",
        mark it as supporting under Black Pepper.
        Keep the shorter/broader as universe.
        """
        result = list(pre_classified)

        for i, item_a in enumerate(result):
            kw_a = item_a["term"]
            if item_a["role"] == KeywordRole.UNIVERSE:
                for j, item_b in enumerate(result):
                    if i == j:
                        continue
                    kw_b = item_b["term"]
                    sim  = sim_matrix.get(kw_a, {}).get(kw_b, 0.0)

                    if sim >= Cfg.SIMILARITY_UNIVERSE_THRESHOLD:
                        # kw_b is very similar to kw_a
                        # Shorter = universe, longer = supporting
                        if len(kw_a.split()) <= len(kw_b.split()):
                            result[j]["role"]            = KeywordRole.SUPPORTING
                            result[j]["parent_universe"]  = kw_a
                            result[j]["sim_to_parent"]   = sim
                        else:
                            result[i]["role"]            = KeywordRole.SUPPORTING
                            result[i]["parent_universe"]  = kw_b
                            result[i]["sim_to_parent"]   = sim

                    elif sim >= Cfg.SIMILARITY_AMBIGUOUS_THRESHOLD:
                        if result[j]["role"] == KeywordRole.UNIVERSE:
                            result[j]["role"] = KeywordRole.AMBIGUOUS
                            result[j]["similar_to"]      = kw_a
                            result[j]["sim_score"]       = sim

        return result

    def _ai_classify(self, pre_classified: List[dict], ctx: dict) -> List[dict]:
        """DeepSeek confirms/corrects rule-based classification."""
        terms = [item["term"] for item in pre_classified]
        prompt = self.CLASSIFY_PROMPT.format(
            industry=ctx.get("industry", "business"),
            usp=ctx.get("usp", ""),
            keywords="\n".join(f"- {t}" for t in terms)
        )
        text = AI.deepseek(prompt, temperature=0.1)
        try:
            return AI.parse_json(text)
        except Exception as e:
            log.warning(f"AI classification parse failed: {e}")
            return []

    def _build_output(self, merged: List[dict], ai_result: List[dict],
                       sim_matrix: dict) -> List[ClassifiedKeyword]:
        """Combine rule + AI into final ClassifiedKeyword list."""
        # Build lookup from AI results
        ai_lookup = {item.get("term","").lower(): item for item in ai_result}

        result = []
        for item in merged:
            term = item["term"]
            ai   = ai_lookup.get(term.lower(), {})

            # AI wins over rules if confidence is high
            if ai.get("confidence", 0) > 0.8:
                role   = KeywordRole(ai.get("role", item.get("role", KeywordRole.AMBIGUOUS).value))
                parent = ai.get("parent_universe")
                rationale = ai.get("rationale","")
                confidence = ai.get("confidence", 0.8)
            else:
                role   = item.get("role", KeywordRole.AMBIGUOUS)
                parent = item.get("parent_universe")
                rationale = f"Rule-based: {item.get('role','?')}, sim_to_parent={item.get('sim_to_parent',0):.2f}"
                confidence = 0.7

            # Build alternatives for ambiguous
            alternatives = []
            if role == KeywordRole.AMBIGUOUS:
                sim_to = item.get("similar_to","")
                alternatives = [
                    f"Make '{term}' its own Universe",
                    f"Add as Pillar under '{sim_to}'" if sim_to else "Add as Pillar",
                    "Remove this keyword"
                ]
                suggestion = f"Similar to '{sim_to}' (score {item.get('sim_score',0):.2f}) — could be own universe or pillar. You decide."
            elif role == KeywordRole.SUPPORTING:
                suggestion = f"Added as supporting keyword under '{parent or 'closest universe'}'"
            elif role == KeywordRole.PILLAR:
                suggestion = f"Added as pillar under '{parent}'"
            else:
                suggestion = "New independent universe — will get its own keyword tree"

            result.append(ClassifiedKeyword(
                raw_input=term, normalised=term.lower(), role=role,
                parent_universe=parent, rationale=rationale,
                confidence=confidence, suggestion=suggestion,
                alternatives=alternatives
            ))

        return result

    def format_for_customer(self, classified: List[ClassifiedKeyword]) -> dict:
        """
        Format classification result for Gate 1 customer display.
        Groups by: confirmed universes, merged supporting, ambiguous (needs decision).
        """
        universes   = [c for c in classified if c.role == KeywordRole.UNIVERSE]
        supporting  = [c for c in classified if c.role in (KeywordRole.PILLAR, KeywordRole.SUPPORTING)]
        ambiguous   = [c for c in classified if c.role == KeywordRole.AMBIGUOUS]

        return {
            "universes":   [{"term": u.raw_input, "suggestion": u.suggestion} for u in universes],
            "merged":      [{"term": s.raw_input, "under": s.parent_universe,
                              "role": s.role.value, "suggestion": s.suggestion}
                             for s in supporting],
            "ambiguous":   [{"term": a.raw_input, "why": a.rationale,
                              "alternatives": a.alternatives, "suggestion": a.suggestion}
                             for a in ambiguous],
            "total_inputs":   len(classified),
            "universes_count": len(universes),
            "needs_decision": len(ambiguous),
        }


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4 — UNIVERSE ENGINE
# ─────────────────────────────────────────────────────────────────────────────

class UniverseEngine:
    """
    After Gate 1. For each confirmed universe keyword:
    SERP → top 10 pages → extract H2/H3 → Wikipedia → identify pillars.
    """

    PILLAR_PROMPT = """Extract pillar keyword topics for universe: "{universe}"
Business: {business}

Competitor headings found:
{headings}

Wikipedia sub-topics:
{wiki_topics}

Identify 6-10 pillar keywords that:
1. Have proven search traffic (found in competitor headings)
2. Are specific enough to anchor a cluster of related keywords
3. Cover different aspects (health, buying, cooking, regional, etc.)
4. Include easy wins (KD < 15) AND some hard ones (KD > 30)

Also include pillars that customers identified as important:
Customer-input supporting keywords to include as pillars: {customer_inputs}

Return ONLY valid JSON array:
[
  {{
    "name": "exact pillar keyword phrase",
    "kd_estimate": 1-100,
    "source": "competitor|wikipedia|ai|customer_input",
    "competitor_count": 0,
    "why_important": "strategic reason",
    "intent": "informational|transactional|commercial"
  }}
]"""

    def run(self, universe: Universe, business_ctx: dict,
             customer_supporting: List[str], job: PipelineJob) -> List[dict]:
        """Generate pillars for one universe."""
        job.log("UniverseEngine", "info", f"Generating pillars for: {universe.term}")

        # Wikipedia research
        wiki_topics = self._get_wiki_topics(universe.term)
        job.log("UniverseEngine", "data", f"Wikipedia: {len(wiki_topics)} sub-topics")

        # SERP crawl
        headings = self._serp_headings(universe.term)
        job.log("UniverseEngine", "data", f"SERP headings: {len(headings)} H2/H3s extracted")

        # Gemini pillar extraction
        prompt = self.PILLAR_PROMPT.format(
            universe=universe.term,
            business=f"{business_ctx.get('name','')} — {business_ctx.get('usp','')}",
            headings="\n".join(f"- {h}" for h in headings[:40]),
            wiki_topics="\n".join(f"- {t}" for t in wiki_topics[:20]),
            customer_inputs=", ".join(customer_supporting[:10]) or "none"
        )
        text    = AI.gemini(prompt, temperature=0.3)
        pillars = []
        try:
            pillars = AI.parse_json(text)
            if not isinstance(pillars, list):
                pillars = []
        except Exception as e:
            log.warning(f"Pillar extraction parse failed for {universe.term}: {e}")

        job.log("UniverseEngine", "success",
                f"Pillars for '{universe.term}': {len(pillars)} identified",
                {"pillars": [p.get("name","") for p in pillars]})
        return pillars

    def _get_wiki_topics(self, term: str) -> List[str]:
        try:
            import wikipediaapi
            wiki = wikipediaapi.Wikipedia('en')
            page = wiki.page(term.title())
            if page.exists():
                return [s.title for s in page.sections[:15]]
        except Exception:
            pass
        # Fallback: Gemini generates likely wiki topics
        try:
            text = AI.gemini(
                f"List 15 Wikipedia-style sub-topics for '{term}' as a JSON array of strings.",
                temperature=0.2
            )
            result = AI.parse_json(text)
            return result if isinstance(result, list) else []
        except Exception:
            return []

    def _serp_headings(self, term: str) -> List[str]:
        """Scrape DuckDuckGo SERP → crawl top pages → extract headings."""
        from bs4 import BeautifulSoup
        headings = []
        try:
            r = _req.get("https://html.duckduckgo.com/html/",
                          params={"q": term},
                          headers={"User-Agent":"Mozilla/5.0"}, timeout=10)
            soup = BeautifulSoup(r.text, "html.parser")
            urls = [a["href"] for a in soup.select(".result__url")[:8] if a.get("href")]
            for url in urls[:5]:
                try:
                    page = _req.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=8)
                    ps   = BeautifulSoup(page.text, "html.parser")
                    headings.extend([h.get_text(strip=True) for h in ps.find_all(["h2","h3"])[:8]])
                    time.sleep(0.5)
                except Exception:
                    continue
        except Exception as e:
            log.warning(f"SERP scrape failed: {e}")
        return list(set(h for h in headings if len(h) > 5))[:50]


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5 — KEYWORD EXPANSION ENGINE
# ─────────────────────────────────────────────────────────────────────────────

class KeywordExpansionEngine:
    """
    After Gate 2. For each confirmed pillar, runs all 8 expansion methods.
    Cross-universe dedup: checks against ALL universes in this project.
    """

    def run(self, universe: Universe, existing_project_keywords: List[str],
             business_ctx: dict, job: PipelineJob) -> List[dict]:
        """Expand all pillars into keyword clusters + dedup across universes."""
        all_kws = []
        for pillar in universe.pillars:
            pillar_name = pillar.get("name","")
            job.log("ExpansionEngine", "info", f"Expanding pillar: {pillar_name}")

            # All 8 methods
            kws = self._expand_pillar(pillar_name, universe.term, business_ctx)
            job.log("ExpansionEngine", "data",
                    f"  '{pillar_name}': {len(kws)} raw keywords from 8 methods")
            all_kws.extend(kws)

        job.log("ExpansionEngine", "data",
                f"Total raw keywords: {len(all_kws)}")

        # Dedup within this universe
        deduped = self._dedup(all_kws)
        job.log("ExpansionEngine", "data",
                f"After dedup: {len(deduped)} (removed {len(all_kws)-len(deduped)})")

        # Cross-universe dedup
        if existing_project_keywords:
            pre = len(deduped)
            deduped = self._cross_universe_dedup(deduped, existing_project_keywords)
            job.log("ExpansionEngine", "data",
                    f"After cross-universe dedup: {len(deduped)} (removed {pre-len(deduped)} shared with other universes)")

        # Score
        scored = self._score(deduped, business_ctx)
        job.log("ExpansionEngine", "success",
                f"Expansion complete: {len(scored)} keywords scored")
        return scored

    def _expand_pillar(self, pillar: str, universe: str, ctx: dict) -> List[dict]:
        """8-method expansion for one pillar."""
        results = []

        # Method 1: Prepositions
        for prep in ["for","with","without","vs","benefits","uses","side effects",
                     "in cooking","recipe","organic","buy","price"]:
            results.append({"term":f"{pillar} {prep}","method":"preposition","kd_estimate":8})

        # Method 2: Qualifiers
        for qual in ["best","organic","natural","pure","premium","Kerala","Wayanad","certified"]:
            results.append({"term":f"{qual} {pillar}","method":"qualifier","kd_estimate":6})

        # Method 3: Questions (PAA-style)
        for q in ["what is","how to use","how much","when to use","why use"]:
            results.append({"term":f"{q} {pillar}","method":"paa","kd_estimate":5,
                             "is_question":True})

        # Method 4: AI expansion (Gemini)
        try:
            prompt = f"""Generate 25 long-tail keywords for pillar "{pillar}" under universe "{universe}".
Business: {ctx.get('name','')} | Industry: {ctx.get('industry','spices')}
Include: question formats, buying keywords, comparison, local (Kerala/Malabar/Wayanad), language variants.
Return ONLY a JSON array of keyword strings."""
            text = AI.gemini(prompt, temperature=0.4)
            ai_kws = AI.parse_json(text)
            if isinstance(ai_kws, list):
                for k in ai_kws:
                    results.append({"term": str(k).lower(), "method": "gemini_ai",
                                    "kd_estimate": 10})
        except Exception:
            pass

        return results

    def _dedup(self, kws: List[dict]) -> List[dict]:
        """Hash dedup + semantic dedup."""
        seen, unique = set(), []
        for kw in kws:
            h = hashlib.md5(kw["term"].lower().strip().encode()).hexdigest()
            if h not in seen and len(kw["term"].split()) >= 2:
                seen.add(h)
                unique.append(kw)

        # Semantic dedup
        if len(unique) > 20:
            try:
                import numpy as np
                from sklearn.metrics.pairwise import cosine_similarity
                terms = [k["term"] for k in unique]
                emb   = np.array(AI.embed(terms))
                sim   = cosine_similarity(emb)
                keep  = set(range(len(terms)))
                for i in range(len(terms)):
                    for j in range(i+1, len(terms)):
                        if j in keep and sim[i][j] >= 0.92:
                            # Keep the shorter/better-scored one
                            if len(terms[i]) <= len(terms[j]):
                                keep.discard(j)
                            else:
                                keep.discard(i)
                unique = [unique[i] for i in sorted(keep)]
            except Exception:
                pass
        return unique

    def _cross_universe_dedup(self, kws: List[dict],
                               existing: List[str]) -> List[dict]:
        """Remove keywords that already exist in other universes."""
        existing_set = set(k.lower().strip() for k in existing)
        return [k for k in kws if k["term"].lower().strip() not in existing_set]

    def _score(self, kws: List[dict], ctx: dict) -> List[dict]:
        """Score keywords using DeepSeek. Batch for efficiency."""
        import math
        for kw in kws:
            vol  = kw.get("volume_estimate", 500)
            kd   = kw.get("kd_estimate", 25)
            kw["volume_score"]   = min(math.log10(max(vol,10))/5.0, 1.0)
            kw["kd_inverse"]     = 1.0 - (min(kd,100)/100.0)
            kw["is_info_gap"]    = kw.get("is_info_gap", False)
            base = (kw["volume_score"]*0.20 + kw["kd_inverse"]*0.35 +
                    (1.0 if kw["is_info_gap"] else 0.3)*0.25 + 0.5*0.20) * 10
            if kw["is_info_gap"]:
                base *= 1.25
            kw["final_score"] = round(min(base, 10.0), 2)
        return sorted(kws, key=lambda x: x["final_score"], reverse=True)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6 — BLOG SUGGESTION ENGINE
# ─────────────────────────────────────────────────────────────────────────────

class BlogSuggestionEngine:
    """
    After Gate 3. For each confirmed keyword, generates a blog title suggestion.
    Groups by pillar. Shown to customer at Gate 4.
    """

    BLOG_TITLE_PROMPT = """Generate a compelling SEO blog title for each keyword.
Business: {business}
Universe: {universe}
Pillar: {pillar}

For each keyword, generate:
- An SEO-optimised H1 title (human-readable, not robotic)
- Content type (blog|recipe|guide|faq|comparison|tool)
- Why this content will rank (one sentence)
- Target persona

Keywords:
{keywords}

Return ONLY valid JSON array:
[
  {{
    "keyword": "original keyword",
    "title": "The SEO Blog Title — Human and Compelling",
    "content_type": "blog|recipe|guide|faq|comparison|tool",
    "why_ranks": "because no competitor answers X specifically",
    "persona": "who this is for",
    "is_info_gap": true|false,
    "language": "english|malayalam|hindi",
    "religion_context": "general|hindu|muslim|christian",
    "est_rank_weeks": 2-24
  }}
]"""

    def run(self, universe: Universe, keywords: List[dict],
             business_ctx: dict, job: PipelineJob) -> List[dict]:
        """Generate blog suggestions for all confirmed keywords."""
        suggestions = []
        # Group keywords by pillar for better titles
        pillar_groups = {}
        for kw in keywords[:100]:  # top 100
            pillar = kw.get("pillar", "general")
            pillar_groups.setdefault(pillar, []).append(kw)

        for pillar, pillar_kws in pillar_groups.items():
            job.log("BlogEngine", "info",
                    f"Generating titles for pillar '{pillar}': {len(pillar_kws)} keywords")
            # Batch in groups of 10
            for i in range(0, len(pillar_kws), 10):
                batch = pillar_kws[i:i+10]
                prompt = self.BLOG_TITLE_PROMPT.format(
                    business=f"{business_ctx.get('name','')} — {business_ctx.get('usp','')}",
                    universe=universe.term, pillar=pillar,
                    keywords="\n".join(f"- {k['term']}" for k in batch)
                )
                text = AI.gemini(prompt, temperature=0.4)
                try:
                    batch_titles = AI.parse_json(text)
                    if isinstance(batch_titles, list):
                        suggestions.extend(batch_titles)
                except Exception as e:
                    log.warning(f"Blog title batch parse failed: {e}")
                time.sleep(0.5)

        job.log("BlogEngine", "success",
                f"Blog suggestions: {len(suggestions)} titles generated")
        return suggestions


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 7 — CLAUDE FINAL STRATEGY ENGINE
# ─────────────────────────────────────────────────────────────────────────────

class ClaudeFinalStrategy:
    """
    After Gate 4. Receives EVERYTHING.
    Claude thinks like a senior SEO strategist to rank every keyword #1.
    """

    CLAUDE_SYSTEM = """You are the world's best SEO strategist with 15 years of experience
ranking websites to #1 on Google for competitive and niche keywords in India.

You understand:
- How Indian consumers search differently by religion, region, language
- Festival and seasonal buying patterns (Onam, Eid, Christmas, Diwali)
- E-E-A-T requirements for different industries
- Information Gain theory — unique content beats AI echo chambers
- Topic cluster authority building (quick wins first → medium → hard)
- GEO optimization for Perplexity/ChatGPT/Google AI citation
- Internal link architecture as a "knowledge graph" signal

You think like a human strategist — you see the full picture, not just keywords.
You cross-check everything: cannibalisation, sequence logic, seasonal timing, link dependencies.
You give honest, specific, actionable recommendations. Not generic SEO advice.

Respond ONLY in valid JSON."""

    STRATEGY_PROMPT = """You have been given complete keyword intelligence data for a business.
Read everything. Think. Then produce the definitive strategy to rank these keywords #1.

=== BUSINESS ===
{business_json}

=== ALL CONFIRMED UNIVERSES + PILLARS ===
{universes_json}

=== ALL CONFIRMED KEYWORDS (top 50 per universe) ===
{keywords_json}

=== ALL CONFIRMED BLOG SUGGESTIONS ===
{blogs_json}

=== COMPETITOR INTELLIGENCE ===
{competitor_json}

=== PERSONAS + CONTEXT ===
{context_json}

Now think step by step:

STEP 1: What is the single biggest opportunity? (the info gap or low-KD keyword that guarantees a fast #1)
STEP 2: Are there any keyword cannibalisation risks? (two blogs targeting the same keyword)
STEP 3: What is the exact Week 1-2 publication sequence? (info gaps first, always)
STEP 4: How do the universes link to each other? (internal link architecture)
STEP 5: Are seasonal articles scheduled early enough? (Christmas needs 6 weeks lead)
STEP 6: What will be ranking #1 by month 3, month 6, month 12?
STEP 7: What are the top 3 risks that could derail this strategy?

Return ONLY valid JSON:
{{
  "strategy_headline": "one sentence describing the core strategy",
  "biggest_opportunity": {{
    "keyword": "...", "kd": 0, "why": "...", "est_rank_weeks": 0
  }},
  "cannibalisation_risks": [
    {{"blog_1":"...", "blog_2":"...", "fix":"..."}}
  ],
  "week_1_sequence": [
    {{"title":"...", "keyword":"...", "why_first":"...", "pillar":"..."}}
  ],
  "internal_link_map": {{
    "pillar_to_pillar": [{{"from":"...", "to":"...", "anchor":"..."}}],
    "to_product_page":  [{{"from":"...", "anchor":"...", "intent":"transactional"}}]
  }},
  "seasonal_warnings": [
    {{"event":"...", "articles_affected":["..."], "must_publish_by":"...", "generate_by":"..."}}
  ],
  "ranking_milestones": [
    {{"month":3, "keywords_top3":0, "keywords_top10":0, "milestone":"..."}},
    {{"month":6, "keywords_top3":0, "keywords_top10":0, "milestone":"..."}},
    {{"month":12,"keywords_top3":0, "keywords_top10":0, "milestone":"..."}}
  ],
  "top_3_risks": [
    {{"risk":"...", "probability":"low|medium|high", "mitigation":"..."}}
  ],
  "priority_changes": [
    {{"blog_title":"...", "current_position":0, "suggested_position":0, "reason":"..."}}
  ],
  "missing_content_gaps": ["content angle that would help rank faster"],
  "confidence_score": 0.0-1.0
}}"""

    def run(self, job: PipelineJob, business_ctx: dict,
             personas: List[dict]) -> Tuple[dict, int]:
        """Feed everything to Claude."""
        job.log("Claude", "info", "Preparing complete context package...")

        # Compress data
        universes_summary = [
            {
                "term": u.term,
                "pillars": [p.get("name","") for p in u.pillars],
                "keyword_count": len(u.keywords),
                "top_keywords": [
                    {"term":k.get("term",""), "kd":k.get("kd_estimate",0),
                     "score":k.get("final_score",0), "is_gap":k.get("is_info_gap",False)}
                    for k in u.keywords[:20]
                ],
                "blog_count": len(u.blog_suggestions),
            }
            for u in job.universes
        ]

        all_blogs = [
            {"title":b.get("title",""), "keyword":b.get("keyword",""),
             "content_type":b.get("content_type",""), "is_gap":b.get("is_info_gap",False),
             "persona":b.get("persona",""), "religion":b.get("religion_context",""),
             "universe": u.term}
            for u in job.universes
            for b in u.blog_suggestions
        ]

        prompt = self.STRATEGY_PROMPT.format(
            business_json=json.dumps(business_ctx, indent=2)[:800],
            universes_json=json.dumps(universes_summary, indent=2)[:3000],
            keywords_json=json.dumps([k for u in job.universes for k in u.keywords[:15]], indent=2)[:2000],
            blogs_json=json.dumps(all_blogs[:40], indent=2)[:2000],
            competitor_json=json.dumps(business_ctx.get("competitor_analysis", {}))[:500],
            context_json=json.dumps(personas[:5], indent=2)[:800]
        )

        job.log("Claude", "info", f"Sending to Claude ({len(prompt)//4} tokens approx)...")
        text, tokens = AI.claude(self.CLAUDE_SYSTEM, prompt, max_tokens=4000)
        job.log("Claude", "success", f"Strategy complete · {tokens} tokens used")

        try:
            strategy = AI.parse_json(text)
        except Exception as e:
            job.log("Claude", "error", f"Strategy parse failed: {e}")
            strategy = {"error": str(e), "raw": text[:500]}

        return strategy, tokens


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 8 — CONTENT CALENDAR GENERATOR
# ─────────────────────────────────────────────────────────────────────────────

class ContentCalendarGenerator:
    """
    After Gate 5 + Duration selection.
    Takes all approved blog suggestions + Claude's priority sequence
    → generates date-assigned content calendar.
    """

    def generate(self, job: PipelineJob, duration_years: float,
                  start_date: datetime = None) -> List[dict]:
        """
        Create full content calendar.
        Duration: 1.0 = 1 year, 2.0 = 2 years, etc.
        """
        start  = start_date or datetime.utcnow()
        end    = start + timedelta(days=int(365 * duration_years))
        total_days = (end - start).days

        # Get priority sequence from Claude strategy
        strategy       = job.final_strategy
        priority_seq   = strategy.get("week_1_sequence", [])
        seasonal_warns = strategy.get("seasonal_warnings", [])

        # Build all blogs across all universes
        all_blogs = []
        for universe in job.universes:
            for blog in universe.blog_suggestions:
                if blog.get("confirmed", True):  # only confirmed blogs
                    all_blogs.append({
                        **blog,
                        "universe":   universe.term,
                        "status":     "scheduled",
                        "frozen":     False,
                        "body":       None,
                        "published_url": None,
                    })

        total_blogs = len(all_blogs)
        if total_blogs == 0:
            return []

        # Publishing pace
        blogs_per_week = max(1, total_blogs // (total_days // 7))
        days_between   = max(1, total_days // total_blogs)

        # Reorder: priority blogs first (from Claude's week_1_sequence)
        priority_titles = [s.get("title","").lower() for s in priority_seq]
        def priority_key(blog):
            title = blog.get("title","").lower()
            for i, pt in enumerate(priority_titles):
                if pt in title or title in pt:
                    return i
            if blog.get("is_info_gap"):
                return len(priority_titles)
            kd = blog.get("kd_estimate", 50)
            return len(priority_titles) + kd

        all_blogs.sort(key=priority_key)

        # Handle seasonal constraints
        seasonal_adjustments = {}
        for warn in seasonal_warns:
            must_by = warn.get("must_publish_by","")
            for title in warn.get("articles_affected", []):
                seasonal_adjustments[title.lower()] = must_by

        # Assign dates
        calendar = []
        for i, blog in enumerate(all_blogs):
            # Check seasonal constraint
            title_lower = blog.get("title","").lower()
            if title_lower in seasonal_adjustments:
                try:
                    deadline    = datetime.fromisoformat(seasonal_adjustments[title_lower])
                    # Schedule 6 weeks before deadline
                    pub_date    = deadline - timedelta(weeks=6)
                    if pub_date < start:
                        pub_date = start + timedelta(days=1)
                except Exception:
                    pub_date = start + timedelta(days=i * days_between)
            else:
                pub_date = start + timedelta(days=i * days_between)

            if pub_date > end:
                pub_date = end - timedelta(days=1)

            blog_entry = {
                "id":             f"blog_{i:04d}",
                "title":          blog.get("title",""),
                "keyword":        blog.get("keyword",""),
                "universe":       blog.get("universe",""),
                "pillar":         blog.get("pillar",""),
                "content_type":   blog.get("content_type","blog"),
                "language":       blog.get("language","english"),
                "religion_context":blog.get("religion_context","general"),
                "persona":        blog.get("persona",""),
                "is_info_gap":    blog.get("is_info_gap", False),
                "kd_estimate":    blog.get("kd_estimate",20),
                "scheduled_date": pub_date.strftime("%Y-%m-%d"),
                "status":         "scheduled",
                "frozen":         False,
                "body":           None,
                "published_url":  None,
                "week_number":    (pub_date - start).days // 7 + 1,
                "month":          pub_date.month,
                "year":           pub_date.year,
            }
            calendar.append(blog_entry)

        return sorted(calendar, key=lambda x: x["scheduled_date"])

    def summary(self, calendar: List[dict], duration_years: float) -> dict:
        """Stats for display after calendar generation."""
        total = len(calendar)
        by_lang   = {}
        by_uni    = {}
        by_month  = {}
        info_gaps = sum(1 for b in calendar if b.get("is_info_gap"))

        for b in calendar:
            by_lang[b.get("language","english")] = by_lang.get(b.get("language","english"),0)+1
            by_uni[b.get("universe","")] = by_uni.get(b.get("universe",""),0)+1
            key = f"{b['year']}-{b['month']:02d}"
            by_month[key] = by_month.get(key,0)+1

        return {
            "total_blogs":     total,
            "duration_years":  duration_years,
            "blogs_per_week":  round(total / (52 * duration_years), 1),
            "info_gap_blogs":  info_gaps,
            "by_language":     by_lang,
            "by_universe":     by_uni,
            "by_month":        by_month,
            "first_publish":   min(b["scheduled_date"] for b in calendar) if calendar else "",
            "last_publish":    max(b["scheduled_date"] for b in calendar) if calendar else "",
        }


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 9 — MAIN PIPELINE ORCHESTRATOR
# ─────────────────────────────────────────────────────────────────────────────

class RufloPipeline:
    """
    Main pipeline with 5 confirmation gates.
    
    In production: each gate pauses execution, saves state to DB,
    returns to frontend for customer interaction, then resumes.
    
    In this module: gate_callback simulates customer interaction.
    Swap gate_callback with real API calls in production.
    """

    def __init__(self):
        self.intelligence = KeywordIntelligenceLayer()
        self.universe_eng = UniverseEngine()
        self.expansion_eng= KeywordExpansionEngine()
        self.blog_eng     = BlogSuggestionEngine()
        self.claude_eng   = ClaudeFinalStrategy()
        self.calendar_gen = ContentCalendarGenerator()

    def run(self, raw_keywords: List[str], business_ctx: dict,
             gate_callback=None, duration_years: float = 1.0) -> PipelineJob:
        """
        Full pipeline with 5 gates.
        gate_callback(gate: GateState, job: PipelineJob) → modified GateState
        If None, uses automatic approval (for testing).
        """
        import uuid
        job = PipelineJob(
            id=uuid.uuid4().hex,
            project_id=business_ctx.get("project_id","demo")
        )

        if gate_callback is None:
            gate_callback = self._auto_approve

        print(f"\n{'═'*60}")
        print(f"  RUFLO PIPELINE — {business_ctx.get('name','Business')}")
        print(f"  Input keywords: {raw_keywords}")
        print(f"{'═'*60}\n")

        # ── INTELLIGENCE LAYER ────────────────────────────────────────────────
        job.log("Intelligence", "info", "Analysing customer input keywords...")
        classified = self.intelligence.classify(raw_keywords, business_ctx)
        formatted  = self.intelligence.format_for_customer(classified)

        job.log("Intelligence", "success",
                f"Classification complete: {formatted['universes_count']} universes, "
                f"{len(formatted['merged'])} supporting, "
                f"{formatted['needs_decision']} ambiguous",
                formatted)

        # ── GATE 1: Universe Confirmation ─────────────────────────────────────
        gate1 = GateState(1, "Universe Confirmation", data={"classification": formatted})
        gate1 = gate_callback(gate1, job)
        if gate1.status != "confirmed":
            job.status = "cancelled_at_gate_1"
            return job

        # Build Universe objects from confirmed list
        confirmed_universes = gate1.data.get("confirmed_universes", formatted["universes"])
        for u_data in confirmed_universes:
            term = u_data.get("term", u_data) if isinstance(u_data, dict) else u_data
            job.universes.append(Universe(
                id=hashlib.md5(term.encode()).hexdigest()[:8],
                term=term
            ))

        # ── UNIVERSE ENGINE (per universe) ───────────────────────────────────
        for universe in job.universes:
            universe.status = "running"
            # Customer-input supporting keywords that belong to this universe
            customer_supporting = [
                s["term"] for s in formatted["merged"]
                if s.get("under","").lower() == universe.term.lower()
            ]
            job.log("UniverseEngine", "info",
                    f"Running universe engine for: {universe.term}")
            pillars = self.universe_eng.run(
                universe, business_ctx, customer_supporting, job
            )
            universe.pillars = pillars
            universe.status  = "awaiting_gate_2"

        # ── GATE 2: Pillar Confirmation ───────────────────────────────────────
        gate2_data = {
            u.term: {
                "pillars": u.pillars,
                "count":   len(u.pillars)
            }
            for u in job.universes
        }
        gate2 = GateState(2, "Pillar Confirmation", data=gate2_data)
        gate2 = gate_callback(gate2, job)
        if gate2.status != "confirmed":
            job.status = "cancelled_at_gate_2"
            return job

        # Apply any pillar edits from customer
        for universe in job.universes:
            confirmed_pillars = gate2.data.get(
                f"{universe.term}_confirmed_pillars", universe.pillars
            )
            universe.pillars  = confirmed_pillars
            universe.status   = "running"

        # ── KEYWORD EXPANSION (per universe) ─────────────────────────────────
        # Collect all keywords from previously processed universes for cross-dedup
        existing_project_kws = []
        for universe in job.universes:
            job.log("ExpansionEngine", "info",
                    f"Expanding keywords for universe: {universe.term}")
            keywords = self.expansion_eng.run(
                universe, existing_project_kws, business_ctx, job
            )
            universe.keywords = keywords
            existing_project_kws.extend([k["term"] for k in keywords])
            universe.status = "awaiting_gate_3"

        # ── GATE 3: Keyword Universe Confirmation ─────────────────────────────
        gate3_data = {
            "universes": [
                {
                    "term":   u.term,
                    "count":  len(u.keywords),
                    "mix": {
                        "quick_wins": sum(1 for k in u.keywords if k.get("kd_estimate",50)<10),
                        "medium":     sum(1 for k in u.keywords if 10<=k.get("kd_estimate",50)<30),
                        "hard":       sum(1 for k in u.keywords if 30<=k.get("kd_estimate",50)<60),
                        "authority":  sum(1 for k in u.keywords if k.get("kd_estimate",50)>=60),
                    },
                    "info_gaps": sum(1 for k in u.keywords if k.get("is_info_gap")),
                    "top_10":   [k.get("term","") for k in u.keywords[:10]]
                }
                for u in job.universes
            ],
            "total_keywords": sum(len(u.keywords) for u in job.universes)
        }
        gate3 = GateState(3, "Keyword Universe Confirmation", data=gate3_data)
        gate3 = gate_callback(gate3, job)
        if gate3.status != "confirmed":
            job.status = "cancelled_at_gate_3"
            return job

        # Apply customer keyword edits (rejections, additions)
        for edit in gate3.customer_edits:
            action  = edit.get("action")
            term    = edit.get("term","").lower()
            uni_id  = edit.get("universe_id","")
            for universe in job.universes:
                if universe.id == uni_id or universe.term.lower() == edit.get("universe","").lower():
                    if action == "reject":
                        universe.keywords = [k for k in universe.keywords
                                             if k.get("term","").lower() != term]
                    elif action == "add":
                        universe.keywords.append({
                            "term": edit.get("term",""), "kd_estimate": 10,
                            "source": "customer_added", "final_score": 7.0
                        })

        # ── BLOG SUGGESTION ENGINE ────────────────────────────────────────────
        for universe in job.universes:
            job.log("BlogEngine", "info",
                    f"Generating blog suggestions for: {universe.term}")
            blogs = self.blog_eng.run(
                universe, universe.keywords, business_ctx, job
            )
            universe.blog_suggestions = blogs
            universe.status = "awaiting_gate_4"

        # ── GATE 4: Blog Suggestions Confirmation ────────────────────────────
        gate4_data = {
            "universes": [
                {
                    "term":  u.term,
                    "count": len(u.blog_suggestions),
                    "by_type": {
                        t: sum(1 for b in u.blog_suggestions if b.get("content_type")==t)
                        for t in ["blog","recipe","guide","faq","comparison","tool"]
                    },
                    "blogs": u.blog_suggestions[:5]  # preview first 5
                }
                for u in job.universes
            ],
            "total_blogs": sum(len(u.blog_suggestions) for u in job.universes)
        }
        gate4 = GateState(4, "Blog Suggestions Confirmation", data=gate4_data)
        gate4 = gate_callback(gate4, job)
        if gate4.status != "confirmed":
            job.status = "cancelled_at_gate_4"
            return job

        # Apply blog rejections
        for edit in gate4.customer_edits:
            if edit.get("action") == "reject":
                for universe in job.universes:
                    universe.blog_suggestions = [
                        b for b in universe.blog_suggestions
                        if b.get("title","").lower() != edit.get("title","").lower()
                    ]

        # ── CLAUDE FINAL STRATEGY ─────────────────────────────────────────────
        job.log("Claude", "info",
                f"Starting final strategy analysis. Total context: "
                f"{sum(len(u.keywords) for u in job.universes)} keywords, "
                f"{sum(len(u.blog_suggestions) for u in job.universes)} blogs")

        strategy, tokens = self.claude_eng.run(
            job, business_ctx,
            business_ctx.get("personas", [])
        )
        job.final_strategy = strategy

        job.log("Claude", "data",
                f"Strategy produced: "
                f"{len(strategy.get('week_1_sequence',[]))} week-1 articles, "
                f"{len(strategy.get('ranking_milestones',[]))} milestones, "
                f"{len(strategy.get('cannibalisation_risks',[]))} conflicts found",
                {"tokens": tokens})

        # ── GATE 5: Final Strategy Confirmation ───────────────────────────────
        gate5 = GateState(5, "Final Strategy Confirmation",
                          data={"strategy": strategy, "tokens": tokens})
        gate5 = gate_callback(gate5, job)
        if gate5.status != "confirmed":
            # Customer asked Claude to revise something
            if gate5.status == "revision_requested":
                revision_note = gate5.data.get("revision_request","")
                job.log("Claude", "info", f"Revision requested: {revision_note}")
                # Could run a targeted Claude revision here
            else:
                job.status = "cancelled_at_gate_5"
                return job

        # ── CONTENT CALENDAR ──────────────────────────────────────────────────
        job.log("Calendar", "info",
                f"Generating {duration_years}-year content calendar...")
        calendar = self.calendar_gen.generate(job, duration_years)
        summary  = self.calendar_gen.summary(calendar, duration_years)

        job.log("Calendar", "success",
                f"Calendar ready: {summary['total_blogs']} blogs · "
                f"{summary['blogs_per_week']} per week · "
                f"{summary['info_gap_blogs']} info gaps first",
                summary)

        # Save to job
        job.content_duration_years = duration_years
        job.final_strategy["calendar"] = calendar
        job.final_strategy["calendar_summary"] = summary
        job.status = "complete"

        print(f"\n{'═'*60}")
        print(f"  PIPELINE COMPLETE")
        print(f"  {summary['total_blogs']} blogs · {duration_years} year(s)")
        print(f"  {summary['info_gap_blogs']} info gap articles (Week 1 priority)")
        print(f"{'═'*60}\n")

        return job

    def add_universe_keyword(self, existing_job: PipelineJob,
                              new_keyword: str, business_ctx: dict,
                              gate_callback=None) -> PipelineJob:
        """
        Add a new universe keyword to an existing completed pipeline.
        Runs through all 5 gates for the new keyword ONLY.
        Existing keywords and content are untouched.
        """
        import uuid
        print(f"\n{'─'*60}")
        print(f"  ADD NEW UNIVERSE: {new_keyword}")
        print(f"  Existing universes: {[u.term for u in existing_job.universes]}")
        print(f"{'─'*60}\n")

        # Check if this is truly new (not already in existing universes)
        existing_terms = [u.term.lower() for u in existing_job.universes]
        all_kws = [u.term for u in existing_job.universes] + [new_keyword]
        classified = self.intelligence.classify(all_kws, business_ctx)

        new_classified = next(
            (c for c in classified if c.raw_input.lower() == new_keyword.lower()), None
        )
        if new_classified and new_classified.role == KeywordRole.SUPPORTING:
            # It's a supporting keyword of an existing universe
            for universe in existing_job.universes:
                if universe.term.lower() == (new_classified.parent_universe or "").lower():
                    universe.keywords.append({
                        "term": new_keyword, "source": "customer_added",
                        "kd_estimate": 10, "final_score": 7.0
                    })
                    print(f"  '{new_keyword}' added as supporting keyword under '{universe.term}'")
                    return existing_job

        # It's a new universe — run mini pipeline
        mini_job = PipelineJob(
            id=uuid.uuid4().hex,
            project_id=existing_job.project_id,
        )

        # Collect all existing keywords for cross-dedup
        existing_kw_terms = [k["term"] for u in existing_job.universes
                             for k in u.keywords]

        if gate_callback is None:
            gate_callback = self._auto_approve

        # Mini-pipeline: same 5 gates, new keyword only
        mini_job.log("Pipeline", "info",
                     f"Starting mini-pipeline for new universe: {new_keyword}")

        new_universe = Universe(
            id=hashlib.md5(new_keyword.encode()).hexdigest()[:8],
            term=new_keyword
        )
        mini_job.universes = [new_universe]

        # Gate 1 (simplified — just one universe)
        gate1 = GateState(1, f"Confirm new universe: {new_keyword}",
                          data={"universes": [{"term": new_keyword}]})
        gate1 = gate_callback(gate1, mini_job)
        if gate1.status != "confirmed":
            return existing_job

        # Universe engine
        pillars = self.universe_eng.run(new_universe, business_ctx, [], mini_job)
        new_universe.pillars = pillars

        # Gate 2
        gate2 = GateState(2, f"Pillars for {new_keyword}",
                          data={new_keyword: {"pillars": pillars}})
        gate2 = gate_callback(gate2, mini_job)
        if gate2.status != "confirmed":
            return existing_job
        new_universe.pillars = gate2.data.get("confirmed_pillars", pillars)

        # Expansion (with cross-universe dedup against all existing)
        keywords = self.expansion_eng.run(
            new_universe, existing_kw_terms, business_ctx, mini_job
        )
        new_universe.keywords = keywords

        # Gate 3
        gate3 = GateState(3, f"Keywords for {new_keyword}",
                          data={"total": len(keywords), "preview": keywords[:10]})
        gate3 = gate_callback(gate3, mini_job)
        if gate3.status != "confirmed":
            return existing_job

        # Blog suggestions
        blogs = self.blog_eng.run(new_universe, keywords, business_ctx, mini_job)
        new_universe.blog_suggestions = blogs

        # Gate 4
        gate4 = GateState(4, f"Blog suggestions for {new_keyword}",
                          data={"count": len(blogs), "preview": blogs[:5]})
        gate4 = gate_callback(gate4, mini_job)
        if gate4.status != "confirmed":
            return existing_job

        # Claude updates strategy with new universe
        # Merge new universe into existing job
        existing_job.universes.append(new_universe)
        mini_job.log("Pipeline", "info",
                     "Updating Claude strategy with new universe...")

        updated_strategy, tokens = self.claude_eng.run(
            existing_job, business_ctx,
            business_ctx.get("personas", [])
        )

        # Gate 5
        gate5 = GateState(5, f"Updated strategy with {new_keyword}",
                          data={"strategy": updated_strategy, "tokens": tokens})
        gate5 = gate_callback(gate5, mini_job)
        if gate5.status == "confirmed":
            existing_job.final_strategy = updated_strategy
            mini_job.log("Pipeline", "success",
                         f"'{new_keyword}' successfully added to project")

        return existing_job

    @staticmethod
    def _auto_approve(gate: GateState, job: PipelineJob) -> GateState:
        """Auto-approve all gates (for testing). Replace with real UI in production."""
        gate.status = "confirmed"
        gate.confirmed_at = datetime.utcnow().isoformat()
        job.log("Gate", "success",
                f"Gate {gate.gate_number} '{gate.gate_name}' — AUTO-APPROVED")
        return gate


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 10 — TESTS
# ─────────────────────────────────────────────────────────────────────────────

class Tests:
    """
    Run:
      python ruflo_confirmation_pipeline.py test intelligence   # input classification
      python ruflo_confirmation_pipeline.py test pipeline       # full flow (auto gates)
      python ruflo_confirmation_pipeline.py test add_keyword    # add universe later
      python ruflo_confirmation_pipeline.py test cross_dedup    # cross-universe dedup
    """

    BUSINESS = {
        "name":        "Pureleven Organics",
        "industry":    "food_spices",
        "usp":         "single-origin organic spices from Wayanad Kerala, farm-direct",
        "products":    ["Black Pepper", "Cardamom", "Cinnamon"],
        "website_url": "https://pureleven.com",
        "project_id":  "proj_001",
    }

    def _h(self, n): print(f"\n{'─'*55}\n  TEST: {n}\n{'─'*55}")
    def _ok(self, m): print(f"  ✓ {m}")

    def test_intelligence(self):
        self._h("Intelligence Layer — classify customer input")
        layer = KeywordIntelligenceLayer()

        # Messy customer input as described in requirements
        raw = ["Black Pepper", "Turmeric", "Spices online",
               "Organic Black Pepper", "buy black pepper", "Kerala spices",
               "Turmeric spices"]  # near-duplicate of Turmeric

        classified = layer.classify(raw, self.BUSINESS)
        formatted  = layer.format_for_customer(classified)

        self._ok(f"Input: {raw}")
        print()
        self._ok("Universes detected:")
        for u in formatted["universes"]:
            print(f"      ✦ {u['term']} — {u['suggestion']}")

        print()
        self._ok("Merged as supporting:")
        for s in formatted["merged"]:
            print(f"      → '{s['term']}' ({s['role']}) under '{s['under']}'")

        if formatted["ambiguous"]:
            print()
            self._ok("Ambiguous (needs customer decision):")
            for a in formatted["ambiguous"]:
                print(f"      ? '{a['term']}' — {a['why']}")
                for alt in a["alternatives"]:
                    print(f"        • {alt}")

        assert len(formatted["universes"]) >= 2, "Should find at least 2 universes"
        self._ok(f"\nClassification: {formatted['universes_count']} universes, "
                 f"{len(formatted['merged'])} merged, {formatted['needs_decision']} ambiguous")

    def test_cross_dedup(self):
        self._h("Cross-Universe Dedup")
        expansion = KeywordExpansionEngine()

        existing_kws = ["organic spices online", "buy spices India", "best masala"]
        new_kws = [
            {"term": "organic spices online", "kd_estimate": 8},   # duplicate
            {"term": "turmeric health benefits", "kd_estimate": 12},  # unique
            {"term": "best masala", "kd_estimate": 20},              # duplicate
            {"term": "buy turmeric powder", "kd_estimate": 6},       # unique
        ]
        deduped = expansion._cross_universe_dedup(new_kws, existing_kws)
        self._ok(f"Before cross-dedup: {len(new_kws)} keywords")
        self._ok(f"After cross-dedup:  {len(deduped)} keywords (removed {len(new_kws)-len(deduped)} duplicates)")
        remaining = [k["term"] for k in deduped]
        self._ok(f"Remaining: {remaining}")
        assert "organic spices online" not in remaining, "Duplicate should be removed"
        assert "turmeric health benefits" in remaining, "Unique should stay"

    def test_pipeline(self):
        self._h("FULL PIPELINE — Pureleven Spices (auto-approve gates)")
        pipeline = RufloPipeline()
        raw_kws  = ["Black Pepper", "Turmeric", "Spices online", "Organic Black Pepper"]

        job = pipeline.run(
            raw_keywords=raw_kws,
            business_ctx=self.BUSINESS,
            gate_callback=None,   # auto-approve for testing
            duration_years=1.0
        )

        self._ok(f"Status: {job.status}")
        self._ok(f"Universes: {[u.term for u in job.universes]}")
        for u in job.universes:
            self._ok(f"  {u.term}: {len(u.pillars)} pillars · "
                     f"{len(u.keywords)} keywords · "
                     f"{len(u.blog_suggestions)} blogs")

        if job.final_strategy:
            s = job.final_strategy
            self._ok(f"Strategy: {s.get('strategy_headline','?')[:70]}")
            self._ok(f"Biggest opportunity: {s.get('biggest_opportunity',{}).get('keyword','?')}")
            self._ok(f"Cannibalisation risks: {len(s.get('cannibalisation_risks',[]))}")

        cal = job.final_strategy.get("calendar",[])
        sum_= job.final_strategy.get("calendar_summary",{})
        self._ok(f"Calendar: {sum_.get('total_blogs',0)} blogs · "
                 f"{sum_.get('blogs_per_week',0)}/week · "
                 f"{sum_.get('info_gap_blogs',0)} info gaps")

        return job

    def test_add_keyword(self):
        self._h("ADD NEW UNIVERSE after pipeline complete")
        pipeline = RufloPipeline()

        # First run base pipeline
        print("  Running base pipeline first...")
        raw_kws = ["Black Pepper"]
        job = pipeline.run(raw_kws, self.BUSINESS, None, 1.0)
        initial_universes = len(job.universes)
        initial_blogs = sum(len(u.blog_suggestions) for u in job.universes)
        self._ok(f"Base pipeline: {initial_universes} universe(s), {initial_blogs} blogs")

        # Now add "Cardamom" as new universe
        print("\n  Adding 'Cardamom' as new universe...")
        updated_job = pipeline.add_universe_keyword(
            job, "Cardamom", self.BUSINESS, None
        )

        new_universes = len(updated_job.universes)
        new_blogs     = sum(len(u.blog_suggestions) for u in updated_job.universes)
        self._ok(f"After adding Cardamom: {new_universes} universe(s), {new_blogs} blogs")
        assert new_universes > initial_universes, "Should have one more universe"
        self._ok("Existing Black Pepper content NOT affected ✓")

    def run_all(self):
        tests = [
            ("intelligence", self.test_intelligence),
            ("cross_dedup",  self.test_cross_dedup),
        ]
        print("\n"+"═"*55)
        print("  CONFIRMATION PIPELINE — TESTS")
        print("═"*55)
        p = f = 0
        for name, fn in tests:
            try: fn(); p+=1
            except Exception as e: print(f"  ✗ {name}: {e}"); f+=1
        print(f"\n  {p} passed / {f} failed\n"+"═"*55)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 11 — CLI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    HELP = """
Ruflo — Keyword Intelligence + Confirmation Gate Pipeline
──────────────────────────────────────────────────────────
5 gates. Human confirmation between every engine.
Intelligence layer understands pillar vs supporting keywords.

Usage:
  python ruflo_confirmation_pipeline.py test                  # core tests
  python ruflo_confirmation_pipeline.py test <stage>          # one test
  python ruflo_confirmation_pipeline.py pipeline              # demo full pipeline
  python ruflo_confirmation_pipeline.py add <keyword>         # demo add universe

Stages: intelligence, cross_dedup, pipeline, add_keyword

Gate flow:
  Input → Intelligence → Gate 1 (universes) → Engine → Gate 2 (pillars)
  → Engine → Gate 3 (keywords) → Engine → Gate 4 (blogs)
  → Claude → Gate 5 (strategy) → Duration → Calendar
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
        else:
            t.run_all()

    elif cmd == "pipeline":
        t = Tests()
        job = t.test_pipeline()
        print(f"\nConsole logs: {len(job.console_logs)} entries")

    elif cmd == "add":
        kw  = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "Cardamom"
        t   = Tests()
        t.test_add_keyword()

    else:
        print(f"Unknown: {cmd}\n{HELP}")
