from datetime import datetime, timezone
import json
import time

try:
    import sentry_sdk
except ModuleNotFoundError:
    sentry_sdk = None

from jobqueue.connection import redis_conn, pipeline_queue
from jobqueue.locks import acquire_job_lock, release_job_lock
from services import job_tracker
from services.checkpoint import should_run_step, mark_step_start, mark_step_complete
from services.job_control import check_control_state, PauseExecution
from services.pipeline_steps import STEPS, STEP_PROGRESS
from services.step_executor import get_next_step
from engines.serp import SERPEngine
from services.internal_linking.linker import plan_links
from services.scoring_engine import ScoringEngine
from services.strategy_schema import load_strategy_schema
from services.strategy_validator import validate_strategy_output
from services.llm_parser import parse_llm_json
from services.llm_audit import save_llm_audit
from services.quota import check_and_consume_quota
from engines.ruflo_final_strategy_engine import FinalStrategyEngine, DefaultLLMClient
from core.log_setup import get_logger, bind_context, log_event
from core.metrics import jobs_total, jobs_failed, step_duration_seconds, strategy_step_duration_seconds, job_duration_seconds, llm_tokens_total, llm_cost_usd_total


def _main_module():
    import main
    return main


def _log_info(logger, event, **fields):
    if hasattr(logger, 'bind'):
        logger.info(event, **fields)
    else:
        extras = ' '.join(f"{k}={v}" for k, v in fields.items())
        logger.info(f"{event} {extras}")


def _log_error(logger, event, **fields):
    if hasattr(logger, 'bind'):
        logger.error(event, **fields)
    else:
        extras = ' '.join(f"{k}={v}" for k, v in fields.items())
        logger.error(f"{event} {extras}")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _acquire_locks(db, job_id):
    if not acquire_job_lock(job_id):
        return False
    if not job_tracker.acquire_job_lock(db, job_id):
        release_job_lock(job_id)
        return False
    return True


def _release_locks(db, job_id):
    try:
        job_tracker.release_job_lock(db, job_id)
    except Exception:
        pass
    try:
        release_job_lock(job_id)
    except Exception:
        pass


def _check_post_step_control(db, job_id):
    job = job_tracker.get_strategy_job(db, job_id)
    if not job:
        return None

    if bool(job.get("cancel_requested", False)) or job.get("control_state") == "cancelling":
        return job_tracker.update_strategy_job(db, job_id, status="cancelled", control_state="cancelled")

    if job.get("control_state") == "paused":
        return job_tracker.update_strategy_job(db, job_id, status="paused")

    return None


def run_research_job(job_id: str):
    main = _main_module()
    db = main.get_db()
    job = job_tracker.get_strategy_job(db, job_id)
    if not job:
        return

    if job.get("cancel_requested") or job.get("control_state") == "cancelling":
        job_tracker.update_strategy_job(db, job_id, status="cancelled", control_state="cancelled")
        return

    try:
        check_control_state(job, db)
    except PauseExecution:
        return
    except Exception:
        return

    if not should_run_step(job, "research"):
        return

    mark_step_start(db, job_id, "research")

    max_retries = job.get("max_retries", 2) or 2
    attempt = (job.get("retry_count", 0) or 0) + 1

    if not _acquire_locks(db, job_id):
        return

    try:
        job_tracker.update_strategy_job(db, job_id, status="running", started_at=_now(), current_step="research", progress=5, retry_count=attempt, last_heartbeat=_now())
        payload = job.get("input_payload", {}) or {}
        project_id = payload.get("project_id")
        session_id = payload.get("session_id", "")
        customer_url = payload.get("customer_url", "")
        competitor_urls = payload.get("competitor_urls", [])

        main._run_research_job(job_id, project_id, session_id, customer_url, competitor_urls)

        mark_step_complete(db, job_id, "research", progress=100)

        _check_post_step_control(db, job_id)

        job_tracker.update_strategy_job(db, job_id, status="completed", completed_at=_now(), last_heartbeat=_now())
    except PauseExecution:
        return
    except Exception as exc:
        backoff_seconds = min(30, 2 ** (attempt - 1))
        if attempt >= max_retries:
            job_tracker.update_strategy_job(db, job_id, status="failed", retry_count=attempt, error_message=str(exc), error_type="provider_error", completed_at=_now())
        else:
            job_tracker.update_strategy_job(db, job_id, status="retrying", retry_count=attempt, error_message=str(exc), error_type="provider_error")
            time.sleep(backoff_seconds)
        raise
    finally:
        _release_locks(db, job_id)


