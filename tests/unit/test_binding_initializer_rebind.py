"""Local prospective proposals from retained synthetic evidence, never VM trust."""

import copy
import hashlib
import io
import json
import socket
import stat
import subprocess
from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_binding_initializer import _acl, _snapshot
from test_native_runtime import operator, operator_base, registered
from test_physical_metadata import current_account_owner

from cadence_mcp_bridge import binding_initializer as exporter
from cadence_mcp_bridge.domain_provisioning import _canonical
from cadence_mcp_bridge.native_runtime import NativeRegistration, bundle, projection

__all__ = ["operator", "operator_base", "registered"]


@pytest.fixture(autouse=True)
def ordinary_account_output_owner():
    # Disposable output must have ordinary-account ownership even in elevated
    # hosted Windows. The product ownership and DACL guards remain unchanged.
    with current_account_owner():
        yield


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def forbidden(*args, **kwargs):
    pytest.fail("prospective local export reached process or network boundary")


@pytest.fixture
def evidence(registered, tmp_path):
    context, registration, native_path = registered
    # Isolate the synthetic retained state from the output parent. No journal,
    # lock, VM tree, executable or actual initializer is created by this fixture.
    context = replace(context, resource_state_root=tmp_path / "retained-state")
    original = json.loads(registration.model_dump_json())
    source = original["routes"][0]["libraries"][0]
    user_snapshot = _snapshot([
        ["directory", "", 0o755, 500, 500, "100.000000000"],
        ["file", "libInit.il", 0o664, 500, 500, "100.000000000", 3, "e" * 64, 1],
    ])
    source["tree_sha256"] = user_snapshot["tree_sha256"]
    installed_snapshot = _snapshot([
        ["directory", "", 0o775, 0, 0, "100.000000000"],
        ["file", "context.cxt", 0o644, 0, 0, "100.000000000", 3, "a" * 64, 1],
        ["file", "libInit.il", 0o664, 0, 0, "100.000000000", 3, "b" * 64, 1],
        ["directory", "cell", 0o755, 0, 0, "100.000000000"],
        ["file", "cell/sch.oa", 0o644, 0, 0, "100.000000000", 3, "c" * 64, 1],
    ])
    installed = dict(name="InstallationLib", path="/opt/eda/reference",
                     tree_sha256=installed_snapshot["tree_sha256"])
    original["routes"][0]["libraries"].append(installed)
    native_path.write_bytes(_canonical(original))
    registration = NativeRegistration.model_validate_json(native_path.read_bytes())
    compiled = projection(context, registration)
    bundle_path = tmp_path / "bundle"
    manifest = bundle(context, native_path, bundle_path)
    profile = context.contracts.environment.model_dump(mode="json")
    snapshots = sorted([[copy.deepcopy(source), user_snapshot],
                        [copy.deepcopy(installed), installed_snapshot]],
                       key=lambda pair: pair[0]["name"])
    records = []
    for index, row in enumerate(installed_snapshot["metadata"][:3]):
        path = installed["path"] + ("/" + row[1] if row[1] else "")
        records.append(dict(path=path, dev=1, ino=index + 10, mode=row[2], uid=row[3],
            gid=row[4], kind=row[0], size=row[6] if row[0] == "file" else None,
            mtime="100" if row[0] == "file" else None,
            sha256=row[7] if row[0] == "file" else None, acl=_acl(row[2]),
            after_mode=row[2] & ~0o022, after_acl=_acl(row[2] & ~0o022),
            reason="remove_shared_code_write_preserve_content_owner_rx"))
    plan = dict(schema_version=2, scope=dict(installation_roots=[installed["path"]],
        paths=[row["path"] for row in records], links=[], profile_sha256=sha(_canonical(profile)),
        resource_lock=profile["paths"]["managed_root"] + "/run.lock"), records=records,
        operation="remove_022_and_default_acl_writes", content_authority="NONE",
        execution_authorized=False, recipe_id=exporter.recipe.RECIPE, profile=profile,
        registration=compiled, library_snapshots=snapshots, library_namespace=[],
        ancestor_acl_records=[], runtime_trust_assessed=False, registration_updated=False)
    transitions = []
    for library, before in snapshots:
        metadata = copy.deepcopy(before["metadata"])
        if library["name"] == installed["name"]:
            for row in metadata[:3]:
                row[2] &= ~0o022
        transitions.append(dict(name=library["name"], path=library["path"],
            original_tree_sha256=before["tree_sha256"],
            current_tree_sha256=_snapshot(metadata)["tree_sha256"],
            content_sha256=before["content_sha256"]))
    plan_path, post_path, admin_path = (tmp_path / name for name in
                                      ("inner-plan.json", "postcheck.json", "admin-result.json"))
    plan_path.write_bytes(_canonical(plan))
    postcheck = dict(schema_version=1, kind="INITIALIZER_ALLOWED_METADATA_DELTA",
        plan_sha256=sha(plan_path.read_bytes()), rollback=False, selected_targets=3,
        libraries=transitions, content_preserved=True, owner_group_preserved=True,
        registration_updated=False, runtime_trust_assessed=False, execution_authorized=False,
        receipt_provenance_assessed=False)
    post_path.write_bytes(_canonical(postcheck) + b"\n")
    administrator = dict(postcheck, receipt_provenance_assessed=True,
        metadata_changes_explicit=True,
        observed_plan_sha256=sha(plan_path.read_bytes()), changed=2,
        applied_plan_receipt_sha256="d" * 64)
    admin_path.write_bytes(_canonical(administrator) + b"\n")
    return dict(context=context, bundle=bundle_path, manifest_sha256=manifest["manifest_sha256"],
        native_registration_path=native_path,
        native_registration_sha256=sha(native_path.read_bytes()),
        plan_path=plan_path, plan_sha256=sha(plan_path.read_bytes()), postcheck_path=post_path,
        postcheck_sha256=sha(post_path.read_bytes()), output=tmp_path / "prospective",
        administrator_result_path=admin_path,
        administrator_result_sha256=sha(admin_path.read_bytes()))


