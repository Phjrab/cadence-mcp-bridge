"""Local recovery accepts exact finite AC data without repeating EDA work."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
recover = importlib.import_module("phase_j_ac_scalar_recover")


def _sample_frame(output_gain: float = 8863.0) -> bytes:
    lines = list(recover.STAGES)
    for signal, real_part in (
        ("Vop", output_gain / 2),
        ("Vom", -output_gain / 2),
        ("Vp", 0.5),
        ("Vm", -0.5),
    ):
        lines.append(f"MCP_AC_VECTOR|{signal}|3|3")
        for index, freq in enumerate((1000, 10000)):
            lines.append(f"MCP_AC_POINT|{signal}|{index}|{freq}|{real_part}|0")
    lines.append("MCP_AC_POINT_COMPLETE|true")
    return ("\n".join(lines) + "\n").encode("ascii")


def test_policy_pins_v2_failure_and_existing_psf() -> None:
    policy = json.loads(recover.POLICY.read_text(encoding="utf-8"))
    old = json.loads(recover.previous.POLICY.read_text(encoding="utf-8"))
    assert policy["parent_policy_sha256"] == recover._sha(recover.v1._canonical(old))
    assert policy["private_artifact_sha256"] == recover.PRIVATE_HASHES
    assert policy["ac_psf_file_sha256"] == recover.PSF_FILES
    assert policy["ac_psf_tree_sha256"] == old["psf_tree_sha256"]
    assert policy["spectre_attempt_count"] == 3
    assert policy["new_eda_execution"] is False
    assert policy["remote_write"] is False


def test_authority_refuses_nonreserved_v2_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = json.loads(recover.previous.POLICY.read_text(encoding="utf-8"))
    base = json.loads(recover.v1.POLICY.read_text(encoding="utf-8"))
    monkeypatch.setattr(
        recover.previous,
        "_authority",
        lambda: (old, recover.PARENT_POLICY_SHA256, tmp_path, base),
    )
    monkeypatch.setattr(
        recover.parent,
        "_read_json",
        lambda _path: {"state": "succeeded", "policy_sha256": recover.PARENT_POLICY_SHA256},
    )
    with pytest.raises(recover.AcScalarRecoveryError, match="v2 read state changed"):
        recover._authority()


def test_exact_frame_accepts_high_finite_small_signal_gain() -> None:
    points = recover._parse_scalars(_sample_frame())
    assert [point["gain_v_per_v"] for point in points] == [8863.0, 8863.0]
    assert all(point["input_diff_mag_v"] == 1.0 for point in points)


def test_parser_rejects_wrong_input_or_point_frequency() -> None:
    wrong_input = _sample_frame().replace(
        b"MCP_AC_POINT|Vm|0|1000|-0.5|0", b"MCP_AC_POINT|Vm|0|1000|0|0"
    )
    with pytest.raises(recover.AcScalarRecoveryError, match="input magnitude changed"):
        recover._parse_scalars(wrong_input)
    wrong_frequency = _sample_frame().replace(
        b"MCP_AC_POINT|Vop|1|10000", b"MCP_AC_POINT|Vop|1|9000"
    )
    with pytest.raises(recover.AcScalarRecoveryError, match="AC point invalid"):
        recover._parse_scalars(wrong_frequency)
