"""Synthetic model inventory tests; protected PDK statements are never fixtures."""

from __future__ import annotations

import importlib
import importlib.util
import json
import posixpath
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]


def scanner() -> ModuleType:
    path = ROOT / "remote/phase-campaign/ade-pvt-prep-v4/inventory.py"
    spec = importlib.util.spec_from_file_location("pvt_inventory_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def virtual_posix(module: ModuleType) -> None:
    # A synthetic Linux filesystem for closure tests hosted on Windows.
    module.__dict__["os"] = SimpleNamespace(
        path=SimpleNamespace(
            normpath=posixpath.normpath,
            join=posixpath.join,
            dirname=posixpath.dirname,
            realpath=lambda path: path,
        )
    )


def test_comments_and_case_preserved_sections() -> None:
    module = scanner()
    data = module.metadata("""// section FF
/* statistics { process { vary hidden } } */
library synthetic
section NN
include "nominal.scs" section=base
endsection NN
endlibrary synthetic
""")
    assert [body["section"] for body in data["sections"]] == [None, "NN"]
    assert data["sections"][1]["includes"] == [("nominal.scs", "base")]
    assert data["sections"][0]["statistics_blocks"] == 0


@pytest.mark.parametrize(
    "text",
    [
        "section NN\nsection FF",
        "endsection NN",
        "section NN",
        "section NN\nendsection FF",
        "section NN\nendsection\nsection NN\nendsection",
    ],
)
def test_ambiguous_sections_rejected(text: str) -> None:
    with pytest.raises(ValueError):
        scanner().metadata(text)


def test_include_closure_counts_only_selected_sections_and_never_claims_variation() -> None:
    module = scanner()
    virtual_posix(module)
    records = {
        module.MAIN: {
            "metadata": module.metadata("""section NN
include "shared.scs" section=nominal
endsection
section MC
include "shared.scs" section=statistical
endsection""")
        },
        module.MODELS + "/shared.scs": {
            "metadata": module.metadata("""section nominal
model nmos1v synthetic
model pmos1v synthetic
endsection
section statistical
statistics { process { vary perturb dist=gauss } mismatch { vary offset dist=gauss } }
model nmos1v synthetic parameter=perturb
endsection""")
        },
    }
    nominal = module.closure(records, "NN")
    assert nominal["statistics_blocks"] == 0
    assert nominal["observed_device_definitions"] == ["nmos1v", "pmos1v"]
    statistical = module.closure(records, "MC")
    assert statistical["process_blocks"] == statistical["mismatch_blocks"] == 1
    assert statistical["vary_declarations"] == 2
    assert statistical["effective_variation_verified"] is False


@pytest.mark.parametrize("target", ["../outside.scs", "/etc/passwd", "missing.scs"])
def test_unsafe_or_missing_include_fails_closed(target: str) -> None:
    module = scanner()
    virtual_posix(module)
    records = {
        module.MAIN: {"metadata": module.metadata(f'section NN\ninclude "{target}"\nendsection')}
    }
    with pytest.raises(ValueError):
        module.closure(records, "NN")


def test_no_model_coefficient_or_source_statement_in_metadata() -> None:
    data = scanner().metadata("model nmos1v synthetic confidentialCoefficient=0.123456789")
    assert "confidentialCoefficient" not in str(data)
    assert "0.123456789" not in str(data)


def test_fixed_read_probe_has_no_simulation_or_state_load_calls() -> None:
    text = (ROOT / "remote/phase-campaign/ade-pvt-prep-v1/api.ocn").read_text()
    assert "isCallable(api)" in text
    assert "dbSave" not in text and "loadState" not in text and "run(" not in text


def test_inventory_rejects_caller_arguments_before_remote_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = scanner()
    monkeypatch.setattr(module.sys, "argv", ["inventory.py", "arbitrary-path"])
    with pytest.raises(ValueError, match="no inventory arguments"):
        module.main()


def test_inline_subckt_binding_uses_actual_circuit_model_token() -> None:
    module = scanner()
    virtual_posix(module)
    records = {
        module.MAIN: {
            "metadata": module.metadata("""section NN
statistics { mismatch { vary syntheticShift dist=gauss } }
inline subckt actualModel (d g s b)
parameters shift=syntheticShift
ends actualModel
endsection""")
        }
    }
    result = module.closure(records, "NN", {"actualModel": 8, "missingModel": 6})
    bindings = result["used_mos_model_bindings"]
    assert bindings[0]["definition_matches"] == 1
    assert bindings[0]["vary_references_in_definition"] == 1
    assert bindings[1]["definition_matches"] == 0
    assert "actualModel" not in str(result)


def test_common_statistics_counted_once_when_file_has_two_selected_sections() -> None:
    module = scanner()
    virtual_posix(module)
    records = {
        module.MAIN: {
            "metadata": module.metadata("""section NN
include "shared.scs" section=A
include "shared.scs" section=B
endsection""")
        },
        module.MODELS + "/shared.scs": {
            "metadata": module.metadata("""statistics { mismatch {} }
section A
endsection
section B
endsection""")
        },
    }
    assert module.closure(records, "NN")["mismatch_blocks"] == 1


def test_circuit_mos_binding_requires_existing_counts() -> None:
    module = scanner()
    text = "\n".join(
        f"{'NM' if i < 8 else 'PM'}{i} (d g s b) {'aModel' if i < 8 else 'bModel'} l=1u"
        for i in range(14)
    )
    assert module.circuit_models(text) == {"aModel": 8, "bModel": 6}
    with pytest.raises(ValueError):
        module.circuit_models(text + "\nNM99 (d g s b) aModel")


def operator(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    return importlib.import_module("ade_pvt_prep")


def test_explicit_authority_required_before_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    module = operator(monkeypatch)

    def deny() -> str:
        raise ValueError("explicit authority absent")

    monkeypatch.setattr(module, "authority", deny)
    monkeypatch.setattr(module.native, "ssh", lambda *_args: pytest.fail("unexpected SSH"))
    with pytest.raises(ValueError, match="explicit authority absent"):
        module.read()


def test_journal_replay_rejected_before_inventory_transport(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = operator(monkeypatch)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    (tmp_path / ".codex").mkdir()
    monkeypatch.setattr(module, "authority", lambda: "bound")
    monkeypatch.setattr(module, "checkpoint", lambda: {})
    module.dc.save_new(module.record("deploy"), {"state": "succeeded", "policy_sha256": "bound"})
    module.dc.save_new(module.record("read"), {"state": "reserved", "policy_sha256": "bound"})
    monkeypatch.setattr(module.native, "ssh", lambda *_args: pytest.fail("unexpected SSH"))
    with pytest.raises(FileExistsError):
        module.read()


def test_wrong_deployment_digest_rejected_before_inventory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = operator(monkeypatch)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    (tmp_path / ".codex").mkdir()
    monkeypatch.setattr(module, "authority", lambda: "bound")
    module.dc.save_new(module.record("deploy"), {"state": "succeeded", "policy_sha256": "other"})
    monkeypatch.setattr(module.native, "ssh", lambda *_args: pytest.fail("unexpected SSH"))
    with pytest.raises(ValueError, match="verified deployment"):
        module.read()


def test_status_exhaustion_rejects_before_transport(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = operator(monkeypatch)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    (tmp_path / ".codex").mkdir()
    monkeypatch.setattr(module, "authority", lambda: "bound")
    module.dc.save_new(module.record("read"), {"state": "reserved", "policy_sha256": "bound"})
    for attempt in range(1, 4):
        module.dc.save_new(module.record("status-" + str(attempt)), {"state": "reserved"})
    monkeypatch.setattr(module.native, "ssh", lambda *_args: pytest.fail("unexpected SSH"))
    with pytest.raises(ValueError, match="communication allowance"):
        module.status()


def test_unknown_source_payload_rejected_from_projection(monkeypatch: pytest.MonkeyPatch) -> None:
    module = operator(monkeypatch)
    with pytest.raises(ValueError, match="unknown or invalid fields"):
        module.validate({"phase": "ADE-PVT-PREP-01", "raw_model": "never return source"})


def test_original_bytes_pinned_even_when_json_values_compare_equal() -> None:
    module = scanner()
    first, second = b'{"value":0.3}', b'{"value":0.29999999999999999}'
    assert json.loads(first) == json.loads(second)
    assert module.sha(first) != module.sha(second)


def test_four_immutable_deployed_versions_match_policies() -> None:
    module = scanner()
    for version in range(1, 5):
        policy = json.loads((ROOT / f"docs/policy/ADE_PVT_PREP_V{version}.json").read_bytes())
        assert policy["new_circuit_runs"] == 0
        for name, digest in policy["files"].items():
            content = (ROOT / f"remote/phase-campaign/ade-pvt-prep-v{version}" / name).read_bytes()
            assert b"\r" not in content and module.sha(content) == digest
