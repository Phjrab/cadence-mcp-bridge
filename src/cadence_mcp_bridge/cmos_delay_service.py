"""Read-only registered TRAN retrieval followed by a separate local delay estimate."""

from __future__ import annotations

import json
import math
from typing import Literal, Self

from pydantic import model_validator

from cadence_mcp_bridge.cmos_delay import (
    CmosDelayRequest,
    CmosDelayResult,
    DelayDefinition,
    DelayEvidence,
    evaluate_cmos_delay,
)
from cadence_mcp_bridge.native_service import NativeOperationQuery, NativeOperationService
from cadence_mcp_bridge.operator_operations import DurableOperation, OperationRejected
from cadence_mcp_bridge.result_reports import make_report
from cadence_mcp_bridge.runtime_context import ExecutionContext
from cadence_mcp_bridge.variable_contracts import Digest, LogicalId, VariableModel, canonical_digest


class CmosDelayResultQuery(NativeOperationQuery):
    definition: DelayDefinition
    supply_signal: LogicalId

    @model_validator(mode="after")
    def separate_supply(self) -> Self:
        if self.supply_signal in (self.definition.input_signal, self.definition.output_signal):
            raise ValueError("distinct registered supply voltage signal required")
        return self


class DelayResultSource(VariableModel):
    evidence: DelayEvidence
    measurement_id: LogicalId
    extraction_receipt_sha256: Digest
    terminal_receipt_sha256: Digest
    conditions_sha256: Digest
    supply_signal: LogicalId
    provider_boundary: Literal["REGISTERED_RESULT_IDENTITY_CHECKS_PASSED"] = (
        "REGISTERED_RESULT_IDENTITY_CHECKS_PASSED"
    )
    provenance: Literal["FIXED_RUNTIME_TERMINAL_RECEIPT_AND_CONTENT_VERIFIED"] = (
        "FIXED_RUNTIME_TERMINAL_RECEIPT_AND_CONTENT_VERIFIED"
    )


class RegisteredCmosDelayResult(VariableModel):
    source: DelayResultSource
    evaluation: CmosDelayResult
    vm_logic_physical_qualification: Literal["NOT_ASSESSED"] = "NOT_ASSESSED"
    new_simulations: Literal[0] = 0
    new_extractions: Literal[0] = 0
    new_reservations: Literal[0] = 0


