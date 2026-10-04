"""Synthetic budget boundaries; no environment or execution metadata."""

import copy
from typing import Any

import pytest

from scripts.reservation_guard import next_reservation

BASE = {"campaign_id": "fictional", "count": 2, "result_reserved_bytes": 11}


def advance(
    counter: dict[str, Any] | None = None,
    baseline: dict[str, Any] | None = None,
    attempts: int = 0,
    reservation: int = 3,
    count_limit: int = 9,
    byte_limit: int = 17,
    phase_limit: int = 2,
) -> Any:
    return next_reservation(  # type: ignore[no-untyped-call]
        BASE if counter is None else counter,
        BASE if baseline is None else baseline,
        attempts,
        reservation,
        count_limit,
        byte_limit,
        phase_limit,
    )


def test_expansion_preserves_prior_consumption_and_inputs() -> None:
    before = copy.deepcopy(BASE)
    with pytest.raises(ValueError, match="storage ceiling"):
        advance(byte_limit=13)
    new = advance(byte_limit=14)
    assert new == {"campaign_id": "fictional", "count": 3, "result_reserved_bytes": 14}
    assert before == BASE
    assert advance(counter=new, attempts=1, byte_limit=17)["result_reserved_bytes"] == 17


@pytest.mark.parametrize(
    "overrides",
    [
        {"count_limit": 2},
        {
            "phase_limit": 1,
            "attempts": 1,
            "counter": {**BASE, "count": 3, "result_reserved_bytes": 14},
        },
        {"byte_limit": 13},
        {"reservation": 0},
        {"attempts": -1},
        {"count_limit": True},
        {"reservation": 3.0},
        {"counter": {**BASE, "count": True}},
        {"counter": {**BASE, "count": 1}},
        {"counter": {**BASE, "result_reserved_bytes": 10}},
        {"counter": {**BASE, "result_reserved_bytes": 12}},
        {"counter": {**BASE, "campaign_id": "other"}},
        {"counter": {**BASE, "extra": 1}},
        {"counter": {}},
        {"counter": {"campaign_id": "fictional", "count": 2}},
    ],
)
def test_rejects_corruption_reset_and_exhaustion(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        advance(**overrides)


def test_last_attempt_is_allowed_then_denied() -> None:
    new = advance(count_limit=3)
    assert new["count"] == 3
    with pytest.raises(ValueError, match="attempt ceiling"):
        advance(counter=new, attempts=1, count_limit=3)
