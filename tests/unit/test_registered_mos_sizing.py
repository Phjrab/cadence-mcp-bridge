"""Closed host-side tests for fresh W/L values and distinct native captures."""

from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest
from test_registered_mos_edit import _cdf_frame, _guest_tuple

from cadence_mcp_bridge.candidate_contracts import CandidateSourceTarget
from cadence_mcp_bridge.parameter_changes import ChangeBaseline
from cadence_mcp_bridge.registered_mos_edit import (
    MosEditSnapshot,
    MosPropertyValue,
    NativeMosEditCapture,
    NativeMosEditReadback,
    RegisteredMosEditBinding,
    RetainedMosEdit,
)
from cadence_mcp_bridge.registered_mos_sizing import (
    MosSizingBounds,
    MosSizingLength,
    MosSizingSupport,
    MosSizingTarget,
    MosSizingValues,
    RegisteredMosSizingRoute,
    RegisteredMosSizingService,
    plan_registered_mos_sizing,
    verify_mos_sizing_save,
)
from cadence_mcp_bridge.schematic_plan import RevisionBinding
from cadence_mcp_bridge.variable_contracts import canonical_digest


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _length(value: str, unit="nm") -> MosSizingLength:
    return MosSizingLength(value=value, unit=unit)


class _Provider:
    record: RetainedMosEdit | None = None

    def __init__(self, publication: NativeMosEditCapture | None) -> None:
        self.publication = publication
        self.dispatches = 0
        self.claims = 0

    def lookup(self, binding):
        return self.record

    def claim(self, binding):
        assert self.record is None
        self.claims += 1
        self.record = RetainedMosEdit(None)
        return True

    def dispatch(self, binding):
        self.dispatches += 1
        self.record = RetainedMosEdit(self.publication)
        return self.record


def _input(length: str, area: str) -> bytes:
    return (
        "simulator lang=spectre\nparameters VDD=1\n"
        "subckt InvLong vdd vin vout vss\n"
        f"MN (vout vin vss vss) gpdk090_nmos1v w=(120n) l={length} "
        f"as={area} ad=98f ps=1.26u pd=1.26u m=(1)*(1) simM=(1)*(1)\n"
        "ends InvLong\nDUT (vdd vin vout 0) InvLong\n"
    ).encode("ascii")


def _fixture():
    baseline_input = _input("100n", "98f")
    after_input = _input("2.5e-7", "1.04e-13")
    parent = RevisionBinding(
        workspace_id="research-workspace",
        design_id="cmos-long-inverter",
        revision_id="long-r1",
        source_baseline_sha256="1" * 64,
    )
    baseline = ChangeBaseline(
        revision=parent,
        revision_sha256="2" * 64,
        testbench_revision_sha256="3" * 64,
        fixed_conditions_sha256="4" * 64,
        netlist_sha256=_sha(baseline_input),
    )
    child = RevisionBinding(
        workspace_id=parent.workspace_id,
        design_id=parent.design_id,
        revision_id="candidate-one",
        parent_revision_id=parent.revision_id,
        parent_revision_sha256=baseline.revision_sha256,
        source_baseline_sha256=parent.source_baseline_sha256,
    )
    before = {key: MosPropertyValue.model_validate(row) for key, row in _guest_tuple(True).items()}
    for key, value in {"w": "120n", "fw": "120n", "model": "gpdk090_nmos1v"}.items():
        before[key] = before[key].model_copy(update={"oa_value": value, "cdf_value": value})
    before["dfm"] = MosPropertyValue(
        oa_type=None, oa_value=None, cdf_type="instData", cdf_units=None, cdf_value="Minimum"
    )
    support = MosSizingSupport(
        cadence_version="6.1.5.500.15",
        pdk_release="4.6",
        pdk_identity_sha256="5" * 64,
        adapter_sha256="6" * 64,
        cdf_constraints_sha256="7" * 64,
        l=MosSizingBounds(),
    )
    route = RegisteredMosSizingRoute(
        baseline=baseline,
        source_library="CmosLong20261111",
        source_cell="InvLong",
        testbench_cell="InvLongTb",
        target=MosSizingTarget(
            instance=CandidateSourceTarget(
                instance_path="DUT/MN",
                master_library="gpdk090",
                master_cell="nmos1v",
                master_view="symbol",
                property_name="l",
            ),
            netlist_path="DUT/MN",
            netlist_model="gpdk090_nmos1v",
            netlist_terminals=("vout", "vin", "vss", "vss"),
        ),
        support=support,
        before=before,
    )
    requested = MosSizingValues(l=_length("250"))
    plan = plan_registered_mos_sizing(route, child, requested)
    binding = RegisteredMosEditBinding(
        operation_id="11111111-1111-4111-8111-111111111111",
        owned_copy_operation_id="22222222-2222-4222-8222-222222222222",
        scope_sha256="8" * 64,
        plan_sha256=plan.plan_sha256,
        route_sha256=plan.route_sha256,
        owned_library="CmosLongSizingFixture",
        owned_cell="InvLong",
        owned_before_view_tree_sha256="9" * 64,
        owned_before_testbench_tree_sha256="a" * 64,
        source_preservation_sha256="b" * 64,
    )
    after = before.copy()
    for key, value in {"l": "0.25u", "as": "104f"}.items():
        after[key] = after[key].model_copy(update={"oa_value": value, "cdf_value": value})
    frame = _cdf_frame("nmos1v", after, "MN")
    start = MosEditSnapshot(
        stage="baseline",
        revision_sha256=binding.owned_before_view_tree_sha256,
        testbench_revision_sha256=binding.owned_before_testbench_tree_sha256,
        footprint_sha256="c" * 64,
        receipt_sha256="d" * 64,
        properties=before,
    )
    saved = start.model_copy(
        update={
            "stage": "saved",
            "revision_sha256": "e" * 64,
            "receipt_sha256": "f" * 64,
            "properties": after,
        }
    )
    reopened = saved.model_copy(update={"stage": "reopened", "receipt_sha256": "10" * 32})
    readback = NativeMosEditReadback(
        operation_id=binding.operation_id,
        plan_sha256=binding.plan_sha256,
        scope_sha256=binding.scope_sha256,
        source_preservation_sha256=binding.source_preservation_sha256,
        baseline=start,
        saved=saved,
        reopened=reopened,
        netlisted_revision_sha256=reopened.revision_sha256,
        netlisted_testbench_revision_sha256=reopened.testbench_revision_sha256,
        netlist_receipt_sha256="11" * 32,
        netlist_sha256=_sha(after_input),
        cdf_frame_sha256=_sha(frame),
    )
    capture = NativeMosEditCapture(readback=readback, netlist=after_input, cdf_frame=frame)
    return route, child, requested, plan, binding, baseline_input, capture


