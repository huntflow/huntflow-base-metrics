from typing import Optional, Sequence
from uuid import uuid4

from aiohttp.test_utils import TestClient, TestServer
from aiohttp.web import RouteTableDef, json_response
from aiohttp.web_app import Application

from huntflow_base_metrics import start_metrics
from huntflow_base_metrics.web_frameworks.aiohttp import add_middleware, get_http_response_metrics

FACILITY_NAME = "test_service"
FACILITY_ID = uuid4().hex


def aiohttp_app(
    include_routes: Optional[Sequence[str]] = None,
    exclude_routes: Optional[Sequence[str]] = None,
):
    routes = RouteTableDef()

    @routes.get("/valueerror")
    async def value_error(request) -> None:
        raise ValueError()

    @routes.get("/ok")
    async def ok(request):
        return json_response(data={"status": "ok"})

    @routes.get("/one")
    async def one(request):
        return json_response(data={"status": "one"})

    @routes.get("/two")
    async def two(request):
        return json_response(data={"status": "two"})

    @routes.get("/metrics")
    async def metrics(request):
        return get_http_response_metrics()

    start_metrics(FACILITY_NAME, FACILITY_ID)
    app = Application()
    app.add_routes(routes)
    add_middleware(app, include_routes=include_routes, exclude_routes=exclude_routes)

    return TestClient(server=TestServer(app))
