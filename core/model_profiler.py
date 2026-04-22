"""
Model Profiler: Adapt timeouts and expectations to ANY AI model (fast/slow, smart/dumb)

Core Principle: Don't try to "fix" slow models - ADAPT to them.
- Ollama qwen2.5:3b @ 12.8 tok/s → 8 min for quality loop pass = OK
- Gemini @ 80 tok/s → 1 min for same pass = OK
- Calculate timeouts dynamically based on model speed
"""
from dataclasses import dataclass, asdict
from typing import Optional, Dict
import time
import json
import logging
from datetime import datetime, timezone

log = logging.getLogger(__name__)


@dataclass
class ModelProfile:
    """Characteristics of an AI model for dynamic timeout/expectation calculation"""
    provider: str
    model: str
    tokens_per_sec: float  # 0 = unknown (use conservative default)
    max_context: int
    reliability: str  # "high" | "medium" | "low"
    avg_response_time: float = 0.0  # Average observed response time (seconds)
    total_calls: int = 0  # Number of times profiled
    last_updated: str = ""
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "ModelProfile":
        return cls(**data)


# Known model profiles (bootstrapped from benchmarks)
KNOWN_PROFILES: Dict[str, ModelProfile] = {
    "ollama:qwen2.5:3b": ModelProfile("ollama", "qwen2.5:3b", 12.8, 8192, "medium"),
    "ollama:mistral:7b-instruct-q4_K_M": ModelProfile("ollama", "mistral:7b-instruct-q4_K_M", 6.4, 8192, "medium"),
    "ollama:llama3:8b": ModelProfile("ollama", "llama3:8b", 10.0, 8192, "medium"),
    "gemini": ModelProfile("gemini", "gemini-1.5-flash", 80.0, 1000000, "high"),
    "gemini_free": ModelProfile("gemini_free", "gemini-1.5-flash", 80.0, 1000000, "high"),
    "gemini_paid": ModelProfile("gemini_paid", "gemini-1.5-pro", 60.0, 2000000, "high"),
    "groq": ModelProfile("groq", "llama-3.3-70b-versatile", 120.0, 8192, "high"),
    "chatgpt": ModelProfile("chatgpt", "gpt-4o-mini", 50.0, 128000, "high"),
    "openai": ModelProfile("openai", "gpt-4o-mini", 50.0, 128000, "high"),
    "openai_paid": ModelProfile("openai_paid", "gpt-4o", 40.0, 128000, "high"),
}


