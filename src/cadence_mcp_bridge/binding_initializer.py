"""Local-only export of a fixed initializer metadata helper; no remote transport.

An export and its hashes describe code and inputs, not execution authority or
runtime trust. The administrator must separately authorize the exact operation.
"""

from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
import math
import os
import re
import stat
from importlib.resources import files
from pathlib import Path, PurePosixPath
from typing import Any, cast

from cadence_mcp_bridge import _binding_initializer as recipe
from cadence_mcp_bridge import _installation_repair as repair
from cadence_mcp_bridge.binding_observation_bootstrap import _Registration
from cadence_mcp_bridge.binding_observer_operator import (
    _directory_identity,
    _held_output,
    _reserved,
)
from cadence_mcp_bridge.domain_provisioning import _canonical, _closed_document
from cadence_mcp_bridge.environments import EnvironmentProfile
from cadence_mcp_bridge.native_runtime import NativeRegistration, projection
from cadence_mcp_bridge.onboarding import _local_path
from cadence_mcp_bridge.physical_metadata import _load_bundle
from cadence_mcp_bridge.runtime_context import ExecutionContext, load_runtime

RESOURCES = {
    "core": "_installation_repair.py",
    "copying": "_native_copy.py",
    "storage": "_binding_storage_admin.py",
    "recipe": "_binding_initializer.py",
}


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


# Python 2.6 entry: fixed package bytes and frozen configuration only. Input
# contains an exact observed plan, never a source/module/command/target selector.
ENTRY = '''import sys
if __name__ == "__main__":
    if (not sys.flags.ignore_environment or not sys.flags.no_user_site
            or not sys.dont_write_bytecode):
        sys.exit("isolated_python_required")
    entry = sys.path[0] if sys.path else None
    sys.path[:] = [p for p in sys.path if p and p != entry]
import os
if __name__ == "__main__":
    excluded = set((os.path.realpath(os.getcwd()),
                    os.path.realpath(os.path.dirname(os.path.abspath(__file__)))))
    sys.path[:] = [p for p in sys.path if os.path.isabs(p)
                  and os.path.realpath(p) not in excluded]
import base64
import hashlib
import json
import signal
import types

CONFIG = json.loads(base64.b64decode(__CONFIG_LITERAL__).decode("ascii"))
SOURCES = __SOURCE_LITERAL__
PINS = __PINS_LITERAL__

def main():
    if len(sys.argv) not in (2, 3) or sys.argv[1] not in (
            "plan", "postcheck", "apply", "rollback"):
        raise ValueError("closed_initializer_operation")
    operation = sys.argv[1]
    if (operation == "plan") != (len(sys.argv) == 2):
        raise ValueError("independent_exact_plan_digest_required")
    if os.name != "posix" or os.uname()[0] != "Linux" or (
            os.uname()[1] != CONFIG["profile"]["host"]["hostname"]
            or os.uname()[4] != CONFIG["profile"]["host"]["architecture"]):
        raise ValueError("exact_standard_vm_required")
    import pwd
    account = pwd.getpwnam(CONFIG["profile"]["host"]["user"])
    if account.pw_uid == 0 or os.getuid() != os.geteuid() or (
            os.getuid() not in (0, account.pw_uid)):
        raise ValueError("registered_operator_or_administrator_required")
    if operation in ("apply", "rollback") and os.getuid() != 0:
        raise ValueError("explicit_administrator_entry_required")
    decoded = {}
    for name in ("core", "copying", "storage", "recipe"):
        raw = base64.b64decode(SOURCES[name])
        if hashlib.sha256(raw).hexdigest() != PINS[name]:
            raise ValueError("fixed_initializer_source_pin")
        decoded[name] = raw
    loaded = {}
    for name in ("core", "copying", "storage", "recipe"):
        module = types.ModuleType("fixed_initializer_" + name)
        module.__dict__["__package__"] = None
        eval(compile(decoded[name], "fixed_initializer_" + name + ".py", "exec"),
             module.__dict__)
        loaded[name] = module
    core, copying, recipe = loaded["core"], loaded["copying"], loaded["recipe"]
    def timeout(signum, frame):
        raise ValueError("initializer_deadline_retain_partial_evidence")
    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(60)
    if operation == "plan":
        result = recipe.inventory(CONFIG["profile"], CONFIG["registration"], copying, core)
    else:
        raw = sys.stdin.read(core.LIMIT + 1).encode("ascii")
        if len(raw) > core.LIMIT:
            raise ValueError("initializer_request_bound")
        request = json.loads(raw.decode("ascii"))
        if (not isinstance(request, dict) or set(request) != set((
                "plan", "expected_plan_sha256", "operator_authority"))
                or core.canonical(request) != raw
                or request["expected_plan_sha256"] != sys.argv[2]
                or core.digest(request["plan"]) != sys.argv[2]
                or request["plan"].get("profile") != CONFIG["profile"]
                or request["plan"].get("registration") != CONFIG["registration"]):
            raise ValueError("initializer_configuration_and_plan_binding")
        if operation == "postcheck":
            if request["operator_authority"] is not None or os.getuid() != account.pw_uid:
                raise ValueError("ordinary_user_postcheck_only")
            result = recipe.verify_delta(request["plan"], copying, core)
        else:
            if (not isinstance(request["operator_authority"], core.TEXT)
                    or not 1 <= len(request["operator_authority"]) <= 512):
                raise ValueError("explicit_operator_authority_required")
            accounting = recipe.build_accounting(
                CONFIG["profile"], CONFIG["registration"], loaded["storage"])
            try:
                accounting.enter()
                result = recipe.mutate(request, copying, core,
                                       rollback=(operation == "rollback"), accounting=accounting)
            finally:
                accounting.close()
    signal.alarm(0)
    raw = core.canonical(result)
    if len(raw) + 1 > core.LIMIT:
        raise ValueError("initializer_response_bound")
    sys.stdout.write(raw.decode("ascii") + chr(10))

if __name__ == "__main__":
    main()
'''


