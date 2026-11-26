import json
from dataclasses import replace
from hashlib import sha256

import pytest

from cadence_mcp_bridge import ota_corrected_candidate_source as source
from cadence_mcp_bridge.domain_provisioning import _canonical

AC = b"simulator lang=spectre\nparameters VBIASN=0.320 VBIASP=702m\nac ac start=1 stop=1000\n"
DC = b"simulator lang=spectre\nparameters VBIASN=320m VBIASP=.702\ndcOp dc\n"
OLD_BIAS = b"simulator lang=spectre\nparameters VBIASN=300m VBIASP=650m\n"


def _sha(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def _artifacts(monkeypatch, ac=AC, dc=DC, *, dc_state=None):
    operation = source._HNL_OPERATION
    job_root = "/managed/native-mcp-v1-jobs"
    views = dict(dut=source._DUT, bench=source._TB, state="1" * 64, symbol="2" * 64)
    counter = dict(campaign_id="AUTO-PHASE-01", count=153, result_reserved_bytes=18_166_579_200)
    fixed = dict(VBIASN="0.32", VBIASP="0.702")
    saved = _canonical(dict(operation_id=source._WRITER, scope_sha256=source._WRITER_SCOPE,
                            plan_sha256=source._PLAN))
    failure = _canonical(dict(
        operation_id=source._WRITER, phase="INDEPENDENT_REOPEN_NETLIST", status="OUTCOME_UNKNOWN",
    ))
    cdf = b"M2_CDF_V2\nCOMPLETE\n"
    locked = _canonical(dict(
        views=views, counter=counter, phases={
            "edit": {"receipt.json": {"sha256": _sha(saved)}},
            "reopen": {"failure.json": {"sha256": _sha(failure)}},
        }, retained_inputs={"cdf": {"sha256": _sha(cdf)}},
    ))
    for key, raw in (("_SAVE", saved), ("_OLD_LOCKED", locked), ("_OLD_FAILURE", failure),
                     ("_OLD_CDF", cdf)):
        monkeypatch.setattr(source, key, _sha(raw))
    program = "3" * 64
    scope = _canonical(dict(
        purpose="OTA17_FIXED_BIAS_DETACHED_DUAL_HNL", operation_id=operation,
        writer_operation_id=source._WRITER, observed_terminal_sha256=_sha(locked),
        saved_receipt_sha256=_sha(saved), fixed_parameters=fixed, counter=counter, views=views,
        ocean_max=1, new_external_copies=0, spectre_max=0, reservations_max=0,
        valid_until_unix=2_000_000_000, job_root=job_root, program_context_sha256=program,
        scratch_cap_bytes=2_097_152, stock_projection_bytes=1_908_736,
    ))
    preflight = _canonical(dict(
        status="OTA17_FIXED_BIAS_DUAL_HNL_PREFLIGHT", operation_id=operation,
        scope_sha256=_sha(scope), counter=counter, scope_cap_bytes=2_097_152,
        stock_projection_bytes=1_908_736, ocean=0, spectre=0, reservations=0, external_copies=0,
    ))
    modes = {}
    stdout = []
    for mode, alias, raw in (("ac", "MCP_GREL_Work", ac), ("dc", "MCP_GREL_WorkDc", dc)):
        area = f"{job_root}/{operation}/{mode}"
        state_path = f"{area}/state-root/{alias}/Grel_{operation.replace('-', '_')}/spectre/state1"
        modes[mode] = dict(
            mode=mode, raw_sha256=_sha(raw), raw_path=f"{area}/project/netlist/input.scs",
            project=f"{area}/project",
            state_path=dc_state if mode == "dc" and dc_state else state_path,
            bench_tree_sha256="4" * 64, state_sha256="5" * 64, static_sha256="6" * 64,
            fixed_parameters=fixed,
        )
        token = _sha(f"{program}|{mode}".encode())
        stdout.extend([f"MCP_GENERIC_ADE_NETLIST|{token}|{operation}",
                       f"OTA17_CORRECTED_HNL_MODE_CLOSED|{mode}|{token}|{operation}"])
    logs = ("\n".join(stdout) + "\n").encode()
    intent = _canonical(dict(operation_id=operation, scope_sha256=_sha(scope), retry=False))
    receipt = _canonical(dict(
        status="OTA17_FIXED_BIAS_DUAL_HNL_CAPTURED", operation_id=operation,
        scope_sha256=_sha(scope), writer_operation_id=source._WRITER,
        saved_receipt_sha256=_sha(saved),
        source_views=views, original_failed_terminal_sha256=_sha(locked), stdout_sha256=_sha(logs),
        intent_sha256=_sha(intent), mode_evidence=modes, counter=counter,
        ocean=1, spectre=0, reservations=0, external_copies=0,
    ))
    return source.OtaCorrectedHnlArtifacts(
        scope, preflight, receipt, _canonical({"receipt_sha256": _sha(receipt)}),
        logs, saved, locked, failure, cdf,
    )


def _proof(artifacts, ac, dc):
    return _canonical(dict(
        schema_version=1, kind="OTA17_VERIFIED_DUAL_HNL_ELECTRICAL",
        custody_sha256=_sha(artifacts.receipt), ac_raw_sha256=_sha(ac), dc_raw_sha256=_sha(dc),
        ac_conditions_sha256="1" * 64, dc_conditions_sha256="2" * 64,
        ac_comparison_sha256=_sha(ac), dc_comparison_sha256=_sha(dc),
        reopened_cdf_sha256=_sha(artifacts.original_reopened_cdf), verified_mos_count=17,
    ))


def _verify(artifacts, proof, ac=AC, dc=DC):
    return source.verify_ota_corrected_dual_hnl_source(
        artifacts, proof, ac, dc, expected_scope_sha256=_sha(artifacts.scope),
        expected_preflight_sha256=_sha(artifacts.preflight),
        expected_custody_sha256=_sha(artifacts.receipt), expected_electrical_sha256=_sha(proof),
    )


def test_exact_native_receipt_join_preserves_original_unknown(monkeypatch):
    artifacts = _artifacts(monkeypatch)
    result = _verify(artifacts, _proof(artifacts, AC, DC))
    assert result.writer_status == "OUTCOME_UNKNOWN"
    assert result.custody.operation_id == source._HNL_OPERATION
    assert result.custody.mode_evidence.ac.raw_sha256 == _sha(AC)
    assert result.valid_until_unix == 2_000_000_000
    assert result.analysis_authorized is False


@pytest.mark.parametrize("bad", [
    OLD_BIAS,
    AC.replace(b"VBIASN=0.320", b"VBIASN=0.320 VBIASN=0.320"),
    AC.replace(b"VBIASP=702m", b"VBIASP=0.702+0"),
])
def test_independently_repinned_bad_bias_rejected(monkeypatch, bad):
    artifacts = _artifacts(monkeypatch, bad)
    with pytest.raises(ValueError, match="ota_corrected_hnl_(bias_mismatch|parameters)"):
        _verify(artifacts, _proof(artifacts, bad, DC), bad, DC)


def test_original_completion_transcript_and_mode_paths_must_match(monkeypatch):
    artifacts = _artifacts(monkeypatch)
    proof = _proof(artifacts, AC, DC)
    with pytest.raises(ValueError, match="ota_corrected_hnl_lineage"):
        _verify(replace(artifacts, complete=b"{}"), proof)
    with pytest.raises(ValueError, match="ota_corrected_hnl_mode_custody"):
        _verify(replace(artifacts, stdout=b"wrong"), proof)
    invalid = _artifacts(monkeypatch, dc_state="/managed/original-writer/state")
    with pytest.raises(ValueError, match="ota_corrected_hnl_mode_binding"):
        _verify(invalid, _proof(invalid, AC, DC))


def test_original_bytes_and_complete_electrical_review_required(monkeypatch):
    artifacts = _artifacts(monkeypatch)
    proof = _proof(artifacts, AC, DC)
    with pytest.raises(ValueError, match="ota_corrected_hnl_raw_binding"):
        _verify(artifacts, proof, DC, AC)
    partial = json.loads(proof)
    del partial["dc_conditions_sha256"]
    with pytest.raises(ValueError, match="dc_conditions_sha256"):
        _verify(artifacts, _canonical(partial))
