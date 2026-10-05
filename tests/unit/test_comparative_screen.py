"""Fictional metrics exercise allocation boundaries and invalid-data handling."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import comparative_screen


def metric(gain: float = 2.0, headroom: float = -0.2, count: float = 3) -> dict[str, float]:
    return {"first_gain": gain, "minimum_headroom": headroom, "negative_devices": count}


@pytest.mark.parametrize("gain,headroom", [(3.0, -0.2), (2.0, -0.1), (3.0, -0.1)])
def test_one_or_both_objectives_improve_without_other_regression(
    gain: float, headroom: float
) -> None:
    result = comparative_screen.compare(metric(gain, headroom), metric(), metric(), metric())
    assert result["eligible"]
    assert result["meaning"] == "relative_diagnostic_allocation_not_specification_pass"


@pytest.mark.parametrize(
    "candidate,reason",
    [
        (metric(), "neither_objective_improves"),
        (metric(1.0, -0.1), "first_gain_worse"),
        (metric(3.0, -0.3), "minimum_headroom_worse"),
    ],
)
def test_tradeoff_or_no_change_does_not_silently_allocate(
    candidate: dict[str, float], reason: str
) -> None:
    result = comparative_screen.compare(candidate, metric(), metric(), metric())
    assert not result["eligible"]
    reasons = result["reasons"]
    assert isinstance(reasons, list)
    assert reason in reasons


def test_second_corner_new_negative_margin_blocks_allocation() -> None:
    result = comparative_screen.compare(metric(3.0), metric(count=4), metric(), metric())
    assert result["reasons"] == ["new_negative_headroom_devices"]


def test_second_corner_other_changes_do_not_become_unspecified_targets() -> None:
    result = comparative_screen.compare(metric(3.0), metric(0.01, -1.0, 2), metric(), metric())
    assert result["eligible"]


@pytest.mark.parametrize(
    "bad",
    [
        {"first_gain": float("nan"), "minimum_headroom": -0.2, "negative_devices": 3},
        metric(headroom=float("inf")),
        metric(gain=True),
        metric(gain=-1),
        metric(count=True),
        metric(count=2.5),
        metric(count=-1),
        {"first_gain": 2.0},
        dict(metric(), qualification_passed=True),
    ],
)
def test_invalid_measurements_raise_instead_of_selecting_fallback(bad: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        comparative_screen.compare(bad, metric(), metric(), metric())
