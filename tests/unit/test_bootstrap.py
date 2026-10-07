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


def test_existing_active_marker_and_update_are_rejected(prepared):
    source, target, digest = prepared
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
    assert set(manifest["files"]) == {"runner.py", "probe.py", "profile.json", "launcher.py"}
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


def test_launcher_collision_preserves_existing_reference(prepared):
    source, target, digest = prepared
    bootstrap.install(source, target, digest)
    binary = target / "bin"
    binary.mkdir()
    existing = binary / "cadence-runner"
    existing.write_bytes(b"historical-reference")
    with pytest.raises(FileExistsError):
        installer.activation(str(target), digest, None)
    assert existing.read_bytes() == b"historical-reference"
    assert not (target / "active-runner.json").exists()


def test_deactivation_preserves_version_and_pointer(prepared):
    source, target, digest = prepared
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
    assert argv[-3] == "preflight" and argv[-2] == digest and len(argv[-1]) == 32
    assert "StrictHostKeyChecking=yes" in argv
    assert not list(source.glob("*.sqlite3"))
