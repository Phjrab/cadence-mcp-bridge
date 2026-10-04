"""Synthetic verification of the bounded native bias phase."""

from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from test_native_diagnostics import remote_module

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
operator = importlib.import_module("bias_headroom")
SAVED = (
    b'tmp1->name = "VBIASN"\ntmp1->expression = "300m"\n'
    b'tmp2->name = "VBIASP"\ntmp2->expression = "650m"\n'
)


def test_retired_v1_cannot_submit_another_job() -> None:
    with pytest.raises(ValueError, match="v1 execution retired"):
        operator.operate("submit", 1)


@pytest.mark.parametrize("pair", range(4))
def test_exact_pair_substitution_including_saved_identity(pair: int) -> None:
    mod = remote_module("bias-headroom-v1")
    mod.PAIR = pair
    result = mod.candidate_variables(SAVED)
    for value in mod.PAIRS[pair]:
        assert f'"{value}m"'.encode() in result
    assert (result == SAVED) is (pair == 2)


@pytest.mark.parametrize("fault", [b'300m" extra', b"301m", b"NaN", b"$(id)"])
def test_saved_variable_drift_or_injection(fault: bytes) -> None:
    mod = remote_module("bias-headroom-v1")
    mod.PAIR = 0
    with pytest.raises(ValueError):
        mod.candidate_variables(SAVED.replace(b"300m", fault))


def frame(mod: Any, margin: float = 0.1) -> str:
    lines = ["BEGIN"]
    for i in range(1, 15):
        for field in mod.FIELDS:
            value = 0.2 + margin if field == "vds" else 0.2 if field == "vdsat" else 0.0
            lines.append(f"OP|mos{i:02d}|{field}|{value}")
    return "\n".join([*lines, "END"]) + "\n"


@pytest.mark.parametrize("fault", ["none", "nan", "inf", "missing", "alias", "order", "huge"])
def test_fixed_numeric_op_inventory(fault: str) -> None:
    mod = remote_module("bias-headroom-v1")
    raw = frame(mod)
    if fault in ("nan", "inf", "huge"):
        raw = raw.replace(
            "|id|0.0", "|id|" + {"nan": "nan", "inf": "inf", "huge": "1e13"}[fault], 1
        )
    elif fault == "missing":
        raw = raw.replace("END\n", "")
    elif fault == "alias":
        raw = raw.replace("mos01", "mos02", 1)
    elif fault == "order":
        raw = raw.replace("|gm|", "|gds|", 1)
    if fault == "none":
        parsed = mod.parse_op(raw)
        assert len(parsed) == 14
        assert mod.op_summary(parsed)["negative_headroom_devices"] == 0
        assert mod.op_summary(parsed)["minimum_headroom_v"] == pytest.approx(0.1)
    else:
        with pytest.raises(ValueError):
            mod.parse_op(raw)


def screens(mod: Any, tmp_path: Path, margins: list[tuple[float, float]]) -> dict[Any, str]:
    requests = {}
    for pair, corners in enumerate(margins):
        for corner, margin in zip(("FF", "FS"), corners, strict=True):
            path = tmp_path / str(uuid4())
            work = path / "work"
            work.mkdir(parents=True)
            raw = frame(mod, margin).encode()
            (work / "op-frame.txt").write_bytes(raw)
            (work / "stage").write_bytes(b"succeeded\n")
            (work / "scalars.txt").write_bytes(b"synthetic")
            data = {
                "job_id": path.name,
                "quality": "valid",
                "pair_index": pair,
                "corner": corner,
                "analysis": "dc",
                "vdd_v": 1.0,
                "spec_evaluation": "not_evaluated",
                "operating_points": mod.parse_op(raw.decode()),
                "op_frame_sha256": mod.BASE.sha(raw),
                "measurement_frame_sha256": mod.BASE.sha(b"synthetic"),
                "psf_sha256": "synthetic-psf",
                "scalars": [],
            }
            (work / "result.json").write_text(json.dumps(data), encoding="utf-8")
            requests[pair, corner, "dc"] = str(path)
    mod.BASE.guard = lambda: SimpleNamespace(dc_result=lambda _: [])
    mod.CAND.tree = lambda _: {"sha256": "synthetic-psf"}
    return requests


def test_selection_requires_both_corners_and_uses_deterministic_tie(tmp_path: Path) -> None:
    mod = remote_module("bias-headroom-v1")
    requests = screens(mod, tmp_path, [(0.3, -0.4), (0.1, 0.1), (0.1, 0.1), (-0.18, -0.4)])
    result = mod.selection(requests)
    assert result["selected_pair_index"] == 1
    assert result["spec_evaluation"] == "not_evaluated"


