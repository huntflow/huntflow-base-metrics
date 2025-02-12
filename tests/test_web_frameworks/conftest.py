from enum import Enum
from typing import TYPE_CHECKING, Callable, Dict, Optional, Sequence, Union

import pytest

if TYPE_CHECKING:
    from aiohttp.test_utils import TestClient as AiohttpTestClient
    from httpx import AsyncClient as HttpxClient


def pytest_addoption(parser):
    parser.addoption("--framework", action="store", help="run with framework")


def pytest_generate_tests(metafunc):
    if "framework" in metafunc.fixturenames:
        if metafunc.config.getoption("framework"):
            frameworks = [metafunc.config.getoption("framework")]
        else:
            frameworks = ["fastapi", "aiohttp", "litestar"]
        metafunc.parametrize("framework", frameworks)


class Framework(str, Enum):
    aiohttp = "aiohttp"
    fastapi = "fastapi"
    litestar = "litestar"


APP_FACTORIES: Dict[Framework, Optional[Callable]] = {
    Framework.fastapi: None,
    Framework.aiohttp: None,
    Framework.litestar: None,
}


def app_factory(framework: Framework):
    factory = APP_FACTORIES[framework]
    if factory:
        return factory

    if framework == Framework.aiohttp:
        from tests.test_web_frameworks.aiohttp import aiohttp_app

        APP_FACTORIES[framework] = aiohttp_app
    elif framework == Framework.fastapi:
        from tests.test_web_frameworks.fastapi import fastapi_app

        APP_FACTORIES[framework] = fastapi_app
    else:
        from tests.test_web_frameworks.litestar import litestar_app

        APP_FACTORIES[framework] = litestar_app

    return APP_FACTORIES[framework]


@pytest.fixture
async def create_app(framework):
    factory = app_factory(framework)
    aiohttp_client = None

    async def create_application(
        include_routes: Optional[Sequence[str]] = None,
        exclude_routes: Optional[Sequence[str]] = None,
    ) -> Union["AiohttpTestClient", "HttpxClient"]:
        client = factory(include_routes=include_routes, exclude_routes=exclude_routes)
        if framework == Framework.aiohttp:
            # For aiohttp client implementation we need to start and stop server
            nonlocal aiohttp_client
            aiohttp_client = client
            await client.start_server()
        return client

    yield create_application

    if aiohttp_client:
        await aiohttp_client.close()
