"""Prepare the local inputs of an operator-registered research generation."""

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from pathlib import PurePosixPath
from typing import Annotated, Literal

from pydantic import Field

from cadence_mcp_bridge.domain_provisioning import _canonical
from cadence_mcp_bridge.native_runtime import RemotePath
from cadence_mcp_bridge.research_adapters import ResearchMosBlockRequest
from cadence_mcp_bridge.research_bench import (
    BenchNetlistConditions,
    _check_bench_conditions,
    plan_research_bench,
    render_research_bench,
)
from cadence_mcp_bridge.research_circuit import plan_owned_mos_block
from cadence_mcp_bridge.variable_contracts import (
    BindingName,
    Digest,
    VariableModel,
    canonical_digest,
)

# Match the bounds on the generation provider's local registration inputs.
_DOCUMENT_LIMIT = 262_144
_EVIDENCE_LIMIT = 65_536


class ResearchGenerationPreparationRequest(ResearchMosBlockRequest):
    owned_library_path: RemotePath
    conditions: BenchNetlistConditions
    expected_conditions_sha256: Digest
    evidence_sha256: Annotated[tuple[Digest, ...], Field(min_length=1, max_length=32)]
    expected_plan_sha256: Digest | None = None
    primitive_cdf_sha256: Digest | None = None
    signed_ac_evidence_sha256: Digest | None = None
    signed_ac_vsin_pair: bool = False


class ResearchGenerationPreparationManifest(VariableModel):
    schema_version: Literal[1] = 1
    status: Literal["LOCAL_GENERATION_PREPARED"] = "LOCAL_GENERATION_PREPARED"
    execution_authorized: Literal[False] = False
    remote_contact: Literal[False] = False
    output_library: BindingName
    owned_library_path: RemotePath
    definition_sha256: Digest
    plan_sha256: Digest
    bench_plan_sha256: Digest
    conditions_sha256: Digest
    cdf_sha256: tuple[Digest, ...]
    save_program_sha256: Digest
    reopen_program_sha256: Digest
    save_markers: tuple[str, ...]
    reopen_markers: tuple[str, ...]


@dataclass(frozen=True)
class ResearchGenerationPreparation:
    manifest: ResearchGenerationPreparationManifest
    files: Mapping[str, bytes]


def prepare_research_generation(
    request: ResearchGenerationPreparationRequest,
    evidence: Mapping[str, bytes],
) -> ResearchGenerationPreparation:
    """Build canonical registration inputs without selecting a runtime or touching disk."""
    request = ResearchGenerationPreparationRequest.model_validate_json(request.model_dump_json())
    pins = set(request.evidence_sha256)
    if pins != set(evidence) or len(pins) != len(request.evidence_sha256):
        raise ValueError("research generation evidence inventory mismatch")
    for pin, raw in evidence.items():
        if type(raw) is not bytes or not 0 < len(raw) <= _EVIDENCE_LIMIT:
            raise ValueError("research generation evidence size or type mismatch")
        if sha256(raw).hexdigest() != pin:
            raise ValueError("research generation evidence digest mismatch")
    conditions_pin = canonical_digest(request.conditions)
    if conditions_pin != request.expected_conditions_sha256:
        raise ValueError("research generation conditions digest mismatch")
    if PurePosixPath(request.owned_library_path).name != request.output_library:
        raise ValueError("research generation path and library name mismatch")
    dut = plan_owned_mos_block(
        request.definition,
        expected_binding=request.expected_binding,
        expected_definition_sha256=request.expected_definition_sha256,
        output_library=request.output_library,
    )
    plan_pin = canonical_digest(dut)
    if request.expected_plan_sha256 is not None and plan_pin != request.expected_plan_sha256:
        raise ValueError("research generation reviewed plan digest mismatch")
    bench = plan_research_bench(
        request.definition,
        dut,
        expected_definition_sha256=request.expected_definition_sha256,
        expected_dut_plan_sha256=plan_pin,
        primitive_cdf_sha256=request.primitive_cdf_sha256,
        signed_ac_evidence_sha256=request.signed_ac_evidence_sha256,
        signed_ac_vsin_pair=request.signed_ac_vsin_pair,
    )
    _check_bench_conditions(bench, request.conditions)
    bench_pin = canonical_digest(bench)
    scripts = render_research_bench(
        bench,
        dut,
        evidence,
        expected_plan_sha256=bench_pin,
        owned_library_path=request.owned_library_path,
    )
    files = {
        "definition.private.json": _canonical(request.definition.model_dump(mode="json")),
        "plan.private.json": _canonical(dut.model_dump(mode="json")),
        "bench-plan.private.json": _canonical(bench.model_dump(mode="json")),
        "conditions.private.json": _canonical(request.conditions.model_dump(mode="json")),
        "save-program.private": scripts.generate.encode("ascii"),
        "reopen-program.private": scripts.reopen.encode("ascii"),
    }
    if any(len(raw) > _DOCUMENT_LIMIT for raw in files.values()):
        raise ValueError("research generation registration input exceeds provider bound")
    manifest = ResearchGenerationPreparationManifest(
        output_library=request.output_library,
        owned_library_path=request.owned_library_path,
        definition_sha256=request.expected_definition_sha256,
        plan_sha256=plan_pin,
        bench_plan_sha256=bench_pin,
        conditions_sha256=conditions_pin,
        cdf_sha256=tuple(sorted(pins)),
        save_program_sha256=sha256(files["save-program.private"]).hexdigest(),
        reopen_program_sha256=sha256(files["reopen-program.private"]).hexdigest(),
        save_markers=scripts.save_markers,
        reopen_markers=scripts.reopen_markers,
    )
    files.update({f"cdf-{pin}.private": evidence[pin] for pin in manifest.cdf_sha256})
    files["preparation.private.json"] = _canonical(manifest.model_dump(mode="json"))
    return ResearchGenerationPreparation(manifest, files)
