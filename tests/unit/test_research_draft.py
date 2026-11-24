"""Porting an explicit flat study is a local declaration transformation."""

import json
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest
from test_m2_inverter import fixture
from test_research_circuit import payload

from cadence_mcp_bridge.__main__ import main
from cadence_mcp_bridge.research_draft import compile_research_draft


def study(count: int) -> tuple[bytes, dict[str, Any]]:
    plan, _ = fixture()
    original = payload(plan)
    dut, bench = original["circuits"]
    rows, decisions = [], []
    for i in range(count):
        device = deepcopy(dut["instances"][i % 2])
        device["name"] = f"M{i}"
        connections = {link["terminal"]: link["net"] for link in device.pop("links")}
        device["resolved_terminals"] = {"B": connections.pop("B")}
        device["spectre"] = {
            "model": device["master"]["cell"],
            "width": device["geometry"]["w"],
            "length": device["geometry"]["length"],
            "multiplier": 1,
            "source": original["source"],
        }
        rows.append(
            {
                "name": device["name"],
                "device_kind_candidate": device["kind"],
                "terminals": connections | {"B": None},
                "dimensions_candidate": {"W": 99, "L": 99, "unit": "um"},
            }
        )
        decisions.append(device)
    raw = json.dumps(
        {
            "document_kind": "research-draft-v1",
            "execution_ready": False,
            "design": {
                "name": "Study",
                "pins_candidates": [{"name": p["name"]} for p in dut["ports"]],
                "devices": rows,
            },
        }
    ).encode()
    return raw, {
        "schema_version": 1,
        "draft_sha256": sha256(raw).hexdigest(),
        "source_design": "Study",
        "topology_source": original["source"],
        "binding": original["binding"],
        "dut": dut["name"],
        "ports": dut["ports"],
        "symbol": dut["symbol"],
        "devices": decisions,
        "bench": bench,
        "analyses": original["analyses"],
    }


def test_compile_seventeen_devices_from_source_nets_and_explicit_target_sizes() -> None:
    draft, port = study(17)
    result = compile_research_draft(draft, json.dumps(port).encode())
    assert len(result.circuits[0].instances) == 17
    device = result.circuits[0].instances[0]
    assert device.kind == "nmos"
    assert device.connections == {"D": "vout", "G": "vin", "S": "vss", "B": "vss"}
    assert device.geometry.w.value == "120" and device.geometry.w.unit == "nm"
    assert result.binding.workspace_id == port["binding"]["workspace_id"]


def test_cli_result_can_be_passed_to_existing_validator(tmp_path: Path) -> None:
    draft, port = study(17)
    source, decisions = tmp_path / "study.json", tmp_path / "port.json"
    request, result = tmp_path / "request.json", tmp_path / "validated.json"
    source.write_bytes(draft)
    decisions.write_bytes(json.dumps(port).encode())
    command = [
        "operator-candidates",
        "compile-research-draft",
        "--draft",
        str(source),
        sha256(draft).hexdigest(),
        "--port",
        str(decisions),
        sha256(decisions.read_bytes()).hexdigest(),
        "--output",
        str(request),
    ]
    assert main(command) == 0
    request_bytes = request.read_bytes()
    assert (
        main(
            [
                "operator-candidates",
                "validate-research-circuit",
                "--request",
                str(request),
                sha256(request_bytes).hexdigest(),
                "--output",
                str(result),
            ]
        )
        == 0
    )
    assert json.loads(result.read_bytes())["execution_authorized"] is False
    assert main(command) != 0
    assert request.read_bytes() == request_bytes


@pytest.mark.parametrize(
    "problem", ["fingerprint", "evidence", "body", "replace", "pin", "pin_net", "type"]
)
def test_compile_rejects_incomplete_or_conflicting_port(problem: str) -> None:
    draft, port = study(2)
    device = port["devices"][0]
    if problem == "fingerprint":
        draft += b" "
    elif problem == "evidence":
        device["geometry"]["source"]["status"] = "assumed"
    elif problem == "body":
        device["resolved_terminals"].clear()
    elif problem == "replace":
        device["resolved_terminals"]["D"] = "vss"
    elif problem == "pin":
        port["ports"].pop()
    elif problem == "pin_net":
        port["ports"][0]["net"] = port["ports"][1]["net"]
    else:
        device["kind"] = "pmos"
    with pytest.raises(ValueError):
        compile_research_draft(draft, json.dumps(port).encode())
