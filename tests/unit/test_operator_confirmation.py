"""Disposable authenticated-record tests; not actual human consent or Cadence jobs."""

import copy
import json
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_shared_reservations import root as root_fixture

from cadence_mcp_bridge import _operator_confirmation as native
from cadence_mcp_bridge import _runner_bootstrap as installer
from cadence_mcp_bridge import _shared_reservations as accounting
from cadence_mcp_bridge import operator_confirmation as host
from cadence_mcp_bridge.__main__ import main

root = root_fixture


@pytest.fixture
def confirmed_domain(root, monkeypatch):
    profile = {
        "host": {
            "hostname": "synthetic-host",
            "user": "synthetic-user",
            "architecture": "synthetic-arch",
        },
        "paths": {
            "managed_root": str(root.resolve()),
            "job_root": str(root.resolve()) + "/" + accounting.JOBS,
        },
        "limits": {"spectre_attempts": 500, "result_reserved_bytes": 10737418240},
    }
    anchor_path = root / accounting.REGISTRY / "manifest.json"
    anchor = accounting.read(str(anchor_path))
    anchor["resource_domain_sha256"] = native.digest(
        native.canonical({"hostname": "synthetic-host", "architecture": "synthetic-arch"})
    )
    anchor_path.write_bytes(native.canonical(anchor))
    anchor_sha = native.digest(native.canonical(anchor))
    home = root.parent / "home"
    home.mkdir(mode=0o700)
    index = home / ".cadence_mcp-domain"
    index.mkdir(mode=0o700)
    accounting.write_new(
        str(index / "manifest.json"),
        {
            "schema_version": 1,
            "root": str(root.resolve()),
            "plan_sha256": "e" * 64,
            "identity_manifest_sha256": anchor_sha,
            "resource_domain_sha256": anchor["resource_domain_sha256"],
        },
    )
    monkeypatch.setattr(native, "account", lambda: (str(home), "synthetic-user", 500))
    monkeypatch.setattr(
        native.os, "uname", lambda: ("Linux", "synthetic-host", "", "", ""), raising=False
    )
    monkeypatch.setattr(
        native,
        "helpers",
        lambda: (accounting, installer, SimpleNamespace(validate_profile=lambda p: p)),
    )
    grant = {
        "schema_version": 1,
        "grant_id": "synthetic-consent",
        "authorization_source": "explicit_operator_record",
        "resource_domain_sha256": anchor["resource_domain_sha256"],
        "runner_sha256": "b" * 64,
        "ledger_ref": accounting.LEDGER_REF,
        "environment_sha256": native.digest(native.canonical(profile)),
        "design_sha256": "c" * 64,
        "pdk_sha256": "d" * 64,
        "design_ids": ["new-rc", "new-mos"],
        "analyses": ["dc", "ac", "tran"],
        "actions": ["submit", "cancel_pending"],
        "numeric_regions": [
            {
                "design_id": "new-mos",
                "logical_id": "voltage",
                "unit": "V",
                "minimum": "0",
                "maximum": "1",
            }
        ],
        "attempt_limit": 6,
        "result_reserved_bytes_limit": 805306368,
        "valid_from_unix": 1,
        "valid_until_unix": int(time.time()) + 3600,
        "status": "active",
    }
    grant_raw = native.canonical(grant)
    request = {
        "schema_version": 1,
        "profile_json": native.canonical(profile).decode("ascii"),
        "grant_json": grant_raw.decode("ascii"),
        "grant_sha256": native.digest(grant_raw),
        "identity_manifest_sha256": anchor_sha,
        "operator_authority": "SYNTHETIC_ONLY-no-actual-authority",
    }
    return root, profile, request


def snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_confirm_repeat_inspect_no_reservation_or_journal(confirmed_domain):
    root, profile, request = confirmed_domain
    before = snapshot(root)
    first = native.confirm(request, "a" * 64)
    assert first["changed"] and first["counter"]["count"] == 82
    after = snapshot(root)
    assert all(after[name] == data for name, data in before.items())
    assert set(after) - set(before) == {
        "operator-confirmations/" + request["grant_sha256"] + ".json"
    }
    second = native.confirm(request, "a" * 64)
    assert not second["changed"] and first["confirmation_sha256"] == second["confirmation_sha256"]
    assert snapshot(root) == after
    value, digest = native.inspect(
        profile, request["grant_sha256"], request["identity_manifest_sha256"]
    )
    assert value["operator_uid"] == 500 and digest == first["confirmation_sha256"]
    assert not first["execution_authorized"] and first["new_reservations"] == 0