def _service(data, provider, *, requested=None, binding=None):
    route, child, default, _, original, baseline, _ = data
    binding = binding or original
    return RegisteredMosSizingService(
        binding,
        route,
        child,
        requested or default,
        baseline,
        provider,
        expected_binding_sha256=canonical_digest(binding),
    )


def test_new_requested_value_without_candidate_witness_and_identical_replay() -> None:
    data = _fixture()
    route, child, _, plan, _, _, capture = data
    provider = _Provider(capture)
    service = _service(data, provider)
    equivalent = MosSizingValues(l=_length("0.25", "um"))
    assert plan_registered_mos_sizing(route, child, equivalent) == plan
    assert plan.changed == ("l",) and plan.expected.w == _length("120")
    assert plan.allowed_derived == ("as", "ad", "ps", "pd")
    assert service.lookup(service.identity).outcome == "NOT_FOUND"
    first = service.apply(service.identity)
    assert first.outcome == "VERIFIED" and first.observed == plan.expected
    assert first.readback == capture.readback
    assert first.effective_input is not None
    assert first.effective_input.artifact_sha256 == _sha(capture.netlist)
    assert first.effective_mos_options == {
        "w": "(120n)",
        "l": "2.5e-7",
        "as": "1.04e-13",
        "ad": "98f",
        "ps": "1.26u",
        "pd": "1.26u",
        "m": "(1)*(1)",
        "simM": "(1)*(1)",
    }
    assert not first.analysis_execution_authorized
    replay_service = _service(data, provider, requested=equivalent)
    replay = replay_service.apply(replay_service.identity)
    assert replay.outcome == "VERIFIED" and replay.replayed and not replay.dispatched_this_call
    assert (provider.claims, provider.dispatches) == (1, 1)
    with pytest.raises(ValueError, match="registration"):
        _service(data, provider, requested=MosSizingValues(l=_length("260")))
    with pytest.raises(ValueError, match="approved operation"):
        service.apply(service.identity.model_copy(update={"expected_plan_sha256": "d" * 64}))
    assert (provider.claims, provider.dispatches) == (1, 1)


@pytest.mark.parametrize("value", ["0", "-1", "NaN", "Infinity", "1e999"])
def test_invalid_new_dimensions(value) -> None:
    with pytest.raises(ValueError):
        _length(value)


