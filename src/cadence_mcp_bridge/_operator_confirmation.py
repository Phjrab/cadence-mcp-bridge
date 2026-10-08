"""Explicit OS-operator confirmation; fixed stdin contract, no EDA or reservation.

The reference records actual human authority. This file/plan cannot manufacture
that authority. Import, doctor, server startup and inspection never confirm.
"""

# mypy: ignore-errors
import hashlib
import json
import os
import re
import stat
import sys
import time
from decimal import Decimal

try:
    STRING_TYPES = (basestring,)
except NameError:
    STRING_TYPES = (str,)

LIMIT = 262144
MEMBERS = ("confirmation.py", "reservations.py", "installer.py", "probe.py")
KIND = "STANDARD_VM_OPERATOR_CONFIRMATION_HELPER"
GRANT_KEYS = (
    "schema_version",
    "grant_id",
    "authorization_source",
    "resource_domain_sha256",
    "runner_sha256",
    "ledger_ref",
    "environment_sha256",
    "design_sha256",
    "pdk_sha256",
    "design_ids",
    "analyses",
    "actions",
    "numeric_regions",
    "attempt_limit",
    "result_reserved_bytes_limit",
    "valid_from_unix",
    "valid_until_unix",
    "status",
)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "ascii"
    )


def digest(value):
    return hashlib.sha256(value).hexdigest()


def closed(data):
    if len(data) > LIMIT:
        raise ValueError("confirmation_input_limit")
    value = json.loads(data.decode("ascii"))
    if canonical(value) != data:
        raise ValueError("confirmation_noncanonical")
    return value


def matches(pattern, value):
    try:
        strings = (basestring,)
    except NameError:
        strings = (str,)
    match = re.match(pattern, value) if isinstance(value, strings) else None
    return match is not None and match.end() == len(value)


def integer(value):
    try:
        integers = (int, long)
    except NameError:
        integers = (int,)
    return type(value) in integers


def private(path, directory=False, ancestor=False):
    if os.path.realpath(path) != os.path.abspath(path):
        raise ValueError("confirmation_linked_path")
    info = os.lstat(path)
    kind = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    if not kind or (not directory and info.st_nlink != 1):
        raise ValueError("confirmation_file_type")
    if os.name != "nt":
        owners = (0, os.getuid()) if ancestor else (os.getuid(),)
        forbidden = 18 if ancestor else 63
        if info.st_uid not in owners or info.st_mode & forbidden:
            raise ValueError("confirmation_permissions")
    return info


def read_private(path):
    info = private(path)
    stream = open(path, "rb")
    try:
        before = os.fstat(stream.fileno())
        data = stream.read(LIMIT + 1)
        after = private(path)
        if (
            (info.st_dev, info.st_ino) != (before.st_dev, before.st_ino)
            or (before.st_dev, before.st_ino, before.st_size, before.st_mtime)
            != (after.st_dev, after.st_ino, after.st_size, after.st_mtime)
            or len(data) > LIMIT
        ):
            raise ValueError("confirmation_file_drift")
        return data
    finally:
        stream.close()


def validate_assets(expected):
    if not matches(r"^[0-9a-f]{64}$", expected):
        raise ValueError("confirmation_helper_digest")
    directory = os.path.dirname(os.path.abspath(__file__))
    private(directory, True)
    ancestor = directory
    while True:
        private(ancestor, True, True)
        parent = os.path.dirname(ancestor)
        if parent == ancestor:
            break
        ancestor = parent
    raw = read_private(directory + "/manifest.json")
    manifest = closed(raw)
    if (
        digest(raw) != expected
        or set(manifest) != set(("schema_version", "kind", "files"))
        or (
            type(manifest["schema_version"]) is not int
            or manifest["schema_version"] != 1
            or manifest["kind"] != KIND
            or set(manifest["files"]) != set(MEMBERS)
            or set(os.listdir(directory)) != set(MEMBERS + ("manifest.json",))
        )
    ):
        raise ValueError("confirmation_helper_inventory")
    for name in MEMBERS:
        data = read_private(directory + "/" + name)
        if manifest["files"][name] != {"sha256": digest(data), "bytes": len(data)}:
            raise ValueError("confirmation_helper_drift")
    # Standalone execution imports only these already verified fixed assets.
    sys.path[:] = [directory] + [p for p in sys.path if p and os.path.isabs(p) and p != directory]
    return expected


def helpers():
    if __package__:
        from cadence_mcp_bridge import _shared_reservations as accounting
        from cadence_mcp_bridge import _runner_bootstrap as installer
        from cadence_mcp_bridge import _environment_probe as probe
    else:
        import reservations as accounting
        import installer
        import probe
    return accounting, installer, probe


