import asyncio
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from prometheus_client import CollectorRegistry
from prometheus_client.metrics import MetricWrapperBase

__all__ = ["METRIC_CONTEXT"]


@dataclass
class _MetricsContext:
    enable_metrics: bool = False
    registry: Optional[CollectorRegistry] = None
    write_to_file_task: Optional[asyncio.Task] = None
    include_routes: Optional[Set[str]] = None
    exclude_routes: Optional[Set[str]] = None

    metrics_by_names: Dict[str, MetricWrapperBase] = field(default_factory=dict)
    metrics_by_objects: Dict[MetricWrapperBase, Tuple[str, List]] = field(default_factory=dict)


METRIC_CONTEXT = _MetricsContext()
