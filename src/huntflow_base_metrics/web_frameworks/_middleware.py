import abc
import time
from dataclasses import dataclass
from typing import Any, Optional, Set

from huntflow_base_metrics import apply_labels
from huntflow_base_metrics._context import METRIC_CONTEXT
from huntflow_base_metrics.web_frameworks._request_metrics import (
    EXCEPTIONS,
    REQUESTS,
    REQUESTS_IN_PROGRESS,
    REQUESTS_PROCESSING_TIME,
    RESPONSES,
)


@dataclass(frozen=True)
class PathTemplate:
    value: str
    is_handled: bool


@dataclass
class RequestContext:
    method: str
    path_template: PathTemplate
    start_time: float
    end_time: float = 0
    status_code: int = 200

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time


class PrometheusMiddleware(abc.ABC):
    include_routes: Optional[Set[str]] = None
    exclude_routes: Optional[Set[str]] = None

    @staticmethod
    def get_method(request: Any) -> str:
        return request.method

    @staticmethod
    @abc.abstractmethod
    def get_path_template(request: Any) -> PathTemplate:
        pass

    @classmethod
    def get_request_context(cls, request: Any) -> RequestContext:
        return RequestContext(
            method=cls.get_method(request),
            path_template=cls.get_path_template(request),
            start_time=time.perf_counter(),
        )

    @classmethod
    def need_process(cls, ctx: RequestContext) -> bool:
        return (
            METRIC_CONTEXT.enable_metrics
            and ctx.path_template.is_handled
            and not cls._is_excluded(ctx.path_template)
        )

    @classmethod
    def count_request_before(cls, ctx: RequestContext) -> None:
        apply_labels(
            REQUESTS_IN_PROGRESS,
            method=ctx.method,
            path_template=ctx.path_template.value,
        ).inc()
        apply_labels(REQUESTS, method=ctx.method, path_template=ctx.path_template.value).inc()

    @classmethod
    def count_request_after(cls, ctx: RequestContext) -> None:
        apply_labels(
            REQUESTS_PROCESSING_TIME,
            method=ctx.method,
            path_template=ctx.path_template.value,
        ).observe(ctx.duration)
        apply_labels(
            RESPONSES,
            method=ctx.method,
            path_template=ctx.path_template.value,
            status_code=str(ctx.status_code),
        ).inc()
        apply_labels(
            REQUESTS_IN_PROGRESS,
            method=ctx.method,
            path_template=ctx.path_template.value,
        ).dec()

    @classmethod
    def count_request_exceptions(cls, ctx: RequestContext, exception_type: str) -> None:
        apply_labels(
            EXCEPTIONS,
            method=ctx.method,
            path_template=ctx.path_template.value,
            exception_type=exception_type,
        ).inc()

    @classmethod
    def _is_excluded(cls, path_template: PathTemplate) -> bool:
        if cls.include_routes:
            return path_template.value not in cls.include_routes
        if cls.exclude_routes:
            return path_template.value in cls.exclude_routes
        return False
