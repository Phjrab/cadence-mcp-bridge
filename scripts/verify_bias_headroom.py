"""Independent arithmetic on privately preserved finite bias measurement frames."""

from __future__ import annotations

import cmath
import json
import math
from typing import Any

import ade_qual as dc
import bias_headroom_v2 as execution
import phase_campaign as campaign

ROOT = execution.ROOT


def equal(actual: float, expected: float) -> None:
    if (
        not math.isfinite(actual)
        or not math.isfinite(expected)
        or not math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-10)
    ):
        raise ValueError("independent arithmetic mismatch")


def verify_dc(raw: str, op: str, data: dict[str, Any]) -> dict[str, Any]:
    rows = raw.splitlines()
    if len(rows) != 6 or rows[-1] != "MCP_DC_SCALAR_COMPLETE|true":
        raise ValueError("independent DC frame shape")
    values = {}
    for row, signal in zip(rows[:5], ("Vop", "Vom", "VDD", "Vp", "Vm"), strict=True):
        fields = row.split("|")
        if len(fields) != 3 or fields[:2] != ["MCP_DC_SCALAR", signal]:
            raise ValueError("independent DC signal")
        values[signal] = float(fields[2])
    scalars = {v["logical_id"]: v["value"] for v in data["scalars"]}
    for signal in values:
        equal(values[signal], scalars[signal.lower()])
    equal(values["VDD"], 1.0)
    equal((values["Vp"] + values["Vm"]) / 2, 0.5)
    equal((values["Vop"] + values["Vom"]) / 2, scalars["output_common_mode"])
    equal(values["Vop"] - values["Vom"], scalars["output_differential"])
    rows = op.splitlines()
    if len(rows) != 142 or rows[0] != "BEGIN" or rows[-1] != "END":
        raise ValueError("independent OP frame shape")
    cursor, margins = 1, []
    field_names = ("id", "gm", "gds", "gmbs", "vgs", "vds", "vbs", "vth", "vdsat", "region")
    for index, point in enumerate(data["operating_points"]):
        op_fields: dict[str, float] = {}
        if point["alias"] != f"mos{index + 1:02d}":
            raise ValueError("independent OP alias")
        for name in field_names:
            parts = rows[cursor].split("|")
            cursor += 1
            if len(parts) != 4 or parts[:3] != ["OP", point["alias"], name]:
                raise ValueError("independent OP identity")
            op_fields[name] = float(parts[3])
            equal(op_fields[name], point["fields"][name])
        margins.append(abs(op_fields["vds"]) - abs(op_fields["vdsat"]))
    if len(margins) != 14 or cursor != 141:
        raise ValueError("independent OP inventory")
    minimum, negatives = min(margins), sum(v < 0 for v in margins)
    equal(minimum, data["headroom"]["minimum_headroom_v"])
    if negatives != data["headroom"]["negative_headroom_devices"]:
        raise ValueError("independent negative headroom count")
    return {
        "output_common_mode_v": scalars["output_common_mode"],
        "output_differential_v": scalars["output_differential"],
        "minimum_headroom_mv": minimum * 1000,
        "negative_headroom_devices": negatives,
    }


