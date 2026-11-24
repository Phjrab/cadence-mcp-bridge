"""Focused checks for the local registration preparation entry point."""

from hashlib import sha256

import pytest
from test_research_bench import _declarative_fixture, _definition

from cadence_mcp_bridge.research_bench import (
    BenchNetlistConditions,
    ResearchBenchPlan,
    render_research_bench,
)
from cadence_mcp_bridge.research_circuit import OwnedMosBlockPlan, ResearchCircuit
from cadence_mcp_bridge.research_generation_preparation import (
    ResearchGenerationPreparationRequest,
    prepare_research_generation,
)
from cadence_mcp_bridge.variable_contracts import canonical_digest


def _request() -> tuple[ResearchGenerationPreparationRequest, dict[str, bytes]]:
    bench, dut, frames, conditions, _, _ = _declarative_fixture()
    definition = ResearchCircuit.model_validate_json(
        _definition()
        .model_copy(update={"circuits": (*dut.circuits, bench.bench), "observations": ()})
        .model_dump_json()
    )
    return (
        ResearchGenerationPreparationRequest(
            definition=definition,
            expected_binding=definition.binding,
            expected_definition_sha256=canonical_digest(definition),
            output_library=dut.output_library,
            owned_library_path=f"/owned/{dut.output_library}",
            conditions=conditions,
            expected_conditions_sha256=canonical_digest(conditions),
            evidence_sha256=tuple(frames),
            primitive_cdf_sha256=bench.primitive_cdf_sha256,
        ),
        frames,
    )


def test_prepare_generation_exports_canonical_loader_inputs_and_programs() -> None:
    request, frames = _request()
    prepared = prepare_research_generation(request, frames)
    manifest, files = prepared.manifest, prepared.files
    assert not manifest.execution_authorized and not manifest.remote_contact
    assert set(files) == {
        "definition.private.json",
        "plan.private.json",
        "bench-plan.private.json",
        "conditions.private.json",
        "save-program.private",
        "reopen-program.private",
        "preparation.private.json",
        *(f"cdf-{pin}.private" for pin in frames),
    }
    for leaf, pin in (
        ("definition.private.json", manifest.definition_sha256),
        ("plan.private.json", manifest.plan_sha256),
        ("bench-plan.private.json", manifest.bench_plan_sha256),
        ("conditions.private.json", manifest.conditions_sha256),
        ("save-program.private", manifest.save_program_sha256),
        ("reopen-program.private", manifest.reopen_program_sha256),
    ):
        assert sha256(files[leaf]).hexdigest() == pin
    plan = OwnedMosBlockPlan.model_validate_json(files["plan.private.json"])
    bench = ResearchBenchPlan.model_validate_json(files["bench-plan.private.json"])
    assert len(plan.circuits[0].instances) == 17
    assert BenchNetlistConditions.model_validate_json(files["conditions.private.json"]) == (
        request.conditions
    )
    direct = render_research_bench(
        bench,
        plan,
        frames,
        expected_plan_sha256=manifest.bench_plan_sha256,
        owned_library_path=request.owned_library_path,
    )
    assert files["save-program.private"] == direct.generate.encode("ascii")
    assert files["reopen-program.private"] == direct.reopen.encode("ascii")


@pytest.mark.parametrize(
    ("pin", "message"),
    [
        ("expected_plan_sha256", "reviewed plan digest mismatch"),
        ("expected_conditions_sha256", "conditions digest mismatch"),
    ],
)
def test_prepare_generation_rejects_stale_reviewed_digests(pin: str, message: str) -> None:
    request, frames = _request()
    with pytest.raises(ValueError, match=message):
        prepare_research_generation(request.model_copy(update={pin: "0" * 64}), frames)


def test_prepare_generation_checks_evidence_bytes() -> None:
    request, frames = _request()
    frames[next(iter(frames))] += b" "
    with pytest.raises(ValueError, match="evidence digest mismatch"):
        prepare_research_generation(request, frames)
