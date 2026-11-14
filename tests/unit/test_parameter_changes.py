from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Literal

import pytest

from cadence_mcp_bridge.candidate_contracts import CandidateSourceTarget, CandidateVariableBinding
from cadence_mcp_bridge.parameter_changes import (
    AmplifierPm0InputEvidence,
    CapacitorQualification,
    CapacitorTarget,
    ChangeBaseline,
    ChangePlan,
    ChangeValue,
    DerivedChange,
    DerivedValue,
    MosWidthQualification,
    MosWidthTarget,
    Readback,
    observe_amplifier_pm0_input,
    plan_ade_change,
    plan_capacitor_change,
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


def test_persisted_ade_checks_independent_values_and_keeps_physical_revision() -> None:
    # Fixture: only the selected ADE variable changes on the saved schematic.
    baseline = BASELINE.model_copy(update={"netlist_sha256": hashlib.sha256(_NETLIST).hexdigest()})
    requested = ChangeValue(value="0.3", unit="V")
    schematic_pin = "f" * 64
    plan = plan_ade_change(
        baseline,
        "candidate",
        CHILD,
        BIAS,
        VIN,
        ChangeValue(value="0", unit="V"),
        requested,
        schematic_revision_sha256=schematic_pin,
    )
    original, reopened, netlist = (
        _row(plan, stage).model_copy(
            update={
                "schematic_revision_sha256": schematic_pin,
                "testbench_revision_sha256": baseline.testbench_revision_sha256,
            }
        )
        for stage in _READBACK_STAGES
    )
    projection = project_netlist_change(
        plan, _NETLIST, _NETLIST.replace(b"m2_vin=0", b"m2_vin=0.30")
    )
    netlist = netlist.model_copy(
        update={"value": projection.value, "artifact_sha256": projection.artifact_sha256}
    )
    reopened = reopened.model_copy(update={"value": ChangeValue(value=".300", unit="V")})
    result = verify_change_readback(plan, baseline=original, reopened=reopened, netlist=netlist)
    assert result.status == "MATCHED"
    assert not result.execution_authorized
    assert result.reopened is not None
    assert result.reopened == reopened and result.netlist == netlist
    assert result.reopened.revision_sha256 != original.revision_sha256

    for update, status, reason in (
        ({"schematic_revision_sha256": None}, "MISSING", "reopened_schematic_revision_required"),
        (
            {"schematic_revision_sha256": "1" * 64},
            "CONFLICT",
            "reopened_schematic_revision_changed",
        ),
        (
            {"testbench_revision_sha256": "7" * 64},
            "CONFLICT",
            "reopened_testbench_revision_changed",
        ),
        ({"revision_sha256": original.revision_sha256}, "STALE", "reopened_binding_mismatch"),
        ({"value": plan.old}, "CONFLICT", "reopened_value_mismatch"),
    ):
        result = verify_change_readback(
            plan, baseline=original, reopened=reopened.model_copy(update=update), netlist=netlist
        )
        assert (result.status, result.reason) == (status, reason)

    assert verify_change_readback(plan, baseline=original, netlist=netlist).status == "MISSING"
    unrelated_tb = {"testbench_revision_sha256": "7" * 64}
    assert (
        verify_change_readback(
            plan,
            baseline=original,
            reopened=reopened.model_copy(update=unrelated_tb),
            netlist=netlist.model_copy(update=unrelated_tb),
        ).reason
        == "reopened_testbench_revision_changed"
    )
    assert (
        verify_change_readback(
            plan,
            baseline=original,
            reopened=reopened.model_copy(update={"artifact_sha256": netlist.artifact_sha256}),
            netlist=netlist,
        ).reason
        == "independent_readback_artifacts_required"
    )
    legacy = _bias()
    assert "schematic_revision_sha256" not in legacy.target.model_dump()
    assert "schematic_revision_sha256" not in _row(legacy, "reopened").model_dump()


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


_CAP_NETLIST = _NETLIST + b"CL (vout 0) capacitor c=1p\n"


def _capacitor() -> CapacitorQualification:
    return CapacitorQualification(
        baseline=BASELINE.model_copy(
            update={"netlist_sha256": hashlib.sha256(_CAP_NETLIST).hexdigest()}
        ),
        target=CapacitorTarget(
            instance=CandidateSourceTarget(
                instance_path="CL",
                master_library="analogLib",
                master_cell="cap",
                master_view="symbol",
                property_name="c",
            )
        ),
        old=ChangeValue(value="1", unit="pF"),
        expected=ChangeValue(value="2", unit="pF"),
        cdf_evidence_sha256="f" * 64,
        legal_value_evidence_sha256="1" * 64,
        update_route_evidence_sha256="2" * 64,
    )


def test_capacitor_projects_only_the_registered_load_and_compares_readback() -> None:
    requested = ChangeValue(value="2e-12", unit="F")
    plan = plan_capacitor_change(_capacitor(), "candidate", CHILD, requested)
    candidate = _CAP_NETLIST.replace(b"c=1p", b"c=2p")
    projection = project_netlist_change(plan, _CAP_NETLIST, candidate)
    assert plan.requested == requested
    assert projection.value == ChangeValue(value="2", unit="pF")
    baseline = _row(plan, "baseline")
    reopened = _row(plan, "reopened").model_copy(update={"value": requested})
    netlist = _row(plan, "netlist").model_copy(
        update={"value": projection.value, "artifact_sha256": projection.artifact_sha256}
    )
    result = verify_change_readback(plan, baseline=baseline, reopened=reopened, netlist=netlist)
    assert result.status == "MATCHED"
    assert result.execution_authorized is False


def test_capacitor_rejects_wrong_unit_or_another_target() -> None:
    qualification = _capacitor()
    with pytest.raises(ValueError, match="qualified finite"):
        plan_capacitor_change(qualification, "candidate", CHILD, ChangeValue(value="2", unit="V"))
    with pytest.raises(ValueError, match="observed analogLib cap CL c"):
        CapacitorTarget(
            instance=qualification.target.instance.model_copy(update={"instance_path": "C1"})
        )


def test_capacitor_rejects_other_device_or_load_connectivity_delta() -> None:
    qualification = _capacitor()
    plan = plan_capacitor_change(qualification, "candidate", CHILD, qualification.expected)
    candidate = _CAP_NETLIST.replace(b"c=1p", b"c=2p")
    with pytest.raises(ValueError, match="fixed netlist"):
        project_netlist_change(plan, _CAP_NETLIST, candidate.replace(b"l=100n", b"l=120n"))
    with pytest.raises(ValueError, match="unsupported CL"):
        project_netlist_change(plan, _CAP_NETLIST, candidate.replace(b"CL (vout 0)", b"CL (vin 0)"))


def test_capacitor_rejects_reuse_of_baseline_testbench_revision() -> None:
    qualification = _capacitor()
    plan = plan_capacitor_change(qualification, "candidate", CHILD, qualification.expected)
    baseline = _row(plan, "baseline")
    stale_binding = {"testbench_revision_sha256": plan.baseline.testbench_revision_sha256}
    reopened = _row(plan, "reopened").model_copy(update=stale_binding)
    netlist = _row(plan, "netlist").model_copy(update=stale_binding)

    result = verify_change_readback(plan, baseline=baseline, reopened=reopened, netlist=netlist)

    assert result.status == "STALE"
    assert result.reason == "capacitor_testbench_revision_reuses_baseline"


def test_width_accepts_only_the_exact_contiguous_top_level_bench_permutation() -> None:
    dut = b"DUT (vdd vin vout 0) InvLong\n"
    sources = (
        b"VDD (vdd 0) vsource dc=1 type=dc\n"
        b"VIN (vin 0) vsource dc=m2_vin type=pulse val0=0 val1=1 period=150n "
        b"delay=10n rise=100p fall=100p width=65n\n"
        b"CL (vout 0) capacitor c=1p\n"
    )
    raw = _NETLIST[: _NETLIST.index(dut)] + dut + sources
    baseline = BASELINE.model_copy(update={"netlist_sha256": hashlib.sha256(raw).hexdigest()})
    qualification = _mos().model_copy(update={"baseline": baseline})
    plan = plan_mos_width_change(qualification, "candidate", CHILD, qualification.expected)
    candidate = raw.replace(dut + sources, sources + dut).replace(b"(350n)", b"(120n)")

    projected = project_netlist_change(plan, raw, candidate)
    assert projected.value == qualification.expected
    assert projected.artifact_sha256 == hashlib.sha256(candidate).hexdigest()

    for changed in (
        candidate.replace(dut, dut + b"VDD (vdd 0) vsource dc=1 type=dc\n"),
        candidate.replace(dut, dut + b"Cextra (vin 0) capacitor c=1p\n"),
        candidate.replace(b"DUT (vdd vin vout 0)", b"DUT (vdd vout vin 0)"),
        candidate.replace(b"capacitor c=1p", b"capacitor c=2p"),
        candidate.replace(b"parameters m2_vin=0\n", b"") + b"parameters m2_vin=0\n",
    ):
        with pytest.raises(ValueError, match="fixed netlist"):
            project_netlist_change(plan, raw, changed)


def test_amplifier_pm0_projection_is_exact_and_does_not_qualify_a_width(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cadence_mcp_bridge import parameter_changes

    pm0 = (
        b"PM0 (net33 Vbiasp VDD VDD) gpdk090_pmos1v w=(20u) l=1u "
        b"as=5.6p ad=5.6p ps=40.56u pd=40.56u m=(1)*(1) simM=(1)*(1)"
    )
    raw = b"simulator lang=spectre\nparameters VBIASN=320m VBIASP=702m\n" + pm0 + b"\n"
    monkeypatch.setattr(parameter_changes, "_AMP_CENTER_SHA256", hashlib.sha256(raw).hexdigest())
    monkeypatch.setattr(
        parameter_changes, "_AMP_PM0_STATEMENT_SHA256", hashlib.sha256(pm0).hexdigest()
    )
    revision = PARENT.model_copy(
        update={
            "design_id": "reference-differential-amplifier-tb2",
            "revision_id": "reference-amplifier-bias-grid-v1",
        }
    )
    baseline = BASELINE.model_copy(
        update={"revision": revision, "netlist_sha256": hashlib.sha256(raw).hexdigest()}
    )
    child = CHILD.model_copy(
        update={"design_id": revision.design_id, "parent_revision_id": revision.revision_id}
    )
    target = MosWidthTarget(instance=MP.model_copy(update={"instance_path": "PM0"}))
    # FIXTURE_ONLY: values and evidence are synthetic, including the candidate width.
    qualification = MosWidthQualification(
        baseline=baseline,
        target=target,
        old=ChangeValue(value="20", unit="um"),
        expected=ChangeValue(value="19", unit="um"),
        fingers=1,
        multiplicity=1,
        cdf_evidence_sha256="1" * 64,
        legal_value_evidence_sha256="2" * 64,
        update_route_evidence_sha256="3" * 64,
        derived=(
            DerivedChange(
                before=DerivedValue(property_name="fw", value="20u"),
                after=DerivedValue(property_name="fw", value="19u"),
            ),
        ),
    )
    plan = plan_mos_width_change(qualification, "candidate", child, qualification.expected)
    candidate = raw.replace(b"w=(20u)", b"w=(19000n)")
    projected = project_netlist_change(plan, raw, candidate)
    assert projected.value == ChangeValue(value="19000", unit="nm")
    assert projected.value != plan.requested
    for invalid, reason in (
        (candidate.replace(b"l=1u", b"l=2u"), "length must remain"),
        (candidate.replace(b"net33 Vbiasp", b"net34 Vbiasp"), "PM0 netlist binding"),
        (candidate.replace(b"as=5.6p", b"as=1p"), "fixed MOS netlist options"),
        (candidate.replace(b"VBIASN=320m", b"VBIASN=0.321"), "fixed netlist"),
        (candidate + pm0 + b"\n", "missing or ambiguous"),
        (
            candidate.replace(b"PM0 ", b"inline subckt Other\nPM0 ") + b"ends Other\n",
            "PM0 netlist binding",
        ),
    ):
        with pytest.raises(ValueError, match=reason):
            project_netlist_change(plan, raw, invalid)
    monkeypatch.setattr(parameter_changes, "_AMP_CENTER_SHA256", "0" * 64)
    with pytest.raises(ValueError, match="registered center DC baseline"):
        project_netlist_change(plan, raw, candidate)


def test_amplifier_pm0_input_observation_requires_independent_matching_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cadence_mcp_bridge import parameter_changes

    # FIXTURE_ONLY: both raw inputs and every evidence pin are synthetic.
    pm0 = (
        b"PM0 (net33 Vbiasp VDD VDD) gpdk090_pmos1v w=(20u) l=1u "
        b"as=5.6p ad=5.6p ps=40.56u pd=40.56u m=(1)*(1) simM=(1)*(1)"
    )
    center = (
        b"simulator lang=spectre\nparameters VBIASN=320m VBIASP=702m\n"
        b"CL (net33 0) capacitor c=1p\n" + pm0 + b"\n"
    )
    candidate = (
        center.replace(b"w=(20u)", b"w=(0.12u)")
        .replace(b"VBIASN=320m VBIASP=702m", b"VBIASN=0.320 VBIASP=0.702")
        .replace(b"5.6p", b"69.6f")
        .replace(b"40.56u", b"1.16u")
    )
    monkeypatch.setattr(parameter_changes, "_AMP_CENTER_SHA256", hashlib.sha256(center).hexdigest())
    monkeypatch.setattr(
        parameter_changes, "_AMP_PM0_STATEMENT_SHA256", hashlib.sha256(pm0).hexdigest()
    )
    baseline = AmplifierPm0InputEvidence(
        revision_sha256="1" * 64,
        testbench_revision_sha256="2" * 64,
        oa_cdf_sha256="3" * 64,
        netlist_sha256=hashlib.sha256(center).hexdigest(),
        width=ChangeValue(value="20", unit="um"),
        geometry=(
            DerivedValue(property_name="fw", value="20u"),
            DerivedValue(property_name="as", value="5.6p"),
            DerivedValue(property_name="ad", value="5.6p"),
            DerivedValue(property_name="ps", value="40.56u"),
            DerivedValue(property_name="pd", value="40.56u"),
        ),
    )
    child = AmplifierPm0InputEvidence(
        revision_sha256="4" * 64,
        testbench_revision_sha256="5" * 64,
        oa_cdf_sha256="6" * 64,
        netlist_sha256=hashlib.sha256(candidate).hexdigest(),
        width=ChangeValue(value="120", unit="nm"),
        geometry=(
            DerivedValue(property_name="fw", value="120n"),
            DerivedValue(property_name="as", value="69.6f"),
            DerivedValue(property_name="ad", value="69.6f"),
            DerivedValue(property_name="ps", value="1.16u"),
            DerivedValue(property_name="pd", value="1.16u"),
        ),
    )

    def observe(raw: bytes, evidence: AmplifierPm0InputEvidence = child):
        return observe_amplifier_pm0_input(
            center,
            raw,
            baseline=baseline,
            child=evidence,
            diagnostic_receipt_sha256="7" * 64,
            footprint_receipt_sha256="8" * 64,
            dfm_evidence_sha256="9" * 64,
            baseline_effective_dfm="Minimum",
            child_effective_dfm="DFM",
        )

    result = observe(candidate)
    assert result.status == "OBSERVATION_ONLY"
    assert result.scope == "NETLIST_INPUT_ONLY"
    assert result.oa_footprint == "MISMATCHED"
    assert result.oa_change_status == "UNQUALIFIED_EXTRA_SETTING"
    assert result.receipt_authentication == "NOT_VERIFIED_BY_THIS_API"
    assert result.automatic_update_route == result.geometry_mode == "NOT_OBSERVED"
    assert not (
        result.admission_authorized or result.execution_authorized or result.selection_authorized
    )
    assert result.netlist.artifact_sha256 == child.netlist_sha256
    assert result.netlist.value == ChangeValue(value="0.12", unit="um")
    assert result.netlist.derived == child.geometry[1:]
    assert result.baseline == baseline and result.child == child
    assert result.dfm_evidence_sha256 == "9" * 64
    assert (result.baseline_effective_dfm, result.child_effective_dfm) == ("Minimum", "DFM")

    args = dict(
        baseline=baseline,
        child=child,
        diagnostic_receipt_sha256="7" * 64,
        footprint_receipt_sha256="8" * 64,
        dfm_evidence_sha256="9" * 64,
        baseline_effective_dfm="Minimum",
    )
    # Exercise malformed inputs from an untyped caller.
    call_observer: Callable[..., object] = observe_amplifier_pm0_input
    with pytest.raises(TypeError, match="child_effective_dfm"):
        call_observer(center, candidate, **args)
    with pytest.raises(ValueError, match="child_effective_dfm"):
        call_observer(center, candidate, **args, child_effective_dfm="Minimum")

    with pytest.raises(ValueError, match="child netlist digest mismatch"):
        observe(candidate + b"\n")
    for invalid, reason in (
        (candidate.replace(b"l=1u", b"l=2u"), "length must remain"),
        (candidate.replace(b"gpdk090_pmos1v", b"other_model"), "PM0 netlist binding"),
        (candidate.replace(b"capacitor c=1p", b"capacitor c=2p"), "fixed netlist"),
        (candidate.replace(b"VBIASP=0.702", b"VBIASP=0.701"), "center bias changed"),
        (candidate.replace(b"VBIASP=0.702", b"VBIASP=701m"), "scalar_expression_denied"),
        (candidate.replace(b"VBIASP=0.702", b"VBIASP=(0.702)"), "scalar_expression_denied"),
        (candidate.replace(b"ad=69.6f", b"ad=1p"), "geometry differs"),
        (candidate.replace(b"w=(0.12u)", b"w=(0.13u)"), "effective netlist width differs"),
        (candidate.replace(b"l=1u", b"l=1u dfm=DFM"), "fixed MOS netlist options"),
    ):
        with pytest.raises(ValueError, match=reason):
            observe(
                invalid,
                child.model_copy(update={"netlist_sha256": hashlib.sha256(invalid).hexdigest()}),
            )
    with pytest.raises(ValueError, match="distinct PM0 revisions"):
        observe(
            candidate,
            child.model_copy(
                update={"testbench_revision_sha256": baseline.testbench_revision_sha256}
            ),
        )
    with pytest.raises(ValueError, match="complete observed PM0 geometry"):
        observe(candidate, child.model_copy(update={"geometry": (child.geometry[0],) * 5}))
