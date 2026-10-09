"""Runner content workflow tests are synthetic, never Cadence qualification."""

import hashlib
import json
from pathlib import Path

import pytest

from cadence_mcp_bridge import _runner_bootstrap as installer
from cadence_mcp_bridge import bootstrap
from cadence_mcp_bridge.__main__ import main

EXAMPLES = Path(__file__).resolve().parents[2] / "docs/examples/onboarding"


@pytest.fixture
def prepared(tmp_path: Path):
    source = tmp_path / "bundle"
    report = bootstrap.bundle(EXAMPLES / "environment.json", source)
    target = tmp_path / "managed"
    target.mkdir()
    return source, target, report["manifest_sha256"]


@pytest.fixture
def prepared_bound(prepared):
    # Hash-valid synthetic content bound to this disposable Windows directory.
    # This is not a Linux environment profile or native qualification.
    source, target, _ = prepared
    profile = json.loads((source / "profile.json").read_bytes())
    profile["paths"]["managed_root"] = str(target.resolve())
    raw_profile = installer.canonical(profile)
    (source / "profile.json").write_bytes(raw_profile)
    manifest = json.loads((source / "manifest.json").read_bytes())
    manifest["profile_sha256"] = hashlib.sha256(raw_profile).hexdigest()
    manifest["files"]["profile.json"] = {
        "sha256": manifest["profile_sha256"],
        "bytes": len(raw_profile),
    }
    raw = installer.canonical(manifest)
    (source / "manifest.json").write_bytes(raw)
    return source, target, hashlib.sha256(raw).hexdigest()


def test_install_repeat_and_verify_content_only(prepared):
    source, target, digest = prepared
    first = bootstrap.install(source, target, digest)
    assert first["status"] == "INSTALL_CONTENT_VERIFIED"
    assert bootstrap.install(source, target, digest)["status"] == "EXISTING_EXACT_INSTALL"
    assert bootstrap.verify(target, digest)["execution_authorized"] is False
    assert not (target / "active-runner.json").exists()
    assert not list(target.glob("*.sqlite3"))


@pytest.mark.parametrize(
    "change", ["runner", "profile", "extra", "wrong_hash", "manifest", "linked"]
)
def test_modified_bundle_rejected_without_install(prepared, change):
    source, target, digest = prepared
    if change == "runner":
        (source / "runner.py").write_bytes(b"changed")
    elif change == "profile":
        (source / "profile.json").write_bytes(b"{}")
    elif change == "extra":
        (source / "unexpected.py").write_bytes(b"")
    elif change == "wrong_hash":
        digest = "0" * 64
    elif change == "manifest":
        (source / "manifest.json").write_bytes(b'{"schema_version":1,"schema_version":1}')
    else:
        original = source / "runner.py"
        original.rename(source / "original.py")
        try:
            original.symlink_to(source / "original.py")
        except OSError:
            pytest.skip("OS denies symlink fixture")
    with pytest.raises(ValueError):
        bootstrap.install(source, target, digest)
    assert not (target / "runtime").exists()


def test_partial_install_is_retained_and_never_overwritten(prepared):
    source, target, digest = prepared
    version = target / "runtime" / digest
    version.mkdir(parents=True)
    partial = version / "runner.py"
    partial.write_bytes(b"partial")
    with pytest.raises((ValueError, OSError)):
        bootstrap.install(source, target, digest)
    assert partial.read_bytes() == b"partial"


def test_existing_active_marker_and_update_are_rejected(prepared_bound):
    source, target, digest = prepared_bound
    bootstrap.install(source, target, digest)
    marker = target / "execution.lock"
    marker.write_bytes(b"unknown")
    with pytest.raises(ValueError, match="active_or_unresolved"):
        installer.activation(str(target), digest, None)
    marker.unlink()  # Owned synthetic fixture only.
    result = installer.activation(str(target), digest, None)
    assert result["execution_authorized"] is False
    before = (target / "active-runner.json").read_bytes()
    with pytest.raises(ValueError):
        installer.activation(str(target), digest, None)
    assert (target / "active-runner.json").read_bytes() == before


