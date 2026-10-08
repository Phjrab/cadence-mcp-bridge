"""Operator-only existing-domain planning and explicitly invoked migration."""

from __future__ import annotations

import base64
import hashlib
import json
import shlex
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


def _closed_document(data: bytes) -> None:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in items:
            if key in value:
                raise ValueError("duplicate migration JSON field")
            value[key] = item
        return value

    def constant(_: str) -> None:
        raise ValueError("nonfinite migration JSON")

    if len(data) > 262144:
        raise ValueError("migration document too large")
    try:
        json.loads(data.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
    except RecursionError as error:
        raise ValueError("migration document nesting") from error


def contents(setup: bool = False) -> tuple[dict[str, bytes], bytes, str]:
    sources = {**SOURCES, "setup.py": "_fresh_domain.py"} if setup else SOURCES
    assets = {
        name: files("cadence_mcp_bridge").joinpath(source).read_bytes()
        for name, source in sources.items()
    }
    manifest = {
        "schema_version": 1,
        "kind": "STANDARD_VM_DOMAIN_SETUP_HELPER" if setup else "EXISTING_DOMAIN_OPERATOR_HELPER",
        "files": {
            name: {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
            for name, data in assets.items()
        },
    }
    raw: bytes = _canonical(manifest)
    return assets, raw, hashlib.sha256(raw).hexdigest()


def export(output: Path, setup: bool = False) -> dict[str, object]:
    output = _local_path(output)
    assets, manifest, digest = contents(setup)
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


def prepare(
    profile: Path,
    output: Path,
    expected_helper_sha256: str,
    seal: bool = False,
    result_limit: bool = False,
) -> dict[str, object]:
    environment, data = load_environment(_local_path(profile))
    _, _, expected = contents()
    if expected_helper_sha256 != expected:
        raise ValueError("helper_package_binding_mismatch")
    raw_profile: bytes = _canonical(json.loads(data))
    return _transport(
        environment,
        raw_profile,
        expected,
        "plan-result-limit-v6"
        if result_limit
        else ("inventory-legacy-seal" if seal else "inventory-existing"),
        output,
    )


def _transport(
    environment: EnvironmentProfile, payload: bytes, expected: str, action: str, output: Path
) -> dict[str, object]:
    output = _local_path(output)
    if output.exists() or not output.parent.is_dir():
        raise ValueError("exclusive_receipt_parent_required")
    executable = shutil.which("ssh.exe")
    if executable is None:
        raise ValueError("OpenSSH unavailable")
    allowed = {
        "inventory-existing",
        "apply-existing",
        "inventory-legacy-seal",
        "seal-existing",
        "plan-fresh",
        "apply-fresh",
        "register-existing",
        "plan-result-limit-v6",
        "apply-result-limit-v6",
    }
    if action not in allowed:
        raise ValueError("fixed_domain_action_required")
    helper_name = (
        "migration.py"
        if action
        in {
            "inventory-existing",
            "apply-existing",
            "inventory-legacy-seal",
            "seal-existing",
            "plan-result-limit-v6",
            "apply-result-limit-v6",
        }
        else "setup.py"
    )
    helper_path = (
        environment.paths.managed_root + "/operator-helpers/" + expected + "/migration.py"
        if helper_name == "migration.py"
        else environment.paths.workspace_root + "/.cadence_mcp-setup/" + expected + "/setup.py"
    )
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
        helper_path,
        action,
        expected,
    ]
    status, stdout, stderr = run_fixed(
        argv, payload, OpenSshBackend._ssh_environment(), timeout=60, limit=262144
    )
    if status or stderr:
        raise ValueError("existing_domain_inventory_rejected")
    _closed_document(stdout)
    receipt = json.loads(stdout)
    if action in {"apply-fresh", "register-existing"}:
        return _setup_receipt(receipt, stdout, output, json.loads(payload), action)
    if action == "apply-result-limit-v6":
        from cadence_mcp_bridge import _shared_reservations as accounting

        request = json.loads(payload)
        value = request["plan"]
        if (
            not isinstance(receipt, dict)
            or set(receipt)
            != {
                "status",
                "created",
                "policy_sha256",
                "plan_sha256",
                "ledger_sha256",
                "result_ceiling_bytes",
                "execution_authorized",
                "ledger_modified",
                "ledger_initialized",
                "reservation_cost",
            }
            or receipt["status"] != "RETAINED_RESULT_LIMIT_APPLIED_NO_LEDGER_CHANGE"
            or type(receipt["created"]) is not bool
            or receipt["policy_sha256"] != accounting.RESULT_POLICY_SHA
            or receipt["plan_sha256"] != request["expected_plan_sha256"]
            or receipt["ledger_sha256"] != value["snapshot"]["ledger_sha256"]
            or type(receipt["result_ceiling_bytes"]) is not int
            or receipt["result_ceiling_bytes"] != accounting.MAX_POLICY_BYTES
            or any(
                receipt[k] is not False
                for k in ("execution_authorized", "ledger_modified", "ledger_initialized")
            )
            or type(receipt["reservation_cost"]) is not int
            or receipt["reservation_cost"] != 0
        ):
            raise ValueError("result_limit_apply_receipt_binding")
        installer.exclusive(str(output), stdout)  # type: ignore[no-untyped-call]
        return {**receipt, "remote_contact": True}
    if action in {"apply-existing", "seal-existing"}:
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
    seal: bool = False,
    result_limit: bool = False,
) -> dict[str, object]:
    """Account-owner CLI invocation; authority text records the actual human instruction."""
    environment, data = load_environment(_local_path(profile))
    _, _, expected = contents()
    if expected != expected_helper_sha256:
        raise ValueError("helper_package_binding_mismatch")
    raw = installer.regular(str(_local_path(plan)))  # type: ignore[no-untyped-call]
    _closed_document(raw)
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
    return _transport(
        environment,
        _canonical(request),
        expected,
        "apply-result-limit-v6"
        if result_limit
        else ("seal-existing" if seal else "apply-existing"),
        output,
    )


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


