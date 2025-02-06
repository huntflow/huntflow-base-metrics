from contextlib import suppress
from enum import Enum
from typing import Dict, Optional, Sequence, Union

import pytest
from aiohttp import ClientResponse as AiohttpResponse
from aiohttp.test_utils import TestClient as AiohttpTestClient
from httpx import Response as HttpxResponse
from prometheus_client.exposition import CONTENT_TYPE_LATEST

from huntflow_base_metrics.base import COMMON_LABELS_VALUES, REGISTRY
from tests.test_web_frameworks.aiohttp import aiohttp_app
from tests.test_web_frameworks.fastapi import fastapi_app
from tests.test_web_frameworks.litestar import litestar_app


class Framework(str, Enum):
    aiohttp = "aiohttp"
    fastapi = "fastapi"
    litestar = "litestar"


factories = {
    Framework.fastapi: fastapi_app,
    Framework.aiohttp: aiohttp_app,
    Framework.litestar: litestar_app,
}


@pytest.fixture(params=[Framework.fastapi, Framework.aiohttp, Framework.litestar])
async def create_app(request):
    factory = factories[request.param]
    aiohttp_client: Optional[AiohttpTestClient] = None

    async def test_client(
        include_routes: Optional[Sequence[str]] = None,
        exclude_routes: Optional[Sequence[str]] = None,
    ):
        client = factory(include_routes=include_routes, exclude_routes=exclude_routes)
        if request.param == Framework.aiohttp:
            # For aiohttp client implementation we need to start and stop server
            nonlocal aiohttp_client
            aiohttp_client = client
            await client.start_server()
        return client

    yield test_client

    if aiohttp_client:
        await aiohttp_client.close()


async def check_response(
    resp: Union[HttpxResponse, AiohttpResponse],
    expected_json: Optional[Dict] = None,
    status: int = 200,
) -> None:
    """
    There might be a httpx or aiohttp response with different behavior.
    """
    if expected_json is not None:
        json = await resp.json() if isinstance(resp, AiohttpResponse) else resp.json()
        assert json == expected_json

    status_code = resp.status if isinstance(resp, AiohttpResponse) else resp.status_code

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


async def test_get_http_response_metrics(create_app):
    client = await create_app()

    response = await client.get("/metrics")
    await check_response(response, status=200)
    assert response.headers["Content-Type"] == CONTENT_TYPE_LATEST
