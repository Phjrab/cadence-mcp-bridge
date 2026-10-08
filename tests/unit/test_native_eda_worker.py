"""Compiled worker uses disposable OA/PSF placeholders and synthetic programs."""

import os
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from test_native_gate import confirmed_domain, qualified, root

from cadence_mcp_bridge import _native_copy as copying
from cadence_mcp_bridge import _native_eda_worker as eda
from cadence_mcp_bridge import _native_operations as operations
from cadence_mcp_bridge import _native_rendering as rendering
from cadence_mcp_bridge import _runner_bootstrap as installer
from cadence_mcp_bridge import _shared_reservations as accounting
from cadence_mcp_bridge import _storage_worker as storage

# Re-export imported dependent fixtures for pytest discovery.
__all__ = ["confirmed_domain", "qualified", "root"]


@pytest.fixture
def frame_worker():
    worker = eda.EdaWorker(None, operations, rendering, copying, installer)
    worker.operation_id = str(uuid4())
    plan = {"analysis": "dc"}
    reader = {
        "nodes": [{"logical_id": "out", "selector": "/out"}],
        "sources": [],
        "maximum_samples": 16,
    }
    route = {"reader": reader}
    header = "|".join(
        (
            "MCP_GREL_FRAME",
            "1",
            worker.operation_id,
            operations.digest(operations.canonical(plan)),
            "1" * 64,
            operations.digest(operations.canonical(reader)),
        )
    )
    return worker, plan, route, header


def test_native_frame_has_bound_identity_inventory_and_finite_values(frame_worker):
    worker, plan, route, header = frame_worker
    worker.frame((header + "\nV|out|0.5\nEND\n").encode(), plan, route, "1" * 64)


@pytest.mark.parametrize(
    "rows",
    [
        "V|wrong|1\nEND",
        "V|out|NaN\nEND",
        "V|out|inf\nEND",
        "V|out|1\nV|out|2\nEND",
        "V|out|1",
        "END",
    ],
)
def test_native_frame_rejects_malformed_or_partial(frame_worker, rows):
    worker, plan, route, header = frame_worker
    with pytest.raises((ValueError, IndexError)):
        worker.frame((header + "\n" + rows + "\n").encode(), plan, route, "1" * 64)


@pytest.mark.parametrize("field", ["operation", "plan", "input", "reader"])
def test_frame_identity_cannot_be_rebound(frame_worker, field):
    worker, plan, route, header = frame_worker
    parts = header.split("|")
    index = {"operation": 2, "plan": 3, "input": 4, "reader": 5}[field]
    parts[index] = "9" * 64
    with pytest.raises(ValueError, match="frame_binding"):
        worker.frame(("|".join(parts) + "\nV|out|1\nEND\n").encode(), plan, route, "1" * 64)


@pytest.mark.skipif(os.name != "posix", reason="compiled EDA driver requires POSIX")
@pytest.mark.parametrize("failure", [None, "effective", "reader", "source"])
def test_owned_copy_netlist_effective_reader_and_preservation_pipeline(
    qualified, monkeypatch, failure
):
    root, gate, plan, _ = qualified
    gate.storage = storage
    gate.profile["paths"]["job_root"] = str(root / accounting.JOBS)
    gate.profile["tools"] = {
        "ocean": {"path": "/synthetic/ocean"},
        "spectre": {"path": "/synthetic/spectre"},
    }
    route = gate.route(plan)
    route["profile"] = {
        "binding": {
            "library": "SourceLib",
            "cell": "SourceCell",
            "view": "schematic",
            "ade": {"state": "state1"},
        }
    }
    route["libraries"] = [{"name": "SourceLib", "path": str(Path(route["source_cell"]).parent)}]
    route["ade"].update(
        inputs={
            "analysis": "dc",
            "mode": "saved_operating_point",
            "statement_sha256": operations.digest(b"dc "),
        },
        static_statements_sha256=rendering.static_fingerprint(["R0 (in out) resistor r=1000"]),
    )
    route["reader"] = {
        "nodes": [{"logical_id": "out", "selector": "/out"}],
        "sources": [],
        "maximum_samples": 16,
    }
    worker = eda.EdaWorker(gate, operations, rendering, copying, installer)
    calls = []
    op = str(uuid4())
    journal = operations.OperationJournal(str(root), op, plan, accounting)
    originals = {key: copying.snapshot(route[key]) for key in ("source_cell", "source_state")}

    def program(session, journal, argv, label, seconds, amount):
        calls.append(label)
        session.check()
        assert amount == plan["request"]["result_reservation_bytes"]
        if label == "netlist":
            folder = Path(journal.job) / "project/nested/netlist"
            folder.mkdir(parents=True)
            resistor = "2000" if failure == "effective" else "1000"
            (folder / "input.scs").write_text(
                "simulator lang=spectre\nR0 (in out) resistor r=" + resistor + "\ndc0 dc\n",
                encoding="ascii",
            )
            if failure == "source":
                (Path(route["source_cell"]) / "synthetic-oa").write_bytes(b"injected source drift")
        elif label == "spectre":
            (Path(journal.work) / "psf").mkdir()
            (Path(journal.work) / "psf/synthetic-result").write_bytes(b"synthetic PSF placeholder")
        else:
            header = "|".join(
                (
                    "MCP_GREL_FRAME",
                    "1",
                    op,
                    journal.plan_sha,
                    operations.digest(installer.regular(journal.work + "/input.scs")),
                    operations.digest(operations.canonical(route["reader"])),
                )
            )
            (Path(journal.work) / "generic-frame.txt").write_text(
                header + ("\nEND\n" if failure == "reader" else "\nV|out|0.5\nEND\n"),
                encoding="ascii",
            )

    monkeypatch.setattr(worker, "program", program)
    with accounting.ReservationSession(str(root)) as session:
        permit, _ = gate.check(session, plan, "submit")
        journal.create(permit)
        receipt = session.reserve(op, permit)
        journal.append(session, "RESERVED", operations.digest(operations.canonical(receipt)))
        journal.append(session, "DISPATCHED", "e" * 64)
        journal.append(session, "RUNNING", "e" * 64)
        if failure:
            with pytest.raises((ValueError, IndexError)):
                worker.run(session, journal, plan)
        else:
            worker.run(session, journal, plan)
    if failure != "source":
        for key in originals:
            assert copying.snapshot(route[key]) == originals[key]
    assert accounting.read(str(root / accounting.LEDGER))["count"] == 83
    if failure in ("effective", "source"):
        assert calls == ["netlist"]
        assert not (Path(journal.work) / "psf").exists()
    else:
        assert calls == ["netlist", "spectre", "reader"]
        assert journal.observation()["progress"]["phase"] == (
            "EXTRACTION_FAILED" if failure else "SUCCEEDED"
        )
    if failure is None:
        assert (
            operations.read(journal.work + "/effective-input.json")[
                "planned_execution_input_sha256"
            ]
            != operations.read(journal.work + "/extraction-receipt.json")["native_input_sha256"]
        )
        owned_info = Path(journal.job) / (
            "state-root/MCP_GREL_Work/Grel_"
            + op.replace("-", "_")
            + "/spectre/state1/ADE_state.info"
        )
        assert b"MCP_GREL_Work" in owned_info.read_bytes()
        assert b"SourceLib" in (Path(route["source_state"]) / "ADE_state.info").read_bytes()


