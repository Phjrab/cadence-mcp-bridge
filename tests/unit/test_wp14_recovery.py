"""Recovery tests use only temporary fixtures and the existing fake transport."""

import hashlib
import json
import shutil
from pathlib import Path

import pytest
import test_wp14_narrow_deployer as base

RECOVERY = base.ROOT / "scripts/deploy-wp14-recovery.ps1"
PLAN = Path("docs/WP14_POST_CLOSE_RECOVERY_PLAN_V1.md")
PRIOR_HASH = "095bbda61bf7f0a8d11fe1428aec0ce2139183586b8edcaf98346ed646bc08c5"


@pytest.fixture
def recovery(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    original = base.DEPLOYER
    monkeypatch.setattr(base, "DEPLOYER", RECOVERY)
    fixture = base.isolated_deployer.__wrapped__(tmp_path)
    fake = fixture / "fake.py"
    fake.write_text(
        fake.read_text(encoding="utf-8").replace(
            "*AUTHORIZATION_V2.json", "*RECOVERY_AUTHORIZATION_V1.json"
        ),
        encoding="utf-8",
    )
    script = fixture / RECOVERY.relative_to(base.ROOT)
    # Only the temporary copy substitutes a synthetic preserved activation digest.
    synthetic_hash = hashlib.sha256(b"{}").hexdigest()
    text = script.read_text(encoding="utf-8").replace(PRIOR_HASH, synthetic_hash)
    text = text.replace(
        "0a469a94880383ffeada740c3b19e261ba5b50382ddf360a91243c7054782ba7",
        hashlib.sha256(b"synthetic evidence only").hexdigest(),
    )
    target = fixture / original.relative_to(base.ROOT)
    target.write_text(text, encoding="utf-8")
    monkeypatch.setattr(base, "DEPLOYER", original)
    shutil.copyfile(base.ROOT / PLAN, fixture / PLAN)
    prior_auth = fixture / base.AUTHORIZATION
    prior_auth.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        base, "AUTHORIZATION", Path("docs/approvals/WP14_NARROW_RECOVERY_AUTHORIZATION_V1.json")
    )
    ledger = fixture / "ledger"
    ledger.mkdir()
    prior = {
        "state": "consumed_before_transport",
        "authorization_id": "4f06b6ca-3377-48ae-a643-aefc3fb90dbc",
        "authorization_sha256": synthetic_hash,
        "package_sha256": base.PACKAGE_HASH,
        "deployer_sha256": "3251100bafde66c0df4179d36462de8029c6856b59111629dba627c1b668fddc",
        "consumed_at": "2026-09-17T08:20:37.8800486+00:00",
    }
    (ledger / f"attempt-{base.CLAIM_HASH}.json").write_text(json.dumps(prior), encoding="utf-8")
    base.authorize_fixture(
        fixture,
        record_kind="explicit_single_recovery_deployment_authorization",
        recovery_plan_sha256=base.normalized_hash(base.ROOT / PLAN),
    )
    return fixture


def test_success_preserves_predecessor_and_consumes_once(recovery: Path) -> None:
    prior = recovery / "ledger" / f"attempt-{base.CLAIM_HASH}.json"
    before = prior.read_bytes()
    result = base.run_fixture(recovery)
    assert result["success"], result
    assert len(result["calls"]) == 25
    assert prior.read_bytes() == before
    claim = recovery / "ledger/recovery-v1.json"
    assert claim.is_file()
    after = claim.read_bytes()
    replay = base.run_fixture(recovery)
    assert not replay["success"] and replay["calls"] == result["calls"]
    assert claim.read_bytes() == after


@pytest.mark.parametrize("kind", ["missing", "empty", "wrong", "array", "extra", "duplicate"])
def test_predecessor_rejected_without_transport(recovery: Path, kind: str) -> None:
    prior = recovery / "ledger" / f"attempt-{base.CLAIM_HASH}.json"
    if kind == "missing":
        prior.unlink()
    elif kind == "empty":
        prior.write_text("", encoding="utf-8")
    elif kind == "duplicate":
        prior.write_text('{"state":"x","state":"y"}', encoding="utf-8")
    else:
        obj = json.loads(prior.read_text(encoding="utf-8"))
        if kind == "extra":
            obj["extra"] = True
        else:
            obj["state"] = ["consumed_before_transport"] if kind == "array" else "wrong"
        prior.write_text(json.dumps(obj), encoding="utf-8")
    result = base.run_fixture(recovery)
    assert not result["success"] and not result["calls"]
    assert not (recovery / "ledger/recovery-v1.json").exists()


@pytest.mark.parametrize("target", ["plan", "prior_auth", "recovery_claim"])
def test_preservation_and_binding_fail_closed(recovery: Path, target: str) -> None:
    paths = {
        "plan": recovery / PLAN,
        "prior_auth": recovery
        / "docs/approvals/WP14_NARROW_REMOTE_DEPLOYMENT_AUTHORIZATION_V2.json",
        "recovery_claim": recovery / "ledger/recovery-v1.json",
    }
    paths[target].write_text("tampered", encoding="utf-8")
    result = base.run_fixture(recovery)
    assert not result["success"] and not result["calls"]


def test_failed_transport_consumes_recovery(recovery: Path) -> None:
    result = base.run_fixture(recovery, "fail-preflight")
    assert not result["success"] and len(result["calls"]) == 1
    assert (recovery / "ledger/recovery-v1.json").exists()
    replay = base.run_fixture(recovery)
    assert not replay["success"] and replay["calls"] == result["calls"]


def test_fixed_production_boundaries() -> None:
    original = base.DEPLOYER.read_text(encoding="utf-8")
    new = RECOVERY.read_text(encoding="utf-8")
    assert (
        original[original.index("function Invoke-BoundedTransport") :]
        == new[new.index("function Invoke-BoundedTransport") :]
    )
    assert base.normalized_hash(base.DEPLOYER) == (
        "3251100bafde66c0df4179d36462de8029c6856b59111629dba627c1b668fddc"
    )
    assert "System32\\OpenSSH\\$Kind.exe" in new
    assert "'operation.lock'" in new
    assert "'recovery-v1.json'" in new


@pytest.mark.parametrize("field", ["recovery_plan_sha256", "evidence_sha256", "record_kind"])
def test_recovery_authority_binding(recovery: Path, field: str) -> None:
    auth = recovery / base.AUTHORIZATION
    obj = json.loads(auth.read_text(encoding="utf-8"))
    obj[field] = "wrong"
    auth.write_text(json.dumps(obj), encoding="utf-8")
    result = base.run_fixture(recovery)
    assert not result["success"] and not result["calls"]
    assert not (recovery / "ledger/recovery-v1.json").exists()
