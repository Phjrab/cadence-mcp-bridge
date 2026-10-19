"""Synthetic finite admission and owned-process tests; no VM or Cadence qualification."""

import copy
import errno
import json
import os
import signal
import sys
import time
from pathlib import Path

import pytest
from test_binding_observation import binding, frame
from test_binding_observation_worker import (
    controlled_inventory,
    declared_case,
    rebind_declared_documents,
    root,
    selected,
)

from cadence_mcp_bridge import _binding_observation as observer
from cadence_mcp_bridge.binding_observation import BindingScanRequest, parse_frame

__all__ = ["controlled_inventory", "declared_case", "root", "selected"]

_CATEGORIES = (
    "system_interpreter_and_startup",
    "os_loader_and_libraries",
    "cadence_launchers_runtime_and_contexts",
    "registered_library_initializers",
)
_PROTECTED = (
    "originals_preserved", "owned_copy_preserved", "ledger_preserved", "cds_lib_preserved",
)
_ORDINARY_LINUX = pytest.mark.skipif(
    sys.platform != "linux" or os.getuid() == 0 if os.name == "posix" else True,
    reason="actual ordinary Linux flock, owned process group and durable receipts",
)


def documents(worker, manifest=None):
    """Fixture-only approval/trust descriptions, never actual operator evidence."""
    now = int(time.time())
    subject = {key: worker.selection[key] for key in (
        "profile_sha256", "registration_sha256", "request_sha256",
        "collector_sha256", "helper_sha256",
    )}
    manifest_raw = observer.canonical({} if manifest is None else manifest)
    closure = {
        "schema_version": 1,
        "kind": "STANDARD_VM_BINDING_OBSERVER_EXECUTION_ATTESTATION",
        "subject": subject,
        "declared_members_sha256": observer.digest(manifest_raw),
        "launch_recipe": "OWNED_COPY_NOGRAPH_NOCDSINIT_V1",
        "review_reference": "synthetic-fixture:no-real-review",
        "trust_categories": [
            {"category": category, "evidence_sha256": str(index + 1) * 64}
            for index, category in enumerate(_CATEGORIES)
        ],
        "runtime_roots": sorted(worker.profile["paths"]["protected_roots"]),
        "libraries": sorted(worker.route["libraries"], key=lambda item: item["name"]),
        "permitted_effects": "PRIVATE_STAGE_ONLY",
        "unresolved_dependencies": [],
        "valid_from_unix": now - 1,
        "valid_until_unix": now + 1200,
    }
    admission = {
        **subject,
        "schema_version": 1,
        "kind": "FINITE_BINDING_OBSERVATION",
        "authority_reference": "synthetic-fixture:no-real-authorization",
        "approval_receipt_sha256": "a" * 64,
        "prepared_plan_sha256": "b" * 64,
        "package_sha256": "c" * 64,
        "resource_domain_sha256": "a" * 64,
        "identity_manifest_sha256": worker.registration.get(
            "identity_manifest_sha256", "d" * 64,
        ),
        "expected_counter": {
            "campaign_id": "AUTO-PHASE-01", "count": 82, "result_reserved_bytes": 9798942720,
        },
        "declared_members_sha256": observer.digest(manifest_raw),
        "execution_attestation_sha256": observer.digest(observer.canonical(closure)),
        "predecessor": {key: "e" * 64 for key in (
            "predecessor_collector_sha256", "predecessor_plan_sha256",
            "predecessor_host_request_sha256", "predecessor_remote_request_sha256",
        )},
        "valid_from_unix": now - 1,
        "valid_until_unix": now + 1200,
        "limits": {
            "remote_attempts": 1, "ocean_starts": 1, "outer_seconds": observer.OUTER_SECONDS,
            "ocean_seconds": observer.PROCESS_SECONDS, "stage_bytes": observer.STAGE_BYTES,
            "new_simulations": 0, "new_extractions": 0, "new_reserved_bytes": 0,
        },
    }
    return admission, manifest_raw, closure


def encoded(admission, manifest_raw, closure):
    return observer.canonical(admission), manifest_raw, observer.canonical(closure)


