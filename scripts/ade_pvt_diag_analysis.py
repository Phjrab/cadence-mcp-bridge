"""Local arithmetic on fixed preserved private MOS evidence; no remote execution."""

from __future__ import annotations

import json
import math
import sys
from typing import Any

import ade_pvt_diag as diag
import ade_pvt_qual as qual
import ade_qual as dc
import phase_campaign as campaign

GRAPH_SHA = "c23b33abf0dae4f838f14cc013dbc964f9a003dfc590883b935fa82137a04a44"
CORNER_ORDER = ("NN", "FF", "SS", "FS", "SF")


def divide(numerator: float, denominator: float) -> float | None:
    """Missing or nonpositive conductance must not become an infinite gain."""
    if not math.isfinite(numerator) or not math.isfinite(denominator):
        raise ValueError("nonfinite conductance")
    return numerator / denominator if denominator > 0 else None


def metrics(fields: dict[str, float | None]) -> dict[str, float | None]:
    def numeric(key: str) -> float | None:
        value = fields[key]
        if value is not None and not math.isfinite(value):
            raise ValueError("nonfinite operating point")
        return value

    gm, gds, vds, vdsat, current = (numeric(k) for k in ("gm", "gds", "vds", "vdsat", "id"))
    return {
        "abs_current_a": None if current is None else abs(current),
        "intrinsic_gain": None if gm is None or gds is None else divide(gm, gds),
        "headroom_v": None if vds is None or vdsat is None else abs(vds) - abs(vdsat),
        # Region is retained as a number. No undocumented code-to-name mapping.
        "region_code": numeric("region"),
    }


def solve(matrix: list[list[float]], rhs: list[float]) -> list[float]:
    """Partial-pivot Gaussian elimination for the small conductance matrix."""
    size = len(rhs)
    if not size or len(matrix) != size or any(len(row) != size for row in matrix):
        raise ValueError("conductance matrix shape")
    augmented = [list(row) + [value] for row, value in zip(matrix, rhs, strict=True)]
    if any(not math.isfinite(v) for row in augmented for v in row):
        raise ValueError("nonfinite conductance matrix")
    scale = max(abs(v) for row in matrix for v in row)
    for column in range(size):
        pivot = max(range(column, size), key=lambda i: abs(augmented[i][column]))
        if abs(augmented[pivot][column]) <= scale * 1e-14:
            raise ValueError("singular or unresolved conductance matrix")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        augmented[column] = [v / divisor for v in augmented[column]]
        for row in range(size):
            if row != column:
                factor = augmented[row][column]
                augmented[row] = [
                    a - factor * b for a, b in zip(augmented[row], augmented[column], strict=True)
                ]
    answer = [row[-1] for row in augmented]
    residual = max(
        abs(sum(a * x for a, x in zip(row, answer, strict=True)) - b)
        for row, b in zip(matrix, rhs, strict=True)
    )
    bound = max(max(abs(v) for v in rhs), scale * max(abs(v) for v in answer))
    if residual > max(1e-20, bound * 1e-10):
        raise ValueError("unresolved nodal residual")
    return answer


def nodal(
    devices: list[dict[str, Any]],
    points: list[dict[str, Any]],
    fixed: dict[str, float],
) -> dict[str, float]:
    """MOS-only DC linearization; currents follow the saved drain convention."""
    by_alias = {p["alias"]: p["fields"] for p in points}
    if len(by_alias) != len(points) or set(by_alias) != {d["alias"] for d in devices}:
        raise ValueError("nodal device identity")
    nodes = sorted({n for d in devices for n in d["nodes"]} - set(fixed))
    index = {node: i for i, node in enumerate(nodes)}
    matrix = [[0.0] * len(nodes) for _ in nodes]
    rhs = [0.0] * len(nodes)
    for device in devices:
        drain, gate, source, bulk = device["nodes"]
        f = by_alias[device["alias"]]
        gm, gds, gmbs = (f[k] for k in ("gm", "gds", "gmbs"))
        if any(type(v) not in (float, int) or not math.isfinite(v) for v in (gm, gds, gmbs)):
            raise ValueError("missing or nonfinite nodal conductance")
        if min(gm, gds, gmbs) < 0:
            raise ValueError("negative saved conductance")
        coefficients = ((drain, gds), (gate, gm), (source, -gds - gm - gmbs), (bulk, gmbs))
        for row_node, sign in ((drain, 1), (source, -1)):
            if row_node not in index:
                continue
            row = index[row_node]
            for column_node, value in coefficients:
                if column_node in index:
                    matrix[row][index[column_node]] += sign * value
                else:
                    rhs[row] -= sign * value * fixed[column_node]
    values = solve(matrix, rhs)
    return fixed | dict(zip(nodes, values, strict=True))


