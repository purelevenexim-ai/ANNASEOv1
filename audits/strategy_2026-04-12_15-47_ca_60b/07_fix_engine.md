# Fix Engine

```python
# ═══ FILE: engines/ruflo_strategy_dev_engine.py ════
"""
================================================================================
RUFLO — STRATEGY DEVELOPMENT ENGINE
================================================================================
Business-agnostic strategy engine that thinks like a human strategist.

Key innovation: Audience Intelligence Engine
  "Who buys spices?" → home cooks → wives at home → "best masala for fish curry"
  "Who else?"        → restaurants → bulk buyers → "wholesale pepper Kerala"
  "Who else?"        → Christians → Christmas bakers → "Christmas cake cinnamon"
  "Who else?"        → Muslims → Malabar cooks → "halal biryani masala Moplah"

Context Engine: Location × Religion × Language = unique keyword clusters
  Christian × Malabar × Malayalam = "Kerala Christmas plum cake karuvapatta"
  Muslim × Malabar × English      = "Malabar chicken masala halal recipe"
  Hindu × Wayanad × Malayalam     = "Wayanad ജൈവ കുരുമുളക് Ayurveda"

Works for ANY business: spice brand, hospital, tourism, SaaS, real estate.
Industry determines the entire strategy template, persona chains, content type.

AI routing:
  DeepSeek (Ollama) → audience chain expansion, intent classification, scoring
  Gemini (free)     → persona elaboration, context keyword generation
  Claude Sonnet     → final strategy synthesis (called once)
================================================================================
"""

import os, json, re, time, logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from dotenv import load_dotenv
import requests as _req

load_dotenv()
log = logging.getLogger("ruflo.strategy_dev")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


# ──────────────────────────────────────────────────────────────