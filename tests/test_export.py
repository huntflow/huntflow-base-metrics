import asyncio
from uuid import uuid4

from prometheus_client.parser import text_fd_to_metric_families

from huntflow_base_metrics import (
    observe_metrics,
    register_method_observe_histogram,
    start_metrics,
)
from huntflow_base_metrics.export import start_export_to_file, stop_export_to_file


async def test_file_export(tmp_path):
    method = "test_method"
    metric_name = "test_export_histogram"
    histogram = register_method_observe_histogram(metric_name, "Test histogram")

    @observe_metrics(method, histogram)
    async def observable_func(sleep_time=None):
        if sleep_time:
            await asyncio.sleep(sleep_time)
        return sleep_time

    facility_name = uuid4().hex
    facility_id = uuid4().hex

    start_metrics(facility_name, facility_id)

    sleep_time = 0.2
    result = await observable_func(sleep_time)
    assert sleep_time == result

    file_path = tmp_path / "test_metrics.prom"
    start_export_to_file(file_path, 0.1)
    try:
        await asyncio.sleep(0.15)
        with open(file_path) as fin:
            metrics = [
                metric for metric in text_fd_to_metric_families(fin) if metric.name == metric_name
            ]
    finally:
        stop_export_to_file()
        await asyncio.sleep(0)

    assert len(metrics) == 1
    metric = metrics[0]
    count = None
    sum_ = None
    for sample in metric.samples:
        if sample.name == "test_export_histogram_count":
            count = sample.value
        elif sample.name == "test_export_histogram_sum":
            sum_ = sample.value
    assert count == 1
    assert sum_ is not None
    assert (sleep_time - 0.01) < sum_ < (sleep_time + 0.01)