def test_export_standalone_installer_is_exclusive(tmp_path):
    output = tmp_path / "install.py"
    result = bootstrap.export_installer(output)
    assert result["sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    with pytest.raises(FileExistsError):
        bootstrap.export_installer(output)


def test_cli_errors_are_bounded(prepared, capsys):
    source, target, _ = prepared
    assert (
        main(
            [
                "runner",
                "install",
                "--bundle",
                str(source),
                "--target",
                str(target),
                "--expected-plan-sha256",
                "a" * 64,
            ]
        )
        == 1
    )
    report = capsys.readouterr().out
    assert "RUNNER_INSTALL_REJECTED" in report
    assert str(target) not in report


def test_content_hashes_and_private_asset_names(prepared):
    source, _, digest = prepared
    manifest = json.loads((source / "manifest.json").read_bytes())
    assert set(manifest["files"]) == {
        "runner.py",
        "probe.py",
        "profile.json",
        "launcher.py",
        "reservations.py",
    }
    assert hashlib.sha256((source / "manifest.json").read_bytes()).hexdigest() == digest
    assert "script" not in manifest


def test_hardlinked_asset_rejected(prepared, tmp_path):
    source, target, digest = prepared
    original = source / "runner.py"
    link = tmp_path / "hardlinked.py"
    try:
        link.hardlink_to(original)
    except OSError:
        pytest.skip("OS denies hardlink fixture")
    with pytest.raises(ValueError):
        bootstrap.install(source, target, digest)


def test_launcher_collision_preserves_existing_reference(prepared_bound):
    source, target, digest = prepared_bound
    bootstrap.install(source, target, digest)
    binary = target / "bin"
    binary.mkdir()
    existing = binary / "cadence-runner"
    existing.write_bytes(b"historical-reference")
    with pytest.raises(FileExistsError):
        installer.activation(str(target), digest, None)
    assert existing.read_bytes() == b"historical-reference"
    assert not (target / "active-runner.json").exists()


def test_deactivation_preserves_version_and_pointer(prepared_bound):
    source, target, digest = prepared_bound
    bootstrap.install(source, target, digest)
    installer.activation(str(target), digest, None)
    before = (target / "active-runner.json").read_bytes()
    assert installer.deactivate(str(target), digest)["execution_authorized"] is False
    assert (target / "active-runner.json").read_bytes() == before
    assert (target / "runtime" / digest / "runner.py").exists()


def test_untrusted_self_rehashed_runner_cannot_preflight(prepared, monkeypatch):
    source, _, _ = prepared
    path = source / "runner.py"
    path.write_bytes(path.read_bytes() + b"\n# changed\n")
    manifest = json.loads((source / "manifest.json").read_bytes())
    manifest["files"]["runner.py"] = {
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
    }
    raw = installer.canonical(manifest)
    (source / "manifest.json").write_bytes(raw)
    from unittest.mock import MagicMock

    transport = MagicMock()
    monkeypatch.setattr("cadence_mcp_bridge.operator_transport.run_fixed", transport)
    with pytest.raises(ValueError, match="package_binding"):
        bootstrap.preflight(source, hashlib.sha256(raw).hexdigest())
    transport.assert_not_called()


def test_preflight_selects_exact_manifest_and_preserves_permission_rejection(prepared, monkeypatch):
    source, _, digest = prepared
    from unittest.mock import MagicMock

    transport = MagicMock(return_value=(1, b"", b"executable_permissions\n"))
    monkeypatch.setattr("cadence_mcp_bridge.operator_transport.run_fixed", transport)
    from cadence_mcp_bridge.environments import EnvironmentRejected

    with pytest.raises(EnvironmentRejected) as error:
        bootstrap.preflight(source, digest)
    assert error.value.reason == "executable_permissions"
    argv = transport.call_args.args[0]
    assert argv[-4].endswith("/bin/cadence-operator-runner")
    assert argv[-8:-4] == ["/usr/bin/python", "-E", "-s", "-B"]
    assert argv[-3] == "preflight" and argv[-2] == digest and len(argv[-1]) == 32
    assert "StrictHostKeyChecking=yes" in argv
    assert not list(source.glob("*.sqlite3"))


@pytest.mark.parametrize(
    "target", ["/srv/project", "/srv/project/source", "/srv/other/.cadence_mcp"]
)
def test_native_install_target_must_match_hash_verified_managed_root(prepared, target):
    source, _, digest = prepared
    manifest, contents, _ = installer.validate(str(source), digest)
    with pytest.raises(ValueError, match="installation_target_binding"):
        installer.target_binding(manifest, contents, target)
    installer.target_binding(manifest, contents, "/srv/project/.cadence_mcp")


def test_standalone_wrong_target_creates_nothing(prepared):
    source, target, digest = prepared
    with pytest.raises(ValueError, match="installation_target_binding"):
        installer.install(str(source), str(target), digest)
    assert not list(target.iterdir())


def test_windows_local_content_scope_is_not_native_installation(prepared):
    import os

    if os.name != "nt":
        pytest.skip("Windows local staging scope")
    source, target, digest = prepared
    result = bootstrap.install(source, target, digest)
    assert result["installation_scope"] == "WINDOWS_LOCAL_CONTENT_STAGING_ONLY"
    assert result["native_installation_verified"] is False
    assert result["execution_authorized"] is False


@pytest.mark.parametrize("asset", ["_runner_launcher", "_generic_runner"])
@pytest.mark.parametrize(
    "mode,owner", [(0o40777, 500), (0o40775, 0), (0o40700, 501), (0o100600, 500)]
)
def test_native_runner_refuses_unsafe_ancestor_before_import(asset, mode, owner, monkeypatch):
    import importlib
    import ntpath
    from types import SimpleNamespace

    module = importlib.import_module("cadence_mcp_bridge." + asset)
    calls = []

    def observed(path):
        calls.append(path)
        return SimpleNamespace(st_mode=mode, st_uid=owner)

    fake = SimpleNamespace(name="posix", getuid=lambda: 500, path=ntpath, lstat=observed)
    monkeypatch.setattr(module, "os", fake)
    with pytest.raises(ValueError, match="runner_directory_permissions"):
        module.trusted_directory_chain("C:/owned/runtime/digest")
    assert len(calls) == 1


@pytest.mark.parametrize("asset", ["_runner_launcher", "_generic_runner"])
def test_native_runner_checks_complete_owned_or_root_ancestor_chain(asset, monkeypatch):
    import importlib
    import ntpath
    from types import SimpleNamespace

    module = importlib.import_module("cadence_mcp_bridge." + asset)
    calls = []

    def observed(path):
        calls.append(path)
        return SimpleNamespace(st_mode=0o40755, st_uid=0 if path == "C:\\" else 500)

    fake = SimpleNamespace(name="posix", getuid=lambda: 500, path=ntpath, lstat=observed)
    monkeypatch.setattr(module, "os", fake)
    module.trusted_directory_chain("C:/owned/runtime/digest")
    assert len(calls) == 4


@pytest.mark.parametrize("command", ["activate", "deactivate"])
def test_standalone_lifecycle_rejects_staged_wrong_target_without_writes(prepared, command):
    import subprocess
    import sys

    source, target, digest = prepared
    bootstrap.install(source, target, digest)
    # Even a copied active pointer cannot authorize writes under another root.
    if command == "deactivate":
        (target / "active-runner.json").write_bytes(
            installer.canonical({"schema_version": 1, "manifest_sha256": digest})
        )
    before = {
        p.relative_to(target).as_posix(): p.read_bytes() for p in target.rglob("*") if p.is_file()
    }
    exported = target.parent / "installer.py"
    bootstrap.export_installer(exported)
    result = subprocess.run(
        [sys.executable, "-I", str(exported), command, str(target), digest],
        capture_output=True,
        timeout=15,
    )
    assert result.returncode == 1
    assert b"RUNNER_INSTALL_REJECTED" in result.stderr
    assert not (target / "bin").exists()
    assert not (target / "runner-revoked.json").exists()
    assert {
        p.relative_to(target).as_posix(): p.read_bytes() for p in target.rglob("*") if p.is_file()
    } == before


def test_schema_one_history_remains_verifiable(prepared, capsys):
    source, target, _ = prepared
    (source / "reservations.py").unlink()  # Disposable bundle migration fixture only.
    manifest = json.loads((source / "manifest.json").read_bytes())
    manifest["schema_version"] = 1
    del manifest["files"]["reservations.py"]
    raw = installer.canonical(manifest)
    (source / "manifest.json").write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    bootstrap.install(source, target, digest)
    assert bootstrap.verify(target, digest)["execution_authorized"] is False
    assert set(installer.validate(str(source), digest)[1]) == set(installer.LEGACY_FILES)
    # Historical content can be inspected, but cannot claim current-package preflight.
    with pytest.raises(ValueError, match="runner_package_binding_mismatch"):
        bootstrap.preflight(source, digest)
    assert (
        main(["runner", "preflight", "--bundle", str(source), "--expected-plan-sha256", digest])
        == 1
    )
    report = capsys.readouterr().out
    assert str(source) not in report and "REJECTED" in report


def test_reservation_asset_tamper_rejected(prepared):
    source, target, digest = prepared
    (source / "reservations.py").write_bytes(b"altered")
    with pytest.raises(ValueError, match="asset_drift"):
        bootstrap.install(source, target, digest)
    assert not (target / "runtime").exists()


@pytest.fixture
def operator_bound(prepared_bound, monkeypatch):
    # Portable content fixtures; actual shared flock is tested separately below.
    monkeypatch.setattr(installer, "_operator_lock", lambda target: None)
    source, target, digest = prepared_bound
    bootstrap.install(source, target, digest)
    binary = target / "bin"
    binary.mkdir()
    (binary / "cadence-runner").write_bytes(b"historical-reference")
    (target / "active-runner.json").write_bytes(b"historical-pointer")
    (target / "runner-revoked.json").write_bytes(b"historical-revocation")
    (target / "counter.json").write_bytes(b"historical-counter")
    return source, target, digest


def test_operator_activation_coexists_and_repeat_preserves_history(operator_bound):
    _, target, digest = operator_bound
    before = {p.relative_to(target): p.read_bytes() for p in target.rglob("*") if p.is_file()}
    first = installer.operator_activation(str(target), digest)
    assert first["status"] == "OPERATOR_ACTIVATION_RECORDED_NOT_QUALIFIED"
    assert not first["execution_authorized"]
    assert (
        installer.operator_activation(str(target), digest)["status"]
        == "EXISTING_EXACT_OPERATOR_ACTIVATION"
    )
    for name, data in before.items():
        assert (target / name).read_bytes() == data
    assert (target / "bin/cadence-operator-runner").read_bytes() == (
        target / "runtime" / digest / "launcher.py"
    ).read_bytes()


def test_operator_partial_activation_resumes_exact_launcher(operator_bound, monkeypatch):
    _, target, digest = operator_bound
    original = installer.exclusive

    def interrupted(path, content, mode=384):
        if path.endswith("active-operator-runner.json"):
            raise OSError("simulated interruption before pointer")
        return original(path, content, mode)

    monkeypatch.setattr(installer, "exclusive", interrupted)
    with pytest.raises(OSError, match="interruption"):
        installer.operator_activation(str(target), digest)
    assert (target / "bin/cadence-operator-runner").exists()
    assert not (target / "active-operator-runner.json").exists()
    monkeypatch.setattr(installer, "exclusive", original)
    assert (
        installer.operator_activation(str(target), digest)["status"]
        == "OPERATOR_ACTIVATION_RECORDED_NOT_QUALIFIED"
    )


def test_operator_launcher_collision_fails_without_overwrite(operator_bound):
    _, target, digest = operator_bound
    launcher = target / "bin/cadence-operator-runner"
    launcher.write_bytes(b"unrelated code")
    launcher.chmod(0o700)
    with pytest.raises(ValueError, match="operator_launcher_collision"):
        installer.operator_activation(str(target), digest)
    assert launcher.read_bytes() == b"unrelated code"
    assert not (target / "active-operator-runner.json").exists()


def test_operator_deactivation_is_repeatable_preserves_bytes_and_blocks_reactivation(
    operator_bound,
):
    _, target, digest = operator_bound
    installer.operator_activation(str(target), digest)
    before = (target / "active-operator-runner.json").read_bytes()
    assert installer.operator_deactivate(str(target), digest)["execution_authorized"] is False
    assert installer.operator_deactivate(str(target), digest)["execution_authorized"] is False
    assert (target / "active-operator-runner.json").read_bytes() == before
    with pytest.raises(ValueError, match="operator_runner_revoked"):
        installer.operator_activation(str(target), digest)
    assert (target / "runner-revoked.json").read_bytes() == b"historical-revocation"


def test_operator_wrong_manifest_and_active_jobs_deny_before_writes(operator_bound):
    _, target, digest = operator_bound
    (target / "execution.lock").write_bytes(b"unresolved")
    with pytest.raises(ValueError, match="active_or_unresolved_jobs"):
        installer.operator_activation(str(target), digest)
    assert not (target / "bin/cadence-operator-runner").exists()
    assert (target / "counter.json").read_bytes() == b"historical-counter"


def test_operator_lock_requires_existing_domain_and_obeys_flock(tmp_path, monkeypatch):
    import os
    import stat

    if os.name == "nt":
        pytest.skip("Linux shared resource lock")
    import fcntl

    real_lstat = os.lstat

    # The fixture ancestors are deliberately disposable /tmp, not a native target.
    def fixture_stat(path):
        info = real_lstat(path)
        if str(path) in ("/tmp", "/tmp/pytest-of-root"):
            parts = list(info)
            parts[0] = stat.S_IFDIR | 0o755
            return os.stat_result(parts)
        return info

    monkeypatch.setattr(os, "lstat", fixture_stat)
    with pytest.raises(OSError):
        installer._operator_lock(str(tmp_path))
    lock = tmp_path / "run.lock"
    assert not lock.exists()
    lock.write_bytes(b"")
    lock.chmod(0o600)
    with lock.open("rb") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ValueError, match="operator_domain_busy"):
            installer._operator_lock(str(tmp_path))
    fd = installer._operator_lock(str(tmp_path))
    os.close(fd)


