"""Synthetic SSH stand-in for the WP-14 renewal collector tests."""

import hashlib
import json
import os
import sys
import time
from pathlib import Path

ASSETS = (
    "bin/cadence-runner",
    "lib/runner-common.sh",
    "lib/run-ade-profile-introspection.sh",
    "lib/run-wp14-role-discovery.sh",
    "py26/actual_profile_audit.py",
    "py26/ade_profile_introspection.py",
    "py26/wp14_role_discovery.py",
    "discovery/ade-profile-introspection.il",
    "discovery/wp14-role-discovery.il",
    "config/runner-lineage.json",
    "profiles/actual-differential-amplifier-tb2-transient/profile.json",
)
REMOTE_ROOT = "/home/buet/cds_work/.cadence_mcp"

scenario = os.environ["WP14_RENEWAL_SCENARIO"]
call_file = Path(os.environ["WP14_RENEWAL_CALL_FILE"])
args = sys.argv[1:]
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
assert len(args) == 13 and args[11] == "cadence-vm"
command = args[12]
for relative in ASSETS:
    assert f"{REMOTE_ROOT}/{relative}" in command
for forbidden in ("virtuoso", "spectre", "ocean", "dbOpenCellView", "cadence-runner' version"):
    assert forbidden not in command
with call_file.open("a", encoding="utf-8") as stream:
    stream.write(json.dumps({"pid": os.getpid(), "scenario": scenario}) + "\n")
    stream.flush()
    os.fsync(stream.fileno())

if scenario == "launch-nonzero":
    sys.exit(42)
if scenario == "hang":
    time.sleep(20)
if scenario in {"flood-stdout", "flood-stderr", "flood-both"}:
    while True:
        if scenario != "flood-stderr":
            os.write(1, b"X" * 4096)
        if scenario != "flood-stdout":
            os.write(2, b"Y" * 4096)
if scenario == "stderr":
    os.write(2, b"SYNTHETIC_DO_NOT_DISCLOSE\n")
    sys.exit(0)
if scenario == "invalid-utf8":
    os.write(1, b"\xff")
    sys.exit(0)

hostname = "other" if scenario == "wrong-host" else "cadence"
user = "other" if scenario == "wrong-user" else "buet"
root = "/unexpected" if scenario == "wrong-root" else REMOTE_ROOT
root_symlink = "true" if scenario == "root-symlink" else "false"
lines = [f"WP14_ID\t{hostname}\t{user}\t{root}\t{root}\ttrue\t{root_symlink}\ttrue"]
for index, relative in enumerate(ASSETS):
    absent = scenario == "absent-optional" and index == 3
    absent = absent or (scenario == "missing-required" and index == 0)
    if absent:
        lines.append(f"WP14_ASSET\t{index}\tabsent\t-\t-\t-\t-\t-\tfalse\ttrue")
        continue
    digest = hashlib.sha256(relative.encode()).hexdigest()
    mode = "700" if index < 7 else "600"
    owner = "buet"
    kind = "regular_file"
    links = "1"
    symlink = "false"
    contained = "true"
    if index == 0:
        if scenario == "bad-hash":
            digest = "not-a-hash"
        if scenario == "wrong-mode":
            mode = "777"
        if scenario == "wrong-owner":
            owner = "root"
        if scenario == "wrong-type":
            kind = "directory"
        if scenario == "wrong-links":
            links = "2"
        if scenario == "asset-symlink":
            symlink = "true"
        if scenario == "outside-root":
            contained = "false"
    record_index = 1 if scenario == "duplicate-index" and index == 2 else index
    lines.append(
        f"WP14_ASSET\t{record_index}\tfile\t{digest}\t{mode}\t{owner}\t"
        f"{kind}\t{links}\t{symlink}\t{contained}"
    )
if scenario == "missing-line":
    lines.pop()
if scenario == "extra-line":
    lines.append("UNEXPECTED")
if scenario == "protected-content":
    lines[1] += "\tSYNTHETIC_PROTECTED_CONTENT"
lines.append("WRONG_END" if scenario == "wrong-end" else "WP14_END")
sys.stdout.write("\n".join(lines) + "\n")