class ModelProfiler:
    """Manages model profiles and provides dynamic timeout calculation"""
    
    def __init__(self, db=None):
        self.db = db
        self._profiles_cache = {}
        self._load_profiles_from_db()
    
    def _load_profiles_from_db(self):
        """Load cached profiles from database"""
        if not self.db:
            return
        try:
            rows = self.db.execute(
                "SELECT provider, model, tokens_per_sec, max_context, reliability, "
                "avg_response_time, total_calls, last_updated FROM model_profiles"
            ).fetchall()
            for row in rows:
                key = f"{row[0]}:{row[1]}" if row[1] else row[0]
                self._profiles_cache[key] = ModelProfile(
                    provider=row[0], model=row[1], tokens_per_sec=row[2],
                    max_context=row[3], reliability=row[4],
                    avg_response_time=row[5], total_calls=row[6], last_updated=row[7]
                )
        except Exception as e:
            log.warning(f"Could not load model profiles from DB: {e}")
    
    def get_profile(self, provider: str, model: str = "") -> ModelProfile:
        """Get profile for a model. Returns default if unknown."""
        key = f"{provider}:{model}" if model else provider
        
        # Check cache first
        if key in self._profiles_cache:
            return self._profiles_cache[key]
        
        # Check known profiles
        if key in KNOWN_PROFILES:
            profile = KNOWN_PROFILES[key]
            self._profiles_cache[key] = profile
            return profile
        
        # Unknown model - create conservative default profile
        log.warning(f"Unknown model {key} - using conservative default profile (50 tok/s, medium reliability)")
        profile = ModelProfile(
            provider=provider,
            model=model,
            tokens_per_sec=50.0,  # Conservative middle ground
            max_context=8192,
            reliability="medium",
        )
        self._profiles_cache[key] = profile
        return profile
    
    def update_profile(self, provider: str, model: str, response_time: float, tokens_generated: int):
        """Update profile with observed performance metrics"""
        key = f"{provider}:{model}" if model else provider
        profile = self.get_profile(provider, model)
        
        # Calculate tokens/sec from this observation
        observed_tps = tokens_generated / response_time if response_time > 0 else 0
        
        # Update running average
        if profile.total_calls == 0:
            profile.tokens_per_sec = observed_tps
            profile.avg_response_time = response_time
        else:
            # Weighted average (more weight to recent observations)
            weight = 0.3  # 30% weight to new observation
            profile.tokens_per_sec = profile.tokens_per_sec * (1 - weight) + observed_tps * weight
            profile.avg_response_time = profile.avg_response_time * (1 - weight) + response_time * weight
        
        profile.total_calls += 1
        profile.last_updated = datetime.now(timezone.utc).isoformat()
        
        # Save to cache
        self._profiles_cache[key] = profile
        
        # Save to DB
        if self.db:
            try:
                self.db.execute(
                    """INSERT OR REPLACE INTO model_profiles(provider, model, tokens_per_sec, max_context, 
                       reliability, avg_response_time, total_calls, last_updated) 
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (profile.provider, profile.model, profile.tokens_per_sec, profile.max_context,
                     profile.reliability, profile.avg_response_time, profile.total_calls, profile.last_updated)
                )
                self.db.commit()
            except Exception as e:
                log.warning(f"Could not save model profile to DB: {e}")
        
        log.info(f"Updated profile {key}: {profile.tokens_per_sec:.1f} tok/s (avg over {profile.total_calls} calls)")
    
    def calculate_timeout(
        self, 
        prompt_chars: int, 
        max_tokens: int, 
        profile: ModelProfile,
        operation_type: str = "standard"  # "standard" | "quality_loop" | "redevelop"
    ) -> int:
        """
        Calculate appropriate timeout based on model speed
        
        Args:
            prompt_chars: Length of input prompt in characters
            max_tokens: Maximum output tokens requested
            profile: Model profile with speed characteristics
            operation_type: Type of operation (affects safety margin)
        
        Returns:
            Timeout in seconds
        """
        if profile.tokens_per_sec == 0 or profile.tokens_per_sec < 1.0:
            # Unknown or unreliable speed - use very conservative default
            log.warning(f"Model {profile.provider}:{profile.model} has unknown/zero speed - using 600s default timeout")
            return 600
        
        # Estimate tokens (rough: 1 token ≈ 3-4 chars for most models)
        prompt_tokens = prompt_chars // 3
        total_tokens = prompt_tokens + max_tokens
        
        # Base time = tokens / speed
        base_time = total_tokens / profile.tokens_per_sec
        
        # Safety margin based on reliability
        if profile.reliability == "high":
            margin = 1.5  # Gemini/Groq/GPT are very consistent
        elif profile.reliability == "medium":
            margin = 2.5  # Ollama can vary (GPU load, model quantization, etc.)
        else:
            margin = 3.5  # Unknown/unreliable models need extra buffer
        
        # Additional margin for complex operations
        if operation_type == "quality_loop":
            margin *= 1.2  # Quality loop prompts are complex, may need more thinking time
        elif operation_type == "redevelop":
            margin *= 1.3  # Redevelop is the most complex operation
        
        timeout = int(base_time * margin) + 30  # +30s for network/overhead
        
        # Enforce minimum timeout (avoid race conditions)
        min_timeout = 60
        timeout = max(min_timeout, timeout)
        
        # Enforce reasonable maximum (catch runaway calculations)
        max_timeout = 3600  # 1 hour max
        timeout = min(max_timeout, timeout)
        
        log.debug(
            f"Calculated timeout for {profile.provider}:{profile.model}: {timeout}s "
            f"(prompt={prompt_chars}c, max_tokens={max_tokens}, "
            f"speed={profile.tokens_per_sec:.1f} tok/s, margin={margin:.1f}x)"
        )
        
        return timeout
    
    def estimate_duration(self, prompt_chars: int, max_tokens: int, profile: ModelProfile) -> int:
        """Estimate how long an operation will take (for progress reporting)"""
        if profile.tokens_per_sec == 0:
            return 300  # Conservative guess
        prompt_tokens = prompt_chars // 3
        total_tokens = prompt_tokens + max_tokens
        # Use the base time without safety margins (this is expected, not worst-case)
        return int(total_tokens / profile.tokens_per_sec) + 10
    
    def create_tables(self):
        """Create DB tables for model profiles"""
        if not self.db:
            return
        try:
            self.db.execute("""
                CREATE TABLE IF NOT EXISTS model_profiles (
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    tokens_per_sec REAL DEFAULT 0,
                    max_context INTEGER DEFAULT 8192,
                    reliability TEXT DEFAULT 'medium',
                    avg_response_time REAL DEFAULT 0,
                    total_calls INTEGER DEFAULT 0,
                    last_updated TEXT,
                    PRIMARY KEY(provider, model)
                )
            """)
            self.db.commit()
            log.info("Model profiles table created/verified")
        except Exception as e:
            log.warning(f"Could not create model_profiles table: {e}")


# Singleton instance
_profiler_instance: Optional[ModelProfiler] = None


def get_profiler(db=None) -> ModelProfiler:
    """Get or create singleton ModelProfiler"""
    global _profiler_instance
    if _profiler_instance is None:
        _profiler_instance = ModelProfiler(db)
    return _profiler_instance


def init_profiler(db):
    """Initialize profiler with database connection"""
    global _profiler_instance
    _profiler_instance = ModelProfiler(db)
    _profiler_instance.create_tables()
    return _profiler_instance