def account():
    import pwd

    info = pwd.getpwuid(os.getuid())
    if info.pw_uid == 0:
        raise ValueError("confirmation_normal_user_required")
    return info.pw_dir, info.pw_name, info.pw_uid


def domain(profile, anchor):
    accounting, installer, probe = helpers()
    profile = probe.validate_profile(profile)
    root = profile["paths"]["managed_root"]
    directory = root
    while True:
        private(directory, True, True)
        parent = os.path.dirname(directory)
        if parent == directory:
            break
        directory = parent
    home, username, uid = account()
    if username != profile["host"]["user"] or os.uname()[1] != profile["host"]["hostname"]:
        raise ValueError("confirmation_host_account_mismatch")
    domain_sha = digest(
        canonical(
            {
                "hostname": profile["host"]["hostname"],
                "architecture": profile["host"]["architecture"],
            }
        )
    )
    index = closed(read_private(home + "/.cadence_mcp-domain/manifest.json"))
    if set(index) != set(
        (
            "schema_version",
            "root",
            "resource_domain_sha256",
            "identity_manifest_sha256",
            "plan_sha256",
        )
    ) or (
        type(index["schema_version"]) is not int
        or index["schema_version"] != 1
        or index["root"] != root
        or index["resource_domain_sha256"] != domain_sha
        or index["identity_manifest_sha256"] != anchor
        or not matches(r"^[0-9a-f]{64}$", anchor)
        or not matches(r"^[0-9a-f]{64}$", index["plan_sha256"])
    ):
        raise ValueError("confirmation_existing_index_mismatch")
    binding = {
        "root_sha256": digest(root.encode("utf-8")),
        "resource_domain_sha256": domain_sha,
        "ledger_ref": accounting.LEDGER,
        "identity_manifest_sha256": anchor,
    }
    actual = accounting.identity_manifest(root, binding)
    policy = actual.get(
        "policy",
        {
            "attempt_ceiling": accounting.CEILING_COUNT,
            "result_ceiling_bytes": accounting.CEILING_BYTES,
        },
    )
    if (profile["limits"]["spectre_attempts"], profile["limits"]["result_reserved_bytes"]) != (
        policy["attempt_ceiling"],
        policy["result_ceiling_bytes"],
    ) or profile["paths"]["job_root"] != root + "/" + accounting.JOBS:
        raise ValueError("confirmation_resource_policy_mismatch")
    return root, binding, username, uid


def grant_document(raw, expected, profile, binding, live=True):
    accounting, installer, probe = helpers()
    if not matches(r"^[0-9a-f]{64}$", expected) or not isinstance(raw, STRING_TYPES):
        raise ValueError("confirmation_grant_document")
    data = raw.encode("ascii")
    if len(data) > 65536 or digest(data) != expected:
        raise ValueError("confirmation_grant_digest")
    # Canonical grant bytes also reject duplicate fields on Python2.6.
    grant = json.loads(raw)
    if canonical(grant) != data:
        raise ValueError("confirmation_canonical_grant_required")
    if (
        set(grant) != set(GRANT_KEYS)
        or type(grant["schema_version"]) is not int
        or (
            grant["schema_version"] != 1
            or grant["authorization_source"] != "explicit_operator_record"
            or grant["ledger_ref"] != accounting.LEDGER
            or grant["resource_domain_sha256"] != binding["resource_domain_sha256"]
            or not matches(r"^[a-z][a-z0-9-]{0,63}$", grant["grant_id"])
        )
    ):
        raise ValueError("confirmation_grant_shape")
    for name in ("runner_sha256", "environment_sha256", "design_sha256", "pdk_sha256"):
        if not matches(r"^[0-9a-f]{64}$", grant[name]):
            raise ValueError("confirmation_grant_binding")
    for name, allowed, minimum, maximum in (
        ("design_ids", None, 1, 16),
        ("analyses", ("dc", "ac", "tran"), 1, 3),
        ("actions", ("submit", "cancel_pending", "recover_extraction"), 1, 3),
    ):
        values = grant[name]
        if (
            not isinstance(values, list)
            or not minimum <= len(values) <= maximum
            or (
                len(values) != len(set(values))
                or any(
                    value not in allowed
                    if allowed is not None
                    else not matches(r"^[a-z][a-z0-9-]{0,63}$", value)
                    for value in values
                )
            )
        ):
            raise ValueError("confirmation_grant_scope")
    for name in (
        "attempt_limit",
        "result_reserved_bytes_limit",
        "valid_from_unix",
        "valid_until_unix",
    ):
        if not integer(grant[name]):
            raise ValueError("confirmation_grant_integer")
    if not (
        1 <= grant["attempt_limit"] <= min(500, profile["limits"]["spectre_attempts"])
        and 1 <= grant["result_reserved_bytes_limit"] <= profile["limits"]["result_reserved_bytes"]
        and 0 < grant["valid_from_unix"] < grant["valid_until_unix"] < 4102444800
    ) or (grant["status"] not in ("active", "revoked")):
        raise ValueError("confirmation_grant_bounds")
    if live and (
        grant["status"] != "active"
        or not grant["valid_from_unix"] <= time.time() < grant["valid_until_unix"]
    ):
        raise ValueError("confirmation_grant_inactive")
    regions = grant["numeric_regions"]
    if not isinstance(regions, list) or len(regions) > 32:
        raise ValueError("confirmation_numeric_regions")
    seen = set()
    for region in regions:
        if set(region) != set(("design_id", "logical_id", "unit", "minimum", "maximum")) or (
            region["design_id"] not in grant["design_ids"]
            or not matches(r"^[a-z][a-z0-9-]{0,63}$", region["logical_id"])
            or region["unit"] not in ("V", "A", "ohm", "F", "s", "Hz", "K", "degC", "1")
        ):
            raise ValueError("confirmation_numeric_region")
        key = (region["design_id"], region["logical_id"])
        if key in seen:
            raise ValueError("confirmation_duplicate_region")
        seen.add(key)
        for field in ("minimum", "maximum"):
            value = region[field]
            if not matches(r"^-?(0|[1-9][0-9]{0,63})(\.[0-9]{1,63})?$", value) or len(value) > 48:
                raise ValueError("confirmation_numeric_scalar")
            number = Decimal(value)
            if abs(number.adjusted()) > 30 or abs(number.as_tuple().exponent) > 40:
                raise ValueError("confirmation_numeric_bound")
        if Decimal(region["minimum"]) > Decimal(region["maximum"]):
            raise ValueError("confirmation_numeric_order")
    return grant