def evidence_rebound(admission, manifest_raw, closure):
    admission["declared_members_sha256"] = observer.digest(manifest_raw)
    admission["execution_attestation_sha256"] = observer.digest(observer.canonical(closure))
    return encoded(admission, manifest_raw, closure)


def forbid_filesystem(monkeypatch, worker):
    def forbidden(*args, **kwargs):
        pytest.fail("pure admission attempted filesystem observation, write or process launch")

    monkeypatch.setattr(observer.os, "open", forbidden)
    monkeypatch.setattr(observer.os, "lstat", forbidden)
    monkeypatch.setattr(observer.subprocess, "Popen", forbidden)
    for name in ("_preflight", "_declared_code_members", "_stage", "_program"):
        monkeypatch.setattr(worker, name, forbidden)


def test_complete_synthetic_admission_is_pure_and_never_qualifies_execution(
    declared_case, selected, monkeypatch,
):
    worker, manifest = declared_case
    request = selected[1]
    admission, manifest_raw, closure = documents(worker, manifest)
    forbid_filesystem(monkeypatch, worker)
    assert worker._admission(request, *encoded(admission, manifest_raw, closure)) == admission
    assert worker.observe(request)["status"] == "CAPABILITY_NOT_QUALIFIED"
    assert "qualified" not in admission and "execution_authorized" not in admission


@pytest.mark.parametrize("change,reason", [
    ("admission-extra", "admission_scope"),
    ("admission-bool", "admission_scope"),
    ("admission-kind", "admission_scope"),
    ("missing-binding", "admission_scope"),
    ("wrong-binding", "admission_scope"),
    ("bool-limit", "admission_scope"),
    ("second-attempt", "admission_scope"),
    ("simulation", "admission_scope"),
    ("missing-predecessor", "predecessor_shape"),
    ("bool-predecessor", "token"),
    ("bool-counter", "expected_counter"),
    ("negative-counter", "expected_counter"),
    ("counter-extra", "expected_counter"),
    ("approval-digest", "token"),
    ("authority-code", "token"),
    ("expired", "authority_not_current"),
    ("future", "authority_not_current"),
    ("bool-time", "authority_not_current"),
    ("excess-window", "authority_not_current"),
    ("manifest-digest", "execution_evidence_binding"),
    ("attestation-digest", "execution_evidence_binding"),
    ("closure-extra", "execution_attestation_scope"),
    ("closure-bool", "execution_attestation_scope"),
    ("closure-subject", "execution_attestation_scope"),
    ("closure-declared", "execution_attestation_scope"),
    ("closure-recipe", "execution_attestation_scope"),
    ("closure-effects", "execution_attestation_scope"),
    ("closure-unresolved", "execution_attestation_scope"),
    ("closure-expired", "authority_not_current"),
    ("closure-roots", "execution_attestation_scope"),
    ("closure-library", "execution_attestation_scope"),
    ("category-missing", "execution_trust_categories"),
    ("category-duplicate", "execution_trust_categories"),
    ("category-extra", "execution_trust_categories"),
    ("category-bool", "execution_trust_categories"),
    ("category-evidence", "token"),
])
def test_invalid_or_unresolved_admission_rejects_before_io(
    declared_case, selected, monkeypatch, change, reason,
):
    worker, manifest = declared_case
    admission, manifest_raw, closure = documents(worker, manifest)
    if change == "admission-extra":
        admission["approved"] = True
    elif change == "admission-bool":
        admission["schema_version"] = True
    elif change == "admission-kind":
        admission["kind"] = "GENERAL_EDA_PERMISSION"
    elif change == "missing-binding":
        del admission["request_sha256"]
    elif change == "wrong-binding":
        admission["request_sha256"] = "f" * 64
    elif change == "bool-limit":
        admission["limits"]["ocean_starts"] = True
    elif change == "second-attempt":
        admission["limits"]["remote_attempts"] = 2
    elif change == "simulation":
        admission["limits"]["new_simulations"] = 1
    elif change == "missing-predecessor":
        admission["predecessor"].pop("predecessor_collector_sha256")
    elif change == "bool-predecessor":
        admission["predecessor"]["predecessor_collector_sha256"] = True
    elif change == "bool-counter":
        admission["expected_counter"]["count"] = True
    elif change == "negative-counter":
        admission["expected_counter"]["result_reserved_bytes"] = -1
    elif change == "counter-extra":
        admission["expected_counter"]["reset"] = True
    elif change == "approval-digest":
        admission["approval_receipt_sha256"] = "not-an-approval"
    elif change == "authority-code":
        admission["authority_reference"] = "human\nrun()"
    elif change == "expired":
        admission["valid_until_unix"] = admission["valid_from_unix"]
    elif change == "future":
        admission["valid_from_unix"] += 600
    elif change == "bool-time":
        admission["valid_from_unix"] = True
    elif change == "excess-window":
        admission["valid_until_unix"] = admission["valid_from_unix"] + 3601
    elif change == "manifest-digest":
        admission["declared_members_sha256"] = "f" * 64
    elif change == "attestation-digest":
        admission["execution_attestation_sha256"] = "f" * 64
    elif change == "closure-extra":
        closure["complete"] = True
    elif change == "closure-bool":
        closure["schema_version"] = True
    elif change == "closure-subject":
        closure["subject"] = {**closure["subject"], "request_sha256": "f" * 64}
    elif change == "closure-declared":
        closure["declared_members_sha256"] = "f" * 64
    elif change == "closure-recipe":
        closure["launch_recipe"] = "INHERIT_USER_STARTUP"
    elif change == "closure-effects":
        closure["permitted_effects"] = "WRITE_ORIGINALS"
    elif change == "closure-unresolved":
        closure["unresolved_dependencies"] = ["unreviewed-library-init"]
    elif change == "closure-expired":
        closure["valid_until_unix"] = closure["valid_from_unix"]
    elif change == "closure-roots":
        closure["runtime_roots"] = []
    elif change == "closure-library":
        closure["libraries"] = []
    elif change == "category-missing":
        closure["trust_categories"].pop()
    elif change == "category-duplicate":
        closure["trust_categories"][-1] = copy.deepcopy(closure["trust_categories"][0])
    elif change == "category-extra":
        closure["trust_categories"][0]["approved"] = True
    elif change == "category-bool":
        closure["trust_categories"][0]["category"] = True
    elif change == "category-evidence":
        closure["trust_categories"][0]["evidence_sha256"] = True
    if change.startswith(("closure-", "category-")):
        evidence_rebound(admission, manifest_raw, closure)
    raw_documents = encoded(admission, manifest_raw, closure)
    forbid_filesystem(monkeypatch, worker)
    with pytest.raises(ValueError, match="^binding_observation_" + reason + "$"):
        worker._admission(selected[1], *raw_documents)
    with pytest.raises(ValueError, match="^binding_observation_" + reason + "$"):
        worker.observe_authorized(selected[1], *raw_documents)


