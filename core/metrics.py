try:
    from prometheus_client import Counter, Histogram, Gauge
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
    from prometheus_client import REGISTRY
except ModuleNotFoundError:
    Counter = Histogram = Gauge = REGISTRY = None
    CONTENT_TYPE_LATEST = "text/plain"
    generate_latest = lambda: b""

api_requests_total = None
api_request_latency_seconds = None
registry = REGISTRY if REGISTRY is not None else None


def _safe_counter(name, doc, labels=None):
    if Counter is None:
        return None
    try:
        if labels:
            return Counter(name, doc, labels)
        return Counter(name, doc)
    except ValueError:
        return None


def _safe_histogram(name, doc, labels=None):
    if Histogram is None:
        return None
    try:
        if labels:
            return Histogram(name, doc, labels)
        return Histogram(name, doc)
    except ValueError:
        return None

if "jobs_total" not in globals():
    jobs_total = _safe_counter("strategy_jobs_total", "Total number of strategy jobs processed")
    jobs_failed = _safe_counter("strategy_jobs_failed", "Total number of failed strategy jobs")

    api_requests_total = _safe_counter("api_requests_total", "Total number of HTTP API requests", ["method", "endpoint", "status"])
    api_request_latency_seconds = _safe_histogram("api_request_latency_seconds", "HTTP API request latency in seconds", ["endpoint"])

    step_duration_seconds = _safe_histogram("strategy_step_duration_seconds", "Duration of each pipeline step", ["step"])
    strategy_step_duration_seconds = _safe_histogram("strategy_step_duration_seconds", "Duration of strategy execution step")
    serp_fetch_duration_seconds = _safe_histogram("serp_fetch_duration_seconds", "Duration of SERP fetch in seconds")
    job_duration_seconds = _safe_histogram("strategy_job_duration_seconds", "Duration of full job execution")

    serp_cache_hit_total = _safe_counter("serp_cache_hit_total", "Total number of SERP cache hits")
    serp_cache_miss_total = _safe_counter("serp_cache_miss_total", "Total number of SERP cache misses")
    serp_cache_stale_total = _safe_counter("serp_cache_stale_total", "Total number of SERP stale cache fallback uses")

    llm_tokens_total = _safe_counter("strategy_llm_tokens_total", "Total LLM tokens consumed", ["model"])
    llm_cost_usd_total = _safe_counter("strategy_llm_cost_usd_total", "Total LLM cost in USD", ["model"])
else:
    jobs_total = jobs_failed = step_duration_seconds = strategy_step_duration_seconds = serp_fetch_duration_seconds = job_duration_seconds = None
    llm_tokens_total = llm_cost_usd_total = None
    serp_cache_hit_total = serp_cache_miss_total = serp_cache_stale_total = None

    llm_tokens_total = Counter(
        "strategy_llm_tokens_total",
        "Total LLM tokens consumed",
        ["model"],
        registry=registry,
    )

    llm_cost_usd_total = Counter(
        "strategy_llm_cost_usd_total",
        "Total LLM cost in USD",
        ["model"],
        registry=registry,
    )

# Safety: if nested imports re-execute, ensure variables exist
if "jobs_total" not in globals():
    jobs_total = jobs_failed = step_duration_seconds = strategy_step_duration_seconds = serp_fetch_duration_seconds = job_duration_seconds = None
    llm_tokens_total = llm_cost_usd_total = None
    serp_cache_hit_total = serp_cache_miss_total = serp_cache_stale_total = None


def collect_metrics_json():
    def safe_counter(v):
        if v is None:
            return 0
        try:
            return int(v._value.get())
        except Exception:
            return 0

    def safe_histogram(v):
        if v is None:
            return {"count": 0, "sum": 0}
        try:
            return {"count": int(v._count.get()), "sum": float(v._sum.get())}
        except Exception:
            return {"count": 0, "sum": 0}

    total_jobs = safe_counter(jobs_total)
    failed_jobs = safe_counter(jobs_failed)
    completed_jobs = max(0, total_jobs - failed_jobs)

    def safe_ratio(num, denom):
        return float(num / denom) if denom > 0 else 0.0

    hit_count = safe_counter(serp_cache_hit_total)
    miss_count = safe_counter(serp_cache_miss_total)
    stale_count = safe_counter(serp_cache_stale_total)
    serp_total = hit_count + miss_count + stale_count

    job_duration_hist = safe_histogram(job_duration_seconds)
    job_duration_avg = round(job_duration_hist["sum"] / job_duration_hist["count"], 4) if job_duration_hist["count"] > 0 else 0.0

    return {
        "strategy_jobs_total": total_jobs,
        "strategy_jobs_failed": failed_jobs,
        "strategy_jobs_successful": completed_jobs,
        "strategy_job_success_rate": round(safe_ratio(completed_jobs, total_jobs), 4),
        "strategy_job_duration_seconds_avg": job_duration_avg,
        "api_requests_total": safe_counter(api_requests_total),
        "api_request_latency_seconds": safe_histogram(api_request_latency_seconds),
        "strategy_step_duration_seconds": safe_histogram(step_duration_seconds),
        "strategy_job_duration_seconds": job_duration_hist,
        "strategy_step_execution_seconds": safe_histogram(strategy_step_duration_seconds),
        "serp_fetch_duration_seconds": safe_histogram(serp_fetch_duration_seconds),
        "strategy_llm_tokens_total": safe_counter(llm_tokens_total),
        "strategy_llm_cost_usd_total": safe_counter(llm_cost_usd_total),
        "serp_cache_hit_total": hit_count,
        "serp_cache_miss_total": miss_count,
        "serp_cache_stale_total": stale_count,
        "serp_cache_hit_rate": round(safe_ratio(hit_count, hit_count + miss_count), 4),
        "serp_cache_fallback_rate": round(safe_ratio(stale_count, serp_total), 4),
    }


def register_metrics(app):
    try:
        from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
    except ModuleNotFoundError:
        CONTENT_TYPE_LATEST = "text/plain"
        generate_latest = lambda: b""
    from fastapi.responses import Response

    @app.get("/metrics")
    def metrics():
        if registry is not None:
            from prometheus_client import generate_latest as prometheus_generate_latest
            return Response(prometheus_generate_latest(registry), media_type=CONTENT_TYPE_LATEST)
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.get("/metrics/json")
    def metrics_json():
        return collect_metrics_json()
