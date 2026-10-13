"""Explicit operator-only confirmation CLI. No MCP grant writer or EDA dispatch."""

from __future__ import annotations

import base64
import hashlib
import json
import shlex
import shutil
import time
from importlib.resources import files
from pathlib import Path
from typing import Any

from cadence_mcp_bridge import _operator_confirmation as confirmation
from cadence_mcp_bridge import _runner_bootstrap as installer
from cadence_mcp_bridge.domain_provisioning import _canonical, _closed_document
from cadence_mcp_bridge.environments import EnvironmentProfile, load_environment
from cadence_mcp_bridge.onboarding import _local_path
from cadence_mcp_bridge.operator_operations import OperationRejected, load_grant, match_grant
from cadence_mcp_bridge.operator_transport import run_fixed
from cadence_mcp_bridge.runtime_context import ExecutionContext
from cadence_mcp_bridge.ssh_backend import OpenSshBackend

SOURCES = {
    "confirmation.py": "_operator_confirmation.py",
    "reservations.py": "_shared_reservations.py",
    "installer.py": "_runner_bootstrap.py",
    "probe.py": "_environment_probe.py",
}


def contents() -> tuple[dict[str, bytes], bytes, str]:
    assets = {
        name: files("cadence_mcp_bridge").joinpath(source).read_bytes()
        for name, source in SOURCES.items()
    }
    raw = _canonical(
        {
            "schema_version": 1,
            "kind": confirmation.KIND,
            "files": {
                name: {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
                for name, data in assets.items()
            },
        }
    )
    return assets, raw, hashlib.sha256(raw).hexdigest()


def export(output: Path) -> dict[str, object]:
    target = _local_path(output)
    assets, raw, expected = contents()
    if target.exists() or not target.parent.is_dir():
        raise OperationRejected("exclusive_confirmation_helper_parent_required")
    target.mkdir(mode=0o700)
    for name, data in {**assets, "manifest.json": raw}.items():
        installer.exclusive(str(target / name), data)  # type: ignore[no-untyped-call]
    return {
        "status": "OPERATOR_CONFIRMATION_HELPER_EXPORTED",
        "manifest_sha256": expected,
        "execution_authorized": False,
        "remote_contact": False,
    }


def _ssh(environment: EnvironmentProfile) -> list[str]:
    executable = shutil.which("ssh.exe")
    if executable is None:
        raise OperationRejected("OpenSSH_unavailable")
    return [
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
    ]


def _expected(expected: str) -> tuple[dict[str, bytes], bytes]:
    assets, raw, actual = contents()
    if expected != actual:
        raise OperationRejected("confirmation_helper_package_binding_mismatch")
    return assets, raw


def stage(profile: Path, expected: str) -> dict[str, object]:
    environment, data = load_environment(_local_path(profile))
    assets, raw = _expected(expected)
    request = {
        "profile": json.loads(data),
        "expected": expected,
        "files": {
            name: base64.b64encode(value).decode("ascii")
            for name, value in {**assets, "manifest.json": raw}.items()
        },
    }
    code = files("cadence_mcp_bridge").joinpath("_setup_stage.py").read_text("utf-8")
    status, stdout, stderr = run_fixed(
        _ssh(environment) + ["-c", shlex.quote(code), expected],
        _canonical(request),
        OpenSshBackend._ssh_environment(),
        timeout=60,
        limit=262144,
    )
    if status or stderr:
        raise OperationRejected("confirmation_staging_rejected")
    _closed_document(stdout)
    receipt = json.loads(stdout)
    if set(receipt) != {"status", "manifest_sha256", "changed_files", "execution_authorized"} or (
        receipt["status"] != "STANDARD_VM_CONFIRMATION_HELPER_STAGED"
        or receipt["manifest_sha256"] != expected
        or type(receipt["changed_files"]) is not int
        or not 0 <= receipt["changed_files"] <= len(assets) + 1
        or receipt["execution_authorized"] is not False
    ):
        raise OperationRejected("confirmation_staging_receipt_mismatch")
    return {**receipt, "remote_contact": True}


def _transport(
    environment: EnvironmentProfile, expected: str, action: str, request: dict[str, Any]
) -> dict[str, Any]:
    _expected(expected)
    if action not in {"confirm", "inspect", "revoke"}:
        raise OperationRejected("confirmation_fixed_action_required")
    helper = (
        environment.paths.workspace_root + "/.cadence_mcp-setup/" + expected + "/confirmation.py"
    )
    status, stdout, stderr = run_fixed(
        _ssh(environment) + [helper, action, expected],
        _canonical(request),
        OpenSshBackend._ssh_environment(),
        timeout=60,
        limit=262144,
    )
    if status or stderr:
        raise OperationRejected("OS_operator_confirmation_rejected")
    _closed_document(stdout)
    receipt = json.loads(stdout)
    expected_keys = {
        "status",
        "grant_sha256",
        "confirmation_sha256",
        "operator_confirmed",
        "execution_authorized",
    }
    if action != "inspect":
        expected_keys |= {"operator_uid", "changed", "new_reservations", "new_simulations"}
    if action == "confirm":
        expected_keys.add("counter")
    expected_status = {
        "confirm": "OS_OPERATOR_CONFIRMATION_RECORDED",
        "inspect": "OS_OPERATOR_CONFIRMATION_OBSERVED",
        "revoke": "OS_OPERATOR_CONFIRMATION_REVOKED",
    }[action]
    if (
        not isinstance(receipt, dict)
        or set(receipt) != expected_keys
        or (
            receipt["status"] != expected_status
            or receipt["grant_sha256"] != request["grant_sha256"]
            or receipt["execution_authorized"] is not False
            or type(receipt["operator_confirmed"]) is not bool
        )
    ):
        raise OperationRejected("confirmation_receipt_mismatch")
    if not confirmation.matches(  # type: ignore[no-untyped-call]
        r"^[0-9a-f]{64}$", receipt["confirmation_sha256"]
    ):
        raise OperationRejected("confirmation_receipt_digest")
    if action != "inspect" and (
        type(receipt["changed"]) is not bool
        or type(receipt["operator_uid"]) is not int
        or receipt["operator_uid"] <= 0
        or type(receipt["new_reservations"]) is not int
        or receipt["new_reservations"] != 0
        or type(receipt["new_simulations"]) is not int
        or receipt["new_simulations"] != 0
        or receipt["operator_confirmed"] != (action == "confirm")
    ):
        raise OperationRejected("confirmation_receipt_scope")
    if action == "confirm":
        counter = receipt["counter"]
        if (
            not isinstance(counter, dict)
            or set(counter) != {"campaign_id", "count", "result_reserved_bytes"}
            or (
                not isinstance(counter["campaign_id"], str)
                or len(counter["campaign_id"]) > 64
                or type(counter["count"]) is not int
                or type(counter["result_reserved_bytes"]) is not int
                or not 0 <= counter["count"] <= environment.limits.spectre_attempts
                or not 0
                <= counter["result_reserved_bytes"]
                <= environment.limits.result_reserved_bytes
            )
        ):
            raise OperationRejected("confirmation_counter_receipt_invalid")
        if (
            receipt["confirmation_sha256"]
            != hashlib.sha256(
                _canonical(
                    {
                        "schema_version": 1,
                        "grant_sha256": request["grant_sha256"],
                        "grant": json.loads(request["grant_json"]),
                        "grant_json": request["grant_json"],
                        "identity_manifest_sha256": request["identity_manifest_sha256"],
                        "root_sha256": hashlib.sha256(
                            environment.paths.managed_root.encode("utf-8")
                        ).hexdigest(),
                        "resource_domain_sha256": json.loads(request["grant_json"])[
                            "resource_domain_sha256"
                        ],
                        "operator_uid": receipt["operator_uid"],
                        "operator_user": environment.host.user,
                        "operator_authority": request["operator_authority"],
                        "confirmation_helper_sha256": expected,
                    }
                )
            ).hexdigest()
        ):
            raise OperationRejected("confirmation_record_receipt_digest")
    return {**receipt, "remote_contact": True}


def perform(
    context: ExecutionContext,
    grant_path: Path,
    grant_sha: str,
    anchor: str,
    expected_helper: str,
    action: str,
    output: Path,
    operator_authority: str | None = None,
) -> dict[str, Any]:
    """Confirm/revoke are explicitly invoked human CLI actions, never model MCP tools."""
    target = _local_path(output)
    if target.exists() or not target.parent.is_dir():
        raise OperationRejected("exclusive_confirmation_receipt_parent_required")
    _expected(expected_helper)
    if not confirmation.matches(r"^[0-9a-f]{64}$", anchor):  # type: ignore[no-untyped-call]
        raise OperationRejected("confirmation_identity_manifest_digest")
    grant, digest = load_grant(grant_path, grant_sha)
    environment, raw_profile = load_environment(context.binding.environment_profile)
    if hashlib.sha256(raw_profile).hexdigest() != context.binding.environment_sha256:
        raise OperationRejected("confirmation_profile_changed")
    request: dict[str, Any] = {
        "profile": environment.model_dump(mode="json"),
        "grant_sha256": digest,
        "identity_manifest_sha256": anchor,
    }
    if action == "confirm":
        match_grant(context, grant, int(time.time()))
        raw = grant_path.read_bytes()
        if raw != _canonical(grant.model_dump(mode="json")):
            raise OperationRejected("confirmation_canonical_grant_required")
        request = {
            "schema_version": 1,
            "profile_json": raw_profile.decode("ascii"),
            "grant_json": raw.decode("ascii"),
            "grant_sha256": digest,
            "identity_manifest_sha256": anchor,
        }
    elif action not in {"inspect", "revoke"}:
        raise OperationRejected("confirmation_fixed_action_required")
    if action != "inspect":
        confirmation.authority_reference(operator_authority)  # type: ignore[no-untyped-call]
        request["operator_authority"] = operator_authority
    receipt = _transport(environment, expected_helper, action, request)
    installer.exclusive(str(target), _canonical(receipt))  # type: ignore[no-untyped-call]
    return receipt
