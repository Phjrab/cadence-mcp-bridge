from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEPLOYER = ROOT / "scripts" / "deploy-wp14-narrow.ps1"
PACKAGE = ROOT / "docs" / "approvals" / (
    "WP14_BOUNDED_READ_ONLY_DISCOVERY_DEPLOYMENT_EXECUTION_APPROVAL_PACKAGE_V1.json"
)
LINEAGE = ROOT / "remote" / "config" / "runner-lineage.json"
PACKAGE_HASH = "7d93fefb96c65dd9a204a4de3fb0dba087ca112edf894bb3ff97e7ee0d3c6f87"


def normalized_hash(path: Path) -> str:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(text.encode()).hexdigest()


def test_immutable_package_and_all_exact_assets_are_bound() -> None:
    package = json.loads(PACKAGE.read_text(encoding="utf-8"))
    deployer = DEPLOYER.read_text(encoding="utf-8")
    assert normalized_hash(PACKAGE) == PACKAGE_HASH
    assert package["record_kind"] == "approval_request_not_grant"
    assert all(value is False for value in package["authority"].values())
    assert len(package["deployment_asset_allowlist"]) == 11
    fixed_paths = set(re.findall(r'Path = "(remote/[^"]+)"', deployer))
    package_paths = {asset["path"] for asset in package["deployment_asset_allowlist"]}
    assert fixed_paths == package_paths
    for asset in package["deployment_asset_allowlist"]:
        path = ROOT / asset["path"]
        assert path.is_file()
        assert normalized_hash(path) == asset["normalized_lf_sha256"]
        assert deployer.count(asset["normalized_lf_sha256"]) == 1
        assert asset["remote_mode"] in {"0600", "0700"}


def test_deployer_is_argument_free_exact_scope_and_keeps_broad_gate_disabled() -> None:
    deployer = DEPLOYER.read_text(encoding="utf-8")
    lineage = json.loads(LINEAGE.read_text(encoding="utf-8"))
    assert re.search(r"param\(\s*\)", deployer)
    assert lineage["deployment_enabled"] is False
    assert 'deployment_enabled -ne $false' in deployer
    assert "WP14_NARROW_REMOTE_DEPLOYMENT_AUTHORIZATION_V1.json" in deployer
    assert "deployer_normalized_lf_sha256" in deployer
    assert "package_normalized_lf_sha256" in deployer
    assert "max_uses -ne 1" in deployer
    assert "maximumWallClockSeconds = 300" in deployer
    assert "maximumOutputBytes = 65536" in deployer
    assert "ServerAliveCountMax=2" in deployer
    assert "wp14-v1-new" in deployer
    assert "deployment-snapshots/wp14-7d93fefb-runner-0.19.0" in deployer
    assert '$snapshot.Add("mkdir \'$snapshotRoot\'")' in deployer
    assert '$snapshot.Add("mkdir -p \'$snapshotRoot\'")' not in deployer
    assert "WP14_NARROW_DEPLOYMENT_VERIFIED" in deployer
    assert "run-design-write" not in deployer
    assert "design-write" not in deployer
    assert "MCP_WorkLib" not in deployer
    for forbidden in ("Invoke-Expression", "eval ", "bash -c", "sh -c"):
        assert forbidden not in deployer


def test_separate_authorization_gate_precedes_transport_and_remote_calls() -> None:
    deployer = DEPLOYER.read_text(encoding="utf-8")
    gate = deployer.index("Assert-SeparateRemoteAuthorization\n")
    transport_lookup = deployer.index('foreach ($command in @("ssh", "scp"))')
    first_remote_call = deployer.index("Invoke-FixedSsh -FixedCommand ($preflight")
    assert gate < transport_lookup < first_remote_call
    authorization = (
        ROOT
        / "docs"
        / "approvals"
        / "WP14_NARROW_REMOTE_DEPLOYMENT_AUTHORIZATION_V1.json"
    )
    assert not authorization.exists()


def test_current_execution_fails_closed_before_transport(tmp_path: Path) -> None:
    marker = tmp_path / "transport-called"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    for name in ("ssh.cmd", "scp.cmd"):
        (fake_bin / name).write_text(f"@echo called>{marker}\r\n", encoding="utf-8")

    env = os.environ.copy()
    env["PATH"] = str(fake_bin) + os.pathsep + env.get("PATH", "")
    completed = subprocess.run(
        ["pwsh", "-NoLogo", "-NoProfile", "-NonInteractive", "-File", str(DEPLOYER)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    combined = completed.stdout + completed.stderr
    assert completed.returncode != 0
    assert "Remote preflight and deployment are not authorized" in combined
    assert "no remote command was invoked" in combined
    assert not marker.exists()


def test_remote_verification_is_syntax_and_surface_only() -> None:
    deployer = DEPLOYER.read_text(encoding="utf-8")
    verify = deployer[deployer.index("$verify =") :]
    assert "bash -n" in verify
    assert "compile(open(sys.argv[1]" in verify
    assert "cadence-runner' version" in verify
    assert "inspect-ade-profile) runner_inspect_ade_profile" in verify
    assert "wp14-role-discovery) runner_wp14_role_discovery" in verify
    for forbidden in (
        "virtuoso -nograph",
        "ocean -nograph",
        "spectre ",
        "submit-profile",
        "actual-profile-baseline-audit",
        "inspect-ade-profile actual",
        "cadence-runner' wp14-role-discovery",
        "dbOpenCellView",
    ):
        assert forbidden not in verify
