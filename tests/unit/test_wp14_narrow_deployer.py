from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
DEPLOYER = ROOT / "scripts" / "deploy-wp14-narrow.ps1"
PACKAGE = (
    ROOT
    / "docs"
    / "approvals"
    / ("WP14_BOUNDED_READ_ONLY_DISCOVERY_DEPLOYMENT_EXECUTION_APPROVAL_PACKAGE_V1.json")
)
LINEAGE = ROOT / "remote" / "config" / "runner-lineage.json"
PACKAGE_HASH = "7d93fefb96c65dd9a204a4de3fb0dba087ca112edf894bb3ff97e7ee0d3c6f87"
OLD_DEPLOYER_HASH = "b48b7cb2b24cb3a8ac257031dd6fa79116ea71a4b2117e22226683837692bc1e"
AUTHORIZATION = Path("docs/approvals/WP14_NARROW_REMOTE_DEPLOYMENT_AUTHORIZATION_V1.json")
PWSH = shutil.which("pwsh")


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
    for binding in package["bound_contracts"]:
        assert normalized_hash(ROOT / binding["path"]) == binding["normalized_lf_sha256"]


def test_deployer_is_argument_free_exact_scope_and_keeps_broad_gate_disabled() -> None:
    deployer = DEPLOYER.read_text(encoding="utf-8")
    lineage = json.loads(LINEAGE.read_text(encoding="utf-8"))
    assert re.search(r"param\(\s*\)", deployer)
    assert lineage["deployment_enabled"] is False
    assert "deployment_enabled -ne $false" in deployer
    assert "WP14_NARROW_REMOTE_DEPLOYMENT_AUTHORIZATION_V1.json" in deployer
    assert "deployer_normalized_lf_sha256" in deployer
    assert "package_normalized_lf_sha256" in deployer
    assert "max_uses -ne 1" in deployer
    assert "maximumWallClockSeconds = 300" in deployer
    assert "maximumOutputBytes = 65536" in deployer
    assert "ServerAliveCountMax=2" in deployer
    assert "wp14-v1-new" in deployer
    assert "deployment-snapshots/wp14-7d93fefb-runner-0.19.0" in deployer
    assert "$snapshot.Add(\"mkdir '$snapshotRoot'\")" in deployer
    assert "$snapshot.Add(\"mkdir -p '$snapshotRoot'\")" not in deployer
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


@pytest.fixture
def isolated_deployer(tmp_path: Path) -> Path:
    """Copy only public repository assets; never copy the live authorization record."""
    fixture = tmp_path / "isolated fixture"
    fixture.mkdir()
    package = json.loads(PACKAGE.read_text(encoding="utf-8"))
    relative_paths = [
        DEPLOYER.relative_to(ROOT),
        PACKAGE.relative_to(ROOT),
        *(Path(entry["path"]) for entry in package["bound_contracts"]),
        *(Path(entry["path"]) for entry in package["deployment_asset_allowlist"]),
    ]
    for relative in relative_paths:
        destination = fixture / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, destination)
    shutil.copyfile(
        ROOT / "tests/fixtures/wp14_narrow_fake_transport.ps1",
        fixture / "harness.ps1",
    )
    (fixture / "empty-bin").mkdir()
    (fixture / "scratch").mkdir()
    assert not (fixture / AUTHORIZATION).exists()
    return fixture


def authorize_fixture(fixture: Path, **overrides: object) -> None:
    """Synthetic authority in tmp_path only; not a user grant or repository activation."""
    assert fixture.name == "isolated fixture"
    assert fixture.resolve() != ROOT.resolve()
    record = {
        "record_kind": "explicit_remote_preflight_and_deployment_authorization",
        "status": "APPROVED",
        "package_normalized_lf_sha256": PACKAGE_HASH,
        "deployer_normalized_lf_sha256": normalized_hash(fixture / DEPLOYER.relative_to(ROOT)),
        "remote_preflight_authorized": True,
        "remote_deployment_authorized": True,
        "max_uses": 1,
    }
    record.update(overrides)
    (fixture / AUTHORIZATION).write_text(json.dumps(record), encoding="utf-8")


