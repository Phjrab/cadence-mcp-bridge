import json
from hashlib import sha256

import pytest

from cadence_mcp_bridge import ota_corrected_candidate_source as source
from cadence_mcp_bridge.domain_provisioning import _canonical

AC = b"simulator lang=spectre\nparameters VBIASN=0.320 VBIASP=702m\nac ac start=1 stop=1000\n"
DC = b"simulator lang=spectre\nparameters VBIASN=320m VBIASP=.702\ndcOp dc\n"
OLD_BIAS = b"simulator lang=spectre\nparameters VBIASN=300m VBIASP=650m\n"
OP = "10000000-0000-4000-8000-000000000001"


def _sha(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def _custody(ac: bytes, dc: bytes) -> bytes:
    def mode(name: str, raw: bytes) -> dict:
        base = f"/managed/{OP}/{name}"
        return dict(
            analysis=name, operation_id=OP, scope_sha256="1" * 64,
            saved_receipt_sha256=source._SAVE, dut_revision_sha256=source._DUT,
            testbench_revision_sha256=source._TB, isolated_bench_tree_sha256="2" * 64,
            isolated_state_tree_sha256="3" * 64, project_tree_sha256="4" * 64,
            registered_inputs_sha256="5" * 64, hnl_stdout_sha256="6" * 64,
            netlist_sha256=_sha(raw), state_path=base + "/state",
            project_path=base + "/project", input_path=base + "/project/input.scs",
            enabled_analyses=[name], netlisted=True,
        )

    return _canonical(dict(
        schema_version=1, kind="OTA17_HNL_ONLY_LOCKED_CUSTODY",
        writer_operation_id=source._WRITER, writer_scope_sha256=source._WRITER_SCOPE,
        writer_plan_sha256=source._PLAN, writer_terminal="OUTCOME_UNKNOWN",
        original_locked_sha256=source._OLD_LOCKED, original_failure_sha256=source._OLD_FAILURE,
        owned_copy_operation_id=source._COPY, operation_id=OP, scope_sha256="1" * 64,
        locked_postflight_sha256="7" * 64, native_intent_sha256="8" * 64,
        native_receipt_sha256="9" * 64, native_complete_sha256="a" * 64,
        reopened_cdf_sha256="b" * 64, reopened_footprint_sha256="c" * 64,
        owned_ade_sha256="d" * 64, source_preservation_sha256="e" * 64,
        model_closure_sha256="f" * 64, design_writes=0,
        diagnostics=dict(schema_version=1, ocean_invocations=1, spectre=0, reservations=0,
                         ac=mode("ac", ac), dc=mode("dc", dc)),
    ))


def _proof(custody: bytes, ac: bytes, dc: bytes) -> bytes:
    return _canonical(dict(
        schema_version=1, kind="OTA17_VERIFIED_DUAL_HNL_ELECTRICAL",
        custody_sha256=_sha(custody), ac_raw_sha256=_sha(ac), dc_raw_sha256=_sha(dc),
        ac_conditions_sha256="1" * 64, dc_conditions_sha256="2" * 64,
        ac_comparison_sha256=_sha(ac), dc_comparison_sha256=_sha(dc),
        reopened_cdf_sha256="b" * 64, verified_mos_count=17,
    ))


def _verify(custody: bytes, proof: bytes, ac: bytes, dc: bytes):
    return source.verify_ota_corrected_dual_hnl_source(
        custody, proof, ac, dc, expected_custody_sha256=_sha(custody),
        expected_electrical_sha256=_sha(proof),
    )


def test_exact_review_join_preserves_original_unknown():
    custody = _custody(AC, DC)
    result = _verify(custody, _proof(custody, AC, DC), AC, DC)
    assert result.writer_status == "OUTCOME_UNKNOWN"
    assert result.custody.operation_id == OP
    assert result.custody.diagnostics.ac.netlist_sha256 == _sha(AC)
    assert result.analysis_authorized is False


@pytest.mark.parametrize("bad", [
    OLD_BIAS,
    AC.replace(b"VBIASN=0.320", b"VBIASN=0.320 VBIASN=0.320"),
    AC.replace(b"VBIASP=702m", b"VBIASP=0.702+0"),
])
def test_independently_repinned_bad_bias_rejected(bad):
    custody = _custody(bad, DC)
    with pytest.raises(ValueError, match="ota_corrected_hnl_(bias_mismatch|parameters)"):
        _verify(custody, _proof(custody, bad, DC), bad, DC)


def test_distinct_original_bytes_and_complete_electrical_review_required():
    custody = _custody(AC, DC)
    proof = _proof(custody, AC, DC)
    with pytest.raises(ValueError, match="ota_corrected_hnl_raw_binding"):
        _verify(custody, proof, DC, AC)
    partial = json.loads(proof)
    del partial["dc_conditions_sha256"]
    with pytest.raises(ValueError, match="dc_conditions_sha256"):
        _verify(custody, _canonical(partial), AC, DC)


def test_fresh_operation_must_own_both_leaves():
    modified = json.loads(_custody(AC, DC))
    modified["diagnostics"]["dc"]["operation_id"] = source._WRITER
    custody = _canonical(modified)
    with pytest.raises(ValueError, match="ota_corrected_hnl_mode_binding"):
        _verify(custody, _proof(custody, AC, DC), AC, DC)
