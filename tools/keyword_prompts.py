"""Keyword prompt renderers inspired by brief LinkedIn-style SEO prompt examples.

Provides simple render functions that return prompt strings ready to paste
into an LLM/agent. Templates are intentionally minimal and include explicit
instructions where structured JSON is expected.
"""

from typing import List


SEED_EXPANSION_TEMPLATE = (
    "Given the seed keyword '{seed}' and industry '{industry}', generate a list of"
    " high-potential keyword variations, modifiers, and long-tail ideas. Return a"
    " plain newline-separated list of keyword phrases. Include regional hints if"
    " region='{region}'."
)


CLUSTER_PROMPT_TEMPLATE = (
    "Group these SEO topics into {n_clusters} larger thematic clusters.\n"
    "Topics: {topics}\n"
    "Seed: {seed}\n\n"
    "Return ONLY valid JSON mapping cluster_name -> [topic1, topic2, ...]."
)


PRIORITY_PROMPT_TEMPLATE = (
    "Given these candidate keywords: {keywords}\n"
    "For each keyword, estimate intent (informational/commercial/transactional),"
    " SERP difficulty (low/medium/high), and a priority score (0-100)."
    " Return ONLY valid JSON: [{{\"keyword\":..., \"intent\":..., \"kd\":..., \"score\":...}}, ...]"
)


def render_seed_expansion(seed: str, industry: str = "general", region: str = "global") -> str:
    return SEED_EXPANSION_TEMPLATE.format(seed=seed, industry=industry, region=region)


def render_clustering_prompt(seed: str, topics: List[str], n_clusters: int = 6) -> str:
    topics_snip = topics[:80]
    return CLUSTER_PROMPT_TEMPLATE.format(seed=seed, topics=topics_snip, n_clusters=n_clusters)


def render_priority_prompt(keywords: List[str]) -> str:
    kws = keywords[:200]
    return PRIORITY_PROMPT_TEMPLATE.format(keywords=kws)


__all__ = [
    "render_seed_expansion",
    "render_clustering_prompt",
    "render_priority_prompt",
]