def run_score_job(job_id: str):
    main = _main_module()
    db = main.get_db()
    job = job_tracker.get_strategy_job(db, job_id)
    if not job:
        return

    if job.get("cancel_requested") or job.get("control_state") == "cancelling":
        job_tracker.update_strategy_job(db, job_id, status="cancelled", control_state="cancelled")
        return

    try:
        check_control_state(job, db)
    except PauseExecution:
        return
    except Exception:
        return

    if not should_run_step(job, "score"):
        return

    mark_step_start(db, job_id, "score")

    max_retries = job.get("max_retries", 2) or 2
    attempt = (job.get("retry_count", 0) or 0) + 1

    if not _acquire_locks(db, job_id):
        return

    try:
        job_tracker.update_strategy_job(db, job_id, status="running", started_at=_now(), current_step="scoring", progress=5, retry_count=attempt, last_heartbeat=_now())
        payload = job.get("input_payload", {}) or {}
        project_id = payload.get("project_id")
        session_id = payload.get("session_id")

        main._run_score_job(job_id, project_id, session_id)

        mark_step_complete(db, job_id, "score", progress=100)

        _check_post_step_control(db, job_id)

        job_tracker.update_strategy_job(db, job_id, status="completed", completed_at=_now(), last_heartbeat=_now())
    except PauseExecution:
        return
    except Exception as exc:
        backoff_seconds = min(30, 2 ** (attempt - 1))
        if attempt >= max_retries:
            job_tracker.update_strategy_job(db, job_id, status="failed", retry_count=attempt, error_message=str(exc), error_type="provider_error", completed_at=_now())
        else:
            job_tracker.update_strategy_job(db, job_id, status="retrying", retry_count=attempt, error_message=str(exc), error_type="provider_error")
            time.sleep(backoff_seconds)
        raise
    finally:
        _release_locks(db, job_id)


def _save_step_output(db, job_id, step, output):
    field_map = {
        "keyword": "keywords",
        "serp": "serp",
        "strategy": "strategy",
        "linking": "links",
        "scoring": "scores",
    }
    field = field_map.get(step)
    if field:
        job_tracker.update_strategy_job(db, job_id, **{field: output})


