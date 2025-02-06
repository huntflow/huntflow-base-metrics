from typing import Optional, Sequence
from uuid import uuid4

from litestar import Litestar, MediaType, Request, Response, get
from litestar.status_codes import HTTP_500_INTERNAL_SERVER_ERROR
from litestar.testing import AsyncTestClient

from huntflow_base_metrics import start_metrics
from huntflow_base_metrics.web_frameworks.litestar import (
    exception_context,
    get_http_response_metrics,
    get_middleware,
)

FACILITY_NAME = "test_service"
FACILITY_ID = uuid4().hex


def exception_handler(_: Request, exc: Exception):
    status_code = getattr(exc, "status_code", HTTP_500_INTERNAL_SERVER_ERROR)
    exception_type = type(exc).__name__
    exception_context.set(exception_type)

    return Response(
        media_type=MediaType.JSON,
        content=exception_type,
        status_code=status_code,
    )


def litestar_app(
    include_routes: Optional[Sequence[str]] = None,
    exclude_routes: Optional[Sequence[str]] = None,
) -> AsyncTestClient:
    @get("/valueerror")
    async def value_error() -> None:
        raise ValueError()

    @get("/ok")
    async def ok() -> dict:
        return {"status": "ok"}

    @get("/one")
    async def one() -> dict:
        return {"status": "one"}

    @get("/two")
    async def two() -> dict:
        return {"status": "two"}

    @get("/metrics")
    async def metrics() -> Response:
        return get_http_response_metrics()

    start_metrics(FACILITY_NAME, FACILITY_ID)
    app = Litestar(
        middleware=[get_middleware(include_routes=include_routes, exclude_routes=exclude_routes)],
        route_handlers=[value_error, ok, one, two, metrics],
        exception_handlers={Exception: exception_handler},
    )

    return AsyncTestClient(app)
