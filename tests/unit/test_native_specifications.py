"""Generic exact conditions/units and operator-owned target comparison, synthetic only."""

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from cadence_mcp_bridge.errors import InvalidInputError
from cadence_mcp_bridge.native_service import NativeOperationResult
from cadence_mcp_bridge.native_specifications import (
    NativeSpecificationContract,
    NativeSpecificationQuery,
    NativeSpecificationSupervisor,
)
from cadence_mcp_bridge.variable_contracts import canonical_digest


def contract(**updates):
    values = dict(
        spec_id="qa-voltage",
        design_id="qa-inverter",
        measurement_id="dc-output",
        operation_plan_sha256="a" * 64,
        reader_registration_sha256="b" * 64,
        metric="dc_voltage",
        signal_id="output",
        unit="V",
        comparison="range",
        target="0",
        upper_target="1.2",
        goal_id="qa-sanity-only",
    )
    values.update(updates)
    return NativeSpecificationContract.model_validate_json(json.dumps(values))


class Native:
    def __init__(self, data):
        self.calls = 0
        self.data = data
        self.fail = False

    async def result(self, query):
        self.calls += 1
        if self.fail:
            raise InvalidInputError("Native operation failed; no valid measurement")
        return NativeOperationResult(
            operation_id=query.operation_id,
            plan_sha256=query.expected_plan_sha256,
            result=self.data,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "updates, status",
    [
        ({}, "PASS"),
        ({"target": "-1", "upper_target": "-0.1"}, "FAIL"),
        ({"target": None, "upper_target": None, "goal_id": None}, "NOT_EVALUATED"),
    ],
)
async def test_exact_native_targets_and_targetless_are_distinct(updates, status):
    c = contract(**updates)
    native = Native(
        dict(
            design_id=c.design_id,
            measurement_id=c.measurement_id,
            analysis="dc",
            reader_registration_sha256="b" * 64,
            nodes=[dict(logical_id="output", unit="V", value=0.6)],
        )
    )
    supervisor = NativeSpecificationSupervisor(native)
    supervisor.contracts = lambda: (c,)
    query = NativeSpecificationQuery(
        spec_id=c.spec_id,
        expected_contract_sha256=canonical_digest(c),
        operation_id=str(uuid4()),
        expected_plan_sha256="a" * 64,
    )
    result = await supervisor.result(query)
    assert result.status == status
    assert native.calls == (0 if status == "NOT_EVALUATED" else 1)
    if status == "NOT_EVALUATED":
        assert result.value is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("design_id", "other"),
        ("measurement_id", "other"),
        ("reader_registration_sha256", "c" * 64),
        ("plan_sha256", "c" * 64),
    ],
)
async def test_mismatch_is_not_pass_or_fail(field, value):
    c = contract()
    data = dict(
        design_id=c.design_id,
        measurement_id=c.measurement_id,
        analysis="dc",
        reader_registration_sha256="b" * 64,
        nodes=[dict(logical_id="output", unit="V", value=0.6)],
    )
    if field != "plan_sha256":
        data[field] = value
    native = Native(data)
    supervisor = NativeSpecificationSupervisor(native)
    supervisor.contracts = lambda: (c,)
    query = NativeSpecificationQuery(
        spec_id=c.spec_id,
        expected_contract_sha256=canonical_digest(c),
        operation_id=str(uuid4()),
        expected_plan_sha256=value if field == "plan_sha256" else "a" * 64,
    )
    assert (await supervisor.result(query)).status == "CONDITION_MISMATCH"


@pytest.mark.asyncio
async def test_failed_job_and_stale_target_stay_errors():
    c = contract()
    native = Native({})
    native.fail = True
    supervisor = NativeSpecificationSupervisor(native)
    supervisor.contracts = lambda: (c,)
    query = NativeSpecificationQuery(
        spec_id=c.spec_id,
        expected_contract_sha256=canonical_digest(c),
        operation_id=str(uuid4()),
        expected_plan_sha256="a" * 64,
    )
    with pytest.raises(InvalidInputError):
        await supervisor.result(query)
    with pytest.raises(InvalidInputError):
        await supervisor.result(query.model_copy(update={"expected_contract_sha256": "c" * 64}))
    assert native.calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "metric,unit,data,extra",
    [
        (
            "ac_gain_db",
            "dB",
            {"analysis": "ac", "transfer": [{"frequency_hz": 10.0, "gain_db": 5.0}]},
            {"signal_id": None, "frequency_hz": "10"},
        ),
        (
            "dc_supply_power",
            "W",
            {"analysis": "dc", "power": {"supply_w": 0.2}},
            {"signal_id": None},
        ),
        (
            "tran_last",
            "V",
            {"analysis": "tran", "transient": [{"logical_id": "output", "unit": "V", "last": 0.7}]},
            {},
        ),
        (
            "tran_mean",
            "V",
            {
                "analysis": "tran",
                "transient": [{"logical_id": "output", "unit": "V", "time_weighted_mean": 0.7}],
            },
            {},
        ),
    ],
)
async def test_registered_projection_metrics_share_exact_comparator(metric, unit, data, extra):
    c = contract(metric=metric, unit=unit, comparison=">=", target="0", upper_target=None, **extra)
    native = Native(
        dict(
            data,
            design_id=c.design_id,
            measurement_id=c.measurement_id,
            reader_registration_sha256="b" * 64,
        )
    )
    supervisor = NativeSpecificationSupervisor(native)
    supervisor.contracts = lambda: (c,)
    result = await supervisor.result(
        NativeSpecificationQuery(
            spec_id=c.spec_id,
            expected_contract_sha256=canonical_digest(c),
            operation_id=str(uuid4()),
            expected_plan_sha256="a" * 64,
        )
    )
    assert result.status == "PASS"
    assert result.measurement_result_sha256 is not None


def test_target_units_shapes_and_opaque_selectors_are_closed():
    for updates in (
        {"target": "1", "goal_id": None},
        {"unit": "W"},
        {"signal_id": "/arbitrary"},
        {"target": "nan"},
        {"upper_target": "-1"},
    ):
        with pytest.raises(ValidationError):
            contract(**updates)
