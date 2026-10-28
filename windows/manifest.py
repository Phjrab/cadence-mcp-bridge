"""Curated Windows payload inventory; no operator state or vendor artifacts."""

import argparse
import hashlib
import importlib.metadata
import json
import subprocess
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--root", type=Path, required=True)
parser.add_argument("--repository", type=Path, required=True)
parser.add_argument("--inputs", type=Path, required=True)
parser.add_argument("--version", required=True)
args = parser.parse_args()
licenses = []
for distribution in importlib.metadata.distributions(
    path=[str(args.root / "runtime/Lib/site-packages")]
):
    licenses.append(
        {
            "name": distribution.metadata["Name"],
            "version": distribution.version,
            "license_expression": distribution.metadata.get("License-Expression"),
            "license": distribution.metadata.get("License"),
            "license_files": [
                str(p) for p in distribution.files or [] if "license" in str(p).lower()
            ],
        }
    )
(args.root / "DEPENDENCY-LICENSES.json").write_text(
    json.dumps(licenses, indent=2), encoding="utf-8"
)
files = {}
for path in sorted(args.root.rglob("*")):
    if path.is_file():
        relative = path.relative_to(args.root).as_posix()
        files[relative] = {
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
git = ["git", "-c", "safe.directory=" + args.repository.resolve().as_posix()]
sha = subprocess.check_output([*git, "rev-parse", "HEAD"], cwd=args.repository, text=True).strip()
dirty = subprocess.check_output(
    [*git, "status", "--porcelain", "--untracked-files=all"],
    cwd=args.repository,
    text=True,
    encoding="utf-8",
)
manifest = {
    "schema_version": 1,
    "version": args.version,
    "architecture": "windows-x64",
    "source_commit": sha,
    "source_tree_dirty": bool(dirty),
    "published": False,
    "code_signed": False,
    "inputs": json.loads(args.inputs.read_text(encoding="utf-8")),
    "files": files,
}
(args.root / "INSTALL-MANIFEST.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
