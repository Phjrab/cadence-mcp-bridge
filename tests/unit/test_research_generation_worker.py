"""Offline guest wire, phase custody and retry tests."""

import base64
import json
import weakref
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from cadence_mcp_bridge import _research_generation_worker as guest


def encoded(raw):
    return base64.b64encode(raw).decode("ascii")


@pytest.fixture
def wire(monkeypatch):
    monkeypatch.setattr(guest.time, "time", lambda: 100.0)
    program = b"fixed fixture\n"
    binding = dict(
        operation_id="11111111-2222-4333-8444-555555555555",
        context_id="research-fixture",
        resource_domain_sha256="1" * 64,
        native_manifest_sha256="2" * 64,
        plan_sha256="3" * 64,
        bench_plan_sha256="4" * 64,
        conditions_sha256="5" * 64,
        output_library="Owned",
        owned_library_path="/workspace/OwnedRun/Owned",
        save_program_sha256=guest.sha(program),
        reopen_program_sha256="6" * 64,
        netlist_program_sha256="7" * 64,
    )
    scope = dict(
        schema_version=1,
        binding=binding,
        layout_manifest_sha256="8" * 64,
        layout_worker_sha256="9" * 64,
        identity_manifest_sha256="a" * 64,
        operator_authority="fixture",
        valid_until_unix=150,
        source_route={},
        technology={},
        dut_cell="Dut",
        bench_cell="Bench",
        dut_subcircuits=["Dut"],
        markers={
            "save": ["MOS_BLOCK_SAVED|fixture"],
            "reopen": ["MOS_BLOCK_REOPENED_CHECKED|fixture"],
            "netlist": ["MCP_GENERIC_ADE_NETLIST|fixture"],
        },
        netlist_statements_sha256="b" * 64,
        protected_sha256="c" * 64,
        additional_protected=[],
        counter={},
        ledger_records_sha256="d" * 64,
        retained_jobs_sha256="e" * 64,
        prior_supplemental_bytes=0,
        external_bytes=2097152,
        job_bytes=4194304,
    )
    scope_raw = guest.canonical(scope)
    pin = guest.sha(scope_raw)
    wire_binding = {**binding, "scope_sha256": pin}
    ack = dict(
        operation_id=binding["operation_id"],
        binding_sha256=guest.sha(guest.canonical(wire_binding)),
        scope_sha256=pin,
        approved_phases=list(guest.PHASES),
        valid_until_unix=150,
    )
    body = dict(
        managed_root="/workspace/.cadence_mcp",
        binding=wire_binding,
        scope_base64=encoded(scope_raw),
        authority_base64=encoded(guest.canonical(ack)),
        program_base64=encoded(program),
    )
    return [pin, "save", ""], body, program


def test_fixed_guest_accepts_concrete_host_wire(wire):
    argv, body, program = wire
    result = guest.parse_request(argv, guest.canonical(body))
    assert result[0] == body["managed_root"]
    assert result[2] == body["binding"]
    assert result[4:] == ("save", None, program)


def test_layout_module_stays_alive_for_runtime_guard(monkeypatch):
    root = "/workspace/.cadence_mcp"
    layout = "1" * 64
    binding = {"native_manifest_sha256": "2" * 64, "resource_domain_sha256": "3" * 64}
    identity = "4" * 64
    manifest = {
        "native_runtime_manifest_sha256": binding["native_manifest_sha256"],
        "resource_domain_sha256": binding["resource_domain_sha256"],
        "identity_manifest_sha256": identity,
    }
    worker = (
        "def private_bytes():\n"
        "    return 'fixture manifest'\n"
        "class Runtime(object):\n"
        "    def read_check(self):\n"
        "        return private_bytes()\n"
        "def load_runtime(expected):\n"
        f"    assert expected == {layout!r}\n"
        "    runtime = Runtime()\n"
        f"    runtime.root = {root!r}\n"
        f"    runtime.manifest = {manifest!r}\n"
        "    return runtime\n"
    ).encode("ascii")
    scope = {
        "layout_manifest_sha256": layout,
        "layout_worker_sha256": guest.sha(worker),
        "identity_manifest_sha256": identity,
    }
    loaded = []

    def track(name):
        module = ModuleType(name)
        loaded.append(weakref.ref(module))
        return module

    def read(path, limit):
        assert path == f"{root}/layout-runtime/{layout}/worker.py"
        assert limit == guest.LIMIT
        return worker

    monkeypatch.setattr(guest, "types", SimpleNamespace(ModuleType=track))
    monkeypatch.setattr(guest.os.path, "realpath", lambda value: value)
    monkeypatch.setattr(guest, "read_regular", read)

    runtime = guest.load_runtime(root, scope, binding)
    assert loaded[0]() is not None
    assert runtime.read_check() == "fixture manifest"


