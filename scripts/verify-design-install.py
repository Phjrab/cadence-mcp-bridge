"""Installed local M2 lifecycle on disposable fixtures; never contacts Cadence."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def verify(workspace: Path, *, preserved: bool) -> None:
    if preserved:
        expected = json.loads((workspace / "preserved.json").read_bytes())
        assert all(
            hashlib.sha256((workspace / name).read_bytes()).hexdigest() == digest
            for name, digest in expected.items()
        )
        print(json.dumps({"status": "M2_LOCAL_STATE_PRESERVED"}))
        return
    import cadence_mcp_bridge
    from cadence_mcp_bridge.m2_cdf import CdfSource, parse_frame, render_collector
    from cadence_mcp_bridge.m2_inverter import OwnedInverterPlan, observed_devices
    from cadence_mcp_bridge.schematic_plan import RevisionBinding

    if not Path(cadence_mcp_bridge.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()):
        raise ValueError("installed package origin required")
    # Pure local generation/parsing is not CDF/PDK qualification or execution.
    script = render_collector(CdfSource("RegisteredLibrary", "RegisteredCell"))
    assert b'"schematic" "" "r"' in script and b"dbSave" not in script
    try:
        parse_frame(b'M2_CDF_V1\nDEVICE|"fixture"|"fixture"|nil\n')
    except ValueError:
        pass
    else:
        raise ValueError("incomplete observed CDF must remain blocked")
    plan = OwnedInverterPlan(
        binding=RevisionBinding(
            workspace_id="fixture",
            design_id="fixture",
            revision_id="r1",
            source_baseline_sha256="a" * 64,
        ),
        cdf_frame_sha256=hashlib.sha256(b"incomplete").hexdigest(),
        output_library="Owned",
        dut_cell="Dut",
        testbench_cell="Bench",
        nmos_library="FixturePdk",
        nmos_cell="N",
        pmos_library="FixturePdk",
        pmos_cell="P",
    )
    try:
        observed_devices(plan, b"incomplete")
    except ValueError:
        pass
    else:
        raise ValueError("installed generator must reject unobserved CDF")
    workspace.mkdir()

    def run(*args: str) -> dict[str, Any]:
        result = subprocess.run(
            [sys.executable, "-I", "-m", "cadence_mcp_bridge", "operator-design", *args],
            capture_output=True,
            timeout=30,
            check=True,
        )
        assert not result.stderr
        payload = json.loads(result.stdout)
        assert not payload["remote_contact"] and not payload["execution_authorized"]
        return payload

    example = workspace / "example"
    store = workspace / "revisions.sqlite3"
    run("example", "--output", str(example))
    run("init", "--store", str(store))
    inputs = [
        "--plan",
        str(example / "plan.json"),
        "--registry",
        str(example / "registry.json"),
        "--binding",
        str(example / "binding.json"),
    ]
    assert run("validate", *inputs)["status"] == "LOCAL_SYNTHETIC_PLAN_VALID"
    first = run("record", "--store", str(store), *inputs)
    assert first == run("record", "--store", str(store), *inputs)
    shown = run(
        "show",
        "--store",
        str(store),
        "--workspace",
        "synthetic-work",
        "--design",
        "inverter",
        "--revision",
        "draft-one",
    )
    assert shown["revision_sha256"] == first["revision_sha256"]
    assert set(shown["verification"].values()) == {"NOT_ASSESSED"}
    from cadence_mcp_bridge.physical_capabilities import PhysicalCapabilityInventory, PhysicalScope

    inventory = PhysicalCapabilityInventory(
        scope=PhysicalScope(
            environment_id="synthetic",
            environment_sha256="a" * 64,
            pdk_id="synthetic",
            pdk_sha256="b" * 64,
        )
    )
    (workspace / "physical.json").write_text(inventory.model_dump_json(), encoding="utf-8")
    assessed = run("physical-assess", "--inventory", str(workspace / "physical.json"))
    assert len(assessed["capabilities"]) == 9
    assert {item["capability"] for item in assessed["capabilities"]} == {
        "layout-db",
        "pcell",
        "technology-library",
        "dbu",
        "layer-purpose",
        "via",
        "drc",
        "lvs",
        "pex",
    }
    for item in assessed["capabilities"]:
        assert item["execution_qualified"] is False and item["signoff_qualified"] is False
        assert {facet["facet"]: facet["status"] for facet in item["facets"]} == {
            "installation": "UNKNOWN",
            "interface": "UNKNOWN",
            "deck": "UNKNOWN",
            "license": "LICENSE_UNVERIFIED",
            "execution": "EXECUTION_UNVERIFIED",
        }
    names = [
        "revisions.sqlite3",
        "example/plan.json",
        "example/registry.json",
        "example/binding.json",
        "physical.json",
    ]
    expected = {name: hashlib.sha256((workspace / name).read_bytes()).hexdigest() for name in names}
    (workspace / "preserved.json").write_text(
        json.dumps(expected, sort_keys=True), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": "INSTALLED_M2_LOCAL_PLAN_REVISION_PASS",
                "remote_contact": False,
                "new_reservations": 0,
                "physical_execution": "NOT_RUN",
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--verify-preserved", action="store_true")
    options = parser.parse_args()
    verify(options.workspace, preserved=options.verify_preserved)
