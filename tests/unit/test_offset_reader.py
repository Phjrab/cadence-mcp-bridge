"""Independent synthetic step science and fail-closed shared execution guards."""

import json
from pathlib import Path

import pytest
from test_native_diagnostics import remote_module

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("case", ["current", "future", "ceiling", "reset", "over-limit", "marker"])
def test_timeless_reader_keeps_historical_accounting(case: str) -> None:
    m = remote_module("offset-read-v1")
    markers = [
        {
            "campaign_id": "AUTO-PHASE-01",
            "count": 68 + i,
            "result_reserved_bytes": 7919894528 + i * 128 * 1024**2,
        }
        for i in range(5)
    ]
    current = dict(markers[-1])
    if case == "future":
        current.update(count=73, result_reserved_bytes=8590983168)
    elif case == "ceiling":
        current.update(count=500, result_reserved_bytes=10 * 1024**3)
    elif case == "reset":
        current["count"] = 71
    elif case == "over-limit":
        current["result_reserved_bytes"] = 10 * 1024**3 + 1
    elif case == "marker":
        markers[0]["count"] = 69
    if case in ("current", "future", "ceiling"):
        m.accounting(current, markers)
    else:
        with pytest.raises(ValueError):
            m.accounting(current, markers)


@pytest.mark.parametrize("case", ["same", "future-job", "removed", "changed", "source", "active"])
def test_reader_preserves_every_old_job_and_protected_fact(case: str) -> None:
    m = remote_module("offset-read-v1")
    before = {
        "native": {"jobs": {"opaque-old": {"hash": "a" * 64}}, "active_eda": False},
        "protected": {"source_hash": "b" * 64},
    }
    now = json.loads(json.dumps(before))
    if case == "future-job":
        now["native"]["jobs"]["opaque-new"] = {"hash": "c" * 64}
    elif case == "removed":
        now["native"]["jobs"] = {}
    elif case == "changed":
        now["native"]["jobs"]["opaque-old"]["hash"] = "d" * 64
    elif case == "source":
        now["protected"]["source_hash"] = "e" * 64
    elif case == "active":
        now["native"]["active_eda"] = True
    if case in ("same", "future-job"):
        m.preserved(before, now)
    else:
        with pytest.raises(ValueError):
            m.preserved(before, now)
