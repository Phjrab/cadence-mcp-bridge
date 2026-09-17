from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
DEPLOYER = ROOT / "scripts" / "deploy-wp14-narrow.ps1"
PACKAGE = (
    ROOT
    / "docs"
    / "approvals"
    / ("WP14_BOUNDED_READ_ONLY_DISCOVERY_DEPLOYMENT_EXECUTION_APPROVAL_PACKAGE_V2.json")
)
LINEAGE = ROOT / "remote" / "config" / "runner-lineage.json"
PACKAGE_HASH = "96d8f001776eb61da5ef09ba3945d988bf587c716fea95a35ad890aa95ba2431"
CLAIM_HASH = "7d93fefb96c65dd9a204a4de3fb0dba087ca112edf894bb3ff97e7ee0d3c6f87"
OLD_DEPLOYER_HASH = "b48b7cb2b24cb3a8ac257031dd6fa79116ea71a4b2117e22226683837692bc1e"
AUTHORIZATION = Path("docs/approvals/WP14_NARROW_REMOTE_DEPLOYMENT_AUTHORIZATION_V2.json")
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
    assert "WP14_NARROW_REMOTE_DEPLOYMENT_AUTHORIZATION_V2.json" in deployer
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
    transport_lookup = deployer.index("Claim-OneAttempt\n", gate)
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
    shutil.copyfile(ROOT / "tests/fixtures/wp14_fake_process.py", fixture / "fake.py")
    # Fixture-only source rewriting, not a production test switch or arbitrary executable hook.
    script = fixture / DEPLOYER.relative_to(ROOT)
    text = script.read_text(encoding="utf-8")
    original = (
        "$process.StartInfo.FileName = Join-Path ([Environment]::GetFolderPath('Windows')) "
        '"System32\\OpenSSH\\$Kind.exe"'
    )
    assert text.count(original) == 1
    replacement = (
        f"$process.StartInfo.FileName = '{sys.executable.replace(chr(39), chr(39) * 2)}'\n"
        "$process.StartInfo.ArgumentList.Add((Join-Path $projectRoot 'fake.py'))\n"
        "$process.StartInfo.ArgumentList.Add($Kind)"
    )
    text = text.replace(original, replacement)
    original_state = (
        "Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) "
        "'CadenceMcpBridge\\wp14-narrow'"
    )
    assert text.count(original_state) == 1
    text = text.replace(original_state, "(Join-Path $projectRoot 'ledger')")
    text = text.replace(
        "[Security.Principal.WindowsIdentity]::GetCurrent().User.Value", "'fixture-sid'"
    ).replace(
        "(Get-ItemProperty -LiteralPath 'HKLM:\\SOFTWARE\\Microsoft\\Cryptography').MachineGuid",
        "'fixture-machine'",
    )
    assert "System32\\OpenSSH" not in text
    script.write_text(text, encoding="utf-8")
    (fixture / "empty-bin").mkdir()
    (fixture / "scratch").mkdir()
    assert not (fixture / AUTHORIZATION).exists()
    return fixture


