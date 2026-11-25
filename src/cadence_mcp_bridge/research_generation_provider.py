"""Fixed host custody for the registered research-generation worker."""

from __future__ import annotations

import base64
import json
import os
import time
from importlib.resources import files
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal

from pydantic import Field, JsonValue

from cadence_mcp_bridge.amplifier_pm0_service import _fixed_guest
from cadence_mcp_bridge.domain_provisioning import _canonical, _closed_document
from cadence_mcp_bridge.generic_ade import LIMIT as ADE_INPUT_LIMIT
from cadence_mcp_bridge.native_diagnostics import OperationId
from cadence_mcp_bridge.native_runtime import KIND, NativeLibrary, RemotePath
from cadence_mcp_bridge.onboarding import _local_path
from cadence_mcp_bridge.operator_confirmation import _ssh
from cadence_mcp_bridge.operator_operations import OperationRejected
from cadence_mcp_bridge.operator_transport import run_fixed
from cadence_mcp_bridge.pmos_default_service import _read, _retain, _sha
from cadence_mcp_bridge.research_bench import BenchNetlistConditions, ResearchBenchPlan
from cadence_mcp_bridge.research_circuit import MosBlockStageReceipt, OwnedMosBlockPlan
from cadence_mcp_bridge.research_generation_service import (
    Phase,
    RegisteredResearchGeneration,
    ResearchGenerationBinding,
    ResearchGenerationCapture,
    ResearchGenerationProgress,
    ResearchGenerationQuery,
)
from cadence_mcp_bridge.runtime_context import ExecutionContext, resource_lock
from cadence_mcp_bridge.ssh_backend import OpenSshBackend
from cadence_mcp_bridge.variable_contracts import Digest, VariableModel, canonical_digest

_PHASES: tuple[Phase, ...] = ("save", "reopen", "netlist")
_DOCUMENT_LIMIT = 262_144
_MARKER_LIMIT = 65_536
_WIRE_LIMIT = 1_048_576
_GUEST_ASSET = "_research_generation_worker.py"
_CLAIM = "generation-intent.private.json"
_CAPTURE_SUFFIXES = (
    "intent.private.json",
    "stdout.private.json",
    "stderr.private.txt",
    "transport.private.json",
)


class _Registration(VariableModel):
    schema_version: Literal[1]
    binding: ResearchGenerationBinding
    binding_sha256: Digest
    authority_sha256: Digest
    guest_sha256: Digest
    cdf_sha256: Annotated[tuple[Digest, ...], Field(min_length=1, max_length=32)]


class _Authority(VariableModel):
    operation_id: OperationId
    binding_sha256: Digest
    scope_sha256: Digest
    approved_phases: tuple[Literal["save"], Literal["reopen"], Literal["netlist"]]
    valid_until_unix: Annotated[int, Field(gt=0)]


class _Capture(VariableModel):
    binding_sha256: Digest
    scope_sha256: Digest
    program_sha256: Digest
    previous_receipt_sha256: Digest | None
    receipt: MosBlockStageReceipt
    stdout_base64: str
    dut_netlist_base64: str
    full_netlist_base64: str


class _GenerationTrees(VariableModel):
    library: Digest
    strict_library: Digest
    dut: Digest
    bench: Digest
    state: Digest


class _GenerationProtection(VariableModel):
    source: Digest
    state: Digest
    protected: Digest
    retained_jobs_sha256: Digest
    counter: dict[str, JsonValue]
    ledger_records_sha256: Digest


class _NetlistPhaseEvidence(VariableModel):
    receipt: MosBlockStageReceipt
    scope_sha256: Digest
    previous_receipt_sha256: Digest
    protected: _GenerationProtection
    trees: _GenerationTrees
    ocean_calls: Literal[1]
    simulations: Literal[0]
    reservations: Literal[0]
    output_sha256: Digest
    dut_sha256: Digest


class ResearchGenerationAnalysisSource(VariableModel):
    """Verified source identities for a separately authorized analysis registration."""

    operation_id: OperationId
    registration_file_sha256: Digest
    binding_sha256: Digest
    handoff_sha256: Digest
    netlist_receipt_sha256: Digest
    native_phase_record_sha256: Digest
    native_completion_sha256: Digest
    native_manifest_sha256: Digest
    conditions_sha256: Digest
    library: NativeLibrary
    strict_library_tree_sha256: Digest
    source_cell: RemotePath
    source_tree_sha256: Digest
    ade_state: RemotePath
    ade_state_tree_sha256: Digest
    full_netlist_sha256: Digest
    static_statements_sha256: Digest
    execution_authorized: Literal[False] = False


