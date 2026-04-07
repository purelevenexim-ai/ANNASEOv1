"""
AI Provider Manager — Centralised resilience layer for all LLM API calls.

Features:
  1. Audit & Logging: unique request IDs, provider/status/latency per call
  2. Exponential backoff with jitter (transient-only: 429, 503, timeouts)
  3. Token-bucket rate limiter per provider
  4. Circuit breaker per provider (open → half-open → closed)
  5. Request tracing correlated with pipeline trace IDs
  6. Live metrics: error counts, latency histograms, rate-limit events
  7. Monitoring API helpers (provider health dashboard)
"""

import asyncio
import logging
import os
import random
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

log = logging.getLogger("ai_provider_manager")

# ─────────────────────────────────────────────────────────────────────────────
# 1. REQUEST ID + TRACE CORRELATION
# ─────────────────────────────────────────────────────────────────────────────

def _gen_request_id() -> str:
    return uuid.uuid4().hex[:12]

# ─────────────────────────────────────────────────────────────────────────────
# 2. TOKEN-BUCKET RATE LIMITER
# ─────────────────────────────────────────────────────────────────────────────

class TokenBucket:
    """Thread-safe token-bucket rate limiter.

    Parameters:
        rate: tokens added per second
        capacity: max burst size
    """

    def __init__(self, rate: float, capacity: float):
        self.rate = rate
        self.capacity = capacity
        self._tokens = capacity
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock() if asyncio else None

    def _refill(self):
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
        self._last_refill = now

    async def acquire(self, tokens: float = 1.0) -> float:
        """Wait until tokens are available. Returns actual wait time in seconds."""
        total_wait = 0.0
        async with self._lock:
            self._refill()
            if self._tokens >= tokens:
                self._tokens -= tokens
                return 0.0
            deficit = tokens - self._tokens
            wait = deficit / self.rate
        # Wait outside the lock so other coroutines can check
        await asyncio.sleep(wait)
        total_wait += wait
        async with self._lock:
            self._refill()
            self._tokens = max(0, self._tokens - tokens)
        return total_wait

    @property
    def available(self) -> float:
        self._refill()
        return self._tokens


# ─────────────────────────────────────────────────────────────────────────────
# 3. CIRCUIT BREAKER
# ─────────────────────────────────────────────────────────────────────────────

class CircuitState(Enum):
    CLOSED = "closed"          # Normal — requests flow
    OPEN = "open"              # Tripped — all requests fail fast
    HALF_OPEN = "half_open"    # Testing — allow one probe request


@dataclass
class CircuitBreaker:
    """Per-provider circuit breaker.

    Opens after `failure_threshold` consecutive failures within `window_seconds`.
    Stays open for `recovery_timeout` then moves to half-open (one probe).
    """
    failure_threshold: int = 5
    recovery_timeout: float = 60.0    # seconds before half-open
    window_seconds: float = 120.0     # rolling window for failure counting

    state: CircuitState = field(default=CircuitState.CLOSED)
    _failures: Deque = field(default_factory=deque)
    _last_failure_time: float = 0.0
    _opened_at: float = 0.0

    def record_success(self):
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED
            self._failures.clear()
            log.info("Circuit breaker → CLOSED (probe succeeded)")
        elif self.state == CircuitState.CLOSED:
            pass  # just clear old failures
        self._prune()

    def record_failure(self):
        now = time.monotonic()
        self._failures.append(now)
        self._last_failure_time = now
        self._prune()
        if self.state == CircuitState.HALF_OPEN:
            # Probe failed — re-open
            self.state = CircuitState.OPEN
            self._opened_at = now
            log.warning("Circuit breaker → OPEN (probe failed)")
        elif self.state == CircuitState.CLOSED and len(self._failures) >= self.failure_threshold:
            self.state = CircuitState.OPEN
            self._opened_at = now
            log.warning(f"Circuit breaker → OPEN ({len(self._failures)} failures in {self.window_seconds}s)")

    def allow_request(self) -> bool:
        now = time.monotonic()
        self._prune()
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            if now - self._opened_at >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                log.info("Circuit breaker → HALF_OPEN (recovery timeout elapsed)")
                return True
            return False
        # HALF_OPEN: allow exactly one request
        return True

    def _prune(self):
        cutoff = time.monotonic() - self.window_seconds
        while self._failures and self._failures[0] < cutoff:
            self._failures.popleft()

    def status_dict(self) -> Dict:
        return {
            "state": self.state.value,
            "recent_failures": len(self._failures),
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
        }


