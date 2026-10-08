"""Installed operator runner planning, exclusive content installation and verification."""

from __future__ import annotations

import hashlib
import os
from importlib.resources import files
from pathlib import Path
from typing import Any

from cadence_mcp_bridge import _runner_bootstrap as installer
from cadence_mcp_bridge.environments import load_environment, probe_bytes
from cadence_mcp_bridge.onboarding import _local_path


def bundle(profile: Path, output: Path) -> dict[str, object]:
    profile = _local_path(profile)
    environment, data = load_environment(profile)
    output = _local_path(output)
    if output.exists() or not output.parent.is_dir():
        raise ValueError("exclusive_bundle_parent_required")
    contents = {
        "reservations.py": files("cadence_mcp_bridge")
        .joinpath("_shared_reservations.py")
        .read_bytes(),
        "profile.json": data,
        "probe.py": probe_bytes(),
        "runner.py": files("cadence_mcp_bridge").joinpath("_generic_runner.py").read_bytes(),
        "launcher.py": files("cadence_mcp_bridge").joinpath("_runner_launcher.py").read_bytes(),
    }
    manifest = {
        "schema_version": 2,
        "environment_id": environment.environment_id,
        "profile_sha256": hashlib.sha256(data).hexdigest(),
        "files": {
            name: {"sha256": hashlib.sha256(value).hexdigest(), "bytes": len(value)}
            for name, value in contents.items()
        },
    }
    raw = installer.canonical(manifest)  # type: ignore[no-untyped-call]
    output.mkdir(mode=0o700)
    for name, value in {**contents, "manifest.json": raw}.items():
        installer.exclusive(str(output / name), value)  # type: ignore[no-untyped-call]
    return {
        "status": "RUNNER_BUNDLE_PREPARED_LOCAL",
        "environment_id": environment.environment_id,
        "manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "runner_sha256": hashlib.sha256(contents["launcher.py"]).hexdigest(),
        "total_asset_bytes": sum(len(value) for value in contents.values()),
        "execution_authorized": False,
        "remote_contact": False,
    }


def export_installer(output: Path) -> dict[str, object]:
    output = _local_path(output)
    data = files("cadence_mcp_bridge").joinpath("_runner_bootstrap.py").read_bytes()
    installer.exclusive(str(output), data)  # type: ignore[no-untyped-call]
    return {
        "status": "FIXED_INSTALLER_EXPORTED",
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "execution_authorized": False,
        "remote_contact": False,
    }


def export_repair_helper(output: Path) -> dict[str, object]:
    """Export only; import/startup/doctor never changes installation metadata."""
    output = _local_path(output)
    data = files("cadence_mcp_bridge").joinpath("_installation_repair.py").read_bytes()
    installer.exclusive(str(output), data)  # type: ignore[no-untyped-call]
    return {
        "status": "OPERATOR_REPAIR_HELPER_EXPORTED",
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "execution_authorized": False,
        "remote_contact": False,
        "protected_permissions_changed": False,
    }


def prepare_repair(profile: Path, output: Path) -> dict[str, object]:
    """Read-only standard-VM inventory; exclusive private plan, no approval minted."""
    import json
    import shlex
    import shutil

    from cadence_mcp_bridge import _installation_repair as repair
    from cadence_mcp_bridge.operator_transport import run_fixed
    from cadence_mcp_bridge.ssh_backend import OpenSshBackend

    environment, data = load_environment(_local_path(profile))
    executable = shutil.which("ssh.exe")
    if executable is None:
        raise ValueError("OpenSSH unavailable")
    code = files("cadence_mcp_bridge").joinpath("_installation_repair.py").read_text("utf-8")
    status, stdout, stderr = run_fixed(
        [executable, "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
         "-o", "ConnectTimeout=10", environment.ssh_alias,
         "/usr/bin/python", "-B", "-c", shlex.quote(code), "inventory"],
        data, OpenSshBackend._ssh_environment(), timeout=60, limit=262144,
    )
    if status or stderr:
        raise ValueError("repair_inventory_rejected")
    result = json.loads(stdout)
    if not isinstance(result, dict) or set(result) != {
        "plan", "plan_sha256", "readonly_compatibility_links", "dependency_scope",
        "native_runtime_attestation",
    } or result["plan_sha256"] != repair.digest(result["plan"]):  # type: ignore[no-untyped-call]
        raise ValueError("repair_inventory_binding")
    if result["plan"]["scope"]["profile_sha256"] != repair.digest(  # type: ignore[no-untyped-call]
        json.loads(data)
    ):
        raise ValueError("repair_profile_binding")
    installer.exclusive(str(_local_path(output)), stdout)  # type: ignore[no-untyped-call]
    return {
        "status": "PRIVATE_REPAIR_PLAN_CREATED_NO_AUTHORITY",
        "plan_sha256": result["plan_sha256"],
        "items": len(result["plan"]["records"]),
        "native_runtime_attestation": "NOT_ATTESTED",
        "execution_authorized": False,
        "remote_contact": True,
        "protected_permissions_changed": False,
    }


def install(bundle_path: Path, target: Path, expected: str) -> dict[str, Any]:
    entry = installer.stage_windows if os.name == "nt" else installer.install
    return dict(
        entry(str(_local_path(bundle_path)), str(_local_path(target)), expected)  # type: ignore[no-untyped-call]
    )