@pytest.mark.parametrize("fault", ["program", "scope", "prior", "authority", "extra"])
def test_fixed_guest_rejects_unbound_wire_before_loading_runtime(wire, fault):
    argv, body, _ = wire
    if fault == "program":
        body["program_base64"] = encoded(b"unreviewed")
    elif fault == "scope":
        body["binding"]["owned_library_path"] = "/workspace/Protected"
    elif fault == "prior":
        argv[2] = "1" * 64
    elif fault == "authority":
        ack = json.loads(base64.b64decode(body["authority_base64"]))
        ack["approved_phases"] = ["save", "reopen"]
        body["authority_base64"] = encoded(guest.canonical(ack))
    else:
        body["command"] = "unexpected"
    with pytest.raises(ValueError, match="research_generation_"):
        guest.parse_request(argv, guest.canonical(body))


def test_dut_projection_excludes_bench_and_rejects_incomplete_or_duplicate_groups():
    lines = [
        "global 0",
        "subckt Dut a z",
        "M0 (z a 0 0) pdk w=1u",
        "ends Dut",
        "VIN (a 0) vsource dc=0",
    ]
    assert guest.dut_projection(lines, ["Dut"]) == (
        b"simulator lang=spectre\nsubckt Dut a z\nM0 (z a 0 0) pdk w=1u\nends Dut\n"
    )
    for invalid in (lines[:3], lines + lines[1:4], ["subckt Bench a z", *lines, "ends Bench"]):
        with pytest.raises(ValueError):
            guest.dut_projection(invalid, ["Dut"])


@pytest.fixture
def stage(tmp_path, monkeypatch):
    instance = object.__new__(guest.GenerationPhase)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    job = tmp_path / "job"
    parent = workspace / "OwnedRun"
    program = b"fixed fixture\n"
    phase_markers = {
        "save": ["MOS_BLOCK_SAVED|fixture"],
        "reopen": ["MOS_BLOCK_REOPENED_CHECKED|fixture"],
        "netlist": ["MCP_GENERIC_ADE_NETLIST|fixture"],
    }
    instance.job, instance.store = job.as_posix(), (job / "research-generation").as_posix()
    instance.library, instance.parent = "/fixture-research-generation/Owned", parent.as_posix()
    instance.library_name, instance.dut, instance.bench = "Owned", "Dut", "Bench"
    instance.op = "11111111-2222-4333-8444-555555555555"
    instance.binding_sha = "f" * 64
    instance.claim = {"operation_id": instance.op}
    instance.binding = dict(
        scope_sha256="a" * 64,
        plan_sha256="b" * 64,
        save_program_sha256=guest.sha(program),
        reopen_program_sha256=guest.sha(program),
        netlist_program_sha256=guest.sha(program),
    )
    instance.scope = dict(
        schema_version=1,
        external_bytes=2097152, job_bytes=4194304, valid_until_unix=10**12, markers=phase_markers
    )
    instance.ops = SimpleNamespace(
        directory=lambda path, accounting: Path(path).mkdir(exist_ok=True)
    )
    instance.r = SimpleNamespace(
        profile={"tools": {"ocean": {"path": "/fixed/ocean"}}},
        accounting=object(),
        rendering=SimpleNamespace(token=lambda value: value),
    )
    instance.copy = SimpleNamespace(path=lambda value: value)
    instance.guard = lambda session: {"protected": "unchanged"}
    instance.maps = list
    instance.prepare = lambda phase, previous, work, maps: None
    instance.trees = lambda: {"library": "c" * 64, "dut": "d" * 64, "bench": "e" * 64}
    monkeypatch.setattr(guest, "read_regular", lambda path, limit: Path(path).read_bytes())
    calls = []

    def write(path, raw):
        with Path(path).open("xb") as output:
            output.write(raw)

    def ocean(guard, journal, argv, label, timeout, limit):
        assert argv[0] == "/fixed/ocean" and label == "ocean" and timeout == 45
        phase = Path(journal.work).parent.name
        calls.append(phase)
        write(
            Path(journal.work) / "ocean.stdout",
            b"Cadence banner \xc2\xa9\n" + (phase_markers[phase][0] + "\n").encode(),
        )
        write(Path(journal.work) / "ocean.stderr", b"")

    instance.eda = SimpleNamespace(write=write, program=ocean)
    return instance, program, calls