# ─────────────────────────────────────────────────────────────────────────────
# 4. PER-PROVIDER METRICS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ProviderMetrics:
    """Rolling window metrics per provider."""
    total_requests: int = 0
    total_successes: int = 0
    total_failures: int = 0
    total_429s: int = 0
    total_timeouts: int = 0
    total_tokens_used: int = 0
    total_wait_time: float = 0.0           # seconds spent waiting for rate limiter
    _latencies: Deque = field(default_factory=lambda: deque(maxlen=200))
    _recent_errors: Deque = field(default_factory=lambda: deque(maxlen=50))

    def record_call(self, latency: float, success: bool, status_code: int = 0,
                    tokens: int = 0, error_msg: str = "", request_id: str = ""):
        self.total_requests += 1
        self._latencies.append(latency)
        if success:
            self.total_successes += 1
        else:
            self.total_failures += 1
            self._recent_errors.append({
                "ts": time.time(),
                "status": status_code,
                "error": error_msg[:200],
                "request_id": request_id,
            })
        if status_code == 429:
            self.total_429s += 1
        if "timeout" in (error_msg or "").lower() or "timed out" in (error_msg or "").lower():
            self.total_timeouts += 1
        self.total_tokens_used += tokens

    @property
    def error_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.total_failures / self.total_requests

    @property
    def avg_latency(self) -> float:
        if not self._latencies:
            return 0.0
        return sum(self._latencies) / len(self._latencies)

    @property
    def p95_latency(self) -> float:
        if not self._latencies:
            return 0.0
        sorted_lat = sorted(self._latencies)
        idx = int(len(sorted_lat) * 0.95)
        return sorted_lat[min(idx, len(sorted_lat) - 1)]

    def status_dict(self) -> Dict:
        return {
            "total_requests": self.total_requests,
            "total_successes": self.total_successes,
            "total_failures": self.total_failures,
            "total_429s": self.total_429s,
            "total_timeouts": self.total_timeouts,
            "error_rate": round(self.error_rate * 100, 1),
            "avg_latency_ms": round(self.avg_latency * 1000),
            "p95_latency_ms": round(self.p95_latency * 1000),
            "total_tokens_used": self.total_tokens_used,
            "total_wait_time_s": round(self.total_wait_time, 1),
            "recent_errors": list(self._recent_errors)[-10:],
        }


# ─────────────────────────────────────────────────────────────────────────────
# 5. AUDIT LOG (ring buffer)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AuditEntry:
    request_id: str
    trace_id: str
    provider: str
    timestamp: float
    latency_ms: float
    status_code: int
    success: bool
    tokens_used: int
    error: str
    rate_limit_remaining: Optional[int]
    retry_after: Optional[float]
    prompt_chars: int
    response_chars: int

# Max 500 entries kept in memory
_audit_log: Deque[Dict] = deque(maxlen=500)

def _record_audit(entry: AuditEntry):
    _audit_log.append({
        "request_id": entry.request_id,
        "trace_id": entry.trace_id,
        "provider": entry.provider,
        "ts": entry.timestamp,
        "latency_ms": round(entry.latency_ms, 1),
        "status": entry.status_code,
        "ok": entry.success,
        "tokens": entry.tokens_used,
        "error": entry.error,
        "rl_remaining": entry.rate_limit_remaining,
        "retry_after": entry.retry_after,
        "prompt_chars": entry.prompt_chars,
        "response_chars": entry.response_chars,
    })

def get_audit_log(limit: int = 100) -> List[Dict]:
    """Return recent audit entries (newest first)."""
    return list(reversed(list(_audit_log)))[:limit]


# ─────────────────────────────────────────────────────────────────────────────
# 6. PROVIDER CONFIG
# ─────────────────────────────────────────────────────────────────────────────