def prepare_fresh(profile: Path, output: Path, expected_helper_sha256: str) -> dict[str, object]:
    environment, data = load_environment(_local_path(profile))
    _, _, expected = contents(True)
    if expected != expected_helper_sha256:
        raise ValueError("helper_package_binding_mismatch")
    return _transport(environment, _canonical(json.loads(data)), expected, "plan-fresh", output)


def setup_existing(
    profile: Path,
    output: Path,
    expected_helper_sha256: str,
    identity_manifest_sha256: str,
    operator_authority: str,
) -> dict[str, object]:
    environment, data = load_environment(_local_path(profile))
    _, _, expected = contents(True)
    if expected != expected_helper_sha256:
        raise ValueError("helper_package_binding_mismatch")
    from cadence_mcp_bridge import _shared_reservations as accounting

    if not accounting.matches(accounting.HASH, identity_manifest_sha256):  # type: ignore[no-untyped-call]
        raise ValueError("identity_manifest_binding")
    _instruction(operator_authority)
    plan = {
        "schema_version": 1,
        "profile": json.loads(data),
        "identity_manifest_sha256": identity_manifest_sha256,
        "helper_manifest_sha256": expected,
    }
    request = {
        "plan": plan,
        "expected_plan_sha256": hashlib.sha256(_canonical(plan)).hexdigest(),
        "operator_authority": operator_authority,
    }
    return _transport(environment, _canonical(request), expected, "register-existing", output)


def _instruction(operator_authority: str) -> None:
    if not 1 <= len(operator_authority) <= 512 or any(ord(c) < 32 for c in operator_authority):
        raise ValueError("actual_operator_instruction_required")