def verify_ac(raw: str, data: dict[str, Any]) -> dict[str, Any]:
    rows = raw.splitlines()
    if (
        rows[:3]
        != ["MCP_AC_STAGE|file_open", "MCP_AC_STAGE|results_open", "MCP_AC_STAGE|ac_selected"]
        or rows[-1] != "MCP_AC_POINT_COMPLETE|true"
    ):
        raise ValueError("independent AC frame markers")
    vectors, cursor, axis = {}, 3, None
    for signal in ("Vop", "Vom", "Vp", "Vm"):
        if rows[cursor].split("|") != ["MCP_AC_VECTOR", signal, "71", "71"]:
            raise ValueError("independent AC vector")
        cursor += 1
        frequencies, vector = [], []
        for index in range(71):
            row = rows[cursor].split("|")
            cursor += 1
            if len(row) != 6 or row[:3] != ["MCP_AC_POINT", signal, str(index)]:
                raise ValueError("independent AC point")
            frequency, real, imag = map(float, row[3:])
            if not math.isclose(frequency, 10 * 10 ** (index / 10), rel_tol=1e-6):
                raise ValueError("independent AC frequency")
            frequencies.append(frequency)
            vector.append(complex(real, imag))
        if axis is not None and frequencies != axis:
            raise ValueError("independent AC common axis")
        axis, vectors[signal] = frequencies, vector
    if cursor != len(rows) - 1 or len(data["spectrum"]) != 71 or axis is None:
        raise ValueError("independent AC point count")
    for index, item in enumerate(data["spectrum"]):
        equal(vectors["Vp"][index].real, 0.5)
        equal(vectors["Vm"][index].real, -0.5)
        equal(vectors["Vp"][index].imag, 0)
        equal(vectors["Vm"][index].imag, 0)
        gain = (vectors["Vop"][index] - vectors["Vom"][index]) / (
            vectors["Vp"][index] - vectors["Vm"][index]
        )
        equal(item["frequency_hz"], axis[index])
        equal(item["gain_v_per_v"], abs(gain))
        equal(item["gain_db"], 20 * math.log10(abs(gain)))
        equal(item["phase_deg"], math.degrees(cmath.phase(gain)))
    first = data["spectrum"][0]
    return {
        "gain_10hz_v_per_v": first["gain_v_per_v"],
        "gain_10hz_db": first["gain_db"],
        "phase_10hz_deg": first["phase_deg"],
        "points_checked": 71,
    }


def run() -> dict[str, Any]:
    execution.authority()
    records: dict[int, Any] = {}
    for index in range(16):
        data = campaign._read_json(
            ROOT / f".codex/bias-headroom-v2-job-{index:02d}-result.private.json"
        )
        frame = ROOT / f".codex/bias-headroom-v2-job-{index:02d}-frame.private.txt"
        if dc.digest(frame.read_bytes()) != data["measurement_frame_sha256"]:
            raise ValueError("preserved private frame drift")
        if index < 11:
            op = ROOT / f".codex/bias-headroom-v2-job-{index:02d}-op.private.txt"
            if dc.digest(op.read_bytes()) != data["op_frame_sha256"]:
                raise ValueError("preserved private OP frame drift")
            result = verify_dc(frame.read_text("ascii"), op.read_text("ascii"), data)
        else:
            result = verify_ac(frame.read_text("ascii"), data)
        records[index] = {"corner": data["corner"], "pair_index": data["pair_index"], **result}
    baseline = campaign._read_json(ROOT / ".codex/ade-pvt-diag-v2-analysis.private.json")
    scores = []
    for pair in range(4):
        rows = [records[pair * 2], records[pair * 2 + 1]]
        eligible = True
        for row in rows:
            margins = [
                m["headroom_v"] for m in baseline["corners"][row["corner"]]["mos_metrics"].values()
            ]
            eligible &= (row["negative_headroom_devices"], -row["minimum_headroom_mv"] / 1000) < (
                sum(m < 0 for m in margins),
                -min(margins),
            )
        if eligible:
            scores.append(
                (
                    max(r["negative_headroom_devices"] for r in rows),
                    -min(r["minimum_headroom_mv"] for r in rows),
                    pair,
                )
            )
    selected = min(scores)[2] if scores else None
    if selected != campaign._read_json(execution.SELECTION)["selected_pair_index"]:
        raise ValueError("independent selection differs")
    return {
        "state": "verified",
        "selected_pair_index": selected,
        "records": records,
        "dc_op_fields_checked": 1540,
        "ac_points_checked": 355,
        "spec_evaluation": "not_evaluated",
    }


if __name__ == "__main__":
    value = run()
    dc.save_new(ROOT / ".codex/bias-headroom-v2-independent-analysis.private.json", value)
    print(json.dumps(value, sort_keys=True))
