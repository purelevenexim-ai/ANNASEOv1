import logging
import os
import json

try:
    import structlog
except ModuleNotFoundError:
    structlog = None


def setup_logging(level=logging.INFO):
    logging.basicConfig(
        format="%(message)s",
        level=level,
        handlers=[logging.StreamHandler()],
    )

    if structlog:
        structlog.configure(
            processors=[
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.add_log_level,
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(level),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(),
            cache_logger_on_first_use=True,
        )


def get_logger(name=None):
    if structlog:
        return structlog.get_logger(name or "annaseo")
    return logging.getLogger(name or "annaseo")


def bind_context(logger, **context):
    if structlog:
        return logger.bind(**context)
    return logger


def log_event(logger, level, event, **kwargs):
    if structlog:
        log_func = getattr(logger, level, None)
        if log_func:
            log_func(event, **kwargs)
    else:
        data = {"event": event, **kwargs}
        msg = json.dumps(data, default=str)
        if level == "info":
            logger.info(msg)
        elif level == "warning":
            logger.warning(msg)
        elif level == "error":
            logger.error(msg)
        elif level == "debug":
            logger.debug(msg)
        else:
            logger.info(msg)