@pytest.mark.parametrize("target", ["admission", "attestation"])
@pytest.mark.parametrize("malformation", ["noncanonical", "duplicate", "nonascii", "oversize"])
def test_admission_document_encoding_is_closed_before_io(
    declared_case, selected, monkeypatch, target, malformation,
):
    worker, manifest = declared_case
    admission, manifest_raw, closure = documents(worker, manifest)
    raw = list(encoded(admission, manifest_raw, closure))
    index = 0 if target == "admission" else 2
    raw[index] = {
        "noncanonical": raw[index] + b"\n",
        "duplicate": b'{"schema_version":1,"schema_version":1}',
        "nonascii": b'{"x":"\xff"}',
        "oversize": b"x" * (16385 if target == "admission" else 32769),
    }[malformation]
    forbid_filesystem(monkeypatch, worker)
    with pytest.raises(ValueError, match="^binding_observation_(invalid_document|document_bound)$"):
        worker._admission(selected[1], *raw)
    with pytest.raises(ValueError, match="^binding_observation_(invalid_document|document_bound)$"):
        worker.observe_authorized(selected[1], *raw)


def operational_case(selected, monkeypatch, case="success"):
    """Real owned child/lock; synthetic executable and external trust witness only."""
    worker, request, _ = selected
    scan = BindingScanRequest.model_validate_json(observer.canonical(request))
    frame_raw = frame(scan, body=["SCAN|1|1", binding()], complete="COMPLETE|1|1|1")
    script = {
        "success": f"open('binding-frame.txt','wb').write({frame_raw!r})",
        "nonzero": "raise SystemExit(7)",
        "timeout": "import time;time.sleep(30)",
        "cancel": "import time;time.sleep(30)",
        "protection-collision": (
            "open('protection-check.json','wb').write(" + repr(observer.canonical({
                name: True for name in _PROTECTED
            })) + ");"
            "open('library/Cell/sch.oa','ab').write(b'changed owned copy');"
            "raise SystemExit(7)"
        ),
    }[case]
    executable = Path(worker.profile["tools"]["ocean"]["path"])
    executable.write_text(f"#!{sys.executable}\n{script}\n", encoding="utf-8")
    executable.chmod(0o700)
    worker.profile["tools"]["ocean"]["sha256"] = observer.digest(executable.read_bytes())
    anchor = Path(worker.root) / worker.accounting.REGISTRY / "manifest.json"
    worker.registration["identity_manifest_sha256"] = observer.digest(anchor.read_bytes())
    rebind_declared_documents(worker)
    witnessed = []

    def synthetic_integrity(raw, expected):
        assert raw == b"{}" and observer.digest(raw) == expected
        witnessed.append(expected)
        return {"scope": "SYNTHETIC_TEST_WITNESS_ONLY"}

    monkeypatch.setattr(worker, "_declared_code_members", synthetic_integrity)
    if case == "timeout":
        monkeypatch.setattr(observer, "PROCESS_SECONDS", 0.15)
    if case == "cancel":
        worker._cancelled = lambda: bool(launched)
    original_stage, original_program = worker._stage, worker._program
    steps, launched = [], []

    def stage(*args):
        steps.append("stage")
        return original_stage(*args)

    def program(*args):
        steps.append("program")
        return original_program(*args)

    monkeypatch.setattr(worker, "_stage", stage)
    monkeypatch.setattr(worker, "_program", program)
    real_popen = observer.subprocess.Popen

    def launch(argv, **options):
        assert argv[0] == str(executable)
        assert options["shell"] is False and options["preexec_fn"] == os.setsid
        child = real_popen(argv, **options)
        launched.append(child)
        return child

    monkeypatch.setattr(observer.subprocess, "Popen", launch)
    return worker, request, documents(worker), frame_raw, witnessed, steps, launched


