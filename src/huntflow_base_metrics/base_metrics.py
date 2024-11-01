"""Base definitions for metrics collections via prometheus client."""

import logging
import platform
import time
import uuid
from contextlib import suppress
from functools import wraps
from typing import Any, Callable, List, Optional, Type

from prometheus_client import (
    CollectorRegistry,
    Gauge,
    Histogram,
)
from prometheus_client.metrics import MetricWrapperBase, T

from ._context import MetricsContext as _MetricsContext
from .metrics_export import start_export_to_file, stop_export_to_file

LOGGER = logging.getLogger(__name__)
REGISTRY = CollectorRegistry()
INSTANCE_ID = platform.node() or str(uuid.uuid4())


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


def register_metric(type_: Type[T], name: str, description: str, labels: List[str]) -> T:
    """Create and register a new metric with the given `type_`.
    :param type_: a prometheus_client class, must be nested from
        MetricWrapperBase class. Examples: Histogram, Counter, etc.
    :param name: unique metric name
    :param description: metric short description
    :param labels: list of metric-specific labels. It shouldn't include
        labels defined in COMMON_LABELS, because these labels will be added
        implicitely.

    Raises ValueError if `name` is already registered.
    """
    if name in _MetricsContext.metrics_by_names:
        raise ValueError(f"Metric '{name}' already registered")
    metric = type_(
        name,
        description,
        COMMON_LABELS + labels,
        registry=REGISTRY,
    )
    _MetricsContext.metrics_by_names[name] = metric
    _MetricsContext.metrics_by_objects[metric] = (name, labels)
    return metric


def register_method_observe_histogram(name: str, description: str) -> Histogram:
    """Create and register a new Histogram.
    The created Histogram will contain label `method` and is suitable to pass
    it to `observe_metrics` decorator.
    """
    return register_metric(Histogram, name, description, ["method"])


def register_method_observe_gauge(name: str, description: str) -> Gauge:
    """Create and register a new Gauge.
    The created Gauge will contain label `method` and is suitable to pass
    it to `observe_metrics` decorator.
    """
    return register_metric(Gauge, name, description, ["method"])


def get_metric(name: str) -> MetricWrapperBase:
    return _MetricsContext.metrics_by_names[name]


def apply_labels(metric: T, **labels: str) -> T:
    """Apply labels for a given metric.
    Requires the same lables that was passed during metric creation
    (see `register_metric` method)
    Checks if the given set of labels is the same that was defined
    when the metrics was registered. If labels don't match, raises ValueError.
    Also applies common labels values implicetly.
    """
    metric_name, expected_labels = _MetricsContext.metrics_by_objects[metric]
    if set(expected_labels) != set(labels):
        raise ValueError(f"Invalid labels set ({list(labels)}) for metric '{metric_name}'")
    return metric.labels(**COMMON_LABELS_VALUES, **labels)


def start_metrics(
    facility_name: str,
    facility_id: str,
    out_file_path: Optional[str] = None,
    enabled: bool = True,
    write_to_file: bool = False,
    file_update_interval: float = 15,
) -> None:
    """Method to initialize metrics_collection.
    :params facility_name: string to specify a service/application name for metrics.
        Will be passed to prometheus as `service` label for all metrics.
    :param facility_id: string to specify an inistance/pod/container of the service.
        If it's empty, then will be used HOSTNAME or a random string.
        It will be passed to prometheus as `pod` label for all metrics.
    :param out_file_path: path in filesystem where will be written metrics.
        May be empty if `write_to_file` is False.
    :param enabled: enable or disable metrics collection.
    :param write_to_file: enable or disable writing metrics
        to file `out_file_path`.
    :param file_update_interval: pause in seconds between saving metrics to `out_file_path` file
    """
    _MetricsContext.enable_metrics = enabled
    _MetricsContext.registry = REGISTRY
    if facility_name:
        COMMON_LABELS_VALUES[SERVICE_LABEL] = facility_name
    if facility_id:
        COMMON_LABELS_VALUES[POD_LABEL] = facility_id
    if enabled and write_to_file:
        if not out_file_path:
            raise ValueError("Empty file path while enabled writing to file")
        start_export_to_file(out_file_path, file_update_interval)
    for metric in _MetricsContext.metrics_by_objects:
        with suppress(ValueError):
            # there is no public interface in registry/collectors to check if the
            # metric is already registered. So just catch names conflict and
            # ignore it
            REGISTRY.register(metric)


def stop_metrics() -> None:
    """Method to stop all background tasks initialized by `start_metrics`.
    Actually handle only the background task to write metrics to a file.
    """
    _MetricsContext.enable_metrics = False
    for metric in _MetricsContext.metrics_by_objects:
        with suppress(KeyError):
            REGISTRY.unregister(metric)
        metric.clear()
    stop_export_to_file()


def observe_metrics(
    method: str, metric_timings: Histogram, metric_inprogress: Optional[Gauge] = None
) -> Callable:
    """Decorator to measure timings of some method
    Applicable only for async methods.
    :param method: `method` label value for observed method/function
    :param metric_timings: histogram collector to observe timing
    :param metric_inprogress: optional Gauge collector to observe in progress
        counter.
    """

    def wrap(coro: Callable) -> Callable:
        @wraps(coro)
        async def _wrapper(*args: Any, **kwargs: Any) -> Any:
            if not _MetricsContext.enable_metrics:
                return await coro(*args, **kwargs)
            start = time.perf_counter()
            if metric_inprogress is not None:
                apply_labels(metric_inprogress, method=method).inc()
            try:
                return await coro(*args, **kwargs)
            finally:
                end = time.perf_counter()
                apply_labels(metric_timings, method=method).observe(end - start)
                if metric_inprogress is not None:
                    apply_labels(metric_inprogress, method=method).dec()

        return _wrapper

    return wrap
