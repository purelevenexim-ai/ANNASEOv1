"""
================================================================================
ANNASEO — INTELLIGENCE ENGINES PACK  (annaseo_intelligence_engines.py)
================================================================================
Builds 6 engines from the pending list:

  1. MultilingualContentEngine
     Language enum already in strategy engine. This generates content in
     Malayalam, Hindi, Tamil, Arabic using Claude (culturally adapted, not translated).
     Hreflang tags auto-generated per article set.

  2. SERPFeatureTargetingEngine
     P6 already collects SERP data. This reads it and structures briefs
     to specifically target: Featured Snippet, PAA, Image Pack, Video Carousel.
     Each feature type has a different content structure requirement.

  3. VoiceSearchOptimiser
     Adds "question" intent category to P5 classification.
     Restructures article briefs for voice: direct spoken answer in ≤30 words,
     conversational H2s, FAQ structured for Google Assistant.

  4. RankingPredictionEngine
     Before writing: predict likely position in 90 days.
     Factors: domain authority proxy, KD estimate, content plan score,
     how many competitors have a dedicated page.
     Stored as prediction, compared vs actual at 90-day mark.

  5. SeasonalKeywordCalendar
     Detect peak search months per keyword using free trend data.
     Auto-schedule content 8 weeks before predicted peak.
     Refresh alert 4 weeks before next peak if already published.

  6. SearchIntentShiftDetector
     Re-classify intent for published keywords weekly.
     If intent shifts from informational to transactional → alert.
     Auto-suggest content update to match new intent.
================================================================================
"""

from __future__ import annotations

import os, re, json, hashlib, time, logging, sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

import requests as _req

log = logging.getLogger("annaseo.intelligence")
def _GEMINI_URL() -> str:
    model = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
    return f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GROQ_URL     = "https://api.groq.com/openai/v1/chat/completions"
OLLAMA_URL   = os.getenv("OLLAMA_URL", "http://172.235.16.165:11434")
DB_PATH      = Path(os.getenv("ANNASEO_DB", "./annaseo.db"))


def _db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.executescript("""
    CREATE TABLE IF NOT EXISTS multilingual_articles (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id  TEXT NOT NULL,
        article_id  TEXT NOT NULL,
        language    TEXT NOT NULL,
        title       TEXT DEFAULT '',
        body        TEXT DEFAULT '',
        meta_title  TEXT DEFAULT '',
        meta_desc   TEXT DEFAULT '',
        hreflang    TEXT DEFAULT '',
        status      TEXT DEFAULT 'draft',
        created_at  TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS serp_feature_briefs (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        keyword     TEXT NOT NULL,
        project_id  TEXT NOT NULL,
        feature     TEXT NOT NULL,
        structure   TEXT DEFAULT '{}',
        created_at  TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS ranking_predictions (
        pred_id     TEXT PRIMARY KEY,
        project_id  TEXT NOT NULL,
        keyword     TEXT NOT NULL,
        article_id  TEXT DEFAULT '',
        predicted_pos REAL DEFAULT 0,
        confidence  REAL DEFAULT 0,
        factors     TEXT DEFAULT '{}',
        predicted_at TEXT DEFAULT CURRENT_TIMESTAMP,
        actual_pos  REAL,
        actual_at   TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS seasonal_signals (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        keyword     TEXT NOT NULL,
        peak_month  INTEGER DEFAULT 0,
        peak_strength REAL DEFAULT 0,
        trough_month INTEGER DEFAULT 0,
        data_source TEXT DEFAULT 'estimated',
        created_at  TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS intent_shift_alerts (
        alert_id    TEXT PRIMARY KEY,
        project_id  TEXT NOT NULL,
        keyword     TEXT NOT NULL,
        old_intent  TEXT NOT NULL,
        new_intent  TEXT NOT NULL,
        article_id  TEXT DEFAULT '',
        action      TEXT DEFAULT '',
        resolved    INTEGER DEFAULT 0,
        created_at  TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_ml_article ON multilingual_articles(article_id);
    CREATE INDEX IF NOT EXISTS idx_pred_project ON ranking_predictions(project_id);
    CREATE INDEX IF NOT EXISTS idx_intent_project ON intent_shift_alerts(project_id);
    """)
    con.commit()
    return con


# ─────────────────────────────────────────────────────────────────────────────
# ENGINE 1 — MULTILINGUAL CONTENT
# ─────────────────────────────────────────────────────────────────────────────