def authorize_fixture(fixture: Path, **overrides: object) -> None:
    """Synthetic authority in tmp_path only; not a user grant or repository activation."""
    assert fixture.name == "isolated fixture"
    assert fixture.resolve() != ROOT.resolve()
    record = {
        "schema_version": 2,
        "record_kind": "explicit_remote_preflight_and_deployment_authorization",
        "status": "APPROVED",
        "package_normalized_lf_sha256": PACKAGE_HASH,
        "deployer_normalized_lf_sha256": normalized_hash(fixture / DEPLOYER.relative_to(ROOT)),
        "remote_preflight_authorized": True,
        "remote_deployment_authorized": True,
        "max_uses": 1,
        "authorization_id": "11111111-2222-3333-4444-555555555555",
        "executor_binding": hashlib.sha256(b"fixture-sid|fixture-machine").hexdigest(),
        "not_before": (datetime.now(UTC) - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expires_at": (datetime.now(UTC) + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "observed_at": (datetime.now(UTC) - timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "evidence_sha256": hashlib.sha256(b"synthetic evidence only").hexdigest(),
        "remote_identity": {
            "hostname": "cadence",
            "user": "buet",
            "root": "/home/buet/cds_work/.cadence_mcp",
            "verified": True,
        },
        "preimages": [
            {
                "path": entry["path"],
                "presence": "file",
                "sha256": hashlib.sha256(entry["path"].encode()).hexdigest(),
                "mode": entry["remote_mode"][1:],
            }
            for entry in json.loads(PACKAGE.read_text(encoding="utf-8"))[
                "deployment_asset_allowlist"
            ]
        ],
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
            # Failed non-final AND operands do not trigger Bash errexit on their own.
            for assertion in call["command"].split(";"):
                if " && " in assertion:
                    assert " || exit 42" in assertion
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


def test_failed_preflight_consumes_record_and_blocks_replay(
    isolated_deployer: Path,
) -> None:
    authorize_fixture(isolated_deployer)
    before = (isolated_deployer / AUTHORIZATION).read_bytes()
    first = run_fixture(isolated_deployer, "fail-preflight")
    assert first["success"] is False and len(first["calls"]) == 1
    claim = isolated_deployer / "ledger" / f"attempt-{CLAIM_HASH}.json"
    assert json.loads(claim.read_text())["state"] == "consumed_before_transport"
    claim_before = claim.read_bytes()
    result = run_fixture(isolated_deployer, "fail-preflight")
    assert result["success"] is False
    assert "already consumed" in result["error"]
    assert len(result["calls"]) == 1  # No additional process; file retains first call.
    assert claim.read_bytes() == claim_before
    assert (isolated_deployer / AUTHORIZATION).read_bytes() == before
    assert sorted(path.name for path in (isolated_deployer / "docs/approvals").iterdir()) == [
        PACKAGE.name,
        AUTHORIZATION.name,
    ]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_uses", "1"),
        ("schema_version", "2"),
        ("remote_preflight_authorized", "true"),
        ("executor_binding", "unknown"),
        ("evidence_sha256", None),
        ("observed_at", "2000-01-01T00:00:00Z"),
        ("expires_at", "2000-01-01T00:00:00Z"),
        ("preimages", []),
        ("authorization_id", "../escape"),
    ],
)
def test_closed_authority_rejects_unverified_fields(
    isolated_deployer: Path,
    field: str,
    value: object,
) -> None:
    authorize_fixture(isolated_deployer, **{field: value})
    result = run_fixture(isolated_deployer)
    assert result["success"] is False and result["calls"] == []
    assert not (isolated_deployer / "ledger").exists()


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown",
        "duplicate",
        "missing",
        "path",
        "hash",
        "mode",
        "absence",
        "host",
        "unverified",
    ],
)
def test_identity_and_preimages_are_closed_and_required(
    isolated_deployer: Path,
    mutation: str,
) -> None:
    authorize_fixture(isolated_deployer)
    path = isolated_deployer / AUTHORIZATION
    record = json.loads(path.read_text())
    entry = record["preimages"][0]
    if mutation == "unknown":
        record["unexpected"] = True
    elif mutation == "duplicate":
        record["preimages"][1] = entry
    elif mutation == "missing":
        record["preimages"].pop()
    elif mutation == "path":
        entry["path"] = "remote/bin/../../escape"
    elif mutation == "hash":
        entry["sha256"] = "'; touch bad"
    elif mutation == "mode":
        entry["mode"] = "777"
    elif mutation == "absence":
        entry.update(presence="absent", sha256=None, mode=None)
    elif mutation == "host":
        record["remote_identity"]["hostname"] = "unverified"
    else:
        record["remote_identity"]["verified"] = False
    path.write_text(json.dumps(record))
    result = run_fixture(isolated_deployer)
    assert result["success"] is False and result["calls"] == []
    assert not (isolated_deployer / "ledger").exists()


