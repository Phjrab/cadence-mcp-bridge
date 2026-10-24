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
    assert report["file_open_guards"] == "READ_ONLY_BUILTINS_IO_OS_OPEN"
    assert report["strict_parser_rejected_frames"] == 6
    assert report["successful_preparation"] == "NOT_TESTED_BY_THIS_CHECKER"
    assert report["authenticated_worker_construction"] == (
        "INSTALLED_FIXED_RESOURCE_FACTORY_SYNTHETIC_CONFIG"
    )
    assert report["cached_worker_and_helper_poisoning"] == "IGNORED_BY_FRESH_AUTHENTICATED_MODULES"
    assert report["wrong_selected_worker_digest"] == "REJECTED_BEFORE_CODE_LOAD"
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


def test_checker_rejects_factory_reusing_cached_worker(source_checker, tmp_path, monkeypatch):
    def cached_factory(*args):
        return object.__new__(source_checker.worker.BindingObservationWorker)

    monkeypatch.setattr(source_checker.bootstrap, "construct_worker", cached_factory)
    with pytest.raises(ValueError, match="cached worker reused"):
        source_checker.verify(tmp_path / "cached-worker")


def test_checker_detects_selected_digest_code_loading(source_checker, tmp_path, monkeypatch):
    construct = source_checker.bootstrap.construct_worker

    def unsafe_factory(profile, registration, selection, request):
        import json

        if json.loads(selection)["helper_sha256"] == "0" * 64:
            source_checker.bootstrap.compile("pass", "must-not-load", "exec")
        return construct(profile, registration, selection, request)

    monkeypatch.setattr(source_checker.bootstrap, "construct_worker", unsafe_factory)
    with pytest.raises(AssertionError, match="process, transport, home or claim"):
        source_checker.verify(tmp_path / "digest-load")


def test_checker_blocks_schema_process_side_effect(source_checker, tmp_path, monkeypatch):
    def unexpected_process(arguments):
        import subprocess

        subprocess.Popen(["must-not-start"])

    monkeypatch.setattr(source_checker, "cli_main", unexpected_process)
    with pytest.raises(AssertionError, match="process, transport, home or claim"):
        source_checker.verify(tmp_path / "process-blocked")


@pytest.mark.parametrize("api", ["builtin", "io", "path", "os"])
@pytest.mark.parametrize("mode", ["w", "a", "x", "r+"])
def test_checker_blocks_file_writes_outside_workspace(
    source_checker, tmp_path, monkeypatch, api, mode,
):
    import io
    import os

    sibling = tmp_path / "outside-workspace"
    if mode == "r+":
        sibling.write_bytes(b"retained evidence")

    def unexpected_write(*arguments):
        if api == "path":
            # Path.open uses io.open, including a keyword mode argument.
            with sibling.open(mode=mode) as stream:
                stream.write("must not write")
        elif api == "os":
            flags = {
                "w": os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                "a": os.O_WRONLY | os.O_CREAT | os.O_APPEND,
                "x": os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                "r+": os.O_RDWR,
            }[mode]
            descriptor = os.open(sibling, flags)
            try:
                os.write(descriptor, b"must not write")
            finally:
                os.close(descriptor)
        else:
            selected = open if api == "builtin" else io.open
            with selected(sibling, mode) as stream:
                stream.write("must not write")

    monkeypatch.setattr(source_checker.bootstrap, "construct_worker", unexpected_write)
    with pytest.raises(AssertionError, match="write-capable file-open boundary"):
        source_checker.verify(tmp_path / "exclusive")
    if mode == "r+":
        assert sibling.read_bytes() == b"retained evidence"
    else:
        assert not sibling.exists()
    assert not list((tmp_path / "exclusive").iterdir())


def test_readonly_file_guard_allows_existing_file_reads(source_checker, tmp_path):
    import io
    import os

    retained = tmp_path / "retained"
    retained.write_bytes(b"read-only content")
    with source_checker._readonly_file_opens():
        with open(retained, "rb") as stream:
            assert stream.read() == b"read-only content"
        with io.open(retained, "rb") as stream:  # noqa: UP020 - distinct guarded API
            assert stream.read() == b"read-only content"
        descriptor = os.open(retained, os.O_RDONLY)
        try:
            assert os.read(descriptor, 100) == b"read-only content"
        finally:
            os.close(descriptor)
    assert retained.read_bytes() == b"read-only content"


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
