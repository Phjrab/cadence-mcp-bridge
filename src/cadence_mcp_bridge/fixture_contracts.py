"""Closed passive fixture contracts; neither OA nor a physical PDK is involved."""

from typing import Literal

from cadence_mcp_bridge.profiles import FIXTURE_PROFILE
from cadence_mcp_bridge.variable_contracts import Digest, LogicalId, VariableModel, canonical_digest


class FixtureAnalysis(VariableModel):
    design_id: LogicalId
    analysis_id: LogicalId
    analysis: Literal["tran"] = "tran"
    design_profile_sha256: Digest
    variable_set_sha256: Digest
    adapter_kind: Literal["fixture-rc-profile-v1"] = "fixture-rc-profile-v1"
    adapter_contract_sha256: Digest
    # The v1 fixed-native analysis interface cannot accept fixture parameters.
    input_policy: Literal["unqualified"] = "unqualified"


class FixtureMeasurement(VariableModel):
    contract_version: Literal[1] = 1
    design_id: LogicalId
    measurement_id: LogicalId
    analysis_id: LogicalId
    analysis_contract_sha256: Digest
    reader: Literal["fixture-completion-v1"] = "fixture-completion-v1"
    output_id: Literal[None] = None
    definition_sha256: Digest


class CompletionDefinition(VariableModel):
    definition_id: Literal["fixture-completion-v1"] = "fixture-completion-v1"
    quantity: Literal["verified_simulator_completion"] = "verified_simulator_completion"
    unit: Literal["1"] = "1"
    effective_inputs_required: Literal[True] = True
    analog_measurement: Literal[False] = False


def fixture_digest() -> str:
    return canonical_digest(FIXTURE_PROFILE)


def completion_digest() -> str:
    return canonical_digest(CompletionDefinition())