def _run_pipeline_step(job, step, db=None, job_id=None):
    if step == "input":
        return job.get("input_payload", {})

    if step == "keyword":
        payload = job.get("input_payload", {}) or {}
        seed_keywords = payload.get("seed_keywords") or payload.get("pillars") or payload.get("keywords") or []
        if isinstance(seed_keywords, str):
            seed_keywords = [seed_keywords]

        clusters = []
        for i, kw in enumerate(seed_keywords[:20]):
            clusters.append({"primary_keyword": kw, "keywords": [kw]})

        return {"clusters": clusters}

    if step == "serp":
        clusters = (job.get("keywords") or {}).get("clusters", [])
        serp_engine = SERPEngine(db)
        serp_results = {
            "keyword": None,
            "friendly_summary": [],
            "organic_results": [],
        }

        for cluster in clusters:
            keyword = cluster.get("primary_keyword") or (cluster.get("keywords") or [None])[0]
            if not keyword:
                continue

            try:
                result = serp_engine.get_serp(keyword, project_id=job.get("project_id"), job_id=job_id)
            except TypeError:
                # backward compatibility for providers without job_id parameter
                result = serp_engine.get_serp(keyword, project_id=job.get("project_id"))
            serp_results["keyword"] = keyword
            serp_results["friendly_summary"].append({
                "keyword": keyword,
                "count": len(result.get("organic_results", [])),
            })
            serp_results["organic_results"].extend(result.get("organic_results", []))

        return serp_results

    if step == "strategy":
        context = {
            **(job.get("input_payload") or {}),
            "keyword_strategy": job.get("keywords", {}),
            "serp_intelligence": job.get("serp", {}),
        }
        engine = FinalStrategyEngine(DefaultLLMClient())

        strategy_logger = get_logger("strategy")
        strategy_logger = bind_context(strategy_logger, job_id=job_id, project_id=job.get("project_id"), step="strategy")

        step_start = time.time()
        result = engine.run(context)
        duration_ms = int((time.time() - step_start) * 1000)

        if strategy_step_duration_seconds is not None:
            strategy_step_duration_seconds.observe(duration_ms / 1000.0)

        if result.get("success"):
            log_event(strategy_logger, "info", "strategy_step", status="success", duration_ms=duration_ms)
        else:
            log_event(strategy_logger, "warning", "strategy_step", status="invalid", error=result.get("error"), duration_ms=duration_ms)

        raw_response = result.get('raw', '')

        # Persist raw LLM output into strategy_jobs row for debugging
        if db is not None and job_id is not None and raw_response:
            job_tracker.update_strategy_job(db, job_id, raw_llm_response=raw_response)

        # Audit and metrics for LLM
        tokens = result.get("tokens_used", 0) or 0
        cost_usd = result.get("cost_usd", 0.0) or 0.0
        if llm_tokens_total is not None:
            llm_tokens_total.labels(model="claude").inc(tokens)
        if llm_cost_usd_total is not None:
            llm_cost_usd_total.labels(model="claude").inc(cost_usd)

        if db is not None and job_id is not None:
            save_llm_audit(
                db,
                job_id=job_id,
                step='strategy',
                prompt='',
                raw_output=raw_response,
                validated_output=result.get('data') if result.get('success') else {},
                error=result.get('error', '') or '',
                attempt=0,
                model='claude',
                tokens=tokens,
                cost_usd=cost_usd,
            )

        if not result.get("success"):
            err_msg = str(result.get("error", "unknown"))
            err_type = result.get("error_type", "strategy_error")
            # Accept missing API key as partial success and preserve prefix outputs
            if "No ANTHROPIC_API_KEY" in err_msg or "No ANTHROPIC_API_KEY set" in err_msg:
                log_event(strategy_logger, "warning", "strategy_partial_success", status="partial_success", error=err_msg, duration_ms=duration_ms)
                if db is not None and job_id is not None:
                    job_tracker.update_strategy_job(db, job_id, status="partial_success", error_message=err_msg, error_type=err_type, completed_at=_now(), last_heartbeat=_now())
                return result.get("data", {}) or {}
            raise RuntimeError(err_type + ": " + err_msg)

        # enforce llm token quota by project
        project_id = (job.get("project_id") or "")
        if project_id:
            allowed, used, limit = check_and_consume_quota(db, project_id, "llm_tokens", result.get("tokens_used", 0) or 0)
            if not allowed:
                raise RuntimeError(f"llm_tokens quota exceeded: {used}/{limit}")

        return result.get("data", {})

    if step == "linking":
        content_pieces = (job.get("strategy") or {}).get("content_strategy", {}).get("content_pieces", [])
        return plan_links(content_pieces)

    if step == "scoring":
        serp_data = job.get("serp", {})
        link_data = job.get("links", {})
        content_pieces = (job.get("strategy") or {}).get("content_strategy", {}).get("content_pieces", [])
        return ScoringEngine().run(serp_data, link_data, content_pieces)

    return {}