def helper_bytes(profile: EnvironmentProfile, registration: dict[str, Any]) -> bytes:
    """Freeze validated operator data and exact installed package sources locally."""
    registered = _Registration.model_validate_json(_canonical(registration))
    profile_value = profile.model_dump(mode="json")
    if registered.environment_sha256 != _sha(_canonical(profile_value)):
        raise ValueError("initializer_environment_binding")
    sources = {
        name: files("cadence_mcp_bridge").joinpath(resource).read_bytes().replace(b"\r\n", b"\n")
        for name, resource in RESOURCES.items()
    }
    if any(not raw or len(raw) > 262_144 for raw in sources.values()):
        raise ValueError("initializer_resource_bound")
    config = {"profile": profile_value, "registration": registered.model_dump(mode="json")}
    # Configuration/source text is represented only as data literals. The
    # generated helper has no path/source argument or unrestricted transport.
    source = ENTRY.replace("__CONFIG_LITERAL__", repr(base64.b64encode(
        _canonical(config)
    ).decode("ascii")))
    source = source.replace("__SOURCE_LITERAL__", repr({
        name: base64.b64encode(raw).decode("ascii") for name, raw in sources.items()
    }))
    source = source.replace("__PINS_LITERAL__", repr({
        name: _sha(raw) for name, raw in sources.items()
    }))
    return source.encode("ascii")


def export(bundle: Path, manifest_sha256: str, output: Path) -> dict[str, Any]:
    """Authenticate the installed bundle, then export without any VM contact."""
    assets, _ = _load_bundle(bundle, manifest_sha256)
    profile = EnvironmentProfile.model_validate_json(assets["profile.json"])
    registration = json.loads(assets["registration.json"])
    raw = helper_bytes(profile, registration)
    manifest = {
        "schema_version": 1,
        "kind": "UNAUTHORIZED_FIXED_INITIALIZER_HELPER_EXPORT",
        "helper_sha256": _sha(raw),
        "native_manifest_sha256": manifest_sha256,
        "profile_canonical_sha256": _sha(_canonical(profile.model_dump(mode="json"))),
        "registration_canonical_sha256": _sha(_canonical(registration)),
        "runtime_behavior_attested": False,
        "execution_authorized": False,
        "remote_contact": False,
    }
    output = _local_path(output)
    if output.is_relative_to(_local_path(bundle)):
        raise ValueError("initializer_export_must_not_change_bundle")
    parents = {path: _directory_identity(path) for path in output.parents}
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    with _held_output(output, parents) as (directory_fd, guard):
        for name, value in (("initializer-admin.py", raw),
                            ("manifest.private.json", _canonical(manifest))):
            guard()
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            fd = (os.open(output / name, flags, 0o600) if directory_fd is None
                  else os.open(name, flags, 0o600, dir_fd=directory_fd))
            with os.fdopen(fd, "wb") as stream:
                guard()
                stream.write(value)
                stream.flush()
                os.fsync(stream.fileno())
                guard()
    return manifest


