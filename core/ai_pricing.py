"""
AI Provider Pricing Table
=========================
Tracks cost per million tokens (input / output) for every provider model.
Cost calculation returns USD.

Usage:
    from core.ai_pricing import get_cost, PRICING_TABLE, get_model_for_provider
    cost = get_cost("groq", "llama-3.3-70b-versatile", input_tokens=1200, output_tokens=800)
"""

from typing import Dict, Tuple, Optional

# ─────────────────────────────────────────────────────────────────────────────
# PRICING TABLE
# Format: model_id → (input_cost_per_1M, output_cost_per_1M)  in USD
# Prices as of 2025. Update when providers change their pricing.
# ─────────────────────────────────────────────────────────────────────────────
PRICING_TABLE: Dict[str, Tuple[float, float]] = {
    # ── Groq ──────────────────────────────────────────────────
    "llama-3.3-70b-versatile":          (0.59, 0.79),
    "llama-3.1-70b-versatile":          (0.59, 0.79),
    "llama-3.1-8b-instant":             (0.05, 0.08),
    "llama3-70b-8192":                  (0.59, 0.79),
    "llama3-8b-8192":                   (0.05, 0.08),
    "mixtral-8x7b-32768":               (0.24, 0.24),
    "gemma2-9b-it":                     (0.20, 0.20),

    # ── OpenAI ────────────────────────────────────────────────
    "gpt-4o":                           (2.50, 10.00),
    "gpt-4o-2024-11-20":               (2.50, 10.00),
    "gpt-4o-mini":                      (0.15, 0.60),
    "gpt-4o-mini-2024-07-18":          (0.15, 0.60),
    "gpt-4-turbo":                      (10.00, 30.00),
    "gpt-4-turbo-preview":              (10.00, 30.00),
    "gpt-4":                            (30.00, 60.00),
    "gpt-3.5-turbo":                    (0.50, 1.50),
    "o1":                               (15.00, 60.00),
    "o1-mini":                          (3.00, 12.00),
    "o3-mini":                          (1.10, 4.40),

    # ── Anthropic / Claude ────────────────────────────────────
    "claude-3-5-sonnet-20241022":       (3.00, 15.00),
    "claude-3-5-sonnet-20240620":       (3.00, 15.00),
    "claude-3-5-haiku-20241022":        (0.80, 4.00),
    "claude-3-opus-20240229":           (15.00, 75.00),
    "claude-3-sonnet-20240229":         (3.00, 15.00),
    "claude-3-haiku-20240307":          (0.25, 1.25),
    "claude-sonnet-4":                  (3.00, 15.00),
    "claude-opus-4":                    (15.00, 75.00),
    "claude-haiku-4":                   (0.80, 4.00),
    "claude-3-7-sonnet-20250219":       (3.00, 15.00),

    # ── Google Gemini ─────────────────────────────────────────
    "gemini-1.5-pro":                   (1.25, 5.00),
    "gemini-1.5-pro-002":               (1.25, 5.00),
    "gemini-1.5-flash":                 (0.075, 0.30),
    "gemini-1.5-flash-002":             (0.075, 0.30),
    "gemini-1.5-flash-8b":              (0.0375, 0.15),
    "gemini-2.0-flash":                 (0.10, 0.40),
    "gemini-2.0-flash-lite":            (0.075, 0.30),
    "gemini-2.5-flash":                 (0.15, 0.60),
    "gemini-2.5-pro":                   (1.25, 10.00),
    "gemini-pro":                       (0.50, 1.50),
    # Gemini Free tier: $0
    "gemini-free":                      (0.0, 0.0),

    # ── OpenRouter models ─────────────────────────────────────
    "deepseek/deepseek-v3.2":           (0.14, 0.28),   # $0.14 in / $0.28 out
    "deepseek/deepseek-r1-0528":        (0.55, 2.19),   # R1 reasoning model
    "google/gemini-2.5-flash":          (0.15, 0.60),
    "google/gemini-2.0-flash-lite-001": (0.075, 0.30),
    "openai/gpt-4o":                    (2.50, 10.00),
    "anthropic/claude-sonnet-4":        (3.00, 15.00),
    "meta-llama/llama-4-maverick":      (0.19, 0.49),
    "qwen/qwen3.6-plus:free":           (0.0, 0.0),
    "qwen/qwen3-next-80b-a3b-instruct:free": (0.0, 0.0),
    "qwen/qwen3-coder:free":            (0.0, 0.0),
    "z-ai/glm-5-turbo":                 (1.20, 1.20),

    # ── Ollama (local) ────────────────────────────────────────
    "ollama":                           (0.0, 0.0),
    "mistral:7b-instruct-q4_K_M":       (0.0, 0.0),
    "llama3:latest":                    (0.0, 0.0),
    "llama3.1:8b":                      (0.0, 0.0),
    "mistral:latest":                   (0.0, 0.0),
    "phi3:latest":                      (0.0, 0.0),
    "gemma2:latest":                    (0.0, 0.0),
    "ollama-local":                     (0.0, 0.0),
}

