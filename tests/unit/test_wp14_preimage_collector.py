from __future__ import annotations

import hashlib
import json
import os
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
COLLECTOR = ROOT / "scripts/collect-wp14-remote-preimages.py"
PACKAGE = (
    ROOT
    / "docs/approvals/WP14_REMOTE_IDENTITY_PREIMAGE_EVIDENCE_COLLECTION_APPROVAL_PACKAGE_V2.json"
)
AUTHORIZATION = Path(
    "docs/approvals/WP14_REMOTE_IDENTITY_PREIMAGE_EVIDENCE_COLLECTION_AUTHORIZATION_V1.json"
)
PACKAGE_HASH = "7b8d4d623a95e67a6d39e0391bcf5b9869c58dedbf02b0dd638c070853048223"
CLAIM_HASH = "1906357b1ef5ba98a3d28241896fc59d0a4ff8053b64eac9f5d45f9a9bde0fcb"
MAIN_COMMIT = "e60ab270a5e002256f8c5bbf6b81e54f65c10a31"


def normalized_hash(path: Path) -> str:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(text.encode()).hexdigest()


def test_production_collector_is_fixed_and_inactive() -> None:
    package = json.loads(PACKAGE.read_text(encoding="utf-8"))
    collector = COLLECTOR.read_text(encoding="utf-8")
    assert normalized_hash(PACKAGE) == PACKAGE_HASH
    assert all(value is False for value in package["authority"].values())
    assert len(package["asset_preimage_allowlist"]) == 11
    assert "System32/OpenSSH/ssh.exe" in collector
    assert "shell=False" in collector and "MAX_WALL_SECONDS = 60" in collector
    assert "MAX_OUTPUT_BYTES = 32768" in collector
    assert "scp" not in collector.lower() and "invoke-expression" not in collector.lower()
    assert "WP14_PREIMAGE_SCENARIO" not in collector and "fake_process" not in collector
    for forbidden in ("virtuoso", "spectre", "ocean", "dbOpenCellView"):
        assert forbidden not in collector
    assert not (ROOT / AUTHORIZATION).exists()
    assert not (
        ROOT / "docs/approvals/WP14_NARROW_REMOTE_DEPLOYMENT_AUTHORIZATION_V2.json"
    ).exists()
    assert (
        json.loads((ROOT / "remote/config/runner-lineage.json").read_text(encoding="utf-8"))[
            "deployment_enabled"
        ]
        is False
    )


@pytest.fixture
def isolated_collector(tmp_path: Path) -> Path:
    fixture = tmp_path / "isolated collector"
    fixture.mkdir()
    relative_paths = [
        COLLECTOR.relative_to(ROOT),
        PACKAGE.relative_to(ROOT),
        Path(
            "docs/approvals/WP14_BOUNDED_READ_ONLY_DISCOVERY_DEPLOYMENT_EXECUTION_APPROVAL_PACKAGE_V2.json"
        ),
        Path("scripts/deploy-wp14-narrow.ps1"),
        Path("remote/config/runner-lineage.json"),
    ]
    for relative in relative_paths:
        destination = fixture / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, destination)
    shutil.copyfile(ROOT / "tests/fixtures/wp14_preimage_fake_process.py", fixture / "fake.py")
    script = fixture / COLLECTOR.relative_to(ROOT)
    text = script.read_text(encoding="utf-8")
    prefix = "SSH_PREFIX = [str(_windows_ssh_path())]"
    assert text.count(prefix) == 1
    text = text.replace(prefix, f"SSH_PREFIX = [{sys.executable!r}, {str(fixture / 'fake.py')!r}]")
    start = text.index("def _state_root() -> Path:")
    end = text.index("\n\ndef _executor_binding", start)
    text = (
        text[:start]
        + "def _state_root() -> Path:\n    return PROJECT_ROOT / 'ledger'\n"
        + text[end:]
    )
    start = text.index("def _executor_binding() -> str:")
    end = text.index("\n\ndef _assert_no_reparse_ancestors", start)
    binding = hashlib.sha256(b"fixture-user|fixture-machine").hexdigest()
    text = text[:start] + f"def _executor_binding() -> str:\n    return {binding!r}\n" + text[end:]
    script.write_text(text, encoding="utf-8")
    return fixture


def authorize_fixture(fixture: Path, **overrides: object) -> None:
    record = {
        "schema_version": 1,
        "record_kind": "explicit_remote_identity_preimage_collection_authorization",
        "status": "APPROVED",
        "package_normalized_lf_sha256": PACKAGE_HASH,
        "collector_normalized_lf_sha256": normalized_hash(fixture / COLLECTOR.relative_to(ROOT)),
        "remote_identity_preimage_collection_authorized": True,
        "max_uses": 1,
        "authorization_id": "11111111-2222-3333-4444-555555555555",
        "executor_binding": hashlib.sha256(b"fixture-user|fixture-machine").hexdigest(),
        "not_before": (datetime.now(UTC) - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expires_at": (datetime.now(UTC) + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repository_main_commit": MAIN_COMMIT,
    }
    record.update(overrides)
    path = fixture / AUTHORIZATION
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record), encoding="utf-8")


