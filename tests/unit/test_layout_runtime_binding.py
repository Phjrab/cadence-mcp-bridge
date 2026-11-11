"""Pinned runtime input checks on disposable documents, never VM setup."""

import hashlib
import json
from pathlib import Path

import pytest
from test_runtime_context import make_settings

from cadence_mcp_bridge.runtime_context import RuntimeRejected, load_runtime


def bind(path: Path, document: Path):
    payload = json.loads(path.read_bytes())
    payload["contexts"][0].update(
        layout_provider_binding=str(document),
        layout_provider_sha256=hashlib.sha256(document.read_bytes()).hexdigest(),
    )
    path.write_text(json.dumps(payload), encoding="utf-8")
    return payload


def test_layout_pin_pair_and_content_drift(tmp_path):
    settings = make_settings(tmp_path)
    document = tmp_path / "layout.json"
    document.write_text('{"schema_version":1}', encoding="utf-8")
    payload = bind(settings, document)
    contexts = load_runtime(settings)
    assert contexts[0].binding.layout_provider_binding == document
    document.write_text('{"schema_version":2}', encoding="utf-8")
    with pytest.raises(RuntimeRejected) as failure:
        load_runtime(settings)
    assert failure.value.reason == "stale_layout_provider_digest"
    del payload["contexts"][0]["layout_provider_sha256"]
    settings.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RuntimeRejected):
        load_runtime(settings)


def test_layout_input_journal_collision_and_relative_path_reject(tmp_path):
    settings = make_settings(tmp_path)
    document = tmp_path / "layout.json"
    document.write_text("{}", encoding="utf-8")
    payload = bind(settings, document)
    payload["contexts"][0]["analysis_journal"] = str(document)
    settings.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RuntimeRejected) as failure:
        load_runtime(settings)
    assert failure.value.reason == "journal_contract_collision"
    payload["contexts"][0]["layout_provider_binding"] = "relative.json"
    settings.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RuntimeRejected) as failure:
        load_runtime(settings)
    assert failure.value.reason == "absolute_native_binding_paths_required"
