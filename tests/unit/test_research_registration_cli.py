"""Operator-local assembly reusing the existing native registration fixture."""

import hashlib
import json
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

import pytest
from test_native_registration import assembly, enrollment, operator, operator_base

from cadence_mcp_bridge.__main__ import main
from cadence_mcp_bridge.native_registration import RegistrationObservation, RegistrationProbeRequest
from cadence_mcp_bridge.native_runtime import NativeRegistration
from cadence_mcp_bridge.research_circuit import MosBlockRegistrationHandoff
from cadence_mcp_bridge.research_registration_cli import ResearchRegistrationRequest

__all__ = ["assembly", "enrollment", "operator", "operator_base"]


def pinned(path: Path) -> dict[str, str]:
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


@pytest.fixture
def research_registration(assembly, operator, tmp_path, monkeypatch):
    context, paths, output = assembly
    observation = RegistrationObservation.model_validate_json(paths[1].read_bytes())
    handoff = tmp_path / "handoff.json"
    library = observation.libraries[0]
    handoff.write_text(
        json.dumps(
            {
                "operation_id": str(uuid4()),
                "binding": {
                    "workspace_id": "research",
                    "design_id": observation.ade.design_id,
                    "revision_id": "owned",
                    "source_baseline_sha256": "1" * 64,
                },
                "library": library.model_dump(mode="json"),
                "source_cell": library.path + "/DUT",
                "source_tree_sha256": "2" * 64,
                "bench_cell": observation.source_cell,
                "bench_tree_sha256": observation.ade.source_tree_sha256,
                "pins": {
                    "plan_sha256": "3" * 64,
                    "save_receipt_sha256": "4" * 64,
                    "reopen_receipt_sha256": "5" * 64,
                    "netlist_receipt_sha256": "6" * 64,
                    "raw_netlist_sha256": "7" * 64,
                    "full_netlist_sha256": observation.baseline_input_sha256,
                },
            }
        )
    )
    document = tmp_path / "research-registration.json"
    settings = operator[3]
    payload = {
        "schema_version": 1,
        "expected_context_sha256": context.context_sha256,
        "expected_handoff_sha256": MosBlockRegistrationHandoff.model_validate_json(
            handoff.read_bytes()
        ).handoff_sha256,
        "identity_manifest_sha256": "d" * 64,
        "probe": pinned(paths[0]),
        "observation": pinned(paths[1]),
        "reader_definition": pinned(paths[2]),
        "handoff": pinned(handoff),
    }
    transport = Mock(side_effect=AssertionError("operator assembly cannot contact VM"))
    monkeypatch.setattr("cadence_mcp_bridge.native_registration.run_fixed", transport)
    return context, observation, paths, settings, document, handoff, payload, output, transport


def invoke(settings, document, payload, output):
    raw = json.dumps(payload).encode()
    ResearchRegistrationRequest.model_validate_json(raw)
    document.write_bytes(raw)
    return main(
        [
            "operator-candidates",
            "assemble-research-registration",
            "--settings",
            str(settings),
            "--context",
            "operator",
            "--request",
            str(document),
            hashlib.sha256(raw).hexdigest(),
            "--output",
            str(output),
        ]
    )


def test_assembled_research_registration_is_read_back_and_exclusive(
    research_registration,
    capsys,
):
    context, observation, paths, settings, document, handoff, payload, output, transport = (
        research_registration
    )
    baseline = RegistrationProbeRequest.model_validate_json(paths[0].read_bytes()).baseline_netlist
    sources = (*paths, handoff, baseline, settings)
    before = [p.read_bytes() for p in sources]
    assert invoke(settings, document, payload, output) == 0
    raw = output.read_bytes()
    registration = NativeRegistration.model_validate_json(raw)
    (route,) = registration.routes
    summary = json.loads(capsys.readouterr().out)
    assert summary["registration_sha256"] == hashlib.sha256(raw).hexdigest()
    assert summary["execution_authorized"] is summary["remote_contact"] is False
    assert summary["provenance"] == "OPERATOR_PINNED_HANDOFF_AND_OBSERVATION"
    assert summary["baseline_input_sha256"] == observation.baseline_input_sha256
    assert summary["dut_netlist_sha256"] == "7" * 64
    assert route.ade == observation.ade and route.libraries == observation.libraries
    assert invoke(settings, document, payload, output) == 2
    assert output.read_bytes() == raw
    assert [p.read_bytes() for p in sources] == before
    assert not context.binding.analysis_journal.exists()
    transport.assert_not_called()


@pytest.mark.parametrize("part", ["baseline", "source_tree", "library_tree", "context", "handoff"])
def test_research_registration_rejects_mixed_evidence(
    research_registration,
    part,
):
    _, _, paths, settings, document, _, payload, output, transport = research_registration
    observation_path = paths[1]
    record = json.loads(observation_path.read_bytes())
    if part == "baseline":
        record["baseline_input_sha256"] = "f" * 64
    elif part == "source_tree":
        record["ade"]["source_tree_sha256"] = "f" * 64
    elif part == "library_tree":
        record["libraries"][0]["tree_sha256"] = "f" * 64
    elif part == "context":
        payload["expected_context_sha256"] = "f" * 64
    else:
        payload["expected_handoff_sha256"] = "f" * 64
    observation_path.write_text(json.dumps(record))
    payload["observation"] = pinned(observation_path)
    assert invoke(settings, document, payload, output) == 2
    assert not output.exists()
    transport.assert_not_called()
