"""Join reviewed OTA17 HNL-only custody and electrical proof without dispatch."""

import json
import re
from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
from pathlib import PurePosixPath
from typing import Any, Literal

from pydantic import field_validator

from cadence_mcp_bridge._native_rendering import statements
from cadence_mcp_bridge.domain_provisioning import _canonical, _closed_document
from cadence_mcp_bridge.native_diagnostics import OperationId
from cadence_mcp_bridge.variable_contracts import Digest, VariableModel

_WRITER = "90bb7446-92f5-4ab4-a687-7cafdc09ca18"
_COPY = "d741743c-dc34-41ef-a893-afe1b146ca3e"
_HNL_OPERATION = "b3a1c02e-a9fb-41ca-b798-17dea5eb7b78"
_WRITER_SCOPE = "858f08fc8dc78cd238d66041e0c8a3947c7213756547219dddc4d3f3a73aa767"
_PLAN = "2fd3666dfec696b527908e30508a4f3261dd6daee39d028a9489a8d1f1b2f299"
_SAVE = "779425060d6787aec5e19fbab1803f70b15c8ca6bd5ae83a1cf5113a9c0c86b8"
_DUT = "2a8572534ea286d82563557d4c4754a7fbb9633528ea7b390cbfbe4f49347dfc"
_TB = "1092a11b28d33c8daa493ead7b98f1df257d4538421c821b71335fbb995dca1e"
_OLD_LOCKED = "fe73b903286fbbb9ef7d9310d4562b850a82459733d4becdc046f765fa18fc73"
_OLD_FAILURE = "964e1c5d59842e251a409248f13c96c6fcfca7e5c18874408cbc56bafed87c55"
_OLD_CDF = "f27cde33349cc763bb523aa801634937724e9a3e3495d211e100780072071fd4"
_PURPOSE = "OTA17_FIXED_BIAS_DETACHED_DUAL_HNL"
_CAPTURED = "OTA17_FIXED_BIAS_DUAL_HNL_CAPTURED"
_BAD_HNL = frozenset((
    "9351137cdd072572b33c4993377477d03f40f9a487878874282cea6cb984bba8",
    "3c130404eb09fa40d8e7ee8854e5d46fc81b8e666aaa6745f70a57b621bccf9a",
))
_BIASES = {"VBIASN": Decimal("0.320"), "VBIASP": Decimal("0.702")}
_SCALAR = re.compile(r"([0-9]{1,4}(?:\.[0-9]{1,9})?|\.[0-9]{1,9})(m)?")


class _Views(VariableModel):
    bench: Digest
    dut: Digest
    state: Digest
    symbol: Digest


class _Counter(VariableModel):
    campaign_id: Literal["AUTO-PHASE-01"]
    count: Literal[153]
    result_reserved_bytes: Literal[18166579200]


class OtaCorrectedHnlMode(VariableModel):
    raw_sha256: Digest
    raw_path: str
    project: str
    state_path: str
    bench_tree_sha256: Digest
    state_sha256: Digest
    fixed_parameters: dict[str, str]
    static_sha256: Digest
    mode: Literal["ac", "dc"]

    @field_validator("raw_path", "project", "state_path")
    @classmethod
    def canonical_path(cls, raw: str) -> str:
        path = PurePosixPath(raw)
        if (
            path.anchor != "/" or path.as_posix() != raw or ".." in path.parts
            or len(raw) > 1024
            or not all(part.isascii() and part.isprintable() for part in path.parts)
        ):
            raise ValueError("ota_corrected_hnl_path")
        return raw


class _Modes(VariableModel):
    ac: OtaCorrectedHnlMode
    dc: OtaCorrectedHnlMode


class OtaCorrectedHnlCustody(VariableModel):
    """Exact C1 native receipt from the separate HNL-only operation."""

    status: Literal["OTA17_FIXED_BIAS_DUAL_HNL_CAPTURED"]
    operation_id: OperationId
    scope_sha256: Digest
    writer_operation_id: OperationId
    saved_receipt_sha256: Digest
    source_views: _Views
    original_failed_terminal_sha256: Digest
    stdout_sha256: Digest
    intent_sha256: Digest
    mode_evidence: _Modes
    counter: _Counter
    ocean: Literal[1]
    spectre: Literal[0]
    reservations: Literal[0]
    external_copies: Literal[0]


@dataclass(frozen=True)
class OtaCorrectedHnlArtifacts:
    scope: bytes
    preflight: bytes
    receipt: bytes
    complete: bytes
    stdout: bytes
    original_save: bytes
    original_locked: bytes
    original_failure: bytes
    original_reopened_cdf: bytes
    closed_custody: bytes