def authority_reference(value):
    if not matches(r"^[A-Za-z0-9][A-Za-z0-9 ._:/#-]{0,255}$", value):
        raise ValueError("confirmation_authority_reference")
    return value


def confirm(request, assets):
    if set(request) != set(
        (
            "schema_version",
            "profile_json",
            "grant_json",
            "grant_sha256",
            "identity_manifest_sha256",
            "operator_authority",
        )
    ) or (type(request["schema_version"]) is not int or request["schema_version"] != 1):
        raise ValueError("confirmation_request_shape")
    reference = authority_reference(request["operator_authority"])
    profile_raw = request["profile_json"].encode("ascii")
    profile = json.loads(profile_raw)
    root, binding, username, uid = domain(profile, request["identity_manifest_sha256"])
    grant = grant_document(request["grant_json"], request["grant_sha256"], profile, binding)
    if grant["environment_sha256"] != digest(profile_raw):
        raise ValueError("confirmation_profile_digest")
    accounting, installer, probe = helpers()
    with accounting.ReservationSession(root) as session:
        domain(profile, request["identity_manifest_sha256"])
        grant_document(request["grant_json"], request["grant_sha256"], profile, binding)
        counter, records = session.observe(binding)
        path = root + "/operator-confirmations"
        if not os.path.lexists(path):
            os.mkdir(path, 448)
            accounting.sync_directory(root)
        private(path, True)
        target = path + "/" + request["grant_sha256"] + ".json"
        value = {
            "schema_version": 1,
            "grant_sha256": request["grant_sha256"],
            "grant": grant,
            "grant_json": request["grant_json"],
            "identity_manifest_sha256": request["identity_manifest_sha256"],
            "root_sha256": binding["root_sha256"],
            "resource_domain_sha256": binding["resource_domain_sha256"],
            "operator_uid": uid,
            "operator_user": username,
            "operator_authority": reference,
            "confirmation_helper_sha256": assets,
        }
        if os.path.lexists(path + "/" + request["grant_sha256"] + ".revoked.json"):
            raise ValueError("confirmation_revoked")
        if os.path.lexists(target):
            raw = read_private(target)
            if closed(raw) != value:
                raise ValueError("confirmation_existing_conflict")
            changed = False
        else:
            accounting.write_new(target, value)
            changed = True
        return {
            "status": "OS_OPERATOR_CONFIRMATION_RECORDED",
            "grant_sha256": request["grant_sha256"],
            "confirmation_sha256": digest(canonical(value)),
            "operator_uid": uid,
            "changed": changed,
            "operator_confirmed": True,
            "execution_authorized": False,
            "counter": counter,
            "new_reservations": 0,
            "new_simulations": 0,
        }


