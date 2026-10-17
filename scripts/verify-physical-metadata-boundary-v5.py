"""Preserve the V4 guard and require its retained sources in the active lineage."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE37 = "d456bf8228647a1171c028e3bea9d92b9377e9c0"
SOURCE38 = "d64a5ea25f17465ef910a35c06f9a16e2d2269d6"
RETAINED = (
    "scripts/verify-physical-metadata-boundary-v4.py",
    "docs/policy/PHYSICAL_METADATA_SOURCE_V4.json",
)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()


def inspect(checkpoint_name: str = "PHYSICAL_METADATA_SOURCE_V4.json") -> dict[str, object]:
    # Object availability alone is insufficient: detached retained corrections
    # must not disappear from counted history after rebase/cherry-pick.
    for revision in (SOURCE37, SOURCE38):
        if subprocess.run(
            ["git", "merge-base", "--is-ancestor", revision, "HEAD"], cwd=ROOT, check=False
        ).returncode:
            raise ValueError("physical retained source37/source38 ancestry missing")
    for path in RETAINED:
        prior = subprocess.check_output(["git", "show", SOURCE38 + ":" + path], cwd=ROOT)
        if sha((ROOT / path).read_bytes()) != sha(prior):
            raise ValueError("physical immutable V4 guard/checkpoint changed")
    spec = importlib.util.spec_from_file_location("physical_retained_v4", ROOT / RETAINED[0])
    if spec is None or spec.loader is None:
        raise ValueError("physical retained V4 loader")
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    result: dict[str, object] = guard.inspect(checkpoint_name)
    result.update(
        status="PHYSICAL_METADATA_SOURCE_BOUNDARY_V5_PASS",
        retained_source37_source38_ancestry=True,
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", default="PHYSICAL_METADATA_SOURCE_V4.json")
    print(json.dumps(inspect(parser.parse_args().checkpoint), sort_keys=True))