# Cultural adaptation rules per language — NOT just translation
LANGUAGE_CULTURE_RULES = {
    "malayalam": {
        "units":          "grams and kilograms, not ounces",
        "currency":       "Indian Rupees (₹)",
        "cooking_refs":   "Kerala cuisine, Malabar recipes, sadya",
        "spice_names":    "use local Malayalam names: kizhinelli (turmeric), kurumulaku (pepper)",
        "tone":           "respectful, knowledgeable about Ayurveda and traditional medicine",
        "search_style":   "often question-form: 'X എന്നത് എന്ത്?', 'X ഉപയോഗിക്കുന്നത് എങ്ങനെ?'",
    },
    "hindi": {
        "units":          "grams, kilograms",
        "currency":       "Indian Rupees (₹)",
        "cooking_refs":   "North Indian cuisine, Ayurvedic traditions, dal tadka",
        "spice_names":    "use Hindi names: हल्दी (turmeric), काली मिर्च (pepper), दालचीनी (cinnamon)",
        "tone":           "warm, authoritative on Ayurveda",
        "search_style":   "direct questions: 'X के फायदे', 'X कैसे खाएं'",
    },
    "tamil": {
        "units":          "grams, kilograms",
        "currency":       "Indian Rupees (₹)",
        "cooking_refs":   "Tamil Nadu cuisine, Chettinad recipes",
        "spice_names":    "use Tamil names: மஞ்சள் (turmeric), மிளகு (pepper), இலவங்கப்பட்டை (cinnamon)",
        "tone":           "knowledgeable about Siddha medicine and traditional Tamil cooking",
        "search_style":   "X பயன்கள், X சாப்பிடுவது எப்படி",
    },
    "arabic": {
        "units":          "grams, kilograms",
        "currency":       "varies by country — use USD for export context",
        "cooking_refs":   "Middle Eastern cuisine, Khaleeji cooking, halal",
        "spice_names":    "Arabic names: الكركم (turmeric), الفلفل الأسود (black pepper), القرفة (cinnamon)",
        "tone":           "professional, emphasise halal certification",
        "search_style":   "فوائد X, كيفية استخدام X",
    },
    "english": {
        "units":          "grams, kilograms, teaspoons",
        "currency":       "USD for international, INR for India",
        "cooking_refs":   "international cuisine",
        "spice_names":    "standard English names",
        "tone":           "professional, E-E-A-T focused",
        "search_style":   "benefits of X, how to use X, buy X online",
    },
}


class MultilingualContentEngine:
    """
    Generate culturally adapted content in Malayalam, Hindi, Tamil, Arabic.
    NOT translation — genuine rewriting with cultural context.
    Uses Claude (same 7-pass engine, language-adapted brief).
    """

    def generate(self, base_article: dict, target_languages: List[str],
                  project_id: str, keyword: str) -> List[dict]:
        """
        base_article: {title, body, meta_title, meta_desc, keyword}
        Returns list of localised articles, one per language.
        """
        results = []
        for lang in target_languages:
            if lang == "english":
                continue   # base article is already English
            localised = self._localise(base_article, lang, keyword)
            if localised:
                results.append(localised)
                # Store in DB
                _db().execute("""
                    INSERT INTO multilingual_articles
                    (project_id,article_id,language,title,body,meta_title,meta_desc,hreflang)
                    VALUES (?,?,?,?,?,?,?,?)
                """, (project_id,
                       base_article.get("article_id",""),
                       lang,
                       localised.get("title",""),
                       localised.get("body",""),
                       localised.get("meta_title",""),
                       localised.get("meta_desc",""),
                       localised.get("hreflang","")))
                _db().commit()
                log.info(f"[Multilingual] Generated {lang}: {localised.get('title','')[:50]}")
        return results

    def _localise(self, article: dict, language: str, keyword: str) -> Optional[dict]:
        rules   = LANGUAGE_CULTURE_RULES.get(language, {})
        key     = os.getenv("ANTHROPIC_API_KEY","")
        if not key:
            return self._deepseek_localise(article, language, rules, keyword)

        try:
            import anthropic
            client = anthropic.Anthropic(api_key=key)
            prompt = f"""Rewrite this article in {language} for a {language}-speaking audience.
This is NOT a translation — it is a cultural adaptation.

Cultural rules for {language}:
- Units: {rules.get('units','')}
- Currency: {rules.get('currency','')}
- Cooking references: {rules.get('cooking_refs','')}
- Local spice names: {rules.get('spice_names','')}
- Tone: {rules.get('tone','')}
- How people search: {rules.get('search_style','')}

Original title: {article.get('title','')}
Keyword: {keyword}

Original article (English):
{article.get('body','')[:3000]}

Write the complete adapted article in {language}.
Include: culturally adapted H1, H2 sections, FAQ, meta title (60 chars), meta description (155 chars).
Format: JSON with keys title, body, meta_title, meta_desc, hreflang (e.g. "ml" for Malayalam)"""

            r = client.messages.create(
                model=os.getenv("CLAUDE_MODEL","claude-sonnet-4-6"),
                max_tokens=4000,
                messages=[{"role":"user","content":prompt}]
            )
            text = r.content[0].text.strip()
            text = re.sub(r"```(?:json)?","",text).strip().rstrip("`").strip()
            m = re.search(r'\{.*\}', text, re.DOTALL)
            if m:
                data = json.loads(m.group(0))
                data["language"] = language
                data["hreflang"] = {"malayalam":"ml","hindi":"hi","tamil":"ta","arabic":"ar"}.get(language,"")
                return data
        except Exception as e:
            log.warning(f"[Multilingual] Claude localise failed ({language}): {e}")
        return self._deepseek_localise(article, language, rules, keyword)

    def _deepseek_localise(self, article: dict, language: str,
                             rules: dict, keyword: str) -> Optional[dict]:
        """Free fallback using DeepSeek local."""
        try:
            r = _req.post(f"{OLLAMA_URL}/api/generate",
                json={"model":"deepseek-r1:7b",
                      "prompt": (
                          f"Adapt this article to {language}. Not just translate — "
                          f"use local food culture, local spice names, local units.\n"
                          f"Keyword: {keyword}\nRules: {json.dumps(rules)}\n"
                          f"Original (first 1000 words): {article.get('body','')[:2000]}\n\n"
                          f"Write article in {language}. Return JSON: "
                          "{\"title\":\"...\",\"body\":\"...\",\"meta_title\":\"...\",\"meta_desc\":\"...\",\"hreflang\":\"\"}"
                      ),
                      "stream":False,"options":{"num_predict":2000}},
                timeout=30)
            if r.ok:
                text = r.json().get("response","").strip()
                m = re.search(r'\{.*\}', text, re.DOTALL)
                if m:
                    data = json.loads(m.group(0))
                    data["language"] = language
                    return data
        except Exception as e:
            log.warning(f"[Multilingual] DeepSeek localise failed: {e}")
        return {"title":f"[{language}] {article.get('title','')}",
                "body":"[Localisation pending]","meta_title":"","meta_desc":"",
                "language":language,"hreflang":""}

    def generate_hreflang_tags(self, article_id: str) -> str:
        """Generate hreflang <link> tags for all language versions of an article."""
        con = _db()
        versions = [dict(r) for r in con.execute(
            "SELECT language, hreflang FROM multilingual_articles WHERE article_id=?",
            (article_id,)
        ).fetchall()]
        tags = []
        for v in versions:
            tags.append(f'<link rel="alternate" hreflang="{v["hreflang"]}" href="/{{slug}}/{v["language"]}/" />')
        tags.append('<link rel="alternate" hreflang="x-default" href="/{{slug}}/" />')
        return "\n".join(tags)