# Default rate limits (requests per second / burst capacity)
PROVIDER_RATE_LIMITS = {
    "groq":         {"rate": 0.45, "capacity": 3},     # ~27 RPM (free tier: 30 RPM)
    "gemini_paid":  {"rate": 1.5,  "capacity": 10},    # ~90 RPM (paid tier generous)
    "gemini_free":  {"rate": 0.15, "capacity": 2},     # ~9 RPM (free tier: 10 RPM)
    "gemini":       {"rate": 0.15, "capacity": 2},
    "ollama":       {"rate": 2.0,  "capacity": 3},     # Remote Ollama
    "openai":       {"rate": 0.8,  "capacity": 5},
    "openai_paid":  {"rate": 2.0,  "capacity": 10},
    "chatgpt":      {"rate": 0.8,  "capacity": 5},
    "claude":       {"rate": 0.5,  "capacity": 3},
    "anthropic":    {"rate": 0.5,  "capacity": 3},
    "anthropic_paid": {"rate": 1.0, "capacity": 5},
    "openrouter":   {"rate": 0.5,  "capacity": 3},     # Gateway — shared free tier
    "or_qwen":      {"rate": 0.3,  "capacity": 2},     # Free tier: conservative
    "or_deepseek":  {"rate": 0.3,  "capacity": 2},
    "or_gemini_flash": {"rate": 0.3, "capacity": 2},
    "or_gemini_lite":  {"rate": 0.3, "capacity": 2},
    "or_glm":       {"rate": 0.3,  "capacity": 2},
    "or_gpt4o":     {"rate": 0.3,  "capacity": 2},
    "or_claude":    {"rate": 0.3,  "capacity": 2},
    "or_llama":     {"rate": 0.3,  "capacity": 2},
    "or_qwen_coder": {"rate": 0.3, "capacity": 2},
    "or_deepseek_r1": {"rate": 0.2, "capacity": 1},    # R1 is slow — very conservative
}

# Transient status codes that should be retried
TRANSIENT_STATUS_CODES = {429, 502, 503, 504}

# Max retry attempts for transient failures (per-provider overrides below)
MAX_RETRIES = 3

# Per-provider max retries (Ollama is slow — don't waste time retrying)
PROVIDER_MAX_RETRIES = {
    "groq": 3,
    "gemini_paid": 2,
    "gemini_free": 2,
    "gemini": 2,
    "ollama": 1,
    "openai": 2,
    "openai_paid": 2,
    "chatgpt": 2,
    "claude": 2,
    "anthropic": 2,
    "anthropic_paid": 2,
    "openrouter": 2,
    "or_qwen": 2,
    "or_deepseek": 2,
    "or_gemini_flash": 2,
    "or_gemini_lite": 2,
    "or_glm": 2,
    "or_gpt4o": 2,
    "or_claude": 2,
    "or_llama": 2,
    "or_qwen_coder": 2,
    "or_deepseek_r1": 2,
}

# Base delay for exponential backoff (seconds)
BASE_DELAY = 1.5

# Max delay cap (seconds) — must accommodate Groq's token-limit reset (~90s)
MAX_DELAY = 90.0


# ─────────────────────────────────────────────────────────────────────────────
# 7. MAIN PROVIDER MANAGER (singleton)
# ─────────────────────────────────────────────────────────────────────────────