@pytest.mark.parametrize(
    "change",
    [
        {"attempt_limit": 501},
        {"attempt_limit": True},
        {"result_reserved_bytes_limit": 10737418241},
        {"ledger_ref": "new-ledger"},
        {"resource_domain_sha256": "0" * 64},
        {"analyses": ["dc", "dc"]},
        {"analyses": ["shell"]},
        {"actions": ["root"]},
        {"valid_until_unix": 2},
        {"status": "revoked"},
        {"environment_sha256": "0" * 64},
    ],
)
def test_grant_denied_without_writes(confirmed_domain, change):
    root, _, request = confirmed_domain
    grant = json.loads(request["grant_json"])
    grant.update(change)
    raw = native.canonical(grant)
    request.update(grant_json=raw.decode("ascii"), grant_sha256=native.digest(raw))
    before = snapshot(root)
    with pytest.raises(ValueError):
        native.confirm(request, "a" * 64)
    assert snapshot(root) == before


@pytest.mark.parametrize(
    "field", ["grant_sha256", "identity_manifest_sha256", "operator_authority"]
)
def test_outer_binding_denied_no_writes(confirmed_domain, field):
    root, _, request = confirmed_domain
    request[field] = "0" * 64 if field != "operator_authority" else "$(arbitrary shell)"
    before = snapshot(root)
    with pytest.raises(ValueError):
        native.confirm(request, "a" * 64)
    assert snapshot(root) == before


def test_duplicate_noncanonical_grant_cannot_be_authenticated(confirmed_domain):
    root, _, request = confirmed_domain
    raw = request["grant_json"].replace(
        '"attempt_limit":6', '"attempt_limit":500,"attempt_limit":6'
    )
    request.update(grant_json=raw, grant_sha256=native.digest(raw.encode("ascii")))
    before = snapshot(root)
    with pytest.raises(ValueError, match="canonical_grant"):
        native.confirm(request, "a" * 64)
    assert snapshot(root) == before


def test_expiry_separates_historical_confirmation_from_execution(confirmed_domain, monkeypatch):
    _, profile, request = confirmed_domain
    native.confirm(request, "a" * 64)
    monkeypatch.setattr(native.time, "time", lambda: 4000000000)
    assert native.inspect(
        profile, request["grant_sha256"], request["identity_manifest_sha256"], False
    )[0]
    with pytest.raises(ValueError, match="inactive"):
        native.inspect(profile, request["grant_sha256"], request["identity_manifest_sha256"])


def test_revocation_append_only_replay_no_refund(confirmed_domain):
    root, profile, request = confirmed_domain
    native.confirm(request, "a" * 64)
    before = snapshot(root)
    revocation = {
        "profile": profile,
        "grant_sha256": request["grant_sha256"],
        "identity_manifest_sha256": request["identity_manifest_sha256"],
        "operator_authority": "SYNTHETIC_ONLY-explicit-revocation",
    }
    assert native.revoke(revocation, "a" * 64)["changed"]
    assert not native.revoke(revocation, "a" * 64)["changed"]
    after = snapshot(root)
    assert all(after[name] == data for name, data in before.items())
    assert len(after) == len(before) + 1
    assert native.inspect(
        profile, request["grant_sha256"], request["identity_manifest_sha256"], False
    )
    with pytest.raises(ValueError, match="revoked"):
        native.inspect(profile, request["grant_sha256"], request["identity_manifest_sha256"])
    with pytest.raises(ValueError, match="revoked"):
        native.confirm(request, "a" * 64)


@pytest.mark.parametrize(
    "change",
    [
        {"operator_uid": 0},
        {"operator_uid": True},
        {"operator_user": "other"},
        {"root_sha256": "f" * 64},
        {"resource_domain_sha256": "f" * 64},
        {"grant_sha256": "f" * 64},
        {"identity_manifest_sha256": "f" * 64},
    ],
)
def test_tampered_record_rejected(confirmed_domain, change):
    root, profile, request = confirmed_domain
    native.confirm(request, "a" * 64)
    path = root / "operator-confirmations" / (request["grant_sha256"] + ".json")
    value = native.closed(path.read_bytes())
    value.update(change)
    path.write_bytes(native.canonical(value))
    with pytest.raises(ValueError, match="binding"):
        native.inspect(profile, request["grant_sha256"], request["identity_manifest_sha256"])


