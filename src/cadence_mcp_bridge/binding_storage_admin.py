"""Local export of an experimental fixed storage administrator helper; no transport."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from importlib.resources import files
from pathlib import Path
from typing import Any

from cadence_mcp_bridge import _binding_storage_admin as admin
from cadence_mcp_bridge.domain_provisioning import _canonical
from cadence_mcp_bridge.environments import EnvironmentProfile


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()

CATEGORIES = {
    "system_interpreter_and_startup",
    "os_loader_and_libraries",
    "formatter_runtime",
    "loop_and_mount_kernel",
}


def prepare_configuration(
    profile: EnvironmentProfile, facts: dict[str, Any], review: dict[str, Any]
) -> dict[str, Any]:
    """Bind an external review to observed facts; do not infer that review's truth.

    A separately reviewed standard-VM trust assumption remains necessary. These
    shape/hash checks do not prove dependency completeness or authorize execution.
    """
    profile_raw = _canonical(profile.model_dump(mode="json"))
    profile_pin = _sha(profile_raw)
    domain = _sha(_canonical({
        "hostname": profile.host.hostname.lower().rstrip("."),
        "architecture": profile.host.architecture,
    }))
    if (
        facts.get("kind") != "FIXED_STORAGE_PREREQUISITE_FACTS"
        or facts.get("status") != "OBSERVATIONS_ONLY"
        or facts.get("profile_canonical_sha256") != profile_pin
        or facts.get("resource_domain_sha256") != domain
        or facts.get("errors") != []
        or any(facts.get(key) is not False for key in (
            "ready_for_apply", "execution_authorized", "runtime_trust_assessed"
        ))
        or any(type(facts.get(key)) is not int or facts[key] != 0 for key in (
            "eda_starts", "new_simulations", "reserved_bytes", "intentional_remote_writes",
            "system_commands_executed",
        ))
    ):
        raise ValueError("observed_storage_subject_required")
    records = facts.get("records")
    if not isinstance(records, list) or len(records) > 128:
        raise ValueError("bounded_storage_records_required")
    roles = {item["role"]: item for item in records}
    if len(roles) != len(records) or any(
        roles.get(name, {}).get("status") != "MISSING"
        or roles.get(name, {}).get("errno") != 2
        for name in ("stage", "backing-image")
    ):
        raise ValueError("fresh_storage_only_recovery_is_separate")
    if set(review) != {
        "schema_version", "kind", "subject", "review_reference", "trust_categories",
        "reviewed_formatter", "unresolved_dependencies",
    } or type(review["schema_version"]) is not int or review["schema_version"] != 1 or (
        review["kind"] != "STANDARD_VM_STORAGE_ADMIN_EXTERNAL_REVIEW"
        or review["subject"] != {
            "profile_canonical_sha256": profile_pin,
            "resource_domain_sha256": domain,
            "identity_manifest_sha256": facts.get("identity_manifest_sha256"),
            "storage_facts_sha256": _sha(_canonical(facts)),
        }
        or review["unresolved_dependencies"] != []
        or not isinstance(review["review_reference"], str)
        or not 1 <= len(review["review_reference"]) <= 256
    ):
        raise ValueError("external_runtime_review_binding_required")
    categories = review["trust_categories"]
    if not isinstance(categories, list) or len(categories) != len(CATEGORIES) or (
        any(not isinstance(item, dict) or set(item) != {"category", "evidence_sha256"}
            or not isinstance(item["evidence_sha256"], str)
            or re.fullmatch(r"[0-9a-f]{64}", item["evidence_sha256"]) is None
            for item in categories)
        or {item["category"] for item in categories} != CATEGORIES
    ):
        raise ValueError("complete_external_runtime_review_categories_required")
    formatter = review["reviewed_formatter"]
    if not isinstance(formatter, dict) or set(formatter) != {"path", "sha256"} or (
        formatter["path"] not in ("/sbin/mke2fs", "/usr/sbin/mke2fs")
    ):
        raise ValueError("closed_formatter_path")
    role = "mke2fs-sbin" if formatter["path"] == "/sbin/mke2fs" else "mke2fs-usr"
    observed = roles.get(role, {})
    if observed.get("status") != "OBSERVED" or observed.get("sha256") != formatter["sha256"] or (
        observed.get("resolved_path_sha256") != _sha(formatter["path"].encode("ascii"))
        or observed.get("root_owned") is not True or observed.get("shared_write") is not False
        or observed.get("executable") is not True
    ):
        raise ValueError("exact_reviewed_formatter_observation_required")
    configuration = {
        "schema_version": 1,
        "kind": "FIXED_BINDING_STORAGE_ADMIN",
        "hostname": profile.host.hostname,
        "architecture": profile.host.architecture,
        "user": profile.host.user,
        "managed_root": profile.paths.managed_root,
        "resource_domain_sha256": domain,
        "identity_manifest_sha256": facts["identity_manifest_sha256"],
        "mke2fs_sha256": formatter["sha256"],
        "formatter_path": formatter["path"],
        "formatter_nlink": observed.get("metadata", {}).get("nlink"),
        "runtime_review_sha256": _sha(_canonical(review)),
        "disk_floor_bytes": profile.limits.disk_floor_bytes,
        "disk_floor_percent": profile.limits.disk_floor_percent,
    }
    admin.valid_config(configuration)  # type: ignore[no-untyped-call]
    return configuration


def export(
    profile: EnvironmentProfile, facts: dict[str, Any], review: dict[str, Any], output: Path
) -> dict[str, Any]:
    config = prepare_configuration(profile, facts, review)
    source = files("cadence_mcp_bridge").joinpath("_binding_storage_admin.py").read_bytes()
    source = source.replace(b"\r\n", b"\n")
    marker = b"CONFIG_JSON = None  # Replaced only by the local package exporter."
    if source.count(marker) != 1:
        raise ValueError("fixed_admin_resource_shape")
    exported = source.replace(marker, b"CONFIG_JSON = " + repr(_canonical(config)).encode("ascii"))
    # Export is local only; no private VM details enter a package or public PR.
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    manifest = {
        "schema_version": 1,
        "kind": "UNAUTHORIZED_EXPERIMENTAL_STORAGE_ADMIN_EXPORT",
        "helper_sha256": hashlib.sha256(exported).hexdigest(),
        "configuration_sha256": _sha(_canonical(config)),
        "external_review_sha256": config["runtime_review_sha256"],
        "runtime_review_validation_scope": "EXTERNAL_RECORD_BINDING_ONLY",
        "execution_authorized": False,
        "remote_contact": False,
    }
    for name, raw in (("storage-admin.py", exported),
                      ("manifest.private.json", _canonical(manifest)),
                      ("runtime-review.private.json", _canonical(review))):
        with (output / name).open("xb") as stream:
            stream.write(raw)
        (output / name).chmod(0o600)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--facts", type=Path, required=True)
    parser.add_argument("--external-review", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = export(
        EnvironmentProfile.model_validate_json(args.profile.read_bytes()),
        json.loads(args.facts.read_bytes()),
        json.loads(args.external_review.read_bytes()), args.output,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
