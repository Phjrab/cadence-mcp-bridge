"""Offline checks of v2 writer isolation and the combined diagnostic gate."""

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from cadence_mcp_bridge import _native_rendering as rendering
from cadence_mcp_bridge import _ota_mos_candidate_runtime as original
from cadence_mcp_bridge import _ota_mos_candidate_v2_runtime as v2

OP = "cc20a49f-d79b-4d3c-80f5-224c015d36a0"
JOB = "/home/buet/jobs/" + OP
SELECTED = JOB + "/" + OP
DIGEST = "a" * 64
AC = dict(analysis="ac", start_hz="1", stop_hz="1000000000", points_per_decade=16)
DC = dict(analysis="dc", mode="saved_operating_point", statement_sha256=DIGEST)


def test_isolated_sessions_use_stock_rendering_and_distinct_settled_mode_markers():
    ac, ac_markers = v2._session_program(
        rendering, JOB, SELECTED, OP, DIGEST, "MCP_GREL_Work", "ac", AC
    )
    dc, dc_markers = v2._session_program(
        rendering, JOB, SELECTED, OP, DIGEST, "MCP_GREL_WorkDc", "dc", DC
    )
    for program, markers, mode, alias in (
        (ac, ac_markers, "ac", "MCP_GREL_Work"),
        (dc, dc_markers, "dc", "MCP_GREL_WorkDc"),
    ):
        assert b"exit(0)\n" not in program
        assert program.count(f'"{SELECTED}/{mode}/project"'.encode()) == 1
        assert program.count(f'"{SELECTED}/{mode}/state-root"'.encode()) == 2
        assert program.count(f'"{alias}"'.encode()) == 4
        assert ("asiGetAnalysis(session '" + mode + ")").encode() in program
        assert program.index(markers[0].encode()) < program.index(b"sevQuit(sevId)")
        assert program.index(b"sevQuit(sevId)") < program.index(markers[1].encode())
    assert set(ac_markers).isdisjoint(dc_markers)
    assert b"MCP_GREL_WorkDc" not in ac
    assert b'"MCP_GREL_Work"' not in dc
    assert b"/dc/" not in ac and b"/ac/" not in dc


def test_v1_runtime_is_unchanged_and_never_rebound_in_the_host(monkeypatch):
    raw = Path(original.__file__).read_bytes()
    fixture_skill = b"# offline parser input\n"
    monkeypatch.setattr(v2, "V2_SKILL_SHA256", original._sha(fixture_skill))
    verified = v2._load_base(raw, b"legacy", b"skill", fixture_skill)
    assert verified.CHILD == original.CHILD
    assert f"{v2.V2_HOLDER}/{original.CHILD}" == verified.CHILD_PATH
    assert f"{v2.V2_HOLDER}/{original.TB}_ADE" == verified.CHILD_STATE
    assert f"{v2.V1_HOLDER}/{original.CHILD}" == original.CHILD_PATH
    with pytest.raises(ValueError, match="v1_program"):
        v2._load_base(raw + b"\n", b"legacy", b"skill", fixture_skill)
    with pytest.raises(ValueError, match="v2_skill"):
        v2._load_base(raw, b"legacy", b"skill", fixture_skill + b"\n")


@pytest.mark.parametrize(
    ("field", "bad"),
    (
        ("schema_version", 2),
        ("job_limit_bytes", 4194305),
        ("supplemental_bytes", 0),
        ("clone_recovery", {}),
        ("writer_limit_bytes", 2621441),
        ("protected_v1_library_sha256", "untrusted"),
    ),
)
def test_clean_safety_rejects_out_of_scope_or_unaudited_copies(field, bad):
    native_safety = dict(
        schema_version=3,
        job_limit_bytes=4194304,
        supplemental_bytes=303104,
        clean_child=dict(
            writer_limit_bytes=2621440,
            protected_v1_library_sha256="1" * 64,
            protected_v1_state_sha256="2" * 64,
        ),
    )
    got = []

    def base_check(pin, route, legacy):
        got.append(pin)

    v2._verify_safety(native_safety, {}, None, base_check)
    assert got == [dict(schema_version=2, job_limit_bytes=4194304, supplemental_bytes=303104)]
    modified = deepcopy(native_safety)
    destination = modified["clean_child"] if field in modified["clean_child"] else modified
    destination[field] = bad
    with pytest.raises(ValueError, match="sealed_peak_safety"):
        v2._verify_safety(modified, {}, None, base_check)


