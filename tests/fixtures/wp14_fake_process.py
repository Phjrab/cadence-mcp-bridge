"""Local subprocess stand-in. NEVER evaluates commands or opens any remote connection."""

import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

root = Path(__file__).resolve().parent
scenario = os.environ["WP14_FAKE_SCENARIO"]
kind, *args = sys.argv[1:]
assert kind in {"ssh", "scp"}
assert args[:11] == [
    "-o",
    "BatchMode=yes",
    "-o",
    "StrictHostKeyChecking=yes",
    "-o",
    "ConnectTimeout=10",
    "-o",
    "ServerAliveInterval=15",
    "-o",
    "ServerAliveCountMax=2",
    "--",
]
assert len(args) == 13
if kind == "ssh":
    assert args[11] == "cadence-vm"
    command = args[12]
    match = re.search(r"printf '(WP14_NARROW_[^']*)'", command)
    assert match
    marker = match[1].split("\\")[0]
    stage = {
        "WP14_NARROW_PREFLIGHT_OK": "preflight",
        "WP14_NARROW_SNAPSHOT_OK": "snapshot",
        "WP14_NARROW_INSTALL_OK": "install",
        "WP14_NARROW_DEPLOYMENT_VERIFIED": "verify",
    }[marker]
    call = {"kind": kind, "stage": stage, "command": command, "pid": os.getpid()}
else:
    stage = "upload"
    source = Path(args[11]).resolve()
    assert source.is_relative_to(root / "scratch")
    assert args[12].startswith("cadence-vm:/home/buet/cds_work/.cadence_mcp/")
    assert args[12].endswith(".wp14-v1-new")
    call = {
        "kind": kind,
        "stage": stage,
        "destination": args[12],
        "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "pid": os.getpid(),
    }
with (root / "calls.jsonl").open("a", encoding="utf-8") as stream:
    stream.write(json.dumps(call) + "\n")
    stream.flush()
    os.fsync(stream.fileno())

if scenario == f"fail-{stage}" or (kind == "scp" and scenario == "fail-scp"):
    sys.exit(42)
if scenario == "hang":
    time.sleep(20)
if scenario == "slow-each":
    time.sleep(1)
if scenario in {"flood-stdout", "flood-stderr", "flood-both"}:
    while True:
        if scenario != "flood-stderr":
            os.write(1, b"X" * 4096)
        if scenario != "flood-stdout":
            os.write(2, b"Y" * 4096)
if scenario == f"overflow-{kind}":
    os.write(1, b"X" * 65537)
    sys.exit(0)
if scenario == "stderr":
    os.write(2, b"DO_NOT_DISCLOSE_TEST_PAYLOAD\n")
    sys.exit(0)
if scenario == "invalid-utf8":
    os.write(1, b"\xff")
    sys.exit(0)
if stage == "preflight":
    # Restricted assertion model, NOT a shell interpreter. Compare exact expected preimages
    # against an independently constructed synthetic remote model; never read actual assets.
    actual_host = "different" if scenario == "drift-host" else "cadence"
    actual_user = "different" if scenario == "drift-user" else "buet"
    if f"$(hostname)\" = '{actual_host}'" not in command:
        sys.exit(42)
    if f"$(id -un)\" = '{actual_user}'" not in command:
        sys.exit(42)
    package = json.loads(
        next((root / "docs/approvals").glob("*PACKAGE_V2.json")).read_text(encoding="utf-8")
    )
    record = json.loads(
        next((root / "docs/approvals").glob("*AUTHORIZATION_V2.json")).read_text(encoding="utf-8")
    )
    expected_presence = {entry["path"]: entry["presence"] for entry in record["preimages"]}
    for asset in package["deployment_asset_allowlist"]:
        path = asset["path"]
        destination = "/home/buet/cds_work/.cadence_mcp/" + path.removeprefix("remote/")
        if expected_presence[path] == "absent":
            assert f"test ! -e '{destination}' && test ! -L '{destination}'" in command
            continue
        actual_hash = hashlib.sha256(path.encode()).hexdigest()
        actual_mode = asset["remote_mode"][1:]
        actual_links = 1
        if path == "remote/bin/cadence-runner":
            if scenario == "drift-hash":
                actual_hash = "f" * 64
            if scenario == "drift-mode":
                actual_mode = "777"
            if scenario == "drift-hardlink":
                actual_links = 2
            if scenario in {"drift-symlink", "drift-type"}:
                required = "test ! -L" if scenario == "drift-symlink" else "test -f"
                assert f"{required} '{destination}'" in command
                sys.exit(42)
        expected = re.search(
            re.escape(f"stat -c '%U:%h:%a' '{destination}')\" = '") + r"([^']+)'",
            command,
        )
        assert expected
        if expected[1] != f"buet:{actual_links}:{actual_mode}":
            sys.exit(42)
        expected = re.search(
            re.escape(f"sha256sum '{destination}' | awk '{{print $1}}')\" = '")
            + r"([0-9a-f]{64})'",
            command,
        )
        assert expected
        if actual_hash != expected[1]:
            sys.exit(42)
if kind == "ssh":
    if scenario == f"wrong-{stage}":
        print("UNEXPECTED_MARKER")
    else:
        # Decode the fixed printf marker only, not the command.
        sys.stdout.write(match[1].encode("ascii").decode("unicode_escape"))
