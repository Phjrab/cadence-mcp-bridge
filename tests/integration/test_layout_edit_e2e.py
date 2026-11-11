"""Read C1's retained actual-VM receipt; C4 never opens a remote writer session.

The receipt only checks retained evidence consistency. C1 command/output and
actual desktop-app evidence remain separately recorded in the acceptance table.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_retained_c1_actual_vm_receipt_matches_fixed_integration_build() -> None:
    receipt_path = os.environ.get("CADENCE_LAYOUT_E2E_RECEIPT")
    if not receipt_path:
        pytest.skip("NOT_RUN: C1 actual-VM receipt not supplied; no VM call is made by this test")
    spec = importlib.util.spec_from_file_location(
        "layout_receipt_verifier", ROOT / "scripts/verify-layout-edit.py"
    )
    assert spec is not None and spec.loader is not None
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    with Path(receipt_path).open("rb") as stream:
        data = stream.read(verifier.MAX_RECEIPT_BYTES + 1)
    if len(data) > verifier.MAX_RECEIPT_BYTES:
        pytest.fail("actual receipt exceeds fixed bound", pytrace=False)
    try:
        receipt = json.loads(data)
        report = verifier.verify_receipt(receipt)
    except (ValueError, KeyError, TypeError):
        pytest.fail(
            "actual receipt inconsistent; inspect retained private C1 evidence", pytrace=False
        )
    build = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert report["build_sha"] == build, "receipt must cover the fixed integration SHA"
    assert report["environment"] == "actual_vm", "synthetic receipt cannot qualify actual VM"
    assert report["status"] == "RECEIPT_CONSISTENT"