def _pinned_document(path: Path, expected: str) -> tuple[bytes, dict[str, Any]]:
    """Read exact retained evidence, never a current filesystem baseline."""
    if not isinstance(expected, str) or re.fullmatch(r"[0-9a-f]{64}", expected) is None:
        raise ValueError("initializer_evidence_digest_required")
    source = _local_path(path)
    before = source.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        raise ValueError("initializer_evidence_regular_file_required")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    with os.fdopen(os.open(source, flags), "rb") as stream:
        opened = os.fstat(stream.fileno())
        raw = stream.read(repair.LIMIT + 1)
        finished = os.fstat(stream.fileno())
    after = source.lstat()

    def identity(info: os.stat_result) -> tuple[int, ...]:
        common = (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
                  info.st_nlink, info.st_size, info.st_mtime_ns)
        # Windows path stat and descriptor stat may expose creation and change
        # time respectively as ctime. Compare each API's time before/after below;
        # POSIX additionally requires the same ctime across both observations.
        return common if os.name == "nt" else (*common, info.st_ctime_ns)

    if len(raw) > repair.LIMIT or any(identity(value) != identity(before)
                                     for value in (opened, finished, after)) or (
        before.st_ctime_ns != after.st_ctime_ns or opened.st_ctime_ns != finished.st_ctime_ns
    ):
        raise ValueError("initializer_evidence_drift_or_bound")
    if _sha(raw) != expected:
        raise ValueError("initializer_evidence_digest_mismatch")
    _closed_document(raw, max_bytes=repair.LIMIT)
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("initializer_evidence_object_required")
    return raw, value


def _snapshot_projection(snapshot: dict[str, Any]) -> list[list[Any]]:
    """Authenticate the retained whole-library metadata and content arrays."""
    if set(snapshot) != {"schema_version", "tree_sha256", "content_sha256", "entries",
                         "bytes", "metadata"} or snapshot["schema_version"] != 2:
        raise ValueError("initializer_rebind_snapshot_shape")
    metadata = snapshot["metadata"]
    if not isinstance(metadata, list) or not 1 <= len(metadata) <= 4096:
        raise ValueError("initializer_rebind_snapshot_bound")
    seen: set[str] = set()
    directories: set[str] = set()
    content: list[list[Any]] = []
    total = 0
    for row in metadata:
        if not isinstance(row, list) or not row or row[0] not in ("file", "directory") or (
            len(row) != (9 if row[0] == "file" else 6)
        ):
            raise ValueError("initializer_rebind_metadata_shape")
        relative = row[1]
        if not isinstance(relative, str) or relative in seen or (
            relative and (str(PurePosixPath(relative)) != relative
                          or PurePosixPath(relative).is_absolute()
                          or ".." in PurePosixPath(relative).parts)
        ) or (not seen and (relative != "" or row[0] != "directory")):
            raise ValueError("initializer_rebind_metadata_path")
        if relative:
            parent = str(PurePosixPath(relative).parent)
            if ("" if parent == "." else parent) not in directories:
                raise ValueError("initializer_rebind_metadata_parent")
        if any(type(value) is not int or value < 0 for value in row[2:5]) or (
            row[2] > 0o7777 or not isinstance(row[5], str)
            or re.fullmatch(r"-?[0-9]+\.[0-9]{9}", row[5]) is None
        ):
            raise ValueError("initializer_rebind_metadata_fields")
        if row[0] == "directory":
            directories.add(relative)
            content.append(["directory", relative])
        else:
            if type(row[6]) is not int or row[6] < 0 or not isinstance(row[7], str) or (
                re.fullmatch(r"[0-9a-f]{64}", row[7]) is None
                or type(row[8]) is not int or row[8] < 1
            ):
                raise ValueError("initializer_rebind_file_fields")
            content.append(["file", relative, row[6], row[7]])
            total += row[6]
        seen.add(relative)
    if type(snapshot["entries"]) is not int or snapshot["entries"] != len(metadata) or (
        type(snapshot["bytes"]) is not int or snapshot["bytes"] != total
        or total > recipe.BYTES or _sha(_canonical(metadata)) != snapshot["tree_sha256"]
        or _sha(_canonical(content)) != snapshot["content_sha256"]
    ):
        raise ValueError("initializer_rebind_snapshot_digest")
    return copy.deepcopy(metadata)


