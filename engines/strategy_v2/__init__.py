"""
Strategy Engine V2 — Blueprint-first content strategy pipeline.

Flow: keyword → intent → angles → blueprints → QA score → (auto-fix) → save

Primary AI: OpenAI (OPENAI_MODEL env var, default gpt-4o)
Fallback:   Gemini Flash → Groq llama-3.3-70b
"""
