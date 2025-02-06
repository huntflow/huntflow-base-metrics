import time
from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable, Iterable, Optional, Type

from litestar import Request, Response
from litestar.enums import ScopeType
from litestar.middleware import AbstractMiddleware
from litestar.types import ASGIApp, Message, Receive, Scope, Send

from huntflow_base_metrics.base import apply_labels
from huntflow_base_metrics.export import export_to_http_response
from huntflow_base_metrics.web_frameworks._middleware import PathTemplate, PrometheusMiddleware
from huntflow_base_metrics.web_frameworks._request_metrics import (
    EXCEPTIONS,
    REQUESTS,
    REQUESTS_IN_PROGRESS,
    REQUESTS_PROCESSING_TIME,
    RESPONSES,
)

__all__ = ["exception_context", "get_http_response_metrics", "get_middleware"]


class _ExceptionContext:
    context = ContextVar("ExceptionType", default="")

    def get(self) -> Optional[str]:
        return self.context.get() or None

    def set(self, value: str) -> None:
        self.context.set(value)


exception_context = _ExceptionContext()


@dataclass
class _RequestSpan:
    start_time: float
    end_time: float = 0
    duration: float = 0
    status_code: int = 200


class _PrometheusMiddleware(PrometheusMiddleware, AbstractMiddleware):
    scopes = {ScopeType.HTTP}

    def __init__(self, app: ASGIApp, *args: Any, **kwargs: Any) -> None:
        self.app = app
        super().__init__(app, *args, **kwargs)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        request = Request[Any, Any, Any](scope, receive)
        method = request.method
        path_template = self.get_path_template(request)

        if not self.need_process(path_template):
            await self.app(scope, receive, send)
            return

        apply_labels(REQUESTS_IN_PROGRESS, method=method, path_template=path_template.value).inc()
        apply_labels(REQUESTS, method=method, path_template=path_template.value).inc()

        span = _RequestSpan(start_time=time.perf_counter())
        send_wrapper = self._get_send_wrapper(send, span)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            status_code = span.status_code
            apply_labels(
                REQUESTS_PROCESSING_TIME, method=method, path_template=path_template.value
            ).observe(span.duration)
            apply_labels(
                RESPONSES,
                method=method,
                path_template=path_template.value,
                status_code=str(status_code),
            ).inc()
            apply_labels(
                REQUESTS_IN_PROGRESS,
                method=method,
                path_template=path_template.value,
            ).dec()
            exception_type = exception_context.get()
            if exception_type:
                apply_labels(
                    EXCEPTIONS,
                    method=method,
                    path_template=path_template.value,
                    exception_type=exception_type,
                ).inc()

    @staticmethod
    def _get_send_wrapper(send: Send, span: _RequestSpan) -> Callable:
        @wraps(send)
        async def wrapped_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                span.status_code = message["status"]

            if message["type"] == "http.response.body":
                end = time.perf_counter()
                span.duration = end - span.start_time
                span.end_time = end

            await send(message)

        return wrapped_send

    @staticmethod
    def get_path_template(request: Request) -> PathTemplate:
        return PathTemplate(value=request.scope["path_template"], is_handled=True)


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
