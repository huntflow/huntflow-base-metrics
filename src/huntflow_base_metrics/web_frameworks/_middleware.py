import abc
from dataclasses import dataclass
from typing import Any, Optional, Set

from huntflow_base_metrics._context import METRIC_CONTEXT


@dataclass(frozen=True)
class PathTemplate:
    value: str
    is_handled: bool


class PrometheusMiddleware(abc.ABC):
    include_routes: Optional[Set[str]] = None
    exclude_routes: Optional[Set[str]] = None

    @staticmethod
    @abc.abstractmethod
    def get_path_template(request: Any) -> PathTemplate:
        pass

    @classmethod
    def is_excluded(cls, path_template: PathTemplate) -> bool:
        if cls.include_routes:
            return path_template.value not in cls.include_routes
        if cls.exclude_routes:
            return path_template.value in cls.exclude_routes
        return False

    @classmethod
    def need_process(cls, path_template: PathTemplate) -> bool:
        return (
            METRIC_CONTEXT.enable_metrics
            and path_template.is_handled
            and not cls.is_excluded(path_template)
        )
