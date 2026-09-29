"""A pre-Spectre claim is resumed without counting a second baseline attempt."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
dc_v2 = importlib.import_module("phase_e_copied_dc_v2")


def test_v2_policy_pins_v1_claim_and_exact_files() -> None:
    policy = json.loads(dc_v2.POLICY.read_text(encoding="utf-8"))
    old = json.loads(dc_v2.previous.POLICY.read_text(encoding="utf-8"))
    assert policy["parent_policy_sha256"] == dc_v2._sha(dc_v2.v1._canonical(old))
    assert policy["v1_files"] == old["files"]
    assert policy["baseline_claim"] == dc_v2.previous.OPERATIONS["baseline"]
    assert policy["spectre_attempt_count_before_resume"] == 1
    for name, path in dc_v2.LOCAL_FILES.items():
        assert dc_v2._sha(path.read_bytes()) == policy["files"][name]
        assert b"\r" not in path.read_bytes()


def test_resume_requires_reserved_pre_spectre_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_read(path: Path) -> dict[str, str]:
        return {"state": "succeeded", "policy_sha256": "old-digest"}

    monkeypatch.setattr(dc_v2.parent, "_read_json", fake_read)
    with pytest.raises(dc_v2.CopiedDcV2Error, match="original baseline claim changed"):
        dc_v2._baseline_pre_execution(tmp_path, "old-digest")


def test_runner_uses_external_prepare_temp_and_existing_baseline() -> None:
    runner = dc_v2.LOCAL_FILES["run.sh"].read_text(encoding="ascii")
    helper = dc_v2.LOCAL_FILES["dc_helper.py"].read_text(encoding="ascii")
    assert 'case "$1" in baseline-resume) MODE=baseline' in runner
    assert 'before="$VERSION/.before.$$.tmp"' in runner
    assert '/usr/bin/python "$HELPER" prepare "$MODE" > "$before"' in runner
    assert 'mv -f "$before" "$JOB/before.json"' in runner
    assert 'if [ "$MODE" = candidate ]; then mkdir -m 700 "$JOB"; fi' in runner
    assert 'os.listdir(job) != ["before.json"]' in helper
    assert 'os.stat(job + "/before.json").st_size != 0' in helper
    assert '"V0 (VDD 0) vsource dc=1 type=dc"' in helper
    assert "timeout 120" in runner


def test_response_rejects_wrong_vdd_or_unbounded_psf() -> None:
    policy = json.loads(dc_v2.POLICY.read_text(encoding="utf-8"))
    payload = {
        "schema_version": 1,
        "plan_id": "WP14_FIXED_COPIED_DC_V1",
        "mode": "baseline",
        "source_sha256": policy["source_fingerprint_sha256"],
        "target_sha256": policy["copy_target_sha256"],
        "netlist_sha256": policy["circuit_netlist_sha256"],
        "model_sha256": policy["model_sha256"],
        "model_section": "NN",
        "temperature_c": 27,
        "vdd_v": 0.9,
        "input_vcm_v": 0.5,
        "bias_values_v": [0.3, 0.65],
        "protected_and_copy_unchanged": True,
        "simulation_run": True,
        "status": "dc_completed",
        "wrapper_sha256": "a" * 64,
        "psf_tree_sha256": "b" * 64,
        "psf_bytes": 1024,
    }
    with pytest.raises(dc_v2.CopiedDcV2Error, match="response mismatch"):
        dc_v2._check_response(json.dumps(payload).encode(), "baseline", policy)
    payload["vdd_v"] = 1.0
    payload["psf_bytes"] = 129 * 1024 * 1024
    with pytest.raises(dc_v2.CopiedDcV2Error, match="result bound invalid"):
        dc_v2._check_response(json.dumps(payload).encode(), "baseline", policy)
