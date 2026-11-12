from __future__ import annotations

import hashlib
from typing import Literal

import pytest

from cadence_mcp_bridge.candidate_contracts import CandidateSourceTarget, CandidateVariableBinding
from cadence_mcp_bridge.parameter_changes import (
    ChangeBaseline,
    ChangePlan,
    ChangeValue,
    DerivedChange,
    DerivedValue,
    MosWidthQualification,
    MosWidthTarget,
    Readback,
    plan_ade_change,
    plan_mos_width_change,
    project_netlist_change,
    verify_change_readback,
)
from cadence_mcp_bridge.schematic_plan import RevisionBinding
from cadence_mcp_bridge.variable_contracts import VariableContract, canonical_digest

PARENT = RevisionBinding(
    workspace_id="workspace",
    design_id="inverter",
    revision_id="base",
    source_baseline_sha256="a" * 64,
)
BASELINE = ChangeBaseline(
    revision=PARENT,
    revision_sha256="b" * 64,
    testbench_revision_sha256="c" * 64,
    fixed_conditions_sha256="d" * 64,
    netlist_sha256="9" * 64,
)
CHILD = RevisionBinding(
    workspace_id="workspace",
    design_id="inverter",
    revision_id="candidate",
    source_baseline_sha256="a" * 64,
    parent_revision_id="base",
    parent_revision_sha256="b" * 64,
)
MP = CandidateSourceTarget(
    instance_path="DUT/MP",
    master_library="gpdk090",
    master_cell="pmos1v",
    master_view="symbol",
    property_name="w",
)
BIAS = VariableContract(
    logical_id="bias",
    cadence_binding="m2_vin",
    unit="V",
    value_type="real",
    default="0",
    mutation_policy="owned_copy_only",
    range_status="qualified",
    minimum="0",
    maximum="1",
    step_policy="grid",
    step="0.1",
    fixed_value=None,
    review_id="review",
)
VIN = CandidateVariableBinding(
    logical_id="bias",
    cadence_binding="m2_vin",
    binding_evidence_sha256="e" * 64,
    targets=(
        CandidateSourceTarget(
            instance_path="VIN",
            master_library="analogLib",
            master_cell="vpulse",
            master_view="symbol",
            property_name="vdc",
        ),
    ),
)


def _bias(requested: ChangeValue | None = None) -> ChangePlan:
    return plan_ade_change(
        BASELINE,
        "candidate",
        CHILD,
        BIAS,
        VIN,
        ChangeValue(value="0", unit="V"),
        requested or ChangeValue(value="0.3", unit="V"),
    )


def _mos() -> MosWidthQualification:
    return MosWidthQualification(
        baseline=BASELINE,
        target=MosWidthTarget(instance=MP),
        old=ChangeValue(value="350", unit="nm"),
        expected=ChangeValue(value="120", unit="nm"),
        fingers=1,
        multiplicity=1,
        cdf_evidence_sha256="f" * 64,
        legal_value_evidence_sha256="1" * 64,
        update_route_evidence_sha256="2" * 64,
        derived=(
            DerivedChange(
                before=DerivedValue(property_name="fw", value="350n"),
                after=DerivedValue(property_name="fw", value="120n"),
            ),
        ),
    )


_READBACK_STAGES: tuple[Literal["baseline", "reopened", "netlist"], ...] = (
    "baseline",
    "reopened",
    "netlist",
)


def _row(plan: ChangePlan, stage: Literal["baseline", "reopened", "netlist"]) -> Readback:
    baseline = stage == "baseline"
    return Readback(
        stage=stage,
        plan_sha256=plan.plan_sha256,
        target_sha256=canonical_digest(plan.target),
        revision=PARENT if baseline else CHILD,
        revision_sha256=("b" if baseline else "6") * 64,
        testbench_revision_sha256=("c" if baseline else "7") * 64,
        fixed_conditions_sha256="d" * 64,
        artifact_sha256={"baseline": "3", "reopened": "4", "netlist": "5"}[stage] * 64,
        value=plan.old if baseline else plan.expected,
        mos_fingers=1 if isinstance(plan.target, MosWidthTarget) and stage != "netlist" else None,
        mos_multiplicity=1
        if isinstance(plan.target, MosWidthTarget) and stage != "netlist"
        else None,
        derived=tuple(
            d.before if baseline else d.after
            for d in plan.allowed_derived
            if stage != "netlist" or d.before.property_name != "fw"
        ),
    )


def test_ade_reuses_reviewed_grid_and_exact_binding() -> None:
    plan = _bias()
    assert plan.target.kind == "ade_variable"
    assert plan.target.binding == VIN
    with pytest.raises(ValueError, match="numeric contract"):
        _bias(ChangeValue(value="0.35", unit="V"))
    with pytest.raises(ValueError, match="numeric contract"):
        _bias(ChangeValue(value="0.3", unit="A"))
    with pytest.raises(ValueError, match="fresh child"):
        plan_ade_change(
            BASELINE,
            "candidate",
            PARENT,
            BIAS,
            VIN,
            ChangeValue(value="0", unit="V"),
            ChangeValue(value="0.3", unit="V"),
        )


@pytest.mark.parametrize("value", ["0", "-0.12", "NaN", "Infinity", "1e100"])
def test_invalid_widths(value: str) -> None:
    with pytest.raises(ValueError):
        ChangeValue(value=value, unit="um")