@pytest.mark.parametrize("version", [True, 1.0])
def test_operator_state_rejects_coerced_version_without_mutation(operator_bound, version):
    _, target, digest = operator_bound
    state = target / "active-operator-runner.json"
    raw = installer.canonical({"schema_version": version, "manifest_sha256": digest})
    state.write_bytes(raw)
    state.chmod(0o600)
    with pytest.raises(ValueError, match="operator_state_shape"):
        installer.operator_activation(str(target), digest)
    assert state.read_bytes() == raw
    assert not (target / "bin/cadence-operator-runner").exists()


@pytest.fixture
def operator_update_pair(operator_bound):
    source, target, previous = operator_bound
    installer.operator_activation(str(target), previous)
    launcher = source / "launcher.py"
    launcher.write_bytes(launcher.read_bytes() + b"\n# new synthetic preflight launcher revision\n")
    manifest = json.loads((source / "manifest.json").read_bytes())
    manifest["files"]["launcher.py"] = {
        "sha256": hashlib.sha256(launcher.read_bytes()).hexdigest(),
        "bytes": len(launcher.read_bytes()),
    }
    raw = installer.canonical(manifest)
    (source / "manifest.json").write_bytes(raw)
    expected = hashlib.sha256(raw).hexdigest()
    bootstrap.install(source, target, expected)
    return source, target, previous, expected


