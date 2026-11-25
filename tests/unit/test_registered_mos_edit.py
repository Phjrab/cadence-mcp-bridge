"""Synthetic transport exercises. Real qualification and receipts belong to C1."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import time
from copy import deepcopy
from pathlib import Path
from typing import Literal

import pytest
from test_runtime_context import make_settings

from cadence_mcp_bridge import _registered_mos_edit_phase as guest_source
from cadence_mcp_bridge import registered_mos_transport as host
from cadence_mcp_bridge.candidate_contracts import CandidateSourceTarget
from cadence_mcp_bridge.domain_provisioning import _canonical
from cadence_mcp_bridge.operator_operations import OperationRejected
from cadence_mcp_bridge.parameter_changes import (
    ChangeBaseline,
    ChangeValue,
    DerivedChange,
    DerivedValue,
    MosOptionTransition,
    RegisteredMosQualification,
    RegisteredMosTarget,
    mos_multiplicity_factors,
)
from cadence_mcp_bridge.registered_mos_edit import (
    MosCdfWriteField,
    MosEditSnapshot,
    MosEditValues,
    MosExplicitSet,
    MosProperty,
    MosPropertyValue,
    MosSetWitness,
    NativeMosEditCapture,
    NativeMosEditReadback,
    NativeMosEditSave,
    RegisteredMosEditBinding,
    RegisteredMosEditRoute,
    RegisteredMosEditService,
    RetainedMosEdit,
    plan_registered_mos_edit,
    verify_explicit_set_evidence,
)
from cadence_mcp_bridge.runtime_context import load_runtime
from cadence_mcp_bridge.schematic_plan import RevisionBinding
from cadence_mcp_bridge.variable_contracts import canonical_digest


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _row(value: str, *, length: bool = False, explicit: bool = True) -> MosPropertyValue:
    return MosPropertyValue(
        oa_type="string" if explicit else None,
        oa_value=value if explicit else None,
        cdf_type="string",
        cdf_units="lengthMetric" if length else None,
        cdf_value=value,
    )


def _fixture(
    master: Literal["nmos1v", "pmos1v"] = "pmos1v",
    primary: Literal["w", "l", "m"] = "w",
    joint: bool = False,
) -> tuple[RegisteredMosEditRoute, RevisionBinding, bytes, bytes, MosEditValues]:
    parent = RevisionBinding(
        workspace_id="test-mos",
        design_id="test-inverter",
        revision_id="base",
        source_baseline_sha256="1" * 64,
    )
    child = parent.model_copy(
        update={
            "revision_id": "child",
            "parent_revision_id": parent.revision_id,
            "parent_revision_sha256": "2" * 64,
        }
    )
    model = f"gpdk090_{master}"

    def netlist(width: str, length: str, area: str, multiplier: str = "1") -> bytes:
        return (
            "simulator lang=spectre\nparameters VDD=1\n"
            f"subckt Inv vdd vin vout gnd\n"
            f"M0 (vout vin vdd vdd) {model} w=({width}) l={length} as={area} "
            f"ad=98f ps=1.26u pd=1.26u m=({multiplier})*(1) simM=({multiplier})*(1)\n"
            "ends Inv\nDUT (vdd vin vout 0) Inv\n"
        ).encode("ascii")

    baseline, new = (
        netlist("350n", "100n", "98f"),
        netlist(
            "120n" if primary == "w" else "350n",
            "150n" if joint or primary == "l" else "100n",
            "69.6f" if primary == "w" else "98f",
            "6" if primary == "m" else "1",
        ),
    )
    before: dict[MosProperty, MosPropertyValue] = {
        "w": _row("350n", length=True),
        "fw": _row("350n", length=True),
        "l": _row("100n", length=True),
        "m": _row("1"),
        "fingers": _row("1"),
        "as": _row("98f"),
        "ad": _row("98f"),
        "ps": _row("1.26u", length=True),
        "pd": _row("1.26u", length=True),
        "model": _row(model),
        "dfm": _row("Minimum"),
        "nf": MosPropertyValue(
            oa_type=None,
            oa_value=None,
            cdf_type=None,
            cdf_units=None,
            cdf_value=None,
        ),
    }
    after = before.copy()
    if primary == "w":
        after["w"] = after["fw"] = _row("120n", length=True, explicit=False)
        after["as"] = _row("69.6f", explicit=False)
        options = (
            MosOptionTransition(name="w", before="(350n)", after="(120n)"),
            MosOptionTransition(name="as", before="98f", after="69.6f"),
        )
        derived = (
            DerivedChange(
                before=DerivedValue(property_name="fw", value="350n"),
                after=DerivedValue(property_name="fw", value="120n"),
            ),
            DerivedChange(
                before=DerivedValue(property_name="as", value="98f"),
                after=DerivedValue(property_name="as", value="69.6f"),
            ),
        )
        old, new_value = "350", "120"
    elif primary == "l":
        after["l"] = _row("150n", length=True)
        options = (MosOptionTransition(name="l", before="100n", after="150n"),)
        derived = ()
        old, new_value = "100", "150"
    else:
        after["m"] = _row("6")
        options = (
            MosOptionTransition(name="m", before="(1)*(1)", after="(6)*(1)"),
            MosOptionTransition(name="simM", before="(1)*(1)", after="(6)*(1)"),
        )
        derived = ()
        old, new_value = "1", "6"
    if joint:
        after["l"] = _row("150n", length=True)
        options += (MosOptionTransition(name="l", before="100n", after="150n"),)
    qualification = RegisteredMosQualification(
        baseline=ChangeBaseline(
            revision=parent,
            revision_sha256="2" * 64,
            testbench_revision_sha256="3" * 64,
            fixed_conditions_sha256="4" * 64,
            netlist_sha256=_sha(baseline),
        ),
        target=RegisteredMosTarget(
            instance=CandidateSourceTarget(
                instance_path="DUT/M0",
                master_library="gpdk090",
                master_cell=master,
                master_view="symbol",
                property_name=primary,
            ),
            quantity="count" if primary == "m" else "length",
            scalar_option=primary,
            scalar_unit="count" if primary == "m" else "nm",
            netlist_path="DUT/M0",
            netlist_model=model,
            netlist_terminals=("vout", "vin", "vdd", "vdd"),
            options=options,
        ),
        old=ChangeValue(value=old, unit="count" if primary == "m" else "nm"),
        expected=ChangeValue(value=new_value, unit="count" if primary == "m" else "nm"),
        evidence_sha256="5" * 64,
        derived=derived,
    )
    request = MosEditValues(**{primary: qualification.expected})
    if joint:
        request = request.model_copy(update={"l": ChangeValue(value="150", unit="nm")})
    route = RegisteredMosEditRoute(
        qualification=qualification,
        before=before,
        after=after,
        update_route_sha256="6" * 64,
    )
    return route, child, baseline, new, request


def _cdf_frame(
    master: str, properties: dict[MosProperty, MosPropertyValue], slot: str = "M0"
) -> bytes:
    lines = ["M2_CDF_V2", f'DEVICE|"gpdk090"|"{master}"|"{slot}"']
    lines.extend(f'TERM|"{key}"' for key in ("D", "G", "S", "B"))
    expressions = {
        "simW": _row('iPar("fw")', length=True),
        "simM": _row('iPar("m")*iPar("fingers")'),
    }
    for scope in ("base", "effective"):
        for key, value in {**properties, **expressions}.items():
            if value.cdf_type is None:
                continue
            unit = json.dumps(value.cdf_units) if value.cdf_units is not None else "nil"
            literal = json.dumps(value.cdf_value)
            lines.append(f'PARAM|"{scope}"|"{key}"|"{value.cdf_type}"|{unit}|{literal}|{literal}')
        for key, kind in (
            ("simInfo", "list"),
            ("spectre", "list"),
            ("componentName", "symbol"),
            ("termOrder", "list"),
            ("namePrefix", "symbol"),
            ("modelName", "symbol"),
            ("instParameters", "list"),
            ("netlistProcedure", "symbol"),
        ):
            status = "missing" if key == "componentName" else "observed"
            value_text = "(D G S B)" if key == "termOrder" else "nil"
            lines.append(f'META|"{scope}"|"{key}"|"{status}"|{kind}|{value_text}')
        lines.append(f'SIM|"{scope}"|nil|(D G S B)')
    return ("\n".join([*lines, "END", "COMPLETE"]) + "\n").encode("ascii")


class _Provider:
    def __init__(self) -> None:
        self.retained: RetainedMosEdit | None = None
        self.publication: NativeMosEditCapture | None = None
        self.dispatches = 0

    def lookup(self, _binding: RegisteredMosEditBinding) -> RetainedMosEdit | None:
        return self.retained

    def claim(self, _binding: RegisteredMosEditBinding) -> bool:
        if self.retained is not None:
            return False
        self.retained = RetainedMosEdit(None)
        return True

    def dispatch(self, _binding: RegisteredMosEditBinding) -> RetainedMosEdit:
        self.dispatches += 1
        self.retained = RetainedMosEdit(self.publication)
        return self.retained


def _service(
    master: Literal["nmos1v", "pmos1v"] = "pmos1v",
    primary: Literal["w", "l", "m"] = "w",
    joint: bool = False,
) -> tuple[RegisteredMosEditService, _Provider, NativeMosEditCapture]:
    route, child, old, new, request = _fixture(master, primary, joint)
    plan = plan_registered_mos_edit(route, child, request)
    binding = RegisteredMosEditBinding(
        operation_id="11111111-1111-4111-8111-111111111111",
        owned_copy_operation_id="22222222-2222-4222-8222-222222222222",
        scope_sha256="7" * 64,
        plan_sha256=plan.plan_sha256,
        route_sha256=canonical_digest(route),
        owned_library="PrivateMos",
        owned_cell="Inv",
        owned_before_view_tree_sha256="8" * 64,
        owned_before_testbench_tree_sha256="9" * 64,
        source_preservation_sha256="a" * 64,
    )
    provider = _Provider()
    engine = RegisteredMosEditService(
        binding,
        route,
        child,
        request,
        old,
        provider,
        expected_binding_sha256=canonical_digest(binding),
    )
    start = MosEditSnapshot(
        stage="baseline",
        revision_sha256=binding.owned_before_view_tree_sha256,
        testbench_revision_sha256=binding.owned_before_testbench_tree_sha256,
        footprint_sha256="b" * 64,
        receipt_sha256="c" * 64,
        properties=route.before,
    )
    saved = start.model_copy(
        update={
            "stage": "saved",
            "revision_sha256": "d" * 64,
            "receipt_sha256": "e" * 64,
            "properties": route.after,
        }
    )
    reopen = saved.model_copy(update={"stage": "reopened", "receipt_sha256": "f" * 64})
    frame = _cdf_frame(master, route.after)
    capture = NativeMosEditCapture(
        NativeMosEditReadback(
            operation_id=binding.operation_id,
            plan_sha256=binding.plan_sha256,
            scope_sha256=binding.scope_sha256,
            baseline=start,
            saved=saved,
            reopened=reopen,
            netlisted_revision_sha256=saved.revision_sha256,
            netlisted_testbench_revision_sha256=saved.testbench_revision_sha256,
            netlist_receipt_sha256="0" * 64,
            netlist_sha256=_sha(new),
            cdf_frame_sha256=_sha(frame),
            source_preservation_sha256=binding.source_preservation_sha256,
        ),
        new,
        frame,
    )
    return engine, provider, capture


@pytest.mark.parametrize(
    ("master", "primary", "joint"),
    [
        ("pmos1v", "w", False),
        ("nmos1v", "l", False),
        ("nmos1v", "w", True),
        ("pmos1v", "m", False),
    ],
)
def test_registered_mos_three_phases_and_same_id_lookup(master, primary, joint) -> None:
    service, provider, capture = _service(master, primary, joint)
    provider.publication = capture
    assert service.lookup(service.identity).outcome == "NOT_FOUND"
    result = service.apply(service.identity)
    assert result.outcome == "VERIFIED" and result.dispatched_this_call is True
    assert result.effective_input is not None
    assert result.effective_input.value.normalized == service.plan.requested.normalized
    saved = service.lookup(service.identity)
    assert service.apply(service.identity) == saved
    assert saved.outcome == "VERIFIED" and saved.replayed and not saved.dispatched_this_call
    assert not saved.analysis_execution_authorized and provider.dispatches == 1


def test_equivalent_lengths_and_constraint_conflicts() -> None:
    route, child, _, _, request = _fixture()
    expected = plan_registered_mos_edit(route, child, request)
    equivalent = MosEditValues(
        fw=ChangeValue(value="0.12", unit="um"),
        l=ChangeValue(value="100", unit="nm"),
        m=ChangeValue(value="1", unit="count"),
        fingers=ChangeValue(value="1", unit="count"),
    )
    assert plan_registered_mos_edit(route, child, equivalent) == expected
    for field, value in (
        ("w", ChangeValue(value="200", unit="nm")),
        ("m", ChangeValue(value="2", unit="count")),
        ("fingers", ChangeValue(value="2", unit="count")),
        ("l", ChangeValue(value="101", unit="nm")),
    ):
        with pytest.raises(ValueError):
            plan_registered_mos_edit(route, child, equivalent.model_copy(update={field: value}))


def test_invalid_native_footprint_or_retained_unknown_never_dispatches_twice() -> None:
    service, provider, capture = _service()
    value = capture.readback
    provider.publication = NativeMosEditCapture(
        value.model_copy(
            update={"reopened": value.reopened.model_copy(update={"footprint_sha256": "4" * 64})}
        ),
        capture.netlist,
        capture.cdf_frame,
    )
    assert service.apply(service.identity).outcome == "OUTCOME_UNKNOWN"
    provider.retained = RetainedMosEdit(None)
    assert service.apply(service.identity).outcome == "OUTCOME_UNKNOWN"
    assert provider.dispatches == 1


def test_joint_route_requires_both_values_and_rejects_conflicting_raw_cdf() -> None:
    route, child, _, _, request = _fixture("nmos1v", joint=True)
    with pytest.raises(ValueError, match="explicitly requested"):
        plan_registered_mos_edit(route, child, MosEditValues(w=request.w))
    service, provider, capture = _service("nmos1v", joint=True)
    other = capture.cdf_frame.replace(b'"M0"', b'"M9"', 1)
    provider.publication = NativeMosEditCapture(
        capture.readback.model_copy(update={"cdf_frame_sha256": _sha(other)}),
        capture.netlist,
        other,
    )
    assert (
        service.apply(service.identity).outcome
        == service.lookup(service.identity).outcome
        == "OUTCOME_UNKNOWN"
    )


def test_multiplier_preserves_factors_and_rejects_equal_product() -> None:
    service, provider, capture = _service("pmos1v", "m")
    forged = capture.netlist.replace(b"(6)*(1)", b"(1)*(6)")
    provider.publication = NativeMosEditCapture(
        capture.readback.model_copy(update={"netlist_sha256": _sha(forged)}),
        forged,
        capture.cdf_frame,
    )
    assert service.apply(service.identity).outcome == "OUTCOME_UNKNOWN"
    assert mos_multiplicity_factors("(6)*(1)") == ("6", "1")
    for token in ("6", "(2+4)*(1)", "(0)*(6)", "(6)*(1.0)", "(6)*(1)*(1)"):
        with pytest.raises(ValueError):
            mos_multiplicity_factors(token)


@pytest.mark.parametrize("capture_state", ["complete", "lost-terminal", "tampered-save"])
def test_pinned_host_factory_calls_two_phases_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capture_state: str
) -> None:
    settings = make_settings(tmp_path)
    context, _ = load_runtime(settings)
    evidence = tmp_path / "mos-evidence"
    evidence.mkdir()
    guest, support, collector = b"pass\n", b"reviewed support\n", b"reviewed collector\n"
    monkeypatch.setattr(host, "_fixed_assets", lambda _: (guest, support, collector))
    monkeypatch.setattr(host, "_ssh", lambda _: ["fixed-ssh", "python"])
    safety, cdf, update = b'{"fixture":true}', b"observed cdf", b"reviewed route"
    route, child, baseline, _, request = _fixture()
    route = route.model_copy(
        update={
            "update_route_sha256": _sha(update),
            "qualification": route.qualification.model_copy(update={"evidence_sha256": _sha(cdf)}),
        }
    )
    plan = plan_registered_mos_edit(route, child, request)
    _, _, capture = _service()
    observed = capture.readback
    scope_raw = _canonical(
        {
            "schema_version": 1,
            "route": "registered_mos_edit",
            "context_id": context.binding.context_id,
            "resource_domain_sha256": context.resource_domain_sha256,
            "environment_sha256": context.binding.environment_sha256,
            "native_manifest_sha256": context.binding.runner_sha256,
            "subject": {
                "operation_id": observed.operation_id,
                "owned_copy_operation_id": "22222222-2222-4222-8222-222222222222",
                "owned_library": "PrivateMos",
                "owned_cell": "Inv",
                "owned_view": "schematic",
                "owned_before_view_tree_sha256": observed.baseline.revision_sha256,
                "owned_before_testbench_tree_sha256": observed.baseline.testbench_revision_sha256,
                "source_preservation_sha256": observed.source_preservation_sha256,
                "plan_sha256": plan.plan_sha256,
                "route_sha256": canonical_digest(route),
            },
            "route_qualification": route.model_dump(mode="json"),
            "plan": plan.model_dump(mode="json"),
            "candidate_request": request.model_dump(mode="json"),
            "native_safety_sha256": _sha(safety),
            "guest_sha256": _sha(guest),
            "valid_until_unix": int(time.time()) + 60,
        }
    )
    scope_sha = _sha(scope_raw)
    ack = _canonical(
        {
            "owner": "C0",
            "operation_id": observed.operation_id,
            "scope_sha256": scope_sha,
            "approved_phases": [host._EDIT, host._REOPEN],
            "valid_until_unix": json.loads(scope_raw)["valid_until_unix"],
        }
    )
    for name, raw in (
        ("execution-scope.private.json", scope_raw),
        ("c0-exact-ack.private.json", ack),
        ("native-safety.private.json", safety),
        ("cdf-evidence.private", cdf),
        ("update-route-evidence.private", update),
        ("baseline-input.private.scs", baseline),
    ):
        (evidence / name).write_bytes(raw)
    registration = evidence / "registration.private.json"
    registration.write_bytes(
        _canonical(
            {
                "schema_version": 3,
                "route": "registered_mos_edit",
                "context_id": context.binding.context_id,
                "resource_domain_sha256": context.resource_domain_sha256,
                "evidence_directory": str(evidence),
                "scope_sha256": scope_sha,
                "authority_sha256": _sha(ack),
            }
        )
    )
    runtime = json.loads(settings.read_bytes())
    runtime["contexts"][0].update(
        pmos_default_change_binding=str(registration),
        pmos_default_change_sha256=_sha(registration.read_bytes()),
    )
    settings.write_bytes(_canonical(runtime))
    context, _ = load_runtime(settings)

    observed = observed.model_copy(
        update={"scope_sha256": scope_sha, "plan_sha256": plan.plan_sha256}
    )
    save_record = observed.model_dump(mode="json", include=set(NativeMosEditSave.model_fields))
    if capture_state == "tampered-save":
        save_record["saved"]["testbench_revision_sha256"] = "0" * 64
    saved = _canonical(save_record)
    terminal = _canonical(
        {
            "readback": observed.model_dump(mode="json"),
            "input_base64": base64.b64encode(capture.netlist).decode("ascii"),
            "cdf_frame_base64": base64.b64encode(capture.cdf_frame).decode("ascii"),
        }
    )
    calls: list[str] = []

    def transport(argv, request, _env, **kwargs):
        phase = argv[-1]
        calls.append(phase)
        assert argv[-2] == scope_sha and request.startswith(guest)
        envelope = json.loads(request[len(guest) :])
        assert base64.b64decode(envelope["authority_base64"]) == ack
        assert base64.b64decode(envelope["native_safety_base64"]) == safety
        assert base64.b64decode(envelope["support_base64"]) == support
        assert base64.b64decode(envelope["cdf_collector_base64"]) == collector
        if phase == host._EDIT:
            assert envelope["previous_receipt_sha256"] is None
            return 0, saved, b""
        assert envelope["previous_receipt_sha256"] == _sha(saved)
        return (0, terminal, b"") if capture_state == "complete" else (1, b"", b"unverified")

    monkeypatch.setattr(host, "run_fixed", transport)
    service = host.registered_mos_edit(context)
    assert service.lookup(service.identity).outcome == "NOT_FOUND"
    (evidence / "native-safety.private.json").write_bytes(b"{}")
    with pytest.raises(OperationRejected, match="Operator operation rejected"):
        service.apply(service.identity)
    assert calls == [] and service.lookup(service.identity).outcome == "NOT_FOUND"
    (evidence / "native-safety.private.json").write_bytes(safety)
    expected = "VERIFIED" if capture_state == "complete" else "OUTCOME_UNKNOWN"
    assert service.apply(service.identity).outcome == expected
    restarted = host.registered_mos_edit(context)
    assert restarted.lookup(service.identity).outcome == expected
    assert restarted.apply(service.identity).outcome == expected
    assert calls == (
        [host._EDIT] if capture_state == "tampered-save" else [host._EDIT, host._REOPEN]
    )


def _guest_tuple(before: bool) -> dict[str, dict[str, str | None]]:
    result = {
        key: {
            field: None for field in ("oa_type", "oa_value", "cdf_type", "cdf_units", "cdf_value")
        }
        for key in guest_source.PROPERTIES
    }
    rows = (
        ("w", "lengthMetric", "350n", "120n"),
        ("fw", "lengthMetric", "350n", "120n"),
        ("l", "lengthMetric", "100n", "100n"),
        ("m", None, "1", "1"),
        ("fingers", None, "1", "1"),
        ("as", None, "98f", "69.6f"),
        ("ad", None, "98f", "69.6f"),
        ("ps", "lengthMetric", "1.26u", "1.16u"),
        ("pd", "lengthMetric", "1.26u", "1.16u"),
        ("model", None, "gpdk090_pmos1v", "gpdk090_pmos1v"),
    )
    for key, units, old, new in rows:
        value = old if before else new
        explicit = before or old == new
        result[key] = dict(
            oa_type="string" if explicit else None,
            oa_value=value if explicit else None,
            cdf_type="instData",
            cdf_units=units,
            cdf_value=value,
        )
    return result


def test_shipped_source9_guest_has_closed_route_and_phase_templates() -> None:
    scope = {
        "subject": {
            "owned_cell": "InvLong",
            "owned_view": "schematic",
            "owned_library": "CmosLongMosTest1",
        },
        "route_qualification": {
            "before": _guest_tuple(True),
            "after": _guest_tuple(False),
            "qualification": {
                "old": {"unit": "nm", "value": "350"},
                "expected": {"unit": "nm", "value": "120"},
                "target": {
                    "instance": {
                        "instance_path": "DUT/MP",
                        "master_library": "gpdk090",
                        "master_cell": "pmos1v",
                        "master_view": "symbol",
                        "property_name": "w",
                    },
                    "quantity": "length",
                    "scalar_option": "w",
                    "scalar_unit": "nm",
                    "netlist_path": "DUT/MP",
                    "netlist_model": "gpdk090_pmos1v",
                    "netlist_terminals": ["vout", "vin", "vdd", "vdd"],
                },
                "baseline": {
                    "netlist_sha256": "5" * 64,
                    "revision": {"design_id": "cmos-long-inverter", "revision_id": "long-r1"},
                },
            },
        },
    }
    route = scope["route_qualification"]
    q = route["qualification"]
    scope["plan"] = {
        "old": q["old"],
        "requested": q["expected"],
        "expected": q["expected"],
        "target": q["target"],
        "baseline": q["baseline"],
    }
    assert guest_source.exact_route(scope) == route
    for template in (guest_source.EDIT, guest_source.REOPEN):
        script = guest_source.COMMON + template
        values = dict.fromkeys(set(re.findall(r"@[A-Z]+@", script)), "fixed")
        values["@BEFORE@"] = guest_source.skill_check(route["before"])
        values["@AFTER@"] = guest_source.skill_check(route["after"])
        values["@OVERRIDES@"], values["@MUTATION@"] = guest_source.skill_mutation(route, "pmos1v")
        rendered = guest_source.render(script, values).decode("ascii")
        depth = 0
        syntax = re.sub(r'"(?:[^"\\]|\\.)*"', '""', rendered)
        for ch in syntax:
            depth += (ch == "(") - (ch == ")")
            assert depth >= 0
        assert depth == 0 and "evalstring" not in rendered and "dbReplaceProp" not in rendered
    assert "dbDeletePropByName" in guest_source.RESTORE and "dbSave" in guest_source.EDIT
    assert "dbSave" not in guest_source.REOPEN and "m2ReopenedMosFrame" in guest_source.REOPEN
    route["after"]["m"]["cdf_value"] = "6"
    with pytest.raises(ValueError, match="registered_cdf_tuple"):
        guest_source.exact_route(scope)

    route["after"] = deepcopy(route["before"])
    route["before"]["l"].update(oa_value="150n", cdf_value="150n")
    route["after"]["l"].update(oa_type=None, oa_value=None)
    q["baseline"]["revision"]["revision_id"] = "registered-length-reference"
    q["target"]["instance"]["property_name"] = q["target"]["scalar_option"] = "l"
    scope["plan"]["old"] = q["old"] = {"value": "0.15", "unit": "um"}
    scope["plan"]["requested"] = scope["plan"]["expected"] = q["expected"] = {
        "value": "100",
        "unit": "nm",
    }
    assert guest_source.exact_route(scope) == route
    assert guest_source.skill_restore(route) == ('\'("l")', '\'(("l" "150n" "100n"))')
    route["after"]["l"].update(oa_type="string", oa_value="100n")
    with pytest.raises(ValueError, match="observed_override_to_default"):
        guest_source.exact_route(scope)


def test_native_property_rows_are_observed_and_complete() -> None:
    rows = _guest_tuple(False)
    raw = (
        "\n".join(
            "|".join(
                [key, *("nil" if value is None else json.dumps(value) for value in row.values())]
            )
            for key, row in rows.items()
        )
        + "\nCOMPLETE\n"
    ).encode("ascii")
    assert guest_source.read_properties(raw) == rows
    with pytest.raises(ValueError, match="property_name"):
        guest_source.read_properties(raw.replace(b"fw|", b"w|"))


@pytest.mark.parametrize(
    ("master", "count_storage"), [("nmos1v", None), ("pmos1v", "int"), ("pmos1v", "string")]
)
def test_explicit_nondefault_joint_route_checks_witness_and_renders_setter(
    master, count_storage
) -> None:
    base, child, _, _, _ = _fixture(master)
    model = f"gpdk090_{master}"
    slot, rail = guest_source.SLOTS[master]
    path = f"DUT/{slot}"
    before = {key: MosPropertyValue.model_validate(row) for key, row in _guest_tuple(True).items()}
    before["model"] = before["model"].model_copy(update={"oa_value": model, "cdf_value": model})
    after = before.copy()
    replacements = {"w": "16u", "fw": "16u", "l": "1u", "as": "4p"}
    if count_storage:
        replacements["m"] = "6"
    for name, value in replacements.items():
        storage = count_storage if name == "m" else "string"
        after[name] = after[name].model_copy(
            update={"oa_type": storage, "oa_value": value, "cdf_value": value}
        )

    def netlist(properties):
        values = {name: row.cdf_value for name, row in properties.items()}
        factor = f"({values['m']})*({values['fingers']})"
        return (
            "simulator lang=spectre\nparameters VDD=1\n"
            "subckt InvLong vdd vin vout vss\n"
            f"{slot} (vout vin {rail} {rail}) {model} w=({values['w']}) l={values['l']} "
            f"as={values['as']} ad={values['ad']} ps={values['ps']} pd={values['pd']} "
            f"m={factor} simM={factor}\n"
            "ends InvLong\nDUT (vdd vin vout 0) InvLong\n"
        ).encode("ascii")

    old, new = netlist(before), netlist(after)
    parent = base.qualification.baseline.revision.model_copy(
        update={"design_id": "cmos-long-inverter"}
    )
    child = child.model_copy(update={"design_id": parent.design_id})
    options = [
        MosOptionTransition(name="w", before="(350n)", after="(16u)"),
        MosOptionTransition(name="l", before="100n", after="1u"),
        MosOptionTransition(name="as", before="98f", after="4p"),
    ]
    if count_storage:
        options += [
            MosOptionTransition(name="m", before="(1)*(1)", after="(6)*(1)"),
            MosOptionTransition(name="simM", before="(1)*(1)", after="(6)*(1)"),
        ]
    target = base.qualification.target.model_copy(
        update={
            "instance": base.qualification.target.instance.model_copy(
                update={"instance_path": path}
            ),
            "netlist_path": path,
            "netlist_terminals": ("vout", "vin", rail, rail),
            "options": tuple(options),
            "scalar_unit": "um",
            "baseline_scalar_unit": "nm",
        }
    )
    qualification = base.qualification.model_copy(
        update={
            "baseline": base.qualification.baseline.model_copy(
                update={"revision": parent, "netlist_sha256": _sha(old)}
            ),
            "target": target,
            "expected": ChangeValue(value="16", unit="um"),
            "derived": (
                DerivedChange(
                    before=DerivedValue(property_name="fw", value="350n"),
                    after=DerivedValue(property_name="fw", value="16u"),
                ),
                DerivedChange(
                    before=DerivedValue(property_name="as", value="98f"),
                    after=DerivedValue(property_name="as", value="4p"),
                ),
            ),
        }
    )
    fields = {
        name: MosCdfWriteField(
            param_type="string", minimum="100n", maximum="20u", callback_present=True
        )
        for name in ("w", "fw", "l")
    }
    if count_storage:
        fields["m"] = MosCdfWriteField(
            param_type=count_storage, minimum="1", maximum=None, callback_present=False
        )
    frame = _cdf_frame(master, after, slot)
    cal_slot = "CalPmos6" if count_storage else "CalNmos"
    cal_frame = _cdf_frame(master, after, cal_slot)
    cal_input = new.replace(f"{slot} (".encode("ascii"), f"{cal_slot} (".encode("ascii"))
    lines = ["M2_CDF_CONSTRAINTS_V1"]
    for name, spec in fields.items():
        lines.append(f'LIMIT|"{master}"|"{name}"|"paramType"|"observed"|string|"{spec.param_type}"')
        for field, value in (("minVal", spec.minimum), ("maxVal", spec.maximum)):
            item = f'"observed"|string|"{value}"' if value is not None else '"missing"|nil|nil'
            lines.append(f'LIMIT|"{master}"|"{name}"|"{field}"|{item}')
        item = '"observed"|string|nil' if spec.callback_present else '"missing"|nil|nil'
        lines.append(f'LIMIT|"{master}"|"{name}"|"callback"|{item}')
    constraints = ("\n".join([*lines, "COMPLETE"]) + "\n").encode("ascii")
    witness = MosSetWitness(
        operation_id="55555555-5555-4555-8555-555555555555",
        method="cadence_edit_object_properties",
        instance=target.instance.model_copy(update={"instance_path": f"DUT/{cal_slot}"}),
        netlist_path=f"DUT/{cal_slot}",
        netlist_terminals=target.netlist_terminals,
        before_footprint_sha256="c" * 64,
        reopened=MosEditSnapshot(
            stage="reopened",
            revision_sha256="a" * 64,
            testbench_revision_sha256="b" * 64,
            footprint_sha256="c" * 64,
            receipt_sha256="d" * 64,
            properties=after,
        ),
        netlisted_revision_sha256="a" * 64,
        netlisted_testbench_revision_sha256="b" * 64,
        cdf_frame_sha256=_sha(cal_frame),
        netlist_sha256=_sha(cal_input),
    )
    witness_raw = _canonical(witness.model_dump(mode="json"))
    proof = MosExplicitSet(
        fields=fields,
        constraints_sha256=_sha(constraints),
        witness_operation_id=witness.operation_id,
        witness_readback_sha256=_sha(witness_raw),
        witness_cdf_sha256=_sha(cal_frame),
        witness_input_sha256=_sha(cal_input),
    )
    route = RegisteredMosEditRoute(
        qualification=qualification,
        before=before,
        after=after,
        update_route_sha256="9" * 64,
        explicit_set=proof,
    )
    requested = MosEditValues(
        w=ChangeValue(value="16000", unit="nm"),
        l=ChangeValue(value="1", unit="um"),
        m=ChangeValue(value="6", unit="count") if count_storage else None,
    )
    plan = plan_registered_mos_edit(route, child, requested)
    verify_explicit_set_evidence(route, constraints, witness_raw, cal_frame, cal_input)
    binding = RegisteredMosEditBinding(
        operation_id="11111111-1111-4111-8111-111111111111",
        owned_copy_operation_id="22222222-2222-4222-8222-222222222222",
        scope_sha256="1" * 64,
        plan_sha256=plan.plan_sha256,
        route_sha256=canonical_digest(route),
        owned_library="CmosLongMosTest1",
        owned_cell="InvLong",
        owned_before_view_tree_sha256="2a" * 32,
        owned_before_testbench_tree_sha256="2b" * 32,
        source_preservation_sha256="2c" * 32,
    )
    provider = _Provider()
    service = RegisteredMosEditService(
        binding,
        route,
        child,
        requested,
        old,
        provider,
        expected_binding_sha256=canonical_digest(binding),
    )
    start = witness.reopened.model_copy(
        update={
            "stage": "baseline",
            "revision_sha256": binding.owned_before_view_tree_sha256,
            "testbench_revision_sha256": binding.owned_before_testbench_tree_sha256,
            "properties": before,
        }
    )
    saved = start.model_copy(
        update={
            "stage": "saved",
            "revision_sha256": "2d" * 32,
            "receipt_sha256": "2e" * 32,
            "properties": after,
        }
    )
    reopened = saved.model_copy(update={"stage": "reopened", "receipt_sha256": "2f" * 32})
    provider.publication = NativeMosEditCapture(
        NativeMosEditReadback(
            operation_id=binding.operation_id,
            plan_sha256=binding.plan_sha256,
            scope_sha256=binding.scope_sha256,
            baseline=start,
            saved=saved,
            reopened=reopened,
            source_preservation_sha256=binding.source_preservation_sha256,
            netlisted_revision_sha256=reopened.revision_sha256,
            netlisted_testbench_revision_sha256=reopened.testbench_revision_sha256,
            netlist_receipt_sha256="3a" * 32,
            netlist_sha256=_sha(new),
            cdf_frame_sha256=_sha(frame),
        ),
        new,
        frame,
    )
    result = service.apply(service.identity)
    assert result.outcome == "VERIFIED" and result.effective_mos_options is not None
    assert result.effective_mos_options["m"] == ("(6)*(1)" if count_storage else "(1)*(1)")
    assert service.lookup(service.identity).replayed and provider.dispatches == 1
    scope = {
        "plan": plan.model_dump(mode="json"),
        "route_qualification": route.model_dump(mode="json"),
        "subject": {
            "owned_library": "CmosLongMosTest1",
            "owned_cell": "InvLong",
            "owned_view": "schematic",
        },
    }
    guest_source.exact_route(scope)
    omit, mutation = guest_source.skill_mutation(scope["route_qualification"], master)
    job = guest_source.Source9MosJob.__new__(guest_source.Source9MosJob)
    job.route, job.library, job.source, job.source_alias = (
        scope["route_qualification"],
        "CmosLongMosTest1",
        "/root/source",
        "CmosLong20261111",
    )
    job.owned, job.operation = "/root/copy", "11111111-1111-4111-8111-111111111111"
    values = job.values("/root/work")
    assert values["@TARGET@"] == slot and values["@RAIL@"] == rail
    edit = guest_source.render(guest_source.COMMON + guest_source.EDIT, values).decode("ascii")
    assert (
        edit.index("param~>callback")
        < edit.index("dbReplaceProp(inst")
        < edit.index("dbSave(child)")
    )
    assert "dbDeletePropByName" not in mutation and "evalstring" not in edit
    assert "@MUTATION@" not in edit and ("m" in omit) == bool(count_storage)
    if count_storage:
        assert ('("m" "int" 6)' if count_storage == "int" else '("m" "string" "6")') in mutation
        with pytest.raises(ValueError, match="explicitly requested"):
            plan_registered_mos_edit(route, child, requested.model_copy(update={"m": None}))
    with pytest.raises(ValueError, match="digest changed"):
        verify_explicit_set_evidence(
            route, constraints, witness_raw, cal_frame, cal_input.replace(b"(16u)", b"(17u)")
        )
    forged = witness.model_copy(update={"netlisted_testbench_revision_sha256": "e" * 64})
    forged_raw = _canonical(forged.model_dump(mode="json"))
    forged_proof = proof.model_copy(update={"witness_readback_sha256": _sha(forged_raw)})
    with pytest.raises(ValueError, match="witness does not match"):
        verify_explicit_set_evidence(
            route.model_copy(update={"explicit_set": forged_proof}),
            constraints,
            forged_raw,
            cal_frame,
            cal_input,
        )
    bad_constraints = constraints.replace(
        b'"callback"|"observed"|string|nil', b'"callback"|"read_error"|nil|nil', 1
    )
    bad_proof = proof.model_copy(update={"constraints_sha256": _sha(bad_constraints)})
    with pytest.raises(ValueError, match="unobserved CDF constraint"):
        verify_explicit_set_evidence(
            route.model_copy(update={"explicit_set": bad_proof}),
            bad_constraints,
            witness_raw,
            cal_frame,
            cal_input,
        )