def test_registration_limits_and_common_parent() -> None:
    route, child, _, _, _, _, _ = _fixture()
    with pytest.raises(ValueError):
        MosSizingValues.model_validate({"m": {"value": "6", "unit": "nm"}})
    with pytest.raises(ValueError):
        _length("1", "m")
    with pytest.raises(ValueError, match="not registered"):
        plan_registered_mos_sizing(route, child, MosSizingValues(w=_length("400")))
    with pytest.raises(ValueError, match="does not change"):
        plan_registered_mos_sizing(route, child, MosSizingValues(l=_length("100")))
    with pytest.raises(ValueError, match="fresh child"):
        plan_registered_mos_sizing(
            route,
            child.model_copy(update={"parent_revision_sha256": "d" * 64}),
            MosSizingValues(l=_length("250")),
        )
    limit = MosSizingBounds(
        minimum=_length("100"), maximum=_length("400"), grid_step=_length("10"), grid_origin_nm="0"
    )
    route = route.model_copy(update={"support": route.support.model_copy(update={"l": limit})})
    with pytest.raises(ValueError, match="registered bounds"):
        plan_registered_mos_sizing(route, child, MosSizingValues(l=_length("410")))
    with pytest.raises(ValueError, match="registered grid"):
        plan_registered_mos_sizing(route, child, MosSizingValues(l=_length("251")))
    both_axes = route.model_copy(
        update={"support": route.support.model_copy(update={"w": MosSizingBounds()})}
    )
    plan = plan_registered_mos_sizing(
        both_axes, child, MosSizingValues(w=_length("0.2", "um"), l=_length("250"))
    )
    assert plan.changed == ("w", "l")
    assert plan.expected.w == _length("200") and plan.expected.l == _length("250")
    assert plan.allowed_derived == ("fw", "as", "ad", "ps", "pd")


def test_changed_oa_and_fixed_fields_fail_before_reopen() -> None:
    route, _, _, plan, binding, _, capture = _fixture()
    save = capture.readback
    verify_mos_sizing_save(plan, route, binding, save)
    for key, value, error in (
        ("l", "249n", "saved OA property l"),
        ("w", "110n", "held property w"),
        ("model", "gpdk090_pmos1v", "fixed property model"),
        ("dfm", "DFM", "fixed property dfm"),
    ):
        properties = save.saved.properties.copy()
        properties[key] = properties[key].model_copy(
            update={"oa_type": "string", "oa_value": value}
        )
        invalid = save.model_copy(
            update={"saved": save.saved.model_copy(update={"properties": properties})}
        )
        with pytest.raises(ValueError, match=error):
            verify_mos_sizing_save(plan, route, binding, invalid)
    wrong_bench = save.saved.model_copy(update={"testbench_revision_sha256": "0" * 64})
    with pytest.raises(ValueError, match="testbench revision"):
        verify_mos_sizing_save(plan, route, binding, save.model_copy(update={"saved": wrong_bench}))


@pytest.mark.parametrize(
    "corruption", ["topology", "model", "l", "geometry", "factor", "stale", "cdf", "conditions"]
)
def test_mismatching_actual_candidate_stays_unknown_and_is_never_reapplied(corruption) -> None:
    data = _fixture()
    capture = data[-1]
    readback = capture.readback
    raw, cdf = capture.netlist, capture.cdf_frame
    if corruption == "stale":
        readback = readback.model_copy(
            update={"netlisted_revision_sha256": readback.baseline.revision_sha256}
        )
    elif corruption == "cdf":
        cdf = cdf.replace(b"0.25u", b"0.24u")
    else:
        old, new = {
            "topology": (b"(vout vin vss vss)", b"(vout vin vss vdd)"),
            "model": (b"gpdk090_nmos1v", b"gpdk090_pmos1v"),
            "l": (b"l=2.5e-7", b"l=2.4e-7"),
            "geometry": (b"as=1.04e-13", b"as=1.14e-13"),
            "factor": (b"simM=(1)*(1)", b"simM=(1)*(2)"),
            "conditions": (b"parameters VDD=1", b"parameters VDD=1.1"),
        }[corruption]
        raw = raw.replace(old, new)
    readback = readback.model_copy(
        update={"netlist_sha256": _sha(raw), "cdf_frame_sha256": _sha(cdf)}
    )
    provider = _Provider(replace(capture, readback=readback, netlist=raw, cdf_frame=cdf))
    service = _service(data, provider)
    first = service.apply(service.identity)
    assert first.outcome == "OUTCOME_UNKNOWN" and first.effective_input is None
    assert service.apply(service.identity).outcome == "OUTCOME_UNKNOWN"
    assert (provider.claims, provider.dispatches) == (1, 1)