class AIProviderManager:
    """Singleton managing rate limiters, circuit breakers, metrics, and audit for all providers."""

    _instance: Optional["AIProviderManager"] = None

    def __init__(self):
        self._rate_limiters: Dict[str, TokenBucket] = {}
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        self._metrics: Dict[str, ProviderMetrics] = {}
        self._concurrency_sems: Dict[str, asyncio.Semaphore] = {}

    @classmethod
    def get_instance(cls) -> "AIProviderManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _get_rate_limiter(self, provider: str) -> TokenBucket:
        if provider not in self._rate_limiters:
            cfg = PROVIDER_RATE_LIMITS.get(provider, {"rate": 1.0, "capacity": 3})
            self._rate_limiters[provider] = TokenBucket(cfg["rate"], cfg["capacity"])
        return self._rate_limiters[provider]

    def _get_circuit_breaker(self, provider: str) -> CircuitBreaker:
        if provider not in self._circuit_breakers:
            # Ollama gets a more generous threshold (slower but not flaky)
            if "ollama" in provider:
                self._circuit_breakers[provider] = CircuitBreaker(
                    failure_threshold=8, recovery_timeout=60.0, window_seconds=300.0
                )
            else:
                self._circuit_breakers[provider] = CircuitBreaker(
                    failure_threshold=5, recovery_timeout=60.0, window_seconds=120.0
                )
        return self._circuit_breakers[provider]

    def _get_metrics(self, provider: str) -> ProviderMetrics:
        if provider not in self._metrics:
            self._metrics[provider] = ProviderMetrics()
        return self._metrics[provider]

    def _get_concurrency_sem(self, provider: str) -> asyncio.Semaphore:
        """Cap concurrent requests per provider."""
        if provider not in self._concurrency_sems:
            if "ollama" in provider:
                limit = 1    # Ollama: single request at a time
            elif provider.startswith("or_") or provider == "openrouter":
                limit = 1    # OpenRouter free tier: single request at a time
            elif provider == "groq":
                limit = 3
            else:
                limit = 5
            self._concurrency_sems[provider] = asyncio.Semaphore(limit)
        return self._concurrency_sems[provider]

    # ── Core method: wrap any AI call with full resilience ────────────────

    async def call(
        self,
        provider: str,
        func: Callable,
        *,
        trace_id: str = "",
        prompt_chars: int = 0,
        parse_response_headers: bool = True,
    ) -> "CallResult":
        """
        Execute an AI provider call with full resilience:
          1. Check circuit breaker
          2. Acquire rate-limiter token
          3. Acquire concurrency semaphore
          4. Execute with exponential backoff on transient failures
          5. Record metrics + audit entry

        Parameters:
            provider: provider name (e.g. "groq", "gemini_paid")
            func: async callable that performs the actual API call.
                  Must return a CallResult (or raise on failure).
            trace_id: pipeline trace ID for correlation
            prompt_chars: character count of the prompt (for audit)
            parse_response_headers: whether to parse rate-limit headers

        Returns:
            CallResult with response data, status, and metadata.
        """
        request_id = _gen_request_id()
        cb = self._get_circuit_breaker(provider)
        rl = self._get_rate_limiter(provider)
        metrics = self._get_metrics(provider)
        sem = self._get_concurrency_sem(provider)

        # ── 1. Circuit breaker check ──
        if not cb.allow_request():
            log.warning(f"[{request_id}] {provider}: circuit breaker OPEN — skipping")
            result = CallResult(
                success=False, provider=provider, request_id=request_id,
                error="circuit_breaker_open", status_code=0,
            )
            metrics.record_call(0, False, 0, error_msg="circuit_breaker_open", request_id=request_id)
            _record_audit(AuditEntry(
                request_id=request_id, trace_id=trace_id, provider=provider,
                timestamp=time.time(), latency_ms=0, status_code=0, success=False,
                tokens_used=0, error="circuit_breaker_open",
                rate_limit_remaining=None, retry_after=None,
                prompt_chars=prompt_chars, response_chars=0,
            ))
            return result

        # ── 2. Rate limiter ──
        wait_time = await rl.acquire()
        if wait_time > 0:
            log.info(f"[{request_id}] {provider}: rate-limited, waited {wait_time:.1f}s")
            metrics.total_wait_time += wait_time

        # ── 3. Retries with exponential backoff + jitter ──
        last_result = None
        max_retries = PROVIDER_MAX_RETRIES.get(provider, MAX_RETRIES)
        for attempt in range(1, max_retries + 1):
            t0 = time.monotonic()
            try:
                async with sem:
                    last_result = await func(request_id)

                latency = time.monotonic() - t0

                # Parse rate-limit headers if present
                rl_remaining = None
                retry_after = None
                if parse_response_headers and last_result.response_headers:
                    rl_remaining = _parse_int_header(last_result.response_headers, "x-ratelimit-remaining-requests")
                    retry_after = _parse_retry_after(last_result.response_headers)
                    # Proactively slow down if nearing limit
                    if rl_remaining is not None and rl_remaining < 3:
                        log.info(f"[{request_id}] {provider}: only {rl_remaining} requests remaining — pacing")

                if last_result.success:
                    cb.record_success()
                    metrics.record_call(
                        latency, True, last_result.status_code,
                        tokens=last_result.tokens_used, request_id=request_id,
                    )
                    _record_audit(AuditEntry(
                        request_id=request_id, trace_id=trace_id, provider=provider,
                        timestamp=time.time(), latency_ms=latency * 1000,
                        status_code=last_result.status_code, success=True,
                        tokens_used=last_result.tokens_used, error="",
                        rate_limit_remaining=rl_remaining, retry_after=retry_after,
                        prompt_chars=prompt_chars, response_chars=last_result.response_chars,
                    ))
                    last_result.request_id = request_id
                    return last_result

                # ── Failure — decide retry vs give up ──
                status = last_result.status_code

                # 200 but empty/invalid content — LLM chose not to respond, don't retry
                if status == 200:
                    break

                if status in TRANSIENT_STATUS_CODES and attempt < max_retries:
                    # Use Retry-After header if present, else exponential backoff
                    if retry_after and retry_after <= MAX_DELAY:
                        delay = retry_after + random.uniform(0.1, 0.5)
                    else:
                        delay = min(BASE_DELAY * (2 ** (attempt - 1)) + random.uniform(0, 1), MAX_DELAY)
                    log.info(f"[{request_id}] {provider}: HTTP {status}, retry {attempt}/{max_retries} in {delay:.1f}s")
                    await asyncio.sleep(delay)
                    continue
                elif status and status >= 400 and status < 500 and status != 429:
                    # Client error (not rate limit) — don't retry
                    log.warning(f"[{request_id}] {provider}: HTTP {status} (client error) — not retrying")
                    break
                else:
                    # Server-side or unknown — retry if attempts remain
                    if attempt < max_retries:
                        delay = min(BASE_DELAY * (2 ** (attempt - 1)) + random.uniform(0, 1), MAX_DELAY)
                        log.info(f"[{request_id}] {provider}: error (status={status}), retry {attempt}/{max_retries} in {delay:.1f}s")
                        await asyncio.sleep(delay)
                        continue
                    break

            except asyncio.TimeoutError:
                latency = time.monotonic() - t0
                last_result = CallResult(
                    success=False, provider=provider, request_id=request_id,
                    error="timeout", status_code=0, latency=latency,
                )
                if attempt < max_retries:
                    delay = min(BASE_DELAY * (2 ** (attempt - 1)) + random.uniform(0, 1), MAX_DELAY)
                    log.info(f"[{request_id}] {provider}: timeout after {latency:.1f}s, retry {attempt}/{max_retries} in {delay:.1f}s")
                    await asyncio.sleep(delay)
                    continue
                break

            except Exception as e:
                latency = time.monotonic() - t0
                err_str = str(e)
                is_transient = any(k in err_str.lower() for k in ("timeout", "timed out", "connection", "429"))
                last_result = CallResult(
                    success=False, provider=provider, request_id=request_id,
                    error=err_str[:300], status_code=0, latency=latency,
                )
                if is_transient and attempt < max_retries:
                    delay = min(BASE_DELAY * (2 ** (attempt - 1)) + random.uniform(0, 1), MAX_DELAY)
                    log.info(f"[{request_id}] {provider}: transient error, retry {attempt}/{max_retries} in {delay:.1f}s")
                    await asyncio.sleep(delay)
                    continue
                break

        # ── All retries exhausted ──
        latency = time.monotonic() - t0 if 't0' in dir() else 0
        cb.record_failure()
        err_msg = last_result.error if last_result else "unknown"
        status_code = last_result.status_code if last_result else 0
        metrics.record_call(
            latency, False, status_code,
            error_msg=err_msg, request_id=request_id,
        )
        _record_audit(AuditEntry(
            request_id=request_id, trace_id=trace_id, provider=provider,
            timestamp=time.time(), latency_ms=latency * 1000,
            status_code=status_code, success=False,
            tokens_used=0, error=err_msg[:200],
            rate_limit_remaining=None, retry_after=None,
            prompt_chars=prompt_chars, response_chars=0,
        ))
        if last_result:
            last_result.request_id = request_id
        return last_result or CallResult(
            success=False, provider=provider, request_id=request_id,
            error="all_retries_exhausted",
        )

    # ── Monitoring helpers ────────────────────────────────────────────────

    def provider_status(self, provider: str) -> Dict:
        """Full status for one provider."""
        return {
            "provider": provider,
            "circuit_breaker": self._get_circuit_breaker(provider).status_dict(),
            "rate_limiter": {
                "available_tokens": round(self._get_rate_limiter(provider).available, 2),
                "rate": self._get_rate_limiter(provider).rate,
                "capacity": self._get_rate_limiter(provider).capacity,
            },
            "metrics": self._get_metrics(provider).status_dict(),
        }

    def all_providers_status(self) -> Dict:
        """Status of all known providers."""
        providers = set(list(self._metrics.keys()) + list(PROVIDER_RATE_LIMITS.keys()))
        result = {}
        for p in sorted(providers):
            result[p] = self.provider_status(p)
        return result

    def alerts(self) -> List[Dict]:
        """Generate alerts based on current metrics."""
        alerts = []
        for provider, m in self._metrics.items():
            if m.total_requests < 5:
                continue
            # High error rate alert (>10% over recent requests)
            if m.error_rate > 0.10:
                alerts.append({
                    "level": "critical" if m.error_rate > 0.25 else "warning",
                    "provider": provider,
                    "type": "high_error_rate",
                    "message": f"{provider}: {m.error_rate*100:.0f}% error rate ({m.total_failures}/{m.total_requests})",
                })
            # High latency alert (p95 > 30s)
            if m.p95_latency > 30.0:
                alerts.append({
                    "level": "warning",
                    "provider": provider,
                    "type": "high_latency",
                    "message": f"{provider}: P95 latency {m.p95_latency:.1f}s",
                })
            # Rate limit spike (>3 429s)
            if m.total_429s > 3:
                alerts.append({
                    "level": "warning",
                    "provider": provider,
                    "type": "rate_limit_spike",
                    "message": f"{provider}: {m.total_429s} rate-limit (429) responses",
                })
            # Circuit breaker open
            cb = self._get_circuit_breaker(provider)
            if cb.state != CircuitState.CLOSED:
                alerts.append({
                    "level": "critical",
                    "provider": provider,
                    "type": "circuit_breaker_open",
                    "message": f"{provider}: circuit breaker {cb.state.value}",
                })
        return alerts

    def reset_provider(self, provider: str):
        """Reset all state for a provider (circuit breaker, metrics, rate limiter)."""
        self._circuit_breakers.pop(provider, None)
        self._metrics.pop(provider, None)
        self._rate_limiters.pop(provider, None)
        log.info(f"Provider {provider} state reset")


