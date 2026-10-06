"""Inspect exact-commit Git source snapshots; this is not licensing clearance.

Reads archives without extraction and compares every retained file to a Git blob.
Downloads are a separate operator action. No network or Cadence access is made.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import subprocess
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

MAX_ARCHIVE_BYTES = 64 * 1024**2
MAX_EXPANDED_BYTES = 128 * 1024**2
MAX_MEMBERS = 4096
EXCLUDED = "docs/agent_plan/"


def safe_name(name: str) -> str:
    value = name.rstrip("/")
    parts = PurePosixPath(value)
    if (
        not value or parts.is_absolute() or "\\" in value or ":" in value
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        raise ValueError("unsafe archive name")
    return value


def read_members(path: Path) -> dict[str, bytes]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError("bounded regular archive required")
    files: dict[str, bytes] = {}
    seen: set[str] = set()
    expanded = 0

    def admit(name: str, size: int) -> str:
        nonlocal expanded
        key = safe_name(name)
        if "/docs/agent_plan/" in "/" + key + "/":
            raise ValueError("imported planning member remains in archive")
        if key in seen or len(seen) >= MAX_MEMBERS or size < 0:
            raise ValueError("duplicate or excessive archive members")
        seen.add(key)
        expanded += size
        if expanded > MAX_EXPANDED_BYTES:
            raise ValueError("expanded archive exceeds bound")
        return key

    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            for entry in archive.infolist():
                key = admit(entry.filename, entry.file_size)
                mode = entry.external_attr >> 16
                if stat.S_ISLNK(mode) or stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR}:
                    raise ValueError("archive links or special members denied")
                if not entry.is_dir():
                    files[key] = archive.read(entry)
    else:
        with tarfile.open(path, "r:*") as stream:
            for member in stream:
                key = admit(member.name, member.size)
                if member.isdir():
                    continue
                if not member.isfile():
                    raise ValueError("archive links or special members denied")
                payload = stream.extractfile(member)
                if payload is None:
                    raise ValueError("regular archive member missing")
                files[key] = payload.read(member.size + 1)
                if len(files[key]) != member.size:
                    raise ValueError("truncated archive member")
    if not files:
        raise ValueError("empty archive")
    return files


def inspect(path: Path, blobs: dict[str, str]) -> dict[str, object]:
    files = read_members(path)
    # Local archives may have no prefix; hosted snapshots have one root directory.
    licenses = [name for name in files if name == "LICENSE" or name.endswith("/LICENSE")]
    if len(licenses) != 1:
        raise ValueError("one root license required")
    prefix = licenses[0][:-len("LICENSE")]
    if prefix and prefix.count("/") != 1:
        raise ValueError("one snapshot root required")
    if any(not name.startswith(prefix) for name in files):
        raise ValueError("mixed snapshot roots")
    normalized = {name[len(prefix):]: data for name, data in files.items()}
    if any(name == EXCLUDED.rstrip("/") or name.startswith(EXCLUDED) for name in normalized):
        raise ValueError("imported planning remains in archive")
    expected = {name: oid for name, oid in blobs.items() if not name.startswith(EXCLUDED)}
    if set(normalized) != set(expected):
        raise ValueError("unexpected archive omission or addition")
    for name, data in normalized.items():
        blob = b"blob " + str(len(data)).encode("ascii") + b"\0" + data
        if hashlib.sha1(blob).hexdigest() != expected[name]:
            raise ValueError("archive content differs from candidate blob")
    required = {"LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md", "README.md", "pyproject.toml"}
    if not required <= normalized.keys() or not any(n.startswith("src/") for n in normalized):
        raise ValueError("installation or notice material missing")
    return {
        "status": "IMPORT_EXCLUDED_VERIFIED",
        "archive_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "file_count": len(normalized),
        "imported_files_excluded": len(blobs) - len(expected),
        "retained_blob_identity": "PASS",
        "expanded_file_bytes": sum(len(data) for data in normalized.values()),
        "rights_status": "LEGAL_REVIEW_REQUIRED",
        "publication_status": "PUBLICATION_NOT_AUTHORIZED",
    }


def candidate_blobs(project: Path, commit: str) -> dict[str, str]:
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("exact SHA-1 commit required")
    result = subprocess.run(
        ["git", "-C", str(project), "ls-tree", "-rz", commit],
        check=True, capture_output=True, timeout=30,
    )
    blobs = {}
    for record in result.stdout.split(b"\0"):
        if not record:
            continue
        metadata, raw_name = record.split(b"\t", 1)
        mode, kind, oid = metadata.decode("ascii").split()
        if kind != "blob" or mode not in {"100644", "100755"}:
            raise ValueError("candidate links or submodules require review")
        blobs[safe_name(raw_name.decode("utf-8"))] = oid
    if not any(name.startswith(EXCLUDED) for name in blobs):
        raise ValueError("candidate import absent; exclusion cannot be established")
    return blobs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--commit", required=True)
    parser.add_argument("--archives", type=Path, nargs="+", required=True)
    args = parser.parse_args()
    try:
        blobs = candidate_blobs(args.project, args.commit)
        reports = [inspect(path, blobs) for path in args.archives]
    except (OSError, ValueError, subprocess.SubprocessError, tarfile.TarError, zipfile.BadZipFile):
        print(json.dumps({"archive_audit": "FAIL", "publication_authorized": False}))
        return 1
    print(json.dumps({"commit": args.commit, "archive_audit": "PASS", "archives": reports}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
