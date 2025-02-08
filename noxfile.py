import os

import nox

os.environ.update({"PDM_IGNORE_SAVED_PYTHON": "1"})
os.environ.update({"PDM_CHECK_UPDATE": "0"})


@nox.session()
@nox.parametrize(
    "fastapi, litestar, aiohttp",
    [
        ("0.66", "2.13.0", "3.9.1"),
        ("0.115.8", "2.14.0", "3.11.12"),
    ],
)
def test_frameworks_compatibility(session, fastapi, litestar, aiohttp):
    session.install("pdm==2.20.1")
    session.run_always("pdm", "install", "--prod", "--frozen-lockfile")
    session.install("pytest", "pytest_asyncio")
    session.install(f"fastapi=={fastapi}")
    session.install(f"litestar=={litestar}")
    session.install(f"aiohttp=={aiohttp}")
    session.run("pytest", "-k", "test_frameworks")