def test_operator_preflight_update_preserves_history_and_is_idempotent(operator_update_pair):
    _, target, previous, expected = operator_update_pair
    old_version = target / "runtime" / previous
    old = {p.name: p.read_bytes() for p in old_version.iterdir()}
    receipt = installer.operator_preflight_update(str(target), expected, previous)
    assert receipt["execution_authorized"] is False
    assert receipt["status"] == "OPERATOR_PREFLIGHT_UPDATE_RECORDED"
    snapshot = {p.relative_to(target): p.read_bytes() for p in target.rglob("*") if p.is_file()}
    assert installer.operator_preflight_update(str(target), expected, previous) == receipt
    assert {
        p.relative_to(target): p.read_bytes() for p in target.rglob("*") if p.is_file()
    } == snapshot
    assert {p.name: p.read_bytes() for p in old_version.iterdir()} == old
    assert (target / "bin/cadence-runner").read_bytes() == b"historical-reference"
    assert (target / "active-runner.json").read_bytes() == b"historical-pointer"
    assert (target / "counter.json").read_bytes() == b"historical-counter"


def test_operator_preflight_update_recovers_interrupted_pair(operator_update_pair, monkeypatch):
    _, target, previous, expected = operator_update_pair
    original = installer._replace_operator_file

    def interrupted(source, destination):
        if destination.endswith("active-operator-runner.json"):
            raise OSError("simulated crash between launcher and pointer")
        return original(source, destination)

    monkeypatch.setattr(installer, "_replace_operator_file", interrupted)
    with pytest.raises(OSError, match="simulated crash"):
        installer.operator_preflight_update(str(target), expected, previous)
    assert (
        json.loads((target / "active-operator-runner.json").read_bytes())["manifest_sha256"]
        == previous
    )
    assert (target / "bin/cadence-operator-runner").read_bytes() == (
        target / "runtime" / expected / "launcher.py"
    ).read_bytes()
    monkeypatch.setattr(installer, "_replace_operator_file", original)
    installer.operator_preflight_update(str(target), expected, previous)
    assert (
        json.loads((target / "active-operator-runner.json").read_bytes())["manifest_sha256"]
        == expected
    )


