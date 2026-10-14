"""Nominal DC nulling numerical fixtures; not actual native qualification."""

import pytest
from pydantic import ValidationError

from cadence_mcp_bridge.generic_offset import InputNullingDefinition, sampled_input_nulling
from cadence_mcp_bridge.operator_operations import OperationRejected


def definition(**changes):
    return InputNullingDefinition(**(dict(
        static_statements_sha256="a" * 64, positive_input="inp", negative_input="inn",
        positive_input_variable="input-plus", negative_input_variable="input-minus",
        positive_output="outp", negative_output="outn", common_mode_v=0.5,
        common_mode_tolerance_v=1e-12, maximum_abs_output_v=0.1,
        load_and_feedback_description="Nominal open loop, unchanged registered load",
    ) | changes))


def samples(offset=0.1e-6, reverse=False):
    return [dict(inp=0.5 + x / 2, inn=0.5 - x / 2,
                 outp=0.5 + (x - offset) * (-1000 if reverse else 1000), outn=0.5)
            for x in (-1e-6, -0.5e-6, 0, 0.5e-6, 1e-6)]


@pytest.mark.parametrize("reverse", [False, True])
def test_signed_applied_input_null_bracket(reverse):
    result = sampled_input_nulling(samples(reverse=reverse), definition())
    assert result["value"] == pytest.approx(0.1e-6, abs=1e-15)
    assert result["bracket_v"] == pytest.approx([0, 0.5e-6])
    assert result["native_provenance"] == "NOT_ATTESTED"
    assert result["status"] == "OBSERVED_SAMPLED_INPUT_NULL"


def test_exact_interior_zero_and_no_extrapolation():
    assert sampled_input_nulling(samples(offset=0), definition())["value"] == 0
    assert sampled_input_nulling(samples(offset=2e-6), definition())["value"] is None
    assert sampled_input_nulling(samples(offset=1e-6), definition())["value"] is None


@pytest.mark.parametrize("bad", ["missing", "commonmode", "nan", "duplicate", "saturated",
                                 "flat", "nonmonotonic", "few"])
def test_unqualified_or_mixed_data_rejects(bad):
    data = samples()
    if bad == "missing":
        del data[0]["outn"]
    elif bad == "commonmode":
        data[0]["inn"] = 0.6
    elif bad == "nan":
        data[0]["outp"] = float("nan")
    elif bad == "duplicate":
        data[1] = data[0].copy()
    elif bad == "saturated":
        data[0]["outp"] = 1
    elif bad == "flat":
        data[1]["outp"] = data[0]["outp"]
    elif bad == "nonmonotonic":
        data[2]["outp"] = data[0]["outp"] - 0.001
    else:
        data = data[:2]
    with pytest.raises(OperationRejected):
        sampled_input_nulling(data, definition())


def test_definition_does_not_allow_same_input_or_output():
    with pytest.raises(ValidationError):
        definition(negative_output="outp")


@pytest.mark.asyncio
async def test_capture_keeps_non_input_bias_conditions(monkeypatch):
    from contextlib import nullcontext
    from types import SimpleNamespace as NS
    from unittest.mock import AsyncMock

    from cadence_mcp_bridge import generic_analog

    identities = [f"00000000-0000-4000-8000-{i:012d}" for i in range(1, 4)]
    progress = NS(phase="SUCCEEDED")
    records = [NS(operation_id=identity, progress=progress, plan=NS(
        plan_sha256="a" * 64, resource_domain_sha256="b" * 64, ledger_ref="retained",
        analysis="dc", request=NS(values=[
            NS(logical_id="input-plus", value="0.5", unit="V"),
            NS(logical_id="input-minus", value="0.5", unit="V"),
        ]),
    )) for identity in identities]
    observation = NS(progress=progress, check=lambda record: None)
    provider = NS(report_result=AsyncMock(return_value=(observation, {
        "nodes": [{"logical_id": "inp", "value": 0.5}, {"logical_id": "inn", "value": 0.5}],
    })))
    store = NS(connection=lambda **kwargs: nullcontext(None),
               _read_operation=lambda connection, identity: records[identities.index(identity)])
    native = NS(current=lambda: None, lifecycle=NS(store=store), provider=provider,
                context=NS(resource_domain_sha256="b" * 64, binding=NS(ledger_ref="retained")))

    def report(record, result):
        bias = "0.32" if record.operation_id == identities[0] else "0.33"
        return NS(analysis_conditions=NS(static_statements_sha256="a" * 64),
                  conditions=lambda: {"values": [
                      {"logical_id": "input-plus", "value": "0.5"},
                      {"logical_id": "input-minus", "value": "0.5"},
                      {"logical_id": "bias-n", "value": bias},
                  ]}, model_dump=lambda **kwargs: {})

    monkeypatch.setattr(generic_analog, "make_report", report)
    with pytest.raises(OperationRejected) as caught:
        await generic_analog.capture_offset(native, [
            {"operation_id": identity, "expected_plan_sha256": "a" * 64}
            for identity in identities
        ], definition())
    assert caught.value.reason == "offset_source_or_conditions_mismatch"
    assert provider.report_result.await_count == 2
