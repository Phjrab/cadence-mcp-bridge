"""Remove only build-generated pip entrypoints/local URLs from a new payload."""

import argparse
import csv
import json
import shutil
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--site", type=Path, required=True)
args = parser.parse_args()
site = args.site.resolve(strict=True)
if site.name != "site-packages" or site.parent.name != "Lib":
    raise ValueError("new_payload_site_required")
removed = []
for metadata in site.glob("*.dist-info"):
    direct = metadata / "direct_url.json"
    if direct.is_file():
        data = json.loads(direct.read_text(encoding="utf-8"))
        if not str(data.get("url", "")).startswith("file:"):
            raise ValueError("unexpected_install_origin")
        removed.append(direct.relative_to(site).as_posix())
        direct.unlink()
entrypoints = site / "bin"
if entrypoints.is_symlink() or entrypoints.is_junction():
    raise ValueError("linked_build_output")
if entrypoints.exists():
    if entrypoints.resolve().parent != site:
        raise ValueError("build_output_escape")
    removed.extend(p.relative_to(site).as_posix() for p in entrypoints.rglob("*") if p.is_file())
    shutil.rmtree(entrypoints)
for record in site.glob("*.dist-info/RECORD"):
    with record.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.reader(stream))
    rows = [row for row in rows if row[0] not in removed and not row[0].startswith("../../bin/")]
    with record.open("w", newline="", encoding="utf-8") as stream:
        csv.writer(stream).writerows(rows)
print(json.dumps({"build_generated_files_removed": len(removed), "operator_state_touched": False}))