@pytest.mark.parametrize(
    "scenario",
    [
        "hang",
        "flood-stdout",
        "flood-stderr",
        "flood-both",
        "stderr",
        "invalid-utf8",
    ],
)
def test_live_process_is_bounded_without_disclosing_output(
    isolated_deployer: Path,
    scenario: str,
) -> None:
    script = isolated_deployer / DEPLOYER.relative_to(ROOT)
    script.write_text(
        script.read_text().replace("$maximumWallClockSeconds = 300", "$maximumWallClockSeconds = 3")
    )
    authorize_fixture(isolated_deployer)
    start = time.monotonic()
    result = run_fixture(isolated_deployer, scenario)
    assert time.monotonic() - start < 12
    assert result["success"] is False
    assert len(result["calls"]) == 1
    assert "DO_NOT_DISCLOSE" not in result["error"]
    assert "X" * 100 not in result["error"] and "Y" * 100 not in result["error"]
    if scenario == "hang":
        assert "wall-clock limit" in result["error"]
    elif scenario.startswith("flood"):
        assert "output limit" in result["error"]
    # Win32 GetExitCodeProcess via ctypes: confirm the owned fake PID is no longer running.
    import ctypes

    kernel = ctypes.windll.kernel32
    handle = kernel.OpenProcess(0x1000, False, result["calls"][0]["pid"])
    if handle:
        code = ctypes.c_ulong()
        assert kernel.GetExitCodeProcess(handle, ctypes.byref(code))
        kernel.CloseHandle(handle)
        assert code.value != 259


@pytest.mark.parametrize("kind", ["host", "user", "mode", "hash", "symlink", "type", "hardlink"])
def test_modeled_remote_drift_stops_before_snapshot(isolated_deployer: Path, kind: str) -> None:
    authorize_fixture(isolated_deployer)
    result = run_fixture(isolated_deployer, f"drift-{kind}")
    assert result["success"] is False
    assert len(result["calls"]) == 1


def test_preimages_are_checked_before_old_runner_and_each_replacement(
    isolated_deployer: Path,
) -> None:
    authorize_fixture(isolated_deployer)
    result = run_fixture(isolated_deployer)
    assert result["success"] is True, result["error"]
    calls = result["calls"]
    preflight = calls[0]["command"]
    entries = json.loads((isolated_deployer / AUTHORIZATION).read_text())["preimages"]
    runner_position = preflight.index("/bin/cadence-runner' version)")
    for entry, install in zip(entries, calls[3:25:2], strict=True):
        assert preflight.index(entry["sha256"]) < runner_position
        assert entry["sha256"] in calls[1]["command"]
        command = install["command"]
        assert command.index(entry["sha256"]) < command.index("mv '")
    assert calls[-1]["command"].count("bash -n '") == 4


def test_duplicate_json_keys_rejected(isolated_deployer: Path) -> None:
    authorize_fixture(isolated_deployer)
    path = isolated_deployer / AUTHORIZATION
    path.write_text(
        path.read_text().replace(
            '{"schema_version": 2', '{"schema_version": 2, "schema_version": 2'
        )
    )
    result = run_fixture(isolated_deployer)
    assert result["success"] is False and result["calls"] == []
    assert "Duplicate" in result["error"]


def test_incomplete_claim_is_never_repaired_or_removed(isolated_deployer: Path) -> None:
    authorize_fixture(isolated_deployer)
    ledger = isolated_deployer / "ledger"
    ledger.mkdir()
    claim = ledger / f"attempt-{CLAIM_HASH}.json"
    claim.write_bytes(b"")
    result = run_fixture(isolated_deployer)
    assert result["success"] is False and result["calls"] == []
    assert claim.read_bytes() == b""


