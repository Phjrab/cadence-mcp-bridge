"""Join reviewed OTA17 HNL-only custody and electrical proof without dispatch."""

import json
import re
from decimal import Decimal
from hashlib import sha256
from typing import Literal, Self

from pydantic import model_validator

from cadence_mcp_bridge._native_rendering import statements
from cadence_mcp_bridge.domain_provisioning import _canonical, _closed_document
from cadence_mcp_bridge.native_diagnostics import OperationId
from cadence_mcp_bridge.ota_dual_hnl_transport import OtaDualHnlReceipt
from cadence_mcp_bridge.variable_contracts import Digest, VariableModel

_WRITER = "90bb7446-92f5-4ab4-a687-7cafdc09ca18"
_COPY = "d741743c-dc34-41ef-a893-afe1b146ca3e"
_WRITER_SCOPE = "858f08fc8dc78cd238d66041e0c8a3947c7213756547219dddc4d3f3a73aa767"
_PLAN = "2fd3666dfec696b527908e30508a4f3261dd6daee39d028a9489a8d1f1b2f299"
_SAVE = "779425060d6787aec5e19fbab1803f70b15c8ca6bd5ae83a1cf5113a9c0c86b8"
_DUT = "2a8572534ea286d82563557d4c4754a7fbb9633528ea7b390cbfbe4f49347dfc"
_TB = "1092a11b28d33c8daa493ead7b98f1df257d4538421c821b71335fbb995dca1e"
_OLD_LOCKED = "fe73b903286fbbb9ef7d9310d4562b850a82459733d4becdc046f765fa18fc73"
_OLD_FAILURE = "964e1c5d59842e251a409248f13c96c6fcfca7e5c18874408cbc56bafed87c55"
_BAD_HNL = frozenset((
    "9351137cdd072572b33c4993377477d03f40f9a487878874282cea6cb984bba8",
    "3c130404eb09fa40d8e7ee8854e5d46fc81b8e666aaa6745f70a57b621bccf9a",
))
_BIASES = {"VBIASN": Decimal("0.320"), "VBIASP": Decimal("0.702")}
_SCALAR = re.compile(r"([0-9]{1,4}(?:\.[0-9]{1,9})?|\.[0-9]{1,9})(m)?")


class OtaCorrectedHnlCustody(VariableModel):
    """Closed projection prepared from C1's independently reviewed HNL-only artifacts."""

    schema_version: Literal[1]
    kind: Literal["OTA17_HNL_ONLY_LOCKED_CUSTODY"]
    writer_operation_id: OperationId
    writer_scope_sha256: Digest
    writer_plan_sha256: Digest
    writer_terminal: Literal["OUTCOME_UNKNOWN"]
    original_locked_sha256: Digest
    original_failure_sha256: Digest
    owned_copy_operation_id: OperationId
    operation_id: OperationId
    scope_sha256: Digest
    locked_postflight_sha256: Digest
    native_intent_sha256: Digest
    native_receipt_sha256: Digest
    native_complete_sha256: Digest
    reopened_cdf_sha256: Digest
    reopened_footprint_sha256: Digest
    owned_ade_sha256: Digest
    source_preservation_sha256: Digest
    model_closure_sha256: Digest
    design_writes: Literal[0]
    diagnostics: OtaDualHnlReceipt

    @model_validator(mode="after")
    def single_saved_source(self) -> Self:
        if (
            str(self.writer_operation_id) != _WRITER
            or self.writer_scope_sha256 != _WRITER_SCOPE
            or self.writer_plan_sha256 != _PLAN
            or self.original_locked_sha256 != _OLD_LOCKED
            or self.original_failure_sha256 != _OLD_FAILURE
            or str(self.owned_copy_operation_id) != _COPY
            or str(self.operation_id) in (_WRITER, _COPY)
            or self.scope_sha256 == _WRITER_SCOPE
        ):
            raise ValueError("ota_corrected_hnl_lineage")
        for leaf in (self.diagnostics.ac, self.diagnostics.dc):
            if (
                leaf.operation_id != self.operation_id
                or leaf.scope_sha256 != self.scope_sha256
                or leaf.saved_receipt_sha256 != _SAVE
                or leaf.dut_revision_sha256 != _DUT
                or leaf.testbench_revision_sha256 != _TB
            ):
                raise ValueError("ota_corrected_hnl_mode_binding")
        return self


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


def verify_ota_corrected_dual_hnl_source(
    custody_raw: bytes,
    electrical_raw: bytes,
    ac_raw: bytes,
    dc_raw: bytes,
    *,
    expected_custody_sha256: str,
    expected_electrical_sha256: str,
) -> OtaCorrectedDualHnlSource:
    """Join independently pinned C1 and C6 projections to the actual mode bytes."""
    for document, expected in (
        (custody_raw, expected_custody_sha256),
        (electrical_raw, expected_electrical_sha256),
    ):
        _closed_document(document, max_bytes=32_768)
        if sha256(document).hexdigest() != expected or _canonical(json.loads(document)) != document:
            raise ValueError("ota_corrected_hnl_review_pin")
    custody = OtaCorrectedHnlCustody.model_validate_json(custody_raw)
    electrical = OtaCorrectedHnlElectricalProof.model_validate_json(electrical_raw)
    if (
        electrical.custody_sha256 != expected_custody_sha256
        or electrical.reopened_cdf_sha256 != custody.reopened_cdf_sha256
    ):
        raise ValueError("ota_corrected_hnl_electrical_binding")
    for raw, native_pin, review_pin in (
        (ac_raw, custody.diagnostics.ac.netlist_sha256, electrical.ac_raw_sha256),
        (dc_raw, custody.diagnostics.dc.netlist_sha256, electrical.dc_raw_sha256),
    ):
        verify_ota_candidate_bias(raw)
        actual = sha256(raw).hexdigest()
        if actual != native_pin or actual != review_pin or actual in _BAD_HNL:
            raise ValueError("ota_corrected_hnl_raw_binding")
    return OtaCorrectedDualHnlSource(
        custody_sha256=expected_custody_sha256,
        electrical_proof_sha256=expected_electrical_sha256,
        custody=custody,
        electrical=electrical,
    )