@_ORDINARY_LINUX
@pytest.mark.parametrize("case", ["success", "nonzero", "timeout", "cancel"])
def test_authorized_flow_runs_real_owned_child_once_and_binds_terminal_receipt(
    selected, controlled_inventory, monkeypatch, case,
):
    worker, request, docs, frame_raw, witnessed, steps, launched = operational_case(
        selected, monkeypatch, case,
    )
    raw = encoded(*docs)
    ledger_path = Path(worker.root) / worker.accounting.LEDGER
    ledger_before, originals = ledger_path.read_bytes(), worker._snapshots()
    result = worker.observe_authorized(request, *raw)
    assert steps == ["stage", "program"] and len(launched) == 1
    assert len(witnessed) >= 3
    assert result["start_attempted"] is True and result["new_eda_starts"] == 1
    assert result["cleanup_complete"] is True and launched[0].returncode is not None
    assert result["execution_trust"] == "OPERATOR_ATTESTED_STANDARD_VM"
    assert result["qualification_established"] is False and result["retry_permitted"] is False
    assert all(result[key] is True for key in _PROTECTED)
    assert result["counter_before"] == result["counter_after"] == docs[0]["expected_counter"]
    assert result["new_simulations"] == result["new_extractions"] == 0
    assert result["new_reserved_bytes"] == 0
    stage = Path(worker.root) / "binding-observations" / request["observation_id"]
    terminal = json.loads((stage / "terminal.json").read_bytes())
    assert terminal == {key: value for key, value in result.items() if key != "frame"}
    assert "frame" not in terminal
    if case == "success":
        assert result["status"] == "PROCESS_COMPLETED" and result["returncode"] == 0
        assert result["frame"].encode("ascii") == frame_raw
        assert result["frame_sha256"] == observer.digest(frame_raw)
        parsed = parse_frame(frame_raw, BindingScanRequest.model_validate_json(
            observer.canonical(request),
        ))
        assert parsed["status"] == "OBSERVED_OWNED_COPY_BINDINGS"
    else:
        expected_reason = {
            "nonzero": "program_failed", "timeout": "process_timeout", "cancel": "cancelled",
        }[case]
        assert result["failure_code"] == "binding_observation_" + expected_reason
        assert result["status"] == ("TIMED_OUT" if case == "timeout" else "FAILED")
        assert result["frame"] is None and result["frame_sha256"] is None
        if case == "nonzero":
            assert result["returncode"] == 7
        else:
            assert result["returncode"] < 0
    worker._cancelled = lambda: False
    repeated = worker.observe_authorized(request, *raw)
    assert repeated["status"] == "REJECTED"
    assert repeated["failure_code"] == "binding_observation_remote_attempt_spent"
    assert repeated["new_eda_starts"] == 0 and len(launched) == 1
    assert (stage / "terminal.json").read_bytes() == observer.canonical(terminal)
    assert ledger_path.read_bytes() == ledger_before and worker._snapshots() == originals
    assert (Path(worker.root) / "binding-observation-01.private.json").is_file()
    # A separate fresh authenticated module still sees the same existing flock.
    with worker.accounting.ReservationSession(worker.root) as session:
        session.check()


