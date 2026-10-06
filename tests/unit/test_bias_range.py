"""Scientific and registry bindings using synthetic data only."""

import copy
import math
from typing import Any

import pytest
from pydantic import ValidationError

from cadence_mcp_bridge.bias_range import (
    BASE_BYTES,
    CASES,
    RESERVATION,
    SOURCES,
    BiasExtraction,
    finite_grid_registry,
)
from cadence_mcp_bridge.designs import reference_contract_registry
from cadence_mcp_bridge.power_measurements import delivered_power
from cadence_mcp_bridge.variable_contracts import canonical_digest


def payload() -> dict[str, Any]:
    rows = []
    for i, case in enumerate(CASES):
        mode, value = case[-2:], 0.319 if case.startswith("lower") else 0.321
        source, input_sha, psf_sha = SOURCES[mode]
        row: dict[str, Any] = {
            "schema_version": 1, "case": case, "analysis": mode,
            "requested_vbiasn_v": str(value), "source_job_id": source,
            "source_input_sha256": input_sha, "source_psf_sha256": psf_sha,
            "input_sha256": "a" * 64, "psf_sha256": "b" * 64,
            "frame_sha256": "c" * 64, "counter": {
                "campaign_id": "AUTO-PHASE-01", "count": 73 + i,
                "result_reserved_bytes": BASE_BYTES + (i + 1) * RESERVATION,
            }, "warnings": 2, "notices": 0, "protected_unchanged": True,
        }
        if mode == "dc":
            row["scalars"] = {"Vop": 0.227, "Vom": 0.227, "Vp": 0.5, "Vm": 0.5,
                              "VDD": 1, "Vbiasn": value, "Vbiasp": 0.702}
            row["sources"] = [{"source_id": n, "role": r, "voltage_v": v, "current_a": j}
                              for n, r, v, j in (
                                  ("vdd", "supply", 1, -0.002),
                                  ("vss", "supply", 0, 0.002),
                                  ("bias-n", "bias", value, 1e-6),
                                  ("bias-p", "bias", 0.702, -1e-6),
                                  ("input-p", "stimulus", 0.5, 0),
                                  ("input-m", "stimulus", 0.5, 0))]
        else:
            row["spectrum"] = [{"frequency_hz": 10 ** (1 + j / 10),
                                "gain_v_per_v": 1000, "gain_db": 60, "phase_deg": 0}
                               for j in range(71)]
        rows.append(row)
    return {"schema_version": 1, "cases": rows}


def test_finite_grid_and_separate_fixed_conditions() -> None:
    e = BiasExtraction.model_validate(payload())
    r = finite_grid_registry(e)
    n, p, vdd = r.variable_sets[0].variables
    assert n.step_policy == "grid" and n.range_status == "qualified"
    for v in ("0.319", "0.32", "0.321"):
        assert n.check_number(v) is None
    assert n.check_number("0.3195") == "off_grid"
    assert n.check_number("0.318") == "outside_reviewed_range"
    assert p.check_number("0.702") is None and p.check_number("0.701") is not None
    assert vdd.check_number("1") is None and vdd.check_number("1.1") is not None
    assert r.range_reviews[0].evidence_sha256 == canonical_digest(e)
    assert reference_contract_registry().variable_sets[0].variables[0].range_status == "unqualified"
    assert not hasattr(r, "analysis_contracts")
    rails, bias, stimulus, total = delivered_power(e.cases[0].sources)
    assert rails == 0.002 and bias == pytest.approx(0.383e-6)
    assert stimulus == 0 and total == pytest.approx(rails + bias)


@pytest.mark.parametrize("change", [
    "case", "analysis", "value", "source", "source-input", "unchanged-input", "count",
    "bytes", "order", "missing", "extra", "node", "bias", "nan", "current",
    "inventory", "sign-role", "frequency", "gain-db", "no-ac", "both",
])
def test_binding_and_scientific_rejections(change: str) -> None:
    p = copy.deepcopy(payload())
    d, a = p["cases"][:2]
    if change == "case":
        d["case"] = "upperdc"
    elif change == "analysis":
        d["analysis"] = "ac"
    elif change == "value":
        d["requested_vbiasn_v"] = "0.321"
    elif change == "source":
        d["source_job_id"] = "another"
    elif change == "source-input":
        d["source_input_sha256"] = "d" * 64
    elif change == "unchanged-input":
        d["input_sha256"] = d["source_input_sha256"]
    elif change in ("count", "bytes"):
        d["counter"]["count" if change == "count" else "result_reserved_bytes"] += 1
    elif change == "order":
        p["cases"] = p["cases"][::-1]
    elif change == "missing":
        p["cases"].pop()
    elif change == "extra":
        d["path"] = "/private"
    elif change == "node":
        del d["scalars"]["Vop"]
    elif change == "bias":
        d["scalars"]["Vbiasn"] = 0.32
    elif change == "nan":
        d["scalars"]["Vop"] = math.nan
    elif change == "current":
        d["sources"][0]["current_a"] = None
    elif change == "inventory":
        d["sources"].pop()
    elif change == "sign-role":
        d["sources"][2]["role"] = "supply"
    elif change == "frequency":
        a["spectrum"][1]["frequency_hz"] = 9
    elif change == "gain-db":
        a["spectrum"][0]["gain_db"] = 63
    elif change == "no-ac":
        a["spectrum"] = []
    elif change == "both":
        a["sources"] = d["sources"]
    with pytest.raises(ValidationError):
        BiasExtraction.model_validate(p)
