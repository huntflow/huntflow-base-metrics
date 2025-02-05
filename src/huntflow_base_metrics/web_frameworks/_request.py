from prometheus_client import Counter, Histogram, Gauge

from huntflow_base_metrics import register_metric


# Metrics labels for HTTP requests stats
HTTP_METRICS_LABELS = ["method", "path_template"]
REQUESTS = register_metric(
    Counter,
    "requests_total",
    "Total count of requests by method and path.",
    HTTP_METRICS_LABELS,
)
RESPONSES = register_metric(
    Counter,
    "responses_total",
    "Total count of responses by method, path and status codes.",
    HTTP_METRICS_LABELS + ["status_code"],
)
REQUESTS_PROCESSING_TIME = register_metric(
    Histogram,
    "requests_processing_time_seconds",
    "Histogram of requests processing time by path (in seconds)",
    HTTP_METRICS_LABELS,
)
EXCEPTIONS = register_metric(
    Counter,
    "exceptions_total",
    "Total count of exceptions raised by path and exception type",
    HTTP_METRICS_LABELS + ["exception_type"],
)
REQUESTS_IN_PROGRESS = register_metric(
    Gauge,
    "requests_in_progress",
    "Gauge of requests by method and path currently being processed",
    HTTP_METRICS_LABELS,
)