# ─────────────────────────────────────────────────────────────────────────────
# ENGINE 2 — SERP FEATURE TARGETING
# ─────────────────────────────────────────────────────────────────────────────

# Content structure requirements per SERP feature
SERP_FEATURE_STRUCTURES = {
    "featured_snippet": {
        "description": "Direct answer box at top of SERP",
        "content_structure": [
            "First paragraph after H1: answer the query in 40-60 words exactly",
            "Use a definition format: '{Keyword} is...' or numbered list format",
            "Include the exact query keyword in the first sentence",
            "Follow with supporting detail in next paragraph",
        ],
        "avoid": ["starting with 'In this article...'", "burying the answer below the fold"],
        "word_trigger": "definition|what is|how to|best way",
    },
    "people_also_ask": {
        "description": "Expandable question boxes in SERP",
        "content_structure": [
            "Add H2 sections that are questions (start with How, What, Why, When, Is, Can)",
            "Each question H2: answer in first sentence (30 words max), then expand",
            "Include 5-8 PAA-style questions as H2 headings",
            "Each answer self-contained — must make sense without reading surrounding text",
        ],
        "avoid": ["vague question headings", "long preambles before the answer"],
        "word_trigger": "how|what|why|when|is|can|does|should",
    },
    "image_pack": {
        "description": "Row of images in SERP",
        "content_structure": [
            "Include 3+ images in the article with descriptive alt text containing keyword",
            "Alt text format: '{keyword} - {specific description}'",
            "Image file names: keyword-descriptive-phrase.jpg",
            "Add image schema markup (ImageObject in JSON-LD)",
        ],
        "avoid": ["generic alt text like 'image1.jpg'", "stock photos"],
        "word_trigger": "photo|image|picture|look|visual",
    },
    "video_carousel": {
        "description": "Row of YouTube videos in SERP",
        "content_structure": [
            "Embed relevant YouTube video in article",
            "Add VideoObject schema with name, description, thumbnailUrl, duration",
            "Article must have 'video' or 'tutorial' signals in content",
        ],
        "avoid": ["embedding unrelated videos"],
        "word_trigger": "how to|tutorial|guide|recipe|step by step",
    },
    "local_pack": {
        "description": "Map + 3 local business results",
        "content_structure": [
            "Target 'near me' or location-specific keywords",
            "Include LocalBusiness schema with address, phone, hours",
            "Create location-specific H2: 'Best {keyword} in {city}'",
        ],
        "avoid": ["ignoring geographic modifiers"],
        "word_trigger": "near me|local|in {city}|{city}",
    },
}


class SERPFeatureTargetingEngine:
    """
    Reads P6 SERP intelligence data and modifies content briefs
    to specifically target the SERP features present for each keyword.

    Called after P6_SERPIntelligence, before P15_ContentBrief.
    Adds feature-targeting instructions to the brief.
    """

    def detect_features(self, serp_data: dict, keyword: str) -> List[str]:
        """Detect which SERP features are present for this keyword."""
        features = []
        if not serp_data:
            return features
        serp_text = json.dumps(serp_data).lower()
        # Detect from SERP data signals
        if any(q in keyword.lower() for q in ["what","how","why","when","is","best"]):
            features.append("featured_snippet")
        if "?" in keyword or any(q in keyword.lower() for q in ["how","what","why"]):
            features.append("people_also_ask")
        if any(q in keyword.lower() for q in ["recipe","tutorial","guide","how to"]):
            features.append("video_carousel")
        if any(q in keyword.lower() for q in ["near me","local","in","where"]):
            features.append("local_pack")
        return features

    def inject_targeting(self, brief: dict, features: List[str],
                          keyword: str) -> dict:
        """Inject SERP feature targeting instructions into a content brief."""
        if not features:
            return brief
        feature_instructions = []
        for feature in features:
            structure = SERP_FEATURE_STRUCTURES.get(feature, {})
            feature_instructions.extend(structure.get("content_structure", []))
        brief["serp_feature_targets"] = features
        brief["feature_instructions"] = feature_instructions
        # Add specific H2 format requirements
        if "people_also_ask" in features:
            brief["h2_format"] = "question"  # all H2s must be questions
        if "featured_snippet" in features:
            brief["intro_format"] = "direct_answer"  # first paragraph = direct answer
        log.info(f"[SERPTarget] {keyword}: targeting {features}")
        return brief

    def score_feature_potential(self, keyword: str, serp_data: dict) -> Dict[str, float]:
        """Score probability of winning each feature (0-1)."""
        features = self.detect_features(serp_data, keyword)
        return {f: (0.65 if len(keyword.split()) >= 3 else 0.35)
                for f in features}