@_ORDINARY_LINUX
@pytest.mark.parametrize("case", ["counter", "identity", "expired", "partial-claim", "trust"])
def test_no_process_start_for_unadmitted_or_spent_operational_scope(
    selected, controlled_inventory, monkeypatch, case,
):
    worker, request, docs, _, _, steps, launched = operational_case(selected, monkeypatch)
    admission, manifest_raw, closure = docs
    claim = Path(worker.root) / "binding-observation-01.private.json"
    if case == "counter":
        admission["expected_counter"]["count"] += 1
    elif case == "identity":
        worker.registration["identity_manifest_sha256"] = "f" * 64
    elif case == "expired":
        admission["valid_until_unix"] = admission["valid_from_unix"]
    elif case == "partial-claim":
        claim.write_bytes(b"{")
        claim.chmod(0o600)
    elif case == "trust":
        def reject(*args):
            raise ValueError("binding_observation_synthetic_dependency_drift")

        monkeypatch.setattr(worker, "_declared_code_members", reject)
    raw = encoded(admission, manifest_raw, closure)
    if case == "expired":
        with pytest.raises(ValueError, match="authority_not_current"):
            worker.observe_authorized(request, *raw)
    else:
        result = worker.observe_authorized(request, *raw)
        assert result["status"] == "REJECTED" and result["new_eda_starts"] == 0
    assert steps == [] and launched == []
    assert not (Path(worker.root) / "binding-observations").exists()
    if case == "partial-claim":
        assert claim.read_bytes() == b"{"
    else:
        assert not claim.exists()


@_ORDINARY_LINUX
@pytest.mark.parametrize("flag,value", [
    *((name, False) for name in _PROTECTED),
    ("originals_preserved", 1),
    ("ledger_preserved", "true"),
])
def test_final_protection_flags_must_be_actual_true_before_success_is_reported(
    selected, controlled_inventory, monkeypatch, flag, value,
):
    worker, request, docs, _, _, _, launched = operational_case(selected, monkeypatch)
    original_finalize = worker._finalize_evidence

    def invalid_finalization(stage, *args):
        original_finalize(stage, *args)
        worker._protection_receipt[flag] = value

    monkeypatch.setattr(worker, "_finalize_evidence", invalid_finalization)
    result = worker.observe_authorized(request, *encoded(*docs))
    assert result["status"] == "FAILED"
    assert result["failure_code"] == "binding_observation_terminal_conservation_failed"
    assert result["frame"] is None and result["frame_sha256"] is None
    assert result[flag] is False and len(launched) == 1


