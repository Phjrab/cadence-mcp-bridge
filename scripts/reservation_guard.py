"""Pure cumulative reservation arithmetic, compatible with legacy Python hosts."""

try:
    INTEGER_TYPES = (int, long)  # type: ignore[name-defined] # noqa: F821
except NameError:
    INTEGER_TYPES = (int,)  # type: ignore[assignment]

try:
    STRING_TYPES = (basestring,)  # type: ignore[name-defined] # noqa: F821
except NameError:
    STRING_TYPES = (str,)


def next_reservation(  # type: ignore[no-untyped-def]
    counter, baseline, attempts, reservation, count_limit, byte_limit, phase_limit
):
    """Check conservation and ceilings before returning a new ledger value."""
    keys = set(("campaign_id", "count", "result_reserved_bytes"))
    if set(counter) != keys or set(baseline) != keys:
        raise ValueError("ledger fields")
    if not isinstance(baseline["campaign_id"], STRING_TYPES) or not baseline["campaign_id"]:
        raise ValueError("campaign identity")
    if counter["campaign_id"] != baseline["campaign_id"]:
        raise ValueError("campaign identity")
    numbers = (
        attempts,
        reservation,
        count_limit,
        byte_limit,
        phase_limit,
        counter["count"],
        counter["result_reserved_bytes"],
        baseline["count"],
        baseline["result_reserved_bytes"],
    )
    if any(type(value) not in INTEGER_TYPES for value in numbers):
        raise ValueError("integer ledger values")
    if min(attempts, baseline["count"], baseline["result_reserved_bytes"]) < 0:
        raise ValueError("negative usage")
    if min(reservation, count_limit, byte_limit, phase_limit) <= 0:
        raise ValueError("positive ceilings and reservation")
    if counter["count"] != baseline["count"] + attempts:
        raise ValueError("attempt conservation")
    expected_bytes = baseline["result_reserved_bytes"] + attempts * reservation
    if counter["result_reserved_bytes"] != expected_bytes:
        raise ValueError("reservation conservation")
    if attempts >= phase_limit or counter["count"] >= count_limit:
        raise ValueError("attempt ceiling")
    if counter["result_reserved_bytes"] + reservation > byte_limit:
        raise ValueError("storage ceiling")
    return {
        "campaign_id": counter["campaign_id"],
        "count": counter["count"] + 1,
        "result_reserved_bytes": counter["result_reserved_bytes"] + reservation,
    }