# ─────────────────────────────────────────────────────────────────────────────
# PROVIDER → MODEL MAPPING
# Maps provider shortnames to their model IDs (for cost lookup when model unknown)
# ─────────────────────────────────────────────────────────────────────────────
PROVIDER_DEFAULT_MODELS: Dict[str, str] = {
    "groq":             "llama-3.3-70b-versatile",
    "gemini":           "gemini-1.5-flash",
    "gemini_free":      "gemini-free",
    "gemini_paid":      "gemini-1.5-pro",
    "ollama":           "ollama-local",
    "openai":           "gpt-4o",
    "openai_paid":      "gpt-4o",
    "chatgpt":          "gpt-4o",
    "claude":           "claude-3-5-haiku-20241022",
    "anthropic":        "claude-3-5-haiku-20241022",
    "anthropic_paid":   "claude-3-5-sonnet-20241022",
    "openrouter":       "gpt-4o",
    "or_qwen":          "qwen/qwen3.6-plus:free",
    "or_qwen_next":     "qwen/qwen3-next-80b-a3b-instruct:free",
    "or_deepseek":      "deepseek/deepseek-v3.2",
    "or_gemini_flash":  "google/gemini-2.5-flash",
    "or_gemini_lite":   "google/gemini-2.0-flash-lite-001",
    "or_glm":           "z-ai/glm-5-turbo",
    "or_gpt4o":         "openai/gpt-4o",
    "or_claude":        "anthropic/claude-sonnet-4",
    "or_llama":         "meta-llama/llama-4-maverick",
    "or_qwen_coder":    "qwen/qwen3-coder:free",
    "or_deepseek_r1":   "deepseek/deepseek-r1-0528",
}

