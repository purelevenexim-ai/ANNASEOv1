# Context Builder

## System Purpose
The provided code implements a Business Intelligence Engine for analyzing a business website and producing a structured profile. The engine orchestrates several steps including crawling the customer site, segmenting content, extracting entities, gathering competitor insights, performing AI analysis, checking consistency, computing confidence scores, and persisting data.

## Core Modules
The following core modules are used in the Business Intelligence Engine:

1. `json` - For handling JSON data structures.
2. `logging` - For logging messages with different severity levels.
3. `datetime` - For working with dates and times.
4. `urllib.parse` - For parsing URLs.
5. `engines.kw2.constants` - Constants used throughout the engine.
6. `engines.kw2.prompts` - Prompts for user interaction.
7. `engines.kw2.ai_caller` - Module for calling AI services.
8. `engines.kw2.content_segmenter` - Module for segmenting content into different sections.
9. `engines.kw2.entity_extractor` - Module for extracting entities from the text.
10. `engines.kw2.competitor` - Module for gathering competitor insights.
11. `engines.kw2.confidence` - Module for computing confidence scores.
12. `engines.kw2.consistency` - Module for checking consistency of the extracted data.
13. `engines.kw2.pillar_extractor` - Module for extracting pillars (key topics) from the text.
14. `engines.kw2.modifier_extractor` - Module for extracting modifiers (additional information about entities) from the text.
15. `engines.kw2.db` - Database module for storing and retrieving business profiles.

## Data Flow
The following is a step-by-step description of the data flow in the Business Intelligence Engine:

1. The `BusinessIntelligenceEngine` class receives various inputs such as project ID, URL, manual input, competitor URLs, AI provider, and force flag.
2. If the force flag is not set to True, the engine checks if there's a cached business profile for the given project ID. If it exists and hasn't expired (based on the `PROFILE_CACHE_DAYS` constant), the cached profile is returned.
3. Otherwise, the engine crawls the customer site using the provided URL. The crawled pages are stored in a list called `pages`.
4. The content of the crawled pages is segmented into different sections (products, categories, about, and found