def test_parent_finalization_retains_actual_false_despite_child_primary_collision(
    selected, tmp_path, monkeypatch,
):
    worker, _, _ = selected
    stage = tmp_path / "colliding-protection"
    stage.mkdir(mode=0o700)
    child_record = observer.canonical({name: True for name in _PROTECTED})
    (stage / "protection-check.json").write_bytes(child_record)
    monkeypatch.setattr(worker, "_snapshots", lambda: "original")
    monkeypatch.setattr(worker.copying, "snapshot", lambda _: "changed-copy")
    monkeypatch.setattr(worker, "_ledger", lambda: "ledger")
    monkeypatch.setattr(worker, "_read", lambda _: b"config")
    worker._finalize_evidence(
        str(stage), [], None, [b"", b""], "original", "synthetic-copy", "copy",
        "ledger", b"config", True, False,
    )
    assert (stage / "protection-check.json").read_bytes() == child_record
    fallback = json.loads((stage / "protection-check-fallback.json").read_bytes())
    assert worker._protection_receipt == fallback
    assert worker._protection_receipt["originals_preserved"] is True
    assert worker._protection_receipt["owned_copy_preserved"] is False
    assert worker._protection_receipt["protection_record"] == "FALLBACK"


@_ORDINARY_LINUX
def test_child_primary_collision_cannot_spoof_failed_terminal_conservation(
    selected, controlled_inventory, monkeypatch,
):
    worker, request, docs, _, _, _, launched = operational_case(
        selected, monkeypatch, "protection-collision",
    )
    result = worker.observe_authorized(request, *encoded(*docs))
    assert len(launched) == 1 and result["new_eda_starts"] == 1
    assert result["status"] == "FAILED" and result["returncode"] == 7
    assert result["failure_code"] == "binding_observation_program_failed"
    assert result["originals_preserved"] is True
    assert result["owned_copy_preserved"] is False
    assert result["ledger_preserved"] is result["cds_lib_preserved"] is True
    stage = Path(worker.root) / "binding-observations" / request["observation_id"]
    primary = json.loads((stage / "protection-check.json").read_bytes())
    fallback = json.loads((stage / "protection-check-fallback.json").read_bytes())
    assert all(primary[name] is True for name in _PROTECTED)
    assert fallback["owned_copy_preserved"] is False
    assert json.loads((stage / "terminal.json").read_bytes())["owned_copy_preserved"] is False
    repeated = worker.observe_authorized(request, *encoded(*docs))
    assert repeated["status"] == "REJECTED" and len(launched) == 1
    assert all(repeated[name] is False for name in _PROTECTED)


@_ORDINARY_LINUX
@pytest.mark.parametrize("observation_number", [2, 3, 4])
def test_live_account_snapshot_drift_stops_before_any_child_start(
    selected, controlled_inventory, monkeypatch, observation_number,
):
    worker, request, docs, _, _, steps, launched = operational_case(selected, monkeypatch)
    original_observe = worker.accounting.ReservationSession.observe
    calls = []

    def changed_snapshot(session, binding):
        counter, records = original_observe(session, binding)
        calls.append(None)
        # Only the returned synthetic witness changes. The actual disposable
        # ledger/identity audit still runs and no fabricated reservation is made.
        if len(calls) >= observation_number:
            counter = {**counter, "count": counter["count"] + 1}
        return counter, records

    monkeypatch.setattr(worker.accounting.ReservationSession, "observe", changed_snapshot)
    result = worker.observe_authorized(request, *encoded(*docs))
    assert result["status"] == "REJECTED" and result["new_eda_starts"] == 0
    assert result["failure_code"] == "binding_observation_live_accounting_drift"
    assert launched == []
    assert steps == {2: [], 3: ["stage"], 4: ["stage", "program"]}[observation_number]
    claim = Path(worker.root) / "binding-observation-01.private.json"
    assert claim.exists() is (observation_number > 2)
    if observation_number > 2:
        stage = Path(worker.root) / "binding-observations" / request["observation_id"]
        assert not (stage / "ocean-start-claimed.json").exists()
        assert json.loads((stage / "terminal.json").read_bytes())["status"] == "REJECTED"