def invoke(evidence, administrator=False):
    args = dict(evidence)
    if not administrator:
        args.pop("administrator_result_path")
        args.pop("administrator_result_sha256")
    return exporter.prospective(**args)


def retained(evidence):
    paths = [evidence[key] for key in ("native_registration_path", "plan_path", "postcheck_path",
                                     "administrator_result_path")]
    paths.extend(evidence["bundle"].iterdir())
    return {path: path.read_bytes() for path in paths}


def rewrite(evidence, key, value):
    evidence[key].write_bytes(_canonical(value))
    evidence[key.replace("_path", "_sha256")] = sha(evidence[key].read_bytes())


def test_mode_only_prospective_delta_preserves_original_and_grants_no_trust(
    evidence, monkeypatch,
):
    original = retained(evidence)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    report = invoke(evidence)
    assert report["status"] == "PROSPECTIVE_NOT_INSTALLED_NOT_AUTHORIZED"
    assert report["administrator_result_authentication"] == "NOT_ASSESSED_RETAINED_STDOUT_ONLY"
    assert report["reported_applied_plan_receipt_sha256"] is None
    assert report["external_review_required"] and report["original_preserved"]
    for key in ("receipt_provenance_assessed", "registration_updated", "installed",
                "runtime_trust_assessed", "qualification_established", "execution_authorized",
                "remote_contact", "ledger_modified"):
        assert report[key] is False
    assert report["new_simulations"] == report["new_reservations"] == 0
    output = evidence["output"]
    assert {path.name for path in output.iterdir()} == {
        "native-registration.prospective.json", "projected-registration.prospective.json",
        "rebind-report.private.json",
    }
    native_raw = (output / "native-registration.prospective.json").read_bytes()
    projected_raw = (output / "projected-registration.prospective.json").read_bytes()
    assert sha(native_raw) == report["prospective_native_registration_sha256"]
    assert sha(projected_raw) == report["prospective_projected_registration_sha256"]
    assert json.loads((output / "rebind-report.private.json").read_bytes()) == report
    native = json.loads(native_raw)
    before = json.loads(original[evidence["native_registration_path"]])
    expected = copy.deepcopy(before)
    installation = next(row for row in report["libraries"] if row["name"] == "InstallationLib")
    user = next(row for row in report["libraries"] if row["name"] != "InstallationLib")
    assert installation["original_tree_sha256"] != installation["current_tree_sha256"]
    assert user["original_tree_sha256"] == user["current_tree_sha256"]
    expected["routes"][0]["libraries"][1]["tree_sha256"] = installation["current_tree_sha256"]
    assert native == expected
    assert json.loads(projected_raw) == projection(
        evidence["context"], NativeRegistration.model_validate_json(native_raw))
    assert retained(evidence) == original
    assert not evidence["context"].resource_state_root.exists()