def run_fixture(fixture: Path, scenario: str = "success") -> dict[str, Any]:
    assert PWSH is not None, "PowerShell is required for isolated deployer tests"
    assert fixture.name == "isolated fixture"
    assert fixture.resolve() != ROOT.resolve()
    env = os.environ.copy()
    # Do not inherit executable search paths: even a missing fake cannot find native SSH/SCP.
    env["PATH"] = str(fixture / "empty-bin")
    env["TEMP"] = env["TMP"] = str(fixture / "scratch")
    completed = subprocess.run(
        [
            PWSH,
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(fixture / "harness.ps1"),
            "-Scenario",
            scenario,
        ],
        cwd=fixture,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    records = [
        line.removeprefix("WP14_TEST_RESULT=")
        for line in completed.stdout.splitlines()
        if line.startswith("WP14_TEST_RESULT=")
    ]
    assert len(records) == 1, completed.stdout
    return json.loads(records[0])


def assert_generated_formats(calls: list[dict[str, Any]]) -> None:
    """Check generated strings without interpreting or executing any shell command."""
    snapshot = next(call["command"] for call in calls if call["stage"] == "snapshot")
    formats = re.findall(r"printf '([^']*)'", snapshot)
    assert formats.count(r"%s\t%s\t%s\n") == 11
    assert formats.count(r"%s\tABSENT\tABSENT\n") == 11
    # A single escaped semicolon must become an argument, not a shell control separator.
    find_command = next(part for part in snapshot.split("; ") if part.startswith("find "))
    lexer = shlex.shlex(find_command, posix=True, punctuation_chars=";")
    lexer.whitespace_split = True
    tokens = list(lexer)
    assert tokens[-3:] == ["500", "{}", ";"]
    assert find_command.endswith(r"{} \;")
    assert r"{} \\;" not in snapshot
    for call in calls:
        if call["kind"] == "ssh":
            marker = re.search(r"printf '(WP14_NARROW_[^']*)'", call["command"])
            assert marker is not None
            assert re.fullmatch(r"WP14_NARROW_[A-Z_]+\\n", marker[1])


def test_missing_authorization_stops_before_fake_transport(isolated_deployer: Path) -> None:
    result = run_fixture(isolated_deployer)
    assert result["success"] is False
    assert "Remote preflight and deployment are not authorized" in result["error"]
    assert "no remote command was invoked" in result["error"]
    assert result["calls"] == []


def test_authorized_flow_uses_only_exact_fake_assets_and_correct_formats(
    isolated_deployer: Path,
) -> None:
    authorize_fixture(isolated_deployer)
    result = run_fixture(isolated_deployer)
    assert result["success"] is True, result["error"]
    assert result["output"] == ["WP14_NARROW_DEPLOYMENT_VERIFIED"]
    calls = result["calls"]
    assert [call["stage"] for call in calls] == (
        ["preflight", "snapshot"] + ["upload", "install"] * 11 + ["verify"]
    )
    assert_generated_formats(calls)
    package = json.loads(PACKAGE.read_text(encoding="utf-8"))
    uploads = [call for call in calls if call["kind"] == "scp"]
    for upload, asset in zip(uploads, package["deployment_asset_allowlist"], strict=True):
        relative = asset["path"].removeprefix("remote/")
        assert upload["destination"] == (
            f"cadence-vm:/home/buet/cds_work/.cadence_mcp/{relative}.wp14-v1-new"
        )
        assert upload["sha256"] == asset["normalized_lf_sha256"]
    installs = [call["command"] for call in calls if call["stage"] == "install"]
    for command, asset in zip(installs, package["deployment_asset_allowlist"], strict=True):
        assert asset["normalized_lf_sha256"] in command
        assert f"chmod '{asset['remote_mode'][1:]}'" in command
        assert "mv '" in command
    preflight = calls[0]["command"]
    assert "'cadence-runner'" not in preflight  # Only the absolute compiled-in path.
    assert "/bin/cadence-runner' version)" in preflight and "= '0.18.0'" in preflight
    assert "readlink -f" in preflight and "test ! -L" in preflight
    verification = calls[-1]["command"]
    assert "= '0.19.0'" in verification
    assert "wp14-role-discovery) runner_wp14_role_discovery" in verification
    assert "bin/cadence-runner' wp14-role-discovery" not in verification


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("deployer_normalized_lf_sha256", OLD_DEPLOYER_HASH),
        ("package_normalized_lf_sha256", "0" * 64),
        ("record_kind", "user_approval_record_not_deployer_activation"),
        ("status", "BLOCKED_BEFORE_REMOTE_PREFLIGHT"),
        ("remote_preflight_authorized", False),
        ("remote_deployment_authorized", False),
        ("max_uses", 0),
        ("max_uses", 2),
    ],
)
def test_invalid_or_previous_authorization_cannot_reach_fake_transport(
    isolated_deployer: Path,
    field: str,
    value: object,
) -> None:
    authorize_fixture(isolated_deployer, **{field: value})
    result = run_fixture(isolated_deployer)
    assert result["success"] is False
    assert "remote authorization is invalid" in result["error"]
    assert result["calls"] == []


@pytest.mark.parametrize(
    "relative",
    [
        str(PACKAGE.relative_to(ROOT)),
        "remote/bin/cadence-runner",
        "docs/plans/WP14_FIXED_NAMES_ONLY_ROLE_DISCOVERY_PLAN_V1.json",
    ],
)
def test_tampered_local_binding_stops_before_fake_transport(
    isolated_deployer: Path,
    relative: str,
) -> None:
    target = isolated_deployer / relative
    target.write_bytes(target.read_bytes() + b"\n")
    authorize_fixture(isolated_deployer)
    result = run_fixture(isolated_deployer)
    assert result["success"] is False
    assert result["calls"] == []


