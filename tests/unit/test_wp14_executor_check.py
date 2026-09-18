"""Only temporary checker copies with synthetic identities are ever invoked."""

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts/verify-wp14-executor.ps1"
DEPLOYER = ROOT / "scripts/deploy-wp14-recovery.ps1"
PWSH = shutil.which("pwsh")
SID = "S-1-5-21-100-200-300-1001"
MACHINE = "12345678-1234-5678-9abc-123456789abc"


def fixture_checker(tmp_path: Path, body: str | None = None) -> Path:
    text = CHECKER.read_text(encoding="utf-8")
    start = text.index("function Read-FixedIdentity {")
    end = text.index("function Test-IdentityShape", start)
    replacement = body or f"return @{{ Sid = '{SID}'; Machine = '{MACHINE}' }}"
    text = text[:start] + "function Read-FixedIdentity {\n" + replacement + "\n}\n\n" + text[end:]
    # Prove the real identity primitives are removed BEFORE any process starts.
    assert "WindowsIdentity" not in text and "Get-ItemProperty" not in text
    assert "HKLM:" not in text
    target = tmp_path / CHECKER.name
    target.write_text(text, encoding="utf-8")
    shutil.copyfile(DEPLOYER, tmp_path / DEPLOYER.name)
    return target


def run_checker(checker: Path, *args: str) -> subprocess.CompletedProcess[str]:
    assert checker.resolve() != CHECKER.resolve()
    assert "WindowsIdentity" not in checker.read_text(encoding="utf-8")
    if not PWSH:
        pytest.fail("PowerShell is required for isolated checker validation")
    return subprocess.run(
        [PWSH, "-NoLogo", "-NoProfile", "-NonInteractive", "-File", str(checker), *args],
        cwd=checker.parent,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
        check=False,
    )


def assert_result(result: subprocess.CompletedProcess[str], code: str) -> None:
    success = code == "LOCAL_RULE_READY"
    assert result.returncode == (0 if success else 1)
    assert result.stderr == ""
    assert len(result.stdout.encode("utf-8")) <= 128
    assert json.loads(result.stdout) == {"success": success, "code": code}
    for secret in (SID, MACHINE, hashlib.sha256(f"{SID}|{MACHINE}".encode()).hexdigest()):
        assert secret not in result.stdout + result.stderr


def test_synthetic_success_preserves_every_file(tmp_path: Path) -> None:
    checker = fixture_checker(tmp_path)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    assert_result(run_checker(checker), "LOCAL_RULE_READY")
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir()}


@pytest.mark.parametrize("arg", ["-WhatIf", "-executor_binding", "x", "-Help"])
def test_arguments_rejected_before_identity(tmp_path: Path, arg: str) -> None:
    checker = fixture_checker(tmp_path, "throw 'SENSITIVE_SENTINEL'")
    assert_result(run_checker(checker, arg), "ARGUMENTS_NOT_ALLOWED")


@pytest.mark.parametrize("kind", ["missing", "tampered", "oversized"])
def test_deployer_integrity_before_identity(tmp_path: Path, kind: str) -> None:
    checker = fixture_checker(tmp_path, "throw 'SENSITIVE_SENTINEL'")
    deployer = tmp_path / DEPLOYER.name
    if kind == "missing":
        deployer.unlink()
    else:
        deployer.write_text("x" * (131073 if kind == "oversized" else 1), encoding="utf-8")
    assert_result(run_checker(checker), "DEPLOYER_INTEGRITY_FAILED")


@pytest.mark.parametrize(
    "body",
    [
        "return $null",
        "return @{ Sid = @('secret'); Machine = 'secret' }",
        f"return @{{ Sid = 'fixture-user'; Machine = '{MACHINE}' }}",
        f"return @{{ Sid = '{SID}'; Machine = '' }}",
        f"return @{{ Sid = '{SID}'; Machine = '00000000-0000-0000-0000-000000000000' }}",
        f"return @{{ Sid = '{SID} '; Machine = '{MACHINE}' }}",
    ],
)
def test_invalid_identity(tmp_path: Path, body: str) -> None:
    assert_result(run_checker(fixture_checker(tmp_path, body)), "IDENTITY_INVALID")


def test_identity_failure_is_suppressed(tmp_path: Path) -> None:
    result = run_checker(fixture_checker(tmp_path, "throw 'SENSITIVE_SENTINEL'"))
    assert_result(result, "IDENTITY_UNAVAILABLE")
    assert "SENSITIVE_SENTINEL" not in result.stdout + result.stderr


def test_identity_changes_between_reads(tmp_path: Path) -> None:
    body = (
        "$script:counter = 1 + (Get-Variable counter -Scope Script -ValueOnly "
        "-ErrorAction SilentlyContinue)\n"
        f"return @{{ Sid = ('{SID}' + $script:counter); Machine = '{MACHINE}' }}"
    )
    assert_result(run_checker(fixture_checker(tmp_path, body)), "IDENTITY_CHANGED")


def test_non_windows_rejected_before_identity(tmp_path: Path) -> None:
    checker = fixture_checker(tmp_path, "throw 'SENSITIVE_SENTINEL'")
    text = checker.read_text(encoding="utf-8").replace("-not $IsWindows", "$true")
    checker.write_text(text, encoding="utf-8")
    assert_result(run_checker(checker), "UNSUPPORTED_RUNTIME")


def test_digest_matches_deployer_rule_with_synthetic_inputs(tmp_path: Path) -> None:
    checker = fixture_checker(tmp_path)
    expected = hashlib.sha256(f"{SID}|{MACHINE}".encode()).hexdigest()
    text = checker.read_text(encoding="utf-8")
    # Temporary assertion only; the production output never reveals the digest.
    text = text.replace(
        "$binding = Get-LocalDigest $first",
        "$binding = Get-LocalDigest $first\n"
        f"    if ($binding -cne '{expected}') {{ throw 'Rule mismatch' }}",
    )
    checker.write_text(text, encoding="utf-8")
    assert_result(run_checker(checker), "LOCAL_RULE_READY")


def test_no_production_transport_or_execution_surface() -> None:
    text = CHECKER.read_text(encoding="utf-8")
    for forbidden in (
        "Invoke-Expression", "ScriptBlock", "Start-Process", "FileMode",
        "WriteAllText", "Out-File", "Set-Content", "CreateDirectory", "Import-Module",
        "ssh.exe", "scp.exe", "ShouldProcess", "Claim-OneAttempt",
    ):
        assert forbidden not in text
    deployer = DEPLOYER.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    assert hashlib.sha256(deployer.encode()).hexdigest() == (
        "e4ed2610aa0cb6a5b930b0ce6a52f1a6d2273c390195f0b58ff3e17c0d976374"
    )