@pytest.mark.skipif(os.name != "posix", reason="actual bounded process group requires POSIX")
@pytest.mark.parametrize("case", ["success", "nonzero", "deadline"])
def test_fixed_program_bounds_owned_group_and_retains_private_logs(qualified, case):
    root, gate, plan, _ = qualified
    gate.storage = storage
    worker = eda.EdaWorker(gate, operations, rendering, copying, installer)
    journal = operations.OperationJournal(str(root), str(uuid4()), plan, accounting)
    with accounting.ReservationSession(str(root)) as session:
        permit, _ = gate.check(session, plan, "submit")
        journal.create(permit)
        script = {
            "success": "print('synthetic output')",
            "nonzero": "raise SystemExit(3)",
            "deadline": "import time;time.sleep(5)",
        }[case]
        if case == "success":
            worker.program(
                session, journal, [sys.executable, "-I", "-c", script], "synthetic", 2, 1048576
            )
        else:
            with pytest.raises(
                ValueError, match="program_failed" if case == "nonzero" else "owned_process_limit"
            ):
                worker.program(
                    session,
                    journal,
                    [sys.executable, "-I", "-c", script],
                    "synthetic",
                    0.2 if case == "deadline" else 2,
                    1048576,
                )
    assert (Path(journal.work) / "synthetic.stdout").exists()
    assert (Path(journal.work) / "synthetic.stderr").exists()
    assert accounting.read(str(root / accounting.LEDGER))["count"] == 82


@pytest.mark.skipif(os.name != "posix", reason="Linux process identity and group ownership")
@pytest.mark.parametrize("ignores_term", [False, True])
def test_exited_leader_does_not_abandon_live_descendant(qualified, ignores_term):
    root, gate, plan, _ = qualified
    gate.storage = storage
    worker = eda.EdaWorker(gate, operations, rendering, copying, installer)
    journal = operations.OperationJournal(str(root), str(uuid4()), plan, accounting)
    # Parent exits immediately. Its child retains the group/logs; no reaping
    # or next execution is allowed until the child has stopped.
    child = (
        "import os,signal,time;"
        + ("signal.signal(signal.SIGTERM,signal.SIG_IGN);" if ignores_term else "")
        + "print(os.getpid(),flush=True);time.sleep(30)"
    )
    parent = (
        "import subprocess,sys;subprocess.Popen([sys.executable,'-I','-c'," + repr(child) + "])"
    )
    with accounting.ReservationSession(str(root)) as session:
        permit, _ = gate.check(session, plan, "submit")
        journal.create(permit)
        with pytest.raises(ValueError, match="owned_process_limit"):
            worker.program(
                session, journal, [sys.executable, "-I", "-c", parent], "descendant", 0.5, 1048576
            )
        pid = int((Path(journal.work) / "descendant.stdout").read_text().strip())
        try:
            state = worker.process_identity(pid)[0]
        except FileNotFoundError:
            state = "gone"
        assert state in ("Z", "X", "gone")
        session.check()
    assert accounting.read(str(root / accounting.LEDGER))["count"] == 82


@pytest.mark.skipif(os.name != "posix", reason="Linux private log descriptors")
def test_partial_log_setup_closes_open_descriptor_without_spawning(qualified, monkeypatch):
    root, gate, plan, _ = qualified
    worker = eda.EdaWorker(gate, operations, rendering, copying, installer)
    journal = operations.OperationJournal(str(root), str(uuid4()), plan, accounting)
    with accounting.ReservationSession(str(root)) as session:
        permit, _ = gate.check(session, plan, "submit")
        journal.create(permit)
        (Path(journal.work) / "partial.stderr").write_bytes(b"retained")
        before = set(os.listdir("/proc/self/fd"))
        monkeypatch.setattr(
            eda.subprocess,
            "Popen",
            lambda *args, **kwargs: pytest.fail("failed setup must not spawn"),
        )
        with pytest.raises(FileExistsError):
            worker.program(session, journal, ["unused"], "partial", 1, 1048576)
        assert set(os.listdir("/proc/self/fd")) == before
        assert (Path(journal.work) / "partial.stderr").read_bytes() == b"retained"