def test_operator_preflight_update_refuses_orphan_replacement(operator_update_pair):
    _, target, previous, expected = operator_update_pair
    state = target / "active-operator-runner.json"
    state.write_bytes(installer.canonical({"schema_version": 1, "manifest_sha256": expected}))
    (target / "bin/cadence-operator-runner").write_bytes(
        (target / "runtime" / expected / "launcher.py").read_bytes()
    )
    with pytest.raises(ValueError, match="operator_update_history_missing"):
        installer.operator_preflight_update(str(target), expected, previous)
    assert not (target / "operator-activation-history").exists() or not list(
        (target / "operator-activation-history").iterdir()
    )


@pytest.mark.parametrize("change", ["runner.py", "profile.json", "probe.py", "reservations.py"])
def test_operator_preflight_update_refuses_nonlauncher_change(operator_update_pair, change):
    source, target, previous, _ = operator_update_pair
    asset = source / change
    asset.write_bytes(asset.read_bytes() + b"\n")
    manifest = json.loads((source / "manifest.json").read_bytes())
    digest = hashlib.sha256(asset.read_bytes()).hexdigest()
    manifest["files"][change] = {"sha256": digest, "bytes": len(asset.read_bytes())}
    if change == "profile.json":
        manifest["profile_sha256"] = digest
    raw = installer.canonical(manifest)
    (source / "manifest.json").write_bytes(raw)
    expected = hashlib.sha256(raw).hexdigest()
    bootstrap.install(source, target, expected)
    before = (target / "active-operator-runner.json").read_bytes()
    with pytest.raises(ValueError, match="preflight_only_update_required"):
        installer.operator_preflight_update(str(target), expected, previous)
    assert (target / "active-operator-runner.json").read_bytes() == before
    assert not (target / "operator-activation-history").exists()


