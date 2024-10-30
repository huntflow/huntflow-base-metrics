"""Base definitions for metrics collections via prometheus client.
The module is intended to be moved to a common library for huntflow services.
It's here to test it in production environment.
"""

import asyncio
import logging
import platform
import time
import uuid
from functools import wraps
from typing import Iterable, Optional, Set

import aiofiles
from fastapi import FastAPI
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Match
from starlette.status import HTTP_500_INTERNAL_SERVER_ERROR

LOGGER = logging.getLogger(__name__)
REGISTRY = CollectorRegistry()
INSTANCE_ID = platform.node() or str(uuid.uuid4())

# Limit for a series of exceptions during saving metrics to file.
# Just to not send too much spam to sentry.
# If we failed to write to a file with this limit, the most probably
# we will fail in the future too. Possible errors:
# * not mounted directory (only container restart will help)
# * insufficiient rights to write to the directory
# * no space left on the disk
_MAX_FILE_WRITE_ERRORS = 5

# Label for service name, should be taken from FACILITY_NAME env
SERVICE_LABEL = "service"
# Label for a running instance, should be taken from FACILITY_ID env
POD_LABEL = "pod"

# Labels must be present in all collectors.
# These labels identify the whole service and it's current instance.
# The values should be set via `init_metrics_common` function
# before usage.
COMMON_LABELS = [SERVICE_LABEL, POD_LABEL]
COMMON_LABELS_VALUES = {
    SERVICE_LABEL: "undefined",
    POD_LABEL: INSTANCE_ID,
}

# Metrics labels for HTTP requests stats
HTTP_METRICS_LABELS = ["method", "path_template"]


REQUESTS = Counter(
    "requests_total",
    "Total count of requests by method and path.",
    COMMON_LABELS + HTTP_METRICS_LABELS,
    registry=REGISTRY,
)
RESPONSES = Counter(
    "responses_total",
    "Total count of responses by method, path and status codes.",
    COMMON_LABELS + HTTP_METRICS_LABELS + ["status_code"],
    registry=REGISTRY,
)
REQUESTS_PROCESSING_TIME = Histogram(
    "requests_processing_time_seconds",
    "Histogram of requests processing time by path (in seconds)",
    COMMON_LABELS + HTTP_METRICS_LABELS,
    registry=REGISTRY,
)
EXCEPTIONS = Counter(
    "exceptions_total",
    "Total count of exceptions raised by path and exception type",
    COMMON_LABELS + HTTP_METRICS_LABELS + ["exception_type"],
    registry=REGISTRY,
)
REQUESTS_IN_PROGRESS = Gauge(
    "requests_in_progress",
    "Gauge of requests by method and path currently being processed",
    COMMON_LABELS + HTTP_METRICS_LABELS,
    registry=REGISTRY,
)


class _MetricsContext:
    enable_metrics: bool = False
    write_to_file_task: asyncio.Task | None = None
    include_routes: Optional[Set[str]] = None
    exclude_routes: Optional[Set[str]] = None


def start_metrics(
    facility_name: str,
    facility_id: str,
    out_file_path: str,
    app: FastAPI | None = None,
    enabled=True,
    write_to_file=True,
    file_update_interval=15,
    include_routes: Optional[Iterable[str]] = None,
    exclude_routes: Optional[Iterable[str]] = None,
) -> None:
    """Method to initialize metrics_collection.
    :params facility_name: string to specify a service/application name for metrics.
        Will be passed to prometheus as `service` label for all metrics.
    :param facility_id: string to specify an inistance/pod/container of the service.
        If it's empty, then will be used HOSTNAME or a random string.
        It will be passed to prometheus as `pod` label for all metrics.
    :param out_file_path: path in filesystem where will be written metrics.
        May be empty if `write_to_file` is False.
    :param app: Optional FastAPI application to collect metrics for http requests
    :param enabled: enable or disable metrics collection.
    :param write_to_file: enable or disable writing metrics
        to file `out_file_path`.
    :param file_update_interval: pause in seconds between saving metrics to `out_file_path` file
    :param include_routes: optional list of path templates to observe.
        If it's not empty, then only the specified routes will be observed
        (also exclude_routes will be ignored).
    :param exclude_routes: optional list of path templates to not observer.
        If it's not empty (and include_routes is not specified), then the
        specified routes will not be observed.
    """
    _MetricsContext.enable_metrics = enabled
    if facility_name:
        COMMON_LABELS_VALUES[SERVICE_LABEL] = facility_name
    if facility_id:
        COMMON_LABELS_VALUES[POD_LABEL] = facility_id
    if not enabled:
        LOGGER.info("Metrics disabled. Bypass saving to a file")
        return
    if enabled and write_to_file:
        assert out_file_path
        task = asyncio.create_task(_update_metric_file(out_file_path, file_update_interval))
        _MetricsContext.write_to_file_task = task
    if include_routes is not None:
        _MetricsContext.include_routes = set(include_routes)
    if exclude_routes is not None:
        _MetricsContext.exclude_routes = set(exclude_routes)
    if enabled and app is not None:
        app.add_middleware(_PrometheusMiddleware)


