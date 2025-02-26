from contextlib import suppress
from inspect import iscoroutine
from typing import TYPE_CHECKING, Dict, Optional, Union

from prometheus_client.exposition import CONTENT_TYPE_LATEST

from huntflow_base_metrics.base import COMMON_LABELS_VALUES, REGISTRY

if TYPE_CHECKING:
    from aiohttp import ClientResponse as AiohttpResponse
    from httpx import Response as HttpxResponse


async def check_response(
    resp: Union["HttpxResponse", "AiohttpResponse"],
    expected_json: Optional[Dict] = None,
    status: int = 200,
) -> None:
    """
    There might be a httpx or aiohttp response with different behavior.
    """
    if expected_json is not None:
        json = resp.json()
        if iscoroutine(json):
            json = await json
        assert json == expected_json

    status_code = resp.status if hasattr(resp, "status") else resp.status_code

    assert status_code == status


async def test_ok(create_app):
    client = await create_app()

    response = await client.get("/ok")
    await check_response(response, {"status": "ok"})

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


async def test_exception(create_app):
    client = await create_app()

    with suppress(ValueError):
        response = await client.get("/valueerror")
        await check_response(response, status=500)

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


async def test_include(create_app):
    client = await create_app(include_routes=["/ok"])

    response = await client.get("/ok")
    await check_response(response, {"status": "ok"})

    response = await client.get("/one")
    await check_response(response, {"status": "one"})

    response = await client.get("/two")
    await check_response(response, {"status": "two"})

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


async def test_exclude(create_app):
    client = await create_app(exclude_routes=["/ok", "/one"])

    response = await client.get("/ok")
    await check_response(response, {"status": "ok"})

    response = await client.get("/one")
    await check_response(response, {"status": "one"})

    response = await client.get("/two")
    await check_response(response, {"status": "two"})

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


async def test_unknown_routes_are_skipped(create_app):
    client = await create_app()
    response = await client.get("/unknown")
    await check_response(response, status=404)

    labels = COMMON_LABELS_VALUES.copy()
    labels.update(
        {
            "method": "GET",
            "path_template": "/unknown",
        }
    )

    assert REGISTRY.get_sample_value("requests_total", labels) is None


async def test_get_http_response_metrics(create_app):
    client = await create_app()

    response = await client.get("/metrics")
    await check_response(response, status=200)
    assert response.headers["Content-Type"] == CONTENT_TYPE_LATEST
