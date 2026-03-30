Keyword Prompts — Templates and Usage
===================================

This document describes the prompt templates implemented in `tools/keyword_prompts.py`.

Templates:

- `render_seed_expansion(seed, industry, region)`
  - Purpose: Expand a seed keyword into modifiers, long-tail ideas, and regional variants.
  - Returns: plain text list; suitable for feeding into embedding or clustering.

- `render_clustering_prompt(seed, topics, n_clusters)`
  - Purpose: Given topic names, ask the model to group them into thematic clusters.
  - Important: This prompt includes the instruction `Return ONLY valid JSON`.

- `render_priority_prompt(keywords)`
  - Purpose: Ask the model to rate intent, SERP difficulty, and priority score per keyword.
  - Important: This prompt includes the instruction `Return ONLY valid JSON`.

Usage notes:
- Use the seed expansion for P2 debugging or as an optional generator step.
- Use clustering prompt for P9 candidate cluster formation if LLM clustering is desired.
- Use priority prompt to synthesize SERP heuristics or when human-in-the-loop prioritization is required.

Example (paste into agent):
```
{prompt}
```
