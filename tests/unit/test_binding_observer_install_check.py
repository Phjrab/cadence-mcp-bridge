"""Checker self-tests use a source-origin seam; installed checks run separately."""

import importlib.util
from pathlib import Path

import pytest

CHECKER = Path(__file__).resolve().parents[2] / "scripts/verify-binding-observer-install.py"


@pytest.fixture
def checker():
    spec = importlib.util.spec_from_file_location("binding_observer_install_check", CHECKER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def source_checker(checker, monkeypatch):
    # This seam cannot attest installed provenance; the actual checker has no
    # bypass argument and rejects source imports outside its interpreter prefix.
    monkeypatch.setattr(checker, "_verify_origins", lambda: None)
    return checker


def test_synthetic_checker_checks_protocol_cli_pins_and_blocked_worker(source_checker, tmp_path):
    report = source_checker.verify(tmp_path / "exclusive")
    assert report["status"] == "PASS"
    assert report["scope"] == "INSTALLED_BINDING_OBSERVER_SYNTHETIC_NOT_CADENCE"
    assert report["strict_parser_rejected_frames"] == 6
    assert report["successful_preparation"] == "NOT_TESTED_BY_THIS_CHECKER"
    assert report["authenticated_worker_construction"] == "NOT_TESTED_BY_THIS_CHECKER"
    assert report["new_simulations"] == report["new_extractions"] == 0
    assert not report["remote_contact"] and not report["claim_spent"]
    assert not report["qualification_established"]
    assert not list((tmp_path / "exclusive").iterdir())


def test_source_origin_rejected_before_workspace_created(checker, tmp_path, monkeypatch):
    monkeypatch.setattr(checker.sys, "prefix", str(tmp_path / "fictional-installed-prefix"))
    with pytest.raises(ValueError, match="installed wheel origin required"):
        checker.verify(tmp_path / "not-created")
    assert not (tmp_path / "not-created").exists()


def test_existing_workspace_is_preserved(source_checker, tmp_path):
    workspace = tmp_path / "retained"
    workspace.mkdir()
    evidence = workspace / "retained-evidence"
    evidence.write_bytes(b"existing evidence")
    with pytest.raises(FileExistsError):
        source_checker.verify(workspace)
    assert evidence.read_bytes() == b"existing evidence"


def test_checker_rejects_wrong_installed_helper_pin(source_checker, tmp_path, monkeypatch):
    monkeypatch.setitem(source_checker.worker.HELPER_PINS, "copy.py", "0" * 64)
    with pytest.raises(ValueError, match="installed helper pin mismatch"):
        source_checker.verify(tmp_path / "bad-pin")


def test_checker_detects_permissive_frame_parser(source_checker, tmp_path, monkeypatch):
    correct = source_checker.contract.parse_frame
    good = correct(source_checker._frame(source_checker._request()), source_checker._request())
    monkeypatch.setattr(source_checker.contract, "parse_frame", lambda *args: good)
    with pytest.raises(ValueError, match="malformed synthetic frame accepted"):
        source_checker.verify(tmp_path / "permissive")


def test_checker_blocks_schema_process_side_effect(source_checker, tmp_path, monkeypatch):
    def unexpected_process(arguments):
        import subprocess

        subprocess.Popen(["must-not-start"])

    monkeypatch.setattr(source_checker, "cli_main", unexpected_process)
    with pytest.raises(AssertionError, match="process, transport, home or claim"):
        source_checker.verify(tmp_path / "process-blocked")


@pytest.mark.parametrize("boundary", ["claim", "home", "backend", "stage"])
def test_checker_blocks_private_side_effect_boundaries(
    source_checker, tmp_path, monkeypatch, boundary,
):
    def unexpected_action(arguments):
        if boundary == "claim":
            source_checker.binding_observation_claim.claim(None, None, None)
        elif boundary == "home":
            source_checker.physical_metadata._operator_home()
        elif boundary == "backend":
            source_checker.ExecutionContext.backend(None, None)
        else:
            source_checker.worker.BindingObservationWorker._stage(None, None, None)

    monkeypatch.setattr(source_checker, "cli_main", unexpected_action)
    with pytest.raises(AssertionError, match="process, transport, home or claim"):
        source_checker.verify(tmp_path / boundary)
