"""
================================================================================
ANNASEO — AI BRAIN MODULE
================================================================================
Central AI processing layer for AnnaSEO keyword intelligence pipeline.

Architecture:
  PRIMARY:   Groq Llama-3.3-70b (free, fast) — bulk keyword analysis
  FALLBACK:  Ollama/DeepSeek (local, free)    — offline / Groq unavailable  
  PRECISION: Claude Sonnet (pay-per-use)       — quality gate, <1000 tokens

Each engine phase calls AnnaBrain to think, score, and classify.
Console output is streamed back for live review with quality gates.

Usage:
  from annaseo_ai_brain import AnnaBrain
  brain = AnnaBrain()
  intents = brain.classify_intents(["buy black pepper", "black pepper benefits"])
  pillars = brain.identify_pillars(keywords, seed="black pepper")
================================================================================
"""

from __future__ import annotations
import os, json, time, logging, re
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger("annaseo.brain")

# Import central AI config & router
try:
    import sys as _sys, os as _os
    _sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), '..', 'core'))
    from ai_config import AICfg, AIRouter
    _central_ai = True
except ImportError:
    _central_ai = False
    log.warning("[Brain] Central AIRouter not available — using inline fallback")


# ─────────────────────────────────────────────────────────────────────────────
# CONFIG — mirrors central config, kept for backward compatibility
# ─────────────────────────────────────────────────────────────────────────────

class BrainCfg:
    GROQ_KEY    = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL  = os.getenv("GROQ_MODEL",   "llama-3.1-8b-instant")
    OLLAMA_URL  = os.getenv("OLLAMA_URL",   "http://172.235.16.165:11434")
    OLLAMA_MODEL= os.getenv("OLLAMA_MODEL", "deepseek-r1:7b")
    CLAUDE_KEY  = os.getenv("ANTHROPIC_API_KEY", "")
    CLAUDE_MODEL= os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
    CLAUDE_MAX_TOKENS = 1000


# ─────────────────────────────────────────────────────────────────────────────
# PHASE RESULT — structure for console display
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PhaseResult:
    phase:       str
    title:       str
    status:      str    = "running"   # running | complete | error | needs_review
    summary:     str    = ""
    data:        Any    = field(default_factory=dict)
    quality_score: float = 0.0
    ai_model:    str    = ""
    tokens_used: int    = 0
    duration_s:  float  = 0.0
    console_lines: List[str] = field(default_factory=list)

    def add_line(self, text: str):
        self.console_lines.append(text)
        log.info(f"[{self.phase}] {text}")

    def to_dict(self) -> dict:
        return {
            "phase": self.phase, "title": self.title,
            "status": self.status, "summary": self.summary,
            "quality_score": self.quality_score, "ai_model": self.ai_model,
            "tokens_used": self.tokens_used, "duration_s": round(self.duration_s, 2),
            "console_lines": self.console_lines,
        }


# ─────────────────────────────────────────────────────────────────────────────
# AI BRAIN
# ─────────────────────────────────────────────────────────────────────────────

