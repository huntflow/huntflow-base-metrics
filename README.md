# huntflow-base-metrics
Base definitions for metrics collection via prometheus client library.
* ready-to use collectors to measure HTTP requests and responses.
* decorator to observe timings of custom methods/functions.
* builtin support for common labels across all collectors

Intended to be used in Huntflow services based on:
* AioHTTP
* FastAPI
* Litestar

# Installation

```shell
pip install huntflow_base_metrics
```

# Usage

## Common labels and methods

The package provides two labels which should be set for every metric:

* `service` - name for your service
* `pod` - instance of your service (supposed to be k8s pod name)

You don't need to set those labels manually. The labels are handled implicitly by the package public
methods.

For request metrics you don't need to deal with labels at all.

For another metrics use `register_metric` method. It will accept a custom list of labels and create
a collector with your labels + common labels. To get labelled metric instance (registered with `register_metric`) use
`apply_labels` method.

## Collect FastAPI requests metrics

```python
from contextlib import asynccontextmanager

from fastAPI import FastAPI

from huntflow_base_metrics import start_metrics, stop_metrics
from huntflow_base_metrics.web_frameworks.fastapi import add_middleware


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


def create_app() -> FastAPI:
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

## Collect Litestar requests metrics

```python
from uuid import uuid4

from litestar import Litestar, MediaType, Request, Response, get
from litestar.status_codes import HTTP_500_INTERNAL_SERVER_ERROR

from huntflow_base_metrics import start_metrics, stop_metrics
from huntflow_base_metrics.web_frameworks.litestar import (
    exception_context,
    get_http_response_metrics,
    get_middleware,
)

FACILITY_NAME = "test_service"
FACILITY_ID = uuid4().hex

async def on_shutdown(app: Litestar):
    stop_metrics()


def exception_handler(_: Request, exc: Exception):
    """
    Important!
    If you need to collect EXCEPTIONS metrics you should set it to exception_context here
    """
    status_code = getattr(exc, "status_code", HTTP_500_INTERNAL_SERVER_ERROR)
    exception_type = type(exc).__name__

    exception_context.set(exception_type)

    return Response(
        media_type=MediaType.JSON,
        content=exception_type,
        status_code=status_code,
    )


def create_app() -> Litestar:
    @get("/ok")
    async def ok() -> dict:
        return {"status": "ok"}

    @get("/metrics")
    async def metrics() -> Response:
        return get_http_response_metrics()

    start_metrics(
        FACILITY_NAME,
        FACILITY_ID,
        out_file_path=f"/app/metrics/{FACILITY_NAME}-{FACILITY_ID}.prom",
        enabled=True,
        write_to_file=True,
        file_update_interval=15,
    )
    prometheus_middleware = get_middleware()
    app = Litestar(
        middleware=[prometheus_middleware],
        route_handlers=[ok, metrics],
        exception_handlers={Exception: exception_handler},
        on_shutdown=[on_shutdown],
    )

    return app
```

## Collect AioHTTP requests metrics

```python
from aiohttp import web
from aiohttp.web_app import Application

from huntflow_base_metrics import start_metrics, stop_metrics
from huntflow_base_metrics.web_frameworks.aiohttp import add_middleware, get_http_response_metrics


# Service name (in most cases should be provided in `FACILITY_NAME` environment variable)
FACILITY_NAME = "my-service-name"
# Service instance name (should provided in `FACILITY_ID` environment variable)
FACILITY_ID = "qwerty"


async def on_cleanup(app):
    stop_metrics()


def create_app() -> Application:
    routes = web.RouteTableDef()

    @routes.get("/ok")
    async def ok(request):
        return web.json_response(data={"status": "ok"})
    
    @routes.get("/metrics")
    async def ok(request):
        return get_http_response_metrics()

    start_metrics(
        FACILITY_NAME,
        FACILITY_ID,
        out_file_path=f"/app/metrics/{FACILITY_NAME}-{FACILITY_ID}.prom",
        enabled=True,
        write_to_file=True,
        file_update_interval=15,
    )
    app = Application()
    app.add_routes(routes)
    add_middleware(app)
    app.on_cleanup.append(on_cleanup)
    return app
```

## Request metrics

### requests_total

Incremental counter for total number of requests

**Type** Counter

**Labels**

* `service`
* `pod`
* `method` - HTTP method like `GET`, `POST`
* `template_path` - path provided as a route

### responses_total

Incremental counter for total number of responses

**Type** Counter

**Labels**

* `service`
* `pod`
* `method` - HTTP method like `GET`, `POST`
* `template_path` - path provided as a route
* `status_code` - HTTP status code return by response (200, 404, 500, etc)


### requests_processing_time_seconds

Historgam collects latency (request processing time) for requests

**Type** Histogram

**Labels**

* `service`
* `pod`
* `method` - HTTP method like `GET`, `POST`
* `template_path` - path provided as a route
* `le` - bucket in histogram (builtin label in Histogram collector)


### requests_in_progress

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