def test_diagnostic_mode_requires_original_fixed_variables_and_enrolled_analysis():
    raw = (
        b"simulator lang=spectre\nparameters VBIASN=0.32 VBIASP=0.702\n"
        b'include "/approved/model.scs" section=NN\n'
        b"ac ac start=1 stop=1000000000 dec=16 annotate=status\n"
    )
    mode = dict(
        ade=dict(model_includes=[dict(path="/approved/model.scs", section="NN")], inputs=AC),
        libraries=[],
    )
    captured = []
    owner = object.__new__(v2._CleanOtaJob)
    owner.operation, owner.digest = OP, DIGEST
    owner.analysis = owner.dc = mode
    owner.digest_doc = lambda row: original._sha(original._canonical(row))
    owner.rt = SimpleNamespace(
        copying=SimpleNamespace(
            snapshot=lambda path: {"tree_sha256": path},
            dependency_snapshot=lambda path: {"tree_sha256": path},
        ),
        eda=SimpleNamespace(
            find_input=lambda root: root + "/input.scs",
            normalize_model_includes=lambda data, includes, libraries: data,
            write=lambda path, data: captured.append((path, data)),
        ),
        modules={"rendering": rendering},
    )
    owner.h = SimpleNamespace(read=lambda path, limit, reject_links: raw)
    paths = dict(
        project="ac-project",
        state="ac-state",
        bench="ac-bench",
        state_snapshot={"tree_sha256": "ac-state"},
        bench_snapshot={"tree_sha256": "ac-bench"},
    )
    before = {"dut": "observed-dut", "tb": "observed-bench"}
    result, proof = owner._mode_output("ac", paths, "/work", DIGEST, before, "c" * 64)
    assert result == raw and captured == [("/work/effective-input-ac.scs", raw)]
    assert proof["netlist_sha256"] == original._sha(raw)
    assert proof["dut_revision_sha256"] == before["dut"]
    assert proof["testbench_revision_sha256"] == before["tb"]
    raw = raw.replace(b"0.702", b"0.799")
    with pytest.raises(ValueError, match="spectre_explicit_parameters_mismatch"):
        owner._mode_output("ac", paths, "/work", DIGEST, before, "c" * 64)
    assert len(captured) == 1


def test_combined_peak_constrains_the_independent_writer_cap(monkeypatch):
    class SharedCapacity:
        def _capacity(self):
            return self.combined_remaining

    class Writer(v2._CleanOtaJob, SharedCapacity):
        pass

    owner = object.__new__(Writer)
    owner.job = "/owned/writer"
    owner.clean = {"writer_limit_bytes": 2621440}
    owner.combined_remaining = 2500000
    size = 90112
    owner.rt = SimpleNamespace(eda=SimpleNamespace(size=lambda path: (size, size, 0)))
    monkeypatch.setattr(v2, "os", SimpleNamespace(path=SimpleNamespace(lexists=lambda path: True)))
    assert owner._capacity() == 2500000
    owner.combined_remaining = 3500000
    assert owner._capacity() == 2621440
    size = 2600000
    with pytest.raises(ValueError, match="writer_capacity"):
        owner._capacity()


def test_v1_failed_job_guard_reuses_the_native_allocation_inventory(monkeypatch):
    class OriginalGuard:
        def _source_guard(self):
            pass

    class Writer(v2._CleanOtaJob, OriginalGuard):
        pass

    owner = object.__new__(Writer)
    owner.clean = dict(protected_v1_library_sha256="a" * 64, protected_v1_state_sha256="b" * 64)
    owner.library, owner.jobs, owner.dc = original.CHILD, "/owned/jobs", {}
    owner.request = {"ota_base": original}
    state_leaf = original.TB + "_ADE"
    owner.tree = lambda path: owner.clean["protected_v1_state_sha256"]
    samples = {
        v2.V1_HOLDER: (262144, 303104, "unused-holder-fingerprint"),
        **{owner.jobs + "/" + op: (0, charge, digest) for op, charge, digest in v2._V1_FAILED_JOBS},
    }
    owner.rt = SimpleNamespace(
        gate=SimpleNamespace(model_binding=lambda route: None),
        copying=SimpleNamespace(dependency_snapshot=lambda path: {"tree_sha256": "a" * 64}),
        eda=SimpleNamespace(size=samples.__getitem__),
    )
    monkeypatch.setattr(v2, "os", SimpleNamespace(listdir=lambda path: [state_leaf, owner.library]))
    owner._source_guard()
    old_job_path = owner.jobs + "/" + v2._V1_FAILED_JOBS[0][0]
    samples[old_job_path] = (0, samples[old_job_path][1], "wrong-footprint")
    with pytest.raises(ValueError, match="failed_v1_job"):
        owner._source_guard()