def test_guest_durable_predecessor_and_same_phase_refusal(stage):
    instance, program, calls = stage
    save = json.loads(instance.run(object(), "save", None, program))
    assert save["receipt"]["phase"] == "save"
    raw_stdout = base64.b64decode(save["stdout_base64"])
    assert raw_stdout.startswith(b"Cadence banner \xc2\xa9\n")
    assert save["receipt"]["artifact_sha256"] == guest.sha(raw_stdout)
    prior = guest.sha(guest.canonical(save["receipt"]))
    with pytest.raises(ValueError, match="research_generation_phase_already_started"):
        instance.run(object(), "save", None, program)
    with pytest.raises(ValueError, match="research_generation_predecessor_identity"):
        instance.run(object(), "reopen", "0" * 64, program)
    reopened = json.loads(instance.run(object(), "reopen", prior, program))
    assert reopened["previous_receipt_sha256"] == prior
    assert calls == ["save", "reopen"]


def test_non_ascii_marker_is_rejected_without_publishing_completion(stage):
    instance, program, calls = stage
    run_ocean = instance.eda.program

    def malformed_marker(guard, journal, *args):
        run_ocean(guard, journal, *args)
        stdout = Path(journal.work) / "ocean.stdout"
        stdout.write_bytes(stdout.read_bytes().rstrip() + b"\xff\n")

    instance.eda.program = malformed_marker
    with pytest.raises(ValueError, match="research_generation_markers"):
        instance.run(object(), "save", None, program)
    folder = Path(instance.store) / "save"
    assert not (folder / "complete.json").exists()
    assert json.loads((folder / "failure.json").read_bytes())["status"] == "OUTCOME_UNKNOWN"
    assert calls == ["save"]


def test_retained_inventory_pins_sizes_and_fingerprints_excluding_only_current_job(stage):
    instance, _, _ = stage
    instance.jobs = (Path(instance.job).parent / "retained").as_posix()
    for name in ("b-failure", instance.op, "a-complete"):
        Path(instance.jobs, name).mkdir(parents=True)
    observed = {
        "a-complete": (4, 4096, "a" * 64),
        "b-failure": (5, 4096, "b" * 64),
    }
    instance.eda.size = lambda path: observed[Path(path).name]
    initial = instance.original_jobs()
    assert initial == sorted(observed.items())
    observed["b-failure"] = (5, 4096, "c" * 64)
    assert instance.original_jobs() != initial


def test_guard_rejects_workspace_on_another_device_before_accounting(stage, monkeypatch):
    instance, _, _ = stage
    instance.root = "/fixture/.cadence_mcp"
    instance.workspace = "/fixture"
    instance.jobs = instance.root + "/jobs"
    instance.scope["operator_authority"] = "fixture"
    instance.r.read_check = lambda request: None
    instance.r.modules = {"confirmation": SimpleNamespace(authority_reference=lambda value: None)}
    instance.r.gate = SimpleNamespace(
        storage=SimpleNamespace(active_eda=lambda root, native: False)
    )
    instance.copy.directory = lambda path: SimpleNamespace(
        st_uid=500, st_mode=0o700, st_dev=2 if path == instance.workspace else 1
    )
    monkeypatch.setattr(
        guest,
        "os",
        SimpleNamespace(getuid=lambda: 500, path=SimpleNamespace(lexists=lambda path: True)),
    )
    with pytest.raises(ValueError, match="research_generation_filesystem_mismatch"):
        guest.GenerationPhase.guard(instance, SimpleNamespace(check=lambda: None))


def test_partial_guest_claim_never_relaunches_or_advances(stage):
    instance, program, calls = stage

    def fail(*args):
        calls.append("save")
        raise ValueError("fixture worker timeout")

    instance.eda.program = fail
    with pytest.raises(ValueError, match="fixture worker timeout"):
        instance.run(object(), "save", None, program)
    assert (
        json.loads((Path(instance.store) / "save/failure.json").read_bytes())["status"]
        == "OUTCOME_UNKNOWN"
    )
    for phase, prior in (("save", None), ("reopen", "1" * 64)):
        with pytest.raises(ValueError):
            instance.run(object(), phase, prior, program)
    assert calls == ["save"]


