import nox

DEPENDENCIES = [".", "pytest", "pytest_asyncio", "httpx"]


@nox.session()
@nox.parametrize("fastapi_version", ["0.66", "0.115.8"])
def test_fastapi_versions(session, fastapi_version):
    session.install(*DEPENDENCIES, f"fastapi=={fastapi_version}")
    session.run("pytest", "tests", "--framework=fastapi", "-k", "test_frameworks")


@nox.session()
@nox.parametrize("litestar_version", ["2.13.0", "2.14.0"])
def test_litestar_versions(session, litestar_version):
    session.install(*DEPENDENCIES, f"litestar=={litestar_version}")
    session.run("pytest", "tests", "--framework=litestar", "-k", "test_frameworks")


@nox.session()
@nox.parametrize("aiohttp_version", ["3.9.1", "3.11.12"])
def test_aiohttp_versions(session, aiohttp_version):
    session.install(*DEPENDENCIES, f"aiohttp=={aiohttp_version}")
    session.run("pytest", "tests", "--framework=aiohttp", "-k", "test_frameworks")