def _artifact(encoded: str, limit: int) -> bytes:
    if len(encoded) > 4 * ((limit + 2) // 3):
        raise OperationRejected("research_generation_artifact_limit")
    raw = base64.b64decode(encoded, validate=True)
    if len(raw) > limit:
        raise OperationRejected("research_generation_artifact_limit")
    return raw


class _FixedResearchGenerationProvider:
    def __init__(
        self,
        context: ExecutionContext,
        directory: Path,
        registration: _Registration,
    ) -> None:
        self._context = context
        self._directory = directory
        self._registration = registration
        self._owns_claim = False

    def _check(self, binding: ResearchGenerationBinding) -> None:
        if binding != self._registration.binding:
            raise OperationRejected("research_generation_claim_conflict")

    def _claim_bytes(self, binding: ResearchGenerationBinding) -> bytes:
        return _canonical(
            {
                "binding_sha256": self._registration.binding_sha256,
                "operation_id": binding.operation_id,
                "scope_sha256": binding.scope_sha256,
                "retry": False,
            }
        )

    def _phase_file(self, phase: Phase, suffix: str) -> Path:
        return self._directory / f"generation-{phase}-{suffix}"

    def _program_sha(self, binding: ResearchGenerationBinding, phase: Phase) -> str:
        return {
            "save": binding.save_program_sha256,
            "reopen": binding.reopen_program_sha256,
            "netlist": binding.netlist_program_sha256,
        }[phase]

    def _phase_intent(
        self,
        binding: ResearchGenerationBinding,
        phase: Phase,
        prior: str | None,
    ) -> bytes:
        return _canonical(
            {
                "claim_sha256": _sha(self._claim_bytes(binding)),
                "phase": phase,
                "program_sha256": self._program_sha(binding, phase),
                "previous_receipt_sha256": prior,
                "retry": False,
            }
        )

    def _decode_capture(
        self,
        binding: ResearchGenerationBinding,
        phase: Phase,
        prior: str | None,
        raw: bytes,
    ) -> ResearchGenerationCapture:
        _closed_document(raw, max_bytes=_WIRE_LIMIT)
        envelope = _Capture.model_validate_json(raw)
        receipt = envelope.receipt
        program = self._program_sha(binding, phase)
        if (
            envelope.binding_sha256 != self._registration.binding_sha256
            or envelope.scope_sha256 != binding.scope_sha256
            or envelope.program_sha256 != program
            or envelope.previous_receipt_sha256 != prior
            or (receipt.operation_id, receipt.plan_sha256, receipt.phase)
            != (binding.operation_id, binding.plan_sha256, phase)
            or (receipt.library.name, receipt.library.path)
            != (binding.output_library, binding.owned_library_path)
            or receipt.script_sha256 != (None if phase == "netlist" else program)
        ):
            raise OperationRejected("research_generation_capture_binding")
        stdout = _artifact(envelope.stdout_base64, _MARKER_LIMIT)
        dut = _artifact(envelope.dut_netlist_base64, ADE_INPUT_LIMIT)
        full = _artifact(envelope.full_netlist_base64, ADE_INPUT_LIMIT)
        if phase == "netlist":
            valid = (
                not stdout and bool(dut) and bool(full) and _sha(full) == receipt.artifact_sha256
            )
        else:
            valid = (
                bool(stdout) and not dut and not full and _sha(stdout) == receipt.artifact_sha256
            )
        if not valid:
            raise OperationRejected("research_generation_capture_artifact")
        return ResearchGenerationCapture(
            binding.scope_sha256, program, prior, receipt, stdout, dut, full
        )

    @staticmethod
    def _transport_record(code: int, out: bytes, err: bytes) -> bytes:
        return _canonical(
            {
                "exit_code": code,
                "stdout_sha256": _sha(out),
                "stdout_bytes": len(out),
                "stderr_sha256": _sha(err),
                "stderr_bytes": len(err),
            }
        )

    def lookup(self, binding: ResearchGenerationBinding) -> ResearchGenerationProgress | None:
        self._check(binding)
        path = self._directory / _CLAIM
        if not os.path.lexists(path):
            if any(
                os.path.lexists(self._phase_file(phase, suffix))
                for phase in _PHASES
                for suffix in _CAPTURE_SUFFIXES
            ):
                raise OperationRejected("research_generation_orphan_capture")
            return None
        try:
            claim = _read(path, 4096)
        except (OSError, ValueError):
            return ResearchGenerationProgress(self._registration.binding_sha256)
        if claim != self._claim_bytes(binding):
            raise OperationRejected("research_generation_claim_conflict")
        captures: list[ResearchGenerationCapture] = []
        prior = None
        for phase in _PHASES:
            try:
                if _read(self._phase_file(phase, _CAPTURE_SUFFIXES[0]), 4096) != self._phase_intent(
                    binding,
                    phase,
                    prior,
                ):
                    break
                out = _read(self._phase_file(phase, _CAPTURE_SUFFIXES[1]), _WIRE_LIMIT)
                err = _read(self._phase_file(phase, _CAPTURE_SUFFIXES[2]), _WIRE_LIMIT)
                record = _read(self._phase_file(phase, _CAPTURE_SUFFIXES[3]), 4096)
                if err or record != self._transport_record(0, out, err):
                    break
                capture = self._decode_capture(binding, phase, prior, out)
            except (OSError, ValueError):
                break
            captures.append(capture)
            prior = canonical_digest(capture.receipt)
        return ResearchGenerationProgress(self._registration.binding_sha256, tuple(captures))

    def _inputs(self, binding: ResearchGenerationBinding) -> tuple[bytes, bytes, bytes]:
        scope = _read(
            self._directory / "execution-scope.private.json", _DOCUMENT_LIMIT, binding.scope_sha256
        )
        _closed_document(scope, max_bytes=_DOCUMENT_LIMIT)
        authority = _read(
            self._directory / "c0-exact-ack.private.json", 4096, self._registration.authority_sha256
        )
        _closed_document(authority, max_bytes=4096)
        ack = _Authority.model_validate_json(authority)
        if (ack.operation_id, ack.binding_sha256, ack.scope_sha256) != (
            binding.operation_id,
            self._registration.binding_sha256,
            binding.scope_sha256,
        ) or time.time() >= ack.valid_until_unix:
            raise OperationRejected("research_generation_exact_authority")
        with files("cadence_mcp_bridge").joinpath(_GUEST_ASSET).open("rb") as stream:
            guest = stream.read(_DOCUMENT_LIMIT + 1)
        if not 0 < len(guest) <= _DOCUMENT_LIMIT or _sha(guest) != self._registration.guest_sha256:
            raise OperationRejected("research_generation_fixed_asset_digest")
        return scope, authority, guest

    def claim(self, binding: ResearchGenerationBinding) -> bool:
        self._check(binding)
        with resource_lock(self._context):
            if self.lookup(binding) is not None:
                return False
            self._inputs(binding)
            for phase in _PHASES:
                self._program(binding, phase)
            _retain(self._directory / _CLAIM, self._claim_bytes(binding))
            self._owns_claim = True
        return True

    def _program(self, binding: ResearchGenerationBinding, phase: Phase) -> bytes:
        program = _read(
            self._directory / f"{phase}-program.private",
            _DOCUMENT_LIMIT,
            self._program_sha(binding, phase),
        )
        if not program or not program.isascii():
            raise OperationRejected("research_generation_program_invalid")
        return program

    def run_phase(
        self,
        binding: ResearchGenerationBinding,
        phase: Phase,
        previous_receipt_sha256: Digest | None,
    ) -> ResearchGenerationCapture:
        self._check(binding)
        with resource_lock(self._context):
            prior = self.lookup(binding)
            if not self._owns_claim or prior is None or len(prior.captures) != _PHASES.index(phase):
                raise OperationRejected("research_generation_phase_claim_required")
            expected = canonical_digest(prior.captures[-1].receipt) if prior.captures else None
            if previous_receipt_sha256 != expected or any(
                os.path.lexists(self._phase_file(phase, suffix)) for suffix in _CAPTURE_SUFFIXES
            ):
                raise OperationRejected("research_generation_phase_already_claimed_or_mismatched")
            scope, authority, guest = self._inputs(binding)
            program = self._program(binding, phase)
            payload = guest + _canonical(
                {
                    "managed_root": self._context.contracts.environment.paths.managed_root,
                    "binding": binding.model_dump(mode="json"),
                    **{
                        f"{name}_base64": base64.b64encode(raw).decode("ascii")
                        for name, raw in (
                            ("scope", scope),
                            ("authority", authority),
                            ("program", program),
                        )
                    },
                }
            )
            argv = _ssh(self._context.contracts.environment) + [
                "-c",
                _fixed_guest(guest),
                binding.scope_sha256,
                phase,
                previous_receipt_sha256 or "''",
            ]
            _retain(
                self._phase_file(phase, _CAPTURE_SUFFIXES[0]),
                self._phase_intent(binding, phase, expected),
            )
            transport = self._phase_file(phase, _CAPTURE_SUFFIXES[3])
            try:
                code, out, err = run_fixed(
                    argv, payload, OpenSshBackend._ssh_environment(), timeout=60, limit=_WIRE_LIMIT
                )
            except (OSError, ValueError) as exc:
                _retain(
                    transport,
                    _canonical(
                        {"status": "TRANSPORT_FAILED_RETAINED", "error_type": type(exc).__name__}
                    ),
                )
                raise
            _retain(self._phase_file(phase, _CAPTURE_SUFFIXES[1]), out)
            _retain(self._phase_file(phase, _CAPTURE_SUFFIXES[2]), err)
            _retain(transport, self._transport_record(code, out, err))
            if code != 0 or err:
                raise OperationRejected("research_generation_native_result_unverified")
            return self._decode_capture(binding, phase, expected, out)


def registered_research_generation(
    context: ExecutionContext,
    raw: bytes,
    directory: Path,
) -> RegisteredResearchGeneration:
    """Load one trusted, digest-pinned host registration and its fixed directory."""
    _closed_document(raw, max_bytes=_DOCUMENT_LIMIT)
    registration = _Registration.model_validate_json(raw)
    binding = registration.binding
    directory = _local_path(directory)
    library = PurePosixPath(binding.owned_library_path)
    workspace = PurePosixPath(context.contracts.environment.paths.workspace_root)
    managed = PurePosixPath(context.contracts.environment.paths.managed_root)
    if (
        not directory.is_dir()
        or library.name != binding.output_library
        or not library.is_relative_to(workspace)
        or library.is_relative_to(managed)
        or (binding.context_id, binding.resource_domain_sha256, binding.native_manifest_sha256)
        != (
            context.binding.context_id,
            context.resource_domain_sha256,
            context.binding.runner_sha256,
        )
        or canonical_digest(binding) != registration.binding_sha256
        or len(set(registration.cdf_sha256)) != len(registration.cdf_sha256)
    ):
        raise OperationRejected("research_generation_host_registration_mismatch")
    plan = OwnedMosBlockPlan.model_validate_json(
        _read(directory / "plan.private.json", _DOCUMENT_LIMIT, binding.plan_sha256)
    )
    bench = ResearchBenchPlan.model_validate_json(
        _read(directory / "bench-plan.private.json", _DOCUMENT_LIMIT, binding.bench_plan_sha256)
    )
    conditions = BenchNetlistConditions.model_validate_json(
        _read(directory / "conditions.private.json", _DOCUMENT_LIMIT, binding.conditions_sha256)
    )
    cdf = {
        pin: _read(directory / f"cdf-{pin}.private", _MARKER_LIMIT, pin)
        for pin in registration.cdf_sha256
    }
    return RegisteredResearchGeneration(
        binding,
        plan,
        bench,
        conditions,
        cdf,
        _FixedResearchGenerationProvider(context, directory, registration),
        expected_binding_sha256=registration.binding_sha256,
    )


def registered_generation_analysis_source(
    context: ExecutionContext,
    registration_raw: bytes,
    directory: Path,
    query: ResearchGenerationQuery,
    phase_record: bytes,
    completion: bytes,
    *,
    runtime_manifest: bytes,
    runtime_registration: bytes,
    expected_registration_file_sha256: Digest,
    expected_phase_record_sha256: Digest,
    expected_completion_sha256: Digest,
) -> ResearchGenerationAnalysisSource:
    """Join independently pinned guest custody to the host's retained handoff, locally."""
    if (
        _sha(registration_raw) != expected_registration_file_sha256
        or _sha(phase_record) != expected_phase_record_sha256
        or _sha(completion) != expected_completion_sha256
    ):
        raise OperationRejected("research_generation_native_custody_digest")
    service = registered_research_generation(context, registration_raw, directory)
    handoff = service.registration_handoff(query)
    registration = _Registration.model_validate_json(registration_raw)
    binding = registration.binding
    directory = _local_path(directory)
    provider = _FixedResearchGenerationProvider(context, directory, registration)
    _closed_document(phase_record, max_bytes=8192)
    record = _NetlistPhaseEvidence.model_validate_json(phase_record)
    scope_raw = _read(
        directory / "execution-scope.private.json",
        _DOCUMENT_LIMIT,
        binding.scope_sha256,
    )
    _closed_document(scope_raw, max_bytes=_DOCUMENT_LIMIT)
    scope = json.loads(scope_raw)
    _closed_document(runtime_manifest, max_bytes=_DOCUMENT_LIMIT)
    _closed_document(runtime_registration, max_bytes=_DOCUMENT_LIMIT)
    manifest = json.loads(runtime_manifest)
    compiled = json.loads(runtime_registration)
    compiled_sha = _sha(runtime_registration)
    if (
        _sha(runtime_manifest) != binding.native_manifest_sha256
        or manifest["schema_version"] != 3
        or manifest["kind"] != KIND
        or manifest["profile_sha256"] != context.binding.environment_sha256
        or manifest["registration_sha256"] != compiled_sha
        or manifest["files"]["registration.json"]
        != {"sha256": compiled_sha, "bytes": len(runtime_registration)}
        or compiled["schema_version"] != 1
        or compiled["identity_manifest_sha256"] != scope.get("identity_manifest_sha256")
        or (compiled["environment_sha256"], compiled["design_sha256"], compiled["pdk_sha256"])
        != (
            context.binding.environment_sha256,
            context.binding.design_sha256,
            context.binding.pdk_sha256,
        )
    ):
        raise OperationRejected("research_generation_seed_runtime_mismatch")
    route_id = scope["source_route"]
    seeds = [
        route
        for route in compiled["routes"]
        if (route["design_id"], route["analysis_id"])
        == (route_id["design_id"], route_id["analysis_id"])
    ]
    if len(seeds) != 1:
        raise OperationRejected("research_generation_seed_route_mismatch")
    seed = seeds[0]["ade"]
    pins = handoff.pins
    intent = provider._phase_intent(binding, "netlist", pins.reopen_receipt_sha256)
    protection = record.protected
    if (
        completion
        != _canonical(
            {
                "intent_sha256": _sha(intent),
                "receipt_sha256": expected_phase_record_sha256,
            }
        )
        or phase_record != _canonical(record.model_dump(mode="json"))
        or canonical_digest(record.receipt) != pins.netlist_receipt_sha256
        or record.scope_sha256 != binding.scope_sha256
        or record.previous_receipt_sha256 != pins.reopen_receipt_sha256
        or record.dut_sha256 != pins.raw_netlist_sha256
        or record.trees.library != handoff.library.tree_sha256
        or record.trees.dut != handoff.source_tree_sha256
        or record.trees.bench != handoff.bench_tree_sha256
        or protection.source != seed["source_tree_sha256"]
        or protection.state != seed["ade_state_tree_sha256"]
        or protection.protected != scope.get("protected_sha256")
        or protection.retained_jobs_sha256 != scope.get("retained_jobs_sha256")
        or _canonical(protection.counter) != _canonical(scope.get("counter"))
        or protection.ledger_records_sha256 != scope.get("ledger_records_sha256")
    ):
        raise OperationRejected("research_generation_native_custody_mismatch")
    library = PurePosixPath(handoff.library.path)
    ade_state = library.parent / (PurePosixPath(handoff.bench_cell).name + "_ADE")
    return ResearchGenerationAnalysisSource(
        operation_id=binding.operation_id,
        registration_file_sha256=expected_registration_file_sha256,
        binding_sha256=registration.binding_sha256,
        handoff_sha256=handoff.handoff_sha256,
        netlist_receipt_sha256=pins.netlist_receipt_sha256,
        native_phase_record_sha256=expected_phase_record_sha256,
        native_completion_sha256=expected_completion_sha256,
        native_manifest_sha256=binding.native_manifest_sha256,
        conditions_sha256=binding.conditions_sha256,
        library=handoff.library,
        strict_library_tree_sha256=record.trees.strict_library,
        source_cell=handoff.bench_cell,
        source_tree_sha256=handoff.bench_tree_sha256,
        ade_state=str(ade_state),
        ade_state_tree_sha256=record.trees.state,
        full_netlist_sha256=pins.full_netlist_sha256,
        static_statements_sha256=handoff.static_statements_sha256,
    )