def run_fixture(
    fixture: Path, scenario: str = "success", argument: str | None = None
) -> dict[str, Any]:
    env = os.environ.copy()
    env["WP14_PREIMAGE_SCENARIO"] = scenario
    command = [sys.executable, str(fixture / COLLECTOR.relative_to(ROOT))]
    if argument is not None:
        command.append(argument)
    completed = subprocess.run(
        command,
        cwd=fixture,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        timeout=20,
        check=False,
    )
    calls_path = fixture / "calls.jsonl"
    calls = (
        []
        if not calls_path.exists()
        else [json.loads(line) for line in calls_path.read_text(encoding="utf-8").splitlines()]
    )
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "calls": calls,
    }


def test_missing_authorization_and_arguments_stop_before_transport(
    isolated_collector: Path,
) -> None:
    result = run_fixture(isolated_collector)
    assert result["returncode"] == 1 and "not authorized" in result["stderr"]
    assert result["calls"] == []
    result = run_fixture(isolated_collector, argument="unexpected")
    assert result["returncode"] == 1 and "accepts no arguments" in result["stderr"]
    assert result["calls"] == []


def test_success_is_one_call_and_closed_evidence(isolated_collector: Path) -> None:
    authorize_fixture(isolated_collector)
    result = run_fixture(isolated_collector)
    assert result["returncode"] == 0, result["stderr"]
    assert len(result["calls"]) == 1
    evidence = json.loads(result["stdout"])
    assert set(evidence) == {
        "schema_version",
        "record_kind",
        "collector_normalized_lf_sha256",
        "repository_main_commit",
        "observed_at",
        "remote_identity",
        "preimages",
        "blockers",
    }
    assert evidence["repository_main_commit"] == MAIN_COMMIT
    assert evidence["remote_identity"]["verified"] is True
    assert len(evidence["preimages"]) == 11 and evidence["blockers"] == []
    assert all(
        item["owner"] == "buet" and item["hard_link_count"] == 1 for item in evidence["preimages"]
    )
    command = result["calls"][0]["command"]
    assert "sha256sum" in command and "readlink -f" in command and "stat -c" in command


def test_optional_absence_is_explicit(isolated_collector: Path) -> None:
    authorize_fixture(isolated_collector)
    evidence = json.loads(run_fixture(isolated_collector, "absent-optional")["stdout"])
    item = evidence["preimages"][3]
    assert item["presence"] == "absent" and item["sha256"] is None and item["owner"] is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", 2),
        ("record_kind", "wrong"),
        ("status", "UNSET"),
        ("package_normalized_lf_sha256", "0" * 64),
        ("collector_normalized_lf_sha256", "0" * 64),
        ("remote_identity_preimage_collection_authorized", False),
        ("max_uses", 2),
        ("repository_main_commit", "0" * 40),
        ("executor_binding", "wrong"),
        ("authorization_id", "../escape"),
    ],
)
def test_invalid_authorization_never_reaches_transport(
    isolated_collector: Path, field: str, value: object
) -> None:
    authorize_fixture(isolated_collector, **{field: value})
    result = run_fixture(isolated_collector)
    assert result["returncode"] == 1 and result["calls"] == []
    assert not (isolated_collector / "ledger").exists()


@pytest.mark.parametrize(
    "scenario",
    [
        "wrong-host",
        "wrong-user",
        "wrong-root",
        "root-symlink",
        "missing-required",
        "bad-hash",
        "wrong-mode",
        "wrong-owner",
        "wrong-type",
        "wrong-links",
        "asset-symlink",
        "outside-root",
        "duplicate-index",
        "missing-line",
        "extra-line",
        "wrong-end",
    ],
)
def test_remote_identity_or_preimage_drift_fails_closed(
    isolated_collector: Path, scenario: str
) -> None:
    authorize_fixture(isolated_collector)
    result = run_fixture(isolated_collector, scenario)
    assert result["returncode"] == 1 and len(result["calls"]) == 1
    assert result["stdout"] == ""


@pytest.mark.parametrize("scenario", ["fail", "stderr", "invalid-utf8"])
def test_transport_failure_suppresses_output(isolated_collector: Path, scenario: str) -> None:
    authorize_fixture(isolated_collector)
    result = run_fixture(isolated_collector, scenario)
    assert result["returncode"] == 1 and len(result["calls"]) == 1
    assert "DO_NOT_DISCLOSE" not in result["stderr"]


