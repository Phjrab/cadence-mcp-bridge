"""Local source evidence from a retained fixed-DC netlist with no phase completion."""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from typing import Literal

from cadence_mcp_bridge._native_rendering import partition_input, static_fingerprint
from cadence_mcp_bridge._research_generation_worker import MARKER_PREFIXES, dut_projection
from cadence_mcp_bridge.domain_provisioning import _canonical, _closed_document
from cadence_mcp_bridge.generic_ade import LIMIT as ADE_INPUT_LIMIT
from cadence_mcp_bridge.native_diagnostics import OperationId
from cadence_mcp_bridge.native_runtime import NativeLibrary, RemotePath
from cadence_mcp_bridge.onboarding import _local_path
from cadence_mcp_bridge.operator_operations import OperationRejected
from cadence_mcp_bridge.pmos_default_service import _read, _sha
from cadence_mcp_bridge.research_bench import BenchNetlistConditions, ResearchBenchPlan
from cadence_mcp_bridge.research_circuit import OwnedMosBlockPlan
from cadence_mcp_bridge.research_generation_provider import (
    _DOCUMENT_LIMIT,
    _MARKER_LIMIT,
    _PHASES,
    _WIRE_LIMIT,
    _artifact,
    _FixedResearchGenerationProvider,
    _generation_seed,
    _GenerationProtection,
    _GenerationTrees,
    _NativePhaseEvidence,
    _Registration,
    registered_research_generation,
)
from cadence_mcp_bridge.research_generation_service import ResearchGenerationQuery
from cadence_mcp_bridge.runtime_context import ExecutionContext
from cadence_mcp_bridge.variable_contracts import Digest, VariableModel, canonical_digest


class _ObservedStage(VariableModel):
    records: dict[str, str]
    stdout_base64: str | None
    stdout_sha256: Digest


class _RetainedPhases(VariableModel):
    save: _ObservedStage
    reopen: _ObservedStage
    netlist: _ObservedStage


class _RecoveryEnrollment(VariableModel):
    """Independently selected host pins, separate from the original generation enrollment."""

    schema_version: Literal[1]
    registration_file_sha256: Digest
    binding_sha256: Digest
    locked_witness_sha256: Digest
    nominal_input_sha256: Digest
    retained_input_sha256: Digest
    dut_input_sha256: Digest


class RecoveredGenerationAnalysisSource(VariableModel):
    """Local registration input with no original netlist terminal or execution authority."""

    status: Literal["LOCAL_RETAINED_NETLIST_SOURCE_VERIFIED"] = (
        "LOCAL_RETAINED_NETLIST_SOURCE_VERIFIED"
    )
    generation_status: Literal["OUTCOME_UNKNOWN"] = "OUTCOME_UNKNOWN"
    execution_authorized: Literal[False] = False
    operation_id: OperationId
    binding_sha256: Digest
    scope_sha256: Digest
    recovery_enrollment_sha256: Digest
    locked_witness_sha256: Digest
    reopen_receipt_sha256: Digest
    netlist_failure_sha256: Digest
    expected_statements_sha256: Digest
    equivalence_sha256: Digest
    full_netlist_sha256: Digest
    raw_dut_netlist_sha256: Digest
    static_statements_sha256: Digest
    conditions_sha256: Digest
    native_manifest_sha256: Digest
    runtime_registration_sha256: Digest
    library: NativeLibrary
    strict_library_tree_sha256: Digest
    source_cell: RemotePath
    source_tree_sha256: Digest
    ade_state: RemotePath
    ade_state_tree_sha256: Digest


