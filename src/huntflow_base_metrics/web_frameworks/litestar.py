import time
from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable, Iterable, Set, Type, Optional

from litestar.enums import ScopeType
from litestar.middleware import AbstractMiddleware
from litestar.types import Scope, Receive, Send, ASGIApp, Message

from litestar import Request, Response

from huntflow_base_metrics._context import METRIC_CONTEXT
from huntflow_base_metrics.base import apply_labels
from huntflow_base_metrics.export import export_to_http_response
from huntflow_base_metrics.web_frameworks._request import (
    REQUESTS,
    RESPONSES,
    REQUESTS_PROCESSING_TIME,
    EXCEPTIONS,
    REQUESTS_IN_PROGRESS,
)


class _ExceptionContext:
    context = ContextVar("ExceptionType", default="")

    def get(self) -> Optional[str]:
        return self.context.get() or None

    def set(self, value: str) -> None:
        self.context.set(value)


exception_context = _ExceptionContext()


@dataclass
class RequestSpan:
    start_time: float
    end_time: float = 0
    duration: float = 0
    status_code: int = 200


class _PrometheusMiddleware(AbstractMiddleware):
    include_routes: Optional[Set[str]] = None
    exclude_routes: Optional[Set[str]] = None
    scopes = {ScopeType.HTTP}

    def __init__(self, app: ASGIApp, *args: Any, **kwargs: Any) -> None:
        self.app = app
        super().__init__(app, *args, **kwargs)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        request = Request[Any, Any, Any](scope, receive)
        method = request.method
        path_template = request.scope["path_template"]

        if not METRIC_CONTEXT.enable_metrics or self._is_path_excluded(path_template):
            await self.app(scope, receive, send)
            return

        apply_labels(REQUESTS_IN_PROGRESS, method=method, path_template=path_template).inc()
        apply_labels(REQUESTS, method=method, path_template=path_template).inc()

        span = RequestSpan(start_time=time.perf_counter())
        wrapped_send = self._get_wrapped_send(send, span)

        try:
            await self.app(scope, receive, wrapped_send)
        finally:
            status_code = span.status_code
            apply_labels(
                REQUESTS_PROCESSING_TIME, method=method, path_template=path_template
            ).observe(span.duration)
            apply_labels(
                RESPONSES,
                method=method,
                path_template=path_template,
                status_code=str(status_code),
            ).inc()
            apply_labels(REQUESTS_IN_PROGRESS, method=method, path_template=path_template).dec()
            exception_type = exception_context.get()
            if exception_type:
                apply_labels(
                    EXCEPTIONS,
                    method=method,
                    path_template=path_template,
                    exception_type=exception_type,
                ).inc()

    def _get_wrapped_send(self, send: Send, request_span: RequestSpan) -> Callable:
        @wraps(send)
        async def wrapped_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                request_span.status_code = message["status"]

            if message["type"] == "http.response.body":
                end = time.perf_counter()
                request_span.duration = end - request_span.start_time
                request_span.end_time = end

            await send(message)

        return wrapped_send

    @classmethod
    def _is_path_excluded(cls, path_template: str) -> bool:
        if cls.include_routes:
            return path_template not in cls.include_routes
        if cls.exclude_routes:
            return path_template in cls.exclude_routes
        return False


def get_middleware(
    include_routes: Optional[Iterable[str]] = None,
    exclude_routes: Optional[Iterable[str]] = None,
) -> Type[_PrometheusMiddleware]:
    """
    Returns observing middleware for Litestar application.
    Unlike FastAPI, Litestar does not allow you to add middleware to an existing application.

    :param include_routes: optional list of path templates to observe.
        If it's not empty, then only the specified routes will be observed
        (also exclude_routes will be ignored).
    :param exclude_routes: optional list of path templates to not observer.
        If it's not empty (and include_routes is not specified), then the
        specified routes will not be observed.
    """

    include_routes = set(include_routes) if include_routes is not None else include_routes
    exclude_routes = set(exclude_routes) if exclude_routes is not None else exclude_routes
    _PrometheusMiddleware.include_routes = include_routes
    _PrometheusMiddleware.exclude_routes = exclude_routes

    return _PrometheusMiddleware


def get_http_response_metrics() -> Response:
    """Method returns HTTP Response with current metrics in prometheus format."""
    content, content_type = export_to_http_response()
    return Response(content, headers={"Content-Type": content_type})