def run_pipeline_job(job_id: str, project_id: str, seed: str, language: str = "english", region: str = "india", sequential: bool = False):
    main = _main_module()
    db = main.get_db()
    job = job_tracker.get_strategy_job(db, job_id)
    if not job:
        return

    if job.get("cancel_requested") or job.get("control_state") == "cancelling":
        job_tracker.update_strategy_job(db, job_id, status="cancelled", control_state="cancelled")
        return

    try:
        check_control_state(job, db)
    except PauseExecution:
        return
    except Exception:
        return

    if not _acquire_locks(db, job_id):
        return

    _logger = get_logger("jobqueue.pipeline")
    if hasattr(_logger, 'bind'):
        log = _logger.bind(job_id=job_id, project_id=project_id)
    else:
        log = _logger
    if jobs_total is not None:
        jobs_total.inc()
    start_ts = time.time()

    if sentry_sdk is not None:
        sentry_sdk.set_context("job", {"job_id": job_id, "project_id": project_id})
    try:
        while True:
            job = job_tracker.get_strategy_job(db, job_id)
            step = get_next_step(job)

            if step is None:
                job_tracker.update_strategy_job(db, job_id, status="completed", progress=100, current_step="completed", last_completed_step=len(STEPS))
                return

            if not should_run_step(job, step):
                job_tracker.update_strategy_job(db, job_id, current_step=step, last_heartbeat=_now())
                continue

            mark_step_start(db, job_id, step)
            step_start = time.time()
            try:
                output = _run_pipeline_step(job, step, db=db, job_id=job_id)
                _save_step_output(db, job_id, step, output)

                progress = STEP_PROGRESS.get(step, job.get("progress", 0))
                mark_step_complete(db, job_id, step, progress=progress)
                _check_post_step_control(db, job_id)
            except PauseExecution:
                _log_info(log, "job_paused")
                return
            except Exception as exc:
                if jobs_failed is not None:
                    jobs_failed.inc()
                current_retry = (job.get("retry_count", 0) or 0) + 1
                _log_error(log, "step_failed", step=step, error=str(exc), retry=current_retry)
                job_tracker.update_strategy_job(db, job_id, retry_count=current_retry, status="retrying", error_message=str(exc), error_type="pipeline_error", failed_step=step, last_heartbeat=_now())
                if current_retry > (job.get("max_retries", 2) or 2):
                    job_tracker.update_strategy_job(db, job_id, status="failed", error_message=str(exc), error_type="pipeline_error", failed_step=step, completed_at=_now(), last_heartbeat=_now())
                    return
                backoff = min(30, 2 ** current_retry)
                time.sleep(backoff)
                continue
            finally:
                duration = time.time() - step_start
                if step_duration_seconds is not None:
                    step_duration_seconds.labels(step=step).observe(duration)
                _log_info(log, "step_complete", step=step, duration_seconds=duration)
    except Exception as exc:
        if jobs_failed is not None:
            jobs_failed.inc()
        _log_error(log, "job_failed", error=str(exc))
        job_tracker.update_strategy_job(db, job_id, status="failed", error_message=str(exc), error_type="pipeline_error", completed_at=_now())
    finally:
        duration = time.time() - start_ts
        if job_duration_seconds is not None:
            job_duration_seconds.observe(duration)
        _log_info(log, "job_finished", duration_seconds=duration, status=job_tracker.get_strategy_job(db, job_id).get("status", "unknown"))
        _release_locks(db, job_id)


def run_seo_sync_job(job_id: str, project_id: str, gsc_rows: list, ga4_rows: list):
    main = _main_module()
    db = main.get_db()
    job = job_tracker.get_strategy_job(db, job_id)
    if not job:
        return

    if job.get("cancel_requested") or job.get("control_state") == "cancelling":
        job_tracker.update_strategy_job(db, job_id, status="cancelled", control_state="cancelled")
        return

    try:
        check_control_state(job, db)
    except PauseExecution:
        return
    except Exception:
        return

    if not _acquire_locks(db, job_id):
        return

    try:
        job_tracker.update_strategy_job(db, job_id, status="running", current_step="seo_sync", progress=5, last_heartbeat=_now())

        gsc_metrics = ingest_gsc(db, project_id, gsc_rows)
        ga4_metrics = ingest_ga4(db, project_id, ga4_rows)
        results = sync_to_experiments(db, project_id, gsc_metrics, ga4_metrics)

        job_tracker.update_strategy_job(db, job_id, status="completed", result_payload={"results": results}, progress=100, current_step="seo_sync", completed_at=_now(), last_heartbeat=_now())
        return results
    except Exception as exc:
        job_tracker.update_strategy_job(db, job_id, status="failed", error_message=str(exc), error_type="sync_error", completed_at=_now(), last_heartbeat=_now())
        raise
    finally:
        _release_locks(db, job_id)


