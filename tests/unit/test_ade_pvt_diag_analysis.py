"""Independent synthetic arithmetic; no real graph, operating points or transport."""

from __future__ import annotations

import importlib
import json
import math
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
analysis = importlib.import_module("ade_pvt_diag_analysis")


@pytest.mark.parametrize("sign", [1, -1])
def test_polarity_safe_current_and_headroom(sign: int) -> None:
    result = analysis.metrics(
        {
            "gm": 6.0,
            "gds": 2.0,
            "id": sign * 0.002,
            "vds": sign * 0.1,
            "vdsat": sign * 0.3,
            "region": 17.0,
        }
    )
    assert result["headroom_v"] == pytest.approx(-0.2)
    assert result["intrinsic_gain"] == 3.0
    assert result["abs_current_a"] == 0.002
    assert result["region_code"] == 17.0  # No invented region enum.


@pytest.mark.parametrize("denominator", [0.0, -1.0])
def test_undefined_intrinsic_gain(denominator: float) -> None:
    assert analysis.divide(2.0, denominator) is None


def test_missing_fields_are_not_zero() -> None:
    result = analysis.metrics(dict.fromkeys(["gm", "gds", "id", "vds", "vdsat", "region"]))
    assert all(value is None for value in result.values())


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_nonfinite_arithmetic_rejected(bad: float) -> None:
    with pytest.raises(ValueError, match="nonfinite"):
        analysis.divide(bad, 1.0)
    with pytest.raises(ValueError, match="nonfinite"):
        analysis.solve([[bad]], [1.0])


def test_pivot_and_residual_against_known_solution() -> None:
    assert analysis.solve([[0.0, 2.0], [1.0, -1.0]], [6.0, -1.0]) == [2.0, 3.0]


@pytest.mark.parametrize("matrix", [[], [[0.0]], [[1.0, 2.0]], [[1.0, 1.0], [1.0, 1.0]]])
def test_undefined_system_fails_closed(matrix: list[list[float]]) -> None:
    with pytest.raises(ValueError):
        analysis.solve(matrix, [1.0] * len(matrix))


def synthetic_points(gm: float, gds: float, gmbs: float = 0.0) -> list[dict[str, Any]]:
    return [{"alias": "synthetic", "fields": {"gm": gm, "gds": gds, "gmbs": gmbs}}]


def test_common_source_gain_from_kcl_and_body_drive() -> None:
    devices = [{"alias": "synthetic", "nodes": ["out", "input", "ground", "body"]}]
    values = analysis.nodal(
        devices, synthetic_points(6.0, 2.0, 1.0), {"input": 0.5, "ground": 0.0, "body": 0.2}
    )
    assert values["out"] == pytest.approx(-1.6)


def test_diode_connected_conductance_and_source_stamp() -> None:
    devices = [{"alias": "synthetic", "nodes": ["out", "out", "source", "body"]}]
    values = analysis.nodal(devices, synthetic_points(6.0, 2.0, 1.0), {"source": 1.0, "body": 0.0})
    assert values["out"] == pytest.approx(9 / 8)


def test_floating_source_row_obeys_current_conservation() -> None:
    devices = [{"alias": "synthetic", "nodes": ["drain", "gate", "source", "body"]}]
    values = analysis.nodal(
        devices,
        synthetic_points(6.0, 2.0, 1.0),
        {"drain": 0.0, "gate": 1.0, "body": 0.0},
    )
    assert values["source"] == pytest.approx(6 / 9)


@pytest.mark.parametrize("fault", ["missing", "identity", "negative", "boolean"])
def test_nodal_bad_evidence_rejected(fault: str) -> None:
    devices = [{"alias": "synthetic", "nodes": ["out", "input", "ground", "ground"]}]
    points = synthetic_points(6.0, 2.0)
    if fault == "identity":
        points[0]["alias"] = "wrong"
    else:
        points[0]["fields"]["gm"] = {"missing": None, "negative": -1.0, "boolean": True}[fault]
    with pytest.raises(ValueError):
        analysis.nodal(devices, points, {"input": 1.0, "ground": 0.0})


def test_independent_stage_arithmetic() -> None:
    fields = [{"gm": 4.0, "gds": 1.0} for _ in range(14)]
    first, second = analysis.stage_gain(fields)
    assert first == 2.0
    assert second == pytest.approx((4 + 4 * 4 / 6) / 2)


def test_zero_transconductance_has_zero_gain() -> None:
    assert analysis.divide(0.0, 1.0) == 0.0


@pytest.mark.parametrize("fault", ["result", "frame", "graph", "journal", "policy"])
def test_private_evidence_tampering_rejected_before_analysis(
    fault: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private = tmp_path / ".codex"
    private.mkdir()
    frame = b"synthetic preserved frame"
    graph = b"[]"
    result = {"measurement_frame_sha256": analysis.dc.digest(frame)}
    encoded = json.dumps(result).encode()
    journal = {
        "state": "succeeded",
        "policy_sha256": "synthetic_policy",
        "local_canonical_result_sha256": analysis.dc.digest(encoded),
    }
    monkeypatch.setattr(analysis.diag, "ROOT", tmp_path)
    monkeypatch.setattr(analysis.diag, "authority", lambda: "synthetic_policy")
    monkeypatch.setattr(analysis.diag, "validate_result", lambda *_: None)
    monkeypatch.setattr(analysis, "GRAPH_SHA", analysis.dc.digest(graph))
    if fault == "result":
        encoded += b" "
    elif fault == "frame":
        frame += b" "
    elif fault == "graph":
        graph += b" "
    elif fault == "journal":
        journal["state"] = "reserved"
    elif fault == "policy":
        journal["policy_sha256"] = "different_policy"
    (private / "ade-pvt-diag-v2-extract-result.json").write_bytes(encoded)
    (private / "ade-pvt-diag-v2-frame.private.txt").write_bytes(frame)
    (private / "ade-pvt-diag-v2-devices.private.json").write_bytes(graph)
    (private / "ade-pvt-diag-v2-extract.json").write_text(json.dumps(journal))
    with pytest.raises(ValueError, match="evidence drift"):
        analysis.run()