@_ORDINARY_LINUX
def test_terminal_publication_failure_preserves_frame_claim_and_no_retry(
    selected, controlled_inventory, monkeypatch,
):
    worker, request, docs, frame_raw, _, _, launched = operational_case(selected, monkeypatch)
    original_write = worker._write_evidence

    def write_except_terminal(stage, leaf, raw):
        if leaf == "terminal.json":
            raise OSError("synthetic terminal durability failure")
        return original_write(stage, leaf, raw)

    monkeypatch.setattr(worker, "_write_evidence", write_except_terminal)
    raw = encoded(*docs)
    result = worker.observe_authorized(request, *raw)
    assert result["status"] == "UNKNOWN" and result["new_eda_starts"] == 1
    assert result["failure_code"] == "binding_observation_terminal_publication_failed"
    assert result["frame"] is None and result["frame_sha256"] is None
    stage = Path(worker.root) / "binding-observations" / request["observation_id"]
    assert (stage / "binding-frame.txt").read_bytes() == frame_raw
    assert not (stage / "terminal.json").exists()
    repeated = worker.observe_authorized(request, *raw)
    assert repeated["status"] == "REJECTED" and repeated["new_eda_starts"] == 0
    assert repeated["failure_code"] == "binding_observation_remote_attempt_spent"
    assert len(launched) == 1


@_ORDINARY_LINUX
def test_fresh_observation_identity_cannot_reset_remote_campaign_claim(
    selected, controlled_inventory, monkeypatch,
):
    worker, request, docs, _, _, steps, launched = operational_case(selected, monkeypatch)
    result = worker.observe_authorized(request, *encoded(*docs))
    assert result["status"] == "PROCESS_COMPLETED" and len(launched) == 1
    claim = Path(worker.root) / "binding-observation-01.private.json"
    retained_claim = claim.read_bytes()
    changed = {**request, "observation_id": "32840434-a830-43e2-818c-950a2f32e012"}
    worker.selection["request_sha256"] = observer.digest(observer.canonical(changed))
    worker.selection["collector_sha256"] = observer.digest(observer.render_collector(changed))
    fresh_result = worker.observe_authorized(changed, *encoded(*documents(worker)))
    assert fresh_result["status"] == "REJECTED" and fresh_result["new_eda_starts"] == 0
    assert fresh_result["failure_code"] == "binding_observation_remote_attempt_spent"
    assert len(launched) == 1 and steps == ["stage", "program"]
    assert claim.read_bytes() == retained_claim
    assert not (Path(worker.root) / "binding-observations" / changed["observation_id"]).exists()


@_ORDINARY_LINUX
def test_unreadable_child_identity_keeps_lock_until_kernel_owned_group_is_stopped(
    selected, controlled_inventory, monkeypatch,
):
    worker, request, docs, _, _, _, launched = operational_case(selected, monkeypatch, "cancel")
    worker._cancelled = lambda: False
    original_identity = worker.processes.process_identity
    real_killpg = observer.os.killpg
    failed_reads, killed = [], []

    def transient_identity_failure(pid):
        if len(failed_reads) < 2:
            failed_reads.append(pid)
            assert observer.os.getpgid(pid) == pid
            with pytest.raises(OSError) as busy:
                competing = worker.accounting.ReservationSession(worker.root)
                competing.close()
            assert busy.value.errno in (errno.EACCES, errno.EAGAIN)
            raise OSError(errno.EACCES, "synthetic temporary child identity denial")
        return original_identity(pid)

    def kill_owned(group, selected_signal):
        assert len(launched) == 1 and group == launched[0].pid
        assert observer.os.getpgid(group) == group
        killed.append((group, selected_signal))
        return real_killpg(group, selected_signal)

    monkeypatch.setattr(worker.processes, "process_identity", transient_identity_failure)
    monkeypatch.setattr(observer.os, "killpg", kill_owned)
    try:
        result = worker.observe_authorized(request, *encoded(*docs))
        assert len(failed_reads) == 2 and len(launched) == 1
        assert killed and all(sig == signal.SIGKILL for _, sig in killed)
        assert result["status"] == "FAILED" and result["new_eda_starts"] == 1
        assert result["cleanup_complete"] is True
        assert result["returncode"] == -signal.SIGKILL
        assert launched[0].returncode == -signal.SIGKILL
        assert launched[0].stdout.closed and launched[0].stderr.closed
        with worker.accounting.ReservationSession(worker.root) as session:
            session.check()
        repeated = worker.observe_authorized(request, *encoded(*docs))
        assert repeated["failure_code"] == "binding_observation_remote_attempt_spent"
        assert len(launched) == 1
    finally:
        # Test-only cleanup if a regression unexpectedly leaves its owned child.
        for child in launched:
            if child.returncode is None:
                try:
                    if observer.os.getpgid(child.pid) == child.pid:
                        real_killpg(child.pid, signal.SIGKILL)
                except OSError:
                    pass
                child.wait(timeout=5)