def test_overlapping_invocations_cannot_start_second_transport(isolated_deployer: Path) -> None:
    script = isolated_deployer / DEPLOYER.relative_to(ROOT)
    script.write_text(
        script.read_text().replace("$maximumWallClockSeconds = 300", "$maximumWallClockSeconds = 8")
    )
    authorize_fixture(isolated_deployer)
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(run_fixture, isolated_deployer, "hang")
        deadline = time.monotonic() + 12
        calls = isolated_deployer / "calls.jsonl"
        while not calls.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert calls.exists(), "First fake process did not start"
        second = run_fixture(isolated_deployer)
        assert second["success"] is False and "concurrent" in second["error"]
        assert len(second["calls"]) == 1
        assert first.result()["success"] is False
    assert len(calls.read_text().splitlines()) == 1


def test_new_record_id_does_not_reset_package_attempt(isolated_deployer: Path) -> None:
    authorize_fixture(isolated_deployer)
    assert run_fixture(isolated_deployer, "fail-preflight")["success"] is False
    authorize_fixture(isolated_deployer, authorization_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    result = run_fixture(isolated_deployer)
    assert result["success"] is False and len(result["calls"]) == 1


def test_missing_identity_is_not_discovered_by_contacting_remote(isolated_deployer: Path) -> None:
    authorize_fixture(isolated_deployer, remote_identity=None)
    result = run_fixture(isolated_deployer)
    assert result["success"] is False and result["calls"] == []


def test_legitimate_absent_new_assets_remain_explicit(isolated_deployer: Path) -> None:
    authorize_fixture(isolated_deployer)
    path = isolated_deployer / AUTHORIZATION
    record = json.loads(path.read_text())
    record["preimages"][3].update(presence="absent", sha256=None, mode=None)
    path.write_text(json.dumps(record))
    result = run_fixture(isolated_deployer)
    assert result["success"] is True, result["error"]
    destination = "/home/buet/cds_work/.cadence_mcp/lib/run-wp14-role-discovery.sh"
    assert (
        f"test ! -e '{destination}' && test ! -L '{destination}'" in result["calls"][0]["command"]
    )


def test_whatif_never_consumes_authority(isolated_deployer: Path) -> None:
    authorize_fixture(isolated_deployer)
    assert run_fixture(isolated_deployer, "whatif")["success"] is True
    assert not (isolated_deployer / "ledger").exists()


def test_claim_remains_after_missing_fake_executable(isolated_deployer: Path) -> None:
    script = isolated_deployer / DEPLOYER.relative_to(ROOT)
    script.write_text(
        script.read_text().replace(
            sys.executable.replace("'", "''"), str(isolated_deployer / "does-not-exist.exe")
        ),
        encoding="utf-8",
    )
    authorize_fixture(isolated_deployer)
    result = run_fixture(isolated_deployer)
    assert result["success"] is False and result["calls"] == []
    assert (isolated_deployer / "ledger" / f"attempt-{CLAIM_HASH}.json").exists()


@pytest.mark.parametrize("contents", [b"", b"historical consumed claim"])
def test_predecessor_claim_blocks_migrated_deployer(
    isolated_deployer: Path, contents: bytes
) -> None:
    authorize_fixture(isolated_deployer)
    ledger = isolated_deployer / "ledger"
    ledger.mkdir()
    claim = ledger / f"attempt-{CLAIM_HASH}.json"
    claim.write_bytes(contents)
    result = run_fixture(isolated_deployer)
    assert result["success"] is False and result["calls"] == []
    assert claim.read_bytes() == contents
    assert not (ledger / f"attempt-{PACKAGE_HASH}.json").exists()


def test_old_package_authority_rejected_after_migration(isolated_deployer: Path) -> None:
    authorize_fixture(isolated_deployer, package_normalized_lf_sha256=CLAIM_HASH)
    result = run_fixture(isolated_deployer)
    assert result["success"] is False and result["calls"] == []
    assert not (isolated_deployer / "ledger").exists()


def test_invalid_json_does_not_echo_raw_content(isolated_deployer: Path) -> None:
    (isolated_deployer / AUTHORIZATION).write_text('{"DO_NOT_DISCLOSE_TEST_PAYLOAD": ')
    result = run_fixture(isolated_deployer)
    assert result["success"] is False and result["calls"] == []
    assert "DO_NOT_DISCLOSE" not in result["error"]


def test_authorization_size_bound(isolated_deployer: Path) -> None:
    (isolated_deployer / AUTHORIZATION).write_text(" " * 32769)
    result = run_fixture(isolated_deployer)
    assert result["success"] is False and result["calls"] == []
    assert "size bound" in result["error"]


def test_valid_but_wrong_preimage_is_rejected_by_fake_model(isolated_deployer: Path) -> None:
    authorize_fixture(isolated_deployer)
    path = isolated_deployer / AUTHORIZATION
    record = json.loads(path.read_text())
    record["preimages"][0]["sha256"] = "a" * 64
    path.write_text(json.dumps(record))
    result = run_fixture(isolated_deployer)
    assert result["success"] is False and len(result["calls"]) == 1


def test_only_fixed_native_executables_and_no_test_bypass_in_production() -> None:
    text = DEPLOYER.read_text()
    assert "System32\\OpenSSH\\$Kind.exe" in text
    assert "Get-Command" not in text
    assert "UseShellExecute = $false" in text
    assert "CreateNoWindow = $true" in text
    assert "ReadAsync" in text and "Kill($true)" in text
    assert "FileMode]::CreateNew" in text and "Flush($true)" in text
    assert "FileShare]::None" in text
    assert "LocalApplicationData" in text and "Get-ExecutorBinding" in text
    assert "WP14_FAKE" not in text and "fake.py" not in text


def test_shared_ledger_blocks_second_checkout(isolated_deployer: Path) -> None:
    second = isolated_deployer.parent / "second checkout" / "isolated fixture"
    shutil.copytree(isolated_deployer, second)
    shared = str(isolated_deployer.parent / "shared ledger").replace("'", "''")
    for fixture in (isolated_deployer, second):
        script = fixture / DEPLOYER.relative_to(ROOT)
        script.write_text(
            script.read_text(encoding="utf-8").replace(
                "(Join-Path $projectRoot 'ledger')", f"'{shared}'"
            ),
            encoding="utf-8",
        )
        authorize_fixture(fixture)
    first_result = run_fixture(isolated_deployer, "fail-preflight")
    assert first_result["success"] is False and len(first_result["calls"]) == 1
    second_result = run_fixture(second)
    assert second_result["success"] is False and second_result["calls"] == []
    assert "already consumed" in second_result["error"]


def test_deadline_is_shared_across_commands(isolated_deployer: Path) -> None:
    script = isolated_deployer / DEPLOYER.relative_to(ROOT)
    script.write_text(
        script.read_text().replace(
            "$maximumWallClockSeconds = 300", "$maximumWallClockSeconds = 4"
        ),
        encoding="utf-8",
    )
    authorize_fixture(isolated_deployer)
    result = run_fixture(isolated_deployer, "slow-each")
    assert result["success"] is False
    assert "wall-clock limit" in result["error"]
    assert 1 < len(result["calls"]) < 25


@pytest.mark.parametrize(
    "field",
    [
        "record_kind",
        "status",
        "package_normalized_lf_sha256",
        "deployer_normalized_lf_sha256",
        "executor_binding",
    ],
)
def test_arrays_cannot_bypass_scalar_identity_bindings(isolated_deployer: Path, field: str) -> None:
    authorize_fixture(isolated_deployer, **{field: []})
    result = run_fixture(isolated_deployer)
    assert result["success"] is False and result["calls"] == []
    assert not (isolated_deployer / "ledger").exists()


@pytest.mark.parametrize("field", ["hostname", "user", "root", "presence"])
def test_nested_identity_fields_require_scalars(isolated_deployer: Path, field: str) -> None:
    authorize_fixture(isolated_deployer)
    path = isolated_deployer / AUTHORIZATION
    record = json.loads(path.read_text())
    if field == "presence":
        record["preimages"][0][field] = ["file"]
    else:
        record["remote_identity"][field] = []
    path.write_text(json.dumps(record))
    result = run_fixture(isolated_deployer)
    assert result["success"] is False and result["calls"] == []
