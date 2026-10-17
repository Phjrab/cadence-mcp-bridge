"""Fixed one-shot filesystem metadata collector; Python2.6, no EDA invocation."""

# mypy: ignore-errors
import hashlib
import json
import os
import re
import stat
import time

LIMIT = 1048576
ENTRY_LIMIT = 128
FOLLOWUP_LIMIT = 10
INITIAL_COLLECTOR_SHA256 = "42da5bd7a1bee41176e0578dc5e04c438b618735c667566db454421b7d6ff15d"
try:
    TEXT = (basestring,)  # noqa: F821
except NameError:
    TEXT = (str,)


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")


def digest(value):
    return hashlib.sha256(value).hexdigest()


def inside(child, parent):
    return child == parent or child.startswith(parent + "/")


def targets(profile, registration):
    """Only registered installation roots/libraries and the three bound tools."""
    protected = profile["paths"]["protected_roots"]
    tools = sorted(set(item["path"] for item in profile["tools"].values()))
    installations = sorted(
        set(root for root in protected if any(inside(tool, root) for tool in tools))
    )
    if not installations:
        raise ValueError("physical_installation_binding_missing")
    libraries = sorted(
        set(
            item["path"]
            for route in registration["routes"]
            for item in route["libraries"]
            if any(inside(item["path"], root) for root in installations)
        )
    )
    # Source circuits/states are never enumerated. Libraries outside installation
    # roots do not become physical targets merely because they are registered.
    roots = sorted(set(installations + libraries))
    if len(roots) > 16 or any(root == "/" for root in roots):
        raise ValueError("physical_target_bound")
    return roots, tools


def metadata(info):
    return {
        "device": info.st_dev,
        "inode": info.st_ino,
        "mode": info.st_mode,
        "uid": info.st_uid,
        "gid": info.st_gid,
        "nlink": info.st_nlink,
        "size": info.st_size,
        # Python2.6 JSON float rendering differs from modern Python. Round-trip
        # strings preserve the observed binary64 value and cross-host digests.
        "mtime": "%.17g" % info.st_mtime,  # noqa: UP031
        "ctime": "%.17g" % info.st_ctime,  # noqa: UP031
    }


def chain(path, roots):
    """Track contained links and reject writable/untrusted ancestors."""
    result = []
    current = os.path.dirname(path)
    while True:
        info = os.lstat(current)
        resolved = os.path.realpath(current)
        if stat.S_ISLNK(info.st_mode):
            if not any(inside(current, root) and inside(resolved, root) for root in roots):
                raise ValueError("physical_ancestor_link_escape")
        elif not stat.S_ISDIR(info.st_mode):
            raise ValueError("physical_ancestor_kind")
        target = os.stat(current)
        if (
            not stat.S_ISDIR(target.st_mode)
            or target.st_uid not in (0, os.getuid())
            or target.st_mode & 18
        ):
            raise ValueError("physical_untrusted_ancestor:" + digest(current.encode("utf-8")))
        result.append((current, metadata(info), resolved, metadata(target)))
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return result


def observe(path, roots):
    ancestors = chain(path, roots)
    info = os.lstat(path)
    kind = (
        "directory"
        if stat.S_ISDIR(info.st_mode)
        else "regular"
        if stat.S_ISREG(info.st_mode)
        else "symlink"
        if stat.S_ISLNK(info.st_mode)
        else "other"
    )
    if kind == "other":
        raise ValueError("physical_special_file")
    resolved = os.path.realpath(path)
    if not any(inside(resolved, root) for root in roots):
        raise ValueError("physical_link_escape")
    target_info = os.stat(path)
    if not (stat.S_ISREG(target_info.st_mode) or stat.S_ISDIR(target_info.st_mode)):
        raise ValueError("physical_special_target")
    target_chain = chain(resolved, roots)
    value = {
        "path": path,
        "kind": kind,
        "metadata": metadata(info),
        "resolved": resolved,
        "target_metadata": metadata(target_info),
        "ancestors": ancestors,
        "target_ancestors": target_chain,
        "target_shared_write": bool(target_info.st_mode & 18),
        "target_owner_trusted": target_info.st_uid in (0, os.getuid()),
    }
    # Content is deliberately not opened. A metadata digest is not a binary hash.
    value["metadata_sha256"] = digest(canonical(value))
    return value


def enumerate_targets(profile, registration):
    roots, tools = targets(profile, registration)
    chosen = set(tools + roots)
    listings = {}
    # The outer installation namespace is inventoried one level deep. Nested
    # registered libraries are exact metadata leaves, not a search through cells.
    enumeration_roots = [
        root for root in roots if not any(other != root and inside(root, other) for other in roots)
    ]
    for root in enumeration_roots:
        before = observe(root, roots)
        if before["kind"] != "directory" or before["target_shared_write"]:
            raise ValueError("physical_root_untrusted")
        names = []
        # No recursion: only direct children of the already bound roots.
        # listdir is bounded by the directory's observed size and final count;
        # pathological directories reject before enumeration.
        if before["metadata"]["size"] > 65536:
            raise ValueError("physical_directory_bound")
        for name in os.listdir(root):
            if (
                not name
                or len(name) > 255
                or "/" in name
                or name in (".", "..")
                or any(ord(char) < 32 or ord(char) > 126 for char in name)
            ):
                raise ValueError("physical_entry_name")
            names.append(name)
            chosen.add(root + "/" + name)
            if len(chosen) > ENTRY_LIMIT:
                raise ValueError("physical_entry_bound")
        listings[root] = sorted(names)
        if observe(root, roots) != before:
            raise ValueError("physical_directory_drift")
    if len(chosen) > ENTRY_LIMIT:
        raise ValueError("physical_entry_bound")
    return roots, sorted(chosen), listings