def run_develop_job(job_id: str, project_id: str, body_dict: dict):
    main = _main_module()
    db = main.get_db()
    job = job_tracker.get_strategy_job(db, job_id)
    if not job:
        return

    if job.get("cancel_requested") or job.get("control_state") == "cancelling":
        job_tracker.update_strategy_job(db, job_id, status="cancelled", control_state="cancelled")
        return

    try:
        check_control_state(job, db)
    except PauseExecution:
        return
    except Exception:
        return

    if not should_run_step(job, "develop"):
        return

    max_retries = job.get("max_retries", 2) or 2
    attempt = (job.get("retry_count", 0) or 0) + 1

    if not _acquire_locks(db, job_id):
        return

    try:
        job_tracker.update_strategy_job(db, job_id, status="running", started_at=_now(), current_step="P1", progress=10, retry_count=attempt, last_heartbeat=_now())
        main._run_strategy_job(job_id, project_id, body_dict, str(main.get_db()))

        mark_step_complete(db, job_id, "develop", progress=100)
        _check_post_step_control(db, job_id)

        job_tracker.update_strategy_job(db, job_id, status="completed", progress=100, completed_at=_now(), last_heartbeat=_now(), last_completed_step=4)
    except PauseExecution:
        return
    except Exception as exc:
        backoff_seconds = min(30, 2 ** (attempt - 1))
        if attempt >= max_retries:
            job_tracker.update_strategy_job(db, job_id, status="failed", retry_count=attempt, error_message=str(exc), error_type="provider_error", completed_at=_now())
        else:
            job_tracker.update_strategy_job(db, job_id, status="retrying", retry_count=attempt, error_message=str(exc), error_type="provider_error")
            time.sleep(backoff_seconds)
        raise
    finally:
        _release_locks(db, job_id)


def run_final_job(job_id: str, project_id: str, universe_result: dict, project: dict):
    main = _main_module()
    db = main.get_db()
    job = job_tracker.get_strategy_job(db, job_id)
    if not job:
        return

    if job.get("cancel_requested") or job.get("control_state") == "cancelling":
        job_tracker.update_strategy_job(db, job_id, status="cancelled", control_state="cancelled")
        return

    try:
        check_control_state(job, db)
    except PauseExecution:
        return
    except Exception:
        return

    if not should_run_step(job, "final"):
        return

    max_retries = job.get("max_retries", 2) or 2
    attempt = (job.get("retry_count", 0) or 0) + 1

    if not _acquire_locks(db, job_id):
        return

    try:
        job_tracker.update_strategy_job(db, job_id, status="running", started_at=_now(), current_step="final", progress=10, retry_count=attempt, last_heartbeat=_now())
        main._run_final_strategy_job(job_id, project_id, universe_result, project, str(main.get_db()))

        mark_step_complete(db, job_id, "final", progress=100)
        _check_post_step_control(db, job_id)

        job_tracker.update_strategy_job(db, job_id, status="completed", progress=100, completed_at=_now(), last_heartbeat=_now(), last_completed_step=5)
    except PauseExecution:
        return
    except Exception as exc:
        backoff_seconds = min(30, 2 ** (attempt - 1))
        if attempt >= max_retries:
            job_tracker.update_strategy_job(db, job_id, status="failed", retry_count=attempt, error_message=str(exc), error_type="provider_error", completed_at=_now())
        else:
            job_tracker.update_strategy_job(db, job_id, status="retrying", retry_count=attempt, error_message=str(exc), error_type="provider_error")
            time.sleep(backoff_seconds)
        raise
    finally:
        _release_locks(db, job_id)


def _record_ai_usage(db, project_id, job_id, model, tokens_used, cost_usd, purpose):
    try:
        db.execute(
            "INSERT INTO ai_usage (project_id, run_id, model, input_tokens, output_tokens, cost_usd, purpose) VALUES (?,?,?,?,?,?,?)",
            (project_id, job_id, model, tokens_used, 0, cost_usd, purpose),
        )
        db.commit()
    except Exception:
        pass