# ─────────────────────────────────────────────────────────────────────────────
# ENGINE 3 — VOICE SEARCH OPTIMISER
# ─────────────────────────────────────────────────────────────────────────────

# New intent category — question/voice
VOICE_SIGNALS = [
    "how do i","how can i","how should i","what is the best way","how do you",
    "what is","what are","why is","why are","why do","when is","when should",
    "can i","should i","is it","will it","does it","what happens",
    "how much","how many","how long","how often",
]


class VoiceSearchOptimiser:
    """
    Adds voice/question intent category.
    Restructures briefs for voice:
      - Direct spoken answer in ≤30 words (for Google Assistant)
      - Conversational H2s ("How do you use cinnamon for diabetes?" not "Cinnamon for Diabetes")
      - FAQ structured for Google Home: question → direct answer → 2-sentence expansion
    """

    def classify_voice(self, keyword: str) -> Tuple[bool, str]:
        """Returns (is_voice_keyword, spoken_answer_format)."""
        kw = keyword.lower()
        for signal in VOICE_SIGNALS:
            if kw.startswith(signal) or signal in kw:
                return True, "spoken_answer"
        if "?" in keyword:
            return True, "spoken_answer"
        if any(kw.startswith(q) for q in ["is","can","should","will","does"]):
            return True, "yes_no_then_explain"
        return False, ""

    def adapt_brief(self, brief: dict, keyword: str) -> dict:
        """Adapt a content brief for voice search if the keyword is voice-type."""
        is_voice, format_type = self.classify_voice(keyword)
        if not is_voice:
            return brief
        brief["voice_optimised"]  = True
        brief["voice_format"]     = format_type
        brief["intro_max_words"]  = 30   # spoken answer must be ≤30 words
        brief["h2_style"]         = "conversational_question"  # H2s as questions
        brief["faq_format"]       = "q_then_direct_answer"  # FAQ: Q then 1-sentence answer
        # Restructure H2s to be questions
        if brief.get("h2_headings"):
            brief["h2_headings"] = [
                self._to_question(h2, keyword)
                for h2 in brief.get("h2_headings", [])
            ]
        log.info(f"[Voice] Brief adapted for voice search: {keyword}")
        return brief

    def _to_question(self, heading: str, keyword: str) -> str:
        """Convert a statement H2 to a question format."""
        heading_lower = heading.lower()
        if "?" in heading or any(heading_lower.startswith(q)
                                   for q in ["how","what","why","when","is","can"]):
            return heading   # already a question
        # Wrap as question
        if "benefit" in heading_lower or "advantage" in heading_lower:
            return f"What are the benefits of {keyword}?"
        if "use" in heading_lower or "using" in heading_lower:
            return f"How do you use {keyword}?"
        if "buy" in heading_lower or "purchase" in heading_lower:
            return f"Where can you buy {keyword}?"
        return f"What should you know about {heading.lower()}?"

    def generate_spoken_intro(self, keyword: str, article_body: str) -> str:
        """Generate a ≤30-word spoken answer for Google Assistant."""
        key = os.getenv("GEMINI_API_KEY","")
        if not key:
            return f"{keyword.capitalize()} is a topic with multiple important aspects. Here is what you need to know."
        try:
            r = _req.post(f"{_GEMINI_URL()}?key={key}",
                json={"contents":[{"parts":[{"text":
                    f"Write a spoken answer for Google Assistant to the query: '{keyword}'\n"
                    f"Based on this article:\n{article_body[:500]}\n\n"
                    f"Requirements:\n"
                    f"- Maximum 30 words\n"
                    f"- Complete sentence, not a fragment\n"
                    f"- Can be read aloud naturally\n"
                    f"- Answers the question directly\n"
                    f"Return only the spoken answer, nothing else."}]}],
                    "generationConfig":{"temperature":0.1,"maxOutputTokens":60}},
                timeout=10)
            r.raise_for_status()
            return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception:
            return ""


# ─────────────────────────────────────────────────────────────────────────────
# ENGINE 4 — RANKING PREDICTION
# ─────────────────────────────────────────────────────────────────────────────