@pytest.mark.parametrize(
    ("stage", "expected_calls"),
    [("preflight", 1), ("snapshot", 2), ("scp", 3), ("install", 4), ("verify", 25)],
)
def test_fake_failure_has_no_retry_cleanup_or_later_stage(
    isolated_deployer: Path,
    stage: str,
    expected_calls: int,
) -> None:
    authorize_fixture(isolated_deployer)
    result = run_fixture(isolated_deployer, f"fail-{stage}")
    assert result["success"] is False
    assert "No retry, cleanup, or fallback" in result["error"]
    assert len(result["calls"]) == expected_calls


@pytest.mark.parametrize(
    ("stage", "expected_calls"),
    [("preflight", 1), ("snapshot", 2), ("install", 4), ("verify", 25)],
)
def test_unexpected_fake_response_stops_without_later_stage(
    isolated_deployer: Path,
    stage: str,
    expected_calls: int,
) -> None:
    authorize_fixture(isolated_deployer)
    result = run_fixture(isolated_deployer, f"wrong-{stage}")
    assert result["success"] is False
    assert len(result["calls"]) == expected_calls


@pytest.mark.parametrize(("kind", "expected_calls"), [("ssh", 1), ("scp", 3)])
def test_completed_fake_output_overflow_is_rejected(
    isolated_deployer: Path,
    kind: str,
    expected_calls: int,
) -> None:
    authorize_fixture(isolated_deployer)
    result = run_fixture(isolated_deployer, f"overflow-{kind}")
    assert result["success"] is False
    assert "exceeded the output limit" in result["error"]
    assert len(result["calls"]) == expected_calls
    assert "X" * 100 not in result["error"]


def test_expired_budget_before_transport_is_rejected(isolated_deployer: Path) -> None:
    # Test-only deadline injection; the production constant remains exactly 300 seconds.
    script = isolated_deployer / DEPLOYER.relative_to(ROOT)
    script.write_text(
        script.read_text(encoding="utf-8").replace(
            "$maximumWallClockSeconds = 300", "$maximumWallClockSeconds = 0"
        ),
        encoding="utf-8",
    )
    authorize_fixture(isolated_deployer)
    result = run_fixture(isolated_deployer)
    assert result["success"] is False
    assert "wall-clock limit" in result["error"]
    assert result["calls"] == []


def test_whatif_does_not_call_even_fake_transport(isolated_deployer: Path) -> None:
    authorize_fixture(isolated_deployer)
    result = run_fixture(isolated_deployer, "whatif")
    assert result["success"] is True
    assert result["calls"] == []


def test_regression_double_escaped_marker_is_detected(isolated_deployer: Path) -> None:
    script = isolated_deployer / DEPLOYER.relative_to(ROOT)
    script.write_text(
        script.read_text(encoding="utf-8").replace(r"PREFLIGHT_OK\n", r"PREFLIGHT_OK\\n"),
        encoding="utf-8",
    )
    authorize_fixture(isolated_deployer)
    result = run_fixture(isolated_deployer)
    assert result["success"] is False
    assert "unexpected response" in result["error"]
    assert len(result["calls"]) == 1


@pytest.mark.parametrize(
    ("correct", "broken"),
    [(r"%s\t%s\t%s\n", r"%s\\t%s\\t%s\\n"), (r"{} \;", r"{} \\;")],
)
def test_generated_string_checker_detects_snapshot_regressions(
    isolated_deployer: Path,
    correct: str,
    broken: str,
) -> None:
    script = isolated_deployer / DEPLOYER.relative_to(ROOT)
    script.write_text(script.read_text(encoding="utf-8").replace(correct, broken), encoding="utf-8")
    authorize_fixture(isolated_deployer)
    result = run_fixture(isolated_deployer)
    # The fake does not execute find/printf; the independent lexical checks must catch this.
    assert result["success"] is True
    with pytest.raises(AssertionError):
        assert_generated_formats(result["calls"])


def test_review_characterizes_single_use_gap_with_fake_preflight_only(
    isolated_deployer: Path,
) -> None:
    """Known gap, not acceptance of replay: a failed preflight leaves the record reusable."""
    authorize_fixture(isolated_deployer)
    before = (isolated_deployer / AUTHORIZATION).read_bytes()
    for _ in range(2):
        result = run_fixture(isolated_deployer, "fail-preflight")
        assert result["success"] is False
        assert len(result["calls"]) == 1
    assert (isolated_deployer / AUTHORIZATION).read_bytes() == before
    assert sorted(path.name for path in (isolated_deployer / "docs/approvals").iterdir()) == [
        PACKAGE.name,
        AUTHORIZATION.name,
    ]