def stop_metrics() -> None:
    """Method to stop all background tasks initialized by `start_metrics`.
    Actually handle only the background task to write metrics to a file.
    """
    task = _MetricsContext.write_to_file_task
    if task is not None:
        task.cancel()
    _MetricsContext.write_to_file_task = None


async def _update_metric_file(file_path: str, update_delay: int) -> None:
    LOGGER.info("Writing metrics to %s", file_path)
    error_count = 0
    while True:
        await asyncio.sleep(update_delay)
        try:
            LOGGER.debug("Updating metrics file")
            async with aiofiles.open(file_path, "wb") as dst:
                await dst.write(generate_latest(REGISTRY))
            error_count = 0
        except asyncio.CancelledError:
            LOGGER.info("Write metric task is cancelled")
            break
        except Exception:
            error_count += 1
            LOGGER.exception("Failed to write metrics to file: %s", file_path)
            if error_count >= _MAX_FILE_WRITE_ERRORS:
                LOGGER.warning("Update metrics file: total number of errors %s. Exit", error_count)
                break


class _PrometheusMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        method = request.method
        path_template, is_handled_path = self.get_path_template(request)

        if not is_handled_path or self._is_path_excluded(path_template):
            return await call_next(request)

        REQUESTS_IN_PROGRESS.labels(
            **COMMON_LABELS_VALUES, method=method, path_template=path_template
        ).inc()
        REQUESTS.labels(**COMMON_LABELS_VALUES, method=method, path_template=path_template).inc()

        before_time = time.perf_counter()
        status_code = HTTP_500_INTERNAL_SERVER_ERROR
        try:
            response = await call_next(request)
        except BaseException as e:
            EXCEPTIONS.labels(
                **COMMON_LABELS_VALUES,
                method=method,
                path_template=path_template,
                exception_type=type(e).__name__,
            ).inc()
            raise
        else:
            status_code = response.status_code
            after_time = time.perf_counter()
            REQUESTS_PROCESSING_TIME.labels(
                **COMMON_LABELS_VALUES, method=method, path_template=path_template
            ).observe(after_time - before_time)
        finally:
            RESPONSES.labels(
                **COMMON_LABELS_VALUES,
                method=method,
                path_template=path_template,
                status_code=status_code,
            ).inc()
            REQUESTS_IN_PROGRESS.labels(
                **COMMON_LABELS_VALUES, method=method, path_template=path_template
            ).dec()

        return response

    @staticmethod
    def _is_path_excluded(path_template):
        if _MetricsContext.include_routes:
            return path_template not in _MetricsContext.include_routes
        if _MetricsContext.exclude_routes:
            return path_template in _MetricsContext.exclude_routes
        return False

    @staticmethod
    def get_path_template(request: Request) -> tuple[str, bool]:
        for route in request.app.routes:
            match, _ = route.matches(request.scope)
            if match == Match.FULL:
                return route.path, True

        return request.url.path, False


def get_http_response_metrics() -> Response:
    """Method returns HTTP Response with current metrics in prometheus format."""
    return Response(generate_latest(REGISTRY), headers={"Content-Type": CONTENT_TYPE_LATEST})


def observe_metrics(method: str, metric_timings: Histogram, metric_inprogress: Gauge | None = None):
    """Decorator to measure timings of some method
    Applicable only for async methods.
    :param method: label value for observed method/function
    :param metric_timings: histogram collector to observe timing
    :param metric_inprogress: optional Gauge collector to observe in progress
        counter.
    """

    def wrap(coro):
        @wraps(coro)
        async def _wrapper(*args, **kwargs):
            if not _MetricsContext.enable_metrics:
                return await coro(*args, **kwargs)
            start = time.perf_counter()
            if metric_inprogress is not None:
                metric_inprogress.labels(**COMMON_LABELS_VALUES, method=method).inc()
            try:
                return await coro(*args, **kwargs)
            finally:
                end = time.perf_counter()
                metric_timings.labels(
                    **COMMON_LABELS_VALUES,
                    method=method,
                ).observe(end - start)
                if metric_inprogress is not None:
                    metric_inprogress.labels(**COMMON_LABELS_VALUES, method=method).dec()

        return _wrapper

    return wrap
