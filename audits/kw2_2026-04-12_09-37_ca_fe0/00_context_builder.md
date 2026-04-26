# Context Builder

# Business Intelligence Engine

The `BusinessIntelligenceEngine` is a Python class that implements the first phase of an AI-powered business analysis system. It takes in various inputs such as project ID, URLs, manual input, and competitor URLs, and returns a structured business profile with a confidence score. The engine uses caching to store previously analyzed data, ensuring efficiency when analyzing similar websites.

## Core Modules

The following core modules are used by the `BusinessIntelligenceEngine`:

1. [NEGATIVE_PATTERNS](https://github.com/kw2-ai/engines/blob/main/constants.py#L4) - A list of negative patterns to exclude from entity extraction.
2. [CRAWL_MAX_PAGES](https://github.com/kw2-ai/engines/blob/main/constants.py#L5) - The maximum number of pages to crawl during the analysis process.
3. [PROFILE_CACHE_DAYS](https://github.com/kw2-ai/engines/blob/main/constants.py#L6) - The number of days for which a cached profile remains valid before being removed from the cache.
4. [BUSINESS_ANALYSIS_SYSTEM](https://github.com/kw2-ai/engines/blob/main/prompts.py#L1) - A prompt for the system analyzing a business website.
5. [BUSINESS_ANALYSIS_USER](https://github.com/kw2-ai/engines/blob/main/prompts.py#L2) - A prompt for the user inputting information about the business being analyzed.
6. [kw2_ai_call](https://github.com/kw2-ai/engines/blob/main/ai_caller.py#L10) - A function that calls an AI provider to analyze the extracted data.
7. [kw2_extract_json](https://github.com/kw2-ai/engines/blob/main/ai_caller.py#L13) - A helper function that extracts JSON from the AI provider's response.
8. [segment_content](https://github.com/kw2-ai/engines/blob/main/content_segmenter.py#L10) - A function that segments the content of the analyzed pages into products, categories, about section, and found products.
9. [extract_entities](https://github.com/kw2-ai/engines/blob/main/entity_extractor.py#L10) - A function that extracts entities from the segmented content