@_ORDINARY_LINUX
@pytest.mark.parametrize("expired", ["admission", "outer-deadline"])
def test_durable_start_marker_delay_never_starts_after_authority_or_deadline(
    selected, controlled_inventory, monkeypatch, expired,
):
    worker, request, docs, _, _, steps, launched = operational_case(selected, monkeypatch)
    ledger = Path(worker.root) / worker.accounting.LEDGER
    retained_ledger = ledger.read_bytes()
    real_write, real_time, real_times = worker._write, observer.time.time, observer.os.times
    advanced = False

    def wall_clock():
        return docs[0]["valid_until_unix"] + 1 if advanced else real_time()

    def elapsed_clock():
        values = list(real_times())
        if advanced:
            values[4] += observer.OUTER_SECONDS + 1
        return tuple(values)

    def delayed_marker(path, raw):
        nonlocal advanced
        real_write(path, raw)
        if path.endswith("/ocean-start-claimed.json"):
            advanced = True

    monkeypatch.setattr(worker, "_write", delayed_marker)
    if expired == "admission":
        monkeypatch.setattr(observer.time, "time", wall_clock)
    else:
        monkeypatch.setattr(observer.os, "times", elapsed_clock)
    raw = encoded(*docs)
    result = worker.observe_authorized(request, *raw)
    assert advanced and steps == ["stage", "program"] and launched == []
    assert result["status"] == "REJECTED" and result["start_attempted"] is False
    assert result["new_eda_starts"] == 0 and result["cleanup_complete"] is True
    expected = "authority_not_current" if expired == "admission" else "process_timeout"
    assert result["failure_code"] == "binding_observation_" + expected
    stage = Path(worker.root) / "binding-observations" / request["observation_id"]
    marker = stage / "ocean-start-claimed.json"
    retained_marker = marker.read_bytes()
    disk_terminal = {key: value for key, value in result.items() if key != "frame"}
    assert (stage / "terminal.json").read_bytes() == observer.canonical(disk_terminal)
    assert result["retry_permitted"] is False and ledger.read_bytes() == retained_ledger
    advanced = False
    repeated = worker.observe_authorized(request, *raw)
    assert repeated["failure_code"] == "binding_observation_remote_attempt_spent"
    assert repeated["new_eda_starts"] == 0 and launched == []
    assert marker.read_bytes() == retained_marker and ledger.read_bytes() == retained_ledger


@_ORDINARY_LINUX
def test_missing_kernel_storage_rejects_before_remote_claim_stage_or_process(
    selected, controlled_inventory, monkeypatch,
):
    worker, request, docs, _, _, steps, launched = operational_case(selected, monkeypatch)
    ledger = Path(worker.root) / worker.accounting.LEDGER
    retained = ledger.read_bytes()

    def missing():
        raise ValueError("binding_observation_bounded_filesystem_required")

    monkeypatch.setattr(worker, "_bounded_storage", missing)
    result = worker.observe_authorized(request, *encoded(*docs))
    assert result["failure_code"] == "binding_observation_bounded_filesystem_required"
    assert result["status"] == "REJECTED" and result["new_eda_starts"] == 0
    assert result["counter_before"] == result["counter_after"] == docs[0]["expected_counter"]
    assert steps == [] and launched == []
    assert not (Path(worker.root) / "binding-observation-01.private.json").exists()
    assert not (Path(worker.root) / "binding-observations").exists()
    assert ledger.read_bytes() == retained
