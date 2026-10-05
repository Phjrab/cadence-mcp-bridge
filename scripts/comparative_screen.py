"""Legacy-compatible relative screening for diagnostic resource allocation.

No absolute design specification, simulation, or qualification decision is defined.
"""

import math


def _metrics(value):
    # type: (dict[str, float]) -> None
    if type(value) is not dict or set(value) != set(
        ("first_gain", "minimum_headroom", "negative_devices")
    ):
        raise ValueError("closed comparative metric schema")
    for key in ("first_gain", "minimum_headroom"):
        item = value[key]
        if type(item) not in (int, float) or math.isnan(item) or math.isinf(item):
            raise ValueError("finite comparative metric required")
    if value["first_gain"] < 0:
        raise ValueError("nonnegative gain magnitude required")
    count = value["negative_devices"]
    if type(count) is not int or count < 0:
        raise ValueError("nonnegative integer device count required")


def compare(fs, nn, baseline_fs, baseline_nn):
    # type: (dict[str, float], dict[str, float], dict[str, float], dict[str, float]) -> dict[str, object]
    """Compare already checked measurements; invalid data raises, never falls back."""
    for value in (fs, nn, baseline_fs, baseline_nn):
        _metrics(value)
    reasons = []
    if fs["first_gain"] < baseline_fs["first_gain"]:
        reasons.append("first_gain_worse")
    if fs["minimum_headroom"] < baseline_fs["minimum_headroom"]:
        reasons.append("minimum_headroom_worse")
    if (
        fs["first_gain"] <= baseline_fs["first_gain"]
        and fs["minimum_headroom"] <= baseline_fs["minimum_headroom"]
    ):
        reasons.append("neither_objective_improves")
    if nn["negative_devices"] > baseline_nn["negative_devices"]:
        reasons.append("new_negative_headroom_devices")
    return {
        "eligible": not reasons,
        "reasons": reasons,
        "meaning": "relative_diagnostic_allocation_not_specification_pass",
    }
