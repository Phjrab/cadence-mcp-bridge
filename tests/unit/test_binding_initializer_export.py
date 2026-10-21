"""Local export evidence only; no current VM or administrator execution."""

import ast
import copy
import hashlib
import json
import os
import socket
import stat
import subprocess
import sys
from importlib.resources import files

import pytest
from test_binding_observation_bootstrap import descriptions, operator, operator_base, registered
from test_physical_metadata import current_account_owner

from cadence_mcp_bridge import binding_initializer as exporter
from cadence_mcp_bridge.environments import EnvironmentProfile

__all__ = ["descriptions", "operator", "operator_base", "registered"]


@pytest.fixture(autouse=True)
def ordinary_account_output_owner():
    # Hosted elevated Windows otherwise assigns disposable output to the
    # Administrators group. Keep the product's token-owner/DACL checks intact.
    with current_account_owner():
        yield


def forbidden(*args, **kwargs):
    pytest.fail("local export reached process, network or administrative boundary")


def subject(descriptions):
    return EnvironmentProfile.model_validate_json(descriptions[0]), json.loads(descriptions[1])


def test_export_freezes_all_installed_assets_without_loading_or_running_them(
    descriptions, tmp_path, monkeypatch,
):
    profile, registration = subject(descriptions)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(exporter, "_load_bundle", lambda *args: ({
        "profile.json": descriptions[0], "registration.json": descriptions[1],
    }, {}))
    output = tmp_path / "export"
    result = exporter.export(tmp_path / "bundle", "a" * 64, output)
    raw = (output / "initializer-admin.py").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == result["helper_sha256"]
    assert not result["execution_authorized"] and not result["remote_contact"]
    assert not result["runtime_behavior_attested"]
    namespace = {"__name__": "inert_export_test"}
    exec(compile(raw, "inert_export_test.py", "exec"), namespace)
    assert namespace["CONFIG"] == {
        "profile": profile.model_dump(mode="json"), "registration": registration,
    }
    assert set(namespace["SOURCES"]) == set(exporter.RESOURCES)
    import base64

    for name, resource in exporter.RESOURCES.items():
        expected = files("cadence_mcp_bridge").joinpath(resource).read_bytes().replace(
            b"\r\n", b"\n")
        assert base64.b64decode(namespace["SOURCES"][name]) == expected
        assert namespace["PINS"][name] == hashlib.sha256(expected).hexdigest()
    with pytest.raises(FileExistsError):
        exporter.export(tmp_path / "bundle", "a" * 64, output)


@pytest.mark.parametrize("change", ["environment", "extra", "route", "library"])
def test_unbound_or_malformed_operator_configuration_rejected(descriptions, change):
    profile, registration = subject(descriptions)
    registration = copy.deepcopy(registration)
    if change == "environment":
        registration["environment_sha256"] = "f" * 64
    elif change == "extra":
        registration["trusted"] = True
    elif change == "route":
        registration["routes"].append(registration["routes"][0])
    else:
        registration["routes"][0]["libraries"].append(
            registration["routes"][0]["libraries"][0])
    with pytest.raises(ValueError):
        exporter.helper_bytes(profile, registration)


def test_export_is_inert_at_import_and_cli_has_no_arbitrary_command(descriptions):
    profile, registration = subject(descriptions)
    raw = exporter.helper_bytes(profile, registration)
    tree = ast.parse(raw)
    assert not any(isinstance(node, ast.ImportFrom) for node in ast.walk(tree))
    assert "shell=True" not in raw.decode("ascii")
    namespace = {"__name__": "inert_initializer"}
    exec(compile(raw, "inert_initializer.py", "exec"), namespace)
    import sys
    from unittest.mock import patch

    for args in (["helper", "shell"], ["helper", "plan", "a" * 64],
                 ["helper", "apply"], ["helper", "chmod", "/etc/passwd"]):
        with patch.object(sys, "argv", args), pytest.raises(ValueError):
            namespace["main"]()
    assert "loaded" not in namespace


