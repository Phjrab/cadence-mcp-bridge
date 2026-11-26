"""Exercise the JSON boundary between a six-device report and the static OTA port."""

import hashlib
import json
import runpy
from pathlib import Path
from uuid import uuid4

import pytest


def test_static_port_reads_grouped_fixture_json_and_checks_bulk(tmp_path: Path) -> None:
    example = (
        Path(__file__).resolve().parents[2] / "docs/examples/research/bind-ota-port-evidence.py"
    )
    binding = runpy.run_path(str(example))
    points = {}
    for key, (slot, master, width, length, count) in binding["FIXTURE_SLOTS"].items():
        rail = "vss" if master == "nmos1v" else "vdd"
        factors = f"({count})*(1)"
        points[key] = {
            "instance": slot,
            "master": master,
            "terminals": ["vout", "vin", rail, rail],
            "observed": {
                "w": {"value": str(width), "unit": "nm"},
                "l": {"value": str(length), "unit": "nm"},
                "m": count,
            },
            "fingers": 1,
            "netlist_options": {
                "w": f"{width}n",
                "l": f"{length}n",
                "m": factors,
                "simM": factors,
                "as": "1p",
                "ad": "1p",
                "ps": "1u",
                "pd": "1u",
            },
            "original_point_pins": [
                {"properties_sha256": ch * 64, "cdf_sha256": ch * 64} for ch in "456"
            ],
        }
    report = {
        "schema_version": 1,
        "status": "VERIFIED_FIXTURE_TUPLES",
        "operation_id": str(uuid4()),
        "fixture_library": "UnitFixture",
        "receipts": dict(
            zip(("setup", "save", "reopen-netlist"), (ch * 64 for ch in "123"), strict=True)
        ),
        "evidence_index_sha256": "a" * 64,
        "scope_sha256": "b" * 64,
        "dut_revision_sha256": "c" * 64,
        "testbench_revision_sha256": "d" * 64,
        "netlist_sha256": "e" * 64,
        "points": points,
    }

    def read() -> int:
        raw = json.dumps(report).encode()
        path = tmp_path / "report.json"
        path.write_bytes(raw)
        artifact = binding["Artifact"](path=Path(path.name), sha256=hashlib.sha256(raw).hexdigest())
        operation, geometries = binding["fixture_points"](tmp_path, artifact)
        assert operation == report["operation_id"]
        return len(geometries)

    assert read() == 6
    points["p4-p04"]["terminals"] = ["vout", "vin", "vdd", "vss"]
    with pytest.raises(ValueError, match="differs from the approved target"):
        read()
