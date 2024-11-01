# huntflow-base-metrics
Base definitions for metrics collection via prometheus client library.
Intended to be used in Huntflow fastapi-based services: ready-to use collectors to measure HTTP requests and responses.
Also provides universal decorator to observe timings of custom methods/functions.

# How to use

## How to collect metrics for FastAPI requests

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

# TODO: another use-cases and development notes
