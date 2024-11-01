from contextlib import suppress
from uuid import uuid4

from fastapi import FastAPI

from huntflow_base_metrics.base_metrics import start_metrics, REGISTRY, COMMON_LABELS_VALUES
from huntflow_base_metrics.fastapi_metrics import add_middleware
from starlette.testclient import TestClient

FACILITY_NAME = "test_service"
FACILITY_ID = uuid4().hex


def create_app() -> FastAPI:
    app = FastAPI()

    @app.get("/valueerror")
    async def get_valuerror():
        raise ValueError()

    @app.get("/ok")
    async def get_ok():
        return {"status": "ok"}

    @app.get("/one")
    async def get_one():
        return {"status": "one"}

    @app.get("/two")
    async def get_two():
        return {"status": "two"}

    return app


def test_ok():
    app = create_app()
    client = TestClient(app)
    start_metrics(FACILITY_NAME, FACILITY_ID)
    add_middleware(app)
    response = client.get("/ok")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

    labels = COMMON_LABELS_VALUES.copy()
    labels.update({
        "method": "GET",
        "path_template": "/ok",
    })
    assert (
        REGISTRY.get_sample_value(
            "requests_total",
            labels,
        )
        == 1
    )
    
    labels_responses_total = labels.copy()
    labels_responses_total["status_code"] = "200"
    assert (
        REGISTRY.get_sample_value(
            "responses_total",
            labels_responses_total,
        )
        == 1
    )

    labels_proc_time = labels.copy()
    labels_proc_time["le"] = "0.005"
    assert (
        REGISTRY.get_sample_value(
            "requests_processing_time_seconds_bucket",
            labels_proc_time,
        )
        == 1
    )

    labels_missed = labels.copy()
    labels_missed["path_template"] = "/unknown_path"
    assert (
        REGISTRY.get_sample_value(
            "requests_total",
            labels_missed,
        )
        is None
    )


def test_exception():
    app = create_app()
    client = TestClient(app)
    start_metrics(FACILITY_NAME, FACILITY_ID)
    add_middleware(app)
    with suppress(ValueError):
        client.get("/valueerror")

    labels = COMMON_LABELS_VALUES.copy()
    labels.update({
        "method": "GET",
        "path_template": "/valueerror",
        "exception_type": "ValueError",
    })

    assert (
        REGISTRY.get_sample_value(
            "exceptions_total",
            labels,
        )
        ==  1
    )


def test_include():
    app = create_app()
    client = TestClient(app)
    start_metrics(FACILITY_NAME, FACILITY_ID)
    add_middleware(app, include_routes=["/ok"])

    response = client.get("/ok")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

    response = client.get("/one")
    assert response.status_code == 200
    assert response.json() == {"status": "one"}

    response = client.get("/two")
    assert response.status_code == 200
    assert response.json() == {"status": "two"}

    labels = COMMON_LABELS_VALUES.copy()
    labels.update({
        "method": "GET",
        "path_template": "/ok",
    })
    assert (
        REGISTRY.get_sample_value(
            "requests_total",
            labels,
        )
        == 1
    )

    labels["path_template"] = "/one"
    assert (
        REGISTRY.get_sample_value(
            "requests_total",
            labels,
        )
        is None
    )

    labels["path_template"] = "/two"
    assert (
        REGISTRY.get_sample_value(
            "requests_total",
            labels,
        )
        is None
    )


def test_exclude():
    app = create_app()
    client = TestClient(app)
    start_metrics(FACILITY_NAME, FACILITY_ID)
    add_middleware(app, exclude_routes=["/ok", "/one"])

    response = client.get("/ok")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

    response = client.get("/one")
    assert response.status_code == 200
    assert response.json() == {"status": "one"}

    response = client.get("/two")
    assert response.status_code == 200
    assert response.json() == {"status": "two"}

    labels = COMMON_LABELS_VALUES.copy()
    labels.update({
        "method": "GET",
        "path_template": "/ok",
    })
    assert (
        REGISTRY.get_sample_value(
            "requests_total",
            labels,
        )
        is None
    )

    labels["path_template"] = "/one"
    assert (
        REGISTRY.get_sample_value(
            "requests_total",
            labels,
        )
        is None
    )

    labels["path_template"] = "/two"
    assert (
        REGISTRY.get_sample_value(
            "requests_total",
            labels,
        )
        == 1
    )
