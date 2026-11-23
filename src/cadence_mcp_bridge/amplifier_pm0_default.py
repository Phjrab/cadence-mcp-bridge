"""Finite AMP PM0 default recovery planning and read-only journal reconciliation.

The registered C1 provider owns dispatch and the durable intent. These helpers
consume the provider's pinned bytes and keep the writer and observer distinct.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Literal

from cadence_mcp_bridge.candidate_execution import (
    PmosDefaultChangeRequest,
    PmosDefaultChangeResult,
)
from cadence_mcp_bridge.domain_provisioning import _closed_document
from cadence_mcp_bridge.native_diagnostics import OperationId
from cadence_mcp_bridge.parameter_changes import _AMP_CENTER_SHA256 as _CENTER
from cadence_mcp_bridge.parameter_changes import (
    ChangePlan,
    ChangeValue,
    DerivedValue,
    GeometryProperty,
    MosWidthQualification,
    MosWidthTarget,
    NetlistProjection,
    plan_mos_width_change,
    project_netlist_change,
)
from cadence_mcp_bridge.schematic_plan import RevisionBinding
from cadence_mcp_bridge.variable_contracts import Digest, VariableModel

_CENTER_VIEW = "046021f90f70d85d05d59e4f80842f0742d6ca38c186d42ba27106a89b81d714"
_GEOMETRY: dict[GeometryProperty, tuple[str, str]] = {
    "fw": ("20u", "120n"),
    "as": ("5.6p", "69.6f"),
    "ad": ("5.6p", "69.6f"),
    "ps": ("40.56u", "1.16u"),
    "pd": ("40.56u", "1.16u"),
}
_WIDTH = ChangeValue(value="120", unit="nm")
_LIMIT = 131_072


class AmplifierPm0ReconciliationPins(VariableModel):
    observation_operation_id: OperationId
    observation_scope_sha256: Digest
    candidate_view_tree_sha256: Digest
    source_writer_failure_sha256: Digest
    observer_receipt_sha256: Digest
    observer_replay_sha256: Digest
    presave_sha256: Digest
    reopened_sha256: Digest
    netlist_sha256: Digest


class AmplifierPm0JournalPins(VariableModel):
    plan_sha256: Digest
    writer_operation_id: OperationId
    writer_scope_sha256: Digest
    writer_intent_sha256: Digest
    baseline_receipt_sha256: Digest
    writer_capture_sha256: Digest | None = None
    reconciliation: AmplifierPm0ReconciliationPins | None = None


@dataclass(frozen=True)
class AmplifierPm0Reconciliation:
    receipt: bytes
    replay: bytes
    presave: bytes
    reopened: bytes
    netlist: bytes


@dataclass(frozen=True)
class AmplifierPm0Journal:
    """Bytes read from the existing operation journal by its registered owner."""

    scope: bytes
    intent: bytes
    baseline_receipt: bytes
    writer_capture: bytes | None = None
    reconciliation: AmplifierPm0Reconciliation | None = None


class AmplifierPm0SavedRevision(VariableModel):
    observation_operation_id: OperationId
    observation_scope_sha256: Digest
    observer_receipt_sha256: Digest
    observer_replay_sha256: Digest
    source_writer_failure_sha256: Digest
    schematic_revision_sha256: Digest
    testbench_revision_sha256: Digest
    reopened_signature_sha256: Digest
    oa_readback_sha256: Digest
    oa_width: ChangeValue
    oa_geometry: tuple[DerivedValue, ...]
    saved_geometry_counter_before: int
    saved_geometry_counter_after: int
    netlist: NetlistProjection


class AmplifierPm0DefaultObservation(VariableModel):
    writer: PmosDefaultChangeResult
    saved_revision: AmplifierPm0SavedRevision | None = None
    execution_authorized: Literal[False] = False


def _check_plan(plan: ChangePlan) -> None:
    baseline = plan.baseline
    revision = baseline.revision
    target = plan.target
    if (
        not isinstance(target, MosWidthTarget)
        or (
            target.instance.instance_path,
            target.instance.master_library,
            target.instance.master_cell,
            target.instance.master_view,
            target.instance.property_name,
        )
        != ("PM0", "gpdk090", "pmos1v", "symbol", "w")
        or (revision.design_id, revision.revision_id)
        != ("reference-differential-amplifier-tb2", "reference-amplifier-bias-grid-v1")
        or baseline.netlist_sha256 != _CENTER
        or baseline.revision_sha256 != _CENTER_VIEW
        or baseline.testbench_revision_sha256 != _CENTER_VIEW
        or revision.source_baseline_sha256 != _CENTER_VIEW
        or plan.old.normalized != ChangeValue(value="20", unit="um").normalized
        or plan.requested.normalized != _WIDTH.normalized
        or plan.expected.normalized != _WIDTH.normalized
        or {
            row.before.property_name: (row.before.value, row.after.value)
            for row in plan.allowed_derived
        }
        != _GEOMETRY
    ):
        raise ValueError("exact AMP PM0 default recovery plan required")


def plan_amplifier_pm0_default_change(
    qualification: MosWidthQualification,
    candidate_id: str,
    candidate_revision: RevisionBinding,
    requested: ChangeValue,
) -> ChangePlan:
    """Resolve the registered 20 µm to 120 nm PM0 transition with the common planner."""
    plan = plan_mos_width_change(qualification, candidate_id, candidate_revision, requested)
    _check_plan(plan)
    return plan


def _pinned(raw: bytes, digest: str, limit: int = _LIMIT) -> bytes:
    if not 0 < len(raw) <= limit or sha256(raw).hexdigest() != digest:
        raise ValueError("AMP journal artifact digest or size mismatch")
    return raw


def _document(raw: bytes, digest: str) -> dict[str, Any]:
    raw = _pinned(raw, digest)
    _closed_document(raw)
    result = json.loads(raw)
    if not isinstance(result, dict):
        raise ValueError("AMP journal record must be an object")
    return result


def _parts(raw: str, count: int) -> tuple[str, ...]:
    """Read the existing native length-prefixed list without evaluating SKILL."""
    prefix = f"L{count}:"
    if not raw.startswith(prefix):
        raise ValueError("invalid AMP signature list")
    offset = len(prefix)
    result = []
    for _ in range(count):
        colon = raw.find(":", offset, offset + 7)
        length = raw[offset:colon] if colon >= 0 else ""
        if not length.isdecimal() or not 0 < int(length) <= _LIMIT or length.startswith("0"):
            raise ValueError("invalid AMP signature item length")
        offset = colon + 1
        end = offset + int(length)
        if end > len(raw):
            raise ValueError("truncated AMP signature")
        result.append(raw[offset:end])
        offset = end
    if offset != len(raw):
        raise ValueError("unexpected AMP signature suffix")
    return tuple(result)


def _signature(raw: bytes) -> tuple[str, ...]:
    text = raw.decode("ascii")
    if not text.endswith("\n"):
        raise ValueError("invalid AMP signature terminator")
    return _parts(text[:-1], 3)


def _view_rows(raw: str) -> dict[str, tuple[str, str]]:
    rows: dict[str, tuple[str, str]] = {}
    for row in _parts(raw, 8):
        name, kind, value = _parts(row, 3)
        if not name.startswith("S") or name[1:] in rows or not kind.startswith("S"):
            raise ValueError("invalid or duplicate AMP cellview property")
        rows[name[1:]] = (kind[1:], value)
    return rows


def _line(lines: tuple[str, ...], prefix: str) -> str:
    matches = [line[len(prefix) :] for line in lines if line.startswith(prefix)]
    if len(matches) != 1:
        raise ValueError("missing or duplicate AMP native journal marker")
    return matches[0]


def _save_metadata(lines: tuple[str, ...], presave: bytes, reopened: bytes) -> tuple[int, int]:
    pre = _signature(presave)
    post = _signature(reopened)
    if (
        lines[-1:] != ("AUTO120_FAIL|SAVE",)
        or pre[1] != _line(lines, "C1_ROWS|EDIT_AFTER|")
        or post[1] != _line(lines, "C1_ROWS|SAVED|")
        or pre[0] != post[0]
        or pre[2] != post[2]
    ):
        raise ValueError("AMP saved circuit or save-stage evidence mismatch")
    before, after = _view_rows(pre[1]), _view_rows(post[1])
    name = "schGeometryLastUpdated"
    old_kind, old_value = before.get(name, ("", ""))
    new_kind, new_value = after.get(name, ("", ""))
    check = _line(lines, "C1_CHECK|EDIT|").split("|")
    if (
        old_kind != "int"
        or new_kind != "int"
        or not old_value.startswith("I")
        or not new_value.startswith("I")
        or not old_value[1:].isdecimal()
        or not new_value[1:].isdecimal()
        or len(check) != 7
        or check[0] != "(0 0)"
        or check[-1] != "t"
        or new_value != "I" + check[4]
        or after.get("connectivityLastUpdated") != ("int", new_value)
        or old_value == new_value
        or tuple(before) != tuple(after)
        or (before | {name: after[name]}) != after
    ):
        raise ValueError("AMP save metadata must match the witnessed live geometry counter")
    old, new = int(old_value[1:]), int(new_value[1:])
    if old > new:
        raise ValueError("AMP saved geometry counter moved backwards")
    return old, new


def _pm0_frame(*, baseline: bool) -> tuple[list[str], dict[str, str]]:
    geometry = {name: pair[0 if baseline else 1] for name, pair in _GEOMETRY.items()}
    effective = geometry | {
        "w": "20u" if baseline else "120n",
        "l": "1u",
        "m": "1",
        "fingers": "1",
        "model": "gpdk090_pmos1v",
        "dfm": "Minimum",
        "nf": "-",
    }
    expected = {"AUTO120_MASTER|PM0|gpdk090|pmos1v|symbol"}
    expected.update(
        f"AUTO120_TERM|{terminal}|{net}"
        for terminal, net in (("B", "VDD"), ("D", "net33"), ("G", "Vbiasp"), ("S", "VDD"))
    )
    for name, value in effective.items():
        explicit = name == "l" or (baseline and (name == "w" or name in geometry))
        raw = f"string|{value}" if explicit else "-|-"
        expected.add(f"AUTO120_PROP|{name}|{raw}|{value}")
    return sorted(expected), effective


def _verify_reopened_pm0(frame: object, lines: tuple[str, ...]) -> tuple[DerivedValue, ...]:
    expected, effective = _pm0_frame(baseline=False)
    for name, value in effective.items():
        raw_type, raw_value = ("string", "1u") if name == "l" else ("-", "-")
        oa_presence = "t" if name == "l" else "nil"
        cdf_presence = "nil|nil" if name == "nf" else "t|string"
        if _line(lines, f"AUTO120_DIAG_PROP|AFTER_REMOVE|{name}|") != (
            f"{value}|{oa_presence}|{raw_type}|{raw_value}|{cdf_presence}|{value}"
        ):
            raise ValueError("AMP pre-save PM0 property mismatch")
    if frame != expected:
        raise ValueError("AMP reopened PM0 properties or terminal binding mismatch")
    return tuple(DerivedValue(property_name=name, value=effective[name]) for name in _GEOMETRY)


def _writer_capture(raw: bytes, pin: str, writer_scope: str) -> tuple[str, tuple[str, ...]]:
    document = _document(raw, pin)
    stages = document.get("stages")
    if document.get("scope") != writer_scope or not isinstance(stages, list) or len(stages) != 1:
        raise ValueError("AMP writer journal scope mismatch")
    stage = stages[0]
    detail = stage["detail"]
    lines = detail["logs"]["ocean.stdout"]["diagnostic"]
    if (
        stage["phase"] != "edit"
        or detail["phase"] != "edit"
        or detail["scope_sha256"] != writer_scope
        or detail["status"] != "OUTCOME_UNKNOWN"
        or detail["conservation"] != "MATCHED"
        or type(detail["ocean_launched"]) is not int
        or detail["ocean_launched"] != 1
        or detail["program_issued"] is not True
        or detail["program_failure"]["cleanup"] != "REAPED"
        or not isinstance(lines, list)
        or len(lines) > 96
        or not all(isinstance(line, str) for line in lines)
        or not isinstance(stage["failure_sha256"], str)
    ):
        raise ValueError("AMP writer failure evidence mismatch")
    return stage["failure_sha256"], tuple(lines)


def _saved_revision(
    data: AmplifierPm0Reconciliation,
    pins: AmplifierPm0ReconciliationPins,
    plan: ChangePlan,
    baseline_input: bytes,
    writer_operation_id: str,
    writer_failure_sha256: str,
    lines: tuple[str, ...],
) -> AmplifierPm0SavedRevision:
    receipt = _document(data.receipt, pins.observer_receipt_sha256)
    replay = _document(data.replay, pins.observer_replay_sha256)
    before = receipt["before"]
    markers = receipt["gate_markers"]
    op = pins.observation_operation_id
    scope = pins.observation_scope_sha256
    if (
        op == writer_operation_id
        or pins.source_writer_failure_sha256 != writer_failure_sha256
        or receipt["operation_id"] != op
        or receipt["scope_sha256"] != scope
        or receipt["failed_operation"] != writer_operation_id
        or receipt["failure"] != writer_failure_sha256
        or receipt["status"] != "RECONCILED_READ_ONLY"
        or receipt["phase"] != "child-netlist"
        or type(receipt["netlists"]) is not int
        or receipt["netlists"] != 1
        or type(receipt["ocean_calls"]) is not int
        or receipt["ocean_calls"] != 1
        or before != receipt["after"]
        or before["view_tree"] != pins.candidate_view_tree_sha256
        or before["view_tree"] == _CENTER_VIEW
        or receipt["input_sha256"] != pins.netlist_sha256
        or receipt["frozen_sha256"] != pins.reopened_sha256
        or markers[:2] != [f"AUTO120_DONE|{op}|reopen", "C1_VERIFIED_INDEPENDENT_REOPEN"]
        or markers[-1:] != [f"C1_AMP_ADE_COMPLETE|child-netlist|{op}"]
        or any(
            type(receipt[k]) is not int or receipt[k] != 0 for k in ("simulations", "reservations")
        )
        or replay["status"] != "RECONCILIATION_REPLAY"
        or replay["operation_id"] != op
        or replay["scope"] != scope
        or replay["receipt_sha256"] != pins.observer_receipt_sha256
        or replay["after"] != before
        or replay["counter"] != receipt["counter"]
        or any(
            type(replay[k]) is not int or replay[k] != 0
            for k in ("writes", "ocean_calls", "simulations", "reservations")
        )
    ):
        raise ValueError("AMP observer receipt or zero-effect replay binding mismatch")
    counters = _save_metadata(
        lines,
        _pinned(data.presave, pins.presave_sha256),
        _pinned(data.reopened, pins.reopened_sha256),
    )
    geometry = _verify_reopened_pm0(receipt["reopen_frame"], lines)
    projection = project_netlist_change(
        plan, baseline_input, _pinned(data.netlist, pins.netlist_sha256, 32768)
    )
    return AmplifierPm0SavedRevision(
        observation_operation_id=op,
        observation_scope_sha256=scope,
        observer_receipt_sha256=pins.observer_receipt_sha256,
        observer_replay_sha256=pins.observer_replay_sha256,
        source_writer_failure_sha256=writer_failure_sha256,
        schematic_revision_sha256=pins.candidate_view_tree_sha256,
        testbench_revision_sha256=pins.candidate_view_tree_sha256,
        reopened_signature_sha256=pins.reopened_sha256,
        oa_readback_sha256=receipt["readback_sha256"],
        oa_width=_WIDTH,
        oa_geometry=geometry,
        saved_geometry_counter_before=counters[0],
        saved_geometry_counter_after=counters[1],
        netlist=projection,
    )


def verify_amplifier_pm0_default_observation(
    request: PmosDefaultChangeRequest,
    plan: ChangePlan,
    journal: AmplifierPm0Journal,
    *,
    pins: AmplifierPm0JournalPins,
    baseline_input: bytes,
) -> AmplifierPm0DefaultObservation:
    """Replay an existing intent and optionally verify its separately registered observer.

    Only the trusted provider supplies journal bytes and independent digest pins.
    Calling repeatedly has no effects and never changes the writer's outcome.
    """
    request = PmosDefaultChangeRequest.model_validate_json(request.model_dump_json())
    plan = ChangePlan.model_validate_json(plan.model_dump_json())
    pins = AmplifierPm0JournalPins.model_validate_json(pins.model_dump_json())
    _check_plan(plan)
    _pinned(baseline_input, plan.baseline.netlist_sha256, 32768)
    if (
        request.expected_plan_sha256 != plan.plan_sha256
        or plan.plan_sha256 != pins.plan_sha256
        or request.operation_id != pins.writer_operation_id
        or request.expected_scope_sha256 != pins.writer_scope_sha256
    ):
        raise ValueError("AMP writer operation, plan or scope conflict")
    scope = _document(journal.scope, pins.writer_scope_sha256)
    intent = _document(journal.intent, pins.writer_intent_sha256)
    baseline = _document(journal.baseline_receipt, pins.baseline_receipt_sha256)
    if (
        scope.get("operation_id") != request.operation_id
        or scope.get("completed_baseline_receipt") != pins.baseline_receipt_sha256
        or scope.get("completed_baseline_scope") != baseline.get("scope_sha256")
        or baseline.get("status") != "CLOSED_BASELINE_MATCHED"
        or baseline.get("frame") != _pm0_frame(baseline=True)[0]
        or intent
        != {
            "phase": "edit",
            "scope_sha256": pins.writer_scope_sha256,
            "prior": [pins.baseline_receipt_sha256],
        }
    ):
        raise ValueError("AMP writer intent identity mismatch")
    writer = PmosDefaultChangeResult(
        operation_id=request.operation_id,
        plan_sha256=plan.plan_sha256,
        scope_sha256=pins.writer_scope_sha256,
        outcome="OUTCOME_UNKNOWN",
        replayed=True,
        dispatched_this_call=False,
        candidate_revision=plan.candidate_revision,
        reason="retained_writer_outcome_unknown",
    )
    if journal.reconciliation is None and pins.reconciliation is None:
        return AmplifierPm0DefaultObservation(writer=writer)
    if (
        journal.reconciliation is None
        or pins.reconciliation is None
        or journal.writer_capture is None
        or pins.writer_capture_sha256 is None
    ):
        raise ValueError("AMP independent observation evidence incomplete")
    try:
        failure, lines = _writer_capture(
            journal.writer_capture, pins.writer_capture_sha256, pins.writer_scope_sha256
        )
        revision = _saved_revision(
            journal.reconciliation,
            pins.reconciliation,
            plan,
            baseline_input,
            request.operation_id,
            failure,
            lines,
        )
    except (KeyError, TypeError, IndexError) as exc:
        raise ValueError("invalid AMP journal evidence shape") from exc
    return AmplifierPm0DefaultObservation(writer=writer, saved_revision=revision)


@dataclass(frozen=True)
class RetainedAmplifierPm0DefaultChange:
    """The existing apply interface over a registered AMP journal, with no dispatch."""

    plan: ChangePlan
    journal: AmplifierPm0Journal
    pins: AmplifierPm0JournalPins
    baseline_input: bytes

    def observe(self, request: PmosDefaultChangeRequest) -> AmplifierPm0DefaultObservation:
        return verify_amplifier_pm0_default_observation(
            request, self.plan, self.journal, pins=self.pins, baseline_input=self.baseline_input
        )

    def apply(self, request: PmosDefaultChangeRequest) -> PmosDefaultChangeResult:
        return self.observe(request).writer
