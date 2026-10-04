"""Budget and evidence math for the finite, unexecuted bias follow-up."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
plan = importlib.import_module("bias_headroom_plan")
LIMIT = {
    "max_spectre_attempts": 500,
    "max_new_results_bytes": 5 * 1024**3,
    "reservation_bytes_per_job": 128 * 1024**2,
}


def test_storage_remains_binding_despite_468_attempts() -> None:
    value = {"campaign_id": "AUTO-PHASE-01", "count": 32, "result_reserved_bytes": 3088056320}
    assert plan.capacity(value, LIMIT, 2 * 1024**2) == {
        "attempts_remaining": 468,
        "reservations_remaining": 16,
    }
    value["count"] = 499
    assert plan.capacity(value, LIMIT, 0)["reservations_remaining"] == 1


@pytest.mark.parametrize(
    "count,reserved",
    [(31, 3088056320), (501, 3088056320), (True, 3088056320), (32, True), (32, 5368709121)],
)
def test_counter_reset_and_expansion_are_rejected(count: int, reserved: int) -> None:
    with pytest.raises(ValueError):
        plan.capacity(
            {"campaign_id": "AUTO-PHASE-01", "count": count, "result_reserved_bytes": reserved},
            LIMIT,
            0,
        )


def test_full_counter_or_storage_has_no_execution_slots() -> None:
    for count, reserved in ((500, 3088056320), (32, 5368709120)):
        assert (
            plan.capacity(
                {"campaign_id": "AUTO-PHASE-01", "count": count, "result_reserved_bytes": reserved},
                LIMIT,
                0,
            )["reservations_remaining"]
            == 0
        )


@pytest.mark.parametrize("fault", ["none", "missing", "nan", "alias", "corner"])
def test_headroom_summary_never_hides_missing_evidence(fault: str) -> None:
    value: dict[str, Any] = {
        corner: {
            "mos_metrics": {
                f"mos{i:02d}": {"headroom_v": -0.1 if i == 1 else 0.2} for i in range(1, 15)
            }
        }
        for corner in ("NN", "FF", "SS", "FS", "SF")
    }
    if fault in ("missing", "nan"):
        value["FS"]["mos_metrics"]["mos01"]["headroom_v"] = (
            None if fault == "missing" else float("nan")
        )
    elif fault == "alias":
        del value["FS"]["mos_metrics"]["mos14"]
    elif fault == "corner":
        del value["SF"]
    if fault == "none":
        assert plan.headroom_summary(value)["FS"] == {
            "minimum_headroom_mv": -100.0,
            "negative_headroom_devices": 1,
        }
    else:
        with pytest.raises(ValueError):
            plan.headroom_summary(value)