class OtaCorrectedHnlElectricalProof(VariableModel):
    """C6's reviewed projection of full candidate and per-mode electrical verification."""

    schema_version: Literal[1]
    kind: Literal["OTA17_VERIFIED_DUAL_HNL_ELECTRICAL"]
    custody_sha256: Digest
    ac_raw_sha256: Digest
    dc_raw_sha256: Digest
    ac_conditions_sha256: Digest
    dc_conditions_sha256: Digest
    ac_comparison_sha256: Digest
    dc_comparison_sha256: Digest
    reopened_cdf_sha256: Digest
    verified_mos_count: Literal[17]


class OtaCorrectedDualHnlSource(VariableModel):
    schema_version: Literal[1] = 1
    kind: Literal["OTA17_CORRECTED_DUAL_HNL_SOURCE_V1"] = "OTA17_CORRECTED_DUAL_HNL_SOURCE_V1"
    writer_status: Literal["OUTCOME_UNKNOWN"] = "OUTCOME_UNKNOWN"
    analysis_authorized: Literal[False] = False
    owned_copy_operation_id: OperationId = _COPY
    scope_sha256: Digest
    preflight_sha256: Digest
    complete_sha256: Digest
    closed_custody_sha256: Digest
    original_reopened_cdf_sha256: Digest
    valid_until_unix: int
    custody_sha256: Digest
    electrical_proof_sha256: Digest
    custody: OtaCorrectedHnlCustody
    electrical: OtaCorrectedHnlElectricalProof


def verify_ota_candidate_bias(raw: bytes) -> None:
    """Check the original HNL bias literals with the existing statement tokenizer."""
    if not 0 < len(raw) <= 32_768:
        raise ValueError("ota_corrected_hnl_raw_size")
    parameters: dict[str, Decimal] = {}
    for statement in statements(raw):  # type: ignore[no-untyped-call]
        keyword, *assignments = statement.split()
        if keyword.lower() != "parameters":
            continue
        if keyword != "parameters" or not assignments:
            raise ValueError("ota_corrected_hnl_parameters")
        for assignment in assignments:
            key, _, token = assignment.partition("=")
            value = _SCALAR.fullmatch(token)
            if key not in _BIASES or key in parameters or value is None:
                raise ValueError("ota_corrected_hnl_parameters")
            number = Decimal(value[1])
            parameters[key] = number.scaleb(-3) if value[2] else number
    if parameters != _BIASES:
        raise ValueError("ota_corrected_hnl_bias_mismatch")


def _document(raw: bytes, expected: str, limit: int = 32_768) -> dict[str, Any]:
    _closed_document(raw, max_bytes=limit)
    data = json.loads(raw)
    if not isinstance(data, dict) or sha256(raw).hexdigest() != expected or _canonical(data) != raw:
        raise ValueError("ota_corrected_hnl_review_pin")
    return data