def test_retained_administrator_stdout_is_correlated_without_authenticating_it(evidence):
    report = invoke(evidence, administrator=True)
    assert report["reported_applied_plan_receipt_sha256"] == "d" * 64
    assert report["administrator_result_input_sha256"] == evidence["administrator_result_sha256"]
    assert report["administrator_result_authentication"] == "NOT_ASSESSED_RETAINED_STDOUT_ONLY"
    assert not report["receipt_provenance_assessed"] and not report["execution_authorized"]


@pytest.mark.parametrize("changed", ["manifest-pin", "bundle-asset", "native-registration",
    "plan-pin", "postcheck-pin", "canonical-plan", "projection-environment"])
def test_changed_exact_inputs_reject_before_any_output(evidence, changed, monkeypatch):
    if changed == "manifest-pin":
        evidence["manifest_sha256"] = "f" * 64
    elif changed == "bundle-asset":
        (evidence["bundle"] / "worker.py").write_bytes(b"changed retained source; never executed")
    elif changed == "native-registration":
        original = json.loads(evidence["native_registration_path"].read_bytes())
        original["identity_manifest_sha256"] = "f" * 64
        rewrite(evidence, "native_registration_path", original)
    elif changed in ("plan-pin", "postcheck-pin"):
        evidence[changed.replace("-pin", "_sha256")] = "f" * 64
    elif changed == "canonical-plan":
        evidence["plan_path"].write_bytes(evidence["plan_path"].read_bytes() + b"\n")
        evidence["plan_sha256"] = sha(evidence["plan_path"].read_bytes())
    else:
        original = exporter._load_bundle

        def changed_profile(*args):
            assets, known = original(*args)
            assets = dict(assets)
            profile = json.loads(assets["profile.json"])
            profile["ssh_alias"] = "another-declared-host"
            assets["profile.json"] = _canonical(profile)
            return assets, known

        monkeypatch.setattr(exporter, "_load_bundle", changed_profile)
    with pytest.raises(ValueError):
        invoke(evidence)
    assert not evidence["output"].exists()


@pytest.mark.parametrize("changed", ["snapshot-content", "snapshot-fake-pin", "selected-execute",
    "selected-acl", "scope", "trust", "original-registration", "nonselected-mode"])
def test_plan_cannot_replace_original_pins_or_expand_allowed_delta(evidence, changed):
    plan = json.loads(evidence["plan_path"].read_bytes())
    installation = next(pair for pair in plan["library_snapshots"]
                        if pair[0]["name"] == "InstallationLib")
    if changed == "snapshot-content":
        installation[1]["metadata"][-1][7] = "f" * 64
    elif changed == "snapshot-fake-pin":
        installation[1]["metadata"][-1][7] = "f" * 64
        installation[1] = _snapshot(installation[1]["metadata"])
    elif changed == "selected-execute":
        plan["records"][1]["after_mode"] |= 0o100
    elif changed == "selected-acl":
        plan["records"][1]["after_acl"] = _acl(0o600)
    elif changed == "scope":
        plan["scope"]["paths"].append("/opt/eda/reference/cell/sch.oa")
    elif changed == "trust":
        plan["runtime_trust_assessed"] = True
    elif changed == "original-registration":
        plan["registration"]["identity_manifest_sha256"] = "f" * 64
    else:
        installation[1]["metadata"][-1][2] = 0o600
        installation[1] = _snapshot(installation[1]["metadata"])
    rewrite(evidence, "plan_path", plan)
    with pytest.raises(ValueError, match="initializer_rebind_"):
        invoke(evidence)
    assert not evidence["output"].exists()


