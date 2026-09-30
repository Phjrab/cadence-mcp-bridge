"""Owned-state candidate substitution, provenance, bounds and replay."""

from __future__ import annotations

import importlib
import json
import re
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
from test_native_ac_tran import helper as load_native_fixture
from test_native_ac_tran import native_input

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
operator = importlib.import_module("native_candidate")


@pytest.fixture
def candidate() -> Any:
    module: Any = ModuleType("candidate_test")
    load: Any = load_native_fixture
    module.NATIVE = load.__wrapped__()
    source = (operator.LOCAL / "helper.py").read_text()
    source = source.replace("import imp\n", "")
    source = source.replace(
        'NATIVE = imp.load_source("candidate_native_guard", ROOT + '
        '"/phase-campaign/native-ac-tran-v4/helper.py")',
        "",
    )
    exec(compile(source, "candidate.py", "exec"), module.__dict__)
    return module


def variables() -> bytes:
    return (
        b'tmp0->name = "VBIASN"\ntmp0->expression = "300m"\n'
        b'tmp1->name = "VBIASP"\ntmp1->expression = "650m"\n'
        b'unchanged_metadata = "synthetic"\n'
    )


def test_owned_variable_substitution_preserves_other_bytes(candidate: Any) -> None:
    before = variables()
    after = candidate.candidate_variables(before)
    assert after == before.replace(b'"300m"', b'"320m"').replace(b'"650m"', b'"702m"')
    assert before == variables()


@pytest.mark.parametrize("fault", ["none", "candidate", "other", "source", "proof"])
def test_owned_state_checks_exact_change_and_protected_source(
    candidate: Any,
    tmp_path: Path,
    fault: str,
) -> None:
    base = candidate.BASE
    candidate.configure("dc")
    base.STATE = str(tmp_path / "original")
    base.COPIED_STATE = str(tmp_path / "owned")
    base.JOB = str(tmp_path / "job")
    for root in (base.STATE, base.COPIED_STATE, base.JOB):
        Path(root).mkdir()
    original = variables()
    changed = candidate.candidate_variables(original)
    Path(base.STATE, "variables").write_bytes(original)
    Path(base.JOB, "source-variables.bin").write_bytes(original)
    Path(base.COPIED_STATE, "variables").write_bytes(changed)
    for root in (base.STATE, base.COPIED_STATE):
        Path(root, "ADE_state.info").write_bytes(b"routing")
        Path(root, "other").write_bytes(b"original")
    proof = {
        "source_variables_sha256": base.sha(original),
        "owned_variables_sha256": base.sha(changed),
        "requested_variables_v": candidate.CANDIDATE,
        "source_variables_v": candidate.SAVED,
    }
    baseline = {"source_sha256": "synthetic"}
    base.snapshot = lambda: baseline.copy()
    base.state_facts = lambda: {"variables_v": candidate.SAVED.copy()}
    candidate.verify_predecessors = lambda: None
    before = {
        **baseline,
        "state_facts": base.state_facts(),
        "state_copy_info_sha256": base.sha(b"routing"),
    }
    if fault == "candidate":
        Path(base.COPIED_STATE, "variables").write_bytes(original)
    elif fault == "other":
        Path(base.COPIED_STATE, "other").write_bytes(b"drift")
    elif fault == "source":
        baseline["source_sha256"] = "drift"
    elif fault == "proof":
        proof["owned_variables_sha256"] = "drift"
    Path(base.JOB, "candidate-state.json").write_text(json.dumps(proof))
    if fault == "none":
        candidate.verify_protected(before)
    else:
        with pytest.raises(ValueError):
            candidate.verify_protected(before)


@pytest.mark.parametrize("fault", ["duplicate", "missing", "extra", "bias", "name", "expression"])
def test_variable_copy_rejects_ambiguous_or_changed_source(candidate: Any, fault: str) -> None:
    data = variables()
    if fault == "duplicate":
        data += b'tmp0->expression = "300m"\n'
    elif fault == "missing":
        data = data.replace(b'tmp1->expression = "650m"\n', b"")
    elif fault == "extra":
        data += b'tmp2->name = "extra"\ntmp2->expression = "1"\n'
    elif fault == "bias":
        data = data.replace(b'"300m"', b'"320m"')
    elif fault == "name":
        data = data.replace(b'"VBIASP"', b'"VBIASN"')
    else:
        data = data.replace(b'"650m"', b'"650m+1"')
    with pytest.raises(ValueError):
        candidate.candidate_variables(data)