# ─────────────────────────────────────────────────────────────────────────────
# DISPLAY PRICING TABLE (for frontend /api/ai-analytics/pricing)
# ─────────────────────────────────────────────────────────────────────────────
PROVIDER_DISPLAY_INFO: Dict[str, dict] = {
    "groq":            {"label": "Groq (Llama 3.3 70B)", "tier": "free",      "input": 0.59, "output": 0.79},
    "gemini_free":     {"label": "Gemini Flash (Free)",  "tier": "free",      "input": 0.0,  "output": 0.0},
    "gemini_paid":     {"label": "Gemini 1.5 Pro",       "tier": "paid",      "input": 1.25, "output": 5.00},
    "gemini":          {"label": "Gemini Flash",         "tier": "free",      "input": 0.075,"output": 0.30},
    "ollama":          {"label": "Ollama (Local)",       "tier": "local",     "input": 0.0,  "output": 0.0},
    "openai":          {"label": "GPT-4o",               "tier": "paid",      "input": 2.50, "output": 10.00},
    "openai_paid":     {"label": "GPT-4o (Paid)",        "tier": "paid",      "input": 2.50, "output": 10.00},
    "claude":          {"label": "Claude 3.5 Haiku",     "tier": "paid",      "input": 0.80, "output": 4.00},
    "anthropic":       {"label": "Claude 3.5 Haiku",     "tier": "paid",      "input": 0.80, "output": 4.00},
    "anthropic_paid":  {"label": "Claude 3.5 Sonnet",    "tier": "paid",      "input": 3.00, "output": 15.00},
    "or_qwen":         {"label": "Qwen 3.6 Plus (Free)", "tier": "free",      "input": 0.0,  "output": 0.0},
    "or_qwen_next":    {"label": "Qwen3 Next 80B (Free)","tier": "free",      "input": 0.0,  "output": 0.0},
    "or_deepseek":     {"label": "DeepSeek V3.2",        "tier": "cheap",     "input": 0.14, "output": 0.28},
    "or_gemini_flash": {"label": "Gemini 2.5 Flash",     "tier": "cheap",     "input": 0.15, "output": 0.60},
    "or_gemini_lite":  {"label": "Gemini 2.0 Flash Lite","tier": "cheap",     "input": 0.075,"output": 0.30},
    "or_glm":          {"label": "GLM 5 Turbo",          "tier": "cheap",     "input": 1.20, "output": 1.20},
    "or_gpt4o":        {"label": "GPT-4o (OpenRouter)",  "tier": "paid",      "input": 2.50, "output": 10.00},
    "or_claude":       {"label": "Claude Sonnet 4 (OR)", "tier": "paid",      "input": 3.00, "output": 15.00},
    "or_llama":        {"label": "Llama 4 Maverick",     "tier": "cheap",     "input": 0.19, "output": 0.49},
    "or_qwen_coder":   {"label": "Qwen3 Coder (Free)",   "tier": "free",      "input": 0.0,  "output": 0.0},
    "or_deepseek_r1":  {"label": "DeepSeek R1",          "tier": "cheap",     "input": 0.55, "output": 2.19},
}


def get_cost(provider: str, model: Optional[str], input_tokens: int, output_tokens: int) -> float:
    """
    Calculate the USD cost for an AI call given provider, model, and token counts.

    Returns 0.0 for local/free providers (Ollama, free-tier Gemini, free OR models).
    """
    if input_tokens <= 0 and output_tokens <= 0:
        return 0.0

    # 1. Try exact model match
    if model and model in PRICING_TABLE:
        inp_rate, out_rate = PRICING_TABLE[model]
        return (input_tokens * inp_rate + output_tokens * out_rate) / 1_000_000

    # 2. Fall back to provider default model
    default_model = PROVIDER_DEFAULT_MODELS.get(provider or "")
    if default_model and default_model in PRICING_TABLE:
        inp_rate, out_rate = PRICING_TABLE[default_model]
        return (input_tokens * inp_rate + output_tokens * out_rate) / 1_000_000

    # 3. Use display info if available
    info = PROVIDER_DISPLAY_INFO.get(provider or "")
    if info:
        return (input_tokens * info["input"] + output_tokens * info["output"]) / 1_000_000

    # 4. Unknown provider — return 0 rather than guess
    return 0.0


def get_model_for_provider(provider: str, env_model: Optional[str] = None) -> str:
    """Return the canonical model name for a provider, preferring env override."""
    if env_model:
        return env_model
    return PROVIDER_DEFAULT_MODELS.get(provider, "unknown")


def estimate_cost_for_comparison(provider: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate what an equivalent call would cost on a given provider."""
    info = PROVIDER_DISPLAY_INFO.get(provider, {})
    return (input_tokens * info.get("input", 0.0) + output_tokens * info.get("output", 0.0)) / 1_000_000


def get_pricing_table_for_api() -> list:
    """Return structured pricing table for the frontend analytics API."""
    rows = []
    for provider, info in PROVIDER_DISPLAY_INFO.items():
        rows.append({
            "provider": provider,
            "label": info["label"],
            "tier": info["tier"],
            "input_per_1m": info["input"],
            "output_per_1m": info["output"],
            "combined_per_1m": round((info["input"] + info["output"]) / 2, 4) if info["input"] or info["output"] else 0.0,
            "is_free": info["input"] == 0.0 and info["output"] == 0.0,
        })
    # Sort: free first, then by cost ascending
    rows.sort(key=lambda r: (not r["is_free"], r["combined_per_1m"]))
    return rows
