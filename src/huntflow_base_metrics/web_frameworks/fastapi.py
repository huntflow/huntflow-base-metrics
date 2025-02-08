import time
from typing import Iterable, Optional

from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Match
from starlette.status import HTTP_500_INTERNAL_SERVER_ERROR

from huntflow_base_metrics.export import export_to_http_response
from huntflow_base_metrics.web_frameworks._middleware import PathTemplate, PrometheusMiddleware

__all__ = ["add_middleware", "get_http_response_metrics"]


class _PrometheusMiddleware(PrometheusMiddleware, BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        ctx = self.get_request_context(request)
        if not self.need_process(ctx):
            return await call_next(request)

        self.count_request_before(ctx)

        try:
            response = await call_next(request)
        except BaseException as e:
            ctx.status_code = HTTP_500_INTERNAL_SERVER_ERROR
            self.count_request_exceptions(ctx, type(e).__name__)
            raise
        else:
            ctx.status_code = response.status_code
        finally:
            ctx.end_time = time.perf_counter()
            self.count_request_after(ctx)

        return response

    @staticmethod
    def get_path_template(request: Request) -> PathTemplate:
        for route in request.app.routes:
            match, _ = route.matches(request.scope)
            if match == Match.FULL:
                return PathTemplate(value=route.path, is_handled=True)

        return PathTemplate(value=request.url.path, is_handled=False)


def add_middleware(
    app: FastAPI,
    include_routes: Optional[Iterable[str]] = None,
    exclude_routes: Optional[Iterable[str]] = None,
) -> None:
    """
    Add observing middleware to the given FastAPI application.

    :param app: FastAPI application.
    :param include_routes: optional set of path templates to observe.
        If it's not empty, then only the specified routes will be observed
        (also exclude_routes will be ignored).
    :param exclude_routes: optional set of path templates to not observe.
        If it's not empty (and include_routes is not specified), then the
        specified routes will not be observed.
    """
    include_routes = set(include_routes) if include_routes is not None else include_routes
    exclude_routes = set(exclude_routes) if exclude_routes is not None else exclude_routes
    _PrometheusMiddleware.include_routes = include_routes
    _PrometheusMiddleware.exclude_routes = exclude_routes
    app.add_middleware(_PrometheusMiddleware)


def get_http_response_metrics() -> Response:
    """Method returns HTTP Response with current metrics in prometheus format."""
    content, content_type = export_to_http_response()
    return Response(content, headers={"Content-Type": content_type})