def same_listings(listings):
    for path, names in listings.items():
        if sorted(os.listdir(path)) != names:
            raise ValueError("physical_namespace_drift")


def validate_followup(value, profile_sha, manifest_sha):
    """Closed operator allowance; source/plan/alias changes cannot add slots."""
    if not isinstance(value, dict) or set(value) != set(("authorization", "slot", "invocation_id")):
        raise ValueError("physical_followup_shape")
    grant = value["authorization"]
    fields = (
        "schema_version",
        "kind",
        "max_additional_attempts",
        "profile_sha256",
        "manifest_sha256",
        "predecessor_collector_sha256",
        "predecessor_plan_sha256",
        "predecessor_host_request_sha256",
        "predecessor_remote_request_sha256",
    )
    if not isinstance(grant, dict) or set(grant) != set(fields):
        raise ValueError("physical_followup_authorization")
    if (
        type(grant["schema_version"]) is not int
        or grant["schema_version"] != 1
        or grant["kind"] != "OPERATOR_APPROVED_PHYSICAL_METADATA_FOLLOWUP_V1"
        or type(grant["max_additional_attempts"]) is not int
        or not 1 <= grant["max_additional_attempts"] <= FOLLOWUP_LIMIT
        or type(value["slot"]) is not int
        or not 1 <= value["slot"] <= grant["max_additional_attempts"]
        or grant["profile_sha256"] != profile_sha
        or grant["manifest_sha256"] != manifest_sha
    ):
        raise ValueError("physical_followup_binding")
    for key in fields:
        if key.endswith("_sha256") and (
            not isinstance(grant[key], TEXT)
            or re.match(r"^[0-9a-f]{64}\Z", grant[key]) is None
        ):
            raise ValueError("physical_followup_digest")
    nonce = value["invocation_id"]
    if (
        not isinstance(nonce, TEXT)
        or re.match(r"^[0-9a-f]{32}\Z", nonce) is None
    ):
        raise ValueError("physical_followup_invocation")
    return grant


def predecessor(root, grant, setup):
    directory = root + "/physical-metadata-v1/" + grant["predecessor_collector_sha256"]
    setup.private(root + "/physical-metadata-v1", True)
    setup.private(directory, True)
    before = metadata(os.lstat(directory))
    if set(os.listdir(directory)) != set(("collector.py", "request.json")):
        raise ValueError("physical_predecessor_not_incomplete")
    source = setup.read(directory + "/collector.py")
    raw = setup.read(directory + "/request.json")
    value = setup.closed(raw)
    if (
        digest(source) != grant["predecessor_collector_sha256"]
        or set(value) != set(("operation", "manifest_sha256", "collector_sha256", "request_sha256"))
        or value["operation"] != "physical-metadata-once-v1"
        or value["manifest_sha256"] != grant["manifest_sha256"]
        or value["collector_sha256"] != grant["predecessor_collector_sha256"]
        or value["request_sha256"] != grant["predecessor_remote_request_sha256"]
    ):
        raise ValueError("physical_predecessor_binding")
    if metadata(os.lstat(directory)) != before:
        raise ValueError("physical_predecessor_namespace_drift")
    return (
        before,
        source,
        raw,
        setup.metadata(directory + "/collector.py"),
        setup.metadata(directory + "/request.json"),
    )


