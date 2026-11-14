from __future__ import annotations

import pytest

from governed_analytics.catalogue import METRICS_DIR, Metric, load_metric


@pytest.fixture
def nmv() -> Metric:
    return load_metric(METRICS_DIR / "net_merchandise_value.yml")