@pytest.mark.parametrize("drift", [False, True])
def test_netlist_stage_preserves_verified_full_input_and_dut(stage, drift):
    from cadence_mcp_bridge import _native_rendering
    from cadence_mcp_bridge.research_circuit import MosBlockStageReceipt

    instance, program, calls = stage
    previous_trees = instance.trees
    instance.trees = lambda: {**previous_trees(), "state": "7" * 64}
    full = b"simulator lang=spectre\nsubckt Dut a z\nM0 (z a 0 0) pdk w=1u\nends Dut\n"
    full += b"VIN (a 0) vsource dc=0\ndcOp dc\n"
    stat = _native_rendering.statements(full)
    instance.scope.update(
        dut_subcircuits=["Dut"],
        netlist_statements_sha256="0" * 64 if drift else guest.sha(guest.canonical(stat)),
    )
    prepare = instance.prepare

    def netlist_inputs(phase, previous, work, maps):
        if phase != "netlist":
            return prepare(phase, previous, work, maps)
        Path(work, "project").mkdir()
        Path(work, "project/input.scs").write_bytes(full)
        return "state", "7" * 64, "bench-copy", {"tree_sha256": "7" * 64}

    instance.prepare = netlist_inputs
    instance.eda.find_input = lambda project: project + "/input.scs"
    instance.copy.snapshot = lambda path: {"tree_sha256": "7" * 64}
    instance.r.modules = {"rendering": _native_rendering}
    prior = None
    for phase in ("save", "reopen"):
        row = json.loads(instance.run(object(), phase, prior, program))
        prior = guest.sha(guest.canonical(row["receipt"]))
    if drift:
        with pytest.raises(ValueError, match="research_generation_netlist_statement_drift"):
            instance.run(object(), "netlist", prior, program)
        assert not (Path(instance.store) / "netlist/complete.json").exists()
    else:
        row = json.loads(instance.run(object(), "netlist", prior, program))
        receipt = MosBlockStageReceipt.model_validate_json(guest.canonical(row["receipt"]))
        assert receipt.artifact_sha256 == guest.sha(full)
        assert base64.b64decode(row["full_netlist_base64"]) == full
        dut = base64.b64decode(row["dut_netlist_base64"])
        assert dut == guest.dut_projection(stat, ["Dut"])
        assert not row["stdout_base64"]
        assert (Path(instance.store) / "netlist/complete.json").exists()
    assert calls == ["save", "reopen", "netlist"]


def _static(worker):
    lines = ["subckt self_cascode_ota_17mos inp inn out VDD VSS"]
    for label in sorted(worker.OTA17_MOS):
        polarity = "nmos1v" if label.startswith("NM") else "pmos1v"
        lines.append(f"{label} (a b c d) gpdk090_{polarity} w=1u")
    lines.extend(
        (
            "ends self_cascode_ota_17mos",
            "DUT (inp inn out vdd 0) self_cascode_ota_17mos",
            "VINP (inp 0) vsource dc=0.5",
            "VINN (inn 0) vsource dc=500m",
            "VSUP (vdd 0) vsource dc=1",
            "CL (out 0) capacitor c=1p",
            "simulatorOptions options temp=27",
        )
    )
    return lines


def test_ota17_projection_protects_exact_terminals_and_model_at_each_named_element():
    worker = guest
    rows = _static(worker)
    expected = worker.ota17_topology(rows)
    sibling_permutation = rows[:1] + rows[1:18][::-1] + rows[18:19] + rows[19:24][::-1] + rows[24:]
    assert worker.canonical(worker.ota17_topology(sibling_permutation)) == worker.canonical(expected)
    changed_bulk = rows.copy()
    changed_bulk[1] = rows[1].replace("(a b c d)", "(a b c VDD)")
    assert worker.ota17_topology(changed_bulk) != expected
    changed_dut_pins = rows.copy()
    changed_dut_pins[19] = rows[19].replace("inp inn", "inn inp")
    assert worker.ota17_topology(changed_dut_pins) != expected


@pytest.mark.parametrize("mutation", ("missing", "duplicate", "wrong_model", "second_subckt", "source_shadow"))
def test_ota17_projection_rejects_wrong_inventory(mutation):
    worker = guest
    rows = _static(worker)
    if mutation == "missing":
        del rows[2]
    elif mutation == "duplicate":
        rows[2] = rows[1]
    elif mutation == "wrong_model":
        rows[1] = rows[1].replace("gpdk090_nmos1v", "gpdk090_pmos1v")
    elif mutation == "second_subckt":
        rows += ["subckt Foreign p n", "ends Foreign"]
    else:
        rows += ["UNREGISTERED (inp 0) vsource dc=0"]
    with pytest.raises(ValueError, match="research_generation_ota17_"):
        worker.ota17_topology(rows)