def recover_retained_generation_source(
    context: ExecutionContext,
    registration_raw: bytes,
    directory: Path,
    query: ResearchGenerationQuery,
    *,
    recovery_enrollment: bytes,
    expected_recovery_enrollment_sha256: Digest,
    locked_witness: bytes,
    runtime_manifest: bytes,
    runtime_registration: bytes,
    nominal_input: bytes,
    retained_input: bytes,
) -> RecoveredGenerationAnalysisSource:
    """Verify a bounded locked observation and original host captures without dispatch."""
    from cadence_mcp_bridge.research_bench import verify_fixed_dc_bench_netlist_equivalence

    _closed_document(recovery_enrollment, max_bytes=4096)
    enrollment = _RecoveryEnrollment.model_validate_json(recovery_enrollment)
    if (
        _sha(recovery_enrollment) != expected_recovery_enrollment_sha256
        or _sha(registration_raw) != enrollment.registration_file_sha256
        or _sha(locked_witness) != enrollment.locked_witness_sha256
        or _sha(nominal_input) != enrollment.nominal_input_sha256
        or _sha(retained_input) != enrollment.retained_input_sha256
    ):
        raise OperationRejected("research_generation_recovery_enrollment_mismatch")
    _closed_document(locked_witness, max_bytes=_DOCUMENT_LIMIT)
    witness = json.loads(locked_witness)
    observed = witness["netlist_observation"]
    phases = _RetainedPhases.model_validate_json(_canonical(observed["original_proof"]))
    trees = _GenerationTrees.model_validate_json(_canonical(observed["trees"]))
    directory = _local_path(directory)
    service = registered_research_generation(context, registration_raw, directory)
    original = service.status(query)
    registration = _Registration.model_validate_json(registration_raw)
    binding = registration.binding
    if (
        original.status != "OUTCOME_UNKNOWN"
        or original.completed_phases != ("save", "reopen")
        or original.handoff_sha256 is not None
        or enrollment.binding_sha256 != registration.binding_sha256
        or witness["status"] != "RESIDUAL_NON_OTA_PRECHECK"
        or any(
            type(witness[key]) is not int or witness[key] != 0
            for key in (
                "vm_writes",
                "ocean_calls",
                "simulations",
                "reservations",
            )
        )
        or _artifact(observed["runtime_manifest_base64"], _DOCUMENT_LIMIT) != runtime_manifest
        or observed["compiled_registration_sha256"] != _sha(runtime_registration)
        or observed["compiled_registration_bytes"] != len(runtime_registration)
        or observed["input"]["sha256"] != enrollment.retained_input_sha256
        or _artifact(observed["input_base64"], ADE_INPUT_LIMIT) != retained_input
        or observed["stderr"]["sha256"] != _sha(b"")
    ):
        raise OperationRejected("research_generation_recovery_binding_mismatch")

    scope_raw = _read(
        directory / "execution-scope.private.json",
        _DOCUMENT_LIMIT,
        binding.scope_sha256,
    )
    _closed_document(scope_raw, max_bytes=_DOCUMENT_LIMIT)
    scope = json.loads(scope_raw)
    seed, route_sha256 = _generation_seed(
        context, binding, scope, runtime_manifest, runtime_registration
    )
    if (
        witness["source_route"] != scope["source_route"]
        or (witness["seed_source"], witness["seed_state"])
        != (seed["source_tree_sha256"], seed["ade_state_tree_sha256"])
        or (observed["source_route_sha256"] != route_sha256)
    ):
        raise OperationRejected("research_generation_recovery_protection_mismatch")
    protected = _GenerationProtection.model_validate_json(
        _canonical(
            {
                "source": witness["seed_source"],
                "state": witness["seed_state"],
                "protected": scope["protected_sha256"],
                "counter": scope["counter"],
                "retained_jobs_sha256": scope["retained_jobs_sha256"],
                "ledger_records_sha256": scope["ledger_records_sha256"],
            }
        )
    )
    if any(
        _canonical(witness[key]) != _canonical(scope[key])
        for key in (
            "protected_sha256",
            "counter",
            "ledger_records_sha256",
        )
    ):
        raise OperationRejected("research_generation_recovery_protection_mismatch")

    provider = _FixedResearchGenerationProvider(context, directory, registration)
    progress = provider.lookup(binding)
    if progress is None or len(progress.captures) != 2:
        raise OperationRejected("research_generation_recovery_prefix_mismatch")
    prior = None
    for phase, capture in zip(_PHASES[:2], progress.captures, strict=True):
        stage = phases.save if phase == "save" else phases.reopen
        pins = witness["corrected_phases"][phase]
        if set(stage.records) != {"intent.json", "receipt.json", "complete.json"} or set(
            stage.records
        ) != set(pins):
            raise OperationRejected("research_generation_recovery_prefix_mismatch")
        records = {key: _artifact(value, 8192) for key, value in stage.records.items()}
        if any(_sha(value) != pins[key] for key, value in records.items()):
            raise OperationRejected("research_generation_recovery_prefix_mismatch")
        intent = provider._phase_intent(binding, phase, prior)
        raw_record = records["receipt.json"]
        _closed_document(raw_record, max_bytes=8192)
        record = _NativePhaseEvidence.model_validate_json(raw_record)
        if (
            records["intent.json"] != intent
            or records["complete.json"]
            != _canonical({"intent_sha256": _sha(intent), "receipt_sha256": _sha(raw_record)})
            or raw_record != _canonical(record.model_dump(mode="json"))
            or record.receipt != capture.receipt
            or record.scope_sha256 != binding.scope_sha256
            or record.previous_receipt_sha256 != prior
            or record.output_sha256 != _sha(capture.stdout)
            or stage.stdout_sha256 != _sha(capture.stdout)
            or (
                stage.stdout_base64
                and _artifact(stage.stdout_base64, _MARKER_LIMIT) != capture.stdout
            )
            or record.dut_sha256 is not None
            or record.trees != trees
            or record.protected != protected
            or (record.trees.library, record.trees.dut, record.trees.bench)
            != (
                capture.receipt.library.tree_sha256,
                capture.receipt.source_tree_sha256,
                capture.receipt.bench_tree_sha256,
            )
        ):
            raise OperationRejected("research_generation_recovery_prefix_mismatch")
        prior = canonical_digest(record.receipt)

    interrupted = phases.netlist
    netlist_intent = provider._phase_intent(binding, "netlist", prior)
    failed_pins = witness["corrected_phases"]["netlist"]
    if set(interrupted.records) != {"intent.json", "failure.json"} or set(failed_pins) != {
        "intent.json",
        "failure.json",
        "failure_checkpoint",
    }:
        raise OperationRejected("research_generation_recovery_netlist_mismatch")
    failure = _artifact(interrupted.records["failure.json"], 1024)
    if interrupted.stdout_base64 is None:
        raise OperationRejected("research_generation_recovery_netlist_mismatch")
    stdout = _artifact(interrupted.stdout_base64, _MARKER_LIMIT)
    markers = [line for line in stdout.splitlines() if line.startswith(MARKER_PREFIXES)]
    out = _read(provider._phase_file("netlist", "stdout.private.json"), _WIRE_LIMIT)
    err = _read(provider._phase_file("netlist", "stderr.private.txt"), _WIRE_LIMIT)
    transport = _read(provider._phase_file("netlist", "transport.private.json"), 4096)
    if (
        _artifact(interrupted.records["intent.json"], 4096) != netlist_intent
        or _sha(netlist_intent) != failed_pins["intent.json"]
        or _sha(failure) != failed_pins["failure.json"]
        or failed_pins["failure_checkpoint"] != "READBACK"
        or _sha(stdout) != observed["stdout"]["sha256"]
        or _sha(stdout) != interrupted.stdout_sha256
        or _read(provider._phase_file("netlist", "intent.private.json"), 4096) != netlist_intent
        or failure != _canonical({"status": "OUTCOME_UNKNOWN", "checkpoint": "READBACK"})
        or out
        or err != b"RESEARCH_GENERATION_REJECTED\n"
        or transport != provider._transport_record(69, out, err)
        or not markers
        or markers != [line.encode("ascii") for line in scope["markers"]["netlist"]]
        or not 0 < len(retained_input) <= ADE_INPUT_LIMIT
    ):
        raise OperationRejected("research_generation_recovery_netlist_mismatch")

    plan = OwnedMosBlockPlan.model_validate_json(
        _read(directory / "plan.private.json", _DOCUMENT_LIMIT, binding.plan_sha256)
    )
    bench = ResearchBenchPlan.model_validate_json(
        _read(directory / "bench-plan.private.json", _DOCUMENT_LIMIT, binding.bench_plan_sha256)
    )
    conditions = BenchNetlistConditions.model_validate_json(
        _read(directory / "conditions.private.json", _DOCUMENT_LIMIT, binding.conditions_sha256)
    )
    _, _, _, static = partition_input(retained_input)  # type: ignore[no-untyped-call]
    dut = dut_projection(static, scope["dut_subcircuits"])
    dut_sha256 = _sha(dut)
    if dut_sha256 != enrollment.dut_input_sha256:
        raise OperationRejected("research_generation_recovery_dut_mismatch")
    equivalence = verify_fixed_dc_bench_netlist_equivalence(
        bench,
        plan,
        nominal_input,
        retained_input,
        dut,
        expected_plan_sha256=binding.bench_plan_sha256,
        expected_statements_sha256=scope["netlist_statements_sha256"],
        expected_raw_sha256=enrollment.nominal_input_sha256,
        observed_raw_sha256=enrollment.retained_input_sha256,
        expected_dut_netlist_sha256=dut_sha256,
        conditions=conditions,
        expected_conditions_sha256=binding.conditions_sha256,
    )
    if (
        equivalence.observed_statements_sha256 != observed["parsed"]["statements"]
        or equivalence.expected_statements_sha256 != observed["expected_statements"]
        or equivalence.observed_statements_sha256 == equivalence.expected_statements_sha256
    ):
        raise OperationRejected("research_generation_recovery_statement_evidence_mismatch")
    receipt = progress.captures[1].receipt
    library = PurePosixPath(receipt.library.path)
    ade_state = library.parent / (PurePosixPath(receipt.bench_cell).name + "_ADE")
    if observed["owned_paths"] != {
        "library": str(library),
        "dut": receipt.source_cell,
        "bench": receipt.bench_cell,
        "ade_state": str(ade_state),
    }:
        raise OperationRejected("research_generation_recovery_source_path_mismatch")
    return RecoveredGenerationAnalysisSource(
        operation_id=binding.operation_id,
        binding_sha256=registration.binding_sha256,
        scope_sha256=binding.scope_sha256,
        recovery_enrollment_sha256=expected_recovery_enrollment_sha256,
        locked_witness_sha256=enrollment.locked_witness_sha256,
        reopen_receipt_sha256=canonical_digest(receipt),
        netlist_failure_sha256=_sha(failure),
        expected_statements_sha256=scope["netlist_statements_sha256"],
        equivalence_sha256=canonical_digest(equivalence),
        full_netlist_sha256=enrollment.retained_input_sha256,
        raw_dut_netlist_sha256=dut_sha256,
        static_statements_sha256=static_fingerprint(static),  # type: ignore[no-untyped-call]
        conditions_sha256=binding.conditions_sha256,
        native_manifest_sha256=binding.native_manifest_sha256,
        runtime_registration_sha256=_sha(runtime_registration),
        library=receipt.library,
        strict_library_tree_sha256=trees.strict_library,
        source_cell=receipt.bench_cell,
        source_tree_sha256=receipt.bench_tree_sha256,
        ade_state=str(ade_state),
        ade_state_tree_sha256=trees.state,
    )