def inspect(profile, grant_sha, anchor, live=True):
    if not matches(r"^[0-9a-f]{64}$", grant_sha):
        raise ValueError("confirmation_grant_digest")
    root, binding, username, uid = domain(profile, anchor)
    path = root + "/operator-confirmations/" + grant_sha
    if live and os.path.lexists(path + ".revoked.json"):
        raise ValueError("confirmation_revoked")
    raw = read_private(path + ".json")
    value = closed(raw)
    if set(value) != set(
        (
            "schema_version",
            "grant_sha256",
            "grant",
            "grant_json",
            "identity_manifest_sha256",
            "root_sha256",
            "resource_domain_sha256",
            "operator_uid",
            "operator_user",
            "operator_authority",
            "confirmation_helper_sha256",
        )
    ) or (
        type(value["schema_version"]) is not int
        or value["schema_version"] != 1
        or value["grant_sha256"] != grant_sha
        or value["identity_manifest_sha256"] != anchor
        or value["operator_uid"] != uid
        or not integer(value["operator_uid"])
        or value["operator_user"] != username
        or value["root_sha256"] != binding["root_sha256"]
        or value["resource_domain_sha256"] != binding["resource_domain_sha256"]
        or not matches(r"^[0-9a-f]{64}$", value["confirmation_helper_sha256"])
    ):
        raise ValueError("confirmation_record_binding")
    authority_reference(value["operator_authority"])
    if grant_document(value["grant_json"], grant_sha, profile, binding, live) != value["grant"]:
        raise ValueError("confirmation_record_grant_mismatch")
    revoked = path + ".revoked.json"
    if os.path.lexists(revoked):
        revocation = closed(read_private(revoked))
        if set(revocation) != set(
            (
                "schema_version",
                "grant_sha256",
                "confirmation_sha256",
                "operator_authority",
                "operator_uid",
                "confirmation_helper_sha256",
            )
        ) or (
            type(revocation["schema_version"]) is not int
            or revocation["schema_version"] != 1
            or revocation["grant_sha256"] != grant_sha
            or revocation["confirmation_sha256"] != digest(raw)
            or not integer(revocation["operator_uid"])
            or revocation["operator_uid"] != uid
            or not matches(r"^[0-9a-f]{64}$", revocation["confirmation_helper_sha256"])
        ):
            raise ValueError("confirmation_revocation_binding")
        authority_reference(revocation["operator_authority"])
    return value, digest(raw)


def revoke(request, assets):
    if set(request) != set(
        ("profile", "grant_sha256", "identity_manifest_sha256", "operator_authority")
    ):
        raise ValueError("confirmation_revoke_shape")
    reference = authority_reference(request["operator_authority"])
    root, binding, username, uid = domain(request["profile"], request["identity_manifest_sha256"])
    accounting, installer, probe = helpers()
    with accounting.ReservationSession(root) as session:
        session.observe(binding)
        value, record_sha = inspect(
            request["profile"], request["grant_sha256"], request["identity_manifest_sha256"], False
        )
        target = root + "/operator-confirmations/" + request["grant_sha256"] + ".revoked.json"
        record = {
            "schema_version": 1,
            "grant_sha256": request["grant_sha256"],
            "confirmation_sha256": record_sha,
            "operator_authority": reference,
            "operator_uid": uid,
            "confirmation_helper_sha256": assets,
        }
        if os.path.lexists(target):
            if closed(read_private(target)) != record:
                raise ValueError("confirmation_revocation_conflict")
            changed = False
        else:
            accounting.write_new(target, record)
            changed = True
        return {
            "status": "OS_OPERATOR_CONFIRMATION_REVOKED",
            "grant_sha256": request["grant_sha256"],
            "confirmation_sha256": record_sha,
            "operator_uid": uid,
            "changed": changed,
            "operator_confirmed": False,
            "execution_authorized": False,
            "new_reservations": 0,
            "new_simulations": 0,
        }


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in ("confirm", "inspect", "revoke"):
        raise ValueError("confirmation_fixed_action")
    assets = validate_assets(sys.argv[2])
    request = closed(sys.stdin.read(LIMIT + 1).encode("ascii"))
    if sys.argv[1] == "confirm":
        result = confirm(request, assets)
    elif sys.argv[1] == "revoke":
        result = revoke(request, assets)
    else:
        if set(request) != set(("profile", "grant_sha256", "identity_manifest_sha256")):
            raise ValueError("confirmation_inspect_shape")
        value, sha = inspect(
            request["profile"], request["grant_sha256"], request["identity_manifest_sha256"], False
        )
        result = {
            "status": "OS_OPERATOR_CONFIRMATION_OBSERVED",
            "grant_sha256": value["grant_sha256"],
            "confirmation_sha256": sha,
            "operator_confirmed": not os.path.lexists(
                request["profile"]["paths"]["managed_root"]
                + "/operator-confirmations/"
                + request["grant_sha256"]
                + ".revoked.json"
            ),
            "execution_authorized": False,
        }
    sys.stdout.write(canonical(result).decode("ascii") + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.stderr.write("OPERATOR_CONFIRMATION_REJECTED\n")
        sys.exit(65)
