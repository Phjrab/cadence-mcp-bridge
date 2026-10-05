"""Read-only registered measurement projection; never submit, extract or mutate."""

from __future__ import annotations

from pydantic import ValidationError

from cadence_mcp_bridge.analyses import AnalysisJobQuery, AnalysisSelection
from cadence_mcp_bridge.analysis_service import AnalysisSupervisor
from cadence_mcp_bridge.designs import RegistryBase
from cadence_mcp_bridge.errors import InvalidInputError, RemoteFailureError
from cadence_mcp_bridge.native_diagnostics import NativeDiagnosticResult
from cadence_mcp_bridge.registered_measurements import (
    MeasurementDescription,
    MeasurementList,
    MeasurementProvenance,
    MeasurementQuery,
    MeasurementResult,
    MeasurementSelection,
    RegisteredMeasurement,
    definition,
)
from cadence_mcp_bridge.variable_contracts import canonical_digest


class MeasurementSupervisor:
    def __init__(self, registry: RegistryBase, analyses: AnalysisSupervisor) -> None:
        self.registry = registry
        self.analyses = analyses

    def contract(self, selection: MeasurementSelection) -> RegisteredMeasurement:
        contracts = self.registry.measurements_for(selection.design_id)
        contract = next(
            (c for c in contracts if c.measurement_id == selection.measurement_id), None
        )
        if contract is None:
            raise InvalidInputError("Measurement ID is not registered for this design")
        return contract

    def describe(self, selection: MeasurementSelection) -> MeasurementDescription:
        contract = self.contract(selection)
        plan = self.analyses.plan(
            AnalysisSelection(design_id=contract.design_id, analysis_id=contract.analysis_id)
        )
        compiled = contract.reader == "native-bounded-result-v1"
        eligible = compiled and plan.dispatch_eligible
        return MeasurementDescription(
            design_id=contract.design_id,
            measurement_id=contract.measurement_id,
            analysis_id=contract.analysis_id,
            contract_sha256=canonical_digest(contract),
            analysis_plan_hash=plan.plan_hash,
            definition=definition(contract.output_id) if contract.output_id is not None else None,
            read_eligible=eligible,
            qualification_scope="fixed_native_compatibility" if eligible else "unqualified",
            blocking_reason=(
                None
                if eligible
                else "reader_unqualified"
                if not compiled
                else "analysis_unqualified"
            ),
        )

    def listing(self, design_id: str) -> MeasurementList:
        profile = self.registry.profile(design_id)
        return MeasurementList(
            design_id=design_id,
            declared_measurements=profile.allowed_measurements,
            measurements=tuple(
                self.describe(
                    MeasurementSelection(design_id=design_id, measurement_id=c.measurement_id)
                )
                for c in self.registry.measurements_for(design_id)
            ),
        )

    async def result(self, query: MeasurementQuery) -> MeasurementResult:
        contract = self.contract(query)
        description = self.describe(query)
        if query.expected_contract_sha256 != description.contract_sha256:
            raise InvalidInputError("Measurement contract does not match the current registry")
        if not description.read_eligible or contract.output_id is None:
            raise InvalidInputError("Registered measurement reader is unqualified")
        # The existing analysis path requires durable admission and PDK/native identity checks.
        try:
            result = await self.analyses.result(
                AnalysisJobQuery(
                    design_id=query.design_id,
                    analysis_id=contract.analysis_id,
                    operation_id=query.operation_id,
                )
            )
            native = NativeDiagnosticResult.model_validate(result.native.model_dump())
        except ValidationError:
            raise RemoteFailureError("Measurement source result failed qualification") from None
        provenance = MeasurementProvenance(
            analysis_plan_hash=result.plan_hash,
            analysis_contract_sha256=contract.analysis_contract_sha256,
            definition_sha256=canonical_digest(definition(contract.output_id)),
            revision_id=native.revision_id,
            operating_point_id=native.operating_point_id,
            settings=native.settings,
            native_result_sha256=canonical_digest(native),
            warnings=native.warnings,
            notices=native.notices,
            **{
                name: getattr(native, name)
                for name in (
                    "source_sha256",
                    "copy_sha256",
                    "state_sha256",
                    "model_sha256",
                    "circuit_sha256",
                    "input_sha256",
                    "owned_variables_sha256",
                    "psf_sha256",
                    "measurement_frame_sha256",
                )
            },
        )
        return MeasurementResult(
            design_id=query.design_id,
            measurement_id=query.measurement_id,
            analysis_id=contract.analysis_id,
            operation_id=query.operation_id,
            contract_sha256=description.contract_sha256,
            definition=definition(contract.output_id),
            provenance=provenance,
            scalars=native.scalars,
            spectrum=native.spectrum,
            transient=native.transient,
        )