def test_operator_update_rejects_reversed_pair(operator_update_pair):
    _, target, previous, expected = operator_update_pair
    installer.operator_preflight_update(str(target), expected, previous)
    (target / "bin/cadence-operator-runner").write_bytes(
        (target / "runtime" / previous / "launcher.py").read_bytes()
    )
    with pytest.raises(ValueError, match="operator_update_state_drift"):
        installer.operator_preflight_update(str(target), expected, previous)
    assert (
        json.loads((target / "active-operator-runner.json").read_bytes())["manifest_sha256"]
        == expected
    )


def test_operator_lock_rechecks_path_after_flock(tmp_path, monkeypatch):
    import os

    if os.name != "posix":
        pytest.skip("POSIX lock replacement race")
    import fcntl

    root = tmp_path / "managed"
    root.mkdir(mode=0o700)
    lock = root / "run.lock"
    lock.write_bytes(b"original lock")
    lock.chmod(0o600)
    original = fcntl.flock

    def replace_after_acquire(fd, operation):
        original(fd, operation)
        lock.rename(root / "preserved-lock")
        lock.write_bytes(b"replacement lock")
        lock.chmod(0o600)

    monkeypatch.setattr(fcntl, "flock", replace_after_acquire)
    with pytest.raises(ValueError, match="operator_lock_drift"):
        installer._operator_lock(str(root))
    assert (root / "preserved-lock").read_bytes() == b"original lock"
    assert lock.read_bytes() == b"replacement lock"
