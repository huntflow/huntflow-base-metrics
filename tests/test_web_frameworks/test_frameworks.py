from contextlib import suppress

import pytest
from prometheus_client.exposition import CONTENT_TYPE_LATEST

from huntflow_base_metrics.base import COMMON_LABELS_VALUES, REGISTRY
from tests.test_web_frameworks.fastapi import fastapi_app
from tests.test_web_frameworks.litestar import litestar_app


@pytest.mark.parametrize("create_app", [fastapi_app, litestar_app])
def test_ok(create_app):
    client = create_app()

    response = client.get("/ok")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

    labels = COMMON_LABELS_VALUES.copy()
    labels.update(
        {
            "method": "GET",
            "path_template": "/ok",
        }
    )
    assert REGISTRY.get_sample_value("requests_total", labels) == 1

    labels_responses_total = labels.copy()
    labels_responses_total["status_code"] = "200"
    assert REGISTRY.get_sample_value("responses_total", labels_responses_total) == 1

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
    assert REGISTRY.get_sample_value("requests_total", labels_missed) is None


@pytest.mark.parametrize("create_app", [fastapi_app, litestar_app])
def test_exception(create_app):
    client = create_app()

    with suppress(ValueError):
        response = client.get("/valueerror")
        assert response.status_code == 500

    labels = COMMON_LABELS_VALUES.copy()
    labels.update(
        {
            "method": "GET",
            "path_template": "/valueerror",
            "exception_type": "ValueError",
        }
    )

    assert (
        REGISTRY.get_sample_value(
            "exceptions_total",
            labels,
        )
        == 1
    )


@pytest.mark.parametrize("create_app", [fastapi_app, litestar_app])
def test_include(create_app):
    client = create_app(include_routes=["/ok"])

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
    labels.update(
        {
            "method": "GET",
            "path_template": "/ok",
        }
    )
    assert REGISTRY.get_sample_value("requests_total", labels) == 1

    labels["path_template"] = "/one"
    assert REGISTRY.get_sample_value("requests_total", labels) is None

    labels["path_template"] = "/two"
    assert REGISTRY.get_sample_value("requests_total", labels) is None


@pytest.mark.parametrize("create_app", [fastapi_app, litestar_app])
def test_exclude(create_app):
    client = create_app(exclude_routes=["/ok", "/one"])

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
    labels.update(
        {
            "method": "GET",
            "path_template": "/ok",
        }
    )
    assert REGISTRY.get_sample_value("requests_total", labels) is None

    labels["path_template"] = "/one"
    assert REGISTRY.get_sample_value("requests_total", labels) is None

    labels["path_template"] = "/two"
    assert REGISTRY.get_sample_value("requests_total", labels) == 1


@pytest.mark.parametrize("create_app", [fastapi_app, litestar_app])
def test_get_http_response_metrics(create_app):
    client = create_app()

    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["Content-Type"] == CONTENT_TYPE_LATEST
