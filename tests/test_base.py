import pytest
from prometheus_client import Histogram

from huntflow_base_metrics.base_metrics import apply_labels, register_metric, COMMON_LABELS_VALUES


def test_apply_labels_ok():
    historgram = register_metric(
        Histogram, "unique_historgram1", "Test histogram", ["label_one", "label_two"]
    )
    result_histogram = apply_labels(historgram, label_one="a", label_two="b")
    expected_values = tuple(list(COMMON_LABELS_VALUES.values()) + ["a", "b"])
    assert expected_values in historgram._metrics
    assert result_histogram is historgram._metrics[expected_values]


def test_apply_labels_mismatch():
    historgram = register_metric(
        Histogram, "unique_historgram2", "Test histogram", ["label_one", "label_two"]
    )
    with pytest.raises(ValueError):
        apply_labels(historgram)

    with pytest.raises(ValueError):
        apply_labels(historgram, label_1="a", label_2="b")

    with pytest.raises(ValueError):
        apply_labels(historgram, label_one="a", label_two="b", label_three="c")