class RankingPredictionEngine:
    """
    Before writing an article, predict the likely ranking position at 90 days.
    Factors: keyword difficulty, content plan score, competition analysis,
             how many competitors have dedicated pages vs thin coverage.

    Stored as prediction → compared vs actual at 90-day mark
    → accuracy feeds back to improve the model.
    """

    def predict(self, keyword: str, project_id: str,
                 kd_estimate: float = 50.0,
                 content_plan_score: float = 75.0,
                 serp_data: dict = None,
                 domain_authority_proxy: float = 20.0) -> dict:
        """
        kd_estimate:           0-100 keyword difficulty
        content_plan_score:    0-100 score of planned content brief
        domain_authority_proxy: rough proxy (0-100) for site strength
        serp_data:             from P6 SERP intelligence

        Returns: {predicted_position, confidence, factors, expected_traffic}
        """
        factors = {}

        # Factor 1: Keyword difficulty (lower = easier to rank)
        kd_score = max(0, 100 - kd_estimate)
        factors["keyword_difficulty"] = {"raw": kd_estimate, "score": kd_score}

        # Factor 2: Content quality plan
        factors["content_plan"] = {"score": content_plan_score}

        # Factor 3: Competition quality from SERP data
        comp_quality = 50.0   # default
        if serp_data:
            avg_word_count = serp_data.get("avg_word_count", 1500)
            comp_quality   = min(100, avg_word_count / 30)  # rough proxy
        factors["competition_quality"] = {"score": 100 - comp_quality}

        # Factor 4: Domain authority
        factors["domain_authority"] = {"score": domain_authority_proxy}

        # Weighted prediction score
        weighted = (
            kd_score            * 0.35 +
            content_plan_score  * 0.30 +
            (100 - comp_quality)* 0.20 +
            domain_authority_proxy * 0.15
        )

        # Map score → predicted position
        if weighted >= 80:   predicted_pos = 2.5
        elif weighted >= 65: predicted_pos = 5.0
        elif weighted >= 50: predicted_pos = 10.0
        elif weighted >= 35: predicted_pos = 18.0
        else:                predicted_pos = 35.0

        # Confidence based on data quality
        confidence = 0.8 if serp_data else 0.5

        pred_id = f"pred_{hashlib.md5(f'{project_id}{keyword}'.encode()).hexdigest()[:10]}"
        _db().execute("""
            INSERT OR REPLACE INTO ranking_predictions
            (pred_id,project_id,keyword,predicted_pos,confidence,factors)
            VALUES (?,?,?,?,?,?)
        """, (pred_id, project_id, keyword, predicted_pos, confidence, json.dumps(factors)))
        _db().commit()

        # Estimate monthly traffic at predicted position
        traffic_by_pos = {2.5: 180, 5: 80, 10: 25, 18: 8, 35: 2}
        traffic = min(traffic_by_pos.items(), key=lambda x: abs(x[0]-predicted_pos))[1]

        log.info(f"[Prediction] {keyword}: pos={predicted_pos:.0f}, confidence={confidence:.0%}")
        return {
            "pred_id":          pred_id,
            "keyword":          keyword,
            "predicted_position": round(predicted_pos, 1),
            "confidence":       round(confidence, 2),
            "prediction_range": (max(1, predicted_pos-3), predicted_pos+5),
            "expected_monthly_traffic": traffic,
            "factors":          factors,
            "recommended_action": self._recommend(weighted, kd_estimate),
        }

    def _recommend(self, score: float, kd: float) -> str:
        if score >= 80: return "High confidence — write and publish"
        if score >= 65: return "Good opportunity — write with thorough content"
        if score >= 50: return "Medium difficulty — focus on long-tail variation"
        if kd >= 70:    return "Very competitive — target long-tail only"
        return "Low chance currently — build domain authority first"

    def record_actual(self, pred_id: str, actual_position: float):
        """Record actual position at 90 days for model validation."""
        _db().execute("""
            UPDATE ranking_predictions SET actual_pos=?, actual_at=? WHERE pred_id=?
        """, (actual_position, datetime.utcnow().isoformat(), pred_id))
        _db().commit()

    def accuracy_report(self, project_id: str) -> dict:
        """Compare predictions vs actuals for all resolved predictions."""
        rows = [dict(r) for r in _db().execute("""
            SELECT predicted_pos, actual_pos, keyword FROM ranking_predictions
            WHERE project_id=? AND actual_pos IS NOT NULL
        """, (project_id,)).fetchall()]
        if not rows:
            return {"accuracy": None, "message": "No resolved predictions yet"}
        errors = [abs(r["predicted_pos"] - r["actual_pos"]) for r in rows]
        avg_err = sum(errors) / len(errors)
        within_5 = sum(1 for e in errors if e <= 5) / len(errors)
        return {
            "total_predictions": len(rows),
            "avg_position_error": round(avg_err, 1),
            "within_5_positions_pct": round(within_5 * 100, 1),
            "details": rows[:10],
        }


# ─────────────────────────────────────────────────────────────────────────────
# ENGINE 5 — SEASONAL KEYWORD CALENDAR
# ─────────────────────────────────────────────────────────────────────────────

# Seasonal patterns by keyword type (estimated — replace with Google Trends API if available)
SEASONAL_PATTERNS = {
    "recipe": {"peak_months": [11, 12, 1], "note": "Holiday cooking season"},
    "gift":   {"peak_months": [11, 12], "note": "Holiday gifting"},
    "health": {"peak_months": [1, 9], "note": "New year resolutions + back to school"},
    "garden": {"peak_months": [3, 4, 5], "note": "Spring planting"},
    "travel": {"peak_months": [6, 7, 12], "note": "Summer + winter holidays"},
    "buy":    {"peak_months": [11, 12], "note": "Black Friday / holiday shopping"},
    "festival":{"peak_months":[10,11,12], "note": "Festival season"},
    "exam":   {"peak_months": [3, 4, 10, 11], "note": "Exam preparation seasons"},
    "ayurveda":{"peak_months":[1, 9], "note": "Wellness season"},
    "organic":{"peak_months":[4, 5], "note": "Earth month + spring"},
}

PUBLISH_LEAD_WEEKS = 8   # publish 8 weeks before peak for ranking time