def test_no_improvement_is_not_pass(tmp_path: Path) -> None:
    mod = remote_module("bias-headroom-v1")
    requests = screens(mod, tmp_path, [(-0.18, -0.4)] * 4)
    assert mod.selection(requests)["selected_pair_index"] is None


@pytest.mark.parametrize(
    "fault", ["missing", "stage", "op", "scalar", "psf", "quality", "identity"]
)
def test_selection_rejects_missing_or_tampered_evidence(tmp_path: Path, fault: str) -> None:
    mod = remote_module("bias-headroom-v1")
    requests = screens(mod, tmp_path, [(0.1, 0.1)] * 4)
    path = Path(requests[0, "FF", "dc"]) / "work"
    if fault == "missing":
        del requests[0, "FF", "dc"]
    elif fault == "stage":
        (path / "stage").write_bytes(b"extracting\n")
    elif fault in ("op", "scalar"):
        (path / ("op-frame.txt" if fault == "op" else "scalars.txt")).write_bytes(b"changed")
    elif fault == "psf":
        mod.CAND.tree = lambda _: {"sha256": "changed"}
    else:
        data = json.loads((path / "result.json").read_bytes())
        data["quality" if fault == "quality" else "job_id"] = "changed"
        (path / "result.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError):
        mod.selection(requests)


def test_phase_usage_duplicate_and_maximum(tmp_path: Path) -> None:
    mod = remote_module("bias-headroom-v1")
    mod.JOBS = str(tmp_path)
    mod.N.contained = lambda _: None
    for index in range(8):
        path = tmp_path / str(uuid4())
        (path / "work").mkdir(parents=True)
        (path / "request.json").write_text(
            json.dumps(
                {
                    "pair_index": index // 2,
                    "corner": ("FF", "FS")[index % 2],
                    "analysis": "dc",
                    "revision_id": mod.N.REVISION,
                    "operating_point_id": mod.N.OPERATING_POINT,
                }
            ),
            encoding="utf-8",
        )
        (path / "work/attempt-reserved").write_text("{}", encoding="utf-8")
    assert mod.usage()[0] == 8
    duplicate = tmp_path / str(uuid4())
    duplicate.mkdir()
    (duplicate / "request.json").write_bytes(next(tmp_path.glob("*/request.json")).read_bytes())
    with pytest.raises(ValueError):
        mod.usage()


def test_nn_model_binding_and_invalid_corner() -> None:
    mod = remote_module("bias-headroom-v1")
    mod.BASE.MODEL = "/synthetic/model.scs"
    mod.os = SimpleNamespace(path=SimpleNamespace(realpath=lambda p: p))
    raw = ('(("' + mod.BASE.MODEL + '" "NN"))\n').encode()
    assert mod.corner_model(raw, "NN") == raw
    assert b'"FS"' in mod.corner_model(raw, "FS")
    with pytest.raises(ValueError):
        mod.corner_model(raw, "TT")


@pytest.mark.parametrize(
    "key,value",
    [
        ("corner", "FF;id"),
        ("analysis", "tran"),
        ("pair_index", True),
        ("pair_index", 4),
        ("job_id", "$(id)"),
    ],
)
def test_operator_transport_closed_arguments(key: str, value: Any) -> None:
    row = {"job_id": str(uuid4()), "corner": "FF", "analysis": "dc", "pair_index": 0}
    row[key] = value
    with pytest.raises(ValueError):
        operator.fixed_command("submit", row)


def test_prepare_uses_owned_pair_guard_and_native_templates() -> None:
    mod = remote_module("bias-headroom-v1")
    # Emulate POSIX rename locally, without changing os for any other test.
    paths = SimpleNamespace(**(vars(os.path) | {"realpath": lambda p: p}))
    mod.os = SimpleNamespace(**(vars(os) | {"rename": os.replace, "path": paths}))
    mod.N.os = mod.os
    mod.configure(str(uuid4()), "dc", "NN", "2")
    assert mod.P.preflight is mod.preflight
    assert mod.CAND.candidate_variables is mod.candidate_variables
    assert mod.BASE.validate_netlist is mod.P.validate_netlist
    assert mod.BASE.reserve is mod.LIMIT.reserve
    assert mod.N.VERSION == mod.VERSION
    assert mod.CAND.CANDIDATE == {"VBIASN": 0.3, "VBIASP": 0.65}