def test_direct_entry_rejects_nonisolated_startup_before_config_or_helper_load(descriptions):
    profile, registration = subject(descriptions)
    source = exporter.helper_bytes(profile, registration)
    # Run only the prefix with real non-isolated test-interpreter flags. A
    # configured helper cannot import filesystem-backed modules before this gate.
    prefix = source.split(b"import os\n", 1)[0]
    import sys
    from types import SimpleNamespace
    from unittest.mock import patch

    with (
        patch.object(sys, "flags", SimpleNamespace(ignore_environment=0, no_user_site=0)),
        pytest.raises(SystemExit, match="isolated_python_required"),
    ):
        exec(compile(prefix, "startup_prefix.py", "exec"), {"__name__": "__main__"})


@pytest.mark.skipif(
    sys.platform != "linux" or os.environ.get("CADENCE_TEST_INITIALIZER_ADMIN") != "1",
    reason="explicit disposable Linux administrator fixture only; no registered VM",
)
def test_actual_disposable_initializer_admin_generated_entry(descriptions, tmp_path):
    """Exact generated entry and four actual modules, not a replacement dispatcher.

    This opt-in hosted fixture invokes only owned synthetic file metadata work.
    It uses the runner's Python, not actual standard-VM/Python2.6 qualification.
    """
    import base64
    import pwd

    from cadence_mcp_bridge import _native_copy as copying

    assert os.getuid() != 0
    account = pwd.getpwuid(os.getuid())
    assert str(tmp_path).startswith(account.pw_dir + "/")
    profile_value, registration = subject(descriptions)
    profile_value = profile_value.model_dump(mode="json")
    registration = copy.deepcopy(registration)
    installation, workspace = tmp_path / "installation", tmp_path / "workspace"
    installation.mkdir(mode=0o755)
    workspace.mkdir(mode=0o700)
    managed, library = workspace / ".cadence_mcp", installation / "library"
    managed.mkdir(mode=0o700)
    library.mkdir(mode=0o755)
    code = library / "libInit.il"
    code.write_bytes(b"; disposable generated-entry initializer, never evaluated\n")
    code.chmod(0o664)
    route = registration["routes"][0]
    cell = library / route["profile"]["binding"]["cell"]
    cell.mkdir(mode=0o755)
    oa = cell / "sch.oa"
    oa.write_bytes(b"owned synthetic OA bytes; no Cadence file opened\n")
    oa.chmod(0o644)
    library.chmod(0o775)
    profile_value["host"].update(
        hostname=os.uname().nodename, architecture=os.uname().machine,
        user=account.pw_name, python_version=".".join(map(str, sys.version_info[:3])),
    )
    profile_value["paths"].update(
        workspace_root=str(workspace), managed_root=str(managed),
        job_root=str(managed / "jobs"), result_root=str(managed / "results"),
        protected_roots=[str(installation)],
    )
    for name, tool in profile_value["tools"].items():
        # No fake or genuine EDA executable is created or invoked. These frozen
        # identifiers bind only the installation classification for this fixture.
        tool["path"] = str(installation / "fixed-tools" / name)
    profile = EnvironmentProfile.model_validate_json(json.dumps(profile_value))
    profile_value = profile.model_dump(mode="json")
    anchor = dict(
        root_sha256=copying.digest(str(managed).encode("ascii")),
        resource_domain_sha256=copying.digest(copying.canonical(dict(
            hostname=profile.host.hostname.lower().rstrip("."),
            architecture=profile.host.architecture,
        ))),
        ledger_ref="sim-mcp-v2-jobs/counter.json",
    )
    registration.update(
        identity_manifest_sha256=copying.digest(copying.canonical(anchor)),
        environment_sha256=copying.digest(copying.canonical(profile_value)),
    )
    route.update(
        source_cell=str(cell), source_state=str(workspace / "preserved-ade-state"),
        libraries=[dict(name=route["profile"]["binding"]["library"], path=str(library),
                        tree_sha256=copying.dependency_snapshot(str(library))["tree_sha256"])],
    )
    for name in ("sim-mcp-v2-jobs", "reservation-identity"):
        (managed / name).mkdir(mode=0o700)
    protected = {
        "run.lock": b"retained generated-entry lifecycle lock",
        "reservation-identity/manifest.json": copying.canonical(anchor),
        "sim-mcp-v2-jobs/counter.json": b'{"count":11,"result_reserved_bytes":2048}',
        "preserved-journal": b"owned synthetic journal; never reset",
    }
    for name, raw in protected.items():
        (managed / name).write_bytes(raw)
        (managed / name).chmod(0o600)
    raw_helper = exporter.helper_bytes(profile, registration)
    helper = tmp_path / "exact-generated-initializer.py"
    helper.write_bytes(raw_helper)
    helper.chmod(0o600)
    # Establish the disposable hosted sudo session before freezing ancestors;
    # a first sudo invocation may otherwise create its normal home-directory
    # marker after the plan. It executes no EDA or filesystem repair.
    administrator_probe = subprocess.run(
        ["sudo", "-n", sys.executable, "-E", "-s", "-B", "-c",
         "import os; assert os.getuid() == os.geteuid() == 0"],
        capture_output=True, timeout=30,
    )
    assert administrator_probe.returncode == 0, administrator_probe.stderr.decode(errors="replace")
    frozen = {"__name__": "inert_generated_fixture_verification"}
    exec(compile(raw_helper, "inert_generated_fixture_verification.py", "exec"), frozen)
    for role, resource in exporter.RESOURCES.items():
        expected = files("cadence_mcp_bridge").joinpath(resource).read_bytes().replace(
            b"\r\n", b"\n")
        assert base64.b64decode(frozen["SOURCES"][role]) == expected
        assert frozen["PINS"][role] == hashlib.sha256(expected).hexdigest()

    def metadata(path):
        info = path.stat()
        return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
                info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)

    original = {name: metadata(managed / name) for name in protected}
    original_oa, original_code = metadata(oa), metadata(code)

    def invoke(operation, request=None, administrator=False):
        args = [sys.executable, "-E", "-s", "-B", str(helper), operation]
        raw = None
        if request is not None:
            args.append(request["expected_plan_sha256"])
            raw = copying.canonical(request)
        if administrator:
            args = ["sudo", "-n", *args]
        completed = subprocess.run(args, input=raw, capture_output=True, timeout=90)
        assert completed.returncode == 0, completed.stderr.decode(errors="replace")
        return json.loads(completed.stdout)

    planned = invoke("plan")
    assert planned["plan"]["registration"] == registration
    assert not planned["plan"]["runtime_trust_assessed"]
    request = dict(plan=planned["plan"], expected_plan_sha256=planned["plan_sha256"],
                   operator_authority="EXPLICIT_DISPOSABLE_GENERATED_ENTRY_TEST_ONLY")
    applied = invoke("apply", request, administrator=True)
    assert applied["changed"] == 2 and applied["receipt_provenance_assessed"]
    assert not applied["runtime_trust_assessed"] and not applied["execution_authorized"]
    assert stat.S_IMODE(library.stat().st_mode) == 0o755
    assert stat.S_IMODE(code.stat().st_mode) == 0o644
    postcheck_request = dict(request, operator_authority=None)
    checked = invoke("postcheck", postcheck_request)
    assert checked["content_preserved"] and not checked["receipt_provenance_assessed"]
    assert not checked["runtime_trust_assessed"] and not checked["execution_authorized"]
    assert invoke("apply", request, administrator=True)["changed"] == 0
    restored = invoke("rollback", request, administrator=True)
    assert restored["changed"] == 2 and restored["receipt_provenance_assessed"]
    assert restored["libraries"][0]["current_tree_sha256"] == route["libraries"][0]["tree_sha256"]
    assert stat.S_IMODE(library.stat().st_mode) == 0o775
    assert stat.S_IMODE(code.stat().st_mode) == 0o664
    assert metadata(code)[:-1] == original_code[:-1]  # Intended chmod changes ctime only.
    assert code.read_bytes() == b"; disposable generated-entry initializer, never evaluated\n"
    assert metadata(oa) == original_oa
    assert oa.read_bytes() == b"owned synthetic OA bytes; no Cadence file opened\n"
    for name, raw in protected.items():
        assert metadata(managed / name) == original[name]
        assert (managed / name).read_bytes() == raw
    assert not (managed / "reservation-identity" / "legacy-seal.json").exists()
    assert helper.read_bytes() == raw_helper
    # Completed root-owned before receipts stay on the disposable hosted runner;
    # no registered VM, actual journal or Cadence/OCEAN/Spectre is contacted.
