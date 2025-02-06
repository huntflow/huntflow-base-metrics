from typing import Optional, Sequence
from uuid import uuid4

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from huntflow_base_metrics import start_metrics
from huntflow_base_metrics.web_frameworks.fastapi import add_middleware, get_http_response_metrics

FACILITY_NAME = "test_service"
FACILITY_ID = uuid4().hex


def fastapi_app(
    include_routes: Optional[Sequence[str]] = None,
    exclude_routes: Optional[Sequence[str]] = None,
) -> AsyncClient:
    app = FastAPI()

    @app.get("/valueerror")
    async def value_error():
        raise ValueError()

    @app.get("/ok")
    async def ok():
        return {"status": "ok"}

    @app.get("/one")
    async def one():
        return {"status": "one"}

    @app.get("/two")
    async def two():
        return {"status": "two"}

    @app.get("/metrics")
    async def metrics():
        return get_http_response_metrics()

    start_metrics(FACILITY_NAME, FACILITY_ID)
    add_middleware(app, include_routes, exclude_routes)

    transport = ASGITransport(app=app)

    return AsyncClient(transport=transport, base_url="http://testserver")
