"""Fixed generation host sequencing over a fake durable worker."""

from dataclasses import dataclass, field, replace
from hashlib import sha256

import pytest
from test_research_bench import _declarative_fixture

from cadence_mcp_bridge.native_runtime import NativeLibrary
from cadence_mcp_bridge.operator_operations import OperationRejected
from cadence_mcp_bridge.research_bench import render_research_bench
from cadence_mcp_bridge.research_circuit import MosBlockStageReceipt
from cadence_mcp_bridge.research_generation_service import (
    Phase,
    RegisteredResearchGeneration,
    ResearchGenerationBinding,
    ResearchGenerationCapture,
    ResearchGenerationProgress,
    ResearchGenerationQuery,
)
from cadence_mcp_bridge.variable_contracts import canonical_digest


@dataclass
class Worker:
    available: dict[Phase, ResearchGenerationCapture]
    failed_phase: Phase | None = None
    retain_netlist: bool = True
    progress: ResearchGenerationProgress | None = None
    phases: list[Phase] = field(default_factory=list)
    claims: int = 0

    def lookup(self, binding: ResearchGenerationBinding) -> ResearchGenerationProgress | None:
        return self.progress

    def claim(self, binding: ResearchGenerationBinding) -> bool:
        self.claims += 1
        if self.progress is not None:
            return False
        self.progress = ResearchGenerationProgress(canonical_digest(binding))
        return True

    def run_phase(
        self,
        binding: ResearchGenerationBinding,
        phase: Phase,
        previous_receipt_sha256: str | None,
    ) -> ResearchGenerationCapture:
        assert self.progress is not None
        assert not self.phases or self.phases[-1] != phase
        self.phases.append(phase)
        if phase == self.failed_phase:
            raise OSError("worker failed after the durable intent")
        capture = self.available[phase]
        assert capture.previous_receipt_sha256 == previous_receipt_sha256
        if phase != "netlist" or self.retain_netlist:
            self.progress = replace(self.progress, captures=(*self.progress.captures, capture))
        return capture


def _fixture() -> tuple[RegisteredResearchGeneration, ResearchGenerationQuery, Worker]:
    bench, plan, frames, conditions, dut_raw, full = _declarative_fixture()
    plan_pin, bench_pin = canonical_digest(plan), canonical_digest(bench)
    path = "/owned/block"
    scripts = render_research_bench(
        bench,
        plan,
        frames,
        expected_plan_sha256=bench_pin,
        owned_library_path=path,
    )
    programs: dict[Phase, str] = dict(
        save=sha256(scripts.generate.encode("ascii")).hexdigest(),
        reopen=sha256(scripts.reopen.encode("ascii")).hexdigest(),
        netlist="f" * 64,
    )
    binding = ResearchGenerationBinding(
        operation_id="11111111-2222-4333-8444-555555555555",
        context_id="registered-research",
        resource_domain_sha256="e" * 64,
        native_manifest_sha256="d" * 64,
        scope_sha256="a" * 64,
        plan_sha256=plan_pin,
        bench_plan_sha256=bench_pin,
        conditions_sha256=canonical_digest(conditions),
        output_library=plan.output_library,
        owned_library_path=path,
        save_program_sha256=programs["save"],
        reopen_program_sha256=programs["reopen"],
        netlist_program_sha256=programs["netlist"],
    )
    library = NativeLibrary(name=plan.output_library, path=path, tree_sha256="c" * 64)
    available: dict[Phase, ResearchGenerationCapture] = {}
    predecessor = None
    phases: tuple[Phase, ...] = ("save", "reopen", "netlist")
    for phase in phases:
        if phase == "netlist":
            stdout = b""
        else:
            marks = scripts.save_markers if phase == "save" else scripts.reopen_markers
            stdout = ("\n".join(marks) + "\n").encode("ascii")
        row = MosBlockStageReceipt(
            phase=phase,
            operation_id=binding.operation_id,
            plan_sha256=plan_pin,
            library=library,
            source_cell=f"{path}/{plan.root}",
            source_tree_sha256="b" * 64,
            bench_cell=f"{path}/{bench.bench.name}",
            bench_tree_sha256="9" * 64,
            artifact_sha256=sha256(full if phase == "netlist" else stdout).hexdigest(),
            script_sha256=None if phase == "netlist" else programs[phase],
        )
        available[phase] = ResearchGenerationCapture(
            binding.scope_sha256,
            programs[phase],
            predecessor,
            row,
            stdout,
            dut_raw if phase == "netlist" else b"",
            full if phase == "netlist" else b"",
        )
        predecessor = canonical_digest(row)
    worker = Worker(available)
    pin = canonical_digest(binding)
    service = RegisteredResearchGeneration(
        binding,
        plan,
        bench,
        conditions,
        frames,
        worker,
        expected_binding_sha256=pin,
    )
    return (
        service,
        ResearchGenerationQuery(
            operation_id=binding.operation_id,
            expected_binding_sha256=pin,
        ),
        worker,
    )


def test_research_generation_submits_in_order_and_reuses_retained_handoff() -> None:
    service, query, worker = _fixture()
    assert service.status(query).status == "NOT_SUBMITTED"
    result = service.submit(query)
    assert result.status == "VERIFIED" and not result.replayed
    assert worker.phases == ["save", "reopen", "netlist"] and worker.claims == 1
    handoff = service.registration_handoff(query)
    assert handoff.handoff_sha256 == result.handoff_sha256
    restarted, _, restarted_provider = _fixture()
    restarted_provider.progress = worker.progress
    assert restarted.submit(query).replayed
    assert restarted.status(query).handoff_sha256 == result.handoff_sha256
    assert restarted_provider.phases == [] and restarted_provider.claims == 0


@pytest.mark.parametrize("fault", ["save", "reopen", "tree", "wrong_program"])
def test_research_generation_stops_before_dependent_execution(fault: str) -> None:
    service, query, worker = _fixture()
    if fault in {"save", "reopen"}:
        worker.failed_phase = "save" if fault == "save" else "reopen"
    else:
        stage = worker.available["reopen"]
        if fault == "tree":
            changed = stage.receipt.model_copy(update={"source_tree_sha256": "8" * 64})
            worker.available["reopen"] = replace(stage, receipt=changed)
        else:
            worker.available["reopen"] = replace(stage, program_sha256="8" * 64)
    expected = ["save"] if fault == "save" else ["save", "reopen"]
    assert service.submit(query).status == "OUTCOME_UNKNOWN"
    assert worker.phases == expected
    assert service.submit(query).status == "OUTCOME_UNKNOWN"
    assert worker.phases == expected and worker.claims == 1
    with pytest.raises(OperationRejected) as error:
        service.registration_handoff(query)
    assert error.value.reason == "research_generation_handoff_unavailable"


def test_research_generation_wrong_registration_never_claims() -> None:
    service, query, worker = _fixture()
    with pytest.raises(OperationRejected) as error:
        service.submit(query.model_copy(update={"expected_binding_sha256": "7" * 64}))
    assert error.value.reason == "research_generation_query_mismatch"
    assert not worker.phases and worker.claims == 0


def test_research_generation_requires_durable_evidence_before_verified() -> None:
    service, query, worker = _fixture()
    worker.retain_netlist = False
    result = service.submit(query)
    assert result.status == "OUTCOME_UNKNOWN"
    assert result.completed_phases == ("save", "reopen") and result.handoff_sha256 is None
    assert service.submit(query).status == "OUTCOME_UNKNOWN"
    assert worker.phases == ["save", "reopen", "netlist"] and worker.claims == 1
