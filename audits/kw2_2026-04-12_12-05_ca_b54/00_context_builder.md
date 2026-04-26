# Context Builder

# System Structure

The provided code implements a **Business Intelligence Engine** for analyzing a business website and producing a structured profile. The engine consists of several core modules that work together in a step-by-step data flow to achieve the system purpose.

## System Purpose
The primary goal of this system is to analyze a business website and provide a comprehensive profile, including competitor insights, confidence score, and persistence.

## Core Modules
1. **`BusinessIntelligenceEngine`**: The main class responsible for executing the full Phase 1 analysis pipeline.
2. **`db`**: A module containing functions to interact with a database for loading and saving business profiles.
3. **`segment_content`**: A module that segments the content of the crawled pages into products, categories, about section, and found products.
4. **`extract_entities`**: A module that extracts entities from the segmented content using named entity recognition (NER) and topic modeling techniques.
5. **`get_competitor_insights`**: A module that retrieves competitor insights based on the extracted entities.
6. **`compute_confidence`**: A module that calculates the confidence score for the business profile based on various factors.
7. **`check_consistency`**: A module that checks the consistency of the extracted data.
8. **`PillarExtractor`**: A module that extracts pillars (key topics) from the segmented content.
9. **`ModifierExtractor`**: A module that extracts modifiers (additional information about entities) from the extracted entities.
10. **`kw2_ai_call`**: A function that calls an AI provider to analyze the extracted data and generate additional insights.
11. **`kw2_extract_json`**: A function that extracts JSON data from the AI provider's response.

## Data Flow
The system follows a step-by-step data flow:

1. The user initiates the analysis by calling the `BusinessIntelligenceEngine` class with the required parameters (project ID, URL, manual input, competitor URLs, AI provider, and force flag).
2. If the force flag is not set or the cache has expired, the system crawls the customer site using the provided URL.
3. The system segments the content of the crawled pages into products, categories, about section, and found products.
4. The system extracts entities from the segmented content using named entity recognition (NER) and topic modeling techniques.
5. The system retrieves competitor insights based on the extracted entities.
6. The system calculates the confidence score for the business profile based on various factors.
7. The system checks the consistency of the extracted