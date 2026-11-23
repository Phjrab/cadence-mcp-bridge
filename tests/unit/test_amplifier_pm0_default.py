"""Exercise the finite PM0 route without a native process or a writable journal."""

import base64
import json
import shlex
import time
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest
from test_runtime_context import make_settings

from cadence_mcp_bridge import amplifier_pm0_default as amp
from cadence_mcp_bridge import amplifier_pm0_service as amp_host
from cadence_mcp_bridge import parameter_changes as changes
from cadence_mcp_bridge.candidate_cli import dispatch_pmos_default_change
from cadence_mcp_bridge.candidate_execution import PmosDefaultChangeRequest
from cadence_mcp_bridge.operator_operations import OperationRejected
from cadence_mcp_bridge.pmos_default_service import registered_pmos_default_change
from cadence_mcp_bridge.runtime_context import load_runtime
from cadence_mcp_bridge.schematic_plan import RevisionBinding
from cadence_mcp_bridge.variable_contracts import canonical_digest

_WRITER = "11111111-1111-4111-8111-111111111111"
_OBSERVER = "22222222-2222-4222-8222-222222222222"
_VIEW = "a" * 64
_FAILURE = "b" * 64


def _sha(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def _json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii")


def _encode(*values: str) -> str:
    return f"L{len(values)}:" + "".join(f"{len(value)}:{value}" for value in values)


def _view_rows(geometry: str) -> str:
    return _encode(
        _encode("SconnectivityLastUpdated", "Sint", "I35"),
        _encode("Sinstance#", "Sint", "I11"),
        _encode("SlastSchematicExtraction", "Stime", "SNov 22 10:14:43 2026"),
        _encode("Snet#", "Sint", "I39"),
        _encode("Spin#", "Sint", "I36"),
        _encode("SschGeometryLastUpdated", "Sint", geometry),
        _encode("SschGeometryVersion", "Sstring", "Ssch.ds.gm.1.4"),
        _encode("SschXtrVersion", "Sstring", "Ssch.10.0"),
    )


@pytest.fixture
def operation(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[amp.RetainedAmplifierPm0DefaultChange, PmosDefaultChangeRequest]:
    pm0 = (
        b"PM0 (net33 Vbiasp VDD VDD) gpdk090_pmos1v w=(20u) l=1u "
        b"as=5.6p ad=5.6p ps=40.56u pd=40.56u m=(1)*(1) simM=(1)*(1)"
    )
    raw = b"simulator lang=spectre\nparameters VBIASN=0.320 VBIASP=0.702\n" + pm0 + b"\n"
    candidate = raw.replace(b"20u", b"120n").replace(b"5.6p", b"69.6f").replace(b"40.56u", b"1.16u")
    monkeypatch.setattr(amp, "_CENTER", _sha(raw))
    monkeypatch.setattr(changes, "_AMP_CENTER_SHA256", _sha(raw))
    monkeypatch.setattr(changes, "_AMP_PM0_STATEMENT_SHA256", _sha(pm0))
    parent = RevisionBinding(
        workspace_id="test-amp",
        design_id="reference-differential-amplifier-tb2",
        revision_id="reference-amplifier-bias-grid-v1",
        source_baseline_sha256=amp._CENTER_VIEW,
    )
    child = parent.model_copy(
        update={
            "revision_id": "test-candidate",
            "parent_revision_id": parent.revision_id,
            "parent_revision_sha256": amp._CENTER_VIEW,
        }
    )
    qualification = changes.MosWidthQualification(
        baseline=changes.ChangeBaseline(
            revision=parent,
            revision_sha256=amp._CENTER_VIEW,
            testbench_revision_sha256=amp._CENTER_VIEW,
            netlist_sha256=_sha(raw),
            fixed_conditions_sha256="1" * 64,
        ),
        target=changes.MosWidthTarget(
            instance=changes.CandidateSourceTarget(
                instance_path="PM0",
                master_library="gpdk090",
                master_cell="pmos1v",
                master_view="symbol",
                property_name="w",
            )
        ),
        old=changes.ChangeValue(value="20", unit="um"),
        expected=changes.ChangeValue(value="120", unit="nm"),
        fingers=1,
        multiplicity=1,
        cdf_evidence_sha256="2" * 64,
        legal_value_evidence_sha256="3" * 64,
        update_route_evidence_sha256="4" * 64,
        derived=tuple(
            changes.DerivedChange(
                before=changes.DerivedValue(property_name=k, value=old),
                after=changes.DerivedValue(property_name=k, value=new),
            )
            for k, (old, new) in amp._GEOMETRY.items()
        ),
    )
    plan = amp.plan_amplifier_pm0_default_change(
        qualification, child.revision_id, child, changes.ChangeValue(value="0.12", unit="um")
    )
    base_frame, _ = amp._pm0_frame(baseline=True)
    base_receipt = _json(
        {
            "status": "CLOSED_BASELINE_MATCHED",
            "scope_sha256": "5" * 64,
            "frame": base_frame,
        }
    )
    scope = _json(
        {
            "operation_id": _WRITER,
            "completed_baseline_receipt": _sha(base_receipt),
            "completed_baseline_scope": "5" * 64,
        }
    )
    intent = _json({"phase": "edit", "scope_sha256": _sha(scope), "prior": [_sha(base_receipt)]})
    request = PmosDefaultChangeRequest(
        operation_id=_WRITER,
        expected_plan_sha256=plan.plan_sha256,
        expected_scope_sha256=_sha(scope),
    )
    before, after = _view_rows("I12"), _view_rows("I35")
    presave = (_encode("L3:mock-design", before, "L158:mock-figures") + "\n").encode("ascii")
    reopened = (_encode("L3:mock-design", after, "L158:mock-figures") + "\n").encode("ascii")
    frame, values = amp._pm0_frame(baseline=False)
    diagnostics = []
    for key, value in values.items():
        oa = "t|string|1u" if key == "l" else "nil|-|-"
        cdf = "nil|nil" if key == "nf" else "t|string"
        diagnostics.append(f"AUTO120_DIAG_PROP|AFTER_REMOVE|{key}|{value}|{oa}|{cdf}|{value}")
    diagnostics.extend(
        [
            f"C1_ROWS|EDIT_AFTER|{before}",
            "C1_CHECK|EDIT|(0 0)|before|after|22|35|nil|t",
            f"C1_ROWS|SAVED|{after}",
            "AUTO120_FAIL|SAVE",
        ]
    )
    capture = _json(
        {
            "scope": _sha(scope),
            "stages": [
                {
                    "phase": "edit",
                    "failure_sha256": _FAILURE,
                    "detail": {
                        "phase": "edit",
                        "scope_sha256": _sha(scope),
                        "status": "OUTCOME_UNKNOWN",
                        "conservation": "MATCHED",
                        "ocean_launched": 1,
                        "program_issued": True,
                        "program_failure": {"cleanup": "REAPED"},
                        "logs": {"ocean.stdout": {"diagnostic": diagnostics}},
                    },
                }
            ],
        }
    )
    scope_observer = "6" * 64
    physical = {"view_tree": _VIEW}
    receipt = _json(
        {
            "operation_id": _OBSERVER,
            "scope_sha256": scope_observer,
            "failed_operation": _WRITER,
            "failure": _FAILURE,
            "status": "RECONCILED_READ_ONLY",
            "phase": "child-netlist",
            "before": physical,
            "after": physical,
            "input_sha256": _sha(candidate),
            "frozen_sha256": _sha(reopened),
            "readback_sha256": "7" * 64,
            "gate_markers": [
                f"AUTO120_DONE|{_OBSERVER}|reopen",
                "C1_VERIFIED_INDEPENDENT_REOPEN",
                f"C1_AMP_ADE_COMPLETE|child-netlist|{_OBSERVER}",
            ],
            "simulations": 0,
            "reservations": 0,
            "netlists": 1,
            "ocean_calls": 1,
            "counter": {"count": 140},
            "reopen_frame": frame,
        }
    )
    replay = _json(
        {
            "status": "RECONCILIATION_REPLAY",
            "operation_id": _OBSERVER,
            "scope": scope_observer,
            "receipt_sha256": _sha(receipt),
            "after": physical,
            "counter": {"count": 140},
            "writes": 0,
            "ocean_calls": 0,
            "simulations": 0,
            "reservations": 0,
        }
    )
    pins = amp.AmplifierPm0JournalPins(
        plan_sha256=plan.plan_sha256,
        writer_operation_id=_WRITER,
        writer_scope_sha256=_sha(scope),
        writer_intent_sha256=_sha(intent),
        baseline_receipt_sha256=_sha(base_receipt),
        writer_capture_sha256=_sha(capture),
        reconciliation=amp.AmplifierPm0ReconciliationPins(
            observation_operation_id=_OBSERVER,
            observation_scope_sha256=scope_observer,
            candidate_view_tree_sha256=_VIEW,
            source_writer_failure_sha256=_FAILURE,
            observer_receipt_sha256=_sha(receipt),
            observer_replay_sha256=_sha(replay),
            presave_sha256=_sha(presave),
            reopened_sha256=_sha(reopened),
            netlist_sha256=_sha(candidate),
        ),
    )
    journal = amp.AmplifierPm0Journal(
        scope,
        intent,
        base_receipt,
        capture,
        amp.AmplifierPm0Reconciliation(receipt, replay, presave, reopened, candidate),
    )
    return amp.RetainedAmplifierPm0DefaultChange(plan, journal, pins, raw), request


def test_verified_saved_revision_does_not_promote_or_redispatch_writer(
    operation: tuple[amp.RetainedAmplifierPm0DefaultChange, PmosDefaultChangeRequest],
) -> None:
    service, request = operation
    result = service.observe(request)
    assert result == service.observe(request)
    assert result.writer == service.apply(request)
    assert result.writer.outcome == "OUTCOME_UNKNOWN"
    assert result.writer.replayed and not result.writer.dispatched_this_call
    assert result.saved_revision is not None
    assert result.saved_revision.schematic_revision_sha256 == _VIEW
    assert result.saved_revision.testbench_revision_sha256 == _VIEW
    assert result.saved_revision.oa_width == result.saved_revision.netlist.value
    assert result.saved_revision.saved_geometry_counter_after == 35
    assert not result.execution_authorized


def test_partial_intent_reports_unknown_and_conflicting_request_rejects(
    operation: tuple[amp.RetainedAmplifierPm0DefaultChange, PmosDefaultChangeRequest],
) -> None:
    service, request = operation
    journal = replace(service.journal, writer_capture=None, reconciliation=None)
    pins = service.pins.model_copy(update={"writer_capture_sha256": None, "reconciliation": None})
    partial = replace(service, journal=journal, pins=pins)
    assert partial.observe(request).saved_revision is None
    assert partial.apply(request).outcome == "OUTCOME_UNKNOWN"
    with pytest.raises(ValueError, match="conflict"):
        partial.apply(request.model_copy(update={"expected_plan_sha256": "9" * 64}))
    with pytest.raises(ValueError, match="digest"):
        replace(partial, journal=replace(journal, intent=b"")).apply(request)


@pytest.mark.parametrize(
    ("field", "original", "changed", "reason"),
    [
        ("reopened", b"mock-design", b"fake-design", "circuit"),
        ("replay", b'"writes":0', b'"writes":1', "replay"),
        ("netlist", b"VBIASN=0.320", b"VBIASN=0.321", "fixed netlist"),
    ],
)
def test_semantically_wrong_repinned_evidence_rejects(
    operation: tuple[amp.RetainedAmplifierPm0DefaultChange, PmosDefaultChangeRequest],
    field: str,
    original: bytes,
    changed: bytes,
    reason: str,
) -> None:
    service, request = operation
    evidence, pins = service.journal.reconciliation, service.pins.reconciliation
    assert evidence is not None and pins is not None
    initial: bytes = getattr(evidence, field)
    assert original in initial
    modified = initial.replace(original, changed)
    receipt = json.loads(evidence.receipt)
    replay = json.loads(evidence.replay)
    update: dict[str, str] = {}
    if field in ("reopened", "netlist"):
        receipt["frozen_sha256" if field == "reopened" else "input_sha256"] = _sha(modified)
        update["reopened_sha256" if field == "reopened" else "netlist_sha256"] = _sha(modified)
    else:
        replay = json.loads(modified)
    new_receipt = _json(receipt)
    replay["receipt_sha256"] = _sha(new_receipt)
    new_replay = _json(replay)
    update |= {
        "observer_receipt_sha256": _sha(new_receipt),
        "observer_replay_sha256": _sha(new_replay),
    }
    evidence = replace(
        evidence, **({field: modified} | {"receipt": new_receipt, "replay": new_replay})
    )
    updated_pins = service.pins.model_copy(
        update={"reconciliation": pins.model_copy(update=update)}
    )
    with pytest.raises(ValueError, match=reason):
        replace(
            service, journal=replace(service.journal, reconciliation=evidence), pins=updated_pins
        ).observe(request)


@pytest.mark.parametrize(
    ("old", "new"),
    [("22|35|nil|t", "22|36|nil|t"), ("22|35|nil|t", "22|35|nil|nil")],
)
def test_save_counter_requires_the_live_checker_witness(
    operation: tuple[amp.RetainedAmplifierPm0DefaultChange, PmosDefaultChangeRequest],
    old: str,
    new: str,
) -> None:
    service, request = operation
    capture = service.journal.writer_capture
    assert capture is not None and old.encode("ascii") in capture
    modified = capture.replace(old.encode("ascii"), new.encode("ascii"))
    with pytest.raises(ValueError, match="geometry counter"):
        replace(
            service,
            journal=replace(service.journal, writer_capture=modified),
            pins=service.pins.model_copy(update={"writer_capture_sha256": _sha(modified)}),
        ).observe(request)


class _NativeProvider:
    def __init__(self, retained: amp.PmosDefaultChangeResult, *, timeout: bool) -> None:
        self.retained = retained
        self.timeout = timeout
        self.claimed = False
        self.claims = 0
        self.launches = 0

    def lookup(
        self, binding: amp.AmplifierPm0DispatchBinding
    ) -> amp.PmosDefaultChangeResult | None:
        return self.retained if self.claimed else None

    def claim(self, binding: amp.AmplifierPm0DispatchBinding) -> bool:
        self.claims += 1
        if self.claimed:
            return False
        self.claimed = True
        return True

    def dispatch(self, binding: amp.AmplifierPm0DispatchBinding) -> amp.PmosDefaultChangeResult:
        assert self.claimed
        self.launches += 1
        if self.timeout:
            raise TimeoutError
        result = self.retained.model_copy(
            update={
                "outcome": "VERIFIED",
                "replayed": False,
                "dispatched_this_call": True,
                "observed_revision_sha256": _VIEW,
                "observed_testbench_revision_sha256": _VIEW,
                "source_preservation_sha256": "8" * 64,
                "reopen_receipt_sha256": "9" * 64,
                "netlist_receipt_sha256": "a" * 64,
                "netlist_sha256": "b" * 64,
                "reason": None,
            }
        )
        self.retained = result.model_copy(update={"replayed": True, "dispatched_this_call": False})
        return result


def _dispatch_registration(
    plan: changes.ChangePlan,
    request: PmosDefaultChangeRequest,
) -> tuple[amp.AmplifierPm0DispatchBinding, changes.MosWidthQualification]:
    assert isinstance(plan.target, changes.MosWidthTarget)
    return (
        amp.AmplifierPm0DispatchBinding(
            operation_id=request.operation_id,
            plan_sha256=plan.plan_sha256,
            scope_sha256=request.expected_scope_sha256,
            owned_library="AmpFresh",
            owned_cell="Differential_Amplifier_TB2",
            owned_view="schematic",
            owned_before_view_tree_sha256="e" * 64,
        ),
        changes.MosWidthQualification(
            baseline=plan.baseline,
            target=plan.target,
            old=plan.old,
            expected=plan.expected,
            fingers=1,
            multiplicity=1,
            cdf_evidence_sha256="2" * 64,
            legal_value_evidence_sha256="3" * 64,
            update_route_evidence_sha256="4" * 64,
            derived=plan.allowed_derived,
        ),
    )


@pytest.mark.parametrize("timeout", [False, True])
def test_normal_apply_adapter_claims_and_dispatches_only_once(
    operation: tuple[amp.RetainedAmplifierPm0DefaultChange, PmosDefaultChangeRequest],
    tmp_path: Path,
    timeout: bool,
) -> None:
    retained_service, request = operation
    binding, qualification = _dispatch_registration(retained_service.plan, request)
    provider = _NativeProvider(retained_service.apply(request), timeout=timeout)
    service = amp.RegisteredAmplifierPm0DefaultChange(
        binding,
        retained_service.plan,
        qualification,
        provider,
        expected_binding_sha256=canonical_digest(binding),
    )
    bad = request.model_copy(update={"expected_scope_sha256": "0" * 64})
    with pytest.raises(ValueError, match="conflicts"):
        service.apply(bad)
    assert provider.claims == provider.launches == 0
    path = tmp_path / "request.json"
    path.write_text(request.model_dump_json(), encoding="utf-8")
    initial = dispatch_pmos_default_change(path, service)
    again = dispatch_pmos_default_change(path, service)
    assert provider.claims == provider.launches == 1
    assert initial.outcome == again.outcome == ("OUTCOME_UNKNOWN" if timeout else "VERIFIED")
    assert not initial.replayed and again.replayed and not again.dispatched_this_call


def test_registered_dispatch_rejects_substituted_copy(
    operation: tuple[amp.RetainedAmplifierPm0DefaultChange, PmosDefaultChangeRequest],
) -> None:
    service, request = operation
    binding, qualification = _dispatch_registration(service.plan, request)
    provider = _NativeProvider(service.apply(request), timeout=False)
    substituted = binding.model_copy(update={"owned_library": "AmpSubstituted"})
    with pytest.raises(ValueError, match="owned copy"):
        amp.RegisteredAmplifierPm0DefaultChange(
            substituted,
            service.plan,
            qualification,
            provider,
            expected_binding_sha256=canonical_digest(binding),
        )
    assert provider.claims == provider.launches == 0


def test_lost_claim_without_readable_result_stays_unknown(
    operation: tuple[amp.RetainedAmplifierPm0DefaultChange, PmosDefaultChangeRequest],
) -> None:
    class _InProgress(_NativeProvider):
        def claim(self, binding: amp.AmplifierPm0DispatchBinding) -> bool:
            self.claims += 1
            return False

    retained, request = operation
    binding, qualification = _dispatch_registration(retained.plan, request)
    provider = _InProgress(retained.apply(request), timeout=False)
    service = amp.RegisteredAmplifierPm0DefaultChange(
        binding,
        retained.plan,
        qualification,
        provider,
        expected_binding_sha256=canonical_digest(binding),
    )
    result = service.apply(request)
    assert result.outcome == "OUTCOME_UNKNOWN"
    assert result.replayed and not result.dispatched_this_call
    assert provider.claims == 1 and provider.launches == 0


def _registered_provider_fixture(
    operation: tuple[amp.RetainedAmplifierPm0DefaultChange, PmosDefaultChangeRequest],
    tmp_path: Path,
) -> tuple[Path, Path, PmosDefaultChangeRequest, amp_host._Scope, tuple[bytes, bytes, bytes]]:
    retained, original_request = operation
    _, qualification = _dispatch_registration(retained.plan, original_request)
    settings = make_settings(tmp_path)
    context = load_runtime(settings)[0]
    directory = tmp_path / "amp-job"
    directory.mkdir()
    evidence = b"synthetic independently reviewed route evidence"
    for name in ("cdf", "legal-value", "update-route"):
        (directory / f"{name}-evidence.private").write_bytes(evidence)
    qualification = qualification.model_copy(
        update={
            "cdf_evidence_sha256": _sha(evidence),
            "legal_value_evidence_sha256": _sha(evidence),
            "update_route_evidence_sha256": _sha(evidence),
        }
    )
    plan = amp.plan_amplifier_pm0_default_change(
        qualification,
        retained.plan.candidate_id,
        retained.plan.candidate_revision,
        retained.plan.requested,
    )
    assets = (b"# synthetic fixed guest\n", b"; fixed edit fixture\n", b"; fixed verify fixture\n")
    scope = amp_host._Scope(
        schema_version=1,
        route="amplifier_pm0_default",
        context_id=context.binding.context_id,
        resource_domain_sha256=context.resource_domain_sha256,
        environment_sha256=context.binding.environment_sha256,
        native_manifest_sha256="b" * 64,
        operation_id=_WRITER,
        owned_library="AmpFresh",
        owned_cell="Differential_Amplifier_TB2",
        owned_view="schematic",
        owned_before_view_tree_sha256="e" * 64,
        source_preservation_sha256="1" * 64,
        qualification=qualification,
        plan=plan,
        plan_sha256=plan.plan_sha256,
        guest_sha256=_sha(assets[0]),
        edit_script_sha256=_sha(assets[1]),
        verify_script_sha256=_sha(assets[2]),
        valid_until_unix=int(time.time()) + 600,
    )
    scope_raw = _json(scope.model_dump(mode="json"))
    scope_pin = _sha(scope_raw)
    (directory / "execution-scope.private.json").write_bytes(scope_raw)
    (directory / "baseline-input.private.scs").write_bytes(retained.baseline_input)
    ack = _json(
        {
            "owner": "C0",
            "operation_id": _WRITER,
            "scope_sha256": scope_pin,
            "approved_actions": ["edit", "readback-netlist"],
            "valid_until_unix": scope.valid_until_unix,
        }
    )
    (directory / "c0-exact-ack.private.json").write_bytes(ack)
    registration = _json(
        {
            "schema_version": 2,
            "route": "amplifier_pm0_default",
            "context_id": context.binding.context_id,
            "resource_domain_sha256": context.resource_domain_sha256,
            "scope_sha256": scope_pin,
            "evidence_directory": str(directory),
            "authority_sha256": _sha(ack),
        }
    )
    binding_path = tmp_path / "amp-registration.json"
    binding_path.write_bytes(registration)
    cfg = json.loads(settings.read_bytes())
    cfg["contexts"][0].update(
        pmos_default_change_binding=str(binding_path), pmos_default_change_sha256=_sha(registration)
    )
    settings.write_bytes(_json(cfg))
    request = PmosDefaultChangeRequest(
        operation_id=_WRITER,
        expected_scope_sha256=scope_pin,
        expected_plan_sha256=plan.plan_sha256,
    )
    return settings, directory, request, scope, assets


@pytest.mark.parametrize("transport_failure", [False, True])
def test_amp_registered_factory_dispatch_and_restart_replay(
    operation: tuple[amp.RetainedAmplifierPm0DefaultChange, PmosDefaultChangeRequest],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    transport_failure: bool,
) -> None:
    settings, directory, request, scope, assets = _registered_provider_fixture(operation, tmp_path)
    installed = tmp_path / "package-fixture"
    installed.mkdir()
    for name, data in zip(amp_host._ASSETS, assets, strict=True):
        (installed / name).write_bytes(data)
    monkeypatch.setattr(amp_host, "files", lambda _: installed)

    evidence = operation[0].journal.reconciliation
    assert evidence is not None
    receipt = amp_host._Receipt(
        status="VERIFIED",
        operation_id=_WRITER,
        scope_sha256=request.expected_scope_sha256,
        plan_sha256=scope.plan_sha256,
        owned_before_view_tree_sha256=scope.owned_before_view_tree_sha256,
        saved_view_tree_sha256=_VIEW,
        reopened_view_tree_sha256=_VIEW,
        netlisted_view_tree_sha256=_VIEW,
        source_preservation_sha256="1" * 64,
        reopen_receipt_sha256="2" * 64,
        netlist_receipt_sha256="3" * 64,
        presave_signature_sha256=_sha(evidence.presave),
        reopened_signature_sha256=_sha(evidence.reopened),
        netlist_sha256=_sha(evidence.netlist),
        edit_live_counter=35,
        reopen_frame=tuple(amp._pm0_frame(baseline=False)[0]),
        ocean_calls=2,
        simulations=0,
        reservations=0,
    )
    output = _json(
        amp_host._Response(
            receipt=receipt,
            receipt_sha256=canonical_digest(receipt),
            presave_base64=base64.b64encode(evidence.presave).decode("ascii"),
            reopened_base64=base64.b64encode(evidence.reopened).decode("ascii"),
            input_base64=base64.b64encode(evidence.netlist).decode("ascii"),
        ).model_dump(mode="json")
    )
    launched = []

    def fixed(
        argv: list[str], payload: bytes, *_: object, **kwargs: object
    ) -> tuple[int, bytes, bytes]:
        assert argv[-2:] == [shlex.quote(assets[0].decode("ascii")), request.expected_scope_sha256]
        packet = json.loads(payload)
        assert base64.b64decode(packet["edit_base64"]) == assets[1]
        assert base64.b64decode(packet["verify_base64"]) == assets[2]
        assert base64.b64decode(packet["baseline_base64"]) == operation[0].baseline_input
        assert kwargs["timeout"] == 60 and kwargs["limit"] == amp_host._LIMIT
        assert (directory / "amp-writer-intent.private.json").is_file()
        assert (directory / "amp-dispatch-intent.private.json").is_file()
        launched.append(payload)
        if transport_failure:
            raise TimeoutError
        return 0, output, b""

    monkeypatch.setattr(amp_host, "run_fixed", fixed)
    apply_path = tmp_path / "amp-request.json"
    apply_path.write_text(request.model_dump_json(), encoding="utf-8")
    initial = dispatch_pmos_default_change(
        apply_path, registered_pmos_default_change(load_runtime(settings)[0])
    )

    # A restarted caller can verify its retained bytes without the launch assets.
    def missing_asset(_: object) -> Path:
        raise AssertionError("replay must not resolve launch assets")

    monkeypatch.setattr(amp_host, "files", missing_asset)
    replay = dispatch_pmos_default_change(
        apply_path, registered_pmos_default_change(load_runtime(settings)[0])
    )
    expected = "OUTCOME_UNKNOWN" if transport_failure else "VERIFIED"
    assert len(launched) == 1 and initial.outcome == replay.outcome == expected
    assert initial.dispatched_this_call == (None if transport_failure else True)
    assert replay.replayed and not replay.dispatched_this_call


def test_amp_registration_without_packaged_assets_stops_before_claim(
    operation: tuple[amp.RetainedAmplifierPm0DefaultChange, PmosDefaultChangeRequest],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings, directory, request, _, _ = _registered_provider_fixture(operation, tmp_path)
    monkeypatch.setattr(amp_host, "files", lambda _: tmp_path / "missing-package")
    service = registered_pmos_default_change(load_runtime(settings)[0])
    with pytest.raises(OperationRejected) as failure:
        service.apply(request)
    assert failure.value.reason == "amp_pm0_reviewed_assets_missing"
    assert not list(directory.glob("amp-*.private.*"))