@pytest.mark.parametrize("analysis", ["dc", "ac", "tran"])
@pytest.mark.parametrize("fault", ["none", "candidate", "saved", "supply", "topology"])
def test_candidate_netlist_is_verified_separately_from_saved_facts(
    candidate: Any,
    analysis: str,
    fault: str,
) -> None:
    native = candidate.NATIVE
    text, circuit, facts = native_input(native, "ac" if analysis == "dc" else analysis)
    if analysis == "dc":
        text = text[: text.index("simulatorOptions")] + native.BASE.NATIVE_CONTROL + "\n"
    text = text.replace("VBIASN=300m VBIASP=650m", "VBIASN=320m VBIASP=702m")
    previous = circuit
    candidate.configure(analysis)
    if fault == "candidate":
        text = text.replace("702m", "703m")
    elif fault == "saved":
        facts["variables_v"] = candidate.CANDIDATE
    elif fault == "supply":
        previous = circuit = circuit.replace("dc=1", "dc=2")
        text = text.replace("dc=1", "dc=2")
    elif fault == "topology":
        circuit = circuit.replace("ampl=50m", "ampl=40m")
        text = text.replace("ampl=50m", "ampl=40m")
    if fault == "none":
        assert candidate.validate_netlist(text, circuit, previous, facts) == (
            "dcOp" if analysis == "dc" else analysis
        )
        assert facts["variables_v"] == candidate.SAVED
    else:
        with pytest.raises(ValueError):
            candidate.validate_netlist(text, circuit, previous, facts)


def test_candidate_emission_retains_saved_provenance(candidate: Any, capsys: Any) -> None:
    candidate.configure("tran")
    candidate.BASE.read = lambda path: b"synthetic-owned-variables"
    data = {"netlist_valid": True, "effective": {"variables_v": candidate.SAVED}}
    candidate.emit(data)
    result = json.loads(capsys.readouterr().out)
    assert result["source_saved_state"]["variables_v"] == candidate.SAVED
    assert result["effective"]["variables_v"] == candidate.CANDIDATE
    assert result["job_analysis_override"]["method"] == "trap"
    candidate.emit(result)
    assert json.loads(capsys.readouterr().out) == result


def test_missing_predecessor_denies_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".codex").mkdir()
    (tmp_path / ".codex/native-candidate-correction-1.json").write_text(
        json.dumps(operator.correction_record("hash"))
    )
    monkeypatch.setattr(operator, "ROOT", tmp_path)
    monkeypatch.setattr(operator, "authority", lambda: ({}, "hash"))
    monkeypatch.setattr(operator.dc, "command", lambda *args: pytest.fail("transport reached"))
    with pytest.raises(operator.campaign.CampaignError):
        operator.run("netlist-tran")


def test_deployment_unknown_cannot_replay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".codex").mkdir()
    monkeypatch.setattr(operator, "ROOT", tmp_path)
    monkeypatch.setattr(operator, "authority", lambda: ({}, "hash"))
    monkeypatch.setattr(operator, "deploy", lambda *args: (_ for _ in ()).throw(ValueError("lost")))
    with pytest.raises(ValueError, match="lost"):
        operator.run("deploy")
    with pytest.raises(FileExistsError):
        operator.run("deploy")
    assert (
        json.loads((tmp_path / ".codex/native-candidate-v2-deploy.json").read_text())["state"]
        == "reserved"
    )


def test_fixed_policy_and_template_boundaries() -> None:
    parent = operator.campaign._read_json(operator.campaign.POLICY)
    policy = json.loads(operator.POLICY.read_text())
    assert policy == operator.expected_policy(
        operator.dc.digest(operator.campaign._canonical(parent))
    )
    assert policy["corrections_used"] == 1
    assert policy["prior_native_change_corrections_preserved"] == "3_of_3"
    for name in operator.FILES:
        data = (operator.LOCAL / name).read_bytes()
        assert b"\r" not in data
        if name.startswith("netlist-"):
            assert b"asiLoadState(" in data and b"sevNetlistFile(" in data
            assert b"dbSave" not in data and b"asiSaveState" not in data


def test_extraction_uses_candidate_templates(candidate: Any, tmp_path: Path) -> None:
    candidate.configure("ac")
    candidate.VERSION = str(tmp_path)
    candidate.configure("ac")
    assert candidate.NATIVE.VERSION == candidate.VERSION
    candidate.BASE.JOB = str(tmp_path)
    candidate.BASE.verify_netlist = lambda: {"result_name": "ac"}
    candidate.BASE.write_new = lambda path, data: Path(path).write_text(data, encoding="utf-8")
    (tmp_path / "extract-ac.ocn").write_text("owned=@JOB@/psf")
    candidate.NATIVE.extraction()
    assert (tmp_path / "extract.ocn").read_text(encoding="utf-8") == f"owned={tmp_path}/psf"


