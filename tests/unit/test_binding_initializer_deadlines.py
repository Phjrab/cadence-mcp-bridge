"""Synthetic deadline/interruption evidence; these cases never contact a VM."""

import copy
import json
import os
from types import SimpleNamespace

import pytest
from test_binding_initializer import _accounting, fixture

from cadence_mcp_bridge import _binding_initializer as recipe
from cadence_mcp_bridge import _binding_storage_admin as storage
from cadence_mcp_bridge import _installation_repair as repair
from cadence_mcp_bridge import _native_copy as copying

__all__ = ["fixture"]


@pytest.fixture
def clock(monkeypatch):
    state = SimpleNamespace(now=100.0)
    proxy = SimpleNamespace(**{name: getattr(os, name) for name in dir(os)})
    proxy.times = lambda: (0, 0, 0, 0, state.now)
    proxy.getuid = proxy.geteuid = lambda: 0
    monkeypatch.setattr(recipe, "os", proxy)
    monkeypatch.setattr(storage, "os", proxy)
    return state


@pytest.mark.parametrize("operation,seconds", [
    ("plan", 60), ("postcheck", 60), ("apply", 3600), ("rollback", 3600),
])
def test_operation_has_one_absolute_deadline_and_rejects_exact_boundary(clock, operation, seconds):
    progress = recipe.Progress(operation)
    assert progress.budget_seconds == seconds and progress.deadline == 100 + seconds
    clock.now = progress.deadline - 0.001
    progress.check()
    clock.now = progress.deadline
    with pytest.raises(ValueError):
        progress.check()
    assert progress.deadline == 100 + seconds


def test_invalid_operation_cannot_select_an_arbitrary_timeout(clock):
    with pytest.raises(ValueError):
        recipe.Progress("simulate")


def test_cancelled_operation_cannot_restart_budget_in_a_later_phase(clock):
    progress = recipe.Progress("apply")
    original_deadline = progress.deadline
    clock.now += 200
    progress.phase("receipt_authentication")
    assert progress.deadline == original_deadline
    progress.cancelled = True
    with pytest.raises(ValueError):
        progress.check()
    assert progress.deadline == original_deadline


def test_accounting_guard_uses_the_same_absolute_deadline_and_cancellation(fixture, clock):
    profile, registration, _, _, _ = fixture
    progress = recipe.Progress("apply")
    clock.now += 120
    accounting = recipe.build_accounting(profile, registration, storage, progress=progress)
    assert accounting.deadline == progress.deadline
    accounting.check()
    progress.cancelled = True
    with pytest.raises(ValueError):
        accounting.check()


def test_legacy_direct_accounting_construction_retains_the_inspection_bound(fixture, clock):
    profile, registration, _, _, _ = fixture
    accounting = recipe.build_accounting(profile, registration, storage)
    assert accounting.deadline == clock.now + recipe.INSPECTION_SECONDS


def test_started_and_completed_union_counts_distinguish_an_interrupted_pass(clock):
    progress = recipe.Progress("apply")
    progress.bind_targets(20)
    progress.start_pass()
    progress.library(3)
    assert progress.report()["union_passes_started"] == 1
    assert progress.report()["union_passes_completed"] == 0
    progress.complete_pass()
    progress.start_pass()
    progress.library(1)
    report = progress.report()
    assert report["maximum_union_passes"] == 176
    assert report["union_passes_started"] == 2
    assert report["union_passes_completed"] == 1
    assert report["library_ordinal"] == 1


def test_union_work_bound_rejects_before_starting_an_extra_pass(clock):
    progress = recipe.Progress("apply")
    progress.bind_targets(1)
    for _ in range(24):
        progress.start_pass()
        progress.complete_pass()
    with pytest.raises(ValueError):
        progress.start_pass()
    assert progress.report()["maximum_union_passes"] == 24
    assert progress.report()["union_passes_started"] == 24


@pytest.mark.parametrize("count", [129, True, -1, 1.5, "20"])
def test_target_count_cannot_expand_the_fixed_maximum_work_bound(clock, count):
    progress = recipe.Progress("apply")
    with pytest.raises(ValueError):
        progress.bind_targets(count)
    assert progress.report()["maximum_union_passes"] <= 1040