def test_width_allows_equivalent_units_and_denies_other_values_or_properties() -> None:
    qualification = _mos()
    request = ChangeValue(value=".12", unit="um")
    plan = plan_mos_width_change(qualification, "candidate", CHILD, request)
    assert plan.requested == request
    assert plan.expected.normalized == ("0.00000012", "m")
    with pytest.raises(ValueError, match="finite transition"):
        plan_mos_width_change(
            qualification, "candidate", CHILD, ChangeValue(value="121", unit="nm")
        )
    with pytest.raises(ValueError, match="width route"):
        MosWidthTarget(instance=MP.model_copy(update={"property_name": "nf"}))


def test_readback_matches_independent_values_and_never_authorizes() -> None:
    plan = plan_mos_width_change(_mos(), "candidate", CHILD, ChangeValue(value=".12", unit="um"))
    baseline, reopened, netlist = (_row(plan, stage) for stage in _READBACK_STAGES)
    netlist = netlist.model_copy(update={"value": ChangeValue(value=".12", unit="um")})
    result = verify_change_readback(plan, baseline=baseline, reopened=reopened, netlist=netlist)
    assert result.status == "MATCHED"
    assert result.execution_authorized is False
    assert result.netlist is not None and result.netlist.value.unit == "um"


def test_readback_does_not_infer_proof_and_rejects_stale_or_changed_evidence() -> None:
    plan = _bias()
    baseline, reopened, netlist = (_row(plan, stage) for stage in _READBACK_STAGES)
    assert verify_change_readback(plan, reopened=reopened).status == "MISSING"
    stale = netlist.model_copy(update={"revision_sha256": "8" * 64})
    assert (
        verify_change_readback(plan, baseline=baseline, reopened=reopened, netlist=stale).status
        == "STALE"
    )
    changed = netlist.model_copy(update={"fixed_conditions_sha256": "8" * 64})
    assert (
        verify_change_readback(plan, baseline=baseline, reopened=reopened, netlist=changed).reason
        == "netlist_fixed_conditions_changed"
    )
    unchanged = netlist.model_copy(update={"value": plan.old})
    assert (
        verify_change_readback(plan, baseline=baseline, reopened=reopened, netlist=unchanged).reason
        == "netlist_value_mismatch"
    )
    copied = netlist.model_copy(update={"artifact_sha256": reopened.artifact_sha256})
    assert (
        verify_change_readback(plan, baseline=baseline, reopened=reopened, netlist=copied).reason
        == "independent_readback_artifacts_required"
    )


_NETLIST = b"""simulator lang=spectre
global 0
parameters m2_vin=0
subckt InvLong vdd vin vout vss
MP (vout vin vdd vdd) pmos w=(350n) l=100n m=(1)*(1) simM=(1)*(1)
ends InvLong
DUT (vdd vin vout 0) InvLong
VIN (vin 0) vsource dc=m2_vin type=dc
"""


def test_raw_netlist_width_projection_and_wrong_scope() -> None:
    baseline = BASELINE.model_copy(update={"netlist_sha256": hashlib.sha256(_NETLIST).hexdigest()})
    qual = _mos().model_copy(update={"baseline": baseline})
    plan = plan_mos_width_change(qual, "candidate", CHILD, ChangeValue(value="120", unit="nm"))
    changed = _NETLIST.replace(b"(350n)", b"(120n)")
    projection = project_netlist_change(plan, _NETLIST, changed)
    assert projection.value == ChangeValue(value="120", unit="nm")
    assert projection.artifact_sha256 == hashlib.sha256(changed).hexdigest()
    with pytest.raises(ValueError, match="effective netlist value"):
        project_netlist_change(plan, _NETLIST, _NETLIST)
    with pytest.raises(ValueError, match="fixed netlist"):
        project_netlist_change(plan, _NETLIST, changed.replace(b") pmos", b") wrong_model"))
    with pytest.raises(ValueError, match="fixed netlist"):
        project_netlist_change(
            plan, _NETLIST, changed.replace(b"(vout vin vdd vdd)", b"(vout vin vdd vss)")
        )
    moved = changed.replace(
        b"MP (vout vin vdd vdd) pmos w=(120n) l=100n m=(1)*(1) simM=(1)*(1)\nends InvLong",
        b"ends InvLong\nMP (vout vin vdd vdd) pmos w=(120n) l=100n m=(1)*(1) simM=(1)*(1)",
    )
    with pytest.raises(ValueError, match="instance is missing"):
        project_netlist_change(plan, _NETLIST, moved)


def test_raw_ade_projection_and_fixed_source_binding() -> None:
    baseline = BASELINE.model_copy(update={"netlist_sha256": hashlib.sha256(_NETLIST).hexdigest()})
    plan = _bias().model_copy(update={"baseline": baseline})
    changed = _NETLIST.replace(b"m2_vin=0", b"m2_vin=0.3")
    assert project_netlist_change(plan, _NETLIST, changed).value == ChangeValue(
        value="0.3", unit="V"
    )
    with pytest.raises(ValueError, match="fixed netlist"):
        project_netlist_change(plan, _NETLIST, changed.replace(b"dc=m2_vin", b"dc=0"))
    with pytest.raises(ValueError, match="baseline netlist digest"):
        project_netlist_change(plan, changed, changed)


def test_planning_revalidates_nested_model_copy_values() -> None:
    qualification = _mos()
    forged_target = qualification.target.model_copy(
        update={"instance": MP.model_copy(update={"property_name": "fingers"})}
    )
    forged = qualification.model_copy(update={"target": forged_target})
    with pytest.raises(ValueError, match="width route"):
        plan_mos_width_change(forged, "candidate", CHILD, qualification.expected)

    plan = _bias()
    forged_row = _row(plan, "netlist").model_copy(
        update={"value": ChangeValue(value="0.3", unit="V").model_copy(update={"value": "NaN"})}
    )
    with pytest.raises(ValueError, match="bounded decimal"):
        verify_change_readback(plan, netlist=forged_row)