def test_confirmation_response_loss_reuses_original_record(confirmed_domain, monkeypatch):
    root, _, request = confirmed_domain
    original = native.write_atomic_record

    def lost(path, value, helper):
        original(path, value, helper)
        if path.endswith(request["grant_sha256"] + ".json"):
            raise OSError("synthetic response loss after durable write")

    monkeypatch.setattr(native, "write_atomic_record", lost)
    with pytest.raises(OSError):
        native.confirm(request, "a" * 64)
    before = snapshot(root)
    monkeypatch.setattr(native, "write_atomic_record", original)
    assert not native.confirm(request, "a" * 64)["changed"]
    assert snapshot(root) == before


def test_changed_account_index_cannot_rebind_confirmation(confirmed_domain):
    root, profile, request = confirmed_domain
    native.confirm(request, "a" * 64)
    changed = copy.deepcopy(profile)
    changed["paths"]["managed_root"] = str(root.parent.resolve())
    with pytest.raises(ValueError, match="index_mismatch"):
        native.inspect(changed, request["grant_sha256"], request["identity_manifest_sha256"])


def test_export_is_explicit_and_no_MCP_mutation(tmp_path, capsys):
    output = tmp_path / "exported"
    assert main(["operator-authority", "export-helper", "--output", str(output)]) == 0
    result = json.loads(capsys.readouterr().out)
    assets, manifest, expected = host.contents()
    assert result["manifest_sha256"] == expected
    assert (output / "manifest.json").read_bytes() == manifest
    assert set(p.name for p in output.iterdir()) == set(assets) | {"manifest.json"}
    assert not result["remote_contact"] and not result["execution_authorized"]
    assert main(["operator-authority", "export-helper", "--output", str(output)]) == 1


def test_active_eda_lock_denies_confirmation_before_record_write(confirmed_domain):
    root, _, request = confirmed_domain
    before = snapshot(root)
    with accounting.ReservationSession(str(root)), pytest.raises((ValueError, OSError)):
        native.confirm(request, "a" * 64)
    assert snapshot(root) == before


def test_partial_confirmation_is_retained_and_never_guessed_valid(confirmed_domain):
    root, _, request = confirmed_domain
    directory = root / "operator-confirmations"
    directory.mkdir(mode=0o700)
    target = directory / (request["grant_sha256"] + ".json")
    target.write_bytes(b'{"partial":')
    target.chmod(0o600)
    before = snapshot(root)
    with pytest.raises(ValueError):
        native.confirm(request, "a" * 64)
    assert snapshot(root) == before


def test_hardlinked_record_denied(confirmed_domain):
    import os

    root, profile, request = confirmed_domain
    native.confirm(request, "a" * 64)
    record = root / "operator-confirmations" / (request["grant_sha256"] + ".json")
    os.link(record, root / "retained-hardlink")
    with pytest.raises(ValueError, match="file_type"):
        native.inspect(profile, request["grant_sha256"], request["identity_manifest_sha256"])


def test_invalid_revocation_cannot_be_reported_as_verified_history(confirmed_domain):
    root, profile, request = confirmed_domain
    native.confirm(request, "a" * 64)
    path = root / "operator-confirmations" / (request["grant_sha256"] + ".revoked.json")
    accounting.write_new(str(path), {"schema_version": 1})
    with pytest.raises(ValueError, match="revocation_binding"):
        native.inspect(profile, request["grant_sha256"], request["identity_manifest_sha256"], False)


def test_stale_local_helper_denies_before_ssh(tmp_path, monkeypatch):
    from cadence_mcp_bridge.operator_operations import OperationRejected

    calls = []
    monkeypatch.setattr(host, "run_fixed", lambda *args, **kwargs: calls.append(args))
    examples = Path(__file__).resolve().parents[2] / "docs/examples/onboarding/environment.json"
    with pytest.raises(OperationRejected, match="Operator operation rejected"):
        host.stage(examples, "0" * 64)
    assert calls == []


@pytest.mark.parametrize(
    "field", ["status", "manifest_sha256", "changed_files", "execution_authorized"]
)
def test_staging_response_field_drift_denies(monkeypatch, field):
    from cadence_mcp_bridge.operator_operations import OperationRejected

    _, _, sha = host.contents()
    receipt = {
        "status": "STANDARD_VM_CONFIRMATION_HELPER_STAGED",
        "manifest_sha256": sha,
        "changed_files": 5,
        "execution_authorized": False,
    }
    receipt[field] = {
        "status": "other",
        "manifest_sha256": "0" * 64,
        "changed_files": True,
        "execution_authorized": True,
    }[field]
    monkeypatch.setattr(host.shutil, "which", lambda _: "ssh.exe")
    monkeypatch.setattr(
        host, "run_fixed", lambda *args, **kwargs: (0, native.canonical(receipt), b"")
    )
    examples = Path(__file__).resolve().parents[2] / "docs/examples/onboarding/environment.json"
    with pytest.raises(OperationRejected):
        host.stage(examples, sha)


