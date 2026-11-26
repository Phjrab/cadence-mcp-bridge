"""Verify the named-port mapping in an original, independently retained OTA HNL input."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import PurePosixPath
from typing import Annotated, Literal

from pydantic import Field

from cadence_mcp_bridge._native_rendering import statements
from cadence_mcp_bridge._research_generation_worker import (
    OTA17_BENCH,
    OTA17_DUT,
    OTA17_MOS,
    dut_projection,
)
from cadence_mcp_bridge.domain_provisioning import _closed_document
from cadence_mcp_bridge.research_bench import (
    BenchNetlistConditions,
    ResearchBenchPlan,
    verify_research_bench_netlist,
)
from cadence_mcp_bridge.research_circuit import Mos, OwnedMosBlockPlan
from cadence_mcp_bridge.variable_contracts import Digest, VariableModel

_DUT = OTA17_DUT
_HEADER = f"subckt {_DUT} VDD VSS inn inp out"
_CALL = f"DUT (vdd 0 inn inp out) {_DUT}"


class _ModelEquivalence(VariableModel):
    alias: str
    canonical_path: str
    device: Annotated[int, Field(strict=True, ge=0)]
    inode: Annotated[int, Field(strict=True, gt=0)]
    file_bytes: Annotated[int, Field(strict=True, gt=0)]
    file_sha256: Digest
    registered_model_leaf_count: Literal[7]
    registered_model_leaf_list_sha256: Digest
    section: Literal["NN"]


class OtaNetlistEquivalence(VariableModel):
    original_input_sha256: Digest
    original_dut_sha256: Digest
    comparison_input_sha256: Digest
    comparison_dut_sha256: Digest
    model_custody_sha256: Digest


def _comparison_lines(lines: list[str], model: _ModelEquivalence) -> list[str]:
    # Substituting only one of the two positional statements reverses polarity.
    substitutions = {
        _HEADER: f"subckt {_DUT} VDD VSS inp inn out",
        _CALL: f"DUT (vdd 0 inp inn out) {_DUT}",
        f'include "{model.alias}" section=NN': f'include "{model.canonical_path}" section=NN',
    }
    if any(lines.count(original) != 1 for original in substitutions):
        raise ValueError("OTA recovery requires the exact paired port mapping and NN include")
    return [substitutions.get(line, line) for line in lines]


def verify_ota17_recovered_netlist(
    dut_plan: OwnedMosBlockPlan,
    bench_plan: ResearchBenchPlan,
    conditions: BenchNetlistConditions,
    raw: bytes,
    *,
    expected_raw_sha256: Digest,
    expected_bench_plan_sha256: Digest,
    expected_conditions_sha256: Digest,
    model_custody: bytes,
    expected_model_custody_sha256: Digest,
    expected_model_closure_sha256: Digest,
) -> OtaNetlistEquivalence:
    """Compare on a local projection. Physical registration retains the original input."""
    if (
        len(raw) > 262144
        or sha256(raw).hexdigest() != expected_raw_sha256
        or sha256(model_custody).hexdigest() != expected_model_custody_sha256
        or dut_plan.root != _DUT
        or len(dut_plan.circuits) != 1
        or {mos.name for mos in dut_plan.circuits[0].instances} != OTA17_MOS
        or any(
            not isinstance(mos, Mos) or mos.geometry.generation_observation is None
            for mos in dut_plan.circuits[0].instances
        )
        or bench_plan.bench.name != OTA17_BENCH
        or not bench_plan.signed_ac_vsin_dc
    ):
        raise ValueError("OTA recovery input or generation plan mismatch")
    _closed_document(model_custody)
    witness = json.loads(model_custody)
    pinned = _ModelEquivalence.model_validate(witness["model_equivalence"])
    canonical_path = PurePosixPath(pinned.canonical_path)
    if (
        not canonical_path.is_absolute()
        or ".." in canonical_path.parts
        or str(canonical_path) != pinned.canonical_path
        or canonical_path.parts[-3:] != ("models", "spectre", "gpdk090.scs")
        or pinned.alias
        != str(canonical_path.parents[2] / "libs.oa22/gpdk090/../../models/spectre/gpdk090.scs")
        or witness["native_input_sha256"] != expected_raw_sha256
        or pinned.registered_model_leaf_list_sha256 != expected_model_closure_sha256
        or conditions.includes != ((pinned.canonical_path, "NN"),)
    ):
        raise ValueError("OTA recovery model identity mismatch")
    lines: list[str] = statements(raw)  # type: ignore[no-untyped-call]
    comparison = _comparison_lines(lines, pinned)
    comparison_input = ("simulator lang=spectre\n" + "\n".join(comparison) + "\n").encode("ascii")
    original_dut: bytes = dut_projection(lines, [_DUT])  # type: ignore[no-untyped-call]
    comparison_dut: bytes = dut_projection(comparison, [_DUT])  # type: ignore[no-untyped-call]
    proof = OtaNetlistEquivalence(
        original_input_sha256=expected_raw_sha256,
        original_dut_sha256=sha256(original_dut).hexdigest(),
        comparison_input_sha256=sha256(comparison_input).hexdigest(),
        comparison_dut_sha256=sha256(comparison_dut).hexdigest(),
        model_custody_sha256=expected_model_custody_sha256,
    )
    verify_research_bench_netlist(
        bench_plan,
        dut_plan,
        comparison_input,
        comparison_dut,
        expected_plan_sha256=expected_bench_plan_sha256,
        expected_netlist_sha256=proof.comparison_input_sha256,
        expected_dut_netlist_sha256=proof.comparison_dut_sha256,
        conditions=conditions,
        expected_conditions_sha256=expected_conditions_sha256,
    )
    return proof
