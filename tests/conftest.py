import pytest

from huntflow_base_metrics.base_metrics import stop_metrics


@pytest.fixture(scope="function", autouse=True)
def disable_metrics():
    """Disable metrics on every test startup"""
    stop_metrics()