@pytest.mark.parametrize("scenario", ["hang", "flood-stdout", "flood-stderr", "flood-both"])
def test_live_transport_is_bounded(isolated_collector: Path, scenario: str) -> None:
    script = isolated_collector / COLLECTOR.relative_to(ROOT)
    script.write_text(
        script.read_text(encoding="utf-8").replace("MAX_WALL_SECONDS = 60", "MAX_WALL_SECONDS = 3"),
        encoding="utf-8",
    )
    authorize_fixture(isolated_collector)
    started = time.monotonic()
    result = run_fixture(isolated_collector, scenario)
    assert time.monotonic() - started < 12
    assert result["returncode"] == 1 and len(result["calls"]) == 1
    assert "X" * 100 not in result["stderr"] and "Y" * 100 not in result["stderr"]


def test_failed_attempt_is_consumed_without_replay(isolated_collector: Path) -> None:
    authorize_fixture(isolated_collector)
    first = run_fixture(isolated_collector, "fail")
    assert first["returncode"] == 1 and len(first["calls"]) == 1
    claim = isolated_collector / "ledger" / f"attempt-{CLAIM_HASH}.json"
    assert json.loads(claim.read_text(encoding="utf-8"))["state"] == ("consumed_before_transport")
    second = run_fixture(isolated_collector)
    assert second["returncode"] == 1 and "already consumed" in second["stderr"]
    assert len(second["calls"]) == 1


def test_duplicate_and_oversized_authorization_are_rejected(isolated_collector: Path) -> None:
    authorize_fixture(isolated_collector)
    path = isolated_collector / AUTHORIZATION
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            '{"schema_version": 1', '{"schema_version": 1, "schema_version": 1'
        ),
        encoding="utf-8",
    )
    result = run_fixture(isolated_collector)
    assert result["returncode"] == 1 and result["calls"] == []


def test_oversized_authorization_is_rejected(isolated_collector: Path) -> None:
    authorize_fixture(isolated_collector)
    path = isolated_collector / AUTHORIZATION
    path.write_text(" " * 16385, encoding="utf-8")
    result = run_fixture(isolated_collector)
    assert result["returncode"] == 1 and result["calls"] == []


@pytest.mark.parametrize("contents", [b"", b"historical consumed claim"])
def test_predecessor_claim_blocks_new_package_without_modification(
    isolated_collector: Path, contents: bytes
) -> None:
    authorize_fixture(isolated_collector)
    ledger = isolated_collector / "ledger"
    ledger.mkdir()
    claim = ledger / f"attempt-{CLAIM_HASH}.json"
    claim.write_bytes(contents)
    result = run_fixture(isolated_collector)
    assert result["returncode"] == 1 and result["calls"] == []
    assert claim.read_bytes() == contents
    assert not (ledger / f"attempt-{PACKAGE_HASH}.json").exists()


def test_old_package_authority_is_not_reusable(isolated_collector: Path) -> None:
    authorize_fixture(isolated_collector, package_normalized_lf_sha256=CLAIM_HASH)
    result = run_fixture(isolated_collector)
    assert result["returncode"] == 1 and result["calls"] == []
    assert not (isolated_collector / "ledger").exists()


@pytest.mark.parametrize(
    "relative",
    [
        PACKAGE.relative_to(ROOT),
        Path("scripts/deploy-wp14-narrow.ps1"),
        Path(
            "docs/approvals/WP14_BOUNDED_READ_ONLY_DISCOVERY_DEPLOYMENT_EXECUTION_APPROVAL_PACKAGE_V2.json"
        ),
    ],
)
def test_migrated_input_tampering_stops_before_transport(
    isolated_collector: Path, relative: Path
) -> None:
    path = isolated_collector / relative
    path.write_bytes(path.read_bytes() + b"\n")
    authorize_fixture(isolated_collector)
    result = run_fixture(isolated_collector)
    assert result["returncode"] == 1 and result["calls"] == []
    assert not (isolated_collector / "ledger").exists()


def test_concurrent_collections_share_one_lineage_claim(isolated_collector: Path) -> None:
    authorize_fixture(isolated_collector)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run_fixture, [isolated_collector, isolated_collector]))
    assert sorted(result["returncode"] for result in results) == [0, 1]
    calls = (isolated_collector / "calls.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(calls) == 1


def test_publication_sensitive_content_is_suppressed(isolated_collector: Path) -> None:
    authorize_fixture(isolated_collector)
    result = run_fixture(isolated_collector, "protected-content")
    assert result["returncode"] == 1 and len(result["calls"]) == 1
    assert result["stdout"] == ""
    assert "SYNTHETIC_PROTECTED_CONTENT" not in result["stderr"]
