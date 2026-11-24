"""Wire checks for the local research generation CLI."""

import json
from hashlib import sha256

import pytest
from test_research_generation_preparation import _request

from cadence_mcp_bridge.__main__ import main
from cadence_mcp_bridge.research_generation_preparation import prepare_research_generation


def test_prepare_generation_cli_checks_raw_evidence_and_preserves_existing_files(
    tmp_path, monkeypatch, capsys
):
    def native_forbidden(*args, **kwargs):
        pytest.fail("preparation tried to select a native runtime")

    monkeypatch.setattr("cadence_mcp_bridge.runtime_context.select_context", native_forbidden)
    request, evidence = _request()
    expected = prepare_research_generation(request, evidence)
    request_path = tmp_path / "request.json"
    request_raw = request.model_dump_json().encode()
    request_path.write_bytes(request_raw)
    invocation = [
        "operator-research-generation",
        "prepare",
        "--request",
        str(request_path),
        sha256(request_raw).hexdigest(),
    ]
    for pin, raw in evidence.items():
        evidence_path = tmp_path / pin
        evidence_path.write_bytes(raw)
        invocation += ["--evidence", str(evidence_path), pin]
    output = tmp_path / "prepared"
    output_args = ["--output-directory", str(output)]

    pin = next(iter(evidence))
    evidence_path = tmp_path / pin
    evidence_path.write_bytes(evidence[pin] + b"\n")
    assert main([*invocation, *output_args]) == 2
    assert not output.exists()
    evidence_path.write_bytes(evidence[pin])
    assert main([*invocation, "--evidence", str(evidence_path), pin, *output_args]) == 2
    assert not output.exists()
    capsys.readouterr()

    assert main([*invocation, *output_args]) == 0
    result = json.loads(capsys.readouterr().out)
    assert (
        result.pop("manifest_file_sha256")
        == sha256(expected.files["preparation.private.json"]).hexdigest()
    )
    assert result == expected.manifest.model_dump(mode="json")
    assert not result["execution_authorized"] and not result["remote_contact"]
    assert {p.name: p.read_bytes() for p in output.iterdir()} == expected.files
    assert main([*invocation, *output_args]) == 2
    assert {p.name: p.read_bytes() for p in output.iterdir()} == expected.files
    assert request_path.read_bytes() == request_raw
    assert all((tmp_path / pin).read_bytes() == raw for pin, raw in evidence.items())
