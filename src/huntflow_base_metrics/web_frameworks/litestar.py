import time
from contextvars import ContextVar
from functools import wraps
from typing import Any, Callable, Iterable, Optional, Type

from litestar import Request, Response
from litestar.enums import ScopeType
from litestar.middleware import AbstractMiddleware
from litestar.types import ASGIApp, Message, Receive, Scope, Send

from huntflow_base_metrics.export import export_to_http_response
from huntflow_base_metrics.web_frameworks._middleware import (
    PathTemplate,
    PrometheusMiddleware,
    RequestContext,
)

__all__ = ["exception_context", "get_http_response_metrics", "get_middleware"]


class _ExceptionContext:
    context = ContextVar("ExceptionType", default="")

    def get(self) -> Optional[str]:
        return self.context.get() or None

    def set(self, value: str) -> None:
        self.context.set(value)


exception_context = _ExceptionContext()


class _PrometheusMiddleware(PrometheusMiddleware[Request], AbstractMiddleware):
    scopes = {ScopeType.HTTP}

    def __init__(self, app: ASGIApp, *args: Any, **kwargs: Any) -> None:
        self.app = app
        super().__init__(app, *args, **kwargs)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        request = Request[Any, Any, Any](scope, receive)
        ctx = self.get_request_context(request)

        if not self.need_process(ctx):
            await self.app(scope, receive, send)
            return

        self.count_request_before(ctx)

        send_wrapper = self._get_send_wrapper(send, ctx)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            self.count_request_after(ctx)
            exception_type = exception_context.get()
            if exception_type:
                self.count_request_exceptions(ctx, exception_type)

    @staticmethod
    def _get_send_wrapper(send: Send, ctx: RequestContext) -> Callable:
        @wraps(send)
        async def wrapped_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                ctx.status_code = message["status"]

            if message["type"] == "http.response.body":
                ctx.end_time = time.perf_counter()

            await send(message)

        return wrapped_send

    @staticmethod
    def get_method(request: Request) -> str:
        return request.method

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
