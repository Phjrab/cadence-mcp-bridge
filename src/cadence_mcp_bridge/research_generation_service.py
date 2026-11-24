"""Registered research generation over the operator's existing durable worker."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from typing import Literal, Protocol

from cadence_mcp_bridge.generic_ade import LIMIT as ADE_INPUT_LIMIT
from cadence_mcp_bridge.native_diagnostics import OperationId
from cadence_mcp_bridge.native_runtime import RemotePath
from cadence_mcp_bridge.operator_operations import OperationRejected
from cadence_mcp_bridge.research_bench import (
    BenchNetlistConditions,
    ResearchBenchPlan,
    _check_bench_conditions,
    render_research_bench,
)
from cadence_mcp_bridge.research_circuit import (
    MosBlockHandoffPins,
    MosBlockRegistrationHandoff,
    MosBlockStageReceipt,
    OwnedMosBlockPlan,
    _check_mos_phase_stdout,
    verify_mos_block_handoff,
)
from cadence_mcp_bridge.variable_contracts import (
    BindingName,
    Digest,
    LogicalId,
    VariableModel,
    canonical_digest,
)

Phase = Literal["save", "reopen", "netlist"]
_PHASES: tuple[Phase, ...] = ("save", "reopen", "netlist")


class ResearchGenerationBinding(VariableModel):
    """Trusted operator registration. It is never accepted as a tool argument."""

    operation_id: OperationId
    context_id: LogicalId
    resource_domain_sha256: Digest
    native_manifest_sha256: Digest
    scope_sha256: Digest
    plan_sha256: Digest
    bench_plan_sha256: Digest
    conditions_sha256: Digest
    output_library: BindingName
    owned_library_path: RemotePath
    save_program_sha256: Digest
    reopen_program_sha256: Digest
    netlist_program_sha256: Digest


class ResearchGenerationQuery(VariableModel):
    operation_id: OperationId
    expected_binding_sha256: Digest


@dataclass(frozen=True)
class ResearchGenerationCapture:
    """Normalized provider evidence backed by independently retained native bytes."""

    scope_sha256: str
    program_sha256: str
    previous_receipt_sha256: str | None
    receipt: MosBlockStageReceipt
    stdout: bytes = b""
    dut_netlist: bytes = b""
    full_netlist: bytes = b""


@dataclass(frozen=True)
class ResearchGenerationProgress:
    """An existing durable claim and its readable phase captures in order."""

    binding_sha256: str
    captures: tuple[ResearchGenerationCapture, ...] = ()


class ResearchGenerationProvider(Protocol):
    """Trusted adapter over the normal owned runner and its existing claim store.

    Lookup reads only retained data. Claim is exclusive and must atomically
    enforce the current scope, admission and resource protections. run_phase
    reuses that claim and must bind execution, preservation and receipts to the
    registered program, phase and predecessor. It must durably retain the
    capture before returning, and reject phase redispatch.
    """

    def lookup(self, binding: ResearchGenerationBinding) -> ResearchGenerationProgress | None: ...

    def claim(self, binding: ResearchGenerationBinding) -> bool: ...

    def run_phase(
        self,
        binding: ResearchGenerationBinding,
        phase: Phase,
        previous_receipt_sha256: Digest | None,
    ) -> ResearchGenerationCapture: ...


class ResearchGenerationStatus(VariableModel):
    operation_id: OperationId
    binding_sha256: Digest
    status: Literal["NOT_SUBMITTED", "OUTCOME_UNKNOWN", "VERIFIED"]
    completed_phases: tuple[Phase, ...] = ()
    replayed: bool
    handoff_sha256: Digest | None = None


class RegisteredResearchGeneration:
    """Host sequencing and evidence verification for one registered operation."""

    def __init__(
        self,
        binding: ResearchGenerationBinding,
        plan: OwnedMosBlockPlan,
        bench: ResearchBenchPlan,
        conditions: BenchNetlistConditions,
        cdf_frames: Mapping[str, bytes],
        provider: ResearchGenerationProvider,
        *,
        expected_binding_sha256: Digest,
    ) -> None:
        self._binding = ResearchGenerationBinding.model_validate_json(binding.model_dump_json())
        self._plan = OwnedMosBlockPlan.model_validate_json(plan.model_dump_json())
        self._bench = ResearchBenchPlan.model_validate_json(bench.model_dump_json())
        self._conditions = BenchNetlistConditions.model_validate_json(conditions.model_dump_json())
        _check_bench_conditions(self._bench, self._conditions)
        self._cdf_frames = dict(cdf_frames)
        self._provider = provider
        self._binding_sha256 = canonical_digest(self._binding)
        if (
            self._binding_sha256 != expected_binding_sha256
            or canonical_digest(self._plan) != self._binding.plan_sha256
            or canonical_digest(self._conditions) != self._binding.conditions_sha256
            or self._plan.output_library != self._binding.output_library
        ):
            raise OperationRejected("research_generation_registration_mismatch")
        self._scripts = render_research_bench(
            self._bench,
            self._plan,
            self._cdf_frames,
            expected_plan_sha256=self._binding.bench_plan_sha256,
            owned_library_path=self._binding.owned_library_path,
        )
        self._programs: dict[Phase, Digest] = {
            "save": self._binding.save_program_sha256,
            "reopen": self._binding.reopen_program_sha256,
            "netlist": self._binding.netlist_program_sha256,
        }
        for expected, script in (
            (self._binding.save_program_sha256, self._scripts.generate),
            (self._binding.reopen_program_sha256, self._scripts.reopen),
        ):
            if sha256(script.encode("ascii")).hexdigest() != expected:
                raise OperationRejected("research_generation_program_mismatch")

    def _check_query(self, query: ResearchGenerationQuery) -> None:
        checked = ResearchGenerationQuery.model_validate_json(query.model_dump_json())
        if (
            checked.operation_id != self._binding.operation_id
            or checked.expected_binding_sha256 != self._binding_sha256
        ):
            raise OperationRejected("research_generation_query_mismatch")

    def _validate_phase(
        self,
        capture: ResearchGenerationCapture,
        phase: Phase,
        prior: MosBlockStageReceipt | None,
    ) -> MosBlockStageReceipt:
        binding = self._binding
        row = MosBlockStageReceipt.model_validate_json(capture.receipt.model_dump_json())
        library = binding.owned_library_path
        if (
            capture.scope_sha256 != binding.scope_sha256
            or capture.program_sha256 != self._programs[phase]
            or capture.previous_receipt_sha256 != (canonical_digest(prior) if prior else None)
            or row.phase != phase
            or row.operation_id != binding.operation_id
            or row.plan_sha256 != binding.plan_sha256
            or (row.library.name, row.library.path) != (binding.output_library, library)
            or row.source_cell != f"{library}/{self._plan.root}"
            or row.bench_cell != f"{library}/{self._scripts.bench_cell}"
            or (
                prior is not None
                and (row.library, row.source_tree_sha256, row.bench_tree_sha256)
                != (prior.library, prior.source_tree_sha256, prior.bench_tree_sha256)
            )
        ):
            raise ValueError("research generation phase evidence mismatch")
        if phase == "netlist":
            if (
                capture.stdout
                or not 0 < len(capture.dut_netlist) <= ADE_INPUT_LIMIT
                or not 0 < len(capture.full_netlist) <= ADE_INPUT_LIMIT
                or sha256(capture.full_netlist).hexdigest() != row.artifact_sha256
            ):
                raise ValueError("research generation netlist evidence mismatch")
        else:
            if capture.dut_netlist or capture.full_netlist:
                raise ValueError("unexpected netlist in saved-view receipt")
            scripts = self._scripts
            script, markers = (
                (scripts.generate, scripts.save_markers)
                if phase == "save"
                else (scripts.reopen, scripts.reopen_markers)
            )
            _check_mos_phase_stdout(capture.stdout, markers, script, row)
        return row

    def _handoff(
        self,
        captures: list[ResearchGenerationCapture],
        rows: list[MosBlockStageReceipt],
    ) -> MosBlockRegistrationHandoff:
        saved, reopened, netlisted = rows
        netlist = captures[2]
        pins = MosBlockHandoffPins(
            plan_sha256=self._binding.plan_sha256,
            bench_plan_sha256=self._binding.bench_plan_sha256,
            bench_conditions_sha256=self._binding.conditions_sha256,
            save_receipt_sha256=canonical_digest(saved),
            reopen_receipt_sha256=canonical_digest(reopened),
            netlist_receipt_sha256=canonical_digest(netlisted),
            full_netlist_sha256=netlisted.artifact_sha256,
            raw_netlist_sha256=sha256(netlist.dut_netlist).hexdigest(),
        )
        return verify_mos_block_handoff(
            self._plan,
            self._bench,
            self._cdf_frames,
            pins=pins,
            conditions=self._conditions,
            saved=saved,
            reopened=reopened,
            netlisted=netlisted,
            save_stdout=captures[0].stdout,
            reopen_stdout=captures[1].stdout,
            raw_netlist=netlist.dut_netlist,
            full_netlist=netlist.full_netlist,
        )

    def _status(
        self,
        status: Literal["NOT_SUBMITTED", "OUTCOME_UNKNOWN", "VERIFIED"],
        *,
        count: int = 0,
        replayed: bool,
        handoff: MosBlockRegistrationHandoff | None = None,
    ) -> ResearchGenerationStatus:
        return ResearchGenerationStatus(
            operation_id=self._binding.operation_id,
            binding_sha256=self._binding_sha256,
            status=status,
            completed_phases=_PHASES[:count],
            replayed=replayed,
            handoff_sha256=handoff.handoff_sha256 if handoff else None,
        )

    def _observe(self) -> tuple[ResearchGenerationStatus, MosBlockRegistrationHandoff | None]:
        evidence = self._provider.lookup(self._binding)
        if evidence is None:
            return self._status("NOT_SUBMITTED", replayed=False), None
        if evidence.binding_sha256 != self._binding_sha256:
            raise OperationRejected("research_generation_claim_conflict")
        rows: list[MosBlockStageReceipt] = []
        try:
            if len(evidence.captures) > len(_PHASES):
                raise ValueError("research generation phase count mismatch")
            for phase, capture in zip(_PHASES, evidence.captures, strict=False):
                rows.append(self._validate_phase(capture, phase, rows[-1] if rows else None))
            if len(rows) == len(_PHASES):
                handoff = self._handoff(list(evidence.captures), rows)
                return self._status(
                    "VERIFIED", count=len(rows), replayed=True, handoff=handoff
                ), handoff
        except (ValueError, OSError):
            pass
        return self._status("OUTCOME_UNKNOWN", count=len(rows), replayed=True), None

    def status(self, query: ResearchGenerationQuery) -> ResearchGenerationStatus:
        self._check_query(query)
        return self._observe()[0]

    def registration_handoff(self, query: ResearchGenerationQuery) -> MosBlockRegistrationHandoff:
        """Read verified retained evidence for the existing registration assembler."""
        self._check_query(query)
        _, handoff = self._observe()
        if handoff is None:
            raise OperationRejected("research_generation_handoff_unavailable")
        return handoff

    def submit(self, query: ResearchGenerationQuery) -> ResearchGenerationStatus:
        self._check_query(query)
        prior, _ = self._observe()
        if prior.status != "NOT_SUBMITTED":
            return prior
        if not self._provider.claim(self._binding):
            status, _ = self._observe()
            if status.status == "NOT_SUBMITTED":
                return self._status("OUTCOME_UNKNOWN", replayed=True)
            return status
        captures: tuple[ResearchGenerationCapture, ...] = ()
        rows: list[MosBlockStageReceipt] = []
        try:
            for phase in _PHASES:
                predecessor = rows[-1] if rows else None
                capture = self._provider.run_phase(
                    self._binding, phase, canonical_digest(predecessor) if predecessor else None
                )
                row = self._validate_phase(capture, phase, predecessor)
                captures = (*captures, capture)
                retained = self._provider.lookup(self._binding)
                if retained != ResearchGenerationProgress(self._binding_sha256, captures):
                    raise ValueError("research generation phase evidence not retained")
                rows.append(row)
            handoff = self._handoff(list(captures), rows)
        except (OSError, ValueError):
            return self._status("OUTCOME_UNKNOWN", count=len(rows), replayed=False)
        return self._status("VERIFIED", count=len(rows), replayed=False, handoff=handoff)