@pytest.mark.parametrize("changed", ["reported-new-pin", "content", "owner", "rollback",
    "plan", "missing-library", "authority", "provenance", "extra"])
def test_exact_postcheck_rejects_reported_drift_and_authority(evidence, changed):
    post = json.loads(evidence["postcheck_path"].read_bytes())
    if changed == "reported-new-pin":
        post["libraries"][0]["current_tree_sha256"] = "f" * 64
    elif changed == "content":
        post["content_preserved"] = False
    elif changed == "owner":
        post["owner_group_preserved"] = False
    elif changed == "rollback":
        post["rollback"] = True
    elif changed == "plan":
        post["plan_sha256"] = "f" * 64
    elif changed == "missing-library":
        post["libraries"].pop()
    elif changed == "authority":
        post["execution_authorized"] = True
    elif changed == "provenance":
        post["receipt_provenance_assessed"] = True
    else:
        post["approved"] = True
    rewrite(evidence, "postcheck_path", post)
    with pytest.raises(ValueError, match="successful_exact_postcheck"):
        invoke(evidence)
    assert not evidence["output"].exists()


@pytest.mark.parametrize("changed", ["receipt", "count", "runtime", "extra", "missing-pin"])
def test_optional_administrator_result_cannot_grant_or_misstate_scope(evidence, changed):
    if changed == "missing-pin":
        evidence["administrator_result_sha256"] = None
    else:
        admin = json.loads(evidence["administrator_result_path"].read_bytes())
        if changed == "receipt":
            admin["applied_plan_receipt_sha256"] = "not-a-sha256"
        elif changed == "count":
            admin["changed"] = 4
        elif changed == "runtime":
            admin["runtime_trust_assessed"] = True
        else:
            admin["approved"] = True
        rewrite(evidence, "administrator_result_path", admin)
    with pytest.raises(ValueError, match="administrator_result_"):
        invoke(evidence, administrator=True)
    assert not evidence["output"].exists()


def test_prospective_projection_must_change_only_library_pins(evidence, monkeypatch):
    original = exporter.projection
    calls = []

    def drifting_projection(*args):
        value = original(*args)
        calls.append(None)
        if len(calls) == 2:
            value["routes"][0]["source_state"] += "/changed"
        return value

    monkeypatch.setattr(exporter, "projection", drifting_projection)
    with pytest.raises(ValueError, match="nonlibrary_projection_drift"):
        invoke(evidence)
    assert len(calls) == 2 and not evidence["output"].exists()


@pytest.mark.parametrize("key", ["native_registration_path", "plan_path", "postcheck_path",
                                 "administrator_result_path"])
def test_final_evidence_revalidation_rejects_later_file_drift(evidence, monkeypatch, key):
    original = exporter._pinned_document
    calls = []

    def drift_after_first_read(path, expected):
        value = original(path, expected)
        if path == evidence[key] and not calls:
            calls.append(None)
            path.write_bytes(path.read_bytes() + b"\n")
        return value

    monkeypatch.setattr(exporter, "_pinned_document", drift_after_first_read)
    with pytest.raises(ValueError, match="evidence_digest_mismatch"):
        invoke(evidence, administrator=True)
    assert calls and not evidence["output"].exists()


