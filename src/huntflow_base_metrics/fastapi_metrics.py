import time
from typing import List, Optional, Tuple

from fastapi import FastAPI
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Match
from starlette.status import HTTP_500_INTERNAL_SERVER_ERROR

from .base_metrics import REGISTRY, apply_labels, register_metric

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


class _PrometheusMiddleware(BaseHTTPMiddleware):
    include_routes: Optional[List[str]] = None
    exclude_routes: Optional[List[str]] = None

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        method = request.method
        path_template, is_handled_path = self.get_path_template(request)

        if not is_handled_path or self._is_path_excluded(path_template):
            return await call_next(request)

        apply_labels(REQUESTS_IN_PROGRESS, method=method, path_template=path_template).inc()
        apply_labels(REQUESTS, method=method, path_template=path_template).inc()

        before_time = time.perf_counter()
        status_code = HTTP_500_INTERNAL_SERVER_ERROR
        try:
            response = await call_next(request)
        except BaseException as e:
            apply_labels(
                EXCEPTIONS,
                method=method,
                path_template=path_template,
                exception_type=type(e).__name__,
            ).inc()
            raise
        else:
            status_code = response.status_code
            after_time = time.perf_counter()
            apply_labels(
                REQUESTS_PROCESSING_TIME, method=method, path_template=path_template
            ).observe(after_time - before_time)
        finally:
            apply_labels(
                RESPONSES,
                method=method,
                path_template=path_template,
                status_code=str(status_code),
            ).inc()
            apply_labels(
                REQUESTS_IN_PROGRESS,
                method=method,
                path_template=path_template,
            ).dec()

        return response

    @classmethod
    def _is_path_excluded(cls, path_template: str) -> bool:
        if cls.include_routes:
            return path_template not in cls.include_routes
        if cls.exclude_routes:
            return path_template in cls.exclude_routes
        return False

    @staticmethod
    def get_path_template(request: Request) -> Tuple[str, bool]:
        for route in request.app.routes:
            match, _ = route.matches(request.scope)
            if match == Match.FULL:
                return route.path, True

        return request.url.path, False


def add_middleware(
    app: FastAPI,
    include_routes: Optional[List[str]] = None,
    exclude_routes: Optional[List[str]] = None,
) -> None:
    """Add observing middleware to the given FastAPI application.
    :param include_routes: optional list of path templates to observe.
        If it's not empty, then only the specified routes will be observed
        (also exclude_routes will be ignored).
    :param exclude_routes: optional list of path templates to not observer.
        If it's not empty (and include_routes is not specified), then the
        specified routes will not be observed.
    """
    _PrometheusMiddleware.include_routes = include_routes
    _PrometheusMiddleware.exclude_routes = exclude_routes
    app.add_middleware(_PrometheusMiddleware)


def get_http_response_metrics() -> Response:
    """Method returns HTTP Response with current metrics in prometheus format."""
    return Response(generate_latest(REGISTRY), headers={"Content-Type": CONTENT_TYPE_LATEST})
