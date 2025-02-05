from typing import Optional, Sequence
from uuid import uuid4

from fastapi import FastAPI
from starlette.testclient import TestClient

from huntflow_base_metrics import start_metrics
from huntflow_base_metrics.web_frameworks.fastapi import get_http_response_metrics, add_middleware


FACILITY_NAME = "test_service"
FACILITY_ID = uuid4().hex


def fastapi_app(
    include_routes: Optional[Sequence[str]] = None,
    exclude_routes: Optional[Sequence[str]] = None,
) -> TestClient:
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

    return TestClient(app)
