"""Attest the original retained input of the single OTA17 generation scope."""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from cadence_mcp_bridge._native_rendering import partition_input, static_fingerprint
from cadence_mcp_bridge._research_generation_worker import MARKER_PREFIXES
from cadence_mcp_bridge.domain_provisioning import _canonical, _closed_document
from cadence_mcp_bridge.generic_ade import LIMIT as ADE_INPUT_LIMIT
from cadence_mcp_bridge.native_diagnostics import OperationId
from cadence_mcp_bridge.native_runtime import RemotePath
from cadence_mcp_bridge.onboarding import _local_path
from cadence_mcp_bridge.ota_reopen_evidence import parse_ota_reopen_properties
from cadence_mcp_bridge.pmos_default_service import _read, _require, _sha
from cadence_mcp_bridge.research_bench import BenchNetlistConditions, ResearchBenchPlan
from cadence_mcp_bridge.research_circuit import OwnedMosBlockPlan
from cadence_mcp_bridge.research_generation_provider import (
    _DOCUMENT_LIMIT,
    _MARKER_LIMIT,
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
from cadence_mcp_bridge.research_generation_recovery import RecoveredGenerationAnalysisSource
from cadence_mcp_bridge.research_generation_service import ResearchGenerationQuery
from cadence_mcp_bridge.runtime_context import ExecutionContext
from cadence_mcp_bridge.variable_contracts import Digest, VariableModel, canonical_digest

_DUT = "self_cascode_ota_17mos"
_BENCH = "self_cascode_ota_tb"
_PREFIX = ("save", "reopen")
_CUSTODY = "research_generation_ota_retained_custody_mismatch"


class _OtaRecoveryEnrollment(VariableModel):
    schema_version: Literal[2]
    registration_file_sha256: Digest
    binding_sha256: Digest
    locked_witness_sha256: Digest
    terminal_witness_sha256: Digest
    detached_witness_sha256: Digest
    model_alias_witness_sha256: Digest
    expected_topology_sha256: Digest
    retained_input_sha256: Digest


class _WitnessBundle(VariableModel):
    schema_version: Literal[2]
    terminal_base64: str
    detached_base64: str
    model_alias_base64: str


class _ObservedAction(VariableModel):
    operation_id: OperationId
    scope_sha256: Digest
    binding_sha256: Digest
    parent_allocated: int
    job_allocated: int
    ocean: Literal[0]
    spectre: Literal[0]
    reservations: Literal[0]
    writes: Literal[0]


class _TerminalWitness(_ObservedAction):
    status: Literal["OTA17_BASELINE_TERMINAL_OBSERVED"]
    closed_originals: _GenerationProtection
    records: dict[str, tuple[Digest, Digest]]
    evidence: dict[str, tuple[str, Digest]]


class _DetachedWitness(_ObservedAction):
    status: Literal["OTA17_RETAINED_NETLIST_CUSTODY_ONLY"]
    locked_originals: _GenerationProtection
    trees: _GenerationTrees
    symbol: Digest
    detached_bench_sha256: Digest
    detached_state_sha256: Digest
    detached_ade_leaf_sha256: Digest
    fail_sha256: Digest
    intent_sha256: Digest
    native_input_sha256: Digest
    ocean_stdout_sha256: Digest
    no_original_completion: Literal[True]


class _ModelAlias(VariableModel):
    alias: RemotePath
    canonical_path: RemotePath
    device: int
    file_bytes: int
    file_sha256: Digest
    inode: int
    registered_model_leaf_count: Literal[7]
    registered_model_leaf_list_sha256: Digest
    section: Literal["NN"]


class _AliasWitness(_DetachedWitness):
    model_equivalence: _ModelAlias


class RecoveredOtaGenerationAnalysisSource(RecoveredGenerationAnalysisSource):
    recovery_kind: Literal["OTA17_NAMED_PORT_PERMUTATION"] = "OTA17_NAMED_PORT_PERMUTATION"
    terminal_witness_sha256: Digest
    detached_witness_sha256: Digest
    model_alias_witness_sha256: Digest
    expected_topology_sha256: Digest
    dut_plan_sha256: Digest
    save_receipt_sha256: Digest
    reopen_stdout_sha256: Digest
    dut_cell: RemotePath
    dut_tree_sha256: Digest
    symbol_tree_sha256: Digest
    cds_lib_sha256: Digest
    detached_bench_sha256: Digest
    detached_state_sha256: Digest
    detached_ade_leaf_sha256: Digest


def _witness_bytes(encoded: str, digest: str, limit: int = _DOCUMENT_LIMIT) -> bytes:
    raw = _artifact(encoded, limit)
    _require(_sha(raw) == digest, _CUSTODY)
    return raw


def _detached_cds_lib(
    context: ExecutionContext,
    scope: dict[str, Any],
    route: dict[str, Any],
    owned: str,
    operation_id: str,
) -> str:
    mappings = [
        (entry["name"], entry["path"])
        for entry in route["libraries"]
        if entry["name"] in ("basic", "analogLib", "gpdk090")
    ]
    _require(
        len(mappings) == 3
        and {name for name, _ in mappings}
        == {
            "basic",
            "analogLib",
            "gpdk090",
        },
        _CUSTODY,
    )
    work = (
        PurePosixPath(context.contracts.environment.paths.managed_root)
        / "native-mcp-v1-jobs"
        / operation_id
        / "research-generation/netlist/work/library"
    )
    mappings.extend(
        (
            ("cdsDefTechLib", scope["technology"]["path"]),
            (PurePosixPath(owned).name, owned),
            ("MCP_GREL_Work", str(work)),
        )
    )
    # C1's locked detached witness compares this complete map to the original cds.lib.
    return _sha("".join(f"DEFINE {name} {path}\n" for name, path in mappings).encode("ascii"))


def recover_ota_generation_analysis_source(
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
) -> RecoveredOtaGenerationAnalysisSource:
    """Read original evidence and attest a distinct source without completing the old ID."""
    from cadence_mcp_bridge.ota_netlist_recovery import verify_ota17_recovered_netlist

    _closed_document(recovery_enrollment, max_bytes=4096)
    enrollment = _OtaRecoveryEnrollment.model_validate_json(recovery_enrollment)
    _require(
        _sha(recovery_enrollment) == expected_recovery_enrollment_sha256
        and _sha(registration_raw) == enrollment.registration_file_sha256
        and _sha(locked_witness) == enrollment.locked_witness_sha256
        and _sha(nominal_input) == enrollment.expected_topology_sha256
        and 0 < len(retained_input) <= ADE_INPUT_LIMIT
        and _sha(retained_input) == enrollment.retained_input_sha256,
        _CUSTODY,
    )
    _closed_document(locked_witness, max_bytes=_DOCUMENT_LIMIT)
    bundle = _WitnessBundle.model_validate_json(locked_witness)
    terminal_raw = _witness_bytes(bundle.terminal_base64, enrollment.terminal_witness_sha256)
    detached_raw = _witness_bytes(bundle.detached_base64, enrollment.detached_witness_sha256)
    alias_raw = _witness_bytes(bundle.model_alias_base64, enrollment.model_alias_witness_sha256)
    for raw in (terminal_raw, detached_raw, alias_raw):
        _closed_document(raw, max_bytes=_DOCUMENT_LIMIT)
    terminal = _TerminalWitness.model_validate_json(terminal_raw)
    detached = _DetachedWitness.model_validate_json(detached_raw)
    alias = _AliasWitness.model_validate_json(alias_raw)
    _require(
        alias.model_dump(exclude={"model_equivalence"}) == detached.model_dump(),
        _CUSTODY,
    )
    directory = _local_path(directory)
    service = registered_research_generation(context, registration_raw, directory)
    registration = _Registration.model_validate_json(registration_raw)
    binding = registration.binding
    state = service.status(query)
    expected_identity = (binding.operation_id, binding.scope_sha256, registration.binding_sha256)
    _require(
        state.status == "OUTCOME_UNKNOWN"
        and state.completed_phases == _PREFIX
        and state.handoff_sha256 is None
        and state.replayed
        and enrollment.binding_sha256 == registration.binding_sha256
        and all(
            (row.operation_id, row.scope_sha256, row.binding_sha256) == expected_identity
            for row in (terminal, detached)
        )
        and detached.native_input_sha256 == enrollment.retained_input_sha256,
        _CUSTODY,
    )
    scope_raw = _read(
        directory / "execution-scope.private.json", _DOCUMENT_LIMIT, binding.scope_sha256
    )
    _closed_document(scope_raw, max_bytes=_DOCUMENT_LIMIT)
    scope = json.loads(scope_raw)
    seed, route_sha = _generation_seed(
        context, binding, scope, runtime_manifest, runtime_registration
    )
    (route,) = (
        item
        for item in json.loads(runtime_registration)["routes"]
        if _sha(_canonical(item)) == route_sha
    )
    protected = _GenerationProtection.model_validate_json(
        _canonical(
            {
                "source": seed["source_tree_sha256"],
                "state": seed["ade_state_tree_sha256"],
                "protected": scope["protected_sha256"],
                "counter": scope["counter"],
                "retained_jobs_sha256": scope["retained_jobs_sha256"],
                "ledger_records_sha256": scope["ledger_records_sha256"],
            }
        )
    )
    _require(
        scope["schema_version"] == 2
        and scope["dut_cell"] == _DUT
        and scope["bench_cell"] == _BENCH
        and scope["dut_subcircuits"] == [_DUT]
        and scope["netlist_statements_sha256"] == enrollment.expected_topology_sha256
        and terminal.closed_originals == detached.locked_originals == protected
        and (terminal.parent_allocated, terminal.job_allocated)
        == (detached.parent_allocated, detached.job_allocated)
        and set(terminal.records) == set(_PREFIX)
        and set(terminal.evidence)
        == {
            *(
                f"{phase}-{leaf}"
                for phase in _PREFIX
                for leaf in ("native-record", "native-completion", "ocean.stdout", "ocean.stderr")
            ),
            "netlist-failure",
            "netlist-observed-raw.scs",
            "netlist-failed-ocean.stdout",
            "netlist-failed-ocean.stderr",
        },
        _CUSTODY,
    )
    provider = _FixedResearchGenerationProvider(context, directory, registration)
    progress = provider.lookup(binding)
    if progress is None or len(progress.captures) != 2:
        raise ValueError(_CUSTODY)
    prior = None
    for phase, capture in zip(_PREFIX, progress.captures, strict=True):
        raw_record = _witness_bytes(*terminal.evidence[f"{phase}-native-record"], 8192)
        raw_complete = _witness_bytes(*terminal.evidence[f"{phase}-native-completion"], 4096)
        stdout = _witness_bytes(*terminal.evidence[f"{phase}-ocean.stdout"], _MARKER_LIMIT)
        stderr = _witness_bytes(*terminal.evidence[f"{phase}-ocean.stderr"], 8192)
        record = _NativePhaseEvidence.model_validate_json(raw_record)
        intent = provider._phase_intent(binding, phase, prior)
        _require(
            (_sha(raw_record), _sha(raw_complete)) == terminal.records[phase]
            and raw_record == _canonical(record.model_dump(mode="json"))
            and raw_complete
            == _canonical({"intent_sha256": _sha(intent), "receipt_sha256": _sha(raw_record)})
            and record.receipt == capture.receipt
            and stdout == capture.stdout
            and not stderr
            and record.output_sha256 == _sha(stdout)
            and record.dut_sha256 is None
            and record.trees == detached.trees
            and record.protected == protected
            and record.previous_receipt_sha256 == prior
            and record.scope_sha256 == binding.scope_sha256
            and (record.trees.library, record.trees.dut, record.trees.bench)
            == (
                capture.receipt.library.tree_sha256,
                capture.receipt.source_tree_sha256,
                capture.receipt.bench_tree_sha256,
            ),
            _CUSTODY,
        )
        prior = canonical_digest(capture.receipt)

    intent = provider._phase_intent(binding, "netlist", prior)
    raw_failure = _witness_bytes(*terminal.evidence["netlist-failure"], 4096)
    netlist_stdout = _witness_bytes(
        *terminal.evidence["netlist-failed-ocean.stdout"], _MARKER_LIMIT
    )
    netlist_stderr = _witness_bytes(*terminal.evidence["netlist-failed-ocean.stderr"], 8192)
    out = _read(provider._phase_file("netlist", "stdout.private.json"), _WIRE_LIMIT)
    err = _read(provider._phase_file("netlist", "stderr.private.txt"), _WIRE_LIMIT)
    transport = _read(provider._phase_file("netlist", "transport.private.json"), 4096)
    _require(
        _sha(intent) == detached.intent_sha256
        and _sha(raw_failure) == detached.fail_sha256
        and _sha(netlist_stdout) == detached.ocean_stdout_sha256
        and not netlist_stderr
        and raw_failure == _canonical({"status": "OUTCOME_UNKNOWN", "checkpoint": "READBACK"})
        and _witness_bytes(*terminal.evidence["netlist-observed-raw.scs"], ADE_INPUT_LIMIT)
        == retained_input
        and _read(provider._phase_file("netlist", "intent.private.json"), 4096) == intent
        and not out
        and err == b"RESEARCH_GENERATION_REJECTED\n"
        and transport == provider._transport_record(69, out, err)
        and [line for line in netlist_stdout.splitlines() if line.startswith(MARKER_PREFIXES)]
        == [line.encode("ascii") for line in scope["markers"]["netlist"]],
        _CUSTODY,
    )
    plan = OwnedMosBlockPlan.model_validate_json(
        _read(directory / "plan.private.json", _DOCUMENT_LIMIT, binding.plan_sha256)
    )
    bench = ResearchBenchPlan.model_validate_json(
        _read(directory / "bench-plan.private.json", _DOCUMENT_LIMIT, binding.bench_plan_sha256)
    )
    conditions = BenchNetlistConditions.model_validate_json(
        _read(directory / "conditions.private.json", _DOCUMENT_LIMIT, binding.conditions_sha256)
    )
    root = next(cell for cell in plan.circuits if cell.name == plan.root)
    saved, reopened = progress.captures
    parse_ota_reopen_properties(
        reopened.stdout,
        stdout_sha256=reopened.receipt.artifact_sha256,
        plan_sha256=binding.plan_sha256,
        cell=_DUT,
        instance_names=tuple(row.name for row in root.instances),
    )
    equivalence = verify_ota17_recovered_netlist(
        plan,
        bench,
        conditions,
        retained_input,
        expected_raw_sha256=enrollment.retained_input_sha256,
        expected_bench_plan_sha256=binding.bench_plan_sha256,
        expected_conditions_sha256=binding.conditions_sha256,
        model_custody=alias_raw,
        expected_model_custody_sha256=enrollment.model_alias_witness_sha256,
        expected_model_closure_sha256=_sha(_canonical(route["model_files"])),
    )
    _, _, _, static = partition_input(retained_input)  # type: ignore[no-untyped-call]
    lib = PurePosixPath(reopened.receipt.library.path)
    return RecoveredOtaGenerationAnalysisSource(
        operation_id=binding.operation_id,
        binding_sha256=registration.binding_sha256,
        scope_sha256=binding.scope_sha256,
        recovery_enrollment_sha256=expected_recovery_enrollment_sha256,
        locked_witness_sha256=enrollment.locked_witness_sha256,
        reopen_receipt_sha256=canonical_digest(reopened.receipt),
        netlist_failure_sha256=detached.fail_sha256,
        expected_statements_sha256=enrollment.expected_topology_sha256,
        equivalence_sha256=canonical_digest(equivalence),
        full_netlist_sha256=enrollment.retained_input_sha256,
        raw_dut_netlist_sha256=equivalence.original_dut_sha256,
        static_statements_sha256=static_fingerprint(static),  # type: ignore[no-untyped-call]
        conditions_sha256=binding.conditions_sha256,
        native_manifest_sha256=binding.native_manifest_sha256,
        runtime_registration_sha256=_sha(runtime_registration),
        library=reopened.receipt.library,
        strict_library_tree_sha256=detached.trees.strict_library,
        source_cell=reopened.receipt.bench_cell,
        source_tree_sha256=detached.trees.bench,
        ade_state=str(lib.parent / f"{_BENCH}_ADE"),
        ade_state_tree_sha256=detached.trees.state,
        terminal_witness_sha256=enrollment.terminal_witness_sha256,
        detached_witness_sha256=enrollment.detached_witness_sha256,
        model_alias_witness_sha256=enrollment.model_alias_witness_sha256,
        expected_topology_sha256=enrollment.expected_topology_sha256,
        dut_plan_sha256=binding.plan_sha256,
        save_receipt_sha256=canonical_digest(saved.receipt),
        reopen_stdout_sha256=_sha(reopened.stdout),
        dut_cell=reopened.receipt.source_cell,
        dut_tree_sha256=detached.trees.dut,
        symbol_tree_sha256=detached.symbol,
        cds_lib_sha256=_detached_cds_lib(
            context, scope, route, binding.owned_library_path, binding.operation_id
        ),
        detached_bench_sha256=detached.detached_bench_sha256,
        detached_state_sha256=detached.detached_state_sha256,
        detached_ade_leaf_sha256=detached.detached_ade_leaf_sha256,
    )
