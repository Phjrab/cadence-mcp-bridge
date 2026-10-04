"""Synthetic corner selection, exact state diff, ledger and immutable plan guards."""

from __future__ import annotations

import importlib
import json
import re
import sys
import uuid
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
from test_native_ac_tran import native_input
from test_native_candidate import candidate as candidate_fixture
from test_native_candidate import variables

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
operator = importlib.import_module("ade_pvt_qual")


@pytest.fixture
def helper() -> Any:
    load: Any = candidate_fixture
    cand = load.__wrapped__()
    module: Any = ModuleType("pvt_qual_test")
    module.N = SimpleNamespace(
        BASE=cand.BASE,
        CAND=cand,
        configure=lambda *args: None,
        ID=re.compile(r"^[0-9a-f-]{36}$"),
        RECORD="",
        ANALYSIS="dc",
    )
    source = (operator.LOCAL / "helper.py").read_text(encoding="utf-8")
    source = source.replace("import imp\n", "").replace(
        'N = imp.load_source("pvt_native", ROOT + "/phase-campaign/native-mcp-v1/helper.py")', ""
    )
    exec(compile(source, "pvt_qual.py", "exec"), module.__dict__)
    module.check_models = module.models
    module.models = lambda: module.MODEL_MANIFEST_SHA
    module.references = lambda: None
    return module


@pytest.mark.parametrize("corner", ["FF", "SS", "FS", "SF"])
@pytest.mark.parametrize("analysis", ["dc", "ac"])
def test_generated_corner_input_verified_before_nn_validator_reuse(
    helper: Any, corner: str, analysis: str
) -> None:
    helper.CAND.configure(analysis)
    helper.CORNER = corner
    text, circuit, facts = native_input(helper.CAND.NATIVE, "ac")
    if analysis == "dc":
        prefix = text.split(circuit)[0]
        text = prefix + circuit + helper.BASE.NATIVE_CONTROL + "\n"
    helper.CAND.configure(analysis)
    text = text.replace("section=NN", "section=" + corner).replace(
        "VBIASN=300m VBIASP=650m", "VBIASN=320m VBIASP=702m"
    )
    assert helper.validate_netlist(text, circuit, circuit, facts) == (
        "dcOp" if analysis == "dc" else "ac"
    )
    for invalid in (
        text.replace("section=" + corner, "section=NN"),
        text.replace("section=" + corner, "section=" + corner + "_highPerf"),
        text + '\ninclude "/arbitrary" section=FF\n',
        text.replace("temp=27", "temp=28"),
        text.replace("VBIASN=320m", "VBIASN=321m"),
    ):
        with pytest.raises(ValueError):
            helper.validate_netlist(invalid, circuit, circuit, facts)


@pytest.mark.parametrize("corner", ["NN", "FF_highPerf", "ff", "FF;id", "FF\n", "TRAN"])
def test_corner_allowlist(helper: Any, corner: str) -> None:
    with pytest.raises(ValueError):
        helper.corner_model(b'(("model" "NN"))\n', corner)


@pytest.mark.parametrize("fault", ["none", "bytes", "manifest", "size", "name"])
def test_all_nine_model_files_are_pinned(helper: Any, tmp_path: Path, fault: str) -> None:
    records = []
    for index in range(9):
        name = "gpdk090_" + str(index) + ".scs"
        data = ("synthetic_" + str(index)).encode()
        (tmp_path / name).write_bytes(data)
        records.append([name, helper.BASE.sha(data), len(data)])
    helper.BASE.MODEL = (tmp_path / "gpdk090.scs").as_posix()
    helper.os = SimpleNamespace(
        path=SimpleNamespace(
            dirname=lambda path: Path(path).parent.as_posix(),
            realpath=lambda path: Path(path).resolve().as_posix(),
        )
    )
    helper.MODEL_MANIFEST = str(tmp_path / "manifest.json")
    if fault == "size":
        records[-1][2] += 1
    elif fault == "name":
        records[-1][0] = "../escape.scs"
    raw = json.dumps({"files": records}).encode()
    Path(helper.MODEL_MANIFEST).write_bytes(raw)
    helper.MODEL_MANIFEST_SHA = helper.BASE.sha(raw)
    if fault == "bytes":
        (tmp_path / records[-1][0]).write_bytes(b"changed")
    elif fault == "manifest":
        Path(helper.MODEL_MANIFEST).write_bytes(b"changed")
    if fault == "none":
        assert helper.check_models() == helper.MODEL_MANIFEST_SHA
    else:
        with pytest.raises(ValueError):
            helper.check_models()