def run_single_call_job(job_id: str):
    main = _main_module()
    db = main.get_db()
    job = job_tracker.get_strategy_job(db, job_id)
    if not job:
        return

    if job.get("cancel_requested") or job.get("control_state") == "cancelling":
        job_tracker.update_strategy_job(db, job_id, status="cancelled", control_state="cancelled")
        return

    schema = load_strategy_schema()
    max_retries = job.get("max_retries", 2) or 2
    retry_count = job.get("retry_count", 0) or 0

    if not _acquire_locks(db, job_id):
        return

    try:
        while retry_count <= max_retries:
            try:
                job_tracker.update_strategy_job(db, job_id, status="running", current_step="single_call", current_step_name="single_call", progress=10, retry_count=retry_count, last_heartbeat=_now())

                input_data = job.get("input_payload", {}) or {}
                project_data = {"project_id": job.get("project_id")}

                engine = FinalStrategyEngine(DefaultLLMClient())
                result = engine.run(input_data)

                raw_response = result.get("raw")
                if raw_response is None:
                    raise RuntimeError("FinalStrategyEngine returned no raw response")

                job_tracker.update_strategy_job(db, job_id, raw_llm_response=raw_response, progress=80)

                if not result.get("success"):
                    err = result.get("error", "Unknown error")
                    etype = result.get("error_type", "provider_error")
                    job_tracker.update_strategy_job(db, job_id,
                        error_type=etype,
                        error_message=err,
                        validation_status=result.get("validation_status", "invalid"),
                        raw_llm_response=raw_response,
                        tokens_used=result.get("tokens_used", 0),
                        cost_usd=result.get("cost_usd", 0.0),
                        retry_count=retry_count,
                    )
                    raise ValueError(f"{etype}: {err}")

                parsed = result.get("data")
                if not isinstance(parsed, dict):
                    job_tracker.update_strategy_job(db, job_id, error_type="parse_error", error_message="parsed data is not dict", validation_status="invalid", raw_llm_response=raw_response, tokens_used=result.get("tokens_used", 0), cost_usd=result.get("cost_usd", 0.0), retry_count=retry_count)
                    raise ValueError("parse_error: parsed data is not dict")

                valid, schema_err = validate_strategy_output(parsed, schema)
                if not valid:
                    job_tracker.update_strategy_job(db, job_id, error_type="schema_error", error_message=schema_err, validation_status="invalid", raw_llm_response=raw_response, tokens_used=result.get("tokens_used", 0), cost_usd=result.get("cost_usd", 0.0), retry_count=retry_count)
                    raise ValueError(f"schema_error: {schema_err}")

                # success
                job_tracker.update_strategy_job(db, job_id,
                    result_payload=parsed,
                    raw_llm_response=raw_response,
                    validation_status="valid",
                    tokens_used=result.get("tokens_used", 0),
                    cost_usd=result.get("cost_usd", 0.0),
                    progress=100,
                    error_type="",
                    error_message="",
                    last_heartbeat=_now(),
                )
                mark_step_complete(db, job_id, "final", progress=100)
                _check_post_step_control(db, job_id)
                job_tracker.update_strategy_job(db, job_id, status="completed", progress=100, completed_at=_now(), last_completed_step=5, last_heartbeat=_now())
                _record_ai_usage(db, job.get("project_id"), job_id, "claude", result.get("tokens_used", 0), result.get("cost_usd", 0.0), "strategy")
                return

            except PauseExecution:
                return
            except Exception as exc:
                retry_count += 1
                err_type = "provider_error"
                if isinstance(exc, ValueError):
                    if str(exc).startswith("parse_error"):
                        err_type = "parse_error"
                    elif str(exc).startswith("schema_error"):
                        err_type = "schema_error"

                if retry_count > max_retries:
                    job_tracker.update_strategy_job(db, job_id, status="failed", retry_count=retry_count, error_message=str(exc), error_type=err_type, completed_at=_now())
                    _record_ai_usage(db, job.get("project_id"), job_id, "claude",
                                     result.get("tokens_used", 0) if isinstance(result, dict) else 0,
                                     result.get("cost_usd", 0.0) if isinstance(result, dict) else 0.0,
                                     "strategy")
                    return

                job_tracker.update_strategy_job(db, job_id, status="retrying", retry_count=retry_count, error_message=str(exc), error_type=err_type)
                delay = min(2 ** retry_count, 30)
                time.sleep(delay)
                continue

    finally:
        _release_locks(db, job_id)


def enqueue_pipeline_job(job_id: str):
    db = get_db()
    job = job_tracker.get_strategy_job(db, job_id)
    if not job:
        return

    payload = job.get("input_payload") or {}
    project_id = job.get("project_id") or payload.get("project_id")
    seed = payload.get("pillar") or payload.get("seed")

    if not project_id or not seed:
        return

    pipeline_queue.enqueue(run_pipeline_job, job_id, project_id, seed, job_timeout=7200, retry=2)
