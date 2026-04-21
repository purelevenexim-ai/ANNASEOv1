"""Canonical v2 routing schema — single source of truth for pipeline step routing.

The real system uses a 3-slot fallback chain per step (first → second → third),
NOT a single provider+model pair. Each slot is a provider ID string.

Canonical steps (7 AI-routed only):
  research, structure, verify, links, references, draft, recovery

Step 7 (Validate & Score) is deterministic/local — excluded from routing.
Legacy fields (review, issues, humanize, redevelop, score, quality_loop)
are handled by the adapter layer, NOT stored in v2 templates.
"""

from typing import Dict, Literal, Optional, Set
from pydantic import BaseModel, Field, validator


# --- Canonical step names (ONLY these exist in v2) ---
CANONICAL_STEPS: Set[str] = {
    "research",
    "structure",
    "verify",
    "links",
    "references",
    "draft",
    "recovery",
    "humanize",
    "quality_loop",
    "redevelop",
}


class StepConfig(BaseModel):
    """3-slot priority chain for a single pipeline step.
    Each slot is a provider ID: groq, ollama, or_claude, skip, etc."""
    first:  str
    second: str = "skip"
    third:  str = "skip"

    class Config:
        extra = "forbid"


class RoutingTemplate(BaseModel):
    """Canonical v2 routing template.

    Partial templates are valid — budget/free presets may only
    cover 2-4 steps; missing steps fall back to pipeline defaults.
    """
    version: Literal[2] = 2
    name:    str
    steps:   Dict[str, StepConfig] = Field(default_factory=dict)

    description: Optional[str] = None
    system:      bool = False

    class Config:
        extra = "forbid"

    @validator("steps")
    def validate_step_keys(cls, v):
        invalid = set(v.keys()) - CANONICAL_STEPS
        if invalid:
            raise ValueError(
                f"Invalid step keys: {invalid}. "
                f"Valid canonical steps: {sorted(CANONICAL_STEPS)}"
            )
        return v


# --- Editorial Intelligence State ---
class ContentState(BaseModel):
    """
    Tracks the state of content generation to ensure continuity and avoid repetition.
    """
    used_anecdotes: Set[str] = Field(default_factory=set, description="Set of hashes of anecdotes/stories already used.")
    used_statistics: Set[str] = Field(default_factory=set, description="Set of hashes of specific statistics/data points already used.")
    keyword_usage: Dict[str, int] = Field(default_factory=dict, description="Frequency map of keywords and their variations.")
    section_topics: Dict[str, str] = Field(default_factory=dict, description="Mapping of section titles to their primary topic.")

    def check_and_add_anecdote(self, anecdote: str) -> bool:
        """Hashes an anecdote, checks if it's been used, and adds it if not. Returns True if it was already used."""
        anecdote_hash = str(hash(anecdote.strip()[:100]))
        if anecdote_hash in self.used_anecdotes:
            return True
        self.used_anecdotes.add(anecdote_hash)
        return False

    def check_and_add_statistic(self, statistic: str) -> bool:
        """Hashes a statistic, checks if it's been used, and adds it if not. Returns True if it was already used."""
        stat_hash = str(hash(statistic.strip()[:100]))
        if stat_hash in self.used_statistics:
            return True
        self.used_statistics.add(stat_hash)
        return False

    def record_keyword_usage(self, keyword: str):
        """Records an instance of a keyword being used."""
        self.keyword_usage[keyword] = self.keyword_usage.get(keyword, 0) + 1