def apply_fresh(
    profile: Path,
    plan: Path,
    output: Path,
    expected_plan_sha256: str,
    expected_helper_sha256: str,
    operator_authority: str,
) -> dict[str, object]:

    environment, data = load_environment(_local_path(profile))
    _, _, expected = contents(True)
    if expected != expected_helper_sha256:
        raise ValueError("helper_package_binding_mismatch")
    raw = installer.regular(str(_local_path(plan)))  # type: ignore[no-untyped-call]
    _closed_document(raw)
    receipt = json.loads(raw)
    _instruction(operator_authority)
    if (
        not isinstance(receipt, dict)
        or set(receipt) != {"plan", "plan_sha256", "execution_authorized", "ledger_initialized"}
        or receipt["execution_authorized"] is not False
        or receipt["ledger_initialized"] is not False
        or not isinstance(receipt["plan"], dict)
        or receipt["plan_sha256"] != expected_plan_sha256
        or receipt["plan"].get("recipe_id") != "fresh-standard-vm-domain-v1"
        or receipt["plan"].get("helper_manifest_sha256") != expected
        or _canonical(receipt["plan"].get("profile")) != _canonical(json.loads(data))
        or hashlib.sha256(_canonical(receipt["plan"])).hexdigest() != expected_plan_sha256
    ):
        raise ValueError("fresh_domain_plan_binding")
    request = {
        "plan": receipt["plan"],
        "expected_plan_sha256": expected_plan_sha256,
        "operator_authority": operator_authority,
    }
    return _transport(environment, _canonical(request), expected, "apply-fresh", output)


def _setup_receipt(
    receipt: Any, raw: bytes, output: Path, request: Any, action: str
) -> dict[str, object]:
    expected = request["plan"].get("identity_manifest_sha256")
    if action == "apply-fresh":
        expected = hashlib.sha256(_canonical(request["plan"]["anchor"])).hexdigest()
    if (
        not isinstance(receipt, dict)
        or set(receipt)
        != {
            "status",
            "identity_manifest_sha256",
            "ledger_initialized",
            "ledger_modified",
            "execution_authorized",
        }
        or receipt["identity_manifest_sha256"] != expected
        or receipt["ledger_modified"] is not False
        or receipt["execution_authorized"] is not False
        or type(receipt["ledger_initialized"]) is not bool
        or (
            action == "register-existing"
            and (
                receipt["ledger_initialized"] is not False
                or receipt["status"] != "EXISTING_DOMAIN_REGISTERED_NO_LEDGER_CHANGE"
            )
        )
        or (
            action == "apply-fresh"
            and (receipt["status"], receipt["ledger_initialized"])
            not in {
                ("FRESH_DOMAIN_INITIALIZED_NOT_EXECUTION_AUTHORITY", True),
                ("EXISTING_FRESH_DOMAIN_REUSED", False),
            }
        )
    ):
        raise ValueError("setup_receipt_binding")
    installer.exclusive(str(output), raw)  # type: ignore[no-untyped-call]
    return {**receipt, "remote_contact": True}


def stage_setup(
    profile: Path, expected_helper_sha256: str, migration: bool = False
) -> dict[str, object]:
    """Stage only current package's fixed helper set, never caller filenames/content/code."""
    environment, data = load_environment(_local_path(profile))
    assets, manifest, expected = contents(not migration)
    if expected != expected_helper_sha256:
        raise ValueError("helper_package_binding_mismatch")
    executable = shutil.which("ssh.exe")
    if executable is None:
        raise ValueError("OpenSSH unavailable")
    payload = {
        "profile": json.loads(data),
        "expected": expected,
        "files": {
            name: base64.b64encode(raw).decode("ascii")
            for name, raw in {**assets, "manifest.json": manifest}.items()
        },
    }
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
        "-c",
        shlex.quote(
            files("cadence_mcp_bridge").joinpath("_setup_stage.py").read_text(encoding="utf-8")
        ),
        expected,
    ]
    status, stdout, stderr = run_fixed(
        argv, _canonical(payload), OpenSshBackend._ssh_environment(), timeout=60, limit=262144
    )
    if status or stderr or len(stdout) > 4096:
        raise ValueError("fixed_setup_staging_rejected")
    _closed_document(stdout)
    result = json.loads(stdout)
    if (
        not isinstance(result, dict)
        or set(result) != {"status", "manifest_sha256", "changed_files", "execution_authorized"}
        or result["status"] != "STANDARD_VM_SETUP_HELPER_STAGED"
        or result["manifest_sha256"] != expected
        or type(result["changed_files"]) is not int
        or not 0 <= result["changed_files"] <= 6
        or result["execution_authorized"] is not False
    ):
        raise ValueError("fixed_setup_staging_receipt")
    return {**result, "remote_contact": True, "ledger_initialized": False}
