"""Installed migration/helper CLI and disposable preservation; no VM contact."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


def snapshots(root: Path) -> dict[str, str]:
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file()
    }


def verify(workspace: Path, examples: Path) -> dict[str, object]:
    import cadence_mcp_bridge
    from cadence_mcp_bridge import _domain_migration as migration
    from cadence_mcp_bridge import _runner_bootstrap as installer
    from cadence_mcp_bridge import _shared_reservations as accounting
    from cadence_mcp_bridge.domain_provisioning import contents

    if not Path(cadence_mcp_bridge.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()):
        raise ValueError("installed wheel required")
    workspace.mkdir(exist_ok=False)
    exported = workspace / "exported"
    report = subprocess.run(
        [
            sys.executable,
            "-I",
            "-m",
            "cadence_mcp_bridge",
            "domain",
            "export-helper-bundle",
            "--output",
            str(exported),
        ],
        capture_output=True,
        check=True,
    )
    assets, manifest, digest = contents()
    assert json.loads(report.stdout)["manifest_sha256"] == digest
    assert (exported / "manifest.json").read_bytes() == manifest
    assert all((exported / name).read_bytes() == data for name, data in assets.items())
    root = workspace / "state"
    root.mkdir(mode=0o700)
    (root / "sim-mcp-v2-jobs").mkdir(mode=0o700)
    (root / accounting.JOBS).mkdir(mode=0o700)
    (root / "run.lock").write_bytes(b"")
    (root / "run.lock").chmod(0o600)
    baseline = {"campaign_id": "AUTO-PHASE-01", "count": 82, "result_reserved_bytes": 9798942720}
    accounting.write_new(str(root / accounting.LEDGER), baseline)
    # Explicitly substitute native profile/locking for this Windows disposable fixture.
    # This is NOT physical VM, authority or fresh-domain qualification.
    original_profile, original_lock = migration.profile, installer._operator_lock
    migration.profile = lambda profile: str(root.resolve())
    installer._operator_lock = lambda target: None
    try:
        profile = json.loads((examples / "environment.json").read_bytes())
        before = snapshots(root)
        planned = migration.plan(profile, digest)
        assert snapshots(root) == before
        request = {
            "plan": planned["plan"],
            "expected_plan_sha256": planned["plan_sha256"],
            "operator_authority": "SYNTHETIC FIXTURE; NOT USER CONSENT",
        }
        result = migration.apply(request, digest)
        assert result["anchor_created"] and not result["ledger_modified"]
        after = snapshots(root)
        assert migration.apply(request, digest)["anchor_created"] is False
        assert snapshots(root) == after
        assert all(after[k] == value for k, value in before.items())
    finally:
        migration.profile, installer._operator_lock = original_profile, original_lock
    (workspace / "preservation.json").write_text(json.dumps(snapshots(root), sort_keys=True))
    return {
        "status": "PASS",
        "scope": "INSTALLED_EXISTING_MIGRATION_SYNTHETIC",
        "exported_helper_sha256": digest,
        "remote_contact": False,
        "ledger_modified": False,
        "execution_authorized": False,
        "native_jobs": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--examples", type=Path)
    parser.add_argument("--verify-preserved", action="store_true")
    args = parser.parse_args()
    if args.verify_preserved:
        expected = json.loads((args.workspace / "preservation.json").read_bytes())
        assert snapshots(args.workspace / "state") == expected
        report = {
            "status": "PASS",
            "scope": "SYNTHETIC_MIGRATION_PRESERVATION",
            "files": len(expected),
        }
    else:
        if args.examples is None:
            parser.error("--examples required")
        report = verify(args.workspace.resolve(), args.examples.resolve())
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
