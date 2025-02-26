import time
from http import HTTPStatus
from typing import Callable, Iterable, Optional

from aiohttp.web import Application, Request, Response, middleware

from huntflow_base_metrics.export import export_to_http_response
from huntflow_base_metrics.web_frameworks._middleware import PathTemplate, PrometheusMiddleware

__all__ = ["add_middleware", "get_http_response_metrics", "get_middleware"]


class _PrometheusMiddleware(PrometheusMiddleware[Request]):
    @classmethod
    @middleware
    async def dispatch(cls, request: Request, handler: Callable) -> Response:
        ctx = cls.get_request_context(request)
        if not cls.need_process(ctx):
            return await handler(request)

        cls.count_request_before(ctx)

        try:
            response = await handler(request)
        except BaseException as e:
            ctx.status_code = HTTPStatus.INTERNAL_SERVER_ERROR
            cls.count_request_exceptions(ctx, type(e).__name__)
            raise
        else:
            ctx.status_code = response.status
        finally:
            ctx.end_time = time.perf_counter()
            cls.count_request_after(ctx)

        return response

    @staticmethod
    def get_method(request: Request) -> str:
        return request.method

    @staticmethod
    def get_path_template(request: Request) -> PathTemplate:
        match_info = request.match_info
        value = request.rel_url.path
        is_handled = False
        if match_info and match_info.route.resource:
            value = match_info.route.resource.canonical
            is_handled = True
        return PathTemplate(value=value, is_handled=is_handled)


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
    _PrometheusMiddleware.configure(include_routes, exclude_routes)
    app.middlewares.append(_PrometheusMiddleware.dispatch)


def get_middleware(
    include_routes: Optional[Iterable[str]] = None,
    exclude_routes: Optional[Iterable[str]] = None,
) -> Callable:
    """
    Returns observing middleware to the given AioHTTP application.
    Use if middleware order matters.

    :param include_routes: optional set of path templates to observe.
        If it's not empty, then only the specified routes will be observed
        (also exclude_routes will be ignored).
    :param exclude_routes: optional set of path templates to not observe.
        If it's not empty (and include_routes is not specified), then the
        specified routes will not be observed.
    """
    _PrometheusMiddleware.configure(include_routes, exclude_routes)
    return _PrometheusMiddleware.dispatch


def get_http_response_metrics() -> Response:
    """Method returns HTTP Response with current metrics in prometheus format."""
    content, content_type = export_to_http_response()
    return Response(body=content, headers={"Content-Type": content_type})
