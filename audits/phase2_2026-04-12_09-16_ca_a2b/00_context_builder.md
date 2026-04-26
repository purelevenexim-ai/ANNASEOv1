# Context Builder

## System Purpose
The provided code implements a keyword universe generator for an AI-powered SEO tool called "kw2". The purpose of the system is to generate a comprehensive list of keywords based on a business profile, which includes information such as pillars (top-level categories), modifiers (subcategories), negative scope (excluded terms), audience, geographic location, and existing universe.

## Core Modules
1. `logging`: Used for logging messages related to the keyword generation process.
2. `json`: Used for serializing and deserializing data structures.
3. `re`: Used for regular expression matching.
4. `concurrent.futures`: Used for managing asynchronous tasks.
5. `db`: A module that interacts with a database to load and save business profile data.
6. `negotiator`: A module that handles negotiation between different components of the system.
7. `ai_caller`: A module that calls an AI provider (e.g., Google, Bing) to expand keywords.
8. `constants`: A module containing various constants used throughout the system.
9. `prompts`: A module containing prompts for different stages of the keyword generation process.
10. `_load_biz_context`: A helper function that loads business context data from a session.
11. `_build_seeds`: A function that generates seeds based on pillars and modifiers.
12. `_rule_expand`: A function that expands rules based on transactional templates.
13. `_google_suggest`: A function that suggests keywords using Google Suggest.
14. `_competitor_crawl`: A function that crawls competitor sites to gather keywords.
15. `_ai_expand`: A function that expands keywords using AI providers.
16. `_negative_filter`: A function that filters out negative keywords.
17. `_normalize`: A function that normalizes the keyword list.
18. `_dedup`: A function that removes duplicate keywords.
19. `_bulk_insert`: A function that inserts the final keyword list into a database.

## Data Flow
The keyword generation process consists of five layers, each generating a new set of keywords based on the previous layer's output. The data flow for each layer is as follows:

1. **Layer 1: Seeds**: This layer generates seeds by combining pillars and modifiers. The resulting seeds are stored in the `all_keywords` list.
2. **Layer 2: Rule expand**: This layer expands rules using transactional templates. The expanded keywords are