class AnnaBrain:
    """
    AI Brain for AnnaSEO — routes prompts to the right AI provider.

    Routing strategy:
      - Groq (free, 6000 TPM) → bulk analysis (intent, clusters, scoring)
      - Ollama/DeepSeek (local) → fallback when Groq unavailable
      - Claude (cheap verification) → quality gate checks only, ≤1000 tokens
    """

    def __init__(self):
        self._groq_client = None
        self._last_groq_call = 0.0

    # ── Low-level callers ─────────────────────────────────────────────────────

    def _call_groq(self, prompt: str, system: str = "You are an expert SEO strategist.",
                   temperature: float = 0.2) -> Tuple[str, int]:
        """Call Groq API. Returns (text, tokens)."""
        if not BrainCfg.GROQ_KEY:
            return self._call_ollama(prompt, system, temperature), 0
        try:
            from groq import Groq
            if self._groq_client is None:
                self._groq_client = Groq(api_key=BrainCfg.GROQ_KEY)
            # Rate limit: Groq free tier ~30 req/min
            elapsed = time.time() - self._last_groq_call
            if elapsed < 2.0:
                time.sleep(2.0 - elapsed)
            resp = self._groq_client.chat.completions.create(
                model=BrainCfg.GROQ_MODEL,
                messages=[{"role": "system", "content": system},
                          {"role": "user",   "content": prompt}],
                temperature=temperature,
                max_tokens=4096,
            )
            self._last_groq_call = time.time()
            text   = resp.choices[0].message.content.strip()
            tokens = getattr(resp.usage, "total_tokens", 0)
            return text, tokens
        except Exception as e:
            log.warning(f"[Brain] Groq error: {e} — falling back to Ollama")
            return self._call_ollama(prompt, system, temperature), 0

    def _call_ollama(self, prompt: str, system: str = "You are an SEO expert.",
                     temperature: float = 0.2) -> str:
        """Call Ollama/DeepSeek locally. Returns text."""
        import requests as req

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

        try:
            combined = f"{system}\n\n{prompt}" if system else prompt
            r = req.post(f"{BrainCfg.OLLAMA_URL}/api/generate", json={
                "model": BrainCfg.OLLAMA_MODEL, "stream": False,
                "options": {"temperature": temperature},
                "prompt": combined
            }, timeout=30)
            r.raise_for_status()
            data = r.json()
            text = data.get("response", "").strip()
            return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        except Exception as e:
            log.warning(f"[Brain] Ollama error: {e}")
            return ""

    def _call_claude(self, prompt: str, system: str,
                     max_tokens: int = None) -> Tuple[str, int]:
        """Call Claude for quality verification — keep tokens under 1000."""
        mt = min(max_tokens or BrainCfg.CLAUDE_MAX_TOKENS, BrainCfg.CLAUDE_MAX_TOKENS)
        if not BrainCfg.CLAUDE_KEY:
            text, _ = self._call_groq(prompt, system)
            return text, 0
        try:
            import anthropic
            c = anthropic.Anthropic(api_key=BrainCfg.CLAUDE_KEY)
            r = c.messages.create(
                model=BrainCfg.CLAUDE_MODEL, max_tokens=mt,
                system=system, messages=[{"role":"user","content":prompt}]
            )
            tokens = r.usage.input_tokens + r.usage.output_tokens
            return r.content[0].text.strip(), tokens
        except Exception as e:
            log.warning(f"[Brain] Claude error: {e}")
            text, tk = self._call_groq(prompt, system)
            return text, tk

    def think(self, prompt: str, system: str = "You are an expert SEO strategist.",
               temperature: float = 0.2, use_claude: bool = False) -> Tuple[str, int]:
        """
        Main think() method. Routes to best available AI via central AIRouter.
        use_claude=True for quality gates (max 1000 tokens, higher accuracy).
        """
        if use_claude and BrainCfg.CLAUDE_KEY:
            return self._call_claude(prompt, system)
        if _central_ai:
            text, tokens = AIRouter.call_with_tokens(prompt, system, temperature)
            return text, tokens
        return self._call_groq(prompt, system, temperature)

    def parse_json(self, text: str) -> Any:
        """Extract and parse JSON from AI response."""
        try:
            # Try direct parse
            return json.loads(text)
        except:
            pass
        # Extract JSON block
        for pattern in [r"```json\s*([\s\S]+?)```", r"```\s*([\s\S]+?)```",
                        r"\{[\s\S]*\}", r"\[[\s\S]*\]"]:
            m = re.search(pattern, text, re.DOTALL)
            if m:
                try:
                    candidate = m.group(0) if pattern in [r"\{[\s\S]*\}", r"\[[\s\S]*\]"] else m.group(1)
                    return json.loads(candidate.strip())
                except:
                    continue
        return {}

    # ── High-level keyword intelligence methods ───────────────────────────────

    def classify_intents(self, keywords: List[str], seed: str = "") -> Dict[str, str]:
        """
        Classify search intent for a batch of keywords using AI.
        Returns: {keyword: intent} where intent ∈ {transactional, informational,
                  commercial, comparison, navigational}
        Uses rule-based classification first, then AI for ambiguous cases.
        """
        from ruflo_20phase_engine import P5_IntentClassification
        p5 = P5_IntentClassification()
        return {kw: p5._classify(kw) for kw in keywords}

    def identify_pillars(self, keywords: List[str], seed: str,
                          n_pillars: int = 5) -> List[Dict]:
        """
        Use AI to identify pillar keywords from a universe.
        Returns list of pillar dicts: [{keyword, pillar_title, reason, cluster_theme}]
        """
        if not keywords:
            return []

        sample = keywords[:50]  # Keep prompt small
        prompt = f"""You are an SEO strategist. Identify {n_pillars} PILLAR KEYWORDS from this list.

Seed keyword: {seed}
Keywords: {json.dumps(sample, indent=2)}

A PILLAR KEYWORD:
- Has the highest monthly search volume (broadest head term)
- Is the primary topic of a cluster (other keywords become supporting content)
- Targets the product/category page, not a blog post
- Example: "black pepper" is pillar; "black pepper health benefits" is cluster topic

Return JSON array:
[
  {{
    "keyword": "exact keyword from the list",
    "pillar_title": "SEO-optimised page title for the pillar page",
    "cluster_theme": "what cluster does this anchor (e.g. 'health & wellness')",
    "reason": "why this is the pillar (1 sentence)"
  }}
]"""
        text, tokens = self.think(prompt)
        result = self.parse_json(text)
        if isinstance(result, list):
            return result[:n_pillars]
        return []

    def generate_keyword_ideas(self, seed: str, n: int = 50,
                                industry: str = "food & spices") -> List[str]:
        """
        Generate keyword ideas for a seed using AI.
        Returns list of keyword strings.
        """
        prompt = f"""Generate {n} SEO keyword ideas for: "{seed}"
Industry: {industry}

Include:
- Informational: "what is {seed}", "how to use {seed}", "{seed} benefits"
- Transactional: "buy {seed}", "{seed} price", "{seed} wholesale"
- Comparison: "{seed} vs [competitor]", "best {seed} brand"
- Commercial: "best {seed}", "top {seed} suppliers"
- Long-tail: "{seed} for [use case]", "{seed} [location/certification]"

Return ONLY a JSON array of keyword strings. No explanation."""
        text, _ = self.think(prompt)
        result  = self.parse_json(text)
        if isinstance(result, list):
            return [str(k).lower().strip() for k in result if k][:n]
        # Fallback: extract lines
        lines = [l.strip(' ",-') for l in text.split("\n") if l.strip()]
        return [l.lower() for l in lines if len(l) > 3][:n]

    def score_keyword_opportunity(self, keyword: str, volume: int,
                                   difficulty: int, intent: str,
                                   seed: str = "") -> Dict:
        """
        AI-enhanced opportunity scoring for a single keyword.
        Returns: {score, tag, reason, content_type, priority}
        """
        # Use Claude for precise single-keyword scoring (under 1000 tokens)
        prompt = f"""Score SEO opportunity for this keyword:

Keyword: "{keyword}"
Seed: "{seed}"
Monthly volume: {volume}
Keyword difficulty: {difficulty}/100
Intent: {intent}

Score from 0-100. Consider: volume vs difficulty ratio, intent value, relevance.
Return ONLY JSON:
{{"score": 85, "tag": "quick_win", "reason": "1 sentence", "content_type": "blog|product|faq|pillar", "priority": "high|medium|low"}}"""
        text, tokens = self.think(prompt, use_claude=True)
        result = self.parse_json(text)
        if isinstance(result, dict) and "score" in result:
            return result
        # Fallback to formula
        ease  = max(0, 100 - difficulty) / 100
        score = round(volume * ease * 0.1, 1)
        return {"score": min(100, score), "tag": "standard",
                "reason": "Formula-based score", "content_type": "blog",
                "priority": "medium"}

    def validate_pillar_cluster_structure(self, pillars: Dict, seed: str) -> Dict:
        """
        Use Claude to validate pillar-cluster structure quality.
        Quality gate: ≤1000 tokens, high precision.
        Returns: {valid: bool, issues: [], score: int, suggestions: []}
        """
        prompt = f"""Review this pillar-cluster SEO structure for "{seed}":

{json.dumps(pillars, indent=2)[:1500]}

Check:
1. Each pillar is a broad head term (not too specific)
2. Clusters properly support their pillar
3. No cannibalization between pillars
4. Good topic coverage

Return JSON: {{"valid": true, "score": 85, "issues": [], "suggestions": []}}"""
        text, tokens = self.think(prompt, use_claude=True)
        result = self.parse_json(text)
        if isinstance(result, dict) and "valid" in result:
            result["tokens_used"] = tokens
            return result
        return {"valid": True, "score": 70, "issues": [], "suggestions": []}

    def summarize_universe(self, keywords: List[str], seed: str,
                            intent_map: Dict[str, str]) -> str:
        """
        Generate a brief summary of the keyword universe for console display.
        Max 200 words. Uses Groq (fast).
        """
        counts = {}
        for intent in intent_map.values():
            counts[intent] = counts.get(intent, 0) + 1

        prompt = f"""Summarize this keyword universe in 3 bullet points (max 100 words total).

Seed: {seed}
Total keywords: {len(keywords)}
Intent distribution: {json.dumps(counts)}
Top keywords: {keywords[:10]}

Format: 3 bullet points starting with •. No header. Be specific and actionable."""
        text, _ = self.think(prompt)
        return text if text else f"• {len(keywords)} keywords found for '{seed}'\n• Intents: {', '.join(f'{v} {k}' for k,v in counts.items())}"