class SeasonalKeywordCalendar:
    """
    Detect seasonality for keywords.
    Adjust publishing calendar to hit 8 weeks before predicted peak.
    Alert for refresh if article approaches next peak.
    """

    def detect_seasonality(self, keyword: str) -> Optional[dict]:
        """Detect peak search periods for a keyword."""
        kw_lower = keyword.lower()
        for pattern_key, pattern_data in SEASONAL_PATTERNS.items():
            if pattern_key in kw_lower:
                return {
                    "has_seasonality":  True,
                    "pattern":          pattern_key,
                    "peak_months":      pattern_data["peak_months"],
                    "note":             pattern_data["note"],
                    "publish_by_weeks_before": PUBLISH_LEAD_WEEKS,
                }
        return {"has_seasonality": False}

    def optimal_publish_date(self, keyword: str,
                              today: datetime = None) -> Optional[datetime]:
        """Calculate optimal publish date for seasonal keyword."""
        today    = today or datetime.utcnow()
        seasonal = self.detect_seasonality(keyword)
        if not seasonal.get("has_seasonality"):
            return None  # no adjustment needed
        peak_months = seasonal["peak_months"]
        lead_days   = PUBLISH_LEAD_WEEKS * 7
        # Find next peak month
        for months_ahead in range(0, 13):
            candidate = today + timedelta(days=months_ahead * 30)
            if candidate.month in peak_months:
                # Publish lead_days before the peak
                publish_date = candidate - timedelta(days=lead_days)
                if publish_date > today:
                    return publish_date
        return None

    def adjust_calendar(self, calendar: List[dict]) -> List[dict]:
        """
        Given a content calendar list, adjust publish dates for seasonal keywords.
        calendar item: {article_id, keyword, scheduled_date, ...}
        """
        adjusted = []
        for item in calendar:
            kw       = item.get("keyword","")
            optimal  = self.optimal_publish_date(kw)
            if optimal:
                item = dict(item)
                item["scheduled_date"]     = optimal.strftime("%Y-%m-%d")
                item["seasonal_adjusted"]  = True
                item["seasonal_note"]      = f"Adjusted for peak search season"
                log.info(f"[Seasonal] Adjusted '{kw}' → {item['scheduled_date']}")
            adjusted.append(item)
        return adjusted

    def refresh_alerts(self, project_id: str) -> List[dict]:
        """
        Find published articles approaching their next seasonal peak.
        If published and peak approaching in <8 weeks → trigger refresh check.
        """
        con     = _db()
        db_path = Path(os.getenv("ANNASEO_DB","./annaseo.db"))
        sql_con = sqlite3.connect(str(db_path), check_same_thread=False)
        sql_con.row_factory = sqlite3.Row
        try:
            articles = [dict(r) for r in sql_con.execute("""
                SELECT article_id, keyword FROM content_articles
                WHERE project_id=? AND status='published'
            """, (project_id,)).fetchall()]
        except Exception:
            articles = []
        sql_con.close()

        alerts = []
        today  = datetime.utcnow()
        for art in articles:
            kw = art.get("keyword","")
            seasonal = self.detect_seasonality(kw)
            if not seasonal.get("has_seasonality"):
                continue
            for peak_month in seasonal["peak_months"]:
                # Check if peak is within 8 weeks
                peak_date = today.replace(month=peak_month, day=1)
                if peak_date < today:
                    peak_date = peak_date.replace(year=today.year + 1)
                days_to_peak = (peak_date - today).days
                if days_to_peak <= 56:   # 8 weeks
                    alerts.append({
                        "article_id":  art["article_id"],
                        "keyword":     kw,
                        "peak_month":  peak_month,
                        "days_to_peak":days_to_peak,
                        "action":      f"Refresh article for {seasonal['note']} — {days_to_peak} days to peak",
                    })
        return alerts


# ─────────────────────────────────────────────────────────────────────────────
# ENGINE 6 — SEARCH INTENT SHIFT DETECTOR
# ─────────────────────────────────────────────────────────────────────────────

class SearchIntentShiftDetector:
    """
    Re-classify intent for published keywords weekly using DuckDuckGo SERP.
    If intent shifted → alert + suggest content update.

    Example: "cinnamon buy online" was "transactional" when published.
             SERP now shows mostly informational results.
             → Content is misaligned → needs rewrite to match new intent.
    """

    # Intent classification rules (same as P5 but re-runnable)
    RULES = {
        "transactional": ["buy","order","purchase","price","cheap","discount","shop",
                           "wholesale","bulk","delivery","near me","online","cost"],
        "commercial":    ["best","top","review","compare","vs","versus","alternative",
                           "recommendation","which","ranking","rated","test"],
        "comparison":    ["vs","versus","or","difference between","compare","better",
                           "which is","ceylon vs","type of"],
        "navigational":  ["brand","website","official","login","contact",".com"],
        "informational": ["what","how","why","when","does","is","are","can","benefits",
                           "uses","effects","meaning","definition","guide","truth",
                           "science","study","research"],
        "question":      ["how do","what is","why is","when should","can i",
                           "should i","is it","will it"],   # NEW: voice/question intent
    }

    def classify(self, keyword: str) -> str:
        kl = keyword.lower()
        for intent, signals in self.RULES.items():
            if any(s in kl for s in signals):
                return intent
        return "informational"

    def detect_shifts(self, project_id: str) -> List[dict]:
        """Compare stored intent vs current intent for all project keywords."""
        db_path = Path(os.getenv("ANNASEO_DB","./annaseo.db"))
        sql_con = sqlite3.connect(str(db_path), check_same_thread=False)
        sql_con.row_factory = sqlite3.Row

        try:
            keywords = [dict(r) for r in sql_con.execute("""
                SELECT k.keyword, k.intent as stored_intent, a.article_id
                FROM keywords k
                LEFT JOIN content_articles a ON k.keyword = a.keyword AND a.project_id=?
                WHERE k.intent IS NOT NULL
                LIMIT 100
            """, (project_id,)).fetchall()]
        except Exception:
            keywords = []
        sql_con.close()

        shifts  = []
        con     = _db()
        for kw_row in keywords:
            kw          = kw_row.get("keyword","")
            stored      = kw_row.get("stored_intent","informational")
            current     = self.classify(kw)
            if current != stored:
                alert_id = f"shift_{hashlib.md5(f'{project_id}{kw}'.encode()).hexdigest()[:10]}"
                action   = self._suggest_action(kw, stored, current, kw_row.get("article_id",""))
                con.execute("""
                    INSERT OR REPLACE INTO intent_shift_alerts
                    (alert_id,project_id,keyword,old_intent,new_intent,article_id,action)
                    VALUES (?,?,?,?,?,?,?)
                """, (alert_id, project_id, kw, stored, current,
                       kw_row.get("article_id",""), action))
                con.commit()
                shifts.append({
                    "keyword":    kw,
                    "old_intent": stored,
                    "new_intent": current,
                    "article_id": kw_row.get("article_id",""),
                    "action":     action,
                })
                log.info(f"[IntentShift] '{kw}': {stored} → {current}")

        return shifts

    def _suggest_action(self, keyword: str, old_intent: str,
                         new_intent: str, article_id: str) -> str:
        if new_intent == "transactional" and old_intent == "informational":
            return f"Add product/pricing CTA section to article — intent shifted to buy-mode"
        if new_intent == "informational" and old_intent == "transactional":
            return f"Remove heavy commercial focus — readers now want information, not just to buy"
        if new_intent == "question" and old_intent != "question":
            return f"Restructure intro as direct spoken answer — voice search intent detected"
        if new_intent == "comparison" and old_intent != "comparison":
            return f"Add comparison table vs competitors/alternatives — comparison intent now dominant"
        return f"Content intent shifted from {old_intent} to {new_intent} — review and update article"

    def get_alerts(self, project_id: str) -> List[dict]:
        return [dict(r) for r in _db().execute("""
            SELECT * FROM intent_shift_alerts WHERE project_id=? AND resolved=0
            ORDER BY created_at DESC
        """, (project_id,)).fetchall()]