def run(request, setup, assets, known, collector_source):
    """One source-hash stage+query under the existing lifetime resource lock."""
    if os.name != "posix" or os.getuid() == 0:
        raise ValueError("physical_normal_user_required")
    followup = request.get("operation") == "physical-metadata-followup-v1"
    if set(request) != set(
        ("schema_version", "operation", "manifest_sha256", "files")
        + (("followup",) if followup else ())
    ):
        raise ValueError("physical_request_shape")
    if type(request["schema_version"]) is not int or request["schema_version"] != 1:
        raise ValueError("physical_request_version")
    if request["operation"] not in ("physical-metadata-once-v1", "physical-metadata-followup-v1"):
        raise ValueError("physical_fixed_operation")
    if not followup and digest(collector_source) != INITIAL_COLLECTOR_SHA256:
        raise ValueError("physical_initial_collection_retired_use_explicit_followup")
    expected = request["manifest_sha256"]
    manifest, profile, registration = setup.inventory(assets, expected, known)
    grant = (
        validate_followup(request["followup"], digest(assets["profile.json"]), expected)
        if followup
        else None
    )
    accounting, installer, probe, confirmation = setup.modules(assets)
    probe.validate_profile(profile)
    root, binding, username, uid = confirmation.domain(
        profile, registration["identity_manifest_sha256"]
    )
    with accounting.ReservationSession(root) as session:
        confirmation.domain(profile, registration["identity_manifest_sha256"])
        before, records = session.observe(binding)
        installed = root + "/runtime/" + expected
        setup.private(installed, True)
        if set(os.listdir(installed)) != set(assets):
            raise ValueError("physical_runtime_inventory")
        for name, raw in assets.items():
            if setup.read(installed + "/" + name) != raw:
                raise ValueError("physical_runtime_drift")
        control_names = ("active-native-provider.json", accounting.LEDGER)
        controls = dict((name, setup.read(root + "/" + name)) for name in control_names)
        control_metadata = dict((name, setup.metadata(root + "/" + name)) for name in control_names)
        if setup.closed(controls["active-native-provider.json"])["manifest_sha256"] != expected:
            raise ValueError("physical_inactive_runtime")
        source_sha = digest(collector_source)
        prior = predecessor(root, grant, setup) if followup else None
        parent = root + ("/physical-metadata-followup-v1" if followup else "/physical-metadata-v1")
        setup.directory(parent, accounting)
        if followup and any(
            name not in ["attempt-" + str(n).zfill(2) for n in range(1, FOLLOWUP_LIMIT + 1)]
            for name in os.listdir(parent)
        ):
            raise ValueError("physical_followup_namespace")
        suffix = "attempt-" + str(request["followup"]["slot"]).zfill(2) if followup else source_sha
        destination = parent + "/" + suffix
        # This is the one-shot claim. It remains on failure; no retry/removal.
        os.mkdir(destination, 448)
        accounting.sync_directory(parent)
        installer.exclusive(destination + "/collector.py", collector_source)
        claim = canonical(
            {
                "operation": request["operation"],
                "manifest_sha256": expected,
                "collector_sha256": source_sha,
                "request_sha256": digest(canonical(request)),
            }
        )
        if followup:
            claim = canonical(
                {
                    "operation": request["operation"],
                    "manifest_sha256": expected,
                    "collector_sha256": source_sha,
                    "request_sha256": digest(canonical(request)),
                    "followup": request["followup"],
                }
            )
        installer.exclusive(destination + "/request.json", claim)
        stage_names = sorted(os.listdir(destination))
        started = time.time()
        roots, paths, listings = enumerate_targets(profile, registration)
        observations = [observe(path, roots) for path in paths]
        session.check()
        same_listings(listings)
        if [observe(path, roots) for path in paths] != observations:
            raise ValueError("physical_metadata_drift")
        if time.time() - started > 45:
            raise ValueError("physical_read_deadline")
        confirmation.domain(profile, registration["identity_manifest_sha256"])
        after, records = session.observe(binding)
        if (
            after != before
            or any(setup.read(root + "/" + name) != raw for name, raw in controls.items())
            or any(
                setup.metadata(root + "/" + name) != value
                for name, value in control_metadata.items()
            )
        ):
            raise ValueError("physical_protected_control_drift")
        if set(os.listdir(installed)) != set(assets) or any(
            setup.read(installed + "/" + name) != raw for name, raw in assets.items()
        ):
            raise ValueError("physical_runtime_drift")
        if (
            sorted(os.listdir(destination)) != stage_names
            or setup.read(destination + "/collector.py") != collector_source
            or setup.read(destination + "/request.json") != claim
        ):
            raise ValueError("physical_stage_drift")
        if followup and predecessor(root, grant, setup) != prior:
            raise ValueError("physical_predecessor_drift")
        result = {
            "schema_version": 1,
            "status": "PHYSICAL_METADATA_OBSERVED",
            "manifest_sha256": expected,
            "collector_sha256": source_sha,
            "profile_sha256": manifest["profile_sha256"],
            "pdk_sha256": registration["pdk_sha256"],
            "observed_at_epoch": time.time(),
            "operator_uid": uid,
            "counter_before": before,
            "counter_after": after,
            "root_count": len(roots),
            "entry_count": len(observations),
            "entries": observations,
            "metadata_unchanged": True,
            "metadata_scope": "lstat_identity_mode_size_mtime_ctime_excludes_atime",
            "license_assessed": False,
            "physical_execution_qualified": False,
            "candidate_file_contents_read": False,
            "new_attempts": 0,
            "new_reserved_bytes": 0,
            "new_extractions": 0,
            "stage_files_created": 3,
        }
        if followup:
            result["followup_slot"] = request["followup"]["slot"]
            result["followup_authorization_sha256"] = digest(canonical(grant))
        if len(canonical(result)) > LIMIT:
            raise ValueError("physical_output_bound")
        # Completion receipt is additional evidence, never execution authority.
        installer.exclusive(destination + "/receipt.json", canonical(result))
        accounting.sync_directory(destination)
        session.check()
        return result
