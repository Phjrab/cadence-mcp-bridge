"""Offline CLI for the canonical research generation preparation service."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cadence_mcp_bridge.candidate_cli import (
    _export_research,
    _output,
    _read_candidate_bytes,
    read_candidate_document,
)
from cadence_mcp_bridge.errors import BridgeError
from cadence_mcp_bridge.research_generation_preparation import (
    ResearchGenerationPreparationRequest,
    prepare_research_generation,
)

_MANIFEST = "preparation.private.json"
_EVIDENCE_LIMIT = 65_536


def run_prepare_research_generation(arguments: argparse.Namespace) -> int:
    try:
        request_file, request_sha256 = arguments.request
        request = ResearchGenerationPreparationRequest.model_validate_json(
            read_candidate_document(Path(request_file), expected_sha256=request_sha256)
        )
        evidence_paths = {pin: Path(file) for file, pin in arguments.evidence}
        if len(evidence_paths) != len(arguments.evidence) or evidence_paths.keys() != set(
            request.evidence_sha256
        ):
            raise ValueError("Preparation evidence inventory differs from the request")
        evidence = {
            pin: _read_candidate_bytes(path, expected_sha256=pin, limit=_EVIDENCE_LIMIT)
            for pin, path in evidence_paths.items()
        }
        prepared = prepare_research_generation(request, evidence)
        output = _output(arguments.output_directory, set())
        output.mkdir(mode=0o700)
        for name, raw in prepared.files.items():
            if name != _MANIFEST:
                _export_research(output / name, raw)
        digest = _export_research(output / _MANIFEST, prepared.files[_MANIFEST])
    except (OSError, ValueError, BridgeError):
        print(json.dumps({"status": "RESEARCH_GENERATION_PREPARATION_REJECTED"}))
        return 2

    result = prepared.manifest.model_dump(mode="json")
    result["manifest_file_sha256"] = digest
    print(json.dumps(result, sort_keys=True))
    return 0
