"""Local-only export of a fixed initializer metadata helper; no remote transport.

An export and its hashes describe code and inputs, not execution authority or
runtime trust. The administrator must separately authorize the exact operation.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from importlib.resources import files
from pathlib import Path
from typing import Any

from cadence_mcp_bridge.binding_observation_bootstrap import _Registration
from cadence_mcp_bridge.binding_observer_operator import _directory_identity, _held_output
from cadence_mcp_bridge.domain_provisioning import _canonical
from cadence_mcp_bridge.environments import EnvironmentProfile
from cadence_mcp_bridge.onboarding import _local_path
from cadence_mcp_bridge.physical_metadata import _load_bundle

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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export(args.bundle, args.manifest_sha256, args.output), sort_keys=True))


if __name__ == "__main__":
    main()
