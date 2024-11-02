# huntflow-base-metrics
Base definitions for metrics collection via prometheus client library.
Intended to be used in Huntflow fastapi-based services:
* ready-to use collectors to measure HTTP requests and responses.
* decorator to observe timings of custom methods/functions.
* builtin support for common lables across all collectors

# Installation

TODO

# Usage

## Common labels and methods

The package provides two labels which should be set for every metric:

* `service` - name for your service
* `pod` - instance of your service (supposed to be k8s pod name)

You don't need to set those labels manually. The labels are handled implicitly by the package public
methods.

For FastAPI metrics you don't need to deal with labels at all.

For another metrics use `register_metric` method. It will accept a custom list of labels and create
a collector with your labels + common labels. To get labelled metric instance (registered with `register_metric`) use
`apply_labels` method.

## Collect FastAPI requests metrics

```python
from contextlib import asynccontextmanager

from fastAPI import FastAPI

from huntflow_base_metrics import start_metrics, stop_metrics, add_middleware


# Service name (in most cases should be provided in `FACILITY_NAME` environment variable)
FACILITY_NAME = "my-service-name"
# Service instance name (should provided in `FACILITY_ID` environment variable)
FACILITY_ID = "qwerty"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await onstartup(app)
    yield
    await onshutdown(app)


async def onstartup(app: FastAPI):
    # do some startup actions
    pass

async def onshutdown(app: FastAPI):
    # do some shutdown actions
    stop_metrics()


def create_app()
    app = FastAPI(lifespan=lifespan)

    start_metrics(
        FACILITY_NAME,
        FACILITY_ID,
        # Optional, only needed if metrics are collected from files.
        # Also, it's mandatory if write_to_file is True
        out_file_path=f"/app/metrics/{FACILITY_NAME}-{FACILITY_ID}.prom",
        enabled=True,
        write_to_file=True,
        # interval in seconds to dump metrics to a file
        file_update_interval=15,
    )
    add_middleware(app)
    return app
```

### FastAPI metrics

#### requests_total

Incremental counter for total number of requests

**Type** Counter

**Labels**

* `service`
* `pod`
* `method` - HTTP method like `GET`, `POST`
* `template_path` - path provided as a route

#### responses_total

Incremental counter for total number of responses

**Type** Counter

**Labels**

* `service`
* `pod`
* `method` - HTTP method like `GET`, `POST`
* `template_path` - path provided as a route
* `status_code` - HTTP status code return by response (200, 404, 500, etc)


#### requests_processing_time_seconds

Historgam collects latency (request processing time) for requests

**Type** Histogram

**Labels**

* `service`
* `pod`
* `method` - HTTP method like `GET`, `POST`
* `template_path` - path provided as a route
* `le` - bucket in histogram (builtin label in Histogram collector)


#### requests_in_progress

Current number of in-progress requests 

**Type** Gauge

**Labels**

* `service`
* `pod`
* `method` - HTTP method like `GET`, `POST`
* `template_path` - path provided as a route

## Observe timing for custom methods

To collect metrics for some method (not FastAPI handlers) use `observe_metrics` decorator.
It can be applied to regular and for async functions/methods.
It accepts two required parameters:

* method - string to identify measured method
* metric_timings - Histogram instance to collect timing

Third optional parameter is `metric_inprogress` (instance of Gauge colector).
Provide it if you need to collect in-progress operations for the observing method.

To create Histogram object useful for `observe_metrics`, call `register_method_observe_histogram`
function. It accepts two parameters:
* name - unique metric name (first argument for Histogram constructor)
* description - metric description

**Labels provided by metric_timings**

* `service`
* `pod`
* `method` - method name passed to observe_metrics decorator
* `le` - bucket name (built-in label of Histogram collector)

Usage example

```python
from huntflow_base_metrics import (
    register_method_observe_histogram,
    observe_metrics,
)


METHOD_HISTOGRAM = register_method_observe_histogram(
    "process_method_timing",
    "Timings for processing logic",
)


@observe_metrics("select_data", METHOD_HISTOGRAM)
async def select_data(filters) -> List[Dict]:
    data = [convert_item(record for record in await repo.select(*filters)]
    return data


@observe_metrics("convert_item", METHOD_HISTOGRAM)
def convert_item(record: Dict) -> RecordDTO:
    return RecrodDTO(**record)


@observe_metrics("calculate_stats", METHOD_HISTOGRAM)
async def calculate_stats(filters) -> StatsDTO:
    data = await select_data(filters)
    stats = aggregate(data)
    return stats


```


# TODO: another use-cases and development notes
