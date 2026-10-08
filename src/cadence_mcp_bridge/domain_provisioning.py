"""Operator-only existing-domain planning and explicitly invoked migration."""

from __future__ import annotations

import hashlib
import json
import shutil
from importlib.resources import files
from pathlib import Path
from typing import Any

from cadence_mcp_bridge import _runner_bootstrap as installer
from cadence_mcp_bridge.environments import EnvironmentProfile, load_environment
from cadence_mcp_bridge.onboarding import _local_path
from cadence_mcp_bridge.operator_transport import run_fixed
from cadence_mcp_bridge.ssh_backend import OpenSshBackend

SOURCES = {
    "migration.py": "_domain_migration.py",
    "reservations.py": "_shared_reservations.py",
    "installer.py": "_runner_bootstrap.py",
    "probe.py": "_environment_probe.py",
}


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "ascii"
    )


def contents() -> tuple[dict[str, bytes], bytes, str]:
    assets = {
        name: files("cadence_mcp_bridge").joinpath(source).read_bytes()
        for name, source in SOURCES.items()
    }
    manifest = {
        "schema_version": 1,
        "kind": "EXISTING_DOMAIN_OPERATOR_HELPER",
        "files": {
            name: {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
            for name, data in assets.items()
        },
    }
    raw: bytes = _canonical(manifest)
    return assets, raw, hashlib.sha256(raw).hexdigest()


def export(output: Path) -> dict[str, object]:
    output = _local_path(output)
    assets, manifest, digest = contents()
    if output.exists() or not output.parent.is_dir():
        raise ValueError("exclusive_helper_parent_required")
    output.mkdir(mode=0o700)
    for name, data in {**assets, "manifest.json": manifest}.items():
        installer.exclusive(str(output / name), data)  # type: ignore[no-untyped-call]
    return {
        "status": "EXISTING_DOMAIN_HELPER_EXPORTED",
        "manifest_sha256": digest,
        "total_asset_bytes": sum(map(len, assets.values())),
        "execution_authorized": False,
        "remote_contact": False,
        "ledger_initialized": False,
    }


def prepare(profile: Path, output: Path, expected_helper_sha256: str) -> dict[str, object]:
    environment, data = load_environment(_local_path(profile))
    _, _, expected = contents()
    if expected_helper_sha256 != expected:
        raise ValueError("helper_package_binding_mismatch")
    raw_profile: bytes = _canonical(json.loads(data))
    return _transport(environment, raw_profile, expected, "inventory-existing", output)


def _transport(
    environment: EnvironmentProfile, payload: bytes, expected: str, action: str, output: Path
) -> dict[str, object]:
    output = _local_path(output)
    if output.exists() or not output.parent.is_dir():
        raise ValueError("exclusive_receipt_parent_required")
    executable = shutil.which("ssh.exe")
    if executable is None:
        raise ValueError("OpenSSH unavailable")
    argv = [
        executable,
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "ConnectTimeout=10",
        environment.ssh_alias,
        "/usr/bin/python",
        "-E",
        "-s",
        "-B",
        environment.paths.managed_root + "/operator-helpers/" + expected + "/migration.py",
        action,
        expected,
    ]
    status, stdout, stderr = run_fixed(
        argv, payload, OpenSshBackend._ssh_environment(), timeout=60, limit=262144
    )
    if status or stderr:
        raise ValueError("existing_domain_inventory_rejected")
    from cadence_mcp_bridge.environments import _closed_json

    _closed_json(stdout)
    receipt = json.loads(stdout)
    if action == "apply-existing":
        return _apply_receipt(receipt, stdout, output, json.loads(payload))
    if (
        not isinstance(receipt, dict)
        or set(receipt) != {"plan", "plan_sha256", "execution_authorized", "ledger_initialized"}
        or receipt["execution_authorized"] is not False
        or receipt["ledger_initialized"] is not False
        or not isinstance(receipt["plan"], dict)
        or receipt["plan"].get("helper_manifest_sha256") != expected
        or receipt["plan"].get("profile_sha256") != hashlib.sha256(payload).hexdigest()
        or receipt["plan_sha256"] != hashlib.sha256(_canonical(receipt["plan"])).hexdigest()
    ):
        raise ValueError("existing_domain_receipt_binding")
    installer.exclusive(str(_local_path(output)), stdout)  # type: ignore[no-untyped-call]
    return {
        "status": "EXISTING_DOMAIN_PLAN_PRIVATE_NOT_APPROVAL",
        "plan_sha256": receipt["plan_sha256"],
        "helper_manifest_sha256": expected,
        "ledger_initialized": False,
        "execution_authorized": False,
        "remote_contact": True,
    }


def apply_existing(
    profile: Path,
    plan: Path,
    output: Path,
    expected_plan_sha256: str,
    expected_helper_sha256: str,
    operator_authority: str,
) -> dict[str, object]:
    """Account-owner CLI invocation; authority text records the actual human instruction."""
    from cadence_mcp_bridge.environments import _closed_json

    environment, data = load_environment(_local_path(profile))
    _, _, expected = contents()
    if expected != expected_helper_sha256:
        raise ValueError("helper_package_binding_mismatch")
    raw = installer.regular(str(_local_path(plan)))  # type: ignore[no-untyped-call]
    _closed_json(raw)
    receipt = json.loads(raw)
    if (
        not isinstance(receipt, dict)
        or set(receipt) != {"plan", "plan_sha256", "execution_authorized", "ledger_initialized"}
        or receipt["execution_authorized"] is not False
        or receipt["ledger_initialized"] is not False
        or not isinstance(receipt["plan"], dict)
        or receipt["plan_sha256"] != expected_plan_sha256
        or receipt["plan"].get("helper_manifest_sha256") != expected
        or _canonical(receipt["plan"].get("profile")) != _canonical(json.loads(data))
        or hashlib.sha256(_canonical(receipt["plan"])).hexdigest() != expected_plan_sha256
        or not 1 <= len(operator_authority) <= 512
        or any(ord(c) < 32 for c in operator_authority)
    ):
        raise ValueError("existing_domain_plan_or_authority_binding")
    request = {
        "plan": receipt["plan"],
        "expected_plan_sha256": expected_plan_sha256,
        "operator_authority": operator_authority,
    }
    return _transport(environment, _canonical(request), expected, "apply-existing", output)


def _apply_receipt(receipt: Any, raw: bytes, output: Path, request: Any) -> dict[str, object]:

    value = request["plan"]
    required = {
        "schema_version",
        "plan_sha256",
        "identity_manifest_sha256",
        "snapshot_sha256",
        "ledger_sha256",
        "status",
        "execution_authorized",
        "ledger_initialized",
        "ledger_modified",
        "reservation_cost",
        "anchor_created",
    }
    if (
        not isinstance(receipt, dict)
        or set(receipt) != required
        or type(receipt["schema_version"]) is not int
        or receipt["schema_version"] != 1
        or receipt["plan_sha256"] != request["expected_plan_sha256"]
        or receipt["identity_manifest_sha256"]
        != hashlib.sha256(_canonical(value["anchor"])).hexdigest()
        or receipt["snapshot_sha256"] != hashlib.sha256(_canonical(value["snapshot"])).hexdigest()
        or receipt["ledger_sha256"] != value["snapshot"]["ledger_sha256"]
        or receipt["status"] != "EXISTING_DOMAIN_ANCHORED_NOT_EXECUTION_AUTHORITY"
        or any(
            receipt[k] is not False
            for k in ("execution_authorized", "ledger_initialized", "ledger_modified")
        )
        or type(receipt["reservation_cost"]) is not int
        or receipt["reservation_cost"] != 0
        or type(receipt["anchor_created"]) is not bool
    ):
        raise ValueError("existing_domain_apply_receipt_binding")
    installer.exclusive(str(output), raw)  # type: ignore[no-untyped-call]
    return {**receipt, "remote_contact": True}