def test_diagnostic_is_closed_bounded_and_does_not_copy_paths_or_exception_text(clock):
    progress = recipe.Progress("apply")
    progress.phase("pre_mutation_guard")
    progress.bind_targets(128)
    clock.now += 1.234
    report = progress.report()
    assert set(report) == {
        "kind", "schema_version", "operation", "phase", "union_passes_started",
        "union_passes_completed", "maximum_union_passes", "library_ordinal",
        "elapsed_ms", "budget_seconds", "mutation_may_have_started",
    }
    assert report["kind"] == "INITIALIZER_FAILURE_PROGRESS"
    assert report["schema_version"] == 1
    assert report["operation"] == "apply" and report["phase"] == "pre_mutation_guard"
    assert report["elapsed_ms"] >= 1233 and report["elapsed_ms"] <= 1235
    assert report["maximum_union_passes"] == 1040
    assert report["mutation_may_have_started"] is False
    raw = repair.canonical(report)
    assert b"/" not in raw and len(b"INITIALIZER_FAILURE_PROGRESS " + raw + b"\n") <= 2048
    with pytest.raises(ValueError):
        progress.phase("/private/install/path")


@pytest.mark.parametrize("point,expected_phase,may_have_started", [
    ("first_guard", "initial_guard", False),
    ("receipt", "receipt_authentication", False),
    ("pre_mutation", "pre_mutation_guard", False),
    ("mutation", "target_mutation", True),
    ("completion", "completion_verification", True),
])
def test_interruption_classifies_target_mutation_conservatively_without_replay(
    fixture, clock, monkeypatch, point, expected_phase, may_have_started,
):
    profile, registration, _, core, plan = fixture
    progress = recipe.Progress("apply")
    events = []
    accounting = _accounting(profile, registration)

    def interrupt():
        clock.now = progress.deadline
        progress.check()

    def guard():
        events.append("accounting_guard")
        if point == "first_guard" and events.count("accounting_guard") == 1:
            interrupt()

    def verify(*_args, **_kwargs):
        if point == "pre_mutation" and progress.report()["phase"] == "pre_mutation_guard":
            interrupt()
        return dict(content_preserved=True)

    def receipt(*_):
        events.append("receipt")
        if point == "receipt":
            interrupt()

    def mutation(*_):
        events.append("mutation")
        assert progress.report()["mutation_may_have_started"] is True
        if point == "mutation":
            interrupt()

    def completion(*_):
        events.append("completion")
        if point == "completion":
            interrupt()

    accounting.guard = guard
    core.authenticate_applied_plan = receipt
    core._mutate_locked = mutation
    core.verify_completed_targets = completion
    core.verify_applied_receipt = lambda *_: events.append("final_receipt")
    monkeypatch.setattr(recipe, "verify_delta", verify)
    request = dict(plan=copy.deepcopy(plan), expected_plan_sha256=repair.digest(plan),
                   operator_authority="SYNTHETIC_INTERRUPTION_ONLY")
    with pytest.raises(ValueError):
        recipe.mutate(request, copying, core, accounting=accounting, progress=progress)
    report = progress.report()
    assert report["phase"] == expected_phase
    assert report["mutation_may_have_started"] is may_have_started
    assert events.count("mutation") == int(may_have_started)
    assert "final_receipt" not in events
    assert "execution_authorized" not in json.dumps(report)


def test_mutation_latch_remains_true_after_later_phase_or_deadline(clock):
    progress = recipe.Progress("rollback")
    progress.enter_mutation()
    progress.phase("final_verification")
    clock.now = progress.deadline
    with pytest.raises(ValueError):
        progress.check()
    assert progress.report()["mutation_may_have_started"] is True


@pytest.mark.skipif(os.name != "posix", reason="Owned Linux complete-library file read")
def test_owned_slow_file_scan_cannot_restart_the_shared_deadline(tmp_path, clock, monkeypatch):
    library = tmp_path / "owned-library"
    library.mkdir(mode=0o700)
    code = library / "libInit.il"
    code.write_bytes(b"; owned synthetic bytes; never executed\n")
    code.chmod(0o600)
    original = copying.dependency_snapshot
    calls = []
    progress = recipe.Progress("postcheck")

    def bounded_slow_read(path):
        result = original(path)
        calls.append(path)
        # Advance the injectable elapsed clock after a real owned-file scan.
        # This is deadline coverage, without an unbounded sleep or VM access.
        clock.now = progress.deadline
        return result

    monkeypatch.setattr(copying, "dependency_snapshot", bounded_slow_read)
    with pytest.raises(ValueError):
        recipe._observe([dict(path=str(library), name="OwnedSynthetic")], copying, repair,
                        progress=progress)
    assert calls == [str(library)]
    assert progress.report()["union_passes_started"] == 1
    assert progress.report()["union_passes_completed"] == 0
    assert code.read_bytes() == b"; owned synthetic bytes; never executed\n"