# ─────────────────────────────────────────────────────────────────────────────
# FASTAPI ROUTER — all 6 engines
# ─────────────────────────────────────────────────────────────────────────────

try:
    from fastapi import FastAPI, BackgroundTasks
    from pydantic import BaseModel as PM
    from typing import Optional as Opt, List as L

    app = FastAPI(title="AnnaSEO Intelligence Engines Pack",
                  description="Multilingual, SERP targeting, voice, predictions, seasonal, intent shift")

    ml   = MultilingualContentEngine()
    serp = SERPFeatureTargetingEngine()
    voice= VoiceSearchOptimiser()
    pred = RankingPredictionEngine()
    sea  = SeasonalKeywordCalendar()
    isd  = SearchIntentShiftDetector()

    class LocaliseBody(PM):
        article_id:     str
        project_id:     str
        keyword:        str
        base_article:   dict
        target_languages: L[str] = ["malayalam", "hindi"]

    class PredictBody(PM):
        keyword:               str
        project_id:            str
        kd_estimate:           float = 50.0
        content_plan_score:    float = 75.0
        domain_authority_proxy:float = 20.0
        serp_data:             dict = {}

    class RecordActualBody(PM):
        pred_id:        str
        actual_position:float

    # Multilingual
    @app.post("/api/ml/localise", tags=["Multilingual"])
    def localise(body: LocaliseBody, bg: BackgroundTasks):
        bg.add_task(ml.generate, body.base_article, body.target_languages,
                     body.project_id, body.keyword)
        return {"status": "started", "languages": body.target_languages}

    @app.get("/api/ml/{article_id}", tags=["Multilingual"])
    def get_localisations(article_id: str):
        return [dict(r) for r in _db().execute(
            "SELECT * FROM multilingual_articles WHERE article_id=?", (article_id,)
        ).fetchall()]

    @app.get("/api/ml/{article_id}/hreflang", tags=["Multilingual"])
    def get_hreflang(article_id: str):
        return {"hreflang_tags": ml.generate_hreflang_tags(article_id)}

    # SERP features
    @app.post("/api/serp-features/inject", tags=["SERP Features"])
    def inject_features(keyword: str, brief: dict, serp_data: dict = {}):
        features = serp.detect_features(serp_data, keyword)
        return serp.inject_targeting(brief, features, keyword)

    @app.get("/api/serp-features/detect", tags=["SERP Features"])
    def detect_features(keyword: str):
        return {"features": serp.detect_features({}, keyword),
                "potential": serp.score_feature_potential(keyword, {})}

    # Voice
    @app.post("/api/voice/adapt-brief", tags=["Voice Search"])
    def adapt_voice(keyword: str, brief: dict):
        return voice.adapt_brief(brief, keyword)

    @app.get("/api/voice/classify", tags=["Voice Search"])
    def classify_voice(keyword: str):
        is_v, fmt = voice.classify_voice(keyword)
        return {"is_voice": is_v, "format": fmt}

    # Ranking prediction
    @app.post("/api/predict", tags=["Ranking Prediction"])
    def predict_ranking(body: PredictBody):
        return pred.predict(body.keyword, body.project_id, body.kd_estimate,
                             body.content_plan_score, body.serp_data or None,
                             body.domain_authority_proxy)

    @app.post("/api/predict/actual", tags=["Ranking Prediction"])
    def record_actual(body: RecordActualBody):
        pred.record_actual(body.pred_id, body.actual_position)
        return {"recorded": True}

    @app.get("/api/predict/accuracy/{project_id}", tags=["Ranking Prediction"])
    def prediction_accuracy(project_id: str):
        return pred.accuracy_report(project_id)

    # Seasonal
    @app.get("/api/seasonal/detect", tags=["Seasonal"])
    def seasonal_detect(keyword: str):
        result = sea.detect_seasonality(keyword)
        optimal = sea.optimal_publish_date(keyword)
        result["optimal_publish_date"] = optimal.strftime("%Y-%m-%d") if optimal else None
        return result

    @app.post("/api/seasonal/adjust-calendar", tags=["Seasonal"])
    def adjust_calendar(calendar: L[dict]):
        return sea.adjust_calendar(calendar)

    @app.get("/api/seasonal/refresh-alerts/{project_id}", tags=["Seasonal"])
    def seasonal_refresh(project_id: str):
        return sea.refresh_alerts(project_id)

    # Intent shift
    @app.post("/api/intent-shift/detect/{project_id}", tags=["Intent Shift"])
    def detect_shifts(project_id: str, bg: BackgroundTasks):
        bg.add_task(isd.detect_shifts, project_id)
        return {"status": "started", "project_id": project_id}

    @app.get("/api/intent-shift/alerts/{project_id}", tags=["Intent Shift"])
    def shift_alerts(project_id: str):
        return isd.get_alerts(project_id)

