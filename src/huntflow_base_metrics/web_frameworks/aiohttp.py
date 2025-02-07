import time
from http import HTTPStatus
from typing import Callable, Iterable, Optional

from aiohttp.web import Application, Request, Response, middleware

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

__all__ = ["add_middleware", "get_http_response_metrics"]


class _PrometheusMiddleware(PrometheusMiddleware):
    @classmethod
    @middleware
    async def dispatch(cls, request: Request, handler: Callable) -> Response:
        method = request.method
        path_template = cls.get_path_template(request)

        if not cls.need_process(path_template):
            return await handler(request)

        apply_labels(REQUESTS_IN_PROGRESS, method=method, path_template=path_template.value).inc()
        apply_labels(REQUESTS, method=method, path_template=path_template.value).inc()

        before_time = time.perf_counter()
        status_code = HTTPStatus.INTERNAL_SERVER_ERROR
        try:
            response = await handler(request)
        except BaseException as e:
            apply_labels(
                EXCEPTIONS,
                method=method,
                path_template=path_template.value,
                exception_type=type(e).__name__,
            ).inc()
            raise
        else:
            status_code = response.status
            after_time = time.perf_counter()
            apply_labels(
                REQUESTS_PROCESSING_TIME, method=method, path_template=path_template.value
            ).observe(after_time - before_time)
        finally:
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

        return response

    @staticmethod
    def get_path_template(request: Request) -> PathTemplate:
        match_info = request.match_info
        value = request.rel_url.path
        if match_info and match_info.route.resource:
            value = match_info.route.resource.canonical
        return PathTemplate(value=value, is_handled=match_info is not None)


def add_middleware(
    app: Application,
    include_routes: Optional[Iterable[str]] = None,
    exclude_routes: Optional[Iterable[str]] = None,
) -> None:
    """
    Add observing middleware to the given AioHTTP application.

    :param app: AioHTTP application.
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
    app.middlewares.append(_PrometheusMiddleware.dispatch)


def get_http_response_metrics() -> Response:
    """Method returns HTTP Response with current metrics in prometheus format."""
    content, content_type = export_to_http_response()
    return Response(body=content, headers={"Content-Type": content_type})