def stage_gain(fields: list[dict[str, Any]]) -> tuple[float, float]:
    """Symmetric half-circuit, checked independently against nodal stamping."""
    inp, bias_load, diode_n, output_n, diode_p, output_p = (fields[i] for i in (0, 8, 4, 7, 10, 11))
    first = divide(inp["gm"], inp["gds"] + bias_load["gds"])
    mirror = divide(diode_p["gm"], diode_n["gm"] + diode_n["gds"] + diode_p["gds"])
    if first is None or mirror is None:
        raise ValueError("undefined stage gain")
    second = divide(
        output_p["gm"] + output_n["gm"] * mirror,
        output_n["gds"] + output_p["gds"],
    )
    if second is None:
        raise ValueError("undefined output gain")
    return first, second


def run() -> dict[str, Any]:
    policy_sha = diag.authority()
    private = diag.ROOT / ".codex"
    source = private / "ade-pvt-diag-v2-extract-result.json"
    frame = private / "ade-pvt-diag-v2-frame.private.txt"
    graph = private / "ade-pvt-diag-v2-devices.private.json"
    if any(p.is_symlink() for p in (source, frame, graph)):
        raise ValueError("private evidence symlink")
    result = campaign._read_json(source)
    diag.validate_result(result, "extract")
    journal = campaign._read_json(diag.journal("extract"))
    if (
        journal.get("state") != "succeeded"
        or journal.get("policy_sha256") != policy_sha
        or journal.get("local_canonical_result_sha256") != dc.digest(source.read_bytes())
        or dc.digest(frame.read_bytes()) != result["measurement_frame_sha256"]
        or dc.digest(graph.read_bytes()) != GRAPH_SHA
    ):
        raise ValueError("private diagnostic evidence drift")
    devices = json.loads(graph.read_bytes())
    required = {"VDD", "VSS", "Vp", "Vm", devices[2]["nodes"][1], devices[8]["nodes"][1]}
    # Only gates with no drain/source connection are independent bias nodes.
    all_nodes = {n for d in devices for n in d["nodes"]}
    active_nodes = {d["nodes"][i] for d in devices for i in (0, 2)}
    if (
        len(required) != 6
        or required - all_nodes
        or all_nodes - active_nodes != required - active_nodes
    ):
        raise ValueError("fixed port/bias binding")
    fixed = dict.fromkeys(required, 0.0) | {"Vp": 0.5, "Vm": -0.5}
    rows = {}
    for corner in CORNER_ORDER:
        points = result["operating_points"][corner]
        voltages = nodal(devices, points, fixed)
        gain = abs(voltages["Vop"] - voltages["Vom"])
        first, second = stage_gain([p["fields"] for p in points])
        if not math.isclose(gain, first * second, rel_tol=1e-5):
            raise ValueError("independent gain arithmetic disagreement")
        rows[corner] = {
            "mos_metrics": {p["alias"]: metrics(p["fields"]) for p in points},
            "first_stage_gain_v_v": first,
            "second_stage_gain_v_v": second,
            "mos_only_nodal_gain_v_v": gain,
            "mos_only_nodal_gain_db": 20 * math.log10(gain),
            "half_circuit_gain_v_v": first * second,
        }
    return {
        "phase": "ADE-PVT-DIAG-01",
        "method": "preserved_mos_dc_linearization_no_simulation",
        "operating_point_units": {"id": "A", "gm_gds_gmbs": "S", "voltages": "V"},
        "region_semantics": "vendor_code_not_mapped",
        "policy_sha256": policy_sha,
        "frame_sha256": result["measurement_frame_sha256"],
        "private_graph_sha256": GRAPH_SHA,
        "new_spectre_attempts": 0,
        "spec_evaluation": "not_evaluated",
        "corners": rows,
    }


if __name__ == "__main__":
    try:
        if len(sys.argv) != 1:
            raise ValueError("fixed local analysis takes no arguments")
        output = run()
        saved = diag.ROOT / ".codex/ade-pvt-diag-v2-analysis.private.json"
        encoded = campaign._canonical(output)
        if saved.exists():
            if saved.read_bytes() != encoded:
                raise ValueError("preserved local analysis drift")
        else:
            qual.save_bytes(saved, encoded)
        print(
            json.dumps(
                {
                    k: {f: v for f, v in row.items() if f != "mos_metrics"}
                    for k, row in output["corners"].items()
                },
                sort_keys=True,
            )
        )
    except (OSError, ValueError, campaign.CampaignError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