def _expected_transitions(
    plan: dict[str, Any], profile: dict[str, Any], registration: dict[str, Any],
) -> list[dict[str, Any]]:
    """Derive replacements from the retained before-state, not reported new pins."""
    if set(plan) != {"schema_version", "scope", "records", "operation", "content_authority",
                     "execution_authorized", "recipe_id", "profile", "registration",
                     "library_snapshots", "library_namespace", "ancestor_acl_records",
                     "runtime_trust_assessed", "registration_updated"} or (
        type(plan["schema_version"]) is not int or plan["schema_version"] != 2
        or plan["recipe_id"] != recipe.RECIPE or plan["profile"] != profile
        or plan["registration"] != registration
        or plan["operation"] != "remove_022_and_default_acl_writes"
        or plan["content_authority"] != "NONE"
        or any(plan[field] is not False for field in (
            "execution_authorized", "runtime_trust_assessed", "registration_updated"))
    ):
        raise ValueError("initializer_rebind_original_plan_binding")
    # The frozen Python 2.6 recipe deliberately has no typing-only dependency.
    dynamic_recipe: Any = recipe
    dynamic_repair: Any = repair
    libraries = dynamic_recipe._libraries(profile, registration, repair)
    snapshots = plan["library_snapshots"]
    if not isinstance(snapshots, list) or len(snapshots) != len(libraries) or any(
        not isinstance(pair, list) or len(pair) != 2 or pair[0] != library
        for pair, library in zip(snapshots, libraries, strict=True)
    ):
        raise ValueError("initializer_rebind_library_inventory")
    metadata = [_snapshot_projection(pair[1]) for pair in snapshots]
    if sum(pair[1]["entries"] for pair in snapshots) > recipe.ENTRIES or (
        sum(pair[1]["bytes"] for pair in snapshots) > recipe.BYTES
    ) or any(pair[1]["tree_sha256"] != pair[0]["tree_sha256"] for pair in snapshots):
        raise ValueError("initializer_rebind_registered_snapshot")
    roots, paths = dynamic_recipe._selected(profile, snapshots, repair)
    if plan["scope"] != dict(installation_roots=roots, paths=paths, links=[],
        profile_sha256=_sha(_canonical(profile)),
        resource_lock=profile["paths"]["managed_root"] + "/run.lock"):
        raise ValueError("initializer_rebind_exact_scope")
    records = plan["records"]
    if not isinstance(records, list) or len(records) != len(paths) or (
        [row.get("path") for row in records if isinstance(row, dict)] != paths
    ):
        raise ValueError("initializer_rebind_selected_records")
    selected = {row["path"]: row for row in records}
    transitions = []
    for (library, before), after in zip(snapshots, metadata, strict=True):
        for row in after:
            target = selected.get(library["path"] + ("/" + row[1] if row[1] else ""))
            if target is None:
                continue
            stamp = target.get("mtime")
            if row[0] == "file" and (not isinstance(stamp, str) or (
                not math.isfinite(float(stamp)) or f"{float(stamp):.9f}" != row[5]
            )):
                raise ValueError("initializer_rebind_original_timestamp")
            if any(type(target.get(key)) is not int or target[key] < 0
                   for key in ("mode", "after_mode", "uid", "gid", "dev", "ino")):
                raise ValueError("initializer_rebind_selected_identity")
            if any(target.get(key) != expected for key, expected in {
                "kind": row[0], "mode": row[2], "uid": row[3], "gid": row[4],
                "size": row[6] if row[0] == "file" else None,
                "sha256": row[7] if row[0] == "file" else None,
                "after_mode": row[2] & ~0o022,
                "reason": "remove_shared_code_write_preserve_content_owner_rx",
            }.items()) or (row[0] == "directory" and stamp is not None) or (
                row[2] & 0o7000 or (row[0] == "file" and row[8] != 1)
            ) or not isinstance(target.get("acl"), str) or (
                not isinstance(target.get("after_acl"), str)
            ) or (
                dynamic_repair.normalize_acl(target.get("after_acl")) !=
                dynamic_repair.normalize_acl(dynamic_repair.restricted_acl(target.get("acl")))
            ):
                raise ValueError("initializer_rebind_only_permitted_mode_acl_delta")
            row[2] = target["after_mode"]
        transitions.append(dict(name=library["name"], path=library["path"],
            original_tree_sha256=before["tree_sha256"],
            current_tree_sha256=_sha(_canonical(after)), content_sha256=before["content_sha256"]))
    return transitions