class CmosDelayService:
    """Construct from an existing registered context, never a public provider/path input.

    The production NativeOperationService builds AuthenticatedOperatorProvider.
    Its analog_result authenticates the terminal receipt, registered reader,
    actual input/frame hashes and bounded samples. Numerical evaluation remains
    LOCAL_SAMPLED_EVIDENCE_ONLY/NOT_ATTESTED, even after that distinct boundary.
    """

    def __init__(self, context: ExecutionContext) -> None:
        self.native = NativeOperationService(context)

    def _record(self, query: CmosDelayResultQuery, record: DurableOperation) -> DurableOperation:
        record = DurableOperation.model_validate_json(record.model_dump_json())
        plan, context = record.plan, self.native.context
        if (record.operation_id, plan.plan_sha256) != (
            query.operation_id, query.expected_plan_sha256,
        ):
            raise OperationRejected("cmos_delay_operation_identity_mismatch")
        if (
            plan.resource_domain_sha256, plan.ledger_ref, plan.runner_sha256,
            plan.environment_sha256, plan.design_sha256, plan.pdk_sha256,
        ) != (
            context.resource_domain_sha256, context.binding.ledger_ref,
            context.binding.runner_sha256,
            context.binding.environment_sha256, context.binding.design_sha256,
            context.binding.pdk_sha256,
        ):
            raise OperationRejected("cmos_delay_context_mismatch")
        if record.progress.phase != "SUCCEEDED" or plan.analysis != "tran":
            raise OperationRejected("cmos_delay_succeeded_tran_required")
        return record

    async def result(self, query: CmosDelayResultQuery) -> RegisteredCmosDelayResult:
        query = CmosDelayResultQuery.model_validate_json(query.model_dump_json())
        native = self.native
        native.current()
        # Gate on an already terminal local record before reconcile: no nonterminal
        # lookup, journal advance, execution, extraction, admission or reservation.
        before = self._record(query, native.lifecycle.read(
            query.operation_id, query.expected_plan_sha256,
        ))
        record = self._record(query, await native.lifecycle.reconcile(
            query.operation_id, query.expected_plan_sha256,
        ))
        if record != before:
            raise OperationRejected("cmos_delay_terminal_changed")
        observed, data = await native.provider.analog_result(query.operation_id, record.plan)
        observed.check(record)
        if observed.progress != record.progress:
            raise OperationRejected("cmos_delay_terminal_mismatch")
        # Reuse the existing source/provenance/analysis-condition validation, and
        # snapshot provider data before using mutable nested collections.
        try:
            data = json.loads(json.dumps(data, allow_nan=False))
            report = make_report(record, data)
            if (
                data.get("remote_contact") is not True
                or data.get("originals_preserved") is not True
            ):
                raise OperationRejected("cmos_delay_provider_boundary_missing")
            evidence = DelayEvidence(
                operation_id=record.operation_id, plan_sha256=record.plan.plan_sha256,
                frame_sha256=report.frame_sha256,
                reader_registration_sha256=report.reader_registration_sha256,
                execution_input_sha256=report.execution_input_sha256,
                static_statements_sha256=report.analysis_conditions.static_statements_sha256,
            )
            if query.supply_signal not in data.get("tran_waveforms", {}):
                raise OperationRejected("missing_supply_evidence")
            request = CmosDelayRequest.model_validate_json(json.dumps({
                "evidence": evidence.model_dump(mode="json"),
                "definition": query.definition.model_dump(mode="json"),
                "tran_waveforms": data["tran_waveforms"],
            }, allow_nan=False))
            self._conditions(query, request, report.analysis_conditions.analysis_inputs)
            evaluation = evaluate_cmos_delay(request)
            terminal_receipt = record.progress.provider_receipt_sha256
            assert terminal_receipt is not None  # SUCCEEDED is validated by DurableOperation.
            source = DelayResultSource(
                evidence=evidence, measurement_id=report.measurement_id,
                extraction_receipt_sha256=report.extraction_receipt_sha256,
                terminal_receipt_sha256=terminal_receipt,
                conditions_sha256=canonical_digest(report.analysis_conditions),
                supply_signal=query.supply_signal,
            )
        except OperationRejected:
            raise
        except (KeyError, TypeError, ValueError):
            raise OperationRejected("cmos_delay_result_invalid") from None
        native.current()
        if self._record(query, native.lifecycle.read(
            query.operation_id, query.expected_plan_sha256,
        )) != record:
            raise OperationRejected("cmos_delay_terminal_changed")
        return RegisteredCmosDelayResult(source=source, evaluation=evaluation)

    @staticmethod
    def _conditions(
        query: CmosDelayResultQuery, request: CmosDelayRequest,
        inputs: object,
    ) -> None:
        from cadence_mcp_bridge.generic_ade import TranInputs

        if not isinstance(inputs, TranInputs):
            raise OperationRejected("cmos_delay_tran_conditions_required")
        waves, definition = request.tran_waveforms, request.definition
        if any(name not in waves for name in (definition.input_signal, definition.output_signal)):
            raise OperationRejected("cmos_delay_signal_evidence_missing")
        axis = [p.time_s for p in waves[definition.input_signal]]
        if any([p.time_s for p in wave] != axis for wave in waves.values()) or any(
            a >= b for a, b in zip(axis, axis[1:], strict=False)
        ):
            raise OperationRejected("cmos_delay_time_grid_mismatch")
        if axis[0] != 0 or not math.isclose(axis[-1], float(inputs.stop_s), rel_tol=1e-12):
            raise OperationRejected("cmos_delay_tran_interval_mismatch")
        if any(
            gap > float(inputs.maxstep_s)
            and not math.isclose(gap, float(inputs.maxstep_s), rel_tol=1e-12, abs_tol=0)
            for gap in (b - a for a, b in zip(axis, axis[1:], strict=False))
        ):
            raise OperationRejected("cmos_delay_tran_maxstep_mismatch")
        for window in (definition.phl_window, definition.plh_window):
            if window.start_s < axis[0] or window.stop_s > axis[-1]:
                raise OperationRejected("cmos_delay_window_outside_result")
            supply = [p.value_v for p in waves[query.supply_signal]
                      if window.start_s <= p.time_s <= window.stop_s]
            if len(supply) < definition.minimum_plateau_samples or any(
                abs(v - definition.vdd_v) > definition.plateau_tolerance_v for v in supply
            ) or max(supply) - min(supply) > definition.plateau_tolerance_v:
                raise OperationRejected("cmos_delay_supply_condition_mismatch")