def test_bundle_is_reauthenticated_after_all_evidence_checks(evidence, monkeypatch):
    original = exporter._load_bundle
    calls = []

    def drift_after_first_load(*args):
        value = original(*args)
        if not calls:
            (evidence["bundle"] / "worker.py").write_bytes(b"changed source; never executed")
        calls.append(None)
        return value

    monkeypatch.setattr(exporter, "_load_bundle", drift_after_first_load)
    with pytest.raises(ValueError):
        invoke(evidence)
    assert calls and not evidence["output"].exists()


@pytest.mark.parametrize("destination", ["native", "plan", "postcheck", "bundle", "state"])
def test_protected_inputs_and_retained_state_are_never_output(evidence, destination):
    original = retained(evidence)
    output = {
        "native": evidence["native_registration_path"], "plan": evidence["plan_path"],
        "postcheck": evidence["postcheck_path"], "bundle": evidence["bundle"] / "proposal",
        "state": evidence["context"].resource_state_root / "proposal",
    }[destination]
    evidence["output"] = output
    with pytest.raises(ValueError, match="output_protected"):
        invoke(evidence)
    assert retained(evidence) == original
    if destination in ("bundle", "state"):
        assert not output.exists()


def test_existing_output_is_preserved_without_replacement(evidence):
    output = evidence["output"]
    output.mkdir()
    (output / "retained").write_bytes(b"previous failed output retained")
    with pytest.raises(FileExistsError):
        invoke(evidence)
    assert {path.name: path.read_bytes() for path in output.iterdir()} == {
        "retained": b"previous failed output retained",
    }


@pytest.mark.parametrize("platform,drift,accepted", [
    ("nt", None, True), ("posix", None, False),
    ("nt", "path-ctime", False), ("nt", "fd-ctime", False),
    ("posix", "path-ctime", False), ("posix", "fd-ctime", False),
    ("nt", "fd-mode", False), ("nt", "fd-inode", False),
    ("nt", "fd-mtime", False), ("nt", "fd-owner", False),
    ("nt", "fd-links", False), ("nt", "fd-size", False),
])
def test_pinned_document_ctime_compares_each_api_without_losing_metadata_guards(
    monkeypatch, tmp_path, platform, drift, accepted,
):
    """Synthetic platform API semantics; integration above uses real file APIs."""
    raw = b"{}"
    base = dict(st_dev=1, st_ino=2, st_mode=stat.S_IFREG | 0o600, st_uid=500,
                st_gid=500, st_nlink=1, st_size=len(raw), st_mtime_ns=100)
    before, after = [SimpleNamespace(**base, st_ctime_ns=10) for _ in range(2)]
    opened, finished = [SimpleNamespace(**base, st_ctime_ns=20) for _ in range(2)]
    if drift == "path-ctime":
        after.st_ctime_ns += 1
    elif drift == "fd-ctime":
        finished.st_ctime_ns += 1
    elif drift is not None:
        field = {"fd-mode": "st_mode", "fd-inode": "st_ino", "fd-mtime": "st_mtime_ns",
                 "fd-owner": "st_uid", "fd-links": "st_nlink", "fd-size": "st_size"}[drift]
        setattr(opened, field, getattr(opened, field) + 1)
        setattr(finished, field, getattr(finished, field) + 1)
    path_values, fd_values = iter((before, after)), iter((opened, finished))

    class ReadStream(io.BytesIO):
        def fileno(self):
            return 7

    fake_path = SimpleNamespace(lstat=lambda: next(path_values))
    monkeypatch.setattr(exporter, "_local_path", lambda _: fake_path)
    monkeypatch.setattr(exporter, "os", SimpleNamespace(name=platform, O_RDONLY=0,
        open=lambda *args: 7, fdopen=lambda *args: ReadStream(raw),
        fstat=lambda _: next(fd_values)))
    if accepted:
        assert exporter._pinned_document(tmp_path / "synthetic", sha(raw)) == (raw, {})
    else:
        with pytest.raises(ValueError, match="evidence_drift_or_bound"):
            exporter._pinned_document(tmp_path / "synthetic", sha(raw))