def prospective(
    context: ExecutionContext, bundle: Path, manifest_sha256: str,
    native_registration_path: Path, native_registration_sha256: str,
    plan_path: Path, plan_sha256: str, postcheck_path: Path, postcheck_sha256: str,
    output: Path, *, administrator_result_path: Path | None = None,
    administrator_result_sha256: str | None = None,
) -> dict[str, Any]:
    """Export an uninstalled proposal; retained stdout cannot authenticate root.

    The plan file is the canonical inner ``plan`` object from the fixed helper.
    Postcheck and optional administrator-result pins cover their exact file bytes,
    including a terminal newline. Nothing here reads or changes the VM or ledger.
    """
    assets, _ = _load_bundle(bundle, manifest_sha256)
    original_raw, original = _pinned_document(native_registration_path, native_registration_sha256)
    registration = NativeRegistration.model_validate_json(original_raw)
    compiled = cast(dict[str, Any], projection(context, registration))
    profile = EnvironmentProfile.model_validate_json(assets["profile.json"]).model_dump(mode="json")
    if compiled != json.loads(assets["registration.json"]) or (
        profile != context.contracts.environment.model_dump(mode="json")
    ):
        raise ValueError("initializer_rebind_original_projection_binding")
    plan_raw, plan = _pinned_document(plan_path, plan_sha256)
    if plan_raw != _canonical(plan):
        raise ValueError("initializer_rebind_canonical_inner_plan_required")
    transitions = _expected_transitions(plan, profile, compiled)
    _, postcheck = _pinned_document(postcheck_path, postcheck_sha256)
    expected_postcheck = dict(schema_version=1, kind="INITIALIZER_ALLOWED_METADATA_DELTA",
        plan_sha256=plan_sha256, rollback=False, selected_targets=len(plan["records"]),
        libraries=transitions, content_preserved=True, owner_group_preserved=True,
        registration_updated=False, runtime_trust_assessed=False, execution_authorized=False,
        receipt_provenance_assessed=False)
    if _canonical(postcheck) != _canonical(expected_postcheck):
        raise ValueError("initializer_rebind_successful_exact_postcheck_required")
    if (administrator_result_path is None) != (administrator_result_sha256 is None):
        raise ValueError("initializer_rebind_administrator_result_pin_required")
    admin = None
    if administrator_result_path is not None and administrator_result_sha256 is not None:
        _, admin = _pinned_document(administrator_result_path, administrator_result_sha256)
        wanted = {**expected_postcheck, "receipt_provenance_assessed": True,
                  "metadata_changes_explicit": True, "observed_plan_sha256": plan_sha256}
        extra = {"changed", "applied_plan_receipt_sha256"}
        if set(admin) != set(wanted) | extra or any(admin[key] != value
                                                  for key, value in wanted.items()) or (
            type(admin["changed"]) is not int or not 0 <= admin["changed"] <= len(plan["records"])
            or re.fullmatch(r"[0-9a-f]{64}", str(admin["applied_plan_receipt_sha256"])) is None
        ):
            raise ValueError("initializer_rebind_administrator_result_correlation")
    revised = copy.deepcopy(original)
    replacements = {(row["name"], row["path"]): row["current_tree_sha256"] for row in transitions}
    for route in revised["routes"]:
        for library in route["libraries"]:
            library["tree_sha256"] = replacements[(library["name"], library["path"])]
    prospective_registration = NativeRegistration.model_validate_json(_canonical(revised))
    predicted = projection(context, prospective_registration)
    expected_compiled = copy.deepcopy(compiled)
    for route in expected_compiled["routes"]:
        for library in route["libraries"]:
            library["tree_sha256"] = replacements[(library["name"], library["path"])]
    if predicted != expected_compiled:
        raise ValueError("initializer_rebind_nonlibrary_projection_drift")
    native_raw, projected_raw = _canonical(revised), _canonical(predicted)
    report = dict(schema_version=1, status="PROSPECTIVE_NOT_INSTALLED_NOT_AUTHORIZED",
        native_manifest_sha256=manifest_sha256,
        original_native_registration_sha256=native_registration_sha256,
        original_projected_registration_sha256=_sha(assets["registration.json"]),
        plan_sha256=plan_sha256, postcheck_input_sha256=postcheck_sha256,
        administrator_result_input_sha256=administrator_result_sha256,
        reported_applied_plan_receipt_sha256=(
            admin["applied_plan_receipt_sha256"] if admin else None),
        administrator_result_authentication="NOT_ASSESSED_RETAINED_STDOUT_ONLY",
        receipt_provenance_assessed=False, external_review_required=True,
        identity_manifest_sha256=registration.identity_manifest_sha256,
        resource_domain_sha256=context.resource_domain_sha256,
        context_sha256=context.context_sha256, libraries=transitions,
        prospective_native_registration_sha256=_sha(native_raw),
        prospective_projected_registration_sha256=_sha(projected_raw),
        original_preserved=True, registration_updated=False, installed=False,
        runtime_trust_assessed=False, qualification_established=False,
        execution_authorized=False, remote_contact=False,
        ledger_modified=False, new_simulations=0, new_reservations=0)
    output = _local_path(output)
    reserved = _reserved(context, native_registration_path) | {
        _local_path(plan_path), _local_path(postcheck_path), _local_path(bundle),
    }
    if administrator_result_path is not None:
        reserved.add(_local_path(administrator_result_path))
    if output in reserved or output.is_relative_to(_local_path(bundle)) or (
        output.is_relative_to(_local_path(context.resource_state_root))
    ):
        raise ValueError("initializer_rebind_output_protected")
    # Validate pinned inputs once more before publication; a changed evidence
    # file never silently becomes the replacement baseline.
    for path, pin in ((native_registration_path, native_registration_sha256),
                      (plan_path, plan_sha256), (postcheck_path, postcheck_sha256)):
        _pinned_document(path, pin)
    if administrator_result_path is not None and administrator_result_sha256 is not None:
        _pinned_document(administrator_result_path, administrator_result_sha256)
    _load_bundle(bundle, manifest_sha256)
    parents = {path: _directory_identity(path) for path in output.parents}
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    with _held_output(output, parents) as (directory_fd, guard):
        for name, raw in (("native-registration.prospective.json", native_raw),
                          ("projected-registration.prospective.json", projected_raw),
                          ("rebind-report.private.json", _canonical(report))):
            guard()
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            fd = (os.open(output / name, flags, 0o600) if directory_fd is None else
                  os.open(name, flags, 0o600, dir_fd=directory_fd))
            with os.fdopen(fd, "wb") as stream:
                guard()
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
                guard()
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prospective", action="store_true",
                        help="Export an uninstalled, unauthorized registration proposal only.")
    parser.add_argument("--runtime-settings", type=Path)
    parser.add_argument("--context-id")
    for name in ("native-registration", "plan", "postcheck", "administrator-result"):
        parser.add_argument("--" + name, type=Path)
        parser.add_argument("--" + name + "-sha256")
    args = parser.parse_args()
    options = (args.runtime_settings, args.context_id, args.native_registration,
               args.native_registration_sha256, args.plan, args.plan_sha256,
               args.postcheck, args.postcheck_sha256)
    if args.prospective:
        if any(value is None for value in options):
            parser.error("prospective export requires runtime, context and all exact evidence pins")
        contexts = [context for context in load_runtime(args.runtime_settings)
                    if context.binding.context_id == args.context_id]
        if len(contexts) != 1:
            parser.error("exactly one existing runtime context is required")
        result = prospective(contexts[0], args.bundle, args.manifest_sha256,
            args.native_registration, args.native_registration_sha256, args.plan, args.plan_sha256,
            args.postcheck, args.postcheck_sha256, args.output,
            administrator_result_path=args.administrator_result,
            administrator_result_sha256=args.administrator_result_sha256)
    else:
        if any(value is not None for value in (*options, args.administrator_result,
                                               args.administrator_result_sha256)):
            parser.error("prospective evidence options require --prospective")
        result = export(args.bundle, args.manifest_sha256, args.output)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