def verify_ota_corrected_hnl_custody(
    artifacts: OtaCorrectedHnlArtifacts,
    *,
    expected_scope_sha256: str,
    expected_preflight_sha256: str,
    expected_custody_sha256: str,
    expected_closed_custody_sha256: str,
) -> tuple[OtaCorrectedHnlCustody, int]:
    """Check the genuine receipt, completion, exact mode transcript and saved predecessor."""
    scope = _document(artifacts.scope, expected_scope_sha256)
    preflight = _document(artifacts.preflight, expected_preflight_sha256)
    _document(artifacts.receipt, expected_custody_sha256)
    custody = OtaCorrectedHnlCustody.model_validate_json(artifacts.receipt)
    closed = _document(artifacts.closed_custody, expected_closed_custody_sha256, 65_536)
    saved = _document(artifacts.original_save, _SAVE)
    locked = _document(artifacts.original_locked, _OLD_LOCKED, 524_288)
    failure = _document(artifacts.original_failure, _OLD_FAILURE)
    operation = _HNL_OPERATION
    intent = _canonical(
        dict(operation_id=operation, scope_sha256=expected_scope_sha256, retry=False)
    )
    fixed = {"VBIASN": "0.32", "VBIASP": "0.702"}
    deadline = scope.get("valid_until_unix")
    if (
        scope.get("purpose") != _PURPOSE
        or scope.get("operation_id") != operation
        or scope.get("writer_operation_id") != _WRITER
        or scope.get("observed_terminal_sha256") != _OLD_LOCKED
        or scope.get("saved_receipt_sha256") != _SAVE
        or scope.get("fixed_parameters") != fixed
        or scope.get("ocean_max") != 1
        or any(
            scope.get(key) != 0
            for key in ("new_external_copies", "spectre_max", "reservations_max")
        )
        or type(deadline) is not int or deadline <= 0
        or str(custody.operation_id) != operation
        or str(custody.writer_operation_id) != _WRITER
        or custody.scope_sha256 != expected_scope_sha256
        or custody.saved_receipt_sha256 != _SAVE
        or custody.original_failed_terminal_sha256 != _OLD_LOCKED
        or custody.intent_sha256 != sha256(intent).hexdigest()
        or artifacts.complete != _canonical({"receipt_sha256": expected_custody_sha256})
        or saved.get("operation_id") != _WRITER
        or saved.get("scope_sha256") != _WRITER_SCOPE
        or saved.get("plan_sha256") != _PLAN
        or failure.get("operation_id") != _WRITER
        or failure.get("phase") != "INDEPENDENT_REOPEN_NETLIST"
        or failure.get("status") != "OUTCOME_UNKNOWN"
        or locked["phases"]["edit"]["receipt.json"]["sha256"] != _SAVE
        or locked["phases"]["reopen"]["failure.json"]["sha256"] != _OLD_FAILURE
        or "complete.json" in locked["phases"]["reopen"]
        or locked["retained_inputs"]["cdf"]["sha256"] != _OLD_CDF
        or custody.source_views.model_dump() != scope.get("views")
        or custody.source_views.model_dump() != locked.get("views")
        or (custody.source_views.dut, custody.source_views.bench) != (_DUT, _TB)
        or sha256(artifacts.original_reopened_cdf).hexdigest() != _OLD_CDF
        or custody.counter.model_dump() != scope.get("counter")
        or custody.counter.model_dump() != locked.get("counter")
        or preflight.get("status") != "OTA17_FIXED_BIAS_DUAL_HNL_PREFLIGHT"
        or preflight.get("operation_id") != operation
        or preflight.get("scope_sha256") != expected_scope_sha256
        or preflight.get("counter") != scope.get("counter")
        or preflight.get("scope_cap_bytes") != scope.get("scratch_cap_bytes")
        or preflight.get("stock_projection_bytes") != scope.get("stock_projection_bytes")
        or any(
            preflight.get(key) != 0
            for key in ("ocean", "spectre", "reservations", "external_copies")
        )
    ):
        raise ValueError("ota_corrected_hnl_lineage")
    root = scope.get("job_root")
    program_context = scope.get("program_context_sha256")
    if not isinstance(root, str) or not isinstance(program_context, str):
        raise ValueError("ota_corrected_hnl_scope_shape")
    markers: list[bytes] = []
    cell = "Grel_" + operation.replace("-", "_")
    for mode, alias, leaf in (
        ("ac", "MCP_GREL_Work", custody.mode_evidence.ac),
        ("dc", "MCP_GREL_WorkDc", custody.mode_evidence.dc),
    ):
        area = f"{root}/{operation}/{mode}"
        expected_state = f"{area}/state-root/{alias}/{cell}/spectre/state1"
        if (
            leaf.mode != mode or leaf.project != f"{area}/project"
            or leaf.state_path != expected_state or leaf.fixed_parameters != fixed
            or PurePosixPath(leaf.project) not in PurePosixPath(leaf.raw_path).parents
        ):
            raise ValueError("ota_corrected_hnl_mode_binding")
        token = sha256(f"{program_context}|{mode}".encode("ascii")).hexdigest()
        markers.extend((
            f"MCP_GENERIC_ADE_NETLIST|{token}|{operation}".encode("ascii"),
            f"OTA17_CORRECTED_HNL_MODE_CLOSED|{mode}|{token}|{operation}".encode("ascii"),
        ))
    prefixes = (b"MCP_GENERIC_ADE_NETLIST|", b"OTA17_CORRECTED_HNL_MODE_CLOSED|")
    if (
        not 0 < len(artifacts.stdout) <= 65_536
        or sha256(artifacts.stdout).hexdigest() != custody.stdout_sha256
        or [line for line in artifacts.stdout.splitlines() if line.startswith(prefixes)] != markers
        or custody.mode_evidence.ac.raw_sha256 == custody.mode_evidence.dc.raw_sha256
    ):
        raise ValueError("ota_corrected_hnl_mode_custody")
    _verify_closed_custody(closed, scope, custody, artifacts.complete)
    return custody, deadline