# ─────────────────────────────────────────────────────────────────────────────
# PHASE CONSOLE RUNNER — runs a phase and displays results with quality gate
# ─────────────────────────────────────────────────────────────────────────────

class PhaseRunner:
    """
    Runs a pipeline phase, captures console output, and enforces quality gates.
    Sends events to SSE stream so frontend can display results live.
    """

    def __init__(self, brain: AnnaBrain = None):
        self.brain = brain or AnnaBrain()

    def run_with_review(self, phase_fn, phase_name: str, phase_title: str,
                         *args, **kwargs) -> PhaseResult:
        """
        Run a phase function, measure quality, and return structured result.
        The caller is responsible for the 15s wait and user confirmation via SSE.
        """
        result = PhaseResult(phase=phase_name, title=phase_title)
        t0 = time.time()

        try:
            result.add_line(f"Starting {phase_title}...")
            data = phase_fn(*args, **kwargs)
            result.data   = data
            result.status = "complete"
            result.add_line(f"Completed in {time.time()-t0:.1f}s")

            # Auto quality check based on output size
            if isinstance(data, list):
                result.quality_score = min(100, len(data) * 2)
                result.add_line(f"Output: {len(data)} items")
            elif isinstance(data, dict):
                result.quality_score = min(100, len(data) * 5)
                result.add_line(f"Output: {len(data)} entries")
            else:
                result.quality_score = 70

            # Flag for review if quality is low
            if result.quality_score < 30:
                result.status = "needs_review"
                result.add_line("⚠ Quality below threshold — review recommended")

        except Exception as e:
            result.status = "error"
            result.add_line(f"Error: {e}")
            log.error(f"[PhaseRunner] {phase_name}: {e}", exc_info=True)

        result.duration_s = time.time() - t0
        return result


# ─────────────────────────────────────────────────────────────────────────────
# CONVENIENCE SINGLETON
# ─────────────────────────────────────────────────────────────────────────────

_brain_instance: Optional[AnnaBrain] = None

def get_brain() -> AnnaBrain:
    """Get or create the global AnnaBrain instance."""
    global _brain_instance
    if _brain_instance is None:
        _brain_instance = AnnaBrain()
    return _brain_instance
