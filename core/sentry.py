import os

try:
    import sentry_sdk
except ModuleNotFoundError:
    sentry_sdk = None


def setup_sentry():
    if sentry_sdk is None:
        return
    dsn = os.getenv("SENTRY_DSN", "")
    if not dsn:
        return

    sentry_sdk.init(
        dsn=dsn,
        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
        environment=os.getenv("ENVIRONMENT", "development"),
    )