def _verify_closed_custody(
    closed: dict[str, Any],
    scope: dict[str, Any],
    custody: OtaCorrectedHnlCustody,
    complete: bytes,
) -> None:
    mode_evidence = closed.get("validated_modes")
    charge = closed.get("diagnostic_charge_bytes")
    cap = scope.get("scratch_cap_bytes")
    if (
        closed.get("status") != "OTA17_FIXED_BIAS_RAW_CUSTODY_LOCKED"
        or closed.get("source_reopen_result") != "OUTCOME_UNKNOWN"
        or closed.get("diagnostic_operation_id") != custody.operation_id
        or closed.get("source_writer") != custody.writer_operation_id
        or closed.get("diagnostic_scope_sha256") != custody.scope_sha256
        or closed.get("diagnostic_receipt_sha256") is None
        or complete != _canonical({"receipt_sha256": closed["diagnostic_receipt_sha256"]})
        or closed.get("diagnostic_complete_sha256") != sha256(complete).hexdigest()
        or closed.get("diagnostic_native_stdout_sha256") != custody.stdout_sha256
        or closed.get("saved_receipt_sha256") != custody.saved_receipt_sha256
        or closed.get("writer_postflight_sha256") != custody.original_failed_terminal_sha256
        or closed.get("source_views") != custody.source_views.model_dump(mode="json")
        or closed.get("counter") != custody.counter.model_dump(mode="json")
        or closed.get("active_runner") != scope.get("native_manifest_sha256")
        or closed.get("active_layout") != scope.get("layout_manifest_sha256")
        or type(charge) is not int or type(cap) is not int or not 0 < charge <= cap
        or any(closed.get(key) != 0 for key in ("ocean", "spectre", "reservations", "writes"))
        or not isinstance(mode_evidence, dict)
        or set(mode_evidence) != {"ac", "dc"}
    ):
        raise ValueError("ota_corrected_hnl_closed_custody")
    for leaf in (custody.mode_evidence.ac, custody.mode_evidence.dc):
        wire = mode_evidence[leaf.mode]
        if not isinstance(wire, dict):
            raise ValueError("ota_corrected_hnl_closed_mode")
        observed = dict(wire)
        normalized = observed.pop("normalized_model_only_sha256", None)
        if (
            not isinstance(normalized, str)
            or re.fullmatch(r"[a-f0-9]{64}", normalized) is None
            or observed != leaf.model_dump(mode="json")
        ):
            raise ValueError("ota_corrected_hnl_closed_mode")


def verify_ota_corrected_dual_hnl_source(
    artifacts: OtaCorrectedHnlArtifacts,
    electrical_raw: bytes,
    ac_raw: bytes,
    dc_raw: bytes,
    *,
    expected_scope_sha256: str,
    expected_preflight_sha256: str,
    expected_custody_sha256: str,
    expected_closed_custody_sha256: str,
    expected_electrical_sha256: str,
) -> OtaCorrectedDualHnlSource:
    """Join independently pinned C1 and C6 projections to the actual mode bytes."""
    custody, deadline = verify_ota_corrected_hnl_custody(
        artifacts, expected_scope_sha256=expected_scope_sha256,
        expected_preflight_sha256=expected_preflight_sha256,
        expected_custody_sha256=expected_custody_sha256,
        expected_closed_custody_sha256=expected_closed_custody_sha256,
    )
    _document(electrical_raw, expected_electrical_sha256)
    electrical = OtaCorrectedHnlElectricalProof.model_validate_json(electrical_raw)
    if (
        electrical.custody_sha256 != expected_custody_sha256
        or electrical.reopened_cdf_sha256 != _OLD_CDF
    ):
        raise ValueError("ota_corrected_hnl_electrical_binding")
    for raw, native_pin, review_pin in (
        (ac_raw, custody.mode_evidence.ac.raw_sha256, electrical.ac_raw_sha256),
        (dc_raw, custody.mode_evidence.dc.raw_sha256, electrical.dc_raw_sha256),
    ):
        verify_ota_candidate_bias(raw)
        actual = sha256(raw).hexdigest()
        if actual != native_pin or actual != review_pin or actual in _BAD_HNL:
            raise ValueError("ota_corrected_hnl_raw_binding")
    return OtaCorrectedDualHnlSource(
        owned_copy_operation_id=_COPY,
        scope_sha256=expected_scope_sha256,
        preflight_sha256=expected_preflight_sha256,
        complete_sha256=sha256(artifacts.complete).hexdigest(),
        closed_custody_sha256=expected_closed_custody_sha256,
        original_reopened_cdf_sha256=_OLD_CDF,
        valid_until_unix=deadline,
        custody_sha256=expected_custody_sha256,
        electrical_proof_sha256=expected_electrical_sha256,
        custody=custody,
        electrical=electrical,
    )
