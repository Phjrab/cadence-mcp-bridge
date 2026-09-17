"""Local stand-in that records but never evaluates the fixed SSH command."""

import hashlib
import json
import os
import sys
import time
from pathlib import Path

root = Path(__file__).resolve().parent
scenario = os.environ["WP14_PREIMAGE_SCENARIO"]
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
package = json.loads(
    (
        root
        / "docs/approvals"
        / "WP14_REMOTE_IDENTITY_PREIMAGE_EVIDENCE_COLLECTION_APPROVAL_PACKAGE_V2.json"
    ).read_text()
)
for item in package["asset_preimage_allowlist"]:
    assert "/home/buet/cds_work/.cadence_mcp/" + item["remote_relative_path"] in command
for forbidden in ("virtuoso", "spectre", "ocean", "dbOpenCellView", "cadence-runner' version"):
    assert forbidden not in command
with (root / "calls.jsonl").open("a", encoding="utf-8") as stream:
    stream.write(json.dumps({"pid": os.getpid(), "command": command}) + "\n")
    stream.flush()
    os.fsync(stream.fileno())

if scenario == "fail":
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
    os.write(2, b"DO_NOT_DISCLOSE_TEST_PAYLOAD\n")
    sys.exit(0)
if scenario == "invalid-utf8":
    os.write(1, b"\xff")
    sys.exit(0)

hostname = "other" if scenario == "wrong-host" else "cadence"
user = "other" if scenario == "wrong-user" else "buet"
remote_root = "/unexpected" if scenario == "wrong-root" else "/home/buet/cds_work/.cadence_mcp"
root_symlink = "true" if scenario == "root-symlink" else "false"
lines = [f"WP14_ID\t{hostname}\t{user}\t{remote_root}\t{remote_root}\ttrue\t{root_symlink}\ttrue"]
for index, item in enumerate(package["asset_preimage_allowlist"]):
    absent = scenario == "absent-optional" and index == 3
    absent = absent or (scenario == "missing-required" and index == 0)
    if absent:
        lines.append(f"WP14_ASSET\t{index}\tabsent\t-\t-\t-\t-\t-\tfalse\ttrue")
        continue
    digest = hashlib.sha256(item["path"].encode()).hexdigest()
    mode, owner, kind, links, symlink, contained = (
        ("700" if index < 7 else "600"),
        "buet",
        "regular_file",
        "1",
        "false",
        "true",
    )
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
