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
    from cadence_mcp_bridge import _fresh_domain as setup

    home = root / "synthetic-fresh-home"
    home.mkdir(mode=0o700)
    fresh_workspace = home / "workspace"
    fresh_workspace.mkdir(mode=0o700)
    fresh_root = fresh_workspace / ".cadence_mcp"
    index = home / ".cadence_mcp-domain"
    original_home, original_setup_profile = setup.home, setup.profile
    setup.home = lambda: str(home)
    setup.profile = lambda profile: (str(fresh_root), str(index))
    original_lock = installer._operator_lock
    installer._operator_lock = lambda target: None
    try:
        _, _, setup_digest = contents(True)
        profile["limits"]["spectre_attempts"] = 3
        profile["limits"]["result_reserved_bytes"] = 1048576
        planned = setup.plan_fresh(profile, setup_digest)
        request = {
            "plan": planned["plan"],
            "expected_plan_sha256": planned["plan_sha256"],
            "operator_authority": "SYNTHETIC ONLY, NOT REAL USER CONSENT",
        }
        assert setup.apply_fresh(request, setup_digest)["ledger_initialized"] is True
        anchor = accounting.read(str(fresh_root / accounting.REGISTRY / "manifest.json"))
        assert anchor["baseline"]["count"] == 0
        from uuid import NAMESPACE_URL, uuid4, uuid5

        binding = {
            "root_sha256": anchor["root_sha256"],
            "resource_domain_sha256": anchor["resource_domain_sha256"],
            "identity_manifest_sha256": accounting.digest(accounting.canonical(anchor)),
            "ledger_ref": accounting.LEDGER,
            "grant_sha256": "a" * 64,
            "runner_sha256": "b" * 64,
            "plan_sha256": "c" * 64,
            "execution_input_sha256": "d" * 64,
            "expires_at": 4000000000,
            "max_attempts": 3,
            "max_reserved_bytes": 1048576,
            "reserve_bytes": 65536,
            "disk_floor_bytes": 0,
        }
        import asyncio

        from mcp import Client

        from cadence_mcp_bridge.amplifier_sweeps import DEFINITION_SHA, REVISION, AmplifierChild
        from cadence_mcp_bridge.bias_range import SOURCES
        from cadence_mcp_bridge.power_measurements import (
            REFERENCE_OPERATION,
            SOURCE_SET,
            PowerExtraction,
        )
        from cadence_mcp_bridge.server import create_server
        from cadence_mcp_bridge.service import CadenceService
        from cadence_mcp_bridge.storage import StorageSnapshot, StorageSupervisor, snapshot_digest

        def verify_consumer():
            counter = accounting.read(str(fresh_root / accounting.LEDGER))
            # Exercise the installed production extraction model, not just its
            # otherwise-unused type alias. Sources are synthetic zero-current frames.
            extracted = PowerExtraction.model_validate_json(json.dumps(dict(
                schema_version=1, job_id=REFERENCE_OPERATION, analysis="dc",
                input_sha256="a" * 64, psf_sha256="b" * 64, frame_sha256="c" * 64,
                sources=[dict(source_id=identity, role=role, voltage_v=voltage, current_a=0)
                         for identity, role, voltage in SOURCE_SET],
                status="EXTRACTED", reason=None, protected_unchanged=True,
                counter=dict(counter, policy=anchor["policy"]),
                new_spectre_attempts=0, new_reservation_bytes=0,
            )))
            assert extracted.counter.count == counter["count"]
            assert extracted.counter.model_dump()["policy"] == anchor["policy"]
            if counter["count"]:
                # Use the actual disposable fresh ledger's early1/2 observations.
                # Scientific frame is synthetic; this is installed parser evidence.
                point = AmplifierChild.model_validate(dict(
                    schema_version=2, definition_sha256=DEFINITION_SHA, revision_id=REVISION,
                    job_id=uuid5(NAMESPACE_URL, "installed-fresh-amplifier-counter"),
                    plan_hash="a" * 64, analysis="dc", requested_vbiasn_v="0.319",
                    input_sha256="a" * 64, psf_sha256="b" * 64, frame_sha256="c" * 64,
                    source_job_id=SOURCES["dc"][0], source_input_sha256=SOURCES["dc"][1],
                    source_psf_sha256=SOURCES["dc"][2],
                    counter=dict(counter, policy=anchor["policy"]),
                    protected_unchanged=True, warnings=0, notices=0,
                    scalars=dict(Vop=0.4, Vom=0.3, Vp=0.5, Vm=0.5, VDD=1,
                                 Vbiasn=0.319, Vbiasp=0.702),
                    sources=[dict(source_id=identity, role=role,
                                  voltage_v=0.319 if identity == "bias-n" else voltage,
                                  current_a=0) for identity, role, voltage in SOURCE_SET],
                ))
                assert point.counter.model_dump() == dict(counter, policy=anchor["policy"])
            snapshot = StorageSnapshot.model_validate(dict(
                contract_version=2, snapshot_id="a" * 64, artifacts=[], coverage_complete=True,
                group_coverage={}, filesystem_free_bytes=10485760, filesystem_total_bytes=20971520,
                reserved_result_bytes=counter["result_reserved_bytes"],
                spectre_attempts=counter["count"], result_ceiling_bytes=1048576,
                ledger_policy=anchor["policy"], active_eda=False, platform_delete_primitives=True,
            ))
            assert snapshot.result_ceiling_bytes == profile["limits"]["result_reserved_bytes"]
            snapshot = snapshot.model_copy(update={"snapshot_id": snapshot_digest(snapshot)})

            class ReadOnlyStorage:
                async def storage_snapshot(self):
                    return snapshot

                async def storage_cleanup(self, _request):
                    raise AssertionError("Installed read-only verification cannot clean storage")

            async def check_summary():
                backend = ReadOnlyStorage()
                summary = await StorageSupervisor(backend).summary()
                assert summary.result_ceiling_bytes == anchor["policy"]["result_ceiling_bytes"]
                assert summary.reserved_result_bytes == counter["result_reserved_bytes"]
                async with Client(create_server(CadenceService(backend))) as client:
                    result = await client.call_tool("cadence_storage_summary", {})
                    assert not result.is_error
                    assert result.structured_content["result_ceiling_bytes"] == (
                        anchor["policy"]["result_ceiling_bytes"]
                    )
                    assert result.structured_content["spectre_attempts"] == counter["count"]

            asyncio.run(check_summary())

        verify_consumer()
        for _ in range(2):
            operation = str(uuid4())
            work = fresh_root / accounting.JOBS / operation / "work"
            work.mkdir(mode=0o700, parents=True)
            receipt = accounting.reserve(str(fresh_root), operation, binding)
            assert accounting.reserve(str(fresh_root), operation, binding) == receipt
            verify_consumer()
        consumed = snapshots(fresh_root)
        assert setup.apply_fresh(request, setup_digest)["ledger_initialized"] is False
        assert snapshots(fresh_root) == consumed
        assert accounting.read(str(fresh_root / accounting.LEDGER))["count"] == 2
    finally:
        setup.home, setup.profile = original_home, original_setup_profile
        installer._operator_lock = original_lock
    (workspace / "preservation.json").write_text(json.dumps(snapshots(root), sort_keys=True))
    return {
        "status": "PASS",
        "scope": "INSTALLED_EXISTING_MIGRATION_SYNTHETIC",
        "exported_helper_sha256": digest,
        "remote_contact": False,
        "ledger_modified": False,
        "execution_authorized": False,
        "native_jobs": 0,
        "fresh_zero_policy_two_batches": "DISPOSABLE_FILES_ONLY_NOT_SIMULATIONS",
        "fresh_storage_and_power_counter_contracts": "PASS_SYNTHETIC_POLICY_BOUND",
        "fresh_production_power_extraction_and_sdk_storage_summary": "PASS_SYNTHETIC_POLICY_BOUND",
        "fresh_early_installed_amplifier_disposable_counter": "PASS_SYNTHETIC_FRAME",
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