@pytest.fixture
def failed_ac(candidate: Any, tmp_path: Path) -> Any:
    candidate.ROOT = str(tmp_path)
    candidate.FAILED_AC = str(tmp_path / "native-candidate-v1-ac")
    candidate.configure("ac")
    old = Path(candidate.FAILED_AC)
    old.mkdir()
    (tmp_path / "native-candidate-v1-dc").mkdir()
    (tmp_path / "native-candidate-v1-dc/result.json").write_bytes(b"preserved-dc")
    netdir = old / "project/WP14_AUTO_PHASE_01_TB2/spectre/schematic/netlist"
    netdir.mkdir(parents=True)
    (netdir / "input.scs").write_bytes(b"synthetic-input")
    (netdir / "netlist").write_bytes(b"synthetic-circuit")
    (old / "psf").mkdir()
    (old / "psf/ac").write_bytes(b"synthetic-psf")
    (old / "stage").write_bytes(b"extraction_failed\n")
    (old / "attempt-reserved").write_bytes(b"reserved")
    (old / "netlist-result.json").write_bytes(b"synthetic-result")
    candidate.AC_NETLIST_SHA = candidate.BASE.sha(b"synthetic-result")
    (old / "before.json").write_text(json.dumps({"state_facts": {}}))
    (old / "spectre.log").write_bytes(b"summary 0 0 0")
    candidate.BASE.verify_netlist = lambda: {
        "applied_bias_values_v": [0.32, 0.702],
        "result_name": "ac",
        "input_sha256": candidate.BASE.sha(b"synthetic-input"),
    }
    candidate.BASE.environment_preflight = lambda: None
    # Remote POSIX rename replaces an existing stage; Windows rename does not.
    candidate.BASE.set_stage = lambda stage: Path(candidate.BASE.JOB, "stage").write_bytes(
        (stage + "\n").encode("ascii")
    )
    (tmp_path / "previous-circuit").write_bytes(b"synthetic-circuit")
    candidate.BASE.guard = lambda: SimpleNamespace(
        NETLIST=str(tmp_path / "previous-circuit"), SUMMARY=re.compile(r"summary (\d+) (\d+) (\d+)")
    )
    candidate.validate_netlist = lambda *args: "ac"

    def fingerprint(path: str) -> dict[str, Any]:
        root = Path(path)
        files = sorted(p for p in root.rglob("*") if p.is_file())
        data = b"".join(str(p.relative_to(root)).encode() + p.read_bytes() for p in files)
        return {
            "sha256": candidate.BASE.sha(data),
            "entry_count": len(files),
            "total_bytes": sum(p.stat().st_size for p in files),
        }

    candidate.tree = fingerprint
    return candidate


def test_ac_recovery_copies_only_and_preserves_failed_job(failed_ac: Any) -> None:
    old = failed_ac.tree(failed_ac.FAILED_AC)
    failed_ac.recover()
    proof = failed_ac.verify_recovery()
    assert proof["source_job_tree"] == old == failed_ac.tree(failed_ac.FAILED_AC)
    assert proof["simulation"] == "reused_succeeded"
    assert proof["extraction"] == "new_only"
    assert Path(failed_ac.BASE.JOB, "attempt-reserved").read_bytes() == b"reserved"
    assert Path(failed_ac.BASE.JOB, "stage").read_bytes() == b"extracting\n"
    with pytest.raises(ValueError, match="replay"):
        failed_ac.recover()


@pytest.mark.parametrize(
    "fault", ["stage", "reservation", "netlist", "artifact", "summary", "psf", "budget"]
)
def test_ac_recovery_rejects_unverified_source(failed_ac: Any, fault: str) -> None:
    old = Path(failed_ac.FAILED_AC)
    if fault == "stage":
        (old / "stage").write_bytes(b"simulator_failed\n")
    elif fault == "reservation":
        (old / "attempt-reserved").unlink()
    elif fault == "netlist":
        (old / "netlist-result.json").write_bytes(b"drift")
    elif fault == "artifact":
        (old / "extract.ocn").write_bytes(b"prior")
    elif fault == "summary":
        (old / "spectre.log").write_bytes(b"summary 1 0 0")
    elif fault == "psf":
        (old / "psf/ac").write_bytes(b"")
    else:
        failed_ac.BASE.RESERVATION = 10
    with pytest.raises(ValueError):
        failed_ac.recover()
    assert not Path(failed_ac.BASE.JOB).exists()


@pytest.mark.parametrize("fault", ["old_psf", "new_psf", "old_dc", "new_input", "proof"])
def test_recovered_ac_rejects_later_drift(failed_ac: Any, fault: str) -> None:
    failed_ac.recover()
    path = {
        "old_psf": Path(failed_ac.FAILED_AC, "psf/ac"),
        "new_psf": Path(failed_ac.BASE.JOB, "psf/ac"),
        "old_dc": Path(failed_ac.ROOT, "native-candidate-v1-dc/result.json"),
        "new_input": Path(failed_ac.BASE.NETDIR, "input.scs"),
        "proof": Path(failed_ac.BASE.JOB, "recovery-source.json"),
    }[fault]
    path.write_bytes(b"{}" if fault == "proof" else b"drift")
    with pytest.raises(ValueError):
        failed_ac.verify_recovery()


def test_recovery_never_reserves_or_runs_spectre() -> None:
    runner = (operator.LOCAL / "run.sh").read_text()
    recover_branch = runner.split('if [ "$1" = recover ]; then', 1)[1].split("    else", 1)[0]
    assert "recover ac" in recover_branch
    assert "reserve" not in recover_branch and "SPECTRE" not in recover_branch
    assert "simulate:ac" not in runner and "netlist:ac" not in runner
