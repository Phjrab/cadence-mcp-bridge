import json
from hashlib import sha256
from pathlib import Path

import pytest
from pydantic import ValidationError
from test_research_draft import study

from cadence_mcp_bridge.__main__ import main
from cadence_mcp_bridge.research_adapters import ResearchCircuitRequest
from cadence_mcp_bridge.research_circuit import ResearchCircuitStaticPreview


def test_static_preview_cli_pins_inputs_and_never_overwrites(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    draft, port = study(17)
    port["devices"][0]["geometry"]["source"] = {"reference": "local size", "status": "assumed"}
    bound = json.dumps(port).encode()
    del port["binding"]
    decisions = json.dumps(port).encode()
    draft_path, port_path = tmp_path / "draft.json", tmp_path / "port.json"
    output = tmp_path / "preview.json"
    draft_path.write_bytes(draft)
    port_path.write_bytes(decisions)
    command = [
        "operator-candidates",
        "compile-research-draft",
        "--draft",
        str(draft_path),
        sha256(draft).hexdigest(),
        "--port",
        str(port_path),
        sha256(decisions).hexdigest(),
    ]

    assert main([*command, "--output", str(output)]) != 0
    assert not output.exists()
    capsys.readouterr()

    wrong_pin = [*command[:-1], "0" * 64, "--static-preview"]
    assert main([*wrong_pin, "--output", str(output)]) != 0
    assert not output.exists()
    capsys.readouterr()

    preview = [*command, "--static-preview"]
    port_path.write_bytes(bound)
    bound_preview = [*command[:-1], sha256(bound).hexdigest(), "--static-preview"]
    assert main([*bound_preview, "--output", str(output)]) != 0
    assert not output.exists()
    port_path.write_bytes(decisions)
    capsys.readouterr()

    assert main([*preview, "--output", str(output)]) == 0
    raw = output.read_bytes()
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "RESEARCH_CIRCUIT_STATIC_PREVIEW_EXPORTED"
    assert result["execution_authorized"] is False
    assert result["file_sha256"] == sha256(raw).hexdigest()
    assert "binding" not in json.loads(raw)
    definition = ResearchCircuitStaticPreview.model_validate_json(raw)
    assert definition.unresolved == ("geometry_evidence", "static_preview")
    assert len(definition.circuits[0].instances) == 17
    with pytest.raises(ValidationError):
        ResearchCircuitRequest.model_validate_json(raw)

    assert main([*preview, "--output", str(output)]) != 0
    assert main([*preview, "--output", str(draft_path)]) != 0
    assert output.read_bytes() == raw
    assert draft_path.read_bytes() == draft
    assert port_path.read_bytes() == decisions