def verify(target: Path, expected: str) -> dict[str, object]:
    root = _local_path(target)
    installer.validate(str(root / "runtime" / expected), expected)  # type: ignore[no-untyped-call]
    return {
        "status": "INSTALL_CONTENT_VERIFIED",
        "manifest_sha256": expected,
        "preflight": "NOT_ASSESSED",
        "analysis_qualification": "NOT_ASSESSED",
        "execution_authorized": False,
        "remote_contact": False,
    }


def diagnose_trust(profile: Path, output: Path) -> dict[str, object]:
    """One fixed read-only metadata program; private paths stay in exclusive output."""
    import json
    import shlex
    import shutil

    from cadence_mcp_bridge.operator_transport import run_fixed
    from cadence_mcp_bridge.ssh_backend import OpenSshBackend

    environment, data = load_environment(_local_path(profile))
    executable = shutil.which("ssh.exe")
    if executable is None:
        raise ValueError("OpenSSH unavailable")
    code = files("cadence_mcp_bridge").joinpath("_runner_trust.py").read_text(encoding="utf-8")
    code_status, stdout, stderr = run_fixed(
        [
            executable,
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            "ConnectTimeout=10",
            environment.ssh_alias,
            "/usr/bin/python",
            "-B",
            "-c",
            shlex.quote(code),
        ],
        data,
        OpenSshBackend._ssh_environment(),
    )
    if code_status or stderr:
        raise ValueError("trust_diagnostic_failed")
    result = json.loads(stdout)
    if (
        not isinstance(result, dict)
        or set(result) != {"schema_version", "tools", "diagnosis"}
        or result["schema_version"] != 1
        or type(result["schema_version"]) is not int
        or result.get("diagnosis") != "METADATA_ONLY_NOT_QUALIFICATION"
        or not isinstance(result["tools"], dict)
        or set(result["tools"]) != {"virtuoso", "spectre", "ocean"}
    ):
        raise ValueError("trust_diagnostic_shape")
    for item in result["tools"].values():
        if (
            not isinstance(item, dict)
            or set(item) != {"unsafe_components", "unsafe_count"}
            or type(item["unsafe_count"]) is not int
            or not 0 <= item["unsafe_count"] <= 64
            or not isinstance(item["unsafe_components"], list)
            or len(item["unsafe_components"]) != item["unsafe_count"]
        ):
            raise ValueError("trust_diagnostic_shape")
    installer.exclusive(str(_local_path(output)), stdout)  # type: ignore[no-untyped-call]
    return {
        "status": "TRUST_DIAGNOSTIC_PRIVATE_REPORT_CREATED",
        "unsafe_components": {
            name: result["tools"][name]["unsafe_count"] for name in ("virtuoso", "spectre", "ocean")
        },
        "execution_authorized": False,
        "remote_write": False,
        "protected_permissions_changed": False,
    }


def preflight(bundle_path: Path, expected: str) -> dict[str, object]:
    """Verify current package/bundle and request the exact installed runner preflight."""
    import hashlib
    import shutil
    from uuid import uuid4

    from cadence_mcp_bridge.environments import (
        EnvironmentObservation,
        _closed_json,
        qualify_observation,
    )
    from cadence_mcp_bridge.operator_transport import run_fixed
    from cadence_mcp_bridge.ssh_backend import OpenSshBackend

    root = _local_path(bundle_path)
    manifest, contents, _ = installer.validate(str(root), expected)  # type: ignore[no-untyped-call]
    for name, source in (
        ("runner.py", "_generic_runner.py"),
        ("launcher.py", "_runner_launcher.py"),
        ("probe.py", "_environment_probe.py"),
        ("reservations.py", "_shared_reservations.py"),
    ):
        trusted = files("cadence_mcp_bridge").joinpath(source).read_bytes()
        if name not in contents or contents[name] != trusted:
            raise ValueError("runner_package_binding_mismatch")
    environment, data = load_environment(root / "profile.json")
    executable = shutil.which("ssh.exe")
    if executable is None:
        raise ValueError("OpenSSH missing")
    nonce = uuid4().hex
    argv = [
        executable,
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "ConnectTimeout=10",
        environment.ssh_alias,
        environment.paths.managed_root + "/bin/cadence-runner",
        "preflight",
        expected,
        nonce,
    ]
    code, stdout, stderr = run_fixed(argv, b"", OpenSshBackend._ssh_environment())
    if code or stderr:
        from cadence_mcp_bridge.environments import EnvironmentRejected

        reason = (
            stderr.decode("ascii", errors="replace").strip()
            if len(stderr) < 128
            else "environment_probe_failed"
        )
        raise EnvironmentRejected(reason)
    _closed_json(stdout)
    observation = EnvironmentObservation.model_validate_json(stdout)
    report = qualify_observation(environment, data, observation, nonce)
    report.update(
        runner_manifest_sha256=expected,
        runner_sha256=hashlib.sha256(contents["launcher.py"]).hexdigest(),
        runner_content_scope="exact_selected_manifest_fixed_package_assets",
        resource_identity="declared_host_requires_ledger_attestation",
        execution_authorized=False,
    )
    return report