@pytest.mark.parametrize("fault", ["none", "model", "variables", "other", "original", "proof"])
def test_owned_state_only_two_biases_model_and_routing_may_change(
    helper: Any, tmp_path: Path, fault: str
) -> None:
    base = helper.BASE
    base.STATE, base.COPIED_STATE, base.JOB = (
        str(tmp_path / name) for name in ("source", "owned", "job")
    )
    for path in (base.STATE, base.COPIED_STATE, base.JOB):
        Path(path).mkdir()
    helper.CORNER = "FS"
    model = f'(("{base.MODEL}" "NN"))\n'.encode("latin-1")
    candidate = helper.CAND.candidate_variables(variables())
    changed = helper.corner_model(model, "FS")
    for path in (base.STATE, base.COPIED_STATE):
        Path(path, "variables").write_bytes(variables() if path == base.STATE else candidate)
        Path(path, "modelSetup").write_bytes(model if path == base.STATE else changed)
        Path(path, "ADE_state.info").write_bytes(b"routing")
        Path(path, "analyses").write_bytes(b"saved_dc")
    Path(base.JOB, "source-variables.bin").write_bytes(variables())
    Path(base.JOB, "candidate-state.json").write_text(
        json.dumps(
            {
                "source_variables_sha256": base.sha(variables()),
                "owned_variables_sha256": base.sha(candidate),
                "requested_variables_v": helper.CAND.CANDIDATE,
                "source_variables_v": helper.CAND.SAVED,
            }
        )
    )
    proof = {
        "corner": "FS",
        "source_model_setup_sha256": base.sha(model),
        "owned_model_setup_sha256": base.sha(changed),
        "model_manifest_sha256": helper.MODEL_MANIFEST_SHA,
    }
    baseline = {"source_sha256": "synthetic"}
    base.snapshot = lambda: baseline.copy()
    base.state_facts = lambda: {"variables_v": helper.CAND.SAVED}
    before = {
        **baseline,
        "state_facts": base.state_facts(),
        "state_copy_info_sha256": base.sha(b"routing"),
    }
    if fault in ("model", "variables", "other"):
        filename = {"model": "modelSetup", "variables": "variables", "other": "analyses"}[fault]
        Path(base.COPIED_STATE, filename).write_bytes(b"unapproved")
    elif fault == "original":
        baseline["source_sha256"] = "changed"
    elif fault == "proof":
        proof["corner"] = "SF"
    Path(base.JOB, "corner-state.json").write_text(json.dumps(proof))
    if fault == "none":
        helper.verify_protected(before)
    else:
        with pytest.raises(ValueError):
            helper.verify_protected(before)


def plan() -> dict[str, Any]:
    return {
        "policy_sha256": "synthetic",
        "jobs": [
            {"job_id": str(uuid.uuid4()), "corner": corner, "analysis": analysis}
            for corner, analysis in operator.PAIRS
        ],
    }


@pytest.mark.parametrize(
    "fault", ["none", "extra", "id", "duplicate", "order", "binding", "count", "schema"]
)
def test_eight_immutable_operator_requests(fault: str) -> None:
    data = plan()
    if fault == "extra":
        data["jobs"][0]["script"] = "arbitrary"
    elif fault == "id":
        data["jobs"][0]["job_id"] = "../escape"
    elif fault == "duplicate":
        data["jobs"][1]["job_id"] = data["jobs"][0]["job_id"]
    elif fault == "order":
        data["jobs"].reverse()
    elif fault == "binding":
        data["policy_sha256"] = "drift"
    elif fault == "count":
        data["jobs"].pop()
    elif fault == "schema":
        data["path"] = "arbitrary"
    if fault == "none":
        assert len(operator.validate_plan(data, "synthetic")) == 8
    else:
        with pytest.raises(ValueError):
            operator.validate_plan(data, "synthetic")


@pytest.mark.parametrize("fault", ["none", "duplicate", "ninth", "drift", "exhausted"])
def test_phase_attempts_and_shared_ledger_never_reset(
    helper: Any, tmp_path: Path, fault: str
) -> None:
    helper.JOBS = str(tmp_path)
    helper.N.contained = lambda path: None
    helper.N.RECORD = str(tmp_path / "new")
    helper.N.ANALYSIS, helper.CORNER = "dc", "FF"
    helper.BASE.COUNTER = str(tmp_path.parent / "counter.json")
    helper.BASE.environment_preflight = lambda: None
    helper.BASE.snapshot = lambda: {}
    helper.BASE.state_facts = lambda: {"variables_v": helper.CAND.SAVED}
    count = 8 if fault in ("exhausted", "ninth") else 2
    for index in range(count):
        path = tmp_path / str(uuid.uuid4())
        (path / "work").mkdir(parents=True)
        corner, analysis = operator.PAIRS[index]
        (path / "request.json").write_text(json.dumps({"corner": corner, "analysis": analysis}))
        (path / "work/attempt-reserved").write_bytes(b"durable")
    counter = {
        "campaign_id": "AUTO-PHASE-01",
        "count": 24 + count,
        "result_reserved_bytes": 2014314496 + count * helper.BASE.RESERVATION,
    }
    if fault == "drift":
        counter["count"] -= 1
    Path(helper.BASE.COUNTER).write_text(json.dumps(counter))
    if fault in ("duplicate", "ninth"):
        path = tmp_path / str(uuid.uuid4())
        path.mkdir()
        (path / "request.json").write_text(json.dumps({"corner": "FF", "analysis": "dc"}))
    if fault == "none":
        helper.CORNER = "SS"
        helper.preflight()
        assert Path(helper.BASE.COUNTER).read_text() == json.dumps(counter)
    else:
        with pytest.raises(ValueError):
            helper.preflight()