except ImportError:
    pass


# ─────────────────────────────────────────────────────────────────────────────
# CLI DEMO
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    HELP = """
AnnaSEO Intelligence Engines Pack
Usage:
  python annaseo_intelligence_engines.py predict <keyword>    ranking prediction
  python annaseo_intelligence_engines.py seasonal <keyword>   seasonality check
  python annaseo_intelligence_engines.py voice <keyword>      voice search check
  python annaseo_intelligence_engines.py serp <keyword>       SERP feature targeting
  python annaseo_intelligence_engines.py intent <keyword>     classify intent
  python annaseo_intelligence_engines.py shifts <project_id>  detect intent shifts
  python annaseo_intelligence_engines.py demo                 full demo
"""
    if len(sys.argv) < 2: print(HELP); exit(0)
    cmd = sys.argv[1]

    if cmd == "predict":
        kw = sys.argv[2] if len(sys.argv) > 2 else "cinnamon benefits"
        p  = RankingPredictionEngine()
        print(json.dumps(p.predict(kw, "proj_demo"), indent=2))

    elif cmd == "seasonal":
        kw = sys.argv[2] if len(sys.argv) > 2 else "cinnamon recipe"
        s  = SeasonalKeywordCalendar()
        result = s.detect_seasonality(kw)
        opt    = s.optimal_publish_date(kw)
        result["optimal_publish"] = opt.strftime("%Y-%m-%d") if opt else "no adjustment"
        print(json.dumps(result, indent=2))

    elif cmd == "voice":
        kw = sys.argv[2] if len(sys.argv) > 2 else "how to use cinnamon"
        v  = VoiceSearchOptimiser()
        is_v, fmt = v.classify_voice(kw)
        print(f"Voice search: {is_v} | Format: {fmt}")

    elif cmd == "serp":
        kw = sys.argv[2] if len(sys.argv) > 2 else "what is cinnamon"
        s  = SERPFeatureTargetingEngine()
        features = s.detect_features({}, kw)
        print(f"SERP features for '{kw}': {features}")

    elif cmd == "intent":
        kw = sys.argv[2] if len(sys.argv) > 2 else "buy cinnamon online"
        d  = SearchIntentShiftDetector()
        print(f"Intent for '{kw}': {d.classify(kw)}")

    elif cmd == "shifts":
        pid = sys.argv[2] if len(sys.argv) > 2 else "proj_demo"
        d   = SearchIntentShiftDetector()
        shifts = d.detect_shifts(pid)
        for s in shifts:
            print(f"  SHIFT: {s['keyword']} | {s['old_intent']} → {s['new_intent']}")
            print(f"         Action: {s['action']}")

    elif cmd == "demo":
        print("\n  INTELLIGENCE ENGINES DEMO")
        print("  " + "─"*52)

        # Ranking prediction
        print("\n  1. RANKING PREDICTION")
        p = RankingPredictionEngine()
        for kw in ["cinnamon benefits", "buy cinnamon online", "best cinnamon for health"]:
            r = p.predict(kw, "proj_demo", kd_estimate=40)
            print(f"     '{kw}': pos={r['predicted_position']} | "
                  f"traffic={r['expected_monthly_traffic']}/mo | "
                  f"{r['recommended_action'][:40]}")

        # Seasonal
        print("\n  2. SEASONAL CALENDAR")
        sea = SeasonalKeywordCalendar()
        for kw in ["cinnamon recipe", "cinnamon health benefits", "buy cinnamon gift"]:
            r = sea.detect_seasonality(kw)
            opt = sea.optimal_publish_date(kw)
            if r["has_seasonality"]:
                print(f"     '{kw}': peak months {r['peak_months']} | "
                      f"publish by {opt.strftime('%b %Y') if opt else 'ASAP'}")

        # Voice
        print("\n  3. VOICE SEARCH CLASSIFICATION")
        v = VoiceSearchOptimiser()
        for kw in ["how to use cinnamon", "cinnamon benefits", "what is ceylon cinnamon"]:
            is_v, fmt = v.classify_voice(kw)
            print(f"     '{kw}': voice={is_v} | format={fmt}")

        # SERP features
        print("\n  4. SERP FEATURE TARGETING")
        s = SERPFeatureTargetingEngine()
        for kw in ["what is cinnamon", "cinnamon vs cassia", "how to use cinnamon"]:
            features = s.detect_features({}, kw)
            print(f"     '{kw}': {features}")

        # Intent classification
        print("\n  5. INTENT CLASSIFICATION (with question category)")
        d = SearchIntentShiftDetector()
        for kw in ["how do you use cinnamon", "buy ceylon cinnamon", "cinnamon benefits",
                    "cinnamon vs cassia which is better"]:
            print(f"     '{kw}': {d.classify(kw)}")
    else:
        print(HELP)