def test_logical_grant_parses_modern_contract_and_internal_path_is_not_live_authority(
    confirmed_domain,
):
    from cadence_mcp_bridge.operator_operations import OperatorGrant

    _, profile, request = confirmed_domain
    grant = OperatorGrant.model_validate_json(request["grant_json"])
    assert grant.ledger_ref == accounting.LEDGER_REF
    wrong = json.loads(request["grant_json"])
    wrong["ledger_ref"] = accounting.LEDGER
    raw = native.canonical(wrong).decode("ascii")
    root, binding, _, _ = native.domain(profile, request["identity_manifest_sha256"])
    with pytest.raises(ValueError, match="grant_shape"):
        native.grant_document(raw, native.digest(raw.encode("ascii")), profile, binding, True)
    # Historical non-live inspection remains possible; this cannot dispatch.
    assert (
        native.grant_document(raw, native.digest(raw.encode("ascii")), profile, binding, False)
        == wrong
    )


@pytest.mark.parametrize("fault", [None, "missing", "duplicate", "outside", "incomplete", "extra"])
def test_v2_confirm_exact_pairs_and_reject_malformed_without_writes(confirmed_domain, fault):
    root, profile, request = confirmed_domain
    grant = json.loads(request["grant_json"])
    grant.update(
        schema_version=2,
        analyses=["dc", "ac"],
        design_analyses=[
            dict(design_id="new-rc", analysis="dc"),
            dict(design_id="new-mos", analysis="ac"),
        ],
    )
    if fault == "missing":
        del grant["design_analyses"]
    elif fault == "duplicate":
        grant["design_analyses"].append(grant["design_analyses"][0])
    elif fault == "outside":
        grant["design_analyses"][0]["design_id"] = "not-registered"
    elif fault == "incomplete":
        grant["design_analyses"].pop()
    elif fault == "extra":
        grant["design_analyses"][0]["action"] = "shell"
    raw = native.canonical(grant)
    request.update(grant_json=raw.decode("ascii"), grant_sha256=native.digest(raw))
    before = snapshot(root)
    if fault:
        with pytest.raises(ValueError):
            native.confirm(request, "a" * 64)
        assert snapshot(root) == before
    else:
        result = native.confirm(request, "a" * 64)
        assert result["changed"] and result["new_reservations"] == 0
        value, _ = native.inspect(
            profile, request["grant_sha256"], request["identity_manifest_sha256"]
        )
        assert value["grant"] == grant and value["grant"]["schema_version"] == 2
        assert not native.confirm(request, "a" * 64)["changed"]


@pytest.mark.parametrize("action", ["confirm", "revoke"])
def test_interrupted_authority_record_can_retry_without_altering_evidence(
    confirmed_domain, monkeypatch, action
):
    import os

    root, profile, request = confirmed_domain
    if action == "revoke":
        native.confirm(request, "a" * 64)
    prior = snapshot(root)
    revoke_request = dict(
        profile=profile,
        grant_sha256=request["grant_sha256"],
        identity_manifest_sha256=request["identity_manifest_sha256"],
        operator_authority="SYNTHETIC_ONLY-revocation",
    )
    selected, arguments = (
        (native.confirm, request) if action == "confirm" else (native.revoke, revoke_request)
    )
    original = os.write

    def interrupted(fd, data):
        original(fd, data[:5])
        raise OSError("synthetic interrupted authority write")

    with monkeypatch.context() as patch:
        patch.setattr(os, "write", interrupted)
        with pytest.raises(OSError):
            selected(arguments, "a" * 64)
    partial = {p: raw for p, raw in snapshot(root).items() if ".confirmation-record-" in p}
    assert partial and all(snapshot(root)[p] == raw for p, raw in prior.items())
    target = (
        root
        / "operator-confirmations"
        / (request["grant_sha256"] + (".json" if action == "confirm" else ".revoked.json"))
    )
    assert not target.exists()
    assert selected(arguments, "a" * 64)["changed"]
    assert not selected(arguments, "a" * 64)["changed"]
    after = snapshot(root)
    assert all(after[p] == raw for p, raw in prior.items())
    assert all(after[p] == raw for p, raw in partial.items())
    assert native.inspect(
        profile, request["grant_sha256"], request["identity_manifest_sha256"], False
    )