# ─────────────────────────────────────────────────────────────────────────────
# 8. CALL RESULT
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CallResult:
    """Result of an AI provider call."""
    success: bool
    provider: str = ""
    request_id: str = ""
    data: Any = None              # Parsed JSON dict or raw string
    error: str = ""
    status_code: int = 0
    latency: float = 0.0
    tokens_used: int = 0
    response_chars: int = 0
    response_headers: Optional[Dict] = None

    @property
    def text(self) -> str:
        """Convenience: get string data."""
        if isinstance(self.data, str):
            return self.data
        return ""

    @property
    def json_data(self) -> Dict:
        """Convenience: get dict data."""
        if isinstance(self.data, dict):
            return self.data
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# 9. HEADER PARSERS
# ─────────────────────────────────────────────────────────────────────────────

def _parse_int_header(headers: Dict, key: str) -> Optional[int]:
    """Parse an integer header value, case-insensitive."""
    for k, v in headers.items():
        if k.lower() == key.lower():
            try:
                return int(v)
            except (ValueError, TypeError):
                return None
    return None

def _parse_retry_after(headers: Dict) -> Optional[float]:
    """Parse Retry-After header from response. Returns seconds as float."""
    for k, v in headers.items():
        if k.lower() == "retry-after":
            try:
                return float(v)
            except (ValueError, TypeError):
                pass
    # Groq-specific: x-ratelimit-reset-requests (e.g. "2m30.5s", "1.5s", "285ms")
    for k, v in headers.items():
        if k.lower() in ("x-ratelimit-reset-tokens", "x-ratelimit-reset-requests"):
            try:
                v = str(v)
                # Handle milliseconds format (e.g. "285ms")
                if v.endswith("ms"):
                    return float(v[:-2]) / 1000.0
                total = 0.0
                parts = v.replace("m", "m ").replace("s", "").split()
                for p in parts:
                    if p.endswith("m"):
                        total += float(p[:-1]) * 60
                    else:
                        total += float(p)
                return min(total, 120.0)
            except (ValueError, TypeError):
                pass
    